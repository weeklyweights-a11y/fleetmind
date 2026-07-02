# Phase 1: Foundation

## What Gets Built

Everything that needs to exist before a single document gets processed. The complete data model in Postgres with all normalized domain tables, the Neo4j graph schema, pgvector configuration, Redis setup, Docker Compose orchestrating all six services, the FastAPI application skeleton, a basic file upload endpoint, and the Alembic migration infrastructure. After this phase, you can start the entire stack with one command, upload a PDF, and see it saved to disk with a document record in Postgres and a job queued in Redis.

---

## Postgres Data Model

Every table below includes these standard columns unless noted otherwise: id (UUID, primary key, server-generated with gen_random_uuid()), tenant_id (integer, default 1, indexed — for future multi-tenancy), created_at (timestamp with time zone, server default now()), updated_at (timestamp with time zone, auto-updated on modification via trigger).

### trucks

Represents a physical vehicle that is or was in the fleet.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| unit_number | integer | not null, unique per tenant | Fleet's internal identifier (6, 9, 12, etc.) |
| vin | varchar(17) | not null, unique per tenant | 17-character Vehicle Identification Number |
| year | integer | not null | Model year |
| make | varchar(100) | not null | Manufacturer (Freightliner, Volvo, Peterbilt, International, Kenworth) |
| model | varchar(100) | not null | Model name (Cascadia 126, VNL 740, 579, ProStar LT625) |
| body_type | varchar(50) | nullable | Body type code (Truck Tractor, Straight Truck, etc.) |
| color | varchar(50) | nullable | Primary color |
| fuel_type | varchar(30) | nullable, default 'Diesel' | Fuel type from title docs |
| gross_vehicle_weight | integer | nullable | GVWR in pounds from title/registration docs |
| status | varchar(20) | not null, default 'active' | Enum: active, inactive, sold, scrapped |
| acquired_date | date | nullable | Date of purchase from Bill of Sale |
| purchase_price | decimal(12,2) | nullable | Purchase price from Bill of Sale |
| acquired_from_vendor_id | uuid | nullable, FK → vendors.id | Seller from Bill of Sale |
| initial_odometer | integer | nullable | Odometer at purchase from Bill of Sale |
| disposed_date | date | nullable | Date of sale/disposal |
| sale_price | decimal(12,2) | nullable | Sale price from Bill of Sale (Sale) |
| disposed_to | varchar(200) | nullable | Buyer name from Bill of Sale (Sale) |
| disposal_type | varchar(30) | nullable | Enum: sold, scrapped, traded, totaled |

Indexes: unit_number, vin, status, acquired_date.

### drivers

Represents a driver who is or was employed/contracted by the fleet.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| driver_code | varchar(10) | nullable, unique per tenant | Internal driver code (D01, D02, etc.) — extracted from CDL header |
| first_name | varchar(100) | not null | First name from CDL |
| last_name | varchar(100) | not null | Last name from CDL |
| full_name | varchar(200) | not null | Full name as it appears on CDL |
| date_of_birth | date | nullable | DOB from CDL |
| address | text | nullable | Address from CDL |
| sex | varchar(1) | nullable | M or F from CDL |
| height | varchar(10) | nullable | Height as displayed (6'-02") |
| weight_lbs | integer | nullable | Weight in pounds |
| eye_color | varchar(10) | nullable | Eye color code (BLU, BRN, etc.) |
| license_number | varchar(30) | not null | DLN from CDL |
| license_state | varchar(2) | not null, default 'KS' | Issuing state |
| license_class | varchar(5) | not null | License class (A, B, etc.) |
| license_endorsements | varchar(30) | nullable | Endorsement codes (T, N, H, X, P, S) |
| license_restrictions | varchar(50) | nullable | Restriction codes or NONE |
| license_issue_date | date | nullable | CDL issue date |
| license_expiry_date | date | not null | CDL expiration date — critical for compliance |
| medical_cert_expiry_date | date | nullable | Medical examiner certificate expiry if tracked |
| status | varchar(20) | not null, default 'active' | Enum: active, inactive, terminated |

Indexes: driver_code, license_number, license_expiry_date, status, full_name.

### trailers

Represents a trailer asset. Not populated in Sunflower dataset but exists for completeness.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| trailer_number | varchar(20) | not null, unique per tenant | Fleet's internal trailer identifier |
| vin | varchar(17) | nullable, unique per tenant | Trailer VIN if available |
| type | varchar(50) | nullable | Dry van, reefer, flatbed, tanker, etc. |
| year | integer | nullable | Model year |
| make | varchar(100) | nullable | Manufacturer |
| model | varchar(100) | nullable | Model |
| status | varchar(20) | not null, default 'active' | Enum: active, inactive, sold |

### vendors

Represents any external entity the fleet does business with — repair shops, equipment dealers, insurance companies, fuel stops, parts suppliers.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| name | varchar(200) | not null | Vendor name as it appears on documents |
| address | text | nullable | Full address |
| phone | varchar(30) | nullable | Phone number |
| vendor_type | varchar(50) | not null | Enum: service_repair, equipment_dealer, parts_supplier, fuel_stop, insurance_company, insurance_agent, leasing_company, buyer, other |
| city | varchar(100) | nullable | Parsed from address for location queries |
| state | varchar(2) | nullable | Parsed from address |

Indexes: name, vendor_type, state.
Unique constraint: (tenant_id, name, address) — same vendor name at a different address is a different vendor.

### assignments

Temporal links between drivers and trucks. Each row represents a period during which a driver was assigned to a truck.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| truck_id | uuid | not null, FK → trucks.id | The truck |
| driver_id | uuid | not null, FK → drivers.id | The driver |
| trailer_id | uuid | nullable, FK → trailers.id | Optional trailer assignment |
| start_date | date | not null | When this assignment began |
| end_date | date | nullable | When it ended — NULL means current/active |
| assignment_type | varchar(20) | not null, default 'primary' | Enum: primary, team, substitute, inferred |
| source_document_id | uuid | nullable, FK → documents.id | Which document established this assignment |
| confidence | decimal(3,2) | not null, default 1.0 | How confident the system is in this assignment |

Indexes: (truck_id, end_date) for current assignment lookup, (driver_id, end_date), (start_date, end_date) for temporal queries.
Constraint: For a given truck, at most one primary assignment should be active (end_date IS NULL AND assignment_type = 'primary'). Team assignments allow multiple active per truck.

### maintenance_events

Every service, repair, or maintenance action. One row per service invoice line item group (one invoice = one maintenance event, even if it has multiple line items).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| truck_id | uuid | not null, FK → trucks.id | Which truck was serviced |
| vendor_id | uuid | not null, FK → vendors.id | Which vendor performed the service |
| service_date | date | not null | Date of service from invoice |
| category | varchar(50) | not null | Service category (Tires, Brakes, Engine, Suspension, Filters, Cooling, Lighting, Electrical, Air System, Emissions, Wheels, Warranty, Transmission, Fuel, Other) |
| description | text | not null | Service description from invoice line items |
| parts_cost | decimal(12,2) | nullable | Parts/materials cost (extracted from SUBTOTAL or line items) |
| labor_cost | decimal(12,2) | nullable | Labor cost (separate line on invoice) |
| total_cost | decimal(12,2) | not null | Grand total from invoice |
| sales_tax | decimal(12,2) | nullable, default 0.00 | Tax amount |
| payment_status | varchar(20) | not null, default 'unknown' | Enum: paid, unpaid, unknown |
| payment_method | varchar(50) | nullable | Payment method (Fleet card ****4417, Company check, etc.) |
| technician_name | varchar(100) | nullable | Technician name from invoice |
| invoice_number | varchar(50) | not null | Vendor's invoice number |
| po_number | varchar(50) | nullable | Purchase order number |
| odometer_reading | integer | nullable | Odometer at time of service if on invoice |
| source_document_id | uuid | not null, FK → documents.id | Source invoice document |

Indexes: (truck_id, service_date), (vendor_id, service_date), category, invoice_number.

### mileage_records

Odometer snapshots extracted from any document that contains an odometer reading.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| truck_id | uuid | not null, FK → trucks.id | Which truck |
| record_date | date | not null | Date of the reading |
| odometer_reading | integer | not null | Odometer value in miles |
| source_type | varchar(50) | not null | What kind of document this came from (bill_of_sale, service_invoice, irp_cab_card, etc.) |
| source_document_id | uuid | not null, FK → documents.id | Source document |

Indexes: (truck_id, record_date).
Used to compute: miles driven between services, cost per mile, validate odometer consistency.

### registrations

State and IRP registration records.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| truck_id | uuid | not null, FK → trucks.id | Which truck |
| registration_type | varchar(30) | not null | Enum: state, irp_apportioned |
| state | varchar(2) | not null | Base state |
| registration_number | varchar(50) | nullable | Registration receipt number |
| plate_number | varchar(20) | nullable | License plate number |
| plate_state | varchar(2) | nullable | Plate issuing state |
| effective_date | date | not null | Registration start date |
| expiry_date | date | not null | Registration expiration — critical for compliance |
| registered_weight | integer | nullable | Gross weight in pounds |
| registration_class | varchar(50) | nullable | Class description (Apportioned — IRP) |
| irp_account_number | varchar(50) | nullable | IRP fleet/account number |
| validation_decal_number | varchar(50) | nullable | Decal/sticker number |
| registration_fee | decimal(10,2) | nullable | Base registration fee |
| property_tax | decimal(10,2) | nullable | Personal property tax |
| irp_apportioned_fee | decimal(10,2) | nullable | IRP apportioned fee |
| title_fee | decimal(10,2) | nullable | Title fee if included |
| total_fees_paid | decimal(10,2) | nullable | Total fees paid |
| source_document_id | uuid | not null, FK → documents.id | Source IRP/registration document |

Indexes: (truck_id, expiry_date), (truck_id, effective_date), plate_number.

### insurance_coverages

Per-vehicle insurance records.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| truck_id | uuid | not null, FK → trucks.id | Which truck is covered |
| policy_number | varchar(50) | not null | Policy number |
| insurer_name | varchar(200) | not null | Insurance company name |
| insurer_vendor_id | uuid | nullable, FK → vendors.id | Insurer as vendor entity |
| agent_name | varchar(200) | nullable | Insurance agent/agency name |
| agent_vendor_id | uuid | nullable, FK → vendors.id | Agent as vendor entity |
| coverage_type | varchar(100) | not null | Coverage type (Commercial Auto Liability, Cargo, etc.) |
| liability_limit | decimal(12,2) | nullable | Liability limit amount |
| cargo_limit | decimal(12,2) | nullable | Cargo coverage limit |
| effective_date | date | not null | Policy effective date |
| expiry_date | date | not null | Policy expiration — critical for compliance |
| naic_number | varchar(10) | nullable | NAIC company number |
| source_document_id | uuid | not null, FK → documents.id | Source insurance card document |

Indexes: (truck_id, expiry_date), policy_number.

### titles

Vehicle title records.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| truck_id | uuid | not null, FK → trucks.id | Which truck |
| title_number | varchar(50) | not null | State title number |
| title_state | varchar(2) | not null | Issuing state |
| issue_date | date | not null | Title issue date |
| vin | varchar(17) | not null | VIN as recorded on title (should match trucks.vin) |
| owner_name | varchar(200) | not null | Owner of record |
| owner_address | text | nullable | Owner address |
| lien_holder | varchar(200) | nullable | Lien holder name — NULL or 'NONE' if clear |
| previous_title_number | varchar(50) | nullable | Previous title reference |
| previous_title_state | varchar(2) | nullable | Previous title state |
| control_number | varchar(50) | nullable | State control number |
| title_fee | decimal(10,2) | nullable | Title fee |
| source_document_id | uuid | not null, FK → documents.id | Source title document |

Indexes: (truck_id), title_number.

### emission_certs

Emission test and certification records. Not a standalone document type in Sunflower (emission services appear as invoices from Diesel Emissions Co) but the table exists for fleets that have separate emission certificates.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| truck_id | uuid | not null, FK → trucks.id | Which truck |
| test_date | date | not null | When the test was performed |
| result | varchar(10) | not null | Enum: pass, fail |
| next_due_date | date | nullable | Next required test date |
| testing_facility | varchar(200) | nullable | Testing facility name |
| certificate_number | varchar(50) | nullable | Certificate number |
| source_document_id | uuid | nullable, FK → documents.id | Source document |

### ifta_filings

Quarterly IFTA (International Fuel Tax Agreement) returns. One row per quarterly filing.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| ifta_account_number | varchar(50) | not null | IFTA account number |
| quarter | varchar(10) | not null | Quarter identifier (2025Q3, 2025Q4, 2026Q1) |
| filing_date | date | not null | Date the return was filed |
| total_fleet_miles | integer | nullable | Total miles across all qualified vehicles |
| total_fleet_gallons | integer | nullable | Total gallons consumed |
| total_tax_due | decimal(12,2) | nullable | Net tax due or credit |
| penalty | decimal(12,2) | nullable, default 0 | Late penalty |
| interest | decimal(12,2) | nullable, default 0 | Interest |
| balance_due | decimal(12,2) | nullable | Total balance |
| average_fleet_mpg | decimal(5,2) | nullable | Fleet average MPG |
| source_document_id | uuid | not null, FK → documents.id | Source IFTA filing document |

Indexes: quarter.
Unique constraint: (tenant_id, quarter).

### ifta_jurisdiction_details

Per-jurisdiction breakdown within a quarterly IFTA filing.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| filing_id | uuid | not null, FK → ifta_filings.id | Parent filing |
| jurisdiction | varchar(100) | not null | State/province name |
| miles | integer | nullable | Miles in this jurisdiction |
| gallons | decimal(10,2) | nullable | Gallons consumed in this jurisdiction |
| taxable_gallons | decimal(10,2) | nullable | Net taxable gallons |
| tax_rate | decimal(8,4) | nullable | Tax rate per gallon |
| tax_due | decimal(10,2) | nullable | Tax due or credit |
| surcharge | decimal(10,2) | nullable | Any surcharge |

Indexes: (filing_id, jurisdiction).

### ifta_vehicle_details

Per-vehicle data within an IFTA filing. Links to trucks via VIN resolution.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| filing_id | uuid | not null, FK → ifta_filings.id | Parent filing |
| truck_id | uuid | nullable, FK → trucks.id | Resolved truck reference |
| vin | varchar(17) | not null | VIN as reported in the filing |
| miles | integer | nullable | Miles for this vehicle in this quarter |
| gallons | integer | nullable | Gallons for this vehicle |

Indexes: (filing_id, truck_id).

### documents

Audit trail for every ingested file. This is NOT where queried data lives — normalized tables above hold the truth. This table tracks provenance.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| original_filename | varchar(500) | not null | Original uploaded filename |
| file_path | text | not null | Storage path (local filesystem or object storage) |
| file_size_bytes | integer | nullable | File size |
| page_count | integer | nullable | Number of pages |
| source_format | varchar(20) | not null | Enum: text_pdf, image_pdf, photo, text |
| parse_method | varchar(30) | nullable | Enum: docling_fast, docling_hires, gemini_vision, direct_text |
| document_type | varchar(50) | nullable | Enum: bill_of_sale_purchase, bill_of_sale_sale, cdl, insurance_card, service_invoice, irp_cab_card, title, ifta_filing, unknown |
| document_number | varchar(50) | nullable | Document's own identifier (BOS-2103-006, CSS-660142, etc.) |
| document_date | date | nullable | Primary date on the document |
| truck_id | uuid | nullable, FK → trucks.id | Resolved truck link |
| driver_id | uuid | nullable, FK → drivers.id | Resolved driver link |
| vendor_id | uuid | nullable, FK → vendors.id | Resolved vendor link |
| raw_extracted_text | text | nullable | Full text extracted from document |
| processing_status | varchar(20) | not null, default 'queued' | Enum: queued, parsing, extracting, normalizing, validating, complete, failed, needs_review |
| parse_confidence | decimal(3,2) | nullable | Confidence from extraction layers (0.0-1.0) |
| entity_resolution_confidence | decimal(3,2) | nullable | Confidence in entity linking |
| review_status | varchar(20) | nullable | Enum: pending, approved, corrected |
| review_notes | text | nullable | Human reviewer notes |
| error_details | text | nullable | Error message if processing failed |

Indexes: document_type, processing_status, (truck_id, document_type), (driver_id), (vendor_id), document_date.

### document_normalized_records

Junction table tracking which normalized records were produced from which document. Enables tracing any data point back to its source and cascading corrections.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| document_id | uuid | not null, FK → documents.id | Source document |
| target_table | varchar(50) | not null | Which normalized table (trucks, maintenance_events, etc.) |
| target_record_id | uuid | not null | ID of the record in the target table |
| extraction_confidence | decimal(3,2) | nullable | Confidence for this specific record |

Indexes: (document_id), (target_table, target_record_id).

### document_chunks

Text chunks with vector embeddings for semantic search over document content.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| document_id | uuid | not null, FK → documents.id | Source document |
| chunk_index | integer | not null | Position within document |
| chunk_text | text | not null | The text chunk |
| embedding | vector(768) | not null | Text embedding from embedding model |
| truck_id | uuid | nullable | Denormalized for filtered vector search |
| driver_id | uuid | nullable | Denormalized |
| document_type | varchar(50) | nullable | Denormalized |
| document_date | date | nullable | Denormalized |

Indexes: GIN index on embedding for vector similarity search. (truck_id, document_type) for metadata-filtered search.

### extraction_corrections

Logs every correction for learning loop analysis.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| document_id | uuid | not null, FK → documents.id | Which document was corrected |
| field_name | varchar(100) | not null | Which field was wrong |
| original_value | text | nullable | What the extraction produced |
| corrected_value | text | not null | What it was corrected to |
| correction_source | varchar(20) | not null | Enum: human, agentic_layer6 |
| corrected_by | varchar(100) | nullable | Who made the correction (for human corrections) |
| corrected_at | timestamp with time zone | not null, default now() | When |

### conversations

Chat session records.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| operator_name | varchar(100) | nullable | Operator identifier (simple string for MVP) |
| started_at | timestamp with time zone | not null, default now() | Session start |
| ended_at | timestamp with time zone | nullable | Session end — NULL means active |
| entities_discussed | jsonb | nullable | Array of {type, id, name} objects |
| topics | jsonb | nullable | Array of topic strings |
| key_findings | jsonb | nullable | Array of finding summary strings |
| unresolved_items | jsonb | nullable | Array of {description, entity_type, entity_id} objects |
| summary_text | text | nullable | LLM-generated session summary |

### conversation_messages

Individual messages within a conversation.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| conversation_id | uuid | not null, FK → conversations.id | Parent conversation |
| role | varchar(10) | not null | Enum: user, assistant |
| content | text | not null | Message content |
| tools_called | jsonb | nullable | Which sub-agent functions were invoked and their results |
| message_index | integer | not null | Order within conversation |

Indexes: (conversation_id, message_index).

### operator_profiles

Long-term operator behavioral memory.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| operator_name | varchar(100) | not null, unique per tenant | Operator identifier |
| frequent_entities | jsonb | nullable | Ranked list of most-queried entities |
| frequent_topics | jsonb | nullable | Ranked list of most-asked-about topics |
| preferred_response_style | varchar(50) | nullable | Detected style preference (concise, detailed, tables, narrative) |
| typical_session_pattern | text | nullable | Observed usage patterns |
| total_conversations | integer | not null, default 0 | Lifetime conversation count |
| last_active | timestamp with time zone | nullable | Last session timestamp |

### anomalies

System-detected fleet anomalies.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| anomaly_type | varchar(50) | not null | Enum: cost_spike, efficiency_decline, frequency_unusual, compliance_gap, missing_document, vendor_cost_increase |
| entity_type | varchar(20) | not null | Enum: truck, driver, vendor, fleet |
| entity_id | uuid | nullable | ID of the affected entity (nullable for fleet-wide anomalies) |
| description | text | not null | Human-readable description of the anomaly |
| severity | varchar(10) | not null | Enum: info, warning, critical |
| supporting_data | jsonb | not null | The numbers, comparisons, and thresholds that triggered detection |
| status | varchar(20) | not null, default 'new' | Enum: new, acknowledged, investigating, dismissed |
| operator_feedback | jsonb | nullable | Why the operator dismissed or what they're investigating |
| detected_at | timestamp with time zone | not null, default now() | When the anomaly was detected |
| resolved_at | timestamp with time zone | nullable | When it was resolved |

Indexes: (status, severity), (entity_type, entity_id).

### fleet_metrics

Pre-computed metrics for dashboard performance. Updated by sub-agent functions or background jobs.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| entity_type | varchar(20) | not null | Enum: truck, driver, vendor, fleet |
| entity_id | uuid | nullable | Entity ID (NULL for fleet-wide metrics) |
| metric_name | varchar(50) | not null | What's being measured (total_maintenance_cost, avg_cost_per_service, service_frequency, cost_per_mile, fuel_efficiency) |
| metric_value | decimal(14,4) | not null | The computed value |
| period_type | varchar(10) | not null | Enum: monthly, quarterly, yearly, all_time |
| period_start | date | not null | Start of the measurement period |
| period_end | date | not null | End of the measurement period |
| computed_at | timestamp with time zone | not null, default now() | When this was last computed |

Indexes: (entity_type, entity_id, metric_name, period_type).

---

## Neo4j Graph Schema

The knowledge graph represents entities and their relationships. It is NOT a replacement for Postgres — it's a derived view optimized for relationship traversal and cross-entity discovery. Every relationship in the graph has a corresponding record in Postgres normalized tables.

### Node Types

**(:Truck)** — Properties: unit_number (integer), vin (string), make (string), model (string), year (integer), color (string), status (string), tenant_id (integer), pg_id (string — the Postgres UUID for cross-reference).

**(:Driver)** — Properties: driver_code (string), full_name (string), license_number (string), license_class (string), license_expiry (date), status (string), tenant_id (integer), pg_id (string).

**(:Trailer)** — Properties: trailer_number (string), type (string), status (string), tenant_id (integer), pg_id (string).

**(:Vendor)** — Properties: name (string), vendor_type (string), city (string), state (string), tenant_id (integer), pg_id (string).

**(:InsurancePolicy)** — Properties: policy_number (string), insurer_name (string), effective_date (date), expiry_date (date), liability_limit (float), tenant_id (integer), pg_id (string).

**(:Document)** — Properties: document_type (string), document_number (string), document_date (date), filename (string), tenant_id (integer), pg_id (string).

**(:IFTAFiling)** — Properties: quarter (string), filing_date (date), total_miles (integer), total_gallons (integer), average_mpg (float), tenant_id (integer), pg_id (string).

### Relationship Types

**(Truck)-[:PURCHASED_FROM {date, price, odometer}]->(Vendor)** — Created from Bill of Sale (Purchase). One per truck acquisition.

**(Truck)-[:SOLD_TO {date, price}]->(Vendor)** — Created from Bill of Sale (Sale). Only for trucks that were sold.

**(Driver)-[:ASSIGNED_TO {start_date, end_date, assignment_type}]->(Truck)** — Created from CDL fleet assignment and lease agreements. Temporal — end_date null means current. Direction is Driver→Truck because queries like "which trucks has this driver operated" are more common than the reverse.

**(Truck)-[:MAINTAINED_AT {service_date, category, total_cost, invoice_number}]->(Vendor)** — Created from service invoices. One edge per maintenance event.

**(Truck)-[:COVERED_BY {effective_date, expiry_date, coverage_type}]->(InsurancePolicy)** — Created from insurance cards. Links a truck to its insurance coverage.

**(InsurancePolicy)-[:ISSUED_BY]->(Vendor)** — Links a policy to the insurance company.

**(InsurancePolicy)-[:BROKERED_BY]->(Vendor)** — Links a policy to the insurance agent.

**(Truck)-[:REGISTERED_IN {effective_date, expiry_date, plate_number, registration_number}]->(jurisdiction string)** — Could be modeled as a property or a (:Jurisdiction) node depending on query needs. For MVP, store as relationship properties.

**(Truck)-[:TITLED_IN {title_number, issue_date}]->(state string)** — Title relationship.

**(Truck)-[:HAS_DOCUMENT]->(Document)** — Links every truck to every document associated with it.

**(Driver)-[:HAS_DOCUMENT]->(Document)** — Links every driver to their CDL documents.

**(Vendor)-[:HAS_DOCUMENT]->(Document)** — Links vendors to invoices they issued.

**(Truck)-[:REPORTED_IN {miles, gallons}]->(IFTAFiling)** — Per-vehicle IFTA data.

### Graph Sync Strategy

The knowledge graph is always written AFTER Postgres. Layer 7 of the extraction pipeline writes to normalized Postgres tables first (source of truth), then creates or updates the corresponding Neo4j nodes and relationships. If Neo4j write fails, the document is still successfully processed — the graph sync is retried separately. The pg_id property on every Neo4j node enables cross-referencing between the two stores.

On startup, a graph integrity check compares Neo4j node counts against Postgres table counts per entity type. If they diverge, a full resync can rebuild the graph from Postgres.

---

## Redis Configuration

**Queue: document_processing**
Used for document processing jobs between the API server and extraction worker. Each job contains: document_id (UUID), file_path (string), original_filename (string), tenant_id (integer). Jobs are picked up FIFO. Failed jobs get moved to a dead letter queue after 3 retries.

**Hash: ws_subscriptions**
Tracks which WebSocket connections are subscribed to which topics. Key: connection_id. Value: set of topic strings. Used by the notifier to route events to the right connections.

**Hash: chat_sessions**
Active chat session state. Key: conversation_id. Value: JSON containing current_entity (type and id), current_time_window (start and end dates), current_intent (last classified intent), turn_history (list of recent turns with abbreviated results). TTL: 24 hours of inactivity.

---

## Docker Compose Services

**postgres** — PostgreSQL 16 with pgvector extension. Port 5432. Persistent volume for data directory. Environment: POSTGRES_DB=fleetmind, POSTGRES_USER, POSTGRES_PASSWORD. Healthcheck: pg_isready.

**redis** — Redis 7. Port 6379. No persistence needed for MVP (queue and session data is transient). Healthcheck: redis-cli ping.

**neo4j** — Neo4j 5 Community Edition. Ports 7474 (browser), 7687 (bolt). Persistent volume for data. Environment: NEO4J_AUTH=neo4j/password. Healthcheck: cypher-shell "RETURN 1". APOC plugin enabled for utility functions.

**api** — FastAPI server. Port 8000. Depends on: postgres, redis, neo4j (healthy). Mounts the document storage directory as a volume. Environment variables: DATABASE_URL, REDIS_URL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, GEMINI_API_KEY, DOCUMENT_STORAGE_PATH. Entry point: uvicorn app.main:app.

**worker** — Extraction worker. Same Docker image as api, different entry point: python -m app.worker.consumer. Depends on: postgres, redis, neo4j (healthy). Same environment variables as api plus the document storage volume. Does NOT expose any ports — it only communicates through Redis (job queue) and Postgres (writes + NOTIFY).

**frontend** — React development server. Port 3000. Depends on: api (healthy). Environment: VITE_API_URL=http://localhost:8000, VITE_WS_URL=ws://localhost:8000/ws.

All services on a shared Docker network: fleetmind_network.

---

## FastAPI Application Skeleton

The API server in this phase has minimal functionality — enough to verify the stack works end-to-end.

**Lifespan events:** On startup, establish Postgres connection pool (async, using asyncpg or SQLAlchemy async), establish Redis connection, establish Neo4j driver connection, start the Postgres NOTIFY listener in a background task. On shutdown, close all connections gracefully.

**Endpoints for Phase 1:**

GET /api/health — Returns status of all service connections (Postgres, Redis, Neo4j). This is the smoke test that the entire stack is operational.

POST /api/documents/upload — Accepts a multipart file upload. Saves the file to the document storage directory with a UUID-based filename. Creates a document record in Postgres with processing_status = 'queued'. Pushes a job onto the Redis document_processing queue. Returns the document_id and status immediately.

GET /api/documents/{id} — Returns the document record including current processing_status. In Phase 1, this always returns 'queued' since the extraction worker isn't built yet.

GET /api/documents — Lists all documents with filtering by processing_status and document_type. Paginated.

POST /api/documents/upload/batch — Accepts multiple files. Creates document records and queue jobs for each. Returns a list of document_ids.

**WebSocket endpoint for Phase 1:**

/ws — Establishes WebSocket connection. In Phase 1, the only functionality is connection management and a simple echo test. Accepts subscribe/unsubscribe messages. Stores subscription state in Redis. This lays the groundwork for Phase 4's live updates.

**Postgres NOTIFY listener:**

A background asyncio task that listens on the 'document_events' channel. In Phase 1, nothing emits to this channel yet (extraction worker isn't built), but the listener is running and ready. When it receives a notification, it will look up subscribed WebSocket connections and push the event.

---

## Alembic Migration Setup

Alembic initialized with async support (using asyncpg). The initial migration creates all tables defined above. The migration runs the pgvector extension creation (CREATE EXTENSION IF NOT EXISTS vector) before creating tables that use the vector type.

Migration naming convention: YYYYMMDD_HHMM_description.py. The initial migration: 20260701_0001_initial_schema.py.

The alembic.ini and env.py are configured to read DATABASE_URL from environment variables, matching the Docker Compose configuration.

---

## Configuration Management

A single config.py using Pydantic Settings. Reads from environment variables with sensible defaults for local development. Variables: DATABASE_URL, REDIS_URL, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, GEMINI_API_KEY, DOCUMENT_STORAGE_PATH (default: ./document_storage), LOG_LEVEL (default: INFO), CORS_ORIGINS (default: http://localhost:3000).

---

## Phase 1 Acceptance Criteria

1. Running `docker compose up` starts all 6 services and they reach healthy state.
2. GET /api/health returns 200 with all service connections showing "connected."
3. POST /api/documents/upload with a PDF file saves the file to disk, creates a document record in Postgres with status "queued," and adds a job to the Redis queue.
4. GET /api/documents/{id} returns the document record with correct metadata.
5. The WebSocket endpoint at /ws accepts connections, handles subscribe/unsubscribe messages, and stores subscription state in Redis.
6. All Postgres tables exist with correct columns, types, constraints, and indexes as verified by running the Alembic migration.
7. Neo4j is accessible and the graph schema constraints are created (uniqueness constraints on Truck.unit_number, Truck.vin, Driver.license_number, Vendor.name+address).
8. The Redis queue "document_processing" exists and jobs can be pushed and popped.
9. The extraction worker process starts, connects to Redis, and begins polling the job queue (but does nothing with jobs yet — just logs "received job for document_id X" and acknowledges).
10. The React frontend starts, displays a minimal page, and successfully establishes a WebSocket connection to the API server.

---

## What Phase 1 Does NOT Build

- No document extraction or processing logic (Phase 2)
- No sub-agent functions or dashboard data endpoints (Phase 3)
- No dashboard UI components beyond a minimal health/upload test page (Phase 4)
- No chat functionality (Phase 5)
- No anomaly detection or intelligence features (Phase 6)
- No authentication or multi-tenancy logic
- No production error tracking or monitoring

---

## Dependencies for Phase 2

Phase 2 requires everything from Phase 1 to be operational: the Postgres tables populated with correct schema, the Neo4j graph database accessible, the Redis job queue functioning, the file upload endpoint saving files and creating document records, and the extraction worker process running and polling for jobs. Phase 2 replaces the worker's "log and acknowledge" stub with the full 7-layer extraction pipeline.
