# FleetMind — Fleet Document Intelligence Platform

## Vision

FleetMind turns a trucking fleet's paper trail into a living, queryable intelligence system. Fleet operators upload documents — bills of sale, service invoices, insurance certificates, driver licenses, registration cards, tax filings — and the platform extracts, validates, normalizes, and connects everything into a real-time operational dashboard backed by a conversational agent that lets them talk to their fleet in plain English.

This is not a document management system. This is not a chatbot over a vector store. This is a fleet intelligence platform where the system understands every truck, every driver, every dollar, every deadline — assembled automatically from raw documents, updated in real-time, and queryable through both visual dashboards and natural conversation.

---

## Problem Statement (Origin: PipeCode / Buildathon Dallas)

Trucking carriers run on paper. An active fleet generates 50+ documents every week — titles, tax forms, fuel records, registration renewals, maintenance receipts. Today it all lives in filing cabinets, glove boxes, and email threads. Nothing is searchable. Nothing is organized by truck.

Operators can't answer basic questions without digging through physical files: which trucks are profitable? How much did I spend on parts last month? Where's the tax form for truck 84? What documents do I need to renew these plates?

Build a system that ingests every fleet document, links each one to the correct truck, driver, and trailer, and lets an operator ask any question in plain English. Some questions need a database query, some need document retrieval, some need both in one answer. The system should handle all of them — accurately, grounded, no hallucinations.

— Nikhil Gurram, PipeCode.AI (Buildathon Dallas Sponsor)

---

## Target Users

**Primary: Fleet operators at small-to-mid-size trucking companies (10-100 trucks)**

These are owner-operators, fleet managers, or office managers who handle everything — driver compliance, maintenance scheduling, insurance renewals, tax filings, vendor relationships, cost tracking. They don't have dedicated IT staff. Their current system is filing cabinets, Excel spreadsheets, and memory.

**Secondary: Maintenance managers, compliance officers, dispatchers**

Larger fleets have specialized roles. Each needs a different view of the same data — maintenance managers care about service history and vendor costs, compliance officers care about expiry dates and regulatory documents, dispatchers care about truck availability and driver assignments.

---

## The Validation Dataset

**Sunflower Freight Lines LLC** — a fictional fleet company based in Wichita, Kansas, provided by Nikhil Gurram with approximately 200 real-format PDFs representing the complete document universe of a small fleet operation.

**Fleet composition:** 23 trucks total (16 active, 4 sold, 3 without current registration). 20 drivers (16 assigned to trucks, 4 unassigned/bench). 11 service vendors.

**247 documents across 8 types:**

**Bills of Sale (23 documents, 2 pages each):** 19 purchase transactions and 4 sale transactions. Each contains fleet unit number, VIN, year, make, model, body type, color, odometer, purchase/sale price, seller/buyer details, notarized signatures. Document numbering convention: BOS-YYMM-UnitNo. Four trucks were sold out of the fleet (units 47, 55, 63, 70), creating both purchase and sale records.

**Commercial Driver Licenses (20 documents, 2 pages each):** One per driver. Labeled "SCANNED DOCUMENT" but contain text layers. The header line encodes the driver-to-truck assignment: "CDL-D01 — D01 / FLEET 6" means Driver 01 is assigned to Fleet Unit 6. Four drivers (D17-D20) have FLEET = None, indicating unassigned/bench drivers. Each contains driver name, DL number, state, class, endorsements, restrictions, DOB, issue and expiry dates, physical description, address.

**Insurance ID Cards (20 documents, 1 page each):** All from Great West Casualty Company under a single fleet policy (GWCA-KS-77 04188). One card per active truck. Agent: Heartland Commercial Insurance. Each contains policy number, insurer, liability limit ($1M CSL), cargo limit ($100K), effective and expiry dates, unit number, vehicle description, license plate, VIN.

**Service Invoices (77 documents, 1 page each):** From 11 different vendors (Southern Tire Mart, Roadrunner Parts Supply, FleetPride, Love's Travel Stop, Wichita Brake & Parts, Petro Stopping Center, Diesel Emissions Co, Cummins Sales and Service, Volvo Trucks, Turbo Specialists, Rush Truck Center OKC). 14 service categories (Tires, Brakes, Suspension, Filters, Cooling, Lighting, Electrical, Air System, Engine, Emissions, Wheels, Warranty, Transmission, Fuel). All 77 are marked PAID with "PAID" stamps. Each contains vendor details, invoice number, date, PO number, unit number, service category, VIN, line items with quantities and pricing, labor cost, subtotal, tax, total, payment method, technician name.

**IRP Cab Cards (16 documents, 2 pages each):** Kansas IRP (International Registration Plan) apportioned registration for each active truck. Issued by Kansas Department of Revenue, Division of Vehicles, Motor Carrier Services Bureau. Each contains license plate number, plate state, VIN, vehicle description, registered gross weight (80,000 lbs), registration class, unit/equipment number, IRP account number, registration receipt number, effective and expiry dates, fee breakdowns (registration, property tax, IRP apportioned fee, title fee, total).

**Kansas Vehicle Titles (19 documents, 1 page each):** State certificate of title per truck. Issued by Kansas Department of Revenue, Division of Vehicles. Each contains title number, issue date, VIN, year, make, model, color, fuel type, body type, gross vehicle weight rating, odometer reading, owner name and address, lien holder status, previous title information, fleet unit number, title fee, control number.

**IFTA Quarterly Filings (3 documents, 2 pages each):** International Fuel Tax Agreement returns for quarters 2025Q3, 2025Q4, 2026Q1. Fleet-level filings with per-jurisdiction breakdowns (miles, gallons, tax rate, tax due/credit for each member jurisdiction). Per-vehicle sample data showing VIN, miles, and gallons for representative fleet units. Summary including total tax/credit due, average fleet fuel mileage (MPG).

**Image PDFs (5 documents, 1 page each):** Documents 064-068. No text layer — require visual/VLM extraction. Document types to be identified through visual inspection of rendered PNGs.

**Key observations about the data:**

All text-layer documents are machine-generated with consistent, predictable layouts within each document type. Service invoices share a common template across all vendors — same field layout, just different vendor names and line items. The document numbering system is systematic and encodes document type and fleet unit. VINs and fleet unit numbers appear on almost every document, making entity resolution straightforward for this dataset. The CDL header line explicitly maps drivers to trucks, which is a data feature specific to this dataset and not generalizable to all fleet operations.

**Critical note:** The data model must NOT be designed exclusively for this dataset's structure. Sunflower validates the system works. The architecture must handle any fleet company, any state, any vendor format, any document type.

---

## Architecture Overview

The system consists of six services connected through well-defined interfaces.

**Service 1: API Server (FastAPI)**

The central hub through which all communication flows. Serves REST endpoints for dashboard data and file uploads. Manages a WebSocket connection pool for live dashboard updates and chat streaming. Contains the chat orchestrator that dispatches LLM calls and sub-agent functions. Listens to Postgres NOTIFY channels for extraction pipeline completion events and routes relevant deltas to subscribed WebSocket clients. Queries both Postgres (structured/aggregation) and Neo4j (relationship traversal) through sub-agent functions.

**Service 2: Extraction Worker**

A separate process from the API server, dedicated to CPU/GPU-intensive document processing. Picks up processing jobs from a Redis queue and runs the 7-layer extraction pipeline. Writes extracted and normalized data to Postgres domain tables and synchronously updates the Neo4j graph with entity nodes and relationships. Emits completion events through Postgres NOTIFY with details about what changed (which entity, which tables, which graph relationships). Separated from the API server to prevent blocking dashboard and chat responsiveness during document processing.

**Service 3: Postgres + pgvector**

The structured source of truth. Contains all normalized domain tables, the documents audit trail, document text chunks with embeddings (pgvector), conversation history, and operator profiles. Serves as the internal event bus through LISTEN/NOTIFY channels between the extraction worker and the API server. Powers sub-agent functions that require typed columns, aggregations, date math, and financial computations.

**Service 4: Neo4j**

The relationship source of truth. Contains entity nodes (Truck, Driver, Vendor, Document, Trailer) and typed relationships (ASSIGNED_TO, SERVICED_BY, INSURED_UNDER, REGISTERED_WITH, EVIDENCED_BY, etc.) with temporal and provenance properties. Populated by Layer 7 of the extraction pipeline alongside Postgres writes — every entity link extracted from a document becomes a graph edge. Powers sub-agent functions that require multi-hop traversal, cross-entity path queries, and connected-component analysis. Entity nodes carry a `postgres_id` property linking back to the corresponding Postgres UUID for join-back when aggregation data is needed.

**Service 5: Redis**

Handles three categories of transient state. The job queue between the API server and extraction worker for document processing. WebSocket subscription state tracking which connections care about which data topics. Chat session state maintaining conversation context between turns (current entity focus, time window, intent, turn history).

**Service 6: React Frontend**

A single-page application providing the fleet operations dashboard, the conversational chat interface, and the document management/upload experience. Connects to the API server via REST for initial page loads and data fetches, and via WebSocket for live updates and chat. All dashboard components receive surgical updates through the WebSocket — individual numbers and panels update without page refresh.

**Inter-service communication:**

The React frontend communicates with the API server bidirectionally through WebSocket (live updates, chat messages) and through REST (initial data loads, file uploads). The API server communicates with the extraction worker through Redis (job queue). The extraction worker communicates completion back to the API server through Postgres NOTIFY channels. Both the API server and extraction worker read from and write to Postgres. Both the API server and extraction worker read from and write to Neo4j (worker writes during extraction; API reads for graph sub-agents). The API server reads from and writes to Redis for session and subscription state.

---

## Tech Stack

**Backend:** Python 3.12, FastAPI, asyncio for concurrent sub-agent execution and WebSocket handling

**Frontend:** React 18, Recharts for data visualization, native WebSocket API

**Document Parsing:** Docling (fast strategy for text-layer PDFs, hi-res for image PDFs with DocLayNet layout detection and TableFormer table extraction)

**Extraction Models:** Rule-based extraction with label dictionaries for text-layer PDFs. Gemini Flash Vision for image PDFs (5 documents in Sunflower dataset). Gemini Flash for agentic correction loop on validation failures.

**Database:** PostgreSQL 16 with pgvector extension for document text embeddings and structured domain data. Neo4j 5 for entity-relationship graph storage and traversal queries.

**Cache/Queue:** Redis for job queue, WebSocket subscription state, and chat session state

**LLM:** Gemini Flash for three specific tasks: (1) image PDF extraction, (2) agentic error correction on validation failures, (3) query understanding and response synthesis in the chat agent. The LLM is never the primary extractor for text-layer documents.

**Infrastructure:** Docker Compose orchestrating all six services. Local filesystem for document storage (S3/GCS path in production).

---

## Extraction Pipeline (7 Layers)

The extraction pipeline transforms raw PDF files into validated rows in normalized domain tables. Each layer solves a distinct computational problem. The LLM is involved in only one layer (Layer 6), and only when validation failures occur.

**Layer 1: Physical Reading**

Determines whether the PDF has a text layer or is image-based. For text-layer PDFs, PyMuPDF (fitz) extracts raw characters with their x,y coordinates on the page. For image-based PDFs, Docling's hi-res strategy with VLM mode processes the page image to recover text and positions. The output is a flat list of text spans with spatial coordinates. No understanding of meaning — just characters and where they sit.

**Layer 2: Layout Understanding**

Takes the text spans with positions and identifies the structural elements of the document. Docling's DocLayNet model detects and classifies layout regions: headers, section titles, key-value pairs, tables, paragraphs, footers. The output is a document structure tree — sections organized hierarchically with their content. The system now knows THAT there's a key labeled "VIN" with a value next to it, but doesn't yet know what a VIN means to the fleet.

**Layer 3: Field Extraction**

Applies a document-type-specific extraction schema to the structure tree from Layer 2. Document type is classified first (from document content keywords, header text, or document number prefix). Each document type has a target schema defining what fields to extract. For text-layer PDFs with consistent structure, extraction is rule-based — matching key text against label dictionaries per document type. For image PDFs or inconsistent layouts, Gemini Flash Vision handles extraction. The output is a raw JSON with schema fields populated as strings.

**Layer 4: Normalization**

Converts raw extracted strings into proper typed values. Dollar amounts strip currency symbols and commas, parse to decimal. Dates parse through multiple format patterns to ISO date. Odometer readings strip units and commas, parse to integer. VINs uppercase and strip whitespace. Fleet unit numbers parse to integer. This layer is entirely deterministic code — regex, type casting, format parsing. No models, no LLM.

**Layer 5: Validation**

Checks extracted data for internal consistency and plausibility. VIN check digit validation (position 9 is a mathematical function of the other 16 characters). VIN decode cross-reference (VIN manufacturer code must match extracted make). Dollar amount sum checks (line items should total to the stated grand total). Date plausibility (purchase date can't precede manufacture year, service date can't be in the future). Odometer consistency (readings should increase over time for the same truck, rate should be plausible for a commercial vehicle). Cross-field consistency (a 2016 International ProStar's VIN should start with "3HS" or similar Navistar prefix). Each check produces pass/fail with a confidence impact.

**Layer 6: Agentic Correction**

Activated ONLY when Layer 5 validation fails on specific fields. The LLM receives a narrow, constrained task: the validation failure details, the raw text around the problematic extraction, and common error patterns (OCR confusions like 2↔Z, 5↔S, 0↔O, 1↔l, 8↔B). The LLM reasons about which character is likely wrong and proposes a correction. The correction is verified against the validation algorithm (e.g., the corrected VIN must pass the check digit). If the LLM can correct confidently and the correction passes validation, the corrected value is stored with an audit note. If it cannot correct confidently, the document is flagged for human review with the specific field and failure highlighted.

**Layer 7: Semantic Enrichment and Normalization**

The extracted, validated data is written to the appropriate normalized domain tables in Postgres AND to the Neo4j graph. Postgres receives typed rows: a Bill of Sale creates or updates a row in the trucks table; a service invoice creates a row in maintenance_events and potentially a row in mileage_records; a CDL creates or updates a driver record and creates an assignment record; an insurance card creates or updates an insurance_coverages record. Neo4j receives corresponding nodes and relationships: entity nodes are MERGE'd by postgres_id, and relationships are created with temporal properties (start_date, end_date) and provenance (source_document_id, confidence). Example graph writes: a service invoice creates `(Truck)-[:SERVICED_BY {service_date, category, total_cost, source_document_id}]->(Vendor)` and `(Document)-[:EVIDENCED_BY]->(Truck)`; a CDL creates `(Driver)-[:ASSIGNED_TO {start_date, end_date, assignment_type}]->(Truck)`; an insurance card creates `(Truck)-[:INSURED_UNDER {effective_date, expiry_date}]->(Vendor)`. Each Postgres write also creates a record in the documents audit trail table linking the source document to the normalized records it produced. Finally, the extraction worker emits a Postgres NOTIFY event indicating what entity was affected, which tables changed, and which graph relationships were created or updated, triggering downstream WebSocket updates.

---

## Data Model (Normalized Domain Tables)

The data model encodes the trucking domain, not the Sunflower dataset specifically. Fixed columns for universally-applicable attributes. The design supports any fleet company, any state, any number of trucks, any combination of document types.

**Asset Tables**

trucks: Represents a physical vehicle in the fleet. Core identity fields (unit_number as the fleet's internal identifier, VIN as the universal identifier), vehicle description (year, make, model, body_type, color), acquisition details (acquired_date, purchase_price, acquired_from_vendor_id, initial_odometer), disposition details (disposed_date, sale_price, disposed_to, disposal_type), and operational status (active, inactive, sold). One row per vehicle that has ever been in the fleet.

trailers: Same pattern as trucks for trailer assets. Unit identifier, VIN, type (dry van, reefer, flatbed), year, make, model, status. Not populated in the Sunflower dataset but the table exists for fleets that track trailers.

**People Tables**

drivers: Represents a driver. Identity fields (name, address, date_of_birth), license details (license_number, license_state, license_class, endorsements, restrictions, license_issue_date, license_expiry_date), physical description (sex, height, weight, eye_color), medical certification details (medical_cert_expiry_date if that document type exists), and operational status (active, inactive, terminated).

**Relationship Tables**

assignments: Temporal links between drivers and trucks (and optionally trailers). Each row represents a period during which a specific driver was assigned to a specific truck. Fields: truck_id, driver_id, trailer_id (nullable), start_date, end_date (nullable — null means current assignment), assignment_type (primary, team, substitute, inferred), source_document_id (which document established this assignment), confidence score.

Multiple concurrent assignments are possible (team driving). Historical assignments are preserved, never deleted — end_date is set when a reassignment occurs. The current assignment for a truck is the row where end_date IS NULL.

**Operational Tables**

maintenance_events: Every service, repair, or maintenance action performed on a truck. One row per service invoice. Fields: truck_id, vendor_id, service_date, category (Tires, Brakes, Engine, etc.), description (the actual service performed), parts_cost, labor_cost, total_cost, payment_status, payment_method, technician_name, invoice_number, po_number. This table powers the maintenance analytics, cost tracking, vendor analysis, and pattern detection.

mileage_records: Odometer snapshots extracted from various documents. truck_id, date, odometer_reading, source_document_id. Used to compute miles driven between service intervals, cost per mile, and validate odometer consistency across documents.

**Compliance Tables**

registrations: State and IRP registration records. truck_id, state, registration_type (state, IRP apportioned), registration_number, plate_number, plate_state, effective_date, expiry_date, registered_weight, registration_class, irp_account_number, fees_paid (broken down by registration, property tax, IRP apportioned, title). One row per registration period per truck.

insurance_coverages: Per-vehicle insurance records. truck_id, policy_number, insurer_name, insurer_vendor_id, agent_name, coverage_type (Commercial Auto Liability, Cargo, etc.), liability_limit, cargo_limit, effective_date, expiry_date. One row per coverage period per truck. A fleet under a single policy has the same policy_number across all trucks but separate rows per truck.

titles: Vehicle title records. truck_id, title_number, title_state, issue_date, lien_holder (None if clear), previous_title_number, previous_title_state, control_number, title_fee.

emission_certs: Emission test/certification records. truck_id, test_date, result (pass/fail), next_due_date, testing_facility, certificate_number. Not present as a separate document type in Sunflower (emission work appears as service invoices), but the table exists for fleets that have standalone emission certificates.

**Tax/Financial Tables**

ifta_filings: Quarterly IFTA returns. Filing-level data: ifta_account_number, quarter (e.g., "2025Q3"), filing_date, total_fleet_miles, total_fleet_gallons, total_tax_due, average_fleet_mpg, penalty, interest, balance_due.

ifta_jurisdiction_details: Per-jurisdiction breakdown within a filing. filing_id, jurisdiction_name, jurisdiction_miles, jurisdiction_gallons, tax_rate, tax_due_or_credit, surcharge.

ifta_vehicle_details: Per-vehicle data within a filing. filing_id, truck_id (resolved from VIN), vin, miles, gallons.

**Reference Tables**

vendors: Every external entity the fleet does business with. name, address, phone, vendor_type (service/repair, equipment_dealer, insurance_company, fuel_stop, parts_supplier, leasing_company). Vendors are created automatically during extraction when a new vendor name appears.

**Document Audit Trail**

documents: Every ingested file. original_filename, file_path (local or object storage), source_format (text_pdf, image_pdf, photo), parse_method (docling_fast, docling_hires, gemini_vision), document_type (bill_of_sale_purchase, bill_of_sale_sale, cdl, insurance_card, service_invoice, irp_cab_card, title, ifta_filing), document_number, document_date, processing_status (queued, parsing, extracting, validating, complete, failed, needs_review), review_status (pending, approved, corrected), truck_id (nullable — resolved entity link), driver_id (nullable), vendor_id (nullable), parse_confidence, entity_resolution_confidence, created_at, updated_at.

document_normalized_records: Junction table tracking which normalized records were created from which document. document_id, target_table (e.g., "maintenance_events"), target_record_id. This enables tracing any data point back to its source document, and cascading corrections or deletions when a document is re-processed or removed.

document_chunks: Text chunks with vector embeddings for semantic search. document_id, chunk_index, chunk_text, embedding (vector), truck_id, driver_id, document_type, document_date. Metadata fields are denormalized from the parent document to enable filtered vector search.

**Extraction Quality Tracking**

extraction_corrections: Logs every human correction for learning loop analysis. document_id, field_name, original_value, corrected_value, correction_source (human, agentic_layer6), corrected_at, corrected_by.

**Conversation Tables**

conversations: Each chat session. operator_name (simple string for MVP), started_at, ended_at, entities_discussed (array of entity references), topics (array of topic tags), key_findings (array of summary statements), unresolved_items (array of flagged follow-ups), summary_text.

conversation_messages: Individual messages within a conversation. conversation_id, role (user, assistant), content, tools_called (structured record of which sub-agent functions the agent invoked), created_at.

operator_profiles: Long-term behavioral memory per operator. name, frequent_entities, frequent_topics, preferred_response_style, typical_session_patterns, total_conversations, last_active.

**Anomaly Tracking**

anomalies: System-detected anomalies from the fleet intelligence layer. anomaly_type (cost_spike, efficiency_decline, frequency_unusual, compliance_gap, missing_document), entity_type (truck, driver, vendor), entity_id, description, severity (info, warning, critical), supporting_data (the numbers and comparisons that triggered the detection), status (new, acknowledged, investigating, dismissed), operator_feedback, detected_at, resolved_at.

---

## Graph Model (Neo4j)

The graph model mirrors the fleet domain's entity relationships. Postgres holds typed attributes and aggregations; Neo4j holds the connective tissue between entities. Every graph node includes `tenant_id` (integer, set to 1 for MVP) and `postgres_id` (UUID linking to the Postgres row).

**Node Labels**

Truck: unit_number, vin, status, year, make, model. Driver: name, license_number, license_state, status. Vendor: name, vendor_type. Document: document_type, document_number, document_date, processing_status. Trailer: unit_number, vin, trailer_type, status.

**Relationship Types**

ASSIGNED_TO (Driver → Truck): start_date, end_date, assignment_type, source_document_id, confidence. SERVICED_BY (Truck → Vendor): service_date, category, total_cost, invoice_number, source_document_id. INSURED_UNDER (Truck → Vendor): policy_number, effective_date, expiry_date, source_document_id. REGISTERED_WITH (Truck → Vendor or jurisdiction node): effective_date, expiry_date, plate_number, registration_type, source_document_id. TITLED_AS (Truck → Document): title_number, issue_date, source_document_id. EVIDENCED_BY (Document → Truck | Driver | Vendor): the provenance link from any ingested document to the entities it establishes or updates. ACQUIRED_FROM (Truck → Vendor): acquired_date, purchase_price, source_document_id. DISPOSED_TO (Truck → Vendor/party): disposed_date, sale_price, source_document_id.

**Query Split Rationale**

Postgres answers "how much," "when does it expire," "what is the total" — anything requiring SUM, AVG, COUNT, date arithmetic, or typed column filters. Neo4j answers "what connects to what," "show me the path," "which entities share a relationship" — anything requiring variable-depth traversal, path finding, or pattern matching across entity types. Sub-agent functions that need both (e.g., "show everything connected to truck 19 with maintenance totals") run a Neo4j traversal first to gather connected entity IDs, then fan out to Postgres aggregation sub-agents via asyncio.gather.

---

## Sub-Agent Functions

Sub-agents are Python functions, not LLM-powered agents. They run SQL queries against Postgres, Cypher queries against Neo4j, or both — then perform computations on the results and return structured dictionaries. The LLM is never involved in sub-agent execution. The same functions power both the dashboard API endpoints and the conversational agent's data gathering.

**Postgres-backed sub-agents (structured data and aggregation):**

**get_truck_identity(truck_id):** Queries the trucks table. Returns unit number, VIN, year, make, model, color, status, acquisition details, disposition details if sold.

**get_truck_assignment(truck_id):** Queries assignments joined with drivers. Returns current driver with their details and assignment start date, plus a list of previous drivers with date ranges. Handles the case where a truck has no current assignment (sold or unassigned).

**get_truck_maintenance(truck_id, time_range, trend):** Queries maintenance_events. Returns total spend, event count, average cost per event, last service details, breakdown by category (list of categories with count and total spend), breakdown by vendor (list of vendors with count and total spend). When trend is requested, returns monthly spend over time for charting. Includes fleet comparison — this truck's metrics vs fleet-wide averages.

**get_truck_compliance(truck_id):** Queries insurance_coverages, registrations, titles, emission_certs. For each compliance category, returns the latest record, its expiry date, days until expiry, and a status flag (green if 30+ days remaining, yellow if under 30 days, red if expired, grey if no record on file).

**get_truck_financials(truck_id):** Combines data across trucks (purchase_price), maintenance_events (total maintenance spend), registrations (total fees), ifta_vehicle_details (fuel data if available). Computes total cost of ownership, cost breakdown by category, cost per mile if odometer data exists, depreciated book value if age-based depreciation is applicable.

**get_truck_documents(truck_id):** Queries the documents table grouped by document_type. Returns counts per type and a list of documents with dates, types, and file paths for linking to original PDFs.

**get_fleet_overview():** Fleet-wide aggregation. Total trucks (active, inactive, sold), total drivers (assigned, unassigned), compliance summary (how many trucks are fully compliant, how many have warnings or expirations), fleet-wide financial summary (total maintenance spend this month vs last month vs rolling average), recent document processing activity.

**get_fleet_comparison(truck_ids):** Runs financial and maintenance analysis for multiple trucks and returns a comparative ranking. Total cost of ownership, maintenance frequency, cost per mile (if available), compliance status side-by-side.

**get_compliance_matrix():** Runs get_truck_compliance for every active truck and assembles the compliance grid — trucks as rows, compliance categories as columns, each cell colored green/yellow/red/grey.

**get_driver_profile(driver_id):** Queries drivers table plus assignment history plus any driver-specific compliance (CDL expiry, medical cert if tracked). Returns identity, current and historical truck assignments, license details, compliance status.

**get_vendor_analysis(vendor_id or all):** Queries maintenance_events grouped by vendor. Returns spend per vendor, frequency, which trucks each vendor services, average cost per service, and cost trend over time.

**get_anomaly_feed(filters):** Queries anomalies table for active (non-dismissed) anomalies, sorted by severity and recency. Each anomaly includes the description, supporting data, affected entity, and available actions (acknowledge, investigate, dismiss).

**get_memory_search(query, operator):** Searches conversation history for past discussions matching the query. Returns relevant conversation summaries with entities discussed, key findings, and unresolved items. Used by the chat orchestrator when the operator references past conversations.

**Neo4j-backed sub-agents (relationship traversal and cross-entity queries):**

**get_truck_connections(truck_id, depth):** Graph traversal from a Truck node. Returns all connected entities (drivers, vendors, documents, trailers) grouped by relationship type, with relationship properties (dates, costs, document types). Answers "show me everything connected to truck 19."

**get_truck_history_graph(truck_id):** Temporal path query across all relationships involving a Truck node, ordered chronologically. Returns a timeline of graph events: assignments, service events, insurance periods, registrations, document ingestions, acquisitions, dispositions. Answers "trace the full history of truck 19."

**get_multi_truck_drivers():** Pattern match query finding Driver nodes connected via ASSIGNED_TO to more than one Truck node (across all time or within a date range). Returns driver identity, list of trucks with assignment date ranges, and current assignment status. Answers "which drivers have worked on multiple trucks."

**get_vendor_truck_map(vendor_id or all):** Traverses SERVICED_BY relationships from Vendor nodes to Truck nodes. Returns vendor identity, list of trucks serviced, service event count per truck, date range of service relationship. Answers "which vendors service which trucks."

**get_fleet_graph(filters):** Returns the full fleet graph or a filtered subgraph (by entity type, status, date range) as nodes and edges suitable for visualization. Powers the Fleet Graph dashboard view. Includes layout hints (entity type, relationship type, temporal properties).

**get_entity_path(source_type, source_id, target_type, target_id):** Shortest-path or all-paths query between two entity nodes. Returns the connecting path with intermediate nodes and relationship properties. Answers cross-entity questions like "how is driver D03 connected to vendor Southern Tire Mart?"

---

## Conversational Agent Architecture

The conversational agent uses the LLM for exactly two tasks: understanding what the operator asked (query understanding) and presenting the results as natural language (response synthesis). Everything between these two LLM calls is deterministic sub-agent function execution.

**Query Understanding (LLM Call 1):**

The operator's message plus conversation context (current entity focus, current time window, current intent from prior turns, operator profile) is sent to the LLM. The LLM returns a structured classification: which entity is being referenced (resolving pronouns, references like "that truck," implicit carryover from prior turns), what time scope applies (resolving "last month," "since we bought it," "recently"), what type of answer is needed (fact, number, document, comparison, status check, explanation), and which sub-agent functions should be dispatched.

**Sub-Agent Dispatch (No LLM):**

The orchestrator calls the identified sub-agent functions in parallel using asyncio. For broad entity questions ("tell me about truck 19"), all relevant sub-agents fire simultaneously. For focused questions ("how much did maintenance cost"), only the relevant sub-agent fires. The orchestrator waits for all dispatched functions to return structured dicts.

**Response Synthesis (LLM Call 2):**

All sub-agent results are passed to the LLM along with the original question and operator preferences. The LLM generates a natural language response that prioritizes the most important information (urgent compliance issues before routine stats), cites source documents where relevant, and adapts to the operator's communication style.

**Conversation Memory:**

Turn-level context (within a session): Maintained in Redis as part of the chat session state. Tracks current entity focus, time window, intent, and results from prior turns. Enables follow-up resolution ("what about truck 22" carries the prior intent, "show me the expensive one" references prior results).

Conversation memory (across sessions): When a conversation ends, the system generates a structured summary (entities discussed, topics, key findings, unresolved items) and stores it in the conversations table. When a new session starts, recent conversation summaries are loaded. When the operator references past discussions, the get_memory_search function retrieves relevant history.

Operator profile (long-term): Updated incrementally after each conversation. Tracks frequent entities, frequent topics, preferred response style, and typical session patterns. Loaded at session start to personalize the agent's behavior.

---

## Dashboard Architecture

The dashboard is the operator's fleet command center. Every visual component maps to a sub-agent function. Data flows from Postgres and Neo4j through sub-agent functions through REST API endpoints to React components, with WebSocket providing live update deltas.

**Fleet Overview Page (Landing Page):**

Fleet stats cards (truck count by status, driver count by assignment status, fleet value). Compliance matrix preview (count of green/yellow/red across all trucks). Monthly cost summary with month-over-month comparison. Upcoming deadlines list (next N compliance expirations, sorted by urgency). Recent document activity (last N documents processed with status). Anomaly feed (active anomalies sorted by severity).

**Truck Detail Page:**

Identity panel (unit number, VIN, make/model/year, color, status, photo if available). Assignment panel (current driver with CDL details, assignment history timeline). Maintenance panel (total spend and event count, timeline of service events, breakdown by category as a chart, breakdown by vendor, fleet comparison indicator). Compliance panel (green/yellow/red indicators for insurance, registration, title, emissions with expiry dates and days remaining). Financial panel (total cost of ownership with breakdown, cost per mile if odometer data exists). Documents panel (grouped list of all source documents with links to view original PDFs).

**Driver Detail Page:**

Identity panel (name, CDL details, address, physical description). License compliance (CDL expiry status, endorsements, restrictions). Assignment history (which trucks, date ranges). Performance indicators (if data supports — maintenance correlation, fuel efficiency correlation).

**Compliance Matrix Page:**

Full-fleet grid. Rows: every active truck. Columns: insurance, registration, emissions, driver CDL, medical cert. Each cell: green (30+ days), yellow (under 30 days), red (expired), grey (no record). Countdown list below the matrix sorted by urgency. Clicking any cell navigates to the relevant detail or opens the source document.

**Financial Analytics Page:**

Fleet-wide cost of ownership over time (line chart). Cost breakdown by category across the fleet (stacked bar). Per-truck cost comparison (horizontal bar chart, sorted). Vendor spend analysis (which vendors, how much, how often). Acquisition timeline (when trucks were bought, at what price and mileage).

**Anomaly Feed Page:**

List of system-detected anomalies with severity indicators. Each anomaly shows the description, the supporting data (the numbers that triggered it), the affected entity with a link to its detail page. Operator actions: acknowledge, investigate (adds to unresolved items for follow-up), dismiss (feeds learning loop with reason).

**Fleet Graph Page:**

Interactive graph visualization powered by get_fleet_graph() from Neo4j. Displays trucks, drivers, vendors, and documents as nodes with typed relationships as edges — assignments, service events, insurance links, document provenance. Filterable by entity type, truck status, and date range. Clicking a node navigates to the relevant detail page (Truck Detail, Driver Detail) or opens the source document. Clicking an edge shows relationship properties (assignment dates, service costs, policy periods). When extraction adds or updates graph relationships, the visualization receives surgical delta updates through the WebSocket fleet_graph topic — new nodes and edges appear without reloading the full graph.

**Chat Interface:**

Slide-out sidebar or panel accessible from any dashboard page. The operator can view a dashboard panel, notice something, and immediately ask the chat about it without navigation. Chat messages stream in real-time through WebSocket. The chat has access to the same data as the dashboard — clicking a red compliance cell could pre-populate a chat question about that truck's compliance status.

**Upload and Processing Experience:**

Persistent upload zone accessible from any page (drag-and-drop or click-to-browse). Supports single files and batch uploads. Processing queue visible as a persistent panel showing each document's progress through the extraction pipeline (queued → parsing → extracting → validating → complete/needs review). Status updates arrive through WebSocket in real-time. Completed documents show a summary of what was extracted. Documents needing review are flagged and accessible in a review queue with the original PDF alongside extracted data and highlighted problem fields.

---

## WebSocket Event System

The WebSocket connection serves three purposes: live dashboard updates, chat message streaming, and document processing status.

**Connection Lifecycle:**

When the operator opens the dashboard, the browser establishes a WebSocket connection to the API server. The connection persists across page navigation within the SPA. If the connection drops (network interruption, server restart), the frontend automatically reconnects and re-subscribes to the appropriate topics for its current view.

**Topic Subscription Model:**

The frontend subscribes to data topics based on the current view. On the fleet overview page: fleet_stats, compliance_overview, recent_documents, anomalies. On the fleet graph page: fleet_graph. On truck 19's detail page: truck_19_identity, truck_19_assignment, truck_19_maintenance, truck_19_compliance, truck_19_financials, truck_19_documents, truck_19_connections. When navigating between pages, the frontend unsubscribes from old topics and subscribes to new ones.

**Delta Push Model:**

When data changes (a document is ingested, a correction is applied, an anomaly is detected), the API server identifies which topics are affected, finds which connections are subscribed to those topics, computes the relevant data deltas, and pushes them. Deltas are granular — "truck 19 maintenance total changed from $31,280 to $36,360" rather than "truck 19 data changed." The frontend applies deltas surgically to specific React component state without re-rendering the entire page.

**Event Flow from Extraction to Dashboard:**

Extraction worker completes document processing and writes to normalized Postgres tables and Neo4j graph. Worker emits Postgres NOTIFY with payload describing the affected entity, tables, and graph relationships. API server receives the notification on its LISTEN channel. API server determines which topics are affected. API server runs the relevant sub-agent function(s) to compute fresh data for affected topics. API server computes delta between previous state (cached) and new state. API server pushes delta to all WebSocket connections subscribed to the affected topics. Frontend receives delta and updates specific component state/DOM elements.

**Chat Message Flow:**

Operator sends a chat message through the WebSocket. API server receives it, loads conversation state from Redis, invokes the chat orchestrator. As the LLM generates the synthesis response, tokens stream back through the WebSocket to the chat component for real-time rendering. Tool call results (which sub-agents were invoked, what they returned) are also sent for transparency if desired. The conversation state is updated in Redis after each turn.

---

## Learning Loops

**Loop 1 — Extraction Accuracy:**
Every human correction on the review queue is stored in the extraction_corrections table. Over time, correction patterns reveal which document types, vendors, or fields consistently cause extraction errors. These patterns inform validation rule refinements and, in future phases, model retraining. Tracked metric: extraction accuracy rate (documents passing validation without human correction / total documents processed).

**Loop 2 — Entity Resolution Confidence:**
Every document-to-entity link is stored with a confidence score and the resolution method used (deterministic, rule-based, inferred). Human confirmations on ambiguous links provide labeled data for tuning resolution parameters. Tracked metric: auto-resolution rate and human review rate.

**Loop 3 — Query Understanding:**
Conversation failures (where the operator corrects the agent's interpretation) are logged with the original query, wrong interpretation, and correction. Patterns feed into the operator profile and the agent's default interpretations. Tracked metric: first-response satisfaction rate (how often the agent's first answer addresses the question without clarification).

**Loop 4 — Fleet Intelligence:**
As documents accumulate, the system builds statistical baselines per truck, per driver, per vendor — maintenance cost averages, service frequencies, fuel efficiency norms. Anomaly detection compares incoming data against these baselines using statistical deviation (standard deviations above/below mean). Operator feedback on anomalies (acknowledged vs dismissed) calibrates detection sensitivity. Tracked metrics: anomaly precision (acted upon / total surfaced) and recall (problems found by operator that system missed).

**Loop 5 — Document Type Evolution:**
When the system encounters a document it cannot classify, it flags it as unknown. After multiple unknown documents of similar structure accumulate, the system can alert the operator to define a new document type. This loop enables the platform to grow its capability without developer intervention.

---

## Phasing

**Phase 1 — Foundation:**
Database schema (all normalized Postgres tables), Neo4j graph schema (node labels, relationship types, indexes), Postgres + pgvector + Neo4j + Redis setup, Docker Compose configuration (six services), project directory structure, FastAPI application skeleton, basic file upload endpoint, document status tracking.

**Phase 2 — Extraction Pipeline:**
All 7 extraction layers, document type classification, rule-based extraction for each of the 8 Sunflower document types, Gemini Vision for image PDFs, normalization, validation with check digit and cross-field checks, agentic correction loop, entity resolution (unit number and VIN lookup), human review queue logic, dual-write to Postgres and Neo4j in Layer 7. Process all 247 Sunflower PDFs and populate normalized tables and graph.

**Phase 3 — Sub-Agents + API Layer:**
All sub-agent functions implemented and tested (Postgres-backed aggregation sub-agents and Neo4j-backed traversal sub-agents), REST endpoints wrapping each function, parallel execution with asyncio, API documentation. After this phase, the complete fleet intelligence is accessible via API.

**Phase 4 — Dashboard + WebSocket:**
React application with all pages and components (including Fleet Graph visualization), WebSocket connection and subscription management, live delta updates from extraction pipeline to dashboard and graph view, file upload UI with processing queue, document viewer (PDF rendering alongside extracted data), progressive panel rendering. After this phase, the operator has a live fleet command center.

**Phase 5 — Conversational Agent:**
Chat orchestrator with LLM integration (query understanding + synthesis), sub-agent dispatch based on intent classification, conversation memory (turn-level, cross-session, operator profile), chat UI integrated into the dashboard as a sidebar, streaming response rendering. After this phase, the operator can talk to their fleet.

**Phase 6 — Intelligence Layer:**
Statistical baseline computation per entity, anomaly detection and severity classification, compliance deadline tracking and proactive alerting, fleet comparison analytics, extraction correction pattern analysis, anomaly feed with operator feedback actions. After this phase, the system proactively surfaces insights without being asked.

---

## Key Design Decisions and Rationale

**Why normalized tables instead of JSONB document storage:**
JSONB makes the extraction pipeline simpler (just dump whatever was extracted) but makes the query engine unreliable (the agent doesn't know the schema). Normalized tables make extraction harder (every document type needs mapping logic to specific tables) but make querying trivial (standard SQL against known columns with proper types and indexes). Since the query engine is the core product experience, optimizing for query reliability over extraction simplicity is the right tradeoff.

**Why sub-agent functions instead of LLM-powered agents:**
Most "agent" tasks in this system are SQL queries and arithmetic — summing costs, comparing dates, ranking entities. Using an LLM for these tasks adds latency, cost, non-determinism, and the possibility of calculation errors. Python functions are faster, cheaper, deterministic, and testable. The LLM is reserved for the two tasks that genuinely require natural language understanding: interpreting the operator's question and presenting the answer.

**Why WebSocket instead of polling or SSE:**
Polling wastes bandwidth and introduces update delays. SSE is one-directional (server → client) and doesn't handle the chat use case (which requires bidirectional communication). WebSocket provides bidirectional, persistent connections that serve both live dashboard updates (server → client) and chat messages (bidirectional) over a single connection.

**Why a separate extraction worker instead of processing in the API server:**
Document extraction involves CPU-intensive operations (Docling parsing, model inference) and potentially slow external API calls (Gemini for image PDFs and error correction). Running these in the API server process would block the event loop, degrading dashboard and chat responsiveness for all connected operators. A separate worker process handles extraction without affecting the API server's ability to serve requests and maintain WebSocket connections.

**Why Postgres NOTIFY instead of a message broker (RabbitMQ, Kafka):**
For the MVP with a single operator and one extraction worker, Postgres NOTIFY provides event-driven communication without adding another infrastructure dependency. The events are simple (document processed, entity updated) and low-volume (at most a few per second during bulk import). If the system scales to multiple workers or high-volume ingestion, migration to a proper message broker is straightforward — the event payload structure remains the same.

**Why dual Postgres + Neo4j instead of Postgres alone:**
Postgres excels at typed columns, aggregations, date arithmetic, and financial computations — the "how much" and "when does it expire" questions. Neo4j excels at variable-depth relationship traversal, path finding, and cross-entity pattern matching — the "what connects to what" and "show me the full history" questions. Fleet intelligence requires both query patterns. Postgres remains the structured source of truth with full typed schemas; Neo4j mirrors entity relationships extracted from documents. Layer 7 writes to both stores atomically (Postgres transaction first, then Neo4j MERGE — rollback and flag for review if graph write fails). Entity nodes carry postgres_id for join-back when a graph traversal needs aggregation data from Postgres sub-agents.

**Why rule-based extraction for text PDFs instead of LayoutLMv3:**
The Sunflower dataset has consistent, machine-generated PDFs where every document of a given type shares the same layout. Rule-based extraction handles these perfectly and is faster, cheaper, and more deterministic than model inference. LayoutLMv3 becomes necessary when handling diverse layouts from different vendors — the same semantic fields (invoice total, VIN, date) in different visual positions. The architecture supports adding LayoutLMv3 as an extraction strategy alongside rule-based extraction when document format diversity requires it.
