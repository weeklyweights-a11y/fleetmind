"""initial schema

Revision ID: 20260701_0001
Revises:
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op

from app.models import Base

revision: str = "20260701_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES_WITH_UPDATED_AT = [
    "vendors",
    "trailers",
    "trucks",
    "drivers",
    "documents",
    "assignments",
    "maintenance_events",
    "mileage_records",
    "registrations",
    "insurance_coverages",
    "titles",
    "emission_certs",
    "ifta_filings",
    "ifta_jurisdiction_details",
    "ifta_vehicle_details",
    "document_normalized_records",
    "document_chunks",
    "extraction_corrections",
    "conversations",
    "conversation_messages",
    "operator_profiles",
    "anomalies",
    "fleet_metrics",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    bind = op.get_bind()
    Base.metadata.create_all(bind)

    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    for table in TABLES_WITH_UPDATED_AT:
        op.execute(
            f"""
            DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};
            CREATE TRIGGER trg_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
            """
        )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_assignments_one_active_primary
        ON assignments (truck_id)
        WHERE end_date IS NULL AND assignment_type = 'primary';
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_document_chunks_document_chunk_index
        ON document_chunks (document_id, chunk_index);
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_truck_document_type
        ON document_chunks (truck_id, document_type);
        """
    )

    # pgvector uses HNSW (phase1 spec says GIN but HNSW is correct for pgvector)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw
        ON document_chunks USING hnsw (embedding vector_cosine_ops);
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_insurance_coverages_truck_expiry ON insurance_coverages (truck_id, expiry_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_maintenance_events_truck_service ON maintenance_events (truck_id, service_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mileage_records_truck_date ON mileage_records (truck_id, record_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_registrations_truck_expiry ON registrations (truck_id, expiry_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_registrations_truck_effective ON registrations (truck_id, effective_date)")


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
    op.execute("DROP FUNCTION IF EXISTS set_updated_at() CASCADE")
