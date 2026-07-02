import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.enums import ProcessingStatus, SourceFormat
from app.exceptions import DocumentNotFoundError, DocumentProcessingError
from app.models.document import Document
from app.models.truck import Truck
from app.schemas import (
    BatchUploadError,
    DocumentBatchUploadResponse,
    DocumentExtractionResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentReviewListResponse,
    DocumentReviewSubmitRequest,
    DocumentReviewSubmitResponse,
    DocumentUploadResponse,
)
from app.services.document_extraction import get_document_extraction
from app.services.document_review import apply_document_review
from app.services.queue import enqueue_document_job
from app.websocket.events import notify_document_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])

DOC_SORT_FIELDS = {
    "created_at": Document.created_at,
    "document_date": Document.document_date,
    "original_filename": Document.original_filename,
    "processing_status": Document.processing_status,
}


async def _document_response(db: AsyncSession, doc: Document) -> DocumentResponse:
    truck_unit = None
    if doc.truck_id:
        truck_unit = (
            await db.execute(select(Truck.unit_number).where(Truck.id == doc.truck_id))
        ).scalar_one_or_none()
    data = DocumentResponse.model_validate(doc)
    return data.model_copy(update={"truck_unit": truck_unit})


def _is_pdf(content: bytes, content_type: str | None) -> bool:
    if content_type == "application/pdf":
        return True
    return content.startswith(b"%PDF")


async def _save_and_queue(
    db: AsyncSession,
    upload: UploadFile,
) -> uuid.UUID:
    content = await upload.read()
    if len(content) > settings.max_upload_bytes:
        raise DocumentProcessingError(
            "File exceeds maximum upload size",
            error_code="FILE_TOO_LARGE",
            details={"max_bytes": settings.max_upload_bytes},
        )
    if not _is_pdf(content, upload.content_type):
        raise DocumentProcessingError(
            "File must be a PDF",
            error_code="INVALID_FILE_TYPE",
        )

    document_id = uuid.uuid4()
    filename = f"{document_id}.pdf"
    storage_dir = Path(settings.document_storage_path)
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / filename
    file_path.write_bytes(content)

    original_name = upload.filename or "upload.pdf"
    doc = Document(
        id=document_id,
        original_filename=original_name,
        file_path=str(file_path),
        file_size_bytes=len(content),
        source_format=SourceFormat.TEXT_PDF.value,
        processing_status=ProcessingStatus.QUEUED.value,
        tenant_id=1,
    )
    db.add(doc)
    await db.flush()

    try:
        await enqueue_document_job(
            document_id=document_id,
            file_path=str(file_path),
            original_filename=original_name,
            tenant_id=1,
        )
    except Exception as exc:
        doc.processing_status = ProcessingStatus.FAILED.value
        doc.error_details = f"Queue enqueue failed: {exc}"
        await db.commit()
        raise DocumentProcessingError(
            "Failed to enqueue document for processing",
            error_code="QUEUE_ENQUEUE_FAILED",
            details={"document_id": str(document_id)},
        ) from exc

    await db.commit()
    await notify_document_event(
        {
            "document_id": str(document_id),
            "status": ProcessingStatus.QUEUED.value,
            "filename": original_name,
            "progress": {"current_layer": 0, "total_layers": 7},
        }
    )
    return document_id


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    document_id = await _save_and_queue(db, file)
    return DocumentUploadResponse(document_id=document_id, status=ProcessingStatus.QUEUED.value)


@router.post("/upload/batch", response_model=DocumentBatchUploadResponse)
async def upload_documents_batch(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
) -> DocumentBatchUploadResponse:
    document_ids: list[uuid.UUID] = []
    errors: list[BatchUploadError] = []

    for upload in files:
        try:
            document_id = await _save_and_queue(db, upload)
            document_ids.append(document_id)
        except DocumentProcessingError as exc:
            errors.append(
                BatchUploadError(
                    filename=upload.filename or "unknown",
                    error_code=exc.error_code,
                    message=exc.message,
                )
            )
        except Exception as exc:
            errors.append(
                BatchUploadError(
                    filename=upload.filename or "unknown",
                    error_code="UPLOAD_FAILED",
                    message=str(exc),
                )
            )

    return DocumentBatchUploadResponse(document_ids=document_ids, errors=errors)


@router.get("/review", response_model=DocumentReviewListResponse)
async def list_review_queue(
    db: AsyncSession = Depends(get_db),
) -> DocumentReviewListResponse:
    result = await db.execute(
        select(Document)
        .where(Document.processing_status == ProcessingStatus.NEEDS_REVIEW.value)
        .order_by(Document.created_at.desc())
    )
    items = [DocumentResponse.model_validate(row) for row in result.scalars().all()]
    return DocumentReviewListResponse(items=items, total=len(items))


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    processing_status: str | None = None,
    processing_status_in: str | None = None,
    document_type: str | None = None,
    truck_id: uuid.UUID | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = settings.default_page_limit,
    offset: int = settings.default_page_offset,
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    limit = min(max(limit, 1), settings.max_page_limit)
    offset = max(offset, 0)

    query = select(Document)
    count_query = select(func.count()).select_from(Document)

    if processing_status:
        query = query.where(Document.processing_status == processing_status)
        count_query = count_query.where(Document.processing_status == processing_status)
    if processing_status_in:
        statuses = [s.strip() for s in processing_status_in.split(",") if s.strip()]
        if statuses:
            query = query.where(Document.processing_status.in_(statuses))
            count_query = count_query.where(Document.processing_status.in_(statuses))
    if document_type:
        query = query.where(Document.document_type == document_type)
        count_query = count_query.where(Document.document_type == document_type)
    if truck_id:
        query = query.where(Document.truck_id == truck_id)
        count_query = count_query.where(Document.truck_id == truck_id)

    total = (await db.execute(count_query)).scalar_one()
    sort_col = DOC_SORT_FIELDS.get(sort_by, Document.created_at)
    order = sort_col.desc() if sort_order == "desc" else sort_col.asc()
    result = await db.execute(query.order_by(order).limit(limit).offset(offset))
    docs = result.scalars().all()
    items = [await _document_response(db, row) for row in docs]

    return DocumentListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{document_id}/extraction", response_model=DocumentExtractionResponse)
async def document_extraction(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> DocumentExtractionResponse:
    return await get_document_extraction(db, document_id)


@router.get("/{document_id}/file")
async def get_document_file(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise DocumentNotFoundError(str(document_id))
    path = Path(doc.file_path)
    if not path.exists():
        raise DocumentNotFoundError(str(document_id))
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=doc.original_filename,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/{document_id}/review", response_model=DocumentReviewSubmitResponse)
async def submit_document_review(
    document_id: uuid.UUID,
    body: DocumentReviewSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> DocumentReviewSubmitResponse:
    return await apply_document_review(
        db,
        document_id,
        body.action,
        body.corrections,
        body.corrected_by,
        body.reprocess,
        body.reject_reason,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if doc is None:
        raise DocumentNotFoundError(str(document_id))
    return await _document_response(db, doc)
