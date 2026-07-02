# Phase 2 Implementation Notes

## Dataset

- Buildathon zip extracts to `data/sunflower/Buildathon_data_track_files/` (**197 PDFs** in provided archive; spec references 247).
- Image PDFs `document_064`–`document_068` confirmed zero text layer — see [`image_pdf_discovery.md`](image_pdf_discovery.md).

## Neo4j deviations (from phase2_spec Cypher)

- `REGISTERED_IN` / `TITLED_IN` use **relationship properties** (`state: 'Kansas'`) — no `State` nodes.
- Property name `pg_id` (not PROJECT.md `postgres_id`).
- Relationships: `MAINTAINED_AT`, `COVERED_BY`, `HAS_DOCUMENT`, `PURCHASED_FROM`, `SOLD_TO` (not PROJECT.md `SERVICED_BY` / `INSURED_UNDER`).

## Field overflow (no Phase 2 migrations)

| Fields | Storage |
|--------|---------|
| BOS notary fields | `raw_extracted_text` + `review_notes` JSON |
| IRP `issue_date` | Validation only; `registrations.effective_date` for period |
| IFTA `carrier_name` + extra jurisdiction columns | `review_notes` / `raw_extracted_text` |
| Title vehicle attrs | Enrich `trucks`; title row holds title metadata |
| Insurance plate/description | Validate against resolved `trucks` row |

## Dual-write policy

Postgres commits first. Neo4j writes retry 3×; on failure document → `failed` with `error_details` JSON and PG rows retained. Use `graph_writer.repair_document_graph(document_id)` stub for manual recovery.

## Wave-4 concurrency

Single worker container uses `asyncio.Semaphore(worker_concurrency)` (default 5). Waves 1–3 processed sequentially by bulk script before wave 4 batch.

## Embeddings

Local `sentence-transformers/all-mpnet-base-v2` (768-dim). Set `SKIP_EMBEDDINGS=true` in tests to avoid model download.
