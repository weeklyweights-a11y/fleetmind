# Phase 6: Intelligence Layer

## What Gets Built

The proactive intelligence that makes the system think for itself rather than waiting to be asked. Statistical baseline computation per entity. Anomaly detection comparing real-time data against baselines. Compliance deadline alerting that surfaces expiring documents before the operator remembers to check. Five learning loops that make the system smarter over time: extraction accuracy, entity resolution confidence, query understanding, fleet intelligence calibration, and document type evolution. A background process that runs on a schedule, scanning the fleet state for things worth surfacing. Integration with the conversational agent so anomalies and proactive insights appear both on the dashboard and in chat.

After this phase, the system is no longer passive. It tells the operator "truck 19's maintenance spiked 3x last month," "truck 22's registration expires in 12 days and no renewal is on file," "you asked me to keep an eye on truck 19's brakes — another brake job came in yesterday." The anomaly feed page built empty in Phase 4 now populates with real detections. The learning loops mean every operator correction, every dismissed alert, every conversation failure makes the system more accurate.

---

## Baseline Computation

### What Baselines Are

A baseline is a statistical summary of normal behavior for an entity over a time period. It's not a model — it's basic descriptive statistics: mean, standard deviation, count, min, max, trend direction. Baselines enable anomaly detection by defining "what's normal" so deviations can be identified.

### Per-Truck Baselines

Computed for every active truck, stored in the `fleet_metrics` table (created in Phase 1).

**Maintenance cost baseline:** For each truck, compute: average monthly maintenance spend (total spend / months since acquisition), standard deviation of monthly spend, average cost per service event, average number of events per month. Recomputed whenever a new `maintenance_event` is added for the truck.

**Maintenance category baseline:** For each truck, compute: the distribution of spend across categories (what percentage goes to Tires vs Brakes vs Engine, etc.), the expected frequency per category (how many brake events per year is normal for this truck). Enables detecting when a specific category spikes: "truck 19 usually has 1 brake event per year, but it's had 3 in the last 6 months."

**Odometer rate baseline:** For trucks with 2+ mileage records, compute: average daily miles (total miles / days between first and last reading), expected annual mileage. Enables detecting usage changes: "truck 22 averaged 120,000 miles/year but this quarter's rate projects to only 80,000 — is it parked or reassigned?"

**Cost per mile baseline:** For trucks with both cost and mileage data: total cost / total miles driven. This number should be relatively stable — a sudden increase means either costs went up or utilization went down.

### Per-Driver Baselines

**Assignment stability:** How long this driver typically stays on a truck. Frequent reassignments might indicate performance issues or operational needs.

**Trucks operated:** Count of distinct trucks. A driver who's operated 5 trucks in a year has a different profile than one who's been on the same truck for 3 years.

### Per-Vendor Baselines

**Average cost per service:** What this vendor typically charges. Enables detecting price increases: "Jim's Truck Repair's average invoice went from $700 to $950 in the last quarter — 36% increase."

**Service frequency:** How often each truck visits this vendor. Enables detecting if a vendor isn't solving problems: "truck 19 has been to Jim's 3 times in 2 months for brake work — recurring issue not being fixed?"

**Truck coverage:** How many different fleet trucks use this vendor. Changes in vendor usage patterns (fleet shifting away from a vendor, or concentrating at one vendor) are worth surfacing.

### Fleet-Wide Baselines

**Average maintenance cost per truck per month:** The fleet average, used for per-truck comparisons.

**Average cost per service event:** Fleet-wide, used for vendor comparison.

**Compliance health score:** Percentage of all compliance cells that are green. Tracked over time to detect systemic compliance degradation.

**Document processing rate:** Average documents ingested per week. A sudden drop might mean the operator stopped uploading, which means the system's knowledge is going stale.

### Baseline Storage

Baselines are stored in the `fleet_metrics` table with `period_type`, `period_start`, `period_end`, and `computed_at` fields. Each baseline computation overwrites the previous value for that metric/entity/period combination.

Historical baselines are kept — monthly baselines from 6 months ago still exist in the table. This enables trend analysis: is the baseline itself shifting? (Is truck 19's average monthly maintenance cost creeping up over time, not just spiking once?)

### Baseline Computation Schedule

Baselines are recomputed in two ways:

**Event-driven recomputation:** When the extraction pipeline finishes processing a document in Phase 2 (NOTIFY event received), the relevant baselines are recomputed. A new service invoice triggers recomputation of the affected truck's maintenance baselines and the fleet average. This keeps baselines current without waiting for a scheduled batch.

**Scheduled full recomputation:** A daily background job (runs once per day, configurable time) recomputes all baselines for all entities. This catches any drift or data corrections that the event-driven approach might have missed. Also computes period-over-period comparisons (this month vs last month, this quarter vs last quarter).

---

## Anomaly Detection

### Detection Logic

Anomaly detection is NOT machine learning. It's statistical deviation detection with domain-specific rules. For each metric, when the current value deviates significantly from the baseline, an anomaly is created.

### Anomaly Types and Their Detection Rules

**cost_spike** — A truck's maintenance spend in the most recent month exceeds 2 standard deviations above its monthly average. Severity: warning if 2–3 SD, critical if >3 SD. Example: "Truck 19 spent $5,080 on maintenance in October vs monthly average of $1,200 (4.2x above average)."

Supporting data stored: `{metric: "monthly_maintenance_spend", current_value: 5080, baseline_mean: 1200, baseline_sd: 800, deviation_sd: 4.85, period: "2025-10"}`.

**frequency_unusual** — A truck had significantly more service events in the recent period than its baseline frequency. Detection: events this month > mean + 2 SD of monthly event count. Example: "Truck 31 had 4 service visits in October vs average of 1.2/month."

**vendor_cost_increase** — A vendor's average invoice amount increased by more than 25% compared to its 6-month rolling average. Applies across all trucks, not per-truck. Example: "Southern Tire Mart's average invoice went from $450 to $620 — 38% increase in the last quarter."

**efficiency_decline** — A truck's cost per mile increased by more than 20% compared to its 6-month rolling average. Requires sufficient odometer data. Example: "Truck 22's cost per mile went from $0.12 to $0.16 over the last 3 months."

**compliance_gap** — A compliance item is missing or about to expire. Three severity levels: info if expiring in 30–60 days, warning if expiring in 7–30 days, critical if expired or expiring within 7 days. Also triggered when a truck has no record for a required compliance category (insurance, registration). Example: "Truck 22's IRP registration expires in 12 days. No renewal document on file."

**missing_document** — A truck has significantly fewer documents than the fleet average for its age. This might indicate that documents aren't being uploaded. Example: "Truck 44 has been in the fleet for 3 years but only has 2 service invoices on record, vs fleet average of 5 per year."

**recurring_issue** — The same maintenance category has appeared 3+ times for the same truck within a 6-month window. Example: "Truck 19 has had 3 brake repairs in 5 months totaling $3,800. Possible recurring issue not being resolved."

### Anomaly Deduplication

Before creating a new anomaly, the system checks if an active (non-dismissed) anomaly of the same type already exists for the same entity with similar supporting data. If so, the existing anomaly is updated (refreshed timestamp, updated supporting data) rather than creating a duplicate. The operator shouldn't see "truck 19 cost spike" as 5 separate anomalies every time the baseline recomputes.

### Anomaly Lifecycle

- **New:** just detected, not yet seen by the operator.
- **Acknowledged:** the operator has seen it and marked it as acknowledged. No further action needed — they're aware.
- **Investigating:** the operator is actively looking into it. The anomaly may be linked to an `unresolved_item` in a conversation.
- **Dismissed:** the operator determined this is not a real issue and provided a reason. The reason is stored in `operator_feedback`.
- **Resolved:** the underlying condition no longer exists (the compliance item was renewed, the cost spike was a one-time overhaul). The system can auto-resolve anomalies when the condition clears.

### Anomaly Auto-Resolution

For **compliance_gap** anomalies: if a new document is ingested that renews the expiring compliance item (a new insurance card with a later expiry date, a new IRP cab card), the anomaly is auto-resolved. The anomaly status changes to `resolved` with a note: "Resolved: new insurance card processed, coverage extended through December 2027."

For **cost_spike** anomalies: if the subsequent month's spend returns to within 1 SD of the baseline, the anomaly can be auto-resolved with a note: "Resolved: maintenance spend returned to normal levels in November."

---

## Compliance Deadline Alerting

Compliance alerting is a specialized form of anomaly detection focused on time-sensitive deadlines.

### Daily Compliance Scan

A daily background job scans all active trucks across all compliance categories. For each compliance item:

- 60+ days remaining: no action
- 30–60 days remaining: create or update a `compliance_gap` anomaly with severity `info`
- 7–30 days remaining: create or update with severity `warning`
- 0–7 days remaining: create or update with severity `critical`
- Expired: create or update with severity `critical` and a stronger description ("EXPIRED — truck may not legally operate")

Missing compliance records (no insurance card on file, no registration) are also flagged with severity `warning` and description "No [compliance type] record on file for truck [unit]."

### Proactive Surfacing

Compliance alerts appear in three places:

**Dashboard anomaly feed:** the anomaly feed shows compliance alerts alongside cost spikes and other anomalies, sorted by severity and urgency.

**Fleet overview upcoming deadlines:** the deadline countdown on the fleet overview page is powered by the same compliance scan data.

**Chat proactive greeting:** When the operator opens the chat, if there are any critical compliance items, the agent can proactively mention them: "Good morning. Heads up — truck 22's registration expires in 5 days." This is triggered by checking the anomalies table for critical compliance items when a new conversation starts (in the `load_context` node of the LangGraph state machine). The agent includes this proactive information in its context and mentions it in response to a greeting or "what's new" type question.

---

## Unresolved Items Processing

In Phase 5, the conversation system tracks unresolved items — things the operator said to follow up on. In Phase 6, a background process checks these against new data.

### Background Unresolved Items Check

A periodic job (runs every 6 hours or on each document ingestion event) scans the conversations table for active unresolved items:

```sql
SELECT unresolved_items FROM conversations
WHERE unresolved_items IS NOT NULL
AND unresolved_items != '[]'
AND ended_at > (now() - interval '30 days')
```

For each unresolved item, the system checks if relevant new data has appeared since the conversation ended. An unresolved item like "keep an eye on truck 19's brakes" triggers: query `maintenance_events` WHERE `truck_id` = (truck 19's ID) AND `category` = 'Brakes' AND `service_date` > (conversation `ended_at`). If new brake events exist, create an anomaly of type `recurring_issue` or `cost_spike` (whichever applies) with a note: "Follow-up: you asked to monitor truck 19's brakes on [conversation date]. A new brake repair was recorded on [date] for [cost] at [vendor]."

This anomaly appears in the anomaly feed and can be discussed in chat. When the operator asks "anything I was tracking," the `get_anomaly_feed` sub-agent returns these follow-up anomalies alongside regular detected anomalies.

### Unresolved Item Expiration

Unresolved items from conversations older than 30 days are considered stale. The background job stops checking them. If the operator asks about old items, the chat can still search conversation history, but the proactive monitoring stops.

---

## Learning Loops

### Loop 1: Extraction Accuracy

**What feeds it:** The `extraction_corrections` table (populated when humans correct extraction errors in the review queue, or when Layer 6 agentic correction makes a fix).

**What it measures:** Extraction accuracy rate = (documents where all fields passed validation without correction) / (total documents processed). Tracked per document type: invoices might have 95% accuracy while CDLs have 99%.

**How it improves the system:** A weekly background job analyzes the corrections table and generates a correction pattern report:

- Which document types have the most corrections
- Which specific fields are most error-prone (VIN misreads, dollar amount errors, date parsing failures)
- Which vendors' invoices cause the most extraction errors (a specific vendor's unusual format causing repeated misreads)
- Common error patterns (specific character confusions: 0↔O, 1↔l, 5↔S)

This report is stored and accessible through an admin/system health endpoint. It informs manual improvements to the extraction schemas: if "Turbo Specialists Inc" invoices consistently misread the total field, the label dictionary or extraction rule for that vendor needs adjustment.

For future versions: the correction pairs become fine-tuning data for LayoutLMv3 or similar models. But for MVP, the loop produces a diagnostic report that guides manual fixes.

**Metric tracked in `fleet_metrics`:** `metric_name` = `"extraction_accuracy"`, `entity_type` = `"fleet"`, computed per document type and overall.

### Loop 2: Entity Resolution Confidence

**What feeds it:** The `documents` table (`entity_resolution_confidence` field) and human confirmations from the review queue.

**What it measures:** Auto-resolution rate = (documents where entity was resolved automatically with confidence >= 0.9) / (total documents processed). Human review rate = (documents requiring human review for entity resolution) / (total).

**How it improves the system:** Tracks which entity resolution strategies are working. In the Sunflower dataset, unit_number direct lookup resolves 90%+ of documents. But for documents where resolution failed (the 8 failing documents from the Phase 2 status report), the system logs: what identifiers were available (unit number, VIN, both, neither), what the resolution attempt was (lookup, fuzzy match, none), and what the correct resolution was (from human review).

Over time, this data reveals: which document types consistently have resolution issues, whether the problem is extraction (unit number not extracted) or resolution (unit number extracted but doesn't match any truck), and whether the fleet registry needs more aliases or identifiers.

**Metric tracked:** `metric_name` = `"entity_resolution_rate"`, `"human_review_rate"`.

### Loop 3: Query Understanding

**What feeds it:** Conversation patterns where the operator corrects the agent's interpretation.

**Detection:** When the agent responds and the operator's next message is a correction ("no, I meant..." or "not that, I'm asking about..." or rephrasing the same question differently), the system infers that query understanding failed.

**What it measures:** First-response satisfaction rate = (turns where the operator moves on to a new topic or asks a deeper follow-up, indicating the answer was useful) / (total assistant turns). A correction or rephrasing counts as unsatisfied. A follow-up deepening the same topic counts as satisfied.

This metric is computed by the conversation summary generator (Phase 5) when a conversation ends. The LLM analyzes the conversation transcript and identifies which turns were satisfactory and which required correction.

**How it improves the system:** Two pathways.

**Pathway 1 — Operator profile updates:** if operator James consistently uses "cost" to mean "total cost including fuel" rather than "maintenance cost only," this preference is recorded in the operator profile. Future query understanding for James applies this preference.

**Pathway 2 — Global defaults:** if 80% of operators interpret "recently" as last 30 days, the query understanding prompt's default for "recently" should be 30 days, not 7.

These improvements are manual for MVP — the system generates the diagnostic data, a developer reviews and updates prompts or defaults.

**Metric tracked:** `metric_name` = `"query_satisfaction_rate"`.

### Loop 4: Fleet Intelligence Calibration

**What feeds it:** Operator actions on anomalies (acknowledge, investigate, dismiss with reason).

**What it measures:** Anomaly precision = (anomalies the operator acknowledged or investigated) / (total anomalies surfaced). A high dismiss rate means the system is noisy. A low dismiss rate means the detections are relevant.

**How it improves the system:**

When an operator dismisses an anomaly with a reason, the system learns what's NOT anomalous. Examples:

"Dismissed: truck 19 cost spike — planned engine overhaul, expected." The system learns: a single high-cost event followed by return-to-normal is likely a planned overhaul, not a true anomaly. Future detection can incorporate this pattern: check if the cost spike is a single event >$10,000 in a category like Engine or Transmission. If so, reduce severity from critical to info and add a note "possible planned overhaul" rather than alarming the operator.

"Dismissed: not a real issue, this always happens in winter." The system learns: seasonal patterns exist. Future detection could adjust baselines by season if enough data accumulates.

"Dismissed: we already know about this." The system learns: this anomaly was already covered in conversation. The deduplication logic should cross-reference active anomalies with recent conversation `key_findings` to avoid surfacing things the operator already discussed.

For MVP, dismissed anomalies with reasons are stored but the adjustments are manual. The diagnostic data is available for a developer to tune thresholds and rules.

**Metrics tracked:** `metric_name` = `"anomaly_precision"`, `"anomaly_dismiss_rate"`.

### Loop 5: Document Type Evolution

**What feeds it:** Documents classified as `"unknown"` by the classifier.

**What it measures:** Unknown document rate = (documents classified as `"unknown"`) / (total documents processed). Should be 0% for the Sunflower dataset (all types are known). Becomes relevant when new tenants upload document types the system hasn't seen.

**How it surfaces:** When 3+ documents are classified as `"unknown"` within a 30-day period, the system creates an anomaly: "3 unrecognized documents uploaded in the last month. These may be a new document type. Review and define." The operator can view the unrecognized documents in the review queue.

**How it improves the system:** A developer or system administrator defines a new document type: adds a classification rule (keywords or patterns), an extraction schema (target fields and label dictionaries), and a normalization mapping (which Postgres table the extracted data writes to). Once defined, existing `"unknown"` documents of that type can be reprocessed.

For MVP, this is entirely manual — the system detects and alerts, the human defines and configures.

**Metric tracked:** `metric_name` = `"unknown_document_rate"`.

---

## Background Processes

### Process 1: Daily Compliance Scanner

**Runs:** Once daily at a configurable time (default: 6:00 AM local time).

**What it does:** Queries all compliance tables (`insurance_coverages`, `registrations`, `titles`, `emission_certs`) for every active truck. Computes days until expiry for each item. Creates or updates `compliance_gap` anomalies based on the severity thresholds (60/30/7/0 days). Auto-resolves any `compliance_gap` anomalies where a newer record now exists with a later expiry date.

Also checks driver CDL and medical cert expiry dates through the assignments → drivers join.

**Output:** Updated `anomalies` table. NOTIFY event emitted: `{type: "anomalies_updated", count: N}` so the dashboard anomaly feed refreshes via WebSocket.

### Process 2: Event-Driven Baseline Update

**Runs:** Triggered by each document ingestion completion (via the NOTIFY event from the extraction worker).

**What it does:** Identifies which truck was affected by the new document. Recomputes that truck's baselines (maintenance cost, frequency, odometer rate). Recomputes the fleet average for the affected metrics. Checks the new data against the updated baselines for anomalies (cost spike, frequency unusual, etc.). Creates anomalies if detected.

**Output:** Updated `fleet_metrics` rows. New anomalies if detected. NOTIFY event if anomalies were created.

### Process 3: Daily Full Baseline Recomputation

**Runs:** Once daily, after the compliance scanner.

**What it does:** Recomputes all baselines for all entities. This catches corrections, deletions, or data changes that the event-driven updates might have missed. Also computes period-over-period comparisons (this month vs last month, this quarter vs last quarter) that the event-driven approach doesn't cover.

**Output:** Updated `fleet_metrics` rows with current baselines.

### Process 4: Unresolved Items Checker

**Runs:** Every 6 hours, or triggered by document ingestion for entities with active unresolved items.

**What it does:** Scans conversations for active unresolved items (less than 30 days old). For each, queries the relevant normalized tables for new data since the conversation ended. If new relevant data exists, creates an anomaly linking back to the unresolved item and the original conversation.

**Output:** Anomalies with a `follow_up` flag and a reference to the original conversation and unresolved item.

### Process 5: Weekly Learning Loop Report

**Runs:** Once weekly (default: Sunday midnight).

**What it does:** Generates the diagnostic reports for all 5 learning loops:

- Extraction accuracy by document type and field
- Entity resolution success rates and failure patterns
- Query understanding satisfaction rates and common misinterpretations
- Anomaly precision and dismiss patterns
- Unknown document type accumulation

**Output:** Stored as a system report accessible via an admin endpoint. Not surfaced to the fleet operator — this is for the system administrator/developer.

### Implementation Notes for Background Processes

All background processes run as periodic tasks within the extraction worker process (or as a separate lightweight worker process). They share the same database connections and code as the main extraction pipeline.

**Scheduling:** use APScheduler (Advanced Python Scheduler) or a simple asyncio loop with sleep intervals. No need for Celery or a heavyweight scheduler for MVP.

Each process is idempotent — running it twice produces the same result. If the daily scanner runs twice due to a restart, it updates the same anomalies rather than creating duplicates.

Each process logs its execution: start time, entities processed, anomalies created/updated/resolved, duration. These logs are queryable for system health monitoring.

---

## System Health Dashboard

A separate section (accessible via `/admin/health` or a dedicated tab) showing the learning loop metrics and system health. This is for the system builder, not the fleet operator.

**Extraction Health Panel:**

- Overall accuracy rate (documents passing validation without correction)
- Accuracy rate by document type (which types are most error-prone)
- Most corrected fields (ranked list of field names with correction counts)
- Correction trend over time (accuracy should improve as fixes are applied)

**Entity Resolution Health Panel:**

- Auto-resolution rate
- Human review rate
- Most common resolution failures (which trucks/drivers consistently fail to resolve)

**Conversation Quality Panel:**

- Total conversations
- Average turns per conversation
- Query satisfaction rate
- Most common intents (what operators ask about most)
- Most common clarification triggers (what questions confuse the agent)

**Fleet Intelligence Panel:**

- Total anomalies detected
- Anomaly precision (acknowledged + investigated vs total)
- Dismiss rate and common dismiss reasons
- Average time from detection to acknowledgement

**System Activity Panel:**

- Documents processed per day/week/month
- Processing success rate
- Average processing time per document
- Queue depth over time
- Background process execution history

---

## Integration with Chat Agent

Phase 6 adds new capabilities to the conversational agent built in Phase 5.

### Proactive Greeting

When a conversation starts and the `load_context` node runs (Phase 5), it now also checks for critical anomalies and compliance items. If any exist, they're included in the conversation context. When the operator sends a greeting ("good morning," "hey"), the synthesis includes the proactive information: "Good morning! A couple things to flag: truck 22's registration expires in 5 days, and truck 19 had a maintenance cost spike last month — $5,080 vs its usual $1,200/month."

This is not a separate LLM call — it's additional context passed to the existing LLM Call 2 during synthesis.

### Anomaly Discussion

The operator can ask about anomalies: "what's flagged right now," "show me the anomalies," "anything unusual." The `get_anomaly_feed` sub-agent returns the active anomalies. The agent presents them conversationally with context: "Three items flagged. Most urgent: truck 22's registration expires Thursday. Second: truck 19's October maintenance was 4x above average — that was the engine overhaul at Cummins. Third: Southern Tire Mart's pricing went up 38% this quarter."

The operator can then interact with anomalies through chat: "dismiss the truck 19 one, that was planned." The agent updates the anomaly status to `dismissed` with the operator's reason. "Tell me more about the tire pricing" → the agent calls `get_vendor_analysis` for Southern Tire Mart and provides the detailed breakdown.

### Follow-Up Reminders

When the operator asks "anything I was tracking" or "what was I keeping an eye on," the agent checks: (1) unresolved items from recent conversations via `get_memory_search`, (2) anomalies with a `follow_up` flag from the background unresolved items checker. It presents both: "You asked to monitor truck 19's brakes on June 30. Since then, one more brake repair came in — $800 at Jim's on July 5. That's the 4th brake job in 6 months, totaling $4,600."

---

## Phase 6 Acceptance Criteria

1. The `fleet_metrics` table contains computed baselines for every active truck: monthly maintenance average, cost per event average, event frequency, and cost per mile (where sufficient odometer data exists).

2. Fleet-wide baselines exist: average maintenance cost per truck, average cost per event, fleet compliance score.

3. Vendor baselines exist: average cost per service for each vendor with 3+ service events.

4. The daily compliance scanner correctly identifies all compliance items expiring within 90 days and creates anomalies with appropriate severity (info for 30–60 days, warning for 7–30 days, critical for <7 days or expired).

5. Cost spike detection works: manually inserting a `maintenance_event` with a cost >3x the truck's baseline triggers a `cost_spike` anomaly with correct supporting data.

6. Recurring issue detection works: if a truck has 3+ maintenance events in the same category within 6 months, a `recurring_issue` anomaly is created.

7. Vendor cost increase detection works: if a vendor's recent average exceeds 125% of their 6-month rolling average, a `vendor_cost_increase` anomaly is created.

8. Compliance auto-resolution works: when a new insurance card with a later expiry date is ingested for a truck that had a `compliance_gap` anomaly, the anomaly status changes to `resolved` with an appropriate note.

9. Anomaly deduplication works: the same anomaly condition detected on consecutive baseline recomputations does not create duplicate anomaly records.

10. Dismissing an anomaly with a reason stores the feedback in the `anomalies` table and the anomaly no longer appears in the active feed.

11. The anomaly feed on the dashboard (built in Phase 4 as empty) now populates with real detections, sorted by severity and recency.

12. Unresolved items from conversations are checked by the background process. After creating an unresolved item about truck 19's brakes in Phase 5, then ingesting a new brake invoice for truck 19, the system creates a follow-up anomaly referencing the original conversation.

13. The chat agent responds to "anything I should worry about" with real anomalies from the anomaly feed, prioritized by severity.

14. The chat agent responds to proactive greeting context: when critical compliance items exist, a greeting like "good morning" includes the compliance alert.

15. Dismissing an anomaly through chat ("dismiss that, it was planned") updates the anomaly status correctly.

16. The weekly learning loop report generates with: extraction accuracy per document type, entity resolution rates, query satisfaction rate, anomaly precision rate.

17. The system health dashboard (admin view) displays all learning loop metrics with current values.

18. All background processes are idempotent — running them twice produces the same anomaly state without duplicates.

19. Background processes log their execution with timing, entity counts, and anomaly creation/resolution counts.

20. Event-driven baseline updates fire correctly: ingesting a new service invoice triggers baseline recomputation for the affected truck and anomaly checking against the updated baseline.

---

## What Phase 6 Completes

Phase 6 is the final phase. After this phase, FleetMind is a complete fleet document intelligence platform:

- Documents are ingested through a 7-layer extraction pipeline that validates, corrects, and normalizes data (Phase 2)
- Normalized data lives in Postgres with relationships in Neo4j (Phase 1 + 2)
- Sub-agent functions compute fleet intelligence on demand from the normalized data (Phase 3)
- A live dashboard shows the fleet's complete state with real-time updates via WebSocket (Phase 4)
- A conversational agent lets operators ask any question in natural language with context carried across turns and sessions (Phase 5)
- The system proactively detects anomalies, alerts on compliance deadlines, tracks follow-ups, and gets smarter over time through operator feedback (Phase 6)

Every question from the original problem statement is answerable: "How much did I spend on parts last month?" (SQL query via sub-agent), "Where's the tax form for truck 84?" (document retrieval via sub-agent), "How much did I spend on parts for truck 62 — and show me the receipts?" (hybrid: SQL aggregation + document retrieval, both via sub-agents, combined by the chat agent). And the system goes beyond the problem statement: it doesn't just answer questions, it raises them.

---

## What Phase 6 Does NOT Build

- No new document types or extraction schemas beyond alerting on unknown types (manual definition remains a developer task)
- No ML-based anomaly detection or predictive maintenance forecasting
- No automatic prompt tuning from learning loops (MVP produces diagnostic reports; threshold and prompt changes are manual)
- No multi-tenant admin isolation beyond the existing tenant_id column
- No mobile push notifications or email alerts (dashboard + chat + WebSocket only)
