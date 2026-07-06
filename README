# FleetMind

**Fleet document intelligence for trucking operators.** FleetMind ingests fleet paperwork—bills of sale, service invoices, insurance cards, registrations, CDLs, and more—extracts structured data with Gemini, links every record to the right truck, driver, and vendor, and surfaces it through a live dashboard and a conversational agent you can talk to in plain English.

Built for small-to-mid-size carriers (10–100 trucks) who today rely on filing cabinets, spreadsheets, and memory. Not a generic document manager. Not RAG-over-PDFs. A fleet operations brain grounded in your actual data.

---

## What you get

| Capability | Description |
|------------|-------------|
| **Document pipeline** | 7-layer extraction: read → classify → extract → validate → normalize → correct → graph write |
| **Fleet dashboard** | Fleet overview, per-truck detail, compliance matrix, vendor analysis, anomaly feed, entity graph |
| **Live updates** | WebSocket deltas when documents finish processing—no page refresh |
| **Conversational agent** | LangGraph orchestration, parallel sub-agent dispatch, streaming chat, session memory |
| **Intelligence layer** | Baselines, anomaly detection (cost spikes, compliance gaps, recurring issues), learning loops |
| **Dual data stores** | Postgres + pgvector for facts and aggregates; Neo4j for relationships |

Validated against the **Sunflower Freight Lines** synthetic dataset (~200 PDFs, 23 trucks, 20 drivers, 11 vendors).

---

## Architecture

### System topology

How the six Docker Compose services connect. The API owns user-facing traffic; the worker owns heavy document processing so chat and dashboards stay responsive.

```mermaid
flowchart TB
    subgraph Client["Browser"]
        UI["React Dashboard\n(Vite + Tailwind)"]
        Chat["Chat Sidebar\n(WebSocket stream)"]
    end

    subgraph API["FastAPI API Server :8000"]
        REST["REST Routers\nfleet · trucks · documents · compliance"]
        WS["WebSocket Hub\nlive deltas + chat"]
        Orch["Chat Orchestrator\nLangGraph + Gemini"]
        Agents["Sub-Agent Layer\n20+ typed query functions"]
        Notify["NOTIFY Listener\ndocument_events · intelligence_events"]
    end

    subgraph Worker["Extraction Worker"]
        Consumer["Redis Queue Consumer"]
        Pipeline["7-Layer Pipeline\nread → classify → extract → validate\n→ normalize → correct → graph"]
        IntelHook["Intelligence Hooks\nbaselines · anomaly detectors"]
    end

    subgraph Data["Data & Messaging"]
        PG[("PostgreSQL 16\n+ pgvector\nstructured fleet data")]
        Redis[("Redis 7\njob queue · chat sessions")]
        Neo4j[("Neo4j 5\nentity graph")]
    end

    UI -->|"HTTP REST"| REST
    UI -->|"WebSocket"| WS
    Chat --> WS

    REST --> Agents
    WS --> Orch
    Orch --> Agents
    Agents --> PG
    Agents --> Neo4j

    REST -->|"upload PDF"| Redis
    Redis --> Consumer
    Consumer --> Pipeline
    Pipeline --> PG
    Pipeline --> Neo4j
    Pipeline -->|"NOTIFY"| PG
    PG -->|"LISTEN"| Notify
    Notify -->|"push deltas"| WS
    Pipeline --> IntelHook
    IntelHook --> PG
    IntelHook -->|"NOTIFY"| PG

    Orch --> Redis
```

### Document ingestion flow

Every uploaded PDF travels through the extraction pipeline once, then fans out to structured storage, the knowledge graph, and live dashboard subscribers.

```mermaid
sequenceDiagram
    actor Op as Operator
    participant FE as Dashboard
    participant API as FastAPI
    participant RQ as Redis Queue
    participant WK as Worker
    participant GM as Gemini
    participant PG as Postgres
    participant N4 as Neo4j
    participant WS as WebSocket

    Op->>FE: Upload PDF
    FE->>API: POST /api/documents
    API->>RQ: Enqueue job
    API-->>FE: 202 Accepted

    WK->>RQ: Dequeue job
    WK->>GM: Classify + extract fields
    WK->>WK: Validate · normalize · correct
    WK->>PG: Write domain tables + embeddings
    WK->>N4: Upsert nodes & relationships
    WK->>PG: NOTIFY document_events

    PG->>API: LISTEN document_events
    API->>WS: Delta payload
    WS-->>FE: Live update (no refresh)

    Note over WK,PG: Intelligence hook recomputes<br/>baselines and runs anomaly detectors
```

### Conversational agent flow

Chat is not free-form RAG. Two Gemini calls bracket parallel sub-agent dispatch against the same APIs the dashboard uses.

```mermaid
flowchart LR
    subgraph Turn["Single chat turn"]
        M["Operator message"]
        Q1["LLM Call 1\nQuery understanding\nintent · entities · dispatch plan"]
        D["Parallel dispatch\nget_truck_* · get_fleet_* · get_anomaly_feed · …"]
        Q2["LLM Call 2\nResponse synthesis\nstreamed via WebSocket"]
        R["Grounded reply"]
    end

    subgraph Memory["Conversation memory"]
        Redis2[("Redis\nturn state · TTL session")]
        PG2[("Postgres\nmessages · summaries")]
        Prof["Operator profile\nfrequent entities · preferences"]
    end

    M --> Q1
    Q1 -->|"confidence < 0.6"| Clarify["Clarifying question"]
    Q1 -->|"confidence ≥ 0.6"| D
    D --> PG2
    D --> Neo4j2[("Neo4j\ngraph queries")]
    D --> Q2
    Q2 --> R
    Q1 --> Redis2
    R --> Redis2
    R --> PG2
    PG2 --> Prof
```

### Intelligence layer

Background jobs and event-driven hooks turn raw fleet data into baselines, anomalies, and weekly learning reports.

```mermaid
flowchart TB
    subgraph Triggers["Triggers"]
        Sched["APScheduler\ndaily baseline recompute\ncompliance scan · weekly report"]
        DocDone["Document complete hook\n(per ingested PDF)"]
        Unres["Unresolved item checker\nconversation follow-ups"]
    end

    subgraph Compute["Compute"]
        Base["Baseline engine\ntruck · fleet · vendor · driver metrics"]
        Det["Anomaly detectors\ncost spike · compliance gap · recurring issue\nvendor cost increase · …"]
        Learn["Learning loops\nextraction accuracy · query satisfaction\nanomaly calibration"]
    end

    subgraph Out["Outputs"]
        Feed["Anomaly feed API\n+ dashboard panel"]
        Admin["Admin health API\n/api/admin/health"]
        ChatAlert["Proactive chat alerts\ncritical compliance · warnings"]
    end

    Sched --> Base
    DocDone --> Base
    Base --> Det
    Det --> Feed
    Det --> ChatAlert
    Unres --> Det
    Sched --> Learn
    Learn --> Admin
```

| Component | Role |
|-----------|------|
| **API** | REST endpoints, WebSocket chat + live dashboard, chat orchestrator, Postgres NOTIFY listener |
| **Worker** | Redis consumer, 7-layer extraction, Postgres + Neo4j writes, intelligence hooks |
| **Frontend** | Fleet pages, document viewer, review queue, anomaly feed, chat sidebar |
| **Postgres** | Source of truth: trucks, events, documents, conversations, fleet_metrics, anomalies |
| **Neo4j** | Relationship traversal: vendor↔truck, driver assignments, graph explorer |
| **Redis** | Document queue, chat session state, compliance scan cache |

---

## Quick start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Compose v2)
- [Google Gemini API key](https://aistudio.google.com/apikey) for extraction and chat

### 1. Clone and configure

```bash
git clone https://github.com/weeklyweights-a11y/fleetmind.git
cd fleetmind
cp .env.example .env
```

Edit `.env` and set:

```env
GEMINI_API_KEY=your_key_here
```

### 2. Add the dataset (optional but recommended)

Place the Sunflower buildathon PDF archive at:

```
data/sunflower/Buildathon_data_track_files/
```

Or set `SUNFLOWER_DATASET_PATH` in `.env` to your local path (mounted read-only in Compose).

### 3. Start the stack

```bash
docker compose up -d --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 |

Migrations run automatically on API startup (`alembic upgrade head`).

### 4. Bulk import documents (first run)

```bash
docker compose exec api python scripts/bulk_import_sunflower.py
```

Watch the processing queue on the dashboard as the worker ingests PDFs.

### 5. Try the chat

Open the dashboard, use the chat sidebar, or connect a WebSocket client to `ws://localhost:8000/ws`.

Example prompts:

- *Tell me about truck 19*
- *Compare trucks 19 and 22*
- *Any compliance issues this week?*
- *Anything I should worry about?*

---

## Project layout

```
fleetmind/
├── backend/                 # FastAPI app, extraction pipeline, agents, intelligence
│   ├── app/
│   │   ├── agents/          # Sub-agent functions (truck, fleet, vendor, graph, …)
│   │   ├── chat/            # LangGraph conversational agent
│   │   ├── extraction/      # 7-layer document pipeline
│   │   ├── intelligence/    # Baselines, detectors, scheduled jobs
│   │   ├── routes/          # REST + WebSocket routers
│   │   └── worker/          # Redis queue consumer
│   ├── migrations/          # Alembic schema revisions
│   └── scripts/             # Import, acceptance verification
├── frontend/                # React dashboard (Vite)
├── data/                    # Local dataset mount (gitignored)
├── docker-compose.yml
└── .env.example
```

---

## Tech stack

| Layer | Technologies |
|-------|----------------|
| API | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic |
| AI | Google Gemini Flash, LangGraph, sentence-transformers |
| Data | PostgreSQL 16 + pgvector, Neo4j 5, Redis 7 |
| Frontend | React 18, Vite, Tailwind CSS, Recharts, react-force-graph |
| Infra | Docker Compose |

---

## Key environment variables

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Required for extraction and chat |
| `DATABASE_URL` | Async Postgres connection string |
| `REDIS_URL` | Document processing queue |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | Graph database |
| `DOCUMENT_STORAGE_PATH` | Uploaded PDF storage |
| `SUNFLOWER_DATASET_PATH` | Bulk import source directory |
| `VITE_API_URL` / `VITE_WS_URL` | Frontend API and WebSocket targets |

See `.env.example` for the full list.

---

## API overview

| Area | Base path |
|------|-----------|
| Health | `GET /api/health` |
| Fleet | `/api/fleet/*` |
| Trucks | `/api/trucks/{unit}/*` |
| Documents | `/api/documents/*` |
| Compliance | `/api/compliance/*` |
| Anomalies | `/api/anomalies` |
| Conversations | `/api/conversations/*` |
| Admin / learning | `/api/admin/*` |
| WebSocket | `ws://host/ws` |

Sub-agent-backed endpoints power both the dashboard and the chat agent—the same structured data, two interfaces.

---

## Development

### Run acceptance checks (inside API container)

```bash
docker compose exec api python scripts/verify_phase3_acceptance.py
docker compose exec api python scripts/verify_phase4_acceptance.py
docker compose exec api python scripts/verify_phase5_acceptance.py
docker compose exec api python scripts/verify_phase6_acceptance.py --mock
```

Phase 5/6 chat checks need `GEMINI_API_KEY` set; omit `--mock` on Phase 6 for full LLM verification.

### Backend tests

```bash
docker compose exec api python -m pytest tests/chat/ -q
docker compose exec api python -m pytest tests/intelligence/test_metrics_store.py -q
```

### Local frontend dev (API in Docker)

```bash
cd frontend && npm install && npm run dev
```

---

## Design principles

1. **Grounded answers** — Chat dispatches typed sub-agents against Postgres and Neo4j; the LLM synthesizes, it does not invent fleet facts.
2. **Real-time ops** — Processing completion pushes WebSocket deltas to subscribed dashboard views.
3. **Dataset-agnostic model** — Sunflower validates the system; schemas and extractors are built to generalize beyond one carrier’s templates.
4. **Separation of concerns** — Heavy extraction runs in a dedicated worker so API and chat stay responsive.

---

## License

Private / all rights reserved unless otherwise specified by the repository owner.

---

## Acknowledgments

Concept and validation dataset from the **PipeCode / Buildathon Dallas** trucking document intelligence challenge (Sunflower Freight Lines synthetic fleet).
