# Graph-Based Data Modeling and Query System

> **Forward-Deployed Engineer Take-Home Task — Dodge AI**
> SAP Order-to-Cash context graph with LLM-powered natural language query interface, streaming responses, and interactive graph visualization.

---

## Live Demo

🔗 **[https://vdcyw7yuosfys99hmyfprsrtbuygxmg5.runable.site](https://vdcyw7yuosfys99hmyfprsrtbuygxmg5.runable.site)**

Full dataset loaded: 21,393 rows · 19 entity types · 4,164 graph edges · 466 visual nodes.

**Suggested queries:**
```
Show me the full journey for sales order 740509
Trace the full flow of billing document 90504274
Which products have the highest number of billing documents?
Find all data quality and broken flow issues
Identify sales orders with incomplete flows
Look up customer 310000108
Are there billing docs without journal entries?
Show me delivered but not billed orders
Find invoices with amount mismatches
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    React + Vite Frontend                     │
│  ┌─────────────────────────┐  ┌──────────────────────────┐  │
│  │     GraphView.jsx        │  │      ChatPanel.jsx        │  │
│  │  Cytoscape.js canvas     │  │  SSE stream consumer      │  │
│  │  dot nodes, hover cards  │  │  NL answer word-by-word   │  │
│  │  highlight + dim logic   │  │  plan badge, result table │  │
│  └─────────────────────────┘  └──────────────────────────┘  │
│                    App.jsx (state, routing)                   │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTP / Server-Sent Events
┌──────────────────────────▼───────────────────────────────────┐
│                   FastAPI Backend                             │
│  GET  /api/graph/overview    — full graph JSON               │
│  GET  /api/graph/stats       — node/edge counts              │
│  POST /api/query             — sync plan + result            │
│  POST /api/query/stream      — SSE: plan→result→tokens→done  │
└──────────────────────────┬───────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
  planner.py          handlers.py         SQLite DB
  Rule-based          4 intent            13 tables
  (95% coverage)      SQL executors       + graph_edges
  + Gemini fallback
```

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app entry point
│   │   ├── api/
│   │   │   ├── router.py              # Registers all API routers
│   │   │   ├── graph.py               # /graph/overview, /graph/stats
│   │   │   ├── query.py               # /query (sync) + /query/stream (SSE)
│   │   │   └── health.py              # /health
│   │   ├── db/
│   │   │   ├── base.py                # SQLAlchemy DeclarativeBase
│   │   │   ├── models.py              # 13 ORM models + GraphEdge
│   │   │   └── session.py             # Engine, SessionLocal, init_db()
│   │   ├── ingestion/
│   │   │   ├── cli.py                 # CLI: python -m app.ingestion.cli <path>
│   │   │   ├── ingest_jsonl.py        # Parses all 19 JSONL entity types
│   │   │   └── graph_builder.py       # Builds graph_edges from relational tables
│   │   ├── llm/
│   │   │   └── planner.py             # Rule-based + Gemini query plan generation
│   │   └── query/
│   │       ├── plans.py               # Pydantic models for 5 plan types
│   │       ├── validation.py          # Strict schema validation layer
│   │       ├── handlers.py            # SQL execution per intent
│   │       └── execute.py             # Routes plan → correct handler
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── App.jsx                    # Root: state, graph data, API calls
│       ├── components/
│       │   ├── GraphView.jsx          # Cytoscape graph, tooltip, highlighting
│       │   └── ChatPanel.jsx          # SSE consumer, streaming chat UI
│       └── main.jsx
└── sap-order-to-cash-dataset/         # Source JSONL files
```

---

## Local Setup

### Prerequisites
- Python 3.11+, Node.js 18+, npm
- Free API key: [Groq](https://console.groq.com) or [Google Gemini](https://ai.google.dev)

### 1 — Install backend
```bash
git clone https://github.com/sreeganeshvemuri-byte/Graph-Based-Data-Modeling-and-Query-System.git
cd Graph-Based-Data-Modeling-and-Query-System

python -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" sqlalchemy pydantic python-dotenv
```

### 2 — Configure API key
```bash
cp backend/.env.example backend/.env
# Edit backend/.env:
GEMINI_API_KEY=AIzaSy...      # gemini-2.5-flash-lite (highest free RPM)
# OR
GROQ_API_KEY=gsk_...
```

> The system works fully without an API key. 95%+ of queries are handled by the rule-based planner with zero API calls. An API key only matters for unusual free-form phrasings and richer NL answers.

### 3 — Ingest dataset
```bash
cd backend
PYTHONPATH=. python -m app.ingestion.cli \
  ../sap-order-to-cash-dataset/sap-o2c-data \
  --build-edges
```
Creates `data/app.db` with ~21,393 rows and 4,164 graph edges. Takes ~10 seconds.

### 4 — Start backend
```bash
PYTHONPATH=. uvicorn app.main:app --port 8000 --reload
```

### 5 — Start frontend
```bash
cd ../frontend && npm install && npm run dev
# Open http://localhost:5173
```

---

## API Reference

### `GET /api/health`
```json
{"status": "ok"}
```

### `GET /api/graph/overview?max_edges=800`
Returns all nodes and edges for visualization. Nodes include lightweight metadata (status, amounts, names).

### `GET /api/graph/stats`
Returns node and edge counts grouped by type.

### `POST /api/query`
Synchronous. Body: `{"query": "..."}`. Returns `{plan, result}`.

### `POST /api/query/stream`
Server-Sent Events. Same body. Emits 4 event types in sequence:
```
data: {"type": "plan",   "payload": {...}}     ← query plan immediately
data: {"type": "result", "payload": {...}}     ← DB result
data: {"type": "token",  "payload": "word "}  ← NL answer tokens
data: {"type": "done",   "payload": null}
```

---

## Query Engine — 4 Intents

| Intent | Trigger | What runs |
|--------|---------|-----------|
| `trace_flow` | "journey", "flow", "trace" + entity ID | Multi-hop SQL: order→delivery→billing→journal→payment |
| `top_products_by_billing` | "top products", "highest billing", "revenue" | GROUP BY material, JOIN billing headers, ORDER BY |
| `find_broken_flows` | "broken", "issues", "without", "mismatch" | 7 gap-analysis queries across the pipeline |
| `lookup_entity` | entity type + ID | Single-entity fetch with optional related data |

### 7 Break Types (`find_broken_flows`)
1. `billing_without_delivery` — billed but no delivery in graph
2. `delivery_without_sales_order` — delivery has no upstream order
3. `billing_without_journal_entry` — no accounting document posted
4. `journal_entry_without_clearing` — AR not cleared/paid
5. `cancelled_without_accounting_doc` — cancelled billing missing reversal entry
6. `active_txn_on_blocked_partner` — transactions on blocked customer
7. `amount_mismatch_billing_vs_journal` — billing total ≠ journal sum

---

## How the Rule-Based Planner Works

The planner checks regex patterns before ever calling the LLM. Coverage: **19/19 common queries** with zero API calls.

```
"Show me the full journey for sales order 740509"
   → regex matches: (sales order|order|so) + 6-digit number + flow keyword
   → returns trace_flow plan instantly, no Gemini call

"Which products have the highest number of billing documents?"
   → regex matches: product keyword + billing keyword + ranking keyword
   → returns top_products_by_billing{sort_by: invoice_count}

"Are there billing docs without journal entries?"
   → regex matches: billing.*journal pattern
   → returns find_broken_flows{break_types: [billing_without_journal_entry]}

"Look up customer 310000108"
   → regex matches: lookup verb + customer + 6-digit number
   → returns lookup_entity{entity_type: customer}
```

Only queries with no clear structural match reach Gemini — things like "which customer placed the most orders this quarter". Those are ~5% of real usage.

---

## LLM Usage and Rate Limits

| Model | RPM (free tier) | Used for |
|-------|----------------|---------|
| `gemini-2.5-flash-lite` | ~30 req/min | Query plan (rare, rule-based covers 95%) + NL answer |
| `gemini-2.0-flash` | ~15 req/min | ❌ Old model, rate-limited immediately |

**Why 429s happened before:** Two Gemini calls per query (plan + NL answer) on a 15 RPM model = rate-limited on second question. Fixed by:
1. Switching to `gemini-2.5-flash-lite` (2x RPM headroom)
2. 95% of queries now rule-based (zero API calls for plan)
3. NL answer auto-falls back to deterministic synthesizer on any 429 — no errors shown to user

---

## Graph Visualization

**Layout algorithms:**
- `breadthfirst` for ≤80 nodes — layers nodes top-to-bottom following edge direction, good for O2C pipelines
- `cose` (Compound Spring Embedder) for >80 nodes — force-directed physics, clusters connected components

**Interaction:**
- Click node → floating metadata tooltip (animates in, close button)
- No labels on nodes by default → clean visual
- ⌇ Edges button → toggle all edge visibility on/off
- ↩ Overview button → appears after a query, resets to full 466-node graph
- +/−/⊡ → zoom controls

**Highlighting after a query:**
```
Queried nodes  → gold border, glow shadow, full opacity, size 18px
Other nodes    → dimmed to 8% opacity
Connecting edges → indigo color, full opacity
Other edges    → dimmed to 4% opacity
Camera         → animates to fit highlighted subgraph (500ms)
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini key (free at ai.google.dev) | — |
| `GROQ_API_KEY` | Groq key (free at console.groq.com) | — |
| `GEMINI_MODEL` | Gemini model override | `gemini-2.5-flash-lite` |
| `GROQ_MODEL` | Groq model override | `llama3-8b-8192` |
| `APP_DB_PATH` | Custom SQLite path | `<repo>/data/app.db` |

---

## Dataset

| Entity | Table | Rows |
|--------|-------|------|
| Sales Order Headers | `sales_order_headers` | 100 |
| Sales Order Items | `sales_order_items` | 166 |
| Sales Order Schedule Lines | `sales_order_schedule_lines` | 200 |
| Outbound Delivery Headers | `outbound_delivery_headers` | 86 |
| Outbound Delivery Items | `outbound_delivery_items` | 142 |
| Billing Document Headers | `billing_document_headers` | 163 |
| Billing Document Items | `billing_document_items` | 329 |
| Billing Document Cancellations | `billing_document_cancellations` | 80 |
| Journal Entry Items (AR) | `journal_entry_items_ar` | 409 |
| Payments (AR) | `payments_accounts_receivable` | 120 |
| Business Partners | `business_partners` | 183 |
| Business Partner Addresses | `business_partner_addresses` | 183 |
| Customer Company Assignments | `customer_company_assignments` | 183 |
| Customer Sales Area Assignments | `customer_sales_area_assignments` | 557 |
| Products | `products` | 521 |
| Product Descriptions | `product_descriptions` | 996 |
| Product Plants | `product_plants` | 3,532 |
| Product Storage Locations | `product_storage_locations` | 13,356 |
| Plants | `plants` | 87 |

**Total: ~21,393 rows · 10 edge types · 4,164 graph edges**
