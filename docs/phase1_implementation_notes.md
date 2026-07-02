# Phase 1 Implementation Notes

Cross-document naming follows `docs/phase1_spec.md` for Phase 1:

| phase1_spec | PROJECT / .cursorrules | Phase 1 decision |
|-------------|------------------------|------------------|
| `pg_id` | `postgres_id` | `pg_id` |
| `MAINTAINED_AT` | `SERVICED_BY` | `MAINTAINED_AT` |
| `COVERED_BY` | `INSURED_UNDER` | `COVERED_BY` |
| `HAS_DOCUMENT` | `EVIDENCED_BY` | `HAS_DOCUMENT` |

Deferred `phase1_spec.md` amendments (non-blocking):

1. pgvector index wording: HNSW not GIN
2. Redis structures: `ws_subscriptions` HSET + JSON; `chat_sessions` keyed strings with TTL
3. API contract section (status codes, pagination, multipart fields, max size)
4. Minimal NOTIFY payload JSON example
5. Phase 1 scope for DLQ/retry and graph integrity (log-only)
6. Acceptance #6 explicit table list
7. Worker acknowledge definition (= BRPOP consume)

Repo hygiene (post-Phase-1): sync `.cursorrules` model tree; create `docs/phase3–6_spec.md` stubs.
