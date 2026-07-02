# Phase 5: Conversational Agent

## What Gets Built

The conversational layer that lets operators talk to their fleet in plain English. Replaces the Phase 4 chat shell placeholder with a real agent powered by two Gemini Flash LLM calls and parallel sub-agent dispatch. LangGraph orchestration managing the reasoning loop. Three-layer conversation memory: turn-level context in Redis, conversation history in Postgres, and operator profiles for long-term personalization. Streaming response delivery through the existing WebSocket connection. Contextual awareness of what the operator is currently viewing on the dashboard.

After this phase, the operator can ask any question about their fleet — "tell me about truck 19," "why is maintenance so high," "compare trucks 19 and 22," "who drives the blue International," "what did we discuss about brakes last week" — and get accurate, grounded answers that reference the real data, cite source documents, and carry context across turns and sessions.

---

## Agent Architecture

The agent uses exactly two LLM calls per question. Everything between them is deterministic Python.

### LLM Call 1: Query Understanding

Takes the operator's message plus conversation context and classifies what the operator is asking.

**Inputs to the LLM:**
- The operator's current message
- The last 5 turns of conversation history (messages + abbreviated sub-agent results from prior turns)
- The current entity focus from turn-level state (if the conversation has been about truck 19, that context is included)
- The current time window from turn-level state (if the operator established "last quarter" as the scope, that's included)
- The operator's current dashboard view (if they're on truck 19's detail page, the LLM knows this — enables "what's going on here" to resolve to truck 19 without the operator saying the unit number)
- The operator profile (frequent topics, preferred response style) from long-term memory

**What the LLM returns (structured output):**

Entity resolution: which entity or entities is the operator asking about. Could be a specific truck (by unit number, VIN, description like "the blue International," or pronoun "it"/"that truck"), a specific driver (by name, code, or "the driver"), a vendor, or the fleet as a whole. For pronouns and implicit references, the LLM resolves from conversation context. If the operator is on truck 19's dashboard page and says "what's going on here," the entity is truck 19.

Time scope: what date range applies. Explicit ("last quarter," "in 2025," "since June") or implicit from context ("what about the month before" means the month before the previously-discussed time window). Default depends on question type: maintenance questions default to all-time, compliance questions default to current status, financial comparisons default to the most recent complete period.

Intent classification: what type of answer the operator wants.
- entity_overview: broad question about an entity ("tell me about truck 19")
- specific_metric: a particular number or fact ("how much did maintenance cost")
- document_retrieval: wants to see a specific document ("show me the invoice," "pull up the tax form")
- comparison: wants entities compared ("which truck costs more," "compare truck 19 and 22")
- compliance_check: wants to know if something is current/valid ("is the insurance up to date")
- explanation: wants to understand WHY something is the case ("why is truck 19 so expensive")
- trend_analysis: wants to see how something changed over time ("is maintenance going up")
- relationship_query: wants to explore connections ("which trucks go to Jim's shop," "who has driven truck 19")
- history_recall: references a past conversation ("what did we talk about last time," "the brake issue from Tuesday")
- action_request: wants the system to do something ("flag truck 19," "mark this as investigated")
- greeting: casual greeting or small talk ("good morning," "hey")

Sub-agent dispatch plan: which sub-agent functions should be called, with what parameters. The LLM outputs a list of function names and their arguments. For an entity_overview of truck 19, the dispatch plan is: get_truck_identity(19), get_truck_assignment(19), get_truck_maintenance(19), get_truck_compliance(19), get_truck_financials(19). For a specific_metric about maintenance cost, the dispatch plan is just: get_truck_maintenance(19, time_range={start, end}). For a history_recall, the dispatch plan is: get_memory_search("brake issue").

Response guidance: any special instructions for synthesis. For example, if the intent is explanation, the synthesis should explain causes not just state numbers. If the intent is compliance_check, the synthesis should lead with the yes/no answer before providing details. If the operator profile says they prefer concise responses, note that.

**Structured output format:**

The LLM is prompted to return JSON with fields: entities (list of {type, identifier, resolved_name}), time_scope ({start_date, end_date, scope_description}), intent (string from the enum above), dispatch_plan (list of {function, params}), response_guidance (string), confidence (float — how confident the LLM is in its interpretation).

If confidence is below 0.6, the agent should ask a clarifying question instead of dispatching sub-agents. "Are you asking about truck 19's maintenance or its overall costs?" This avoids answering the wrong question.

### Sub-Agent Dispatch (No LLM)

The orchestrator takes the dispatch plan from LLM Call 1 and executes it.

All sub-agent functions in the dispatch plan run in parallel using asyncio.gather. Each function is the same Python function from Phase 3 — get_truck_maintenance, get_truck_compliance, etc. They query Postgres and Neo4j and return structured dicts.

The orchestrator collects all results. If any sub-agent returns an error or empty result (truck not found, no maintenance data), this information is passed to LLM Call 2 so the response can acknowledge the gap rather than hallucinating.

For history_recall intent: get_memory_search runs against the conversations table. If matching conversations are found, the orchestrator also checks if any relevant new documents have been ingested since that conversation (by comparing the conversation's ended_at timestamp against documents.created_at for the same entity). This enables "any update on the brake thing?" to not just recall the conversation but also report what's changed since.

### LLM Call 2: Response Synthesis

Takes the sub-agent results and generates the natural language response.

**Inputs to the LLM:**
- The operator's original message
- The intent classification and entity resolution from Call 1
- All sub-agent results as structured data
- The response guidance from Call 1
- The operator profile (preferred style: concise vs detailed, numbers vs narrative)
- Instructions for grounding: every factual claim must be traceable to a sub-agent result. The LLM must not invent numbers, dates, or facts not present in the sub-agent data. If the data doesn't contain an answer, say so.

**What the LLM generates:**

A natural language response that:
- Leads with the most important information (urgent compliance issues before routine stats, the direct answer before supporting context)
- References specific documents when relevant ("according to invoice CSS-660142 from October 2025")
- Includes clickable entity references formatted as markdown links: [truck 19](/trucks/19), [Diesel Emissions Co](/vendors/abc123) — the frontend renders these as navigation links
- Adapts length and detail to the intent: greeting gets a short response, entity_overview gets a comprehensive one, specific_metric gets a focused answer
- For explanation intents: provides reasoning ("truck 19's maintenance is 40% above fleet average, driven primarily by a $25,700 engine overhaul at Cummins in July 2025 — without that single event, regular maintenance is actually 15% below average")
- For comparison intents: uses structured format (natural language comparison with key differentiators, not a raw data dump)

**Streaming:** The synthesis response is streamed token-by-token through the WebSocket as Gemini generates it. The frontend renders tokens as they arrive, giving the operator immediate feedback. The WebSocket message format: {type: "chat_response", conversation_id: "uuid", content: "token_text", streaming: true, done: false}. When generation completes: {type: "chat_response", conversation_id: "uuid", content: "", streaming: false, done: true, tools_used: [{function: "get_truck_maintenance", params: {truck_id: 19}}]}.

---

## LangGraph State Machine

The agent is implemented as a LangGraph state graph with the following nodes and edges.

### State Schema

The LangGraph state object carried through every node:

- message: the operator's current message (string)
- conversation_id: UUID
- conversation_context: the last N turns loaded from Redis
- operator_profile: loaded from Postgres at session start
- dashboard_context: which page/entity the operator is currently viewing
- query_understanding: output of LLM Call 1 (entities, time_scope, intent, dispatch_plan, confidence)
- sub_agent_results: dict of function_name → result dict
- response: the generated response text
- turn_state_update: changes to make to the turn-level state after this turn completes

### Nodes

**load_context** — Entry node. Loads conversation context from Redis (turn-level state) and operator profile from Postgres. If this is the first message of a new conversation, creates a new conversation record in Postgres and initializes empty turn-level state in Redis.

**understand_query** — Executes LLM Call 1. Populates query_understanding in the state. If confidence is below 0.6, routes to clarify instead of dispatch.

**clarify** — Generates a clarifying question without calling sub-agents. Streams the clarification through WebSocket. Saves the turn to conversation history. Exits the graph.

**dispatch_agents** — Reads the dispatch_plan from query_understanding. Executes all listed sub-agent functions in parallel with asyncio.gather. Populates sub_agent_results in the state.

**synthesize_response** — Executes LLM Call 2. Generates and streams the response. Populates response in the state.

**update_state** — Terminal node. Updates turn-level state in Redis: sets current_entity to whatever entity this turn was about, sets current_time_window to whatever time scope was used, sets current_intent to the classified intent, appends this turn (message + abbreviated results + response) to turn_history. If turn_history exceeds 20 turns, truncate the oldest to keep context manageable.

### Edges

load_context → understand_query (always)

understand_query → clarify (if confidence < 0.6)

understand_query → dispatch_agents (if confidence >= 0.6)

clarify → update_state (always)

dispatch_agents → synthesize_response (always)

synthesize_response → update_state (always)

### Error Handling in the Graph

If understand_query fails (LLM API error, timeout): retry once. If it fails again, return a generic error message: "I'm having trouble understanding that right now. Could you try rephrasing?" Do not expose the technical error to the operator.

If a sub-agent function fails (database error, Neo4j connection issue): include the failure in sub_agent_results so the synthesis can acknowledge it: "I couldn't retrieve the maintenance data right now, but here's what I know from the other sources..."

If synthesize_response fails: return the raw sub-agent data formatted as a simple summary rather than generating nothing. A table of facts is better than no response.

---

## Memory System

### Layer 1: Turn-Level Context (Redis)

Stored in Redis with key: session:{conversation_id}. TTL: 24 hours of inactivity.

**Contents:**
- current_entity: {type: "truck", id: UUID, unit_number: 19, display_name: "Truck 19 — 2016 International ProStar"} — the entity the conversation is currently focused on. Updated after every turn that references an entity.
- current_time_window: {start_date: "2026-01-01", end_date: "2026-03-31", description: "Q1 2026"} — the time scope the conversation is currently using. Updated when the operator establishes or shifts a time reference.
- current_intent: "maintenance_cost" — the type of question from the last turn. Used to carry intent forward: "what about truck 22" inherits the maintenance_cost intent from the prior turn.
- turn_history: list of the last 10 turns, each containing: {role: "user"/"assistant", content: "message text", entities_referenced: [...], sub_agents_called: [...], key_results: {...abbreviated results...}}. This is what gets passed to LLM Call 1 as conversation context.

**How context resolution works:**

When the operator says "what about truck 22" — LLM Call 1 receives the turn_history showing the prior turn was about truck 19 maintenance. The LLM understands "what about" means "same question, different entity." It outputs: entity = truck 22, intent = maintenance_cost (carried from prior turn), time_scope = same as prior turn.

When the operator says "show me the most expensive one" — LLM Call 1 receives the turn_history showing the prior turn returned a list of maintenance events for truck 19. "The most expensive one" refers to the maintenance event with the highest cost in the prior results. The LLM outputs: intent = document_retrieval, entity = the specific maintenance event (identified from prior results), dispatch plan = get the source document for that event.

When the operator says "what about last month" — LLM Call 1 sees the current_time_window is Q1 2026. "Last month" relative to the conversation context means the month before, or possibly the prior period. The LLM resolves this and shifts the time_scope.

### Layer 2: Conversation History (Postgres)

Stored in the conversations and conversation_messages tables (created in Phase 1).

**When a conversation ends** (the operator closes the chat sidebar, navigates away, or is inactive for 30 minutes), the system:

1. Writes all messages to conversation_messages if not already written (messages are written during the conversation as they occur, so this is a verification step).

2. Generates a structured conversation summary using an LLM call. This is an async background task — it does not block the operator. The LLM receives the full conversation transcript and outputs:
   - entities_discussed: list of {type, id, name} — every entity mentioned during the conversation
   - topics: list of topic strings — what was discussed (maintenance_costs, compliance_status, vendor_comparison)
   - key_findings: list of finding strings — the important facts or insights that emerged ("truck 19 had a $25,700 engine overhaul that accounts for 70% of its maintenance cost," "truck 22 has the highest total cost of ownership at $78,400")
   - unresolved_items: list of {description, entity_type, entity_id, follow_up_date} — anything the operator said to keep an eye on, follow up on, or revisit. Detected from phrases like "let's keep an eye on this," "remind me about this," "I'll deal with this later," "that's concerning, flag it."

3. Stores the summary in the conversations record: entities_discussed, topics, key_findings, unresolved_items, summary_text, ended_at.

**Cross-session memory retrieval:**

When the operator starts a new conversation, recent conversation summaries (last 5 conversations) are loaded alongside the operator profile. This gives the LLM awareness of what was recently discussed without loading full transcripts.

When the operator references a past conversation ("what did we discuss about brakes," "the truck issue from last week," "any updates"), the get_memory_search sub-agent searches the conversations table:
- Keyword search: against entities_discussed, topics, and key_findings JSONB fields
- Temporal search: if the operator says "last week," filter by ended_at within the last 7 days
- Semantic search: if conversation summaries are embedded in pgvector, do vector similarity search on the query

The search returns matching conversation summaries. The orchestrator then checks: have any new documents been ingested for the entities discussed in that conversation since the conversation ended? This is a Postgres query: SELECT from documents WHERE truck_id IN (entities from conversation) AND created_at > conversation.ended_at. If new documents exist, the orchestrator fetches their details so the response can include "Since we discussed truck 19's brakes on Tuesday, a new service invoice came in yesterday — another brake job at Jim's for $800."

### Layer 3: Operator Profile (Postgres)

Stored in the operator_profiles table (created in Phase 1).

**How the profile is built and updated:**

After each conversation ends, the system updates the operator profile:
- frequent_entities: increment counts for every entity discussed in this conversation. The profile stores a ranked list (e.g., [{type: "truck", id: X, name: "Truck 19", count: 12}, ...]) showing which entities the operator asks about most.
- frequent_topics: increment counts for each topic from the conversation summary.
- total_conversations: increment by 1.
- last_active: set to now.
- preferred_response_style: inferred over time from operator behavior. If the operator frequently asks follow-up questions for more detail, the style leans "detailed." If the operator rarely asks follow-ups and tends to move on after the first answer, the style leans "concise." If the operator frequently asks for comparisons and rankings, note "comparative." This inference is done periodically (every 10 conversations) by an LLM analyzing the pattern of conversation transcripts, not on every turn.

**How the profile is used:**

Loaded once at the start of each conversation session. Passed to both LLM Call 1 (helps understand what the operator likely means by ambiguous queries — if they always ask about maintenance costs, "how's truck 19" probably means maintenance) and LLM Call 2 (adapts response length and style to operator preference).

---

## Dashboard Context Integration

The chat agent knows what the operator is currently viewing on the dashboard. This context is sent as part of the WebSocket chat message.

When the operator sends a chat message, the frontend includes: {type: "chat_message", conversation_id: "uuid", content: "message text", dashboard_context: {current_page: "/trucks/19", current_entity: {type: "truck", id: "uuid", unit: 19}, visible_panels: ["identity", "maintenance", "compliance"]}}.

This enables several interaction patterns:

**Implicit entity resolution:** On truck 19's detail page, "what's going on here" or "anything I should worry about" resolves to truck 19 without the operator naming it.

**Context-aware responses:** If the operator is viewing the compliance matrix and asks "what's the most urgent thing," the agent prioritizes compliance items over maintenance or financial information because that's the context the operator is in.

**Dashboard-to-chat handoff:** The operator sees a red cell on the compliance matrix, clicks it, and the chat pre-populates with "Tell me about truck 22's insurance" (or the operator types a more specific question). The chat agent has the compliance matrix context and can go deeper.

**Chat-to-dashboard suggestions:** When the agent's response references a specific truck or entity, the response includes navigation links: "You might want to check [truck 22's maintenance history](/trucks/22)." The operator can click the link and the dashboard navigates to that page while the chat stays open.

---

## Conversation Lifecycle

### Starting a Conversation

The operator opens the chat sidebar (or it's already open). The frontend sends: {type: "chat_start", operator_name: "default" (MVP has no auth)}. The backend creates a conversation record in Postgres, initializes turn-level state in Redis, loads the operator profile and last 5 conversation summaries, and returns: {type: "chat_started", conversation_id: "uuid"}.

### During a Conversation

Each message goes through the LangGraph state machine. Messages are written to conversation_messages as they occur (both user messages and assistant responses). Turn-level state is updated in Redis after each turn.

### Ending a Conversation

Triggered when: the operator closes the chat sidebar, navigates away from the app (WebSocket disconnects), or is inactive for 30 minutes (timeout detected by a background heartbeat check).

On end: turn-level state in Redis gets a 24-hour TTL (not deleted immediately — allows the operator to reopen and resume within 24 hours). The conversation summary is generated asynchronously. The operator profile is updated.

### Resuming a Conversation

If the operator closes and reopens the chat within 24 hours, the turn-level state is still in Redis. The conversation continues with full context. The frontend loads the conversation_messages from Postgres and renders the prior turns.

If more than 24 hours have passed, the turn-level state has expired. A new conversation starts, but the prior conversation exists in the history and is searchable via get_memory_search.

---

## Contextual Chat Suggestions

The chat sidebar shows contextual suggestion chips above the input field. These suggestions change based on the operator's current dashboard page and the data on screen.

**On fleet overview page:**
- "How's the fleet doing?"
- "Any compliance issues this week?"
- "Which truck costs the most?"

**On truck detail page (truck 19):**
- "Why is maintenance so high?"
- "Is everything up to date?"
- "Compare with other trucks"

**On compliance matrix page:**
- "What's the most urgent item?"
- "Which trucks need attention?"

**On financial analytics page:**
- "Which truck has the highest cost per mile?"
- "How has spending changed this quarter?"

Suggestions are generated statically based on the page route (not LLM-generated). They are quick-action shortcuts, not comprehensive — the operator can always type a free-form question.

When the operator clicks a suggestion chip, it's sent as a regular chat message. The agent processes it like any other message.

---

## Handling Edge Cases

**Ambiguous entity:** The operator says "how's the truck" without specifying which one. If the turn-level state has a current_entity, use it. If not, and the operator is on a truck detail page, use that truck. If neither, the LLM should ask: "Which truck are you asking about?"

**No data available:** The operator asks about a truck that has no maintenance events. The sub-agent returns an empty list. The synthesis should say "Truck 19 has no maintenance events on record. This could mean no service invoices have been uploaded, or the truck hasn't needed service yet." Not a hallucinated answer.

**Contradictory information:** The operator says "truck 19's insurance expired" but the data shows it's valid until December. The agent should gently correct: "Actually, truck 19's insurance under policy GWCA-KS-77 04188 is current through December 31, 2026. Is there a specific concern?"

**Multi-entity questions:** "Compare trucks 19, 22, and 84" — the dispatch plan includes get_truck_financials for each truck, all running in parallel. The synthesis compares them side by side.

**Temporal references without explicit dates:** "Recently" defaults to the last 30 days. "A while ago" defaults to the last 6 months. "When we first got it" resolves to the truck's acquired_date from the truck record. These defaults are encoded in the query understanding prompt.

**Questions the system can't answer:** "What will maintenance cost next quarter?" — the system has historical data but doesn't do forecasting (Phase 6 might add trend projections, but Phase 5 doesn't). The agent should say "I can show you the spending trend over the last year, but I don't have forecasting capability yet. Based on the trend, average monthly maintenance has been $X."

**Operator frustration or repeated questions:** If the operator asks the same question twice (perhaps because the first answer wasn't satisfactory), the LLM should recognize this from turn_history and provide a different angle or more detail rather than repeating the same answer.

---

## Grounding and Hallucination Prevention

Every factual claim in the response must trace to a sub-agent result. The synthesis prompt explicitly instructs:

Do not mention any truck, dollar amount, date, vendor, or event that is not present in the sub-agent results. If the results do not contain information needed to answer the question, say "I don't have that information" rather than guessing. When stating a number, include the time period and source ("total maintenance spend of $36,360 across 6 service events"). When referencing a document, include the document number or a description that the operator can verify ("invoice CSS-660142 from Diesel Emissions Co").

The tools_used field in the chat response message tells the operator (and the system) exactly which sub-agents were invoked and what data they returned. This creates an audit trail for every response.

---

## Phase 5 Acceptance Criteria

1. Sending "tell me about truck 19" through the chat returns an accurate overview covering: identity (2016 International ProStar), current driver (Sergei Volkov, D03), maintenance summary (correct total spend and event count), compliance status (insurance, registration, CDL expiry), and financial summary (total cost of ownership). All numbers match the sub-agent API responses from Phase 3.

2. Follow-up context works: after discussing truck 19, sending "what about truck 22" returns the same type of overview for truck 22 without the operator re-specifying "maintenance" or "overview."

3. Time reference resolution works: "how much did maintenance cost last quarter" returns the correct filtered total. "What about the quarter before that" shifts the time window correctly.

4. Implicit entity resolution works: while on truck 19's dashboard page, sending "anything I should worry about here" resolves to truck 19 and checks compliance and anomaly status.

5. Document retrieval works: "show me the invoice for that engine overhaul" identifies the correct maintenance event from context and returns the source document reference with a viewable link.

6. Comparison works: "compare trucks 19 and 22" dispatches financial sub-agents for both trucks in parallel and returns a comparative analysis.

7. Relationship queries work: "which trucks go to Jim's Truck Repair" dispatches the Neo4j graph query and returns the connected trucks.

8. Responses stream through WebSocket: tokens appear in the chat as they're generated, not all at once after completion.

9. Conversation memory persists across sessions: after discussing truck 19's brakes, closing the chat, then reopening and asking "what did we talk about last time" returns a summary of the prior conversation with the brake discussion.

10. When a new document is ingested between conversations for an entity that was discussed, "any updates on truck 19" surfaces the new document: "Since our last conversation about truck 19, a new service invoice was processed — brake repair at Jim's for $800."

11. Unresolved items are tracked: if the operator says "let's keep an eye on truck 19's brakes," this appears in the conversation summary's unresolved_items. A future question "anything I was tracking" surfaces these items.

12. The agent never fabricates data. If asked about a truck that doesn't exist (unit 99), the response says "I don't have a truck with unit number 99 in the system" rather than inventing information.

13. Clarification works: a vague question like "what's the thing" (no context, no entity) triggers a clarifying question rather than a wrong answer.

14. Contextual suggestion chips appear above the chat input, changing based on the current dashboard page.

15. Operator profile updates after conversations: frequent_entities and frequent_topics reflect the entities and topics discussed.

---

## What Phase 5 Does NOT Build

- No anomaly detection or proactive intelligence (Phase 6 — the agent can report anomalies if they exist in the anomalies table, but Phase 5 does not populate that table)
- No statistical baseline computation (Phase 6)
- No background processes checking unresolved items against new data (Phase 6 — the check happens reactively when the operator asks, not proactively)
- No forecasting or predictive analytics (future scope)
- No action execution beyond flagging (the agent can't update truck status, reassign drivers, or modify data — it's read-only plus flagging)

---

## Dependencies for Phase 6

Phase 6 (Intelligence Layer) requires the conversation system from Phase 5 to be operational so that: unresolved items from conversations can be checked by background processes, the anomaly feed populated by Phase 6 can be discussed in the chat, and operator feedback on anomalies (dismiss with reason) can feed the learning loops. Phase 6 also requires the operator profile infrastructure to support the query understanding learning loop.
