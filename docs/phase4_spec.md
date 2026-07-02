# Phase 4: Dashboard + WebSocket

## What Gets Built

The complete React frontend with all dashboard pages, every panel component mapped to a sub-agent function, the WebSocket event system for live updates, the file upload experience with real-time processing status, the document viewer, the human review interface, and the chat UI shell (visual only — the chat agent logic comes in Phase 5). After this phase, the operator opens a browser and sees their entire fleet — every truck, every driver, every dollar, every deadline — all updating in real-time as documents are processed.

---

## WebSocket Event System

This is the nervous system of the entire dashboard. Before building any UI components, the WebSocket infrastructure must be complete because every component depends on it for live updates.

### Backend: WebSocket Manager

The WebSocket manager in the API server handles four responsibilities.

**Connection lifecycle.** When a browser connects to /ws, the manager assigns a connection_id, stores the connection in an in-memory dict (connection_id → WebSocket object), and registers the connection in Redis (ws_subscriptions hash). When the connection drops (browser close, network failure), the manager removes it from both the in-memory dict and Redis.

**Topic subscription.** The frontend sends subscribe and unsubscribe messages through the WebSocket. Subscribe message: {type: "subscribe", topics: ["fleet_stats", "truck_19_maintenance"]}. The manager updates the Redis subscription state for this connection. Unsubscribe: same format, removes topics. When the frontend navigates from fleet overview to truck 19 detail, it sends an unsubscribe for fleet topics and a subscribe for truck 19 topics in a single message.

**NOTIFY listener integration.** The background asyncio task listening on Postgres NOTIFY channel "document_events" (established in Phase 1) now has real work to do. When a NOTIFY event arrives (from the extraction worker completing a document in Phase 2), the manager determines which topics are affected. A document completing for truck 19 affects topics: truck_19_identity (if it's a Bill of Sale creating the truck), truck_19_maintenance (if it's an invoice), truck_19_compliance (if it's insurance/registration), truck_19_financials (any cost-affecting document), truck_19_documents (any document), fleet_stats (fleet-wide aggregates change), compliance_overview (if compliance status changes). The manager then computes the deltas and pushes them.

**Delta computation and push.** When a topic is affected, the manager calls the relevant sub-agent function to get the fresh data. It compares against the last-known state for that topic (cached in Redis with key pattern topic_cache:{topic_name}). The delta is the difference — which specific values changed. The manager sends the delta to every connection subscribed to that topic.

Delta message format: {type: "data_update", topic: "truck_19_maintenance", timestamp: "ISO datetime", delta: {total_spend: {old: 31280, new: 36360}, event_count: {old: 5, new: 6}, new_event: {date: "2025-10-02", vendor: "Diesel Emissions Co", category: "Emissions", cost: 5080}}}.

Document processing status message format: {type: "document_status", document_id: "uuid", filename: "invoice.pdf", status: "extracting", progress: {current_layer: 3, total_layers: 7}, details: {document_type: "service_invoice", truck_unit: 19}}.

Chat response message format (shell for Phase 5): {type: "chat_response", conversation_id: "uuid", content: "token or full message", streaming: true/false, done: false/true}.

### Frontend: WebSocket Hooks

**useWebSocket hook.** Manages the single WebSocket connection for the entire app. Handles connection establishment, automatic reconnection with exponential backoff (1s, 2s, 4s, 8s, max 30s), and connection state tracking (connecting, connected, disconnected, reconnecting). Provides methods: subscribe(topics), unsubscribe(topics), sendChatMessage(conversationId, content). Exposes the connection state for UI indicators.

**useLiveUpdate hook.** Used by individual panel components to subscribe to specific topics and handle incoming deltas. Takes a topic name and a callback function. On mount: subscribes to the topic via useWebSocket. On unmount: unsubscribes. When a delta arrives for the subscribed topic: calls the callback with the delta data. The component applies the delta to its local state.

**useSubAgent hook.** Wraps API calls to sub-agent endpoints. Takes an endpoint URL and optional params. Returns {data, loading, error, refetch}. On mount: fetches data from the API. Provides refetch() for manual refresh. Integrates with useLiveUpdate: when a delta arrives, the hook can either apply the delta to the existing data (for simple field updates) or trigger a refetch (for complex structural changes).

### Connection State Indicator

A small visual indicator in the dashboard header showing WebSocket connection status: green dot when connected, yellow dot when reconnecting, red dot when disconnected. When disconnected, the indicator shows "Reconnecting..." with the countdown to the next attempt.

---

## Application Shell and Navigation

### Layout Structure

The application uses a fixed layout: top navigation bar (company name, connection indicator, upload button, notification badge, chat toggle button), left sidebar navigation (Fleet Overview, Trucks, Drivers, Compliance, Financials, Vendors, Anomalies), main content area (renders the active page), right slide-out panel (chat sidebar, toggled by the chat button), bottom-right overlay (processing queue, collapsible).

### Routing

React Router with the following routes:

- / → FleetOverview page
- /trucks → Truck list page (table of all trucks)
- /trucks/:id → TruckDetail page (the full truck profile with all panels)
- /drivers → Driver list page
- /drivers/:id → DriverDetail page
- /compliance → ComplianceMatrix page
- /financials → FinancialAnalytics page
- /vendors → VendorAnalysis page
- /vendors/:id → VendorDetail page
- /anomalies → AnomalyFeed page
- /documents → Document list page
- /documents/:id → Document detail page (PDF viewer + extracted data)
- /review → Human review queue page

### Navigation and Subscription Management

When the route changes, the new page component mounts and subscribes to its relevant topics. The previous page component unmounts and its useLiveUpdate hooks unsubscribe. This happens automatically through the hook lifecycle — no manual subscription management needed.

Example: navigating from / (FleetOverview) to /trucks/19 (TruckDetail). FleetOverview unmounts, unsubscribing from fleet_stats, compliance_overview, recent_documents. TruckDetail mounts, subscribing to truck_19_identity, truck_19_assignment, truck_19_maintenance, truck_19_compliance, truck_19_financials, truck_19_documents.

---

## Page Specifications

### Fleet Overview Page (/)

The landing page. Operator's first view every morning. Shows the fleet at a glance.

**Data source:** GET /api/fleet/overview

**WebSocket topics:** fleet_stats, compliance_overview, recent_documents, anomalies

**Components on this page:**

**FleetStatsCards** — Row of summary cards at the top. Card 1: Total Trucks (active count prominently, with sold/inactive as smaller text). Card 2: Total Drivers (assigned count prominently, unassigned count as secondary). Card 3: Fleet Value (sum of purchase prices). Card 4: This Month's Maintenance Spend (with month-over-month change as a percentage badge, green for decrease, red for increase).

**ComplianceOverviewBar** — A single horizontal bar showing the compliance health of the fleet. Green segment = fully compliant trucks. Yellow segment = trucks with warnings. Red segment = trucks with expirations. Each segment is proportional to the truck count. Clicking any segment navigates to the compliance matrix filtered by that status. Below the bar: a count label for each status.

**UpcomingDeadlinesCard** — List of the 5 most urgent compliance deadlines. Each item shows: truck unit number (clickable → truck detail), compliance type (insurance/registration/CDL), expiry date, days remaining, severity color. If no deadlines exist within 90 days, shows "All clear — no upcoming deadlines."

**RecentActivityFeed** — Chronological list of the last 10 documents processed. Each item: document type icon, truck unit number, document description (e.g., "Service Invoice — Brakes — $1,200"), time ago ("2 hours ago"), processing status badge (green for complete, yellow for needs review). Live-updated through WebSocket — new documents appear at the top of the list as they complete processing.

**AnomalyPreview** — Shows the top 3 anomalies by severity (if any exist — populated in Phase 6). Each shows the description and affected entity. "See all" link navigates to /anomalies. In Phase 4 this section is built but shows "No anomalies detected" until Phase 6 populates the data.

**QuickStatsRow** — A row of smaller metrics at the bottom: total maintenance events, total vendors, fleet average cost per mile, most expensive truck this month. These are secondary/reference metrics, not action-driving.

### Truck List Page (/trucks)

**Data source:** GET /api/trucks (list endpoint)

**WebSocket topics:** fleet_stats (for overall count changes)

**Components:**

**TruckTable** — Sortable, filterable table of all trucks. Columns: Unit # (sortable), Make/Model (sortable), Year (sortable), Status (filterable: active/sold/inactive), Driver (current assigned driver name), Compliance (a summary indicator: green dot, yellow dot, red dot), Total Maintenance Spend (sortable, right-aligned dollar amount). Each row is clickable → navigates to /trucks/:id. Filter controls at the top: status dropdown, search by unit number or VIN.

### Truck Detail Page (/trucks/:id)

The most important page in the product. Shows everything about one truck.

**Data sources:** Parallel API calls to all sub-agent endpoints for this truck.

**WebSocket topics:** truck_{id}_identity, truck_{id}_assignment, truck_{id}_maintenance, truck_{id}_compliance, truck_{id}_financials, truck_{id}_documents

**Layout:** Two-column layout. Left column (wider, ~60%): identity panel at top, then maintenance panel (largest), then financial panel. Right column (~40%): compliance panel at top, then assignment panel, then documents panel. Each panel loads independently and shows its own loading state.

**IdentityPanel** — The truck's header card. Large unit number display. VIN (monospaced font, copyable). Year Make Model in a subtitle. Color indicator (a small colored circle). Status badge (Active = green, Sold = grey with sold date). Acquisition details: purchased from [vendor] on [date] for [price] at [odometer] miles. If sold: sold to [buyer] on [date] for [price]. Current odometer (most recent reading) with the date and source.

**AssignmentPanel** — Current driver card: driver name (clickable → driver detail), driver code, CDL class and endorsements, CDL expiry with status indicator. Below: assignment timeline showing historical drivers as a horizontal timeline with date ranges. If no current driver (sold truck): "No current assignment" with explanation.

**MaintenancePanel** — The richest panel. At the top: total spend as a large number, event count, average per event. A trend line chart (Recharts LineChart) showing monthly maintenance spend over time. Below the chart: two side-by-side breakdowns — by category (Recharts PieChart or horizontal BarChart) and by vendor (horizontal BarChart). Below the breakdowns: a scrollable list of all maintenance events, most recent first. Each event shows: date, vendor name, category, description, cost, payment status badge. Clicking an event opens the source document in the document viewer. Fleet comparison indicator: a small callout showing "12% above fleet average" or "8% below fleet average" with an arrow icon.

Pattern alerts: if the sub-agent detected patterns (recurring brake issues, cost escalation), these appear as colored alert banners within the panel — yellow for informational patterns, red for concerning ones. Each alert has a description and a "details" link.

**CompliancePanel** — Vertical stack of compliance items. Each item is a row: compliance type label (Insurance, Registration, Title, Emission, Driver CDL), status indicator (colored circle: green/yellow/red/grey), expiry date, days remaining as a countdown. Rows are sorted by urgency — red items first, then yellow, then green, then grey. Each row expands on click to show details (policy number, insurer, plate number, etc.) and a "View document" link.

**FinancialPanel** — Total cost of ownership as a large number. Below it: a breakdown (Recharts stacked BarChart or horizontal BarChart) showing acquisition cost, maintenance cost, registration fees as segments. Cost per mile (if available) displayed prominently with fleet comparison. Book value with depreciation. A compact table: metric, this truck, fleet average, difference.

**DocumentsPanel** — Grouped list of documents by type. Each group header shows the type name and count. Under each group: individual documents with document number, date, and a "View" button that opens the document viewer. At the bottom: a small upload zone specific to this truck — "Drop files here to add documents to truck [unit]."

### Driver List Page (/drivers)

**Data source:** GET /api/drivers

**Components:** Similar table format to truck list. Columns: Driver Code, Name, CDL Class, Endorsements, CDL Expiry (with status color), Current Truck (unit number, clickable), Status. Sortable and filterable.

### Driver Detail Page (/drivers/:id)

**Data sources:** GET /api/drivers/{id}

**WebSocket topics:** driver_{id}_profile

**Components:**

**DriverIdentityPanel** — Name, driver code, CDL details (number, state, class, endorsements, restrictions), DOB, address, physical description. CDL expiry with a prominent countdown and status color.

**AssignmentHistoryPanel** — Timeline of truck assignments. Current truck highlighted. Each assignment shows: truck unit number (clickable), make/model, date range, duration.

**RelationshipGraphPanel** — Visualization of the driver's Neo4j graph: the driver node connected to trucks they've driven, which connect to vendors that serviced those trucks. Rendered using a simple force-directed graph layout (D3 or a React graph library).

### Compliance Matrix Page (/compliance)

**Data source:** GET /api/compliance/matrix

**WebSocket topics:** compliance_matrix

**Components:**

**ComplianceGrid** — The centerpiece. A table/grid with truck units as rows and compliance categories as columns. Each cell is a colored square (green/yellow/red/grey) with the expiry date or status text inside. Clicking a cell expands to show details and a link to the source document.

Row headers: truck unit number + make/model (e.g., "Unit 19 — International ProStar").

Column headers: Insurance, Registration, Title, Emission, Driver CDL, Medical Cert.

The grid is sorted by compliance urgency — trucks with red cells at the top, then yellow, then all-green at the bottom.

**ComplianceScore** — A percentage prominently displayed above the grid: "Fleet Compliance: 91.7%". A progress bar showing green/yellow/red proportions.

**DeadlineCountdown** — Below the grid: a chronological list of all upcoming expirations within 90 days. Each item: truck unit, compliance type, expiry date, days remaining, severity badge. This list updates live as time passes (days remaining decrements) and as new compliance documents are ingested (items get resolved).

### Financial Analytics Page (/financials)

**Data source:** GET /api/fleet/comparison, GET /api/fleet/overview (financial section)

**WebSocket topics:** fleet_stats

**Components:**

**FleetCostOverview** — Total fleet cost of ownership. Total maintenance spend. Average cost per truck. Average cost per mile (across trucks with sufficient data).

**CostComparisonChart** — Horizontal bar chart (Recharts BarChart) showing each active truck's total cost of ownership, sorted highest to lowest. Each bar is segmented by cost type (acquisition, maintenance, registration). The fleet average is shown as a vertical reference line.

**MonthlyCostTrend** — Line chart showing fleet-wide monthly maintenance spend over time. Optionally overlay individual truck trends.

**VendorSpendBreakdown** — Pie chart or treemap showing spend distribution across vendors. Click a vendor segment → navigate to vendor detail.

**CategoryBreakdown** — Bar chart showing total spend by maintenance category across the fleet. Which categories consume the most budget fleet-wide.

### Vendor Analysis Page (/vendors)

**Data source:** GET /api/vendors

**Components:**

**VendorTable** — Ranked table: vendor name, total spend, event count, trucks serviced, average cost per service, most common category. Sortable by any column. Clickable rows → vendor detail.

**VendorConcentrationIndicator** — Visual showing what percentage of total spend goes to the top vendor and top 3 vendors. A warning if concentration exceeds 50% for a single vendor.

### Vendor Detail Page (/vendors/:id)

**Data source:** GET /api/vendors/{id}

**Components:** Vendor identity, service summary, spend by truck (bar chart), spend by category (bar chart), cost trend over time (line chart), fleet comparison (average cost vs fleet-wide average), relationship graph from Neo4j.

### Anomaly Feed Page (/anomalies)

**Data source:** GET /api/anomalies

**WebSocket topics:** anomalies

**Components:**

**AnomalyList** — Chronological list of anomalies, filterable by severity and status. Each anomaly card shows: severity badge (info/warning/critical), description, affected entity (clickable → entity detail), supporting data (the numbers that triggered the detection), detected date, status. Action buttons: Acknowledge (marks as seen), Investigate (adds to unresolved items), Dismiss (requires a reason — feeds learning loop).

In Phase 4 this page is built but shows empty state until Phase 6 populates anomaly data.

### Document List Page (/documents)

**Data source:** GET /api/documents

**Components:**

**DocumentTable** — All 247 documents with: filename, document type, truck unit, date, processing status badge, confidence score. Filterable by type, status, truck. Sortable. Clickable → document detail.

### Document Detail / Viewer Page (/documents/:id)

**Data source:** GET /api/documents/{id}, GET /api/documents/{id}/file

**Components:**

**SplitView** — Left side: the original PDF rendered in an iframe or PDF.js viewer (using the file serving endpoint). Right side: the extracted data displayed as a structured form with field labels and values. Fields that were corrected by the agentic layer or human review are marked with a small indicator.

Navigation: prev/next document buttons for reviewing multiple documents in sequence.

### Human Review Queue Page (/review)

**Data source:** GET /api/documents/review

**Components:**

**ReviewQueue** — List of documents with processing_status = "needs_review". Each item shows: filename, document type, truck unit, the specific validation failures.

**ReviewInterface** — Clicking a review item opens the split view (PDF on left, extracted data on right). Fields that failed validation are highlighted with the validation error message. The reviewer can: edit the field value directly, approve the current extraction (accept as-is), or reject the document entirely. On submit: POST /api/documents/{id}/review with the corrections. The dashboard updates via WebSocket to reflect the corrected data.

---

## Upload Experience

### UploadZone Component

A persistent upload area accessible from any page. Two states: collapsed (a small "Upload Documents" button in the header bar) and expanded (a full drop zone overlay).

**Drag and drop:** Dragging files over any part of the dashboard activates the drop zone overlay. The overlay shows "Drop files to upload" with a visual indicator. Releasing the files triggers the upload.

**Click to browse:** Clicking the upload button or the expanded drop zone opens the file picker. Accepts .pdf, .jpg, .jpeg, .png, .tiff files. Multiple file selection enabled.

**Batch upload:** When multiple files are selected or dropped, they are uploaded sequentially (to avoid overwhelming the server) with a batch progress indicator: "Uploading 5 of 15 files..."

Each file is uploaded via POST /api/documents/upload (single file) or POST /api/documents/upload/batch (multiple files). The endpoint returns document IDs immediately.

### ProcessingQueue Component

A collapsible panel in the bottom-right corner of the dashboard. Shows all documents currently being processed.

**Collapsed state:** A small badge showing the count of documents in the queue: "3 processing" or "All documents processed" (with the count of today's uploads).

**Expanded state:** A scrollable list of document cards, most recent at top. Each card shows:
- Filename
- A progress indicator showing the current extraction layer (Layer 1: Parsing, Layer 2: Layout, Layer 3: Extracting, Layer 4: Normalizing, Layer 5: Validating, Layer 6: Correcting, Layer 7: Saving). Rendered as a step indicator or progress bar with 7 steps.
- Current status text
- When complete: a summary of what was extracted (document type, truck unit, key fields)
- When failed: error message with a "View details" link
- When needs review: "Needs review" badge with a "Review" link → opens the review interface

All status updates arrive through WebSocket (document_status message type). The processing queue never polls — it renders whatever the WebSocket delivers.

**The demo moment:** Operator drags 247 PDFs onto the dashboard. The processing queue expands and shows 247 items. Documents start processing in waves (Bills of Sale first, then CDLs, then the rest). Each document card shows progress through the 7 layers. As documents complete, the dashboard panels update — trucks appear, drivers appear, compliance fills in, maintenance history builds. The operator watches their fleet come alive in real-time.

---

## Graph Visualization Component

### FleetGraphView

Used on the fleet overview page (as an optional tab/view toggle) and on individual entity detail pages.

**Data source:** GET /api/fleet/graph or GET /api/trucks/{id}/graph

**Rendering:** A force-directed graph layout using a React-compatible graph library. Nodes are colored by type: trucks = blue, drivers = green, vendors = orange, insurance policies = purple. Node size reflects importance (trucks are largest, documents smallest). Edges are labeled with relationship type and key properties (dates, costs).

**Interaction:** Nodes are clickable — clicking a truck node navigates to the truck detail page. Hovering a node shows a tooltip with key properties. Hovering an edge shows relationship properties (assignment dates, service costs). Zoom and pan controls. A legend showing node type colors.

**Scale consideration:** For 23 trucks, 20 drivers, and 11 vendors, the graph has ~54 core nodes plus relationship edges. This is easily renderable. For larger fleets, the graph would need filtering (show only active trucks, show only maintenance relationships, etc.).

---

## Responsive Behavior

The dashboard is primarily designed for desktop (1280px+ viewport). However, basic mobile responsiveness should work:
- On tablet (768-1279px): two-column truck detail collapses to single column, sidebar navigation collapses to a hamburger menu.
- On mobile (<768px): single column layout, navigation as a bottom tab bar or hamburger, charts resize to fit width, tables become horizontally scrollable.

The chat sidebar becomes a full-screen overlay on mobile.

---

## Loading and Empty States

**Loading states:** Each panel shows a skeleton loader (grey placeholder shapes matching the panel layout) while its sub-agent API call is in flight. Panels load independently — the identity panel (single row lookup, fastest) appears first, then assignment, then compliance, then maintenance and financials (aggregation queries, slowest). The operator sees content progressively, not a single loading spinner for the entire page.

**Empty states:** When data doesn't exist for a panel (e.g., a truck with no maintenance events, a driver with no assignment), the panel shows a purposeful empty state message: "No maintenance events recorded" with a subtle prompt: "Upload service invoices to build maintenance history." Empty states are never blank — they guide the operator toward the action that would populate the data.

**Error states:** If a sub-agent API call fails, the panel shows an error message with a retry button. Other panels on the same page are not affected — only the failed panel shows the error. The retry button calls refetch() from the useSubAgent hook.

---

## Chat UI Shell

The chat UI is built in Phase 4 as a visual shell. The actual chat agent (LLM integration, sub-agent dispatch, conversation memory) is Phase 5. In Phase 4, the chat sidebar is fully interactive visually but sends messages to an echo endpoint that returns a placeholder response.

**ChatSidebar** — A right-side slide-out panel, 400px wide on desktop. Toggle button in the header bar shows/hides it. When open, the main content area narrows to accommodate. On mobile, the sidebar becomes a full-screen overlay.

**ChatMessageList** — Scrollable message list. User messages right-aligned, assistant messages left-aligned. Messages support markdown rendering for formatted responses. When a message references a truck or document, the reference is clickable (navigates to the entity detail page).

**ChatInput** — Text input at the bottom of the sidebar with a send button. Enter key sends. Shift+Enter for new line. The input supports suggested quick actions: when the operator is on truck 19's detail page, the chat input shows suggestion chips like "Why is this truck expensive?" or "Compare with other trucks" — contextual to the current page.

**Streaming placeholder:** In Phase 4, sending a message triggers a mock response with a typing indicator. Phase 5 replaces this with real LLM streaming through the WebSocket.

---

## Phase 4 Acceptance Criteria

1. The fleet overview page loads and displays correct fleet stats, compliance overview, upcoming deadlines, and recent document activity from the 247 processed documents.

2. Clicking a truck in the truck list navigates to the truck detail page, which loads all 6 panels in parallel with progressive rendering — identity panel appears first, then others follow.

3. The compliance matrix page shows the full grid with 16 active trucks × 6 compliance categories. Cell colors are correct (green for 30+ days, yellow for <30 days, red for expired, grey for no record). Clicking a cell shows details.

4. The financial analytics page shows all active trucks ranked by cost, with correct totals and fleet averages. Charts render with correct data from the sub-agent endpoints.

5. WebSocket connection establishes on page load. The connection indicator shows green. If the connection drops (simulate by restarting the API server), the indicator changes to yellow/red and auto-reconnects within 30 seconds.

6. Uploading a PDF through the upload zone creates a document record, the file appears in the processing queue with status "queued", and as the extraction worker processes it (Phase 2 pipeline), the processing queue card progresses through the 7 layers in real-time via WebSocket status updates.

7. When a document finishes processing, the affected dashboard panels update WITHOUT a page refresh. Uploading a new service invoice for truck 19 causes: the maintenance panel on truck 19's detail page to update (total spend changes, new event appears), the fleet overview financial summary to update, and the processing queue card to show "Complete."

8. Topic subscription changes correctly on navigation. Going from fleet overview to truck 19 detail unsubscribes from fleet topics and subscribes to truck 19 topics. Verified by checking that only relevant deltas are received (not fleet deltas while viewing truck detail, not truck 19 deltas while viewing fleet overview).

9. The document viewer page shows the original PDF on the left and extracted data on the right in a split view. The PDF renders correctly in the browser.

10. The human review queue page lists any documents with needs_review status. The review interface allows editing field values and submitting corrections, which update the normalized data and the dashboard reflects the changes via WebSocket.

11. The graph visualization renders on the truck detail page, showing the truck connected to its driver, vendors, insurance policy, and documents. Nodes are clickable and hoverable.

12. The fleet graph renders on the fleet overview page (as a tab or toggle view), showing all trucks, drivers, and vendors with their relationships.

13. The chat sidebar opens and closes from any page. Messages can be typed and sent (returning placeholder responses in Phase 4). The UI supports markdown rendering and clickable entity references.

14. All pages have appropriate loading skeletons, empty states, and error states. No page shows a blank white screen during data loading.

15. The upload experience supports drag-and-drop (dragging over the page activates the drop zone) and batch upload (multiple files with progress tracking).

16. Navigation between pages is smooth with no full page reloads. Browser back/forward buttons work correctly with React Router.

---

## What Phase 4 Does NOT Build

- No actual chat agent logic (Phase 5 — the chat UI is a visual shell with placeholder responses)
- No conversation memory or context tracking (Phase 5)
- No anomaly detection or data (Phase 6 — the anomaly feed page is built but shows empty state)
- No statistical baseline computation (Phase 6)
- No proactive alerts or notifications beyond compliance deadline display (Phase 6)

---

## Dependencies for Phase 5

Phase 5 (Conversational Agent) requires the chat UI shell from Phase 4 to be fully functional — the sidebar, message list, input field, and WebSocket chat message handling. Phase 5 replaces the echo/placeholder response handler with the real chat orchestrator that dispatches LLM calls and sub-agent functions, and streams responses back through the WebSocket. Phase 5 also requires all sub-agent functions from Phase 3 to be operational, as the chat agent dispatches these same functions based on the operator's questions.
