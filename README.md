# Graph-Based Data Modeling and Query System

> **Forward-Deployed Engineer Take-Home Task — Dodge AI**
> SAP Order-to-Cash (O2C) context graph with LLM-powered natural language queries, dynamic SQL generation, streaming responses, node highlighting, and interactive visualization.

---

## Live Demo

🔗 **[https://vdcyw7yuosfys99hmyfprsrtbuygxmg5.runable.site](https://vdcyw7yuosfys99hmyfprsrtbuygxmg5.runable.site)**

Full dataset: 21,393 rows · 19 entity types · 4,164 graph edges · 633 unique nodes.

**Try these queries:**
```
Show me the full journey for sales order 740509
Which customer has the highest net value order?
All orders containing product S8907367010814
Which products have the highest number of billing documents?
Find all data quality and broken flow issues
Summarise this dataset
How many cancelled billing documents are there?
Average order value per customer
Trace the full flow of billing document 90504274
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    React + Vite Frontend                          │
│  GraphView (Cytoscape.js)        ChatPanel (SSE streaming)        │
│  · 633 nodes, 4164 edges          · NL answer word-by-word        │
│  · click → floating tooltip       · SQL shown in plan badge       │
│  · highlight + dim on query       · multi-query result tables     │
│  · 4 graph view presets           · conversation memory           │
└────────────────────────┬─────────────────────────────────────────┘
                         │  HTTP / Server-Sent Events
┌────────────────────────▼─────────────────────────────────────────┐
│                  FastAPI Backend (Python)                         │
│  GET  /api/graph/overview?max_edges=N&node_types=X               │
│  GET  /api/graph/stats                                           │
│  POST /api/query/stream   ← main endpoint (SSE)                  │
└──────────────┬────────────────────────────────────────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
rule_planner.py      engine.py
3 structural         Dynamic SQL
patterns             ├─ schema RAG (all 19 tables)
(trace/top/broken)   ├─ LLM → SQL JSON
no LLM needed        ├─ safe execute
                     └─ LLM answers from rows
                              │
                         SQLite (data/app.db)
                         19 tables, 21,393 rows
```

### Two-Path Query Engine

**Path A — Structural (zero LLM calls):**
Rule-based regex detects the 3 task-required query types and routes to dedicated handlers:
- `trace_flow` — multi-hop graph traversal across the O2C pipeline
- `top_products_by_billing` — aggregation by billing count/amount/quantity
- `find_broken_flows` — 7 gap-analysis checks (missing links, mismatches, blocked partners)

**Path B — Dynamic SQL (everything else):**
```
User question
    → LLM receives full 19-table schema as RAG context
    → LLM outputs: {"queries":[{"purpose":"...","sql":"SELECT ..."}]}
    → Execute safely (read-only, 100-row cap)
    → Second LLM call writes grounded answer from actual rows
    → Stream word-by-word via SSE
```

### Model Cascade (Rate Limit Elimination)
Each Gemini/Gemma model family has its own independent rate-limit pool. The engine tries each in order, skipping 429s:
```
gemini-2.5-flash-lite → gemini-2.0-flash-lite → gemma-3-27b-it → gemma-3-4b-it → gemini-2.0-flash
```
In practice, with 3 independent pools, rate limit errors reaching users are eliminated.

---

## Project Structure

```
backend/
  app/
    api/
      graph.py          GET /graph/overview (with node_types filter), /graph/stats
      query.py          POST /query/stream — SSE path router
      health.py
      router.py
    db/
      models.py         13 SQLAlchemy ORM models + GraphEdge
      session.py        SQLite engine, init_db()
      base.py
    ingestion/
      cli.py            python -m app.ingestion.cli <path> --build-edges
      ingest_jsonl.py   19 JSONL entity types → upsert with canonicalization
      graph_builder.py  10 SQL queries → 4,164 graph edges
    llm/
      engine.py         ★ Dynamic SQL engine — schema RAG, cascade, execute, answer
      rule_planner.py   ★ Rule-based structural query detection (120 lines)
    query/
      plans.py          Pydantic plan models (strict validation)
      validation.py     Schema validation layer
      handlers.py       trace_flow / top_products / find_broken_flows SQL
      execute.py        Intent router

frontend/src/
  App.jsx               Root: graph state, view selector, overview fetch
  components/
    GraphView.jsx       Cytoscape, node tooltip, highlighting, edge toggle, view selector
    ChatPanel.jsx       SSE consumer, streaming chat, SQL result tables

ai-coding-logs/
  AI_SESSION_LINKS.md   Links to all 4 AI tool sessions
  cursor_graph_based_data_modeling_platform.md  Cursor session transcript
ai-coding-logs.zip      Zip of above for submission
```

---

## Local Setup

### Prerequisites
- Python 3.11+, Node.js 18+
- Free API key: [Google Gemini](https://ai.google.dev) (recommended) — `gemini-2.5-flash-lite`

### 1 — Install
```bash
git clone https://github.com/sreeganeshvemuri-byte/Graph-Based-Data-Modeling-and-Query-System.git
cd Graph-Based-Data-Modeling-and-Query-System

python -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" sqlalchemy pydantic python-dotenv
```

### 2 — Configure
```bash
cp backend/.env.example backend/.env
# Edit backend/.env:
GEMINI_API_KEY=AIzaSy...
```

### 3 — Ingest dataset
```bash
cd backend
PYTHONPATH=. python -m app.ingestion.cli \
  ../sap-order-to-cash-dataset/sap-o2c-data \
  --build-edges
# → data/app.db: 21,393 rows, 4,164 edges (~10 seconds)
```

### 4 — Run
```bash
# Terminal 1
PYTHONPATH=. uvicorn app.main:app --port 8000 --reload

# Terminal 2
cd ../frontend && npm install && npm run dev
# Open http://localhost:5173
```

---

## Architecture Decisions

### Why SQLite + graph_edges adjacency list (not Neo4j)?
Dataset is ~21K rows. SQLite with indexed joins handles all multi-hop traversals efficiently at this scale. Adding a graph DB would be operational overhead with no performance benefit. The `graph_edges` table (composite PK prevents duplicates) serves as a fast adjacency list.

### LLM Prompting Strategy

**Two-call pattern for dynamic queries:**

1. **Plan call** (temp=0): LLM receives the full 19-table schema as context. Outputs structured JSON:
   ```json
   {"queries": [{"id":"q1","purpose":"top customer by value","sql":"SELECT..."}]}
   ```
   Deterministic, schema-grounded, never invents column names.

2. **Answer call** (temp=0.3): LLM receives actual database rows. Writes a grounded 2–5 sentence answer. Cannot hallucinate — answer is bounded by what rows contain.

**Rule-based fast path (~60% of queries, 0 LLM calls):** The 3 task-evaluated query types are detected by regex and routed to dedicated handlers. Fast, reliable, always correct.

**Conversation memory:** Last 6 turns sent with every request. `_resolve_entity_from_history()` resolves pronouns ("tell me about that billing doc") by scanning history for the contextually relevant entity ID.

### Guardrails

Layer 1 — Before any LLM call:
- Mutation verbs blocked: `delete/drop/remove/truncate/update/alter/create`
- General knowledge patterns: "capital of", "write a poem", "recipe for"
- Domain check: no O2C keywords + no entity IDs → rejected

Layer 2 — SQL execution:
- Regex blocks all write keywords before execution
- 100-row cap, 30-second timeout

Layer 3 — LLM prompt:
- "If question is out of scope: output OUT_OF_SCOPE"

### Streaming (SSE)
`POST /api/query/stream` emits 4 event types:
```
{"type":"plan",   "payload":{...}}   ← immediately after query classification
{"type":"result", "payload":{...}}   ← after DB execution
{"type":"token",  "payload":"word "} ← NL answer, word by word
{"type":"done",   "payload":null}
```
Frontend reads via `ReadableStream`. Graph updates and NL answer stream simultaneously.

---

## Graph Visualization

**Node types (8) with distinct colors:**
sales_order (#6366f1) · delivery (#0891b2) · billing_document (#dc2626) · accounting_document (#d97706) · customer (#2563eb) · payment (#16a34a) · product (#0d9488) · plant (#9333ea)

**Interactions:**
- Click node → floating metadata tooltip (type badge, entity ID, all fields)
- After query → matched nodes glow gold, others dim to 10%, camera animates to fit
- ↩ Overview button — resets to full graph (only visible after a query)
- ⌇ Edges toggle — show/hide all edges
- Graph view selector: Core Flow (800) / Orders & Delivery / Billing & Payments / Full Graph (all 4,164 edges)

**Layout:** `breadthfirst` for query results (layered top→bottom, follows O2C pipeline direction), `cose` force-directed for full overview.

---

## Dataset

| Entity | Table | Rows |
|--------|-------|------|
| Sales Order Headers | sales_order_headers | 100 |
| Sales Order Items | sales_order_items | 166 |
| Schedule Lines | sales_order_schedule_lines | 200 |
| Delivery Headers | outbound_delivery_headers | 86 |
| Delivery Items | outbound_delivery_items | 142 |
| Billing Doc Headers | billing_document_headers | 163 |
| Billing Doc Items | billing_document_items | 329 |
| Cancellations | billing_document_cancellations | 80 |
| Journal Entry Items | journal_entry_items_ar | 409 |
| Payments | payments_accounts_receivable | 120 |
| Business Partners | business_partners | 183 |
| Addresses | business_partner_addresses | 183 |
| Customer Company Assignments | customer_company_assignments | 183 |
| Customer Sales Area Assignments | customer_sales_area_assignments | 557 |
| Products | products | 521 |
| Product Descriptions | product_descriptions | 996 |
| Product Plants | product_plants | 3,532 |
| Product Storage Locations | product_storage_locations | 13,356 |
| Plants | plants | 87 |
| **Total** | | **~21,393** |

**Graph edges: 4,164 across 10 relationship types**

---

## AI Tools Used

| Tool | Purpose | Session |
|------|---------|---------|
| Runable | Final integration, UI redesign, query engine, deployment | [Session](https://runable.com/chat/0c4de663-5340-4c38-8404-3ecb657426c0) |
| Claude Code | Backend logic, query engine, validation | [Session](https://claude.ai/share/f237c3ed-0be4-4ad0-b25f-456a04b9ab43) |
| ChatGPT | Planning, architecture, O2C domain analysis | [Session](https://chatgpt.com/share/69c56e9c-a608-8324-8077-c8bebe6ff36a) |
| Cursor | Initial full-stack implementation | `ai-coding-logs/cursor_graph_based_data_modeling_platform.md` |

Full session logs: [`ai-coding-logs/`](./ai-coding-logs/) · [`ai-coding-logs.zip`](./ai-coding-logs.zip)

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini key (ai.google.dev) | — |
| `GROQ_API_KEY` | Groq key (console.groq.com) — optional backup | — |
| `GEMINI_MODEL` | Pin a specific model | cascade auto-selects |
| `APP_DB_PATH` | Custom SQLite path | `<repo>/data/app.db` |
