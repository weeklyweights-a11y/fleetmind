# Phase 3: Sub-Agents + API Layer

## What Gets Built

Every sub-agent function that computes fleet intelligence from the normalized data. REST API endpoints wrapping each function. Parallel execution infrastructure using asyncio. Neo4j Cypher query patterns for relationship traversal alongside Postgres SQL queries for aggregation. After this phase, the complete fleet intelligence is accessible via API — you can hit any endpoint and get truck profiles, maintenance breakdowns, compliance status, financial analysis, vendor comparisons, driver profiles, and fleet-wide overviews, all computed on demand from the real Sunflower data populated in Phase 2.

---

## Sub-Agent Design Principles

Every sub-agent is a Python async function. No sub-agent makes an LLM call. Every sub-agent returns a typed Pydantic model. Every sub-agent that computes fleet-level comparisons (how does this truck compare to the fleet average) does so by computing the fleet statistics within the same function — it does not call another sub-agent. Sub-agents that need relationship data query Neo4j. Sub-agents that need aggregated numbers query Postgres. Some sub-agents query both.

The API route handler for a sub-agent does exactly three things: validate the request parameters, call the sub-agent function, return the result as JSON. No business logic in route handlers.

When the truck detail page needs all data for a truck, the frontend makes parallel API calls to each sub-agent endpoint. The backend does NOT have a "get everything for truck X" meta-endpoint that calls all sub-agents internally — that coupling belongs in the frontend, not the backend. Each sub-agent is independently callable and independently cacheable.

---

## Sub-Agent Specifications

### get_truck_identity(truck_id)

**Queries:** Postgres trucks table.

**What it computes:** Single row lookup by truck_id or unit_number. Returns the truck's complete identity record.

**Return structure:**
- unit_number
- vin
- year, make, model, body_type, color
- fuel_type, gross_vehicle_weight
- status (active/sold/inactive)
- acquired_date, purchase_price, acquired_from_vendor (vendor name, resolved from vendor_id)
- initial_odometer
- If status is 'sold': disposed_date, sale_price, disposed_to, disposal_type
- current_odometer: the most recent reading from mileage_records for this truck, with the date and source document type
- estimated_current_miles: if multiple odometer readings exist, extrapolate current mileage based on the average daily rate between the last two readings
- age_years: computed from year and current date
- time_in_fleet: computed from acquired_date to disposed_date (or today if active)

**Endpoint:** GET /api/trucks/{id}
Accepts truck_id (UUID) or unit_number (integer via query param ?unit=19).

---

### get_truck_assignment(truck_id)

**Queries:** Postgres assignments table joined with drivers table. Neo4j for the full assignment chain visualization.

**What it computes:**

Current assignment: query assignments WHERE truck_id = X AND end_date IS NULL. Join with drivers to get the driver's full details. If no current assignment exists (truck is sold or unassigned), return current_driver as null with a note explaining why.

Assignment history: query assignments WHERE truck_id = X AND end_date IS NOT NULL, ordered by start_date DESC. For each historical assignment, include the driver name, the date range, the assignment type, and the duration in days.

Neo4j traversal: query all (Driver)-[:ASSIGNED_TO]->(Truck) relationships for this truck to get the visual relationship chain including any team driving or substitute driver patterns.

**Return structure:**
- current_driver: {driver_id, full_name, driver_code, license_number, license_class, license_expiry_date, license_expiry_status (green/yellow/red based on days remaining), endorsements, restrictions, assigned_since, assignment_type, days_assigned}
- previous_drivers: list of {full_name, driver_code, start_date, end_date, duration_days, assignment_type}
- total_drivers_historically: count
- assignment_stability: assessment based on number of driver changes and average tenure (stable if one driver for 1+ year, moderate if 2-3 drivers, unstable if 4+)

**Endpoint:** GET /api/trucks/{id}/assignment

---

### get_truck_maintenance(truck_id, time_range, include_trend)

**Queries:** Postgres maintenance_events table with aggregations. Neo4j for vendor relationship patterns.

**Parameters:**
- truck_id: required
- time_range: optional, object with start_date and end_date. Default: all time.
- include_trend: optional boolean, default false. When true, includes monthly spend breakdown for charting.

**What it computes:**

Summary metrics: total_spend (SUM total_cost), event_count (COUNT), average_cost_per_event (AVG), min and max single event cost.

Last service: the most recent maintenance_event — date, vendor name, category, description, total_cost. How many days ago.

By category: GROUP BY category. For each: category name, event count, total spend, percentage of total spend. Sorted by total spend descending.

By vendor: GROUP BY vendor_id joined with vendors for name. For each: vendor name, event count, total spend, average cost per visit, most recent visit date. Sorted by total spend descending.

Fleet comparison: compute the fleet average maintenance spend per truck (total maintenance spend across all active trucks / count of active trucks). Compare this truck's total to the fleet average. Express as a ratio and a percentile rank. Also compare average cost per event and service frequency (events per year).

Trend (when include_trend is true): GROUP BY year-month (date_trunc('month', service_date)). For each month: total spend, event count. This powers the maintenance cost chart on the dashboard.

Pattern detection: identify if any category has 3+ events in the last 6 months (recurring issue pattern). Identify if total spend has increased by more than 50% compared to the same period in the prior year (cost escalation pattern). These patterns are returned as alerts with description and supporting data.

Neo4j query: traverse (Truck)-[:MAINTAINED_AT]->(Vendor) relationships to get the vendor network for this truck. This shows which vendors have serviced this truck and how frequently, as a graph structure that can be visualized.

**Return structure:**
- summary: {total_spend, event_count, avg_cost, min_cost, max_cost}
- last_service: {date, vendor_name, category, description, cost, days_ago}
- by_category: list of {category, count, total_spend, pct_of_total}
- by_vendor: list of {vendor_name, count, total_spend, avg_cost, last_visit}
- fleet_comparison: {fleet_avg_total, this_truck_total, ratio, rank_in_fleet, fleet_avg_per_event, fleet_avg_frequency}
- trend: list of {month, total_spend, event_count} (only when include_trend=true)
- patterns: list of {pattern_type, description, supporting_data}
- vendor_graph: Neo4j relationship data for visualization

**Endpoint:** GET /api/trucks/{id}/maintenance
Query params: ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&include_trend=true

---

### get_truck_compliance(truck_id)

**Queries:** Postgres insurance_coverages, registrations, titles, emission_certs tables. Also checks the driver's CDL expiry via the current assignment.

**What it computes:**

For each compliance category, finds the most recent/current record and evaluates its status against today's date.

Insurance: query insurance_coverages WHERE truck_id = X ORDER BY expiry_date DESC LIMIT 1. Compute days_until_expiry. Status: green if 30+ days, yellow if 1-30 days, red if expired or past due, grey if no record exists.

Registration: query registrations WHERE truck_id = X ORDER BY expiry_date DESC LIMIT 1. Same status computation.

Title: query titles WHERE truck_id = X ORDER BY issue_date DESC LIMIT 1. Titles don't expire, but the existence of a title record and lien status are relevant. Status: green if title exists with no lien, yellow if lien exists, grey if no title record.

Emission: query emission_certs WHERE truck_id = X ORDER BY test_date DESC LIMIT 1. Status based on next_due_date. If no emission cert exists but the truck has had emission-related maintenance (category = 'Emissions' in maintenance_events), note this.

Driver CDL: resolve the current driver via assignments. Check the driver's license_expiry_date. Status: green if 90+ days, yellow if under 90 days, red if expired. This is included in the truck's compliance because an expired CDL means the truck can't legally operate.

Medical cert: if the driver has a medical_cert_expiry_date, check it. Otherwise grey.

Overall compliance score: all green = "fully compliant". Any yellow = "attention needed". Any red = "non-compliant — action required". Any grey = "incomplete records".

**Return structure:**
- overall_status: "compliant" / "attention_needed" / "non_compliant" / "incomplete"
- categories:
  - insurance: {status, policy_number, insurer, expiry_date, days_remaining, source_document_id}
  - registration: {status, plate_number, registration_number, expiry_date, days_remaining, source_document_id}
  - title: {status, title_number, issue_date, lien_holder, source_document_id}
  - emission: {status, last_test_date, result, next_due_date, days_remaining, source_document_id}
  - driver_cdl: {status, driver_name, license_number, expiry_date, days_remaining}
  - medical_cert: {status, expiry_date, days_remaining} or {status: "no_record"}
- urgent_items: list of any category with status yellow or red, sorted by days_remaining ascending

**Endpoint:** GET /api/trucks/{id}/compliance

---

### get_truck_financials(truck_id)

**Queries:** Postgres trucks, maintenance_events, registrations, ifta_vehicle_details, mileage_records tables.

**What it computes:**

Acquisition cost: from trucks.purchase_price.

Total maintenance spend: SUM of maintenance_events.total_cost for this truck.

Total registration fees: SUM of registrations.total_fees_paid for this truck.

Total insurance cost: not directly available from insurance cards (they don't show premium amounts), so this may be null or estimated.

Total cost of ownership: acquisition + maintenance + registration + insurance (where available).

Cost breakdown: each component as a percentage of total cost.

Cost per mile: if at least 2 odometer readings exist in mileage_records, compute total miles driven (latest - earliest odometer), then total_cost / total_miles. This is the most important financial metric for a fleet operator.

Monthly cost rate: total maintenance spend / months since acquisition. Shows the average monthly operating cost.

Depreciated book value: simple straight-line depreciation over 10 years (standard for commercial trucks). purchase_price - (purchase_price * years_owned / 10). Minimum $0.

Fleet financial comparison: this truck's total cost of ownership vs fleet average, cost per mile vs fleet average, monthly rate vs fleet average. Rank among all active trucks.

Is this truck profitable: if IFTA data exists linking this truck to revenue-generating miles, compute revenue potential (industry average revenue per mile ~$2.50-$3.00 × total miles) vs total cost. This is an approximation but gives directional insight.

**Return structure:**
- acquisition: {price, date, seller, initial_odometer}
- maintenance_total: amount
- registration_total: amount
- insurance_total: amount or null
- total_cost_of_ownership: amount
- cost_breakdown: {acquisition_pct, maintenance_pct, registration_pct, insurance_pct}
- cost_per_mile: amount or null (null if insufficient odometer data)
- monthly_cost_rate: amount
- book_value: {original, depreciated, years_owned, depreciation_method}
- fleet_comparison: {fleet_avg_tco, rank, fleet_avg_cost_per_mile, cost_per_mile_rank}
- total_miles_driven: integer or null

**Endpoint:** GET /api/trucks/{id}/financials

---

### get_truck_documents(truck_id)

**Queries:** Postgres documents table.

**What it computes:**

All documents linked to this truck, grouped by document_type. For each group: count and list of documents. For each document: document_type, document_number, document_date, original_filename, file_path (for PDF viewing), processing_status, parse_confidence.

Also queries Neo4j: (Truck)-[:HAS_DOCUMENT]->(Document) to get the full document graph for this truck, which may include indirect connections (documents linked to the truck's driver, documents linked to vendors who service this truck).

**Return structure:**
- total_documents: count
- by_type: dict of document_type → {count, documents: list of {document_id, document_number, document_date, filename, file_path, status, confidence}}
- timeline: all documents sorted by date, enabling a chronological document history view
- related_documents: documents not directly linked to this truck_id but connected through the graph (driver CDLs, vendor invoices for other trucks at the same vendor)

**Endpoint:** GET /api/trucks/{id}/documents

---

### get_fleet_overview()

**Queries:** Postgres trucks, drivers, assignments, maintenance_events, insurance_coverages, registrations, documents tables. Multiple aggregation queries.

**What it computes:**

Fleet composition: count of trucks by status (active, sold, inactive). Count of drivers by assignment status (assigned, unassigned). Total fleet value (sum of purchase prices for active trucks). Average truck age.

Compliance snapshot: count of trucks with all-green compliance, count with warnings (yellow), count with expirations (red), count with missing records (grey). This is the compliance matrix summarized into a single set of numbers. List of the most urgent compliance items (expiring within 7 days).

Financial snapshot: total maintenance spend this month, last month, and rolling 3-month average. Month-over-month change as a percentage. Total fleet cost of ownership.

Recent activity: last 10 documents processed with their type, associated truck, and processing status. Any documents currently in the review queue.

Quick stats: total maintenance events all-time, total vendors used, most expensive truck (by total maintenance), most frequently serviced truck, average cost per mile across the fleet (for trucks with sufficient odometer data).

**Return structure:**
- fleet_composition: {total_trucks, active, sold, inactive, total_drivers, assigned_drivers, unassigned_drivers, total_fleet_value, avg_truck_age}
- compliance_snapshot: {fully_compliant, warnings, expirations, incomplete, urgent_items: list}
- financial_snapshot: {this_month_spend, last_month_spend, three_month_avg, mom_change_pct, total_fleet_tco}
- recent_activity: list of {document_id, type, truck_unit, date, status}
- review_queue_count: integer
- quick_stats: {total_maintenance_events, total_vendors, most_expensive_truck: {unit, total_spend}, most_serviced_truck: {unit, event_count}, fleet_avg_cost_per_mile}

**Endpoint:** GET /api/fleet/overview

---

### get_fleet_comparison(truck_ids)

**Queries:** Postgres trucks, maintenance_events, mileage_records. Runs financial and maintenance computations for each truck.

**Parameters:**
- truck_ids: optional list of truck IDs or unit numbers to compare. If empty, compares all active trucks.

**What it computes:**

For each truck: total cost of ownership, maintenance spend, event count, cost per mile (if available), most frequent maintenance category, current compliance status (summarized as green/yellow/red), current driver name, truck age.

Rankings: trucks ranked by total cost of ownership (most to least expensive), by maintenance frequency, by cost per mile.

Outlier detection: any truck more than 2 standard deviations above the fleet mean in any metric gets flagged.

**Return structure:**
- trucks: list of {unit_number, make_model_year, driver_name, tco, maintenance_spend, event_count, cost_per_mile, top_category, compliance_status, age_years, outlier_flags}
- rankings: {by_tco: list, by_maintenance: list, by_cost_per_mile: list}
- fleet_averages: {avg_tco, avg_maintenance, avg_events, avg_cost_per_mile}

**Endpoint:** GET /api/fleet/comparison
Query params: ?trucks=19,22,84 (optional, defaults to all active)

---

### get_compliance_matrix()

**Queries:** Runs get_truck_compliance for every active truck. Postgres bulk query across insurance_coverages, registrations, titles, emission_certs, drivers+assignments.

**What it computes:**

The full compliance grid: rows = every active truck (sorted by unit number), columns = insurance, registration, title, emission, driver_cdl, medical_cert. Each cell = {status: green/yellow/red/grey, days_remaining: integer or null, expiry_date: date or null}.

Optimized as a bulk query rather than calling get_truck_compliance 16 times: single query per compliance table joining with trucks, computing status for all trucks at once.

Deadline countdown: all compliance items across all trucks that expire within 90 days, sorted by expiry_date ascending. Each item includes the truck unit number, compliance type, expiry date, and days remaining.

Fleet compliance score: percentage of all cells that are green. A fleet with 16 trucks and 6 compliance categories has 96 cells. If 88 are green, the score is 91.7%.

**Return structure:**
- matrix: list of {truck_unit, truck_make_model, insurance: {status, days, expiry}, registration: {status, days, expiry}, title: {status}, emission: {status, days, expiry}, driver_cdl: {status, days, expiry, driver_name}, medical_cert: {status, days, expiry}}
- deadlines: list of {truck_unit, compliance_type, expiry_date, days_remaining, severity}
- fleet_compliance_score: percentage
- summary: {green_count, yellow_count, red_count, grey_count}

**Endpoint:** GET /api/compliance/matrix

---

### get_driver_profile(driver_id)

**Queries:** Postgres drivers, assignments, trucks tables. Neo4j for relationship visualization.

**What it computes:**

Driver identity: all CDL details (name, license number, class, endorsements, restrictions, DOB, address, physical description, issue/expiry dates).

Current assignment: which truck the driver currently operates, since when, the truck's details (unit, make, model, year).

Assignment history: all trucks this driver has operated, with date ranges and durations. Total time in fleet.

License compliance: CDL expiry status (green/yellow/red), days until expiry, endorsement details.

Neo4j traversal: (Driver)-[:ASSIGNED_TO]->(Truck) chain showing all truck relationships. Also one hop further: (Driver)-[:ASSIGNED_TO]->(Truck)-[:MAINTAINED_AT]->(Vendor) to show which vendors are associated with trucks this driver has operated.

**Return structure:**
- identity: {full_name, driver_code, date_of_birth, address, sex, height, weight, eye_color}
- license: {number, state, class, endorsements, restrictions, issue_date, expiry_date, expiry_status, days_remaining}
- current_assignment: {truck_unit, truck_make_model_year, assigned_since, days_assigned} or null
- assignment_history: list of {truck_unit, truck_make_model, start_date, end_date, duration_days}
- total_trucks_operated: count
- time_in_fleet_days: integer
- relationships_graph: Neo4j data for visualization

**Endpoint:** GET /api/drivers/{id}
Accepts driver_id (UUID) or driver_code (string via query param ?code=D03).

---

### get_vendor_analysis(vendor_id)

**Queries:** Postgres maintenance_events joined with trucks and vendors. Neo4j for vendor-fleet relationship network.

**Parameters:**
- vendor_id: optional. If provided, returns detailed analysis for one vendor. If null, returns fleet-wide vendor summary.

**What it computes (single vendor):**

Vendor details: name, address, type.

Service summary: total spend at this vendor, event count, average cost per service, date range of services (first visit to last visit).

By truck: which trucks this vendor has serviced, with count and spend per truck.

By category: what types of services this vendor provides, with count and spend per category.

Cost trend: monthly spend at this vendor over time.

Comparison: this vendor's average cost per service vs the fleet-wide average across all vendors for similar categories.

Neo4j traversal: (Vendor)<-[:MAINTAINED_AT]-(Truck) showing all trucks connected to this vendor, with edge properties (dates, costs).

**What it computes (fleet-wide):**

All vendors ranked by total spend. For each: name, total spend, event count, truck count (how many different trucks they've serviced), average cost, most common category.

Vendor concentration: what percentage of total maintenance spend goes to the top vendor, top 3 vendors. High concentration = risk.

**Return structure (single vendor):**
- vendor: {name, address, type}
- summary: {total_spend, event_count, avg_cost, first_visit, last_visit}
- by_truck: list of {truck_unit, count, total_spend}
- by_category: list of {category, count, total_spend}
- trend: list of {month, spend, count}
- comparison: {vendor_avg_cost, fleet_avg_cost, difference_pct}
- relationship_graph: Neo4j data

**Return structure (fleet-wide):**
- vendors: list of {name, total_spend, event_count, truck_count, avg_cost, top_category}
- concentration: {top_vendor_pct, top_3_pct, total_vendors}

**Endpoint:** GET /api/vendors (fleet-wide), GET /api/vendors/{id} (single vendor)

---

### get_anomaly_feed(filters)

**Queries:** Postgres anomalies table.

**Parameters:**
- status_filter: optional, defaults to ['new', 'acknowledged', 'investigating'] (excludes dismissed)
- severity_filter: optional, defaults to all
- entity_filter: optional, filter by entity_type and/or entity_id
- limit: optional, default 20

**What it computes:**

Reads from the anomalies table (populated by Phase 6's intelligence layer). In Phase 3, this sub-agent is built and the endpoint exists, but the anomalies table is empty — it returns an empty list. Phase 6 populates the data.

**Return structure:**
- anomalies: list of {anomaly_id, type, entity_type, entity_id, entity_name (resolved), description, severity, supporting_data, status, detected_at}
- counts: {total, new, acknowledged, investigating}

**Endpoint:** GET /api/anomalies
Query params: ?status=new,acknowledged&severity=warning,critical&entity_type=truck&limit=20

---

### get_memory_search(query, operator_name)

**Queries:** Postgres conversations and conversation_messages tables. pgvector semantic search on conversation summaries.

**What it computes:**

Search past conversations for references to the query topic. Two search modes: keyword search on entities_discussed, topics, and key_findings fields (JSONB contains queries). Semantic search using pgvector if conversation summaries are embedded.

Returns matching conversations with their summaries, entities discussed, and unresolved items.

In Phase 3, this sub-agent is built and the endpoint exists, but the conversations table is empty (populated in Phase 5 when the chat is used). The function returns empty results.

**Return structure:**
- matching_conversations: list of {conversation_id, date, summary, entities_discussed, topics, key_findings, unresolved_items, relevance_score}

**Endpoint:** GET /api/conversations/search
Query params: ?q=brake+issue&operator=james

---

### Graph-Specific Sub-Agents

These sub-agents query Neo4j exclusively and serve relationship exploration use cases.

### get_truck_graph(truck_id)

**Queries:** Neo4j only.

**What it computes:**

Starting from the Truck node, traverse all relationships up to 2 hops: (Truck)-[:PURCHASED_FROM]->(Vendor), (Driver)-[:ASSIGNED_TO]->(Truck), (Truck)-[:MAINTAINED_AT]->(Vendor), (Truck)-[:COVERED_BY]->(InsurancePolicy)-[:ISSUED_BY]->(Vendor), (Truck)-[:REGISTERED_IN]->(state), (Truck)-[:TITLED_IN]->(state), (Truck)-[:HAS_DOCUMENT]->(Document), (Truck)-[:REPORTED_IN]->(IFTAFiling).

Returns the full subgraph as nodes and edges for frontend visualization.

**Return structure:**
- nodes: list of {id, label, type (Truck/Driver/Vendor/etc.), properties}
- edges: list of {source, target, type (ASSIGNED_TO/MAINTAINED_AT/etc.), properties}
- center_node: the truck node id

**Endpoint:** GET /api/trucks/{id}/graph

### get_fleet_graph()

**Queries:** Neo4j only.

**What it computes:**

The complete fleet graph: all Truck nodes, all Driver nodes, all Vendor nodes, and the relationships between them. For large fleets this would need pagination or summarization, but for 23 trucks it's manageable as a complete graph.

**Return structure:**
- nodes: list of all entity nodes with type and key properties
- edges: list of all relationships with type and key properties
- stats: {truck_count, driver_count, vendor_count, relationship_count}

**Endpoint:** GET /api/fleet/graph

### get_entity_connections(entity_type, entity_id, max_hops)

**Queries:** Neo4j only.

**What it computes:**

Generic relationship traversal from any entity. "Show me everything connected to vendor X" or "show me everything connected to driver Y." Traverses up to max_hops (default 2) from the starting node.

**Return structure:**
- nodes: list of connected nodes with types and properties
- edges: list of relationships
- paths: list of distinct paths from the starting node

**Endpoint:** GET /api/graph/connections
Query params: ?type=vendor&id={uuid}&hops=2

---

## API Layer Specifications

### Route Organization

Routes are organized by domain resource, not by sub-agent function name.

**/api/trucks/** — truck-related endpoints
- GET /api/trucks — list all trucks, filterable by status
- GET /api/trucks/{id} → get_truck_identity
- GET /api/trucks/{id}/assignment → get_truck_assignment
- GET /api/trucks/{id}/maintenance → get_truck_maintenance
- GET /api/trucks/{id}/compliance → get_truck_compliance
- GET /api/trucks/{id}/financials → get_truck_financials
- GET /api/trucks/{id}/documents → get_truck_documents
- GET /api/trucks/{id}/graph → get_truck_graph

**/api/drivers/** — driver-related endpoints
- GET /api/drivers — list all drivers, filterable by status and assignment
- GET /api/drivers/{id} → get_driver_profile

**/api/fleet/** — fleet-wide endpoints
- GET /api/fleet/overview → get_fleet_overview
- GET /api/fleet/comparison → get_fleet_comparison
- GET /api/fleet/graph → get_fleet_graph

**/api/compliance/** — compliance-related endpoints
- GET /api/compliance/matrix → get_compliance_matrix

**/api/vendors/** — vendor-related endpoints
- GET /api/vendors → get_vendor_analysis (fleet-wide)
- GET /api/vendors/{id} → get_vendor_analysis (single)

**/api/anomalies/** — anomaly-related endpoints
- GET /api/anomalies → get_anomaly_feed

**/api/documents/** — document-related endpoints (upload from Phase 1, review queue)
- GET /api/documents — list documents with filters
- GET /api/documents/{id} — single document detail
- GET /api/documents/{id}/file — serve the original PDF file for viewing
- GET /api/documents/review — list documents needing review
- POST /api/documents/{id}/review — submit review corrections

**/api/conversations/** — conversation-related endpoints
- GET /api/conversations/search → get_memory_search

**/api/graph/** — generic graph endpoints
- GET /api/graph/connections → get_entity_connections

### Request/Response Standards

All list endpoints support: ?page=1&per_page=20 for pagination, ?sort_by=field&sort_order=asc|desc for sorting.

All entity endpoints accept either UUID or the domain identifier (unit_number for trucks, driver_code for drivers). The route handler resolves the identifier to a UUID before calling the sub-agent.

Error responses follow a consistent structure: {error_code: string, message: string, details: object or null}. Error codes: NOT_FOUND, VALIDATION_ERROR, INTERNAL_ERROR, DATABASE_ERROR.

### CORS Configuration

Allow origins: http://localhost:3000 (React dev server). Allow methods: GET, POST, PUT, DELETE, OPTIONS. Allow headers: Content-Type, Authorization. Allow credentials: true (for future auth).

### Document File Serving

GET /api/documents/{id}/file serves the original PDF from the document storage directory. This enables the frontend to render the PDF in an iframe or PDF viewer component alongside the extracted data. The response sets Content-Type: application/pdf and appropriate caching headers.

---

## Parallel Execution Infrastructure

When the frontend requests a truck detail page, it makes 6 parallel API calls. On the backend, each API call runs its sub-agent function independently. But for the fleet comparison endpoint, which needs to run financial analysis for multiple trucks, the backend itself uses asyncio.gather to parallelize the per-truck computations.

The parallel execution pattern:

For fleet comparison with 16 trucks: create 16 coroutines (one per truck), each running the financial computation. Execute all 16 with asyncio.gather. Collect results. Sort and rank. Return.

For compliance matrix: similar pattern — 16 parallel compliance checks, one per truck.

Database connection pooling is critical here. The async database session pool must support enough concurrent connections for parallel sub-agent execution. With 16 trucks and a sub-agent that makes 3-4 queries each, that's 48-64 concurrent queries during a fleet comparison request. The connection pool size should be configured accordingly (minimum 20 connections for MVP).

Neo4j driver connection pooling follows the same principle — the Neo4j driver maintains a pool of bolt connections that are shared across concurrent queries.

---

## Phase 3 Acceptance Criteria

1. GET /api/fleet/overview returns correct fleet composition (23 trucks, 16 active, 4 sold, 20 drivers, 16 assigned, 4 unassigned), correct compliance snapshot, correct financial summary, and recent document activity from the 247 processed documents.

2. GET /api/trucks/{id} for truck 19 (or unit=19) returns: unit 19, VIN 3HSDZAPR7GN145782, 2016 International ProStar LT625, Blue, active, acquired June 21 2022, $51,000, from Roadrunner Equipment Sales, initial odometer 640,300.

3. GET /api/trucks/{id}/assignment for truck 6 returns: current driver Ramon Castillo, driver code D01, CDL K08-44-2917, class A, endorsements T,N, assigned since the CDL issue date.

4. GET /api/trucks/{id}/maintenance for truck 19 returns correct total spend (sum of all invoices for unit 19), correct event count, breakdown by category matching the invoices in the dataset, breakdown by vendor, and fleet comparison metrics.

5. GET /api/trucks/{id}/compliance for any active truck returns the insurance card details (policy GWCA-KS-77 04188, Great West Casualty, effective Jan 1 2026, expiry Dec 31 2026), the IRP registration details with correct plate number and expiry, the title details, and the assigned driver's CDL expiry status.

6. GET /api/trucks/{id}/financials for any active truck returns total cost of ownership computed from purchase price + sum of maintenance invoices + sum of registration fees.

7. GET /api/compliance/matrix returns a grid of 16 active trucks × 6 compliance categories. Every insurance cell shows the GWCA policy with Dec 31 2026 expiry. Every registration cell shows the IRP expiry. Every driver CDL cell shows the correct driver's CDL expiry.

8. GET /api/fleet/comparison returns all active trucks ranked by total cost of ownership with fleet averages computed correctly.

9. GET /api/vendors returns all 11 service vendors ranked by total spend with correct counts of which trucks each vendor has serviced.

10. GET /api/drivers/D03 returns Sergei Volkov's full profile with CDL details and assignment to truck 19.

11. GET /api/trucks/{id}/graph returns a valid Neo4j subgraph with the truck as center node, connected to its driver, its vendors, its insurance policy, and its documents.

12. GET /api/fleet/graph returns the complete fleet graph with all 23 trucks, 20 drivers, all vendors, and their relationships.

13. GET /api/documents/{id}/file serves the original PDF with correct Content-Type headers.

14. GET /api/documents/review returns any documents with processing_status 'needs_review' from Phase 2 processing.

15. All endpoints return properly structured Pydantic-validated JSON responses with consistent error handling.

16. Parallel execution works: GET /api/fleet/comparison for all active trucks completes within 3 seconds (parallel per-truck computations, not sequential).

---

## What Phase 3 Does NOT Build

- No frontend UI (Phase 4)
- No WebSocket live update delivery (Phase 4 — the NOTIFY events from Phase 2 exist but nothing pushes them to the frontend yet)
- No chat agent or LLM integration (Phase 5)
- No anomaly detection logic or data (Phase 6 — the endpoint exists but returns empty)
- No conversation data (Phase 5 — memory search endpoint exists but returns empty)

---

## Dependencies for Phase 4

Phase 4 (Dashboard + WebSocket) requires all API endpoints from Phase 3 to be operational and returning correct data. The frontend components call these endpoints and render the results. Phase 4 also requires the WebSocket infrastructure from Phase 1 to be enhanced with the topic subscription model and delta push logic, using the sub-agent functions from Phase 3 to compute deltas when NOTIFY events arrive.
