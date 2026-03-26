# Graph-Based Data Modeling and Query System

> **Forward-Deployed Engineer Take-Home Task — Dodge AI**
> SAP Order-to-Cash context graph with LLM-powered natural language queries, dynamic SQL generation, streaming responses, and interactive visualization.

---

## Live Demo

🔗 **[https://vdcyw7yuosfys99hmyfprsrtbuygxmg5.runable.site](https://vdcyw7yuosfys99hmyfprsrtbuygxmg5.runable.site)**

Full dataset loaded: 21,393 rows · 19 entity types · 4,164 graph edges · 466 visual nodes.

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
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     React + Vite Frontend                        │
│  ┌──────────────────────────┐  ┌─────────────────────────────┐  │
│  │      GraphView.jsx        │  │       ChatPanel.jsx          │  │
│  │  Cytoscape.js dot graph   │  │  SSE stream consumer         │  │
│  │  node tooltip on click    │  │  streaming NL answer         │  │
│  │  highlight + dim + zoom   │  │  SQL result tables           │  │
│  └──────────────────────────┘  └─────────────────────────────┘  │
│                     App.jsx (state, graph data)                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │  HTTP / Server-Sent Events
┌───────────────────────────▼─────────────────────────────────────┐
│                    FastAPI Backend (port 8000)                    │
│  GET  /api/graph/overview  — full graph JSON                     │
│  GET  /api/graph/stats     — node/edge counts                    │
│  POST /api/query/stream    — SSE: plan → result → tokens → done  │
└──────────────┬──────────────────────────┬────────────────────────┘
               │                          │
        rule_planner.py             engine.py
        3 structural patterns       Dynamic SQL generation
        (trace/top/broken)          Full schema as RAG context
               │                    LLM → SQL → Execute → LLM answer
               ▼                          │
        handlers.py              SQLite (data/app.db)
        Dedicated SQL            19 tables, 21K rows
        for each type            + graph_edges
```

### Two-Path Query Engine

**Path A — Structural (rule-based, no SQL gen needed):**
Handles the 3 task-required query types detected by pattern matching:
- `trace_flow` — multi-hop graph traversal
- `top_products_by_billing` — aggregation query
- `find_broken_flows` — 7 gap-analysis checks

**Path B — Dynamic SQL (everything else):**
```
User question
    ↓
LLM reads full 19-table schema (RAG context)
    ↓ 
LLM outputs {queries: [{purpose, sql}]} JSON — 1-3 queries
    ↓
Execute safely (read-only, 100-row cap)
    ↓
LLM writes grounded NL answer from actual rows
    ↓
Stream word-by-word to user
```

---

## Project Structure

```
backend/
  app/
    api/
      graph.py          GET /graph/overview, /graph/stats
      query.py          POST /query/stream (SSE) — path router
      health.py
      router.py
    db/
      models.py         13 SQLAlchemy ORM models + GraphEdge
      session.py        SQLite engine, init_db(), get_db()
      base.py
    ingestion/
      cli.py            python -m app.ingestion.cli <path> --build-edges
      ingest_jsonl.py   Parses 19 JSONL entity types, upserts rows
      graph_builder.py  Builds graph_edges from relational tables
    llm/
      engine.py         ★ Dynamic SQL engine — schema RAG, plan, execute, answer
      rule_planner.py   ★ Rule-based detection for 3 structural query types
    query/
      plans.py          Pydantic models for structural plan types
      validation.py     Schema validation layer
      handlers.py       SQL execution for trace/top/broken
      execute.py        Intent router

frontend/src/
  App.jsx               Root: graph state, overview fetch on mount
  components/
    GraphView.jsx       Cytoscape graph, tooltip, highlighting, edge toggle
    ChatPanel.jsx       SSE consumer, streaming chat, SQL result tables
```

---

## Local Setup

### Prerequisites
- Python 3.11+, Node.js 18+
- Free API key: [Google Gemini](https://ai.google.dev) (recommended) or [Groq](https://console.groq.com)

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
# Edit backend/.env and add:
GEMINI_API_KEY=AIzaSy...    # gemini-2.5-flash-lite — free, 30 RPM
```

### 3 — Ingest dataset

```bash
cd backend
PYTHONPATH=. python -m app.ingestion.cli \
  ../sap-order-to-cash-dataset/sap-o2c-data \
  --build-edges
# Creates data/app.db — ~21,393 rows, 4,164 graph edges
```

### 4 — Run

```bash
# Terminal 1 — backend
PYTHONPATH=. uvicorn app.main:app --port 8000 --reload

# Terminal 2 — frontend
cd ../frontend && npm install && npm run dev
# Open http://localhost:5173
```

---

## Architecture Decisions

### Why SQLite + graph_edges table (not a graph DB)?

The dataset is small (~21K rows). SQLite with indexed joins performs well at this scale. A graph DB (Neo4j, ArangoDB) would add operational complexity for negligible benefit. The `graph_edges` adjacency list handles all traversal queries efficiently.

```sql
-- Multi-hop traversal: sales order → delivery → billing → journal
SELECT * FROM graph_edges WHERE source_type='sales_order' AND source_id='740509'
-- Then follow target_id through each hop
```

### LLM Prompting Strategy

**Two-call architecture per dynamic query:**

1. **Plan call** — LLM receives the full schema (all 19 tables, columns, join paths) as RAG context and outputs a JSON array of SQL queries to run:
```json
{"queries": [{"id":"q1","purpose":"orders by customer","sql":"SELECT..."}]}
```
Temperature = 0 for deterministic SQL.

2. **Answer call** — LLM receives the actual database rows and writes a grounded NL answer. Temperature = 0.3 for natural prose. The answer can only reference what's in the rows — no hallucination.

**Why two calls instead of one?** SQL generation requires determinism (temp=0) and schema awareness. Answer generation requires natural language fluency (temp=0.3) and result awareness. Separating them gives better output from both.

**Rule-based fast path:** The 3 task-required query types (trace_flow, top_products, broken_flows) are detected by regex and routed to dedicated handlers — no LLM call needed, always reliable, handles the exact evaluation criteria.

### Guardrails

- **Mutation verbs** blocked before any LLM call: `delete/drop/remove/truncate/update/alter/create`
- **General knowledge** blocked by pattern: "capital of", "weather in", "write a poem", etc.
- **Domain signal check**: queries with no O2C keywords and no entity IDs are rejected
- **SQL execution**: read-only enforced by regex blocking all write keywords before execute
- **Row cap**: 100 rows maximum per query, prevents runaway queries

### Model Choice

`gemini-2.5-flash-lite` — confirmed working, highest free-tier RPM (~30/min), fast response time. The planner and answer generator share the same model, with graceful fallback to deterministic text when rate-limited.

### Streaming (SSE)

`POST /api/query/stream` emits 4 event types:
```
data: {"type": "plan",   "payload": {intent/sql, ...}}   — immediately
data: {"type": "result", "payload": {rows/path, ...}}    — after DB query
data: {"type": "token",  "payload": "word "}             — NL answer tokens
data: {"type": "done",   "payload": null}
```

Frontend reads via `ReadableStream` — users see the NL answer appearing word-by-word while the graph updates simultaneously.

### Conversation Memory

Every request includes `history: [{role, content}]` for the last 6 turns (3 exchanges).

- **SQL generation**: history injected into LLM context for follow-up questions ("give me orders with this product" → LLM knows which product from history)
- **Pronoun resolution**: `_resolve_entity_from_history()` extracts entity IDs from history for vague references ("trace its flow", "tell me about that billing doc")
- **NL answers**: history context included so answers can say "as mentioned earlier..."

---

## Graph Visualization

**Nodes:** Small colored dots (10px). No labels by default — clean network view.
**Edges:** Directed (`vee` arrows), color `#93c5fd`, 1.5px, 85% opacity.
**On click:** Floating metadata tooltip appears with entity fields.
**After query:** Matched nodes glow gold, others dim to 8%, camera animates to fit the subgraph.
**Controls:** ↩ Overview (resets to full graph), ⌇ Edges toggle (show/hide edges), +/−/⊡ zoom.

**Layout:** `breadthfirst` for query results (≤80 nodes, layered top-to-bottom following O2C flow direction), `cose` for full overview (466 nodes, force-directed clustering).

---

## Dataset

| Entity | Rows |
|--------|------|
| Sales Order Headers | 100 |
| Sales Order Items | 166 |
| Schedule Lines | 200 |
| Delivery Headers | 86 |
| Delivery Items | 142 |
| Billing Doc Headers | 163 |
| Billing Doc Items | 329 |
| Cancellations | 80 |
| Journal Entry Items (AR) | 409 |
| Payments (AR) | 120 |
| Business Partners | 183 |
| Addresses | 183 |
| Customer Company Assignments | 183 |
| Customer Sales Area Assignments | 557 |
| Products | 521 |
| Product Descriptions | 996 |
| Product Plants | 3,532 |
| Product Storage Locations | 13,356 |
| Plants | 87 |
| **Total** | **~21,393** |

**Graph: 4,164 edges across 10 relationship types**

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini key (ai.google.dev) | — |
| `GROQ_API_KEY` | Groq key (console.groq.com) | — |
| `GEMINI_MODEL` | Model override | `gemini-2.5-flash-lite` |
| `GROQ_MODEL` | Groq model override | `llama3-8b-8192` |
| `APP_DB_PATH` | Custom SQLite path | `<repo>/data/app.db` |
