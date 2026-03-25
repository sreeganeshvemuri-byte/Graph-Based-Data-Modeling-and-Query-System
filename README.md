# Graph-Based Data Modeling and Query System

> **Forward-Deployed Engineer Take-Home Task**
> SAP Order-to-Cash (O2C) context graph with LLM-powered natural language query interface.

---

## Live Demo

🔗 **[https://o2c-graph-explorer.runable.app](https://o2c-graph-explorer.runable.app)**

Use the suggestions in the chat panel or type any of the queries listed below.

---

## What Was Built

A full-stack system that ingests a fragmented SAP O2C dataset (100+ sales orders, 163 billing documents, deliveries, payments, journal entries) into a relational graph, visualizes the entity network interactively, and lets users query it in natural language — with streaming AI-generated answers.

```
┌─────────────────────────────────────────────┐
│              React + Cytoscape UI            │
│   ┌──────────────────┐  ┌─────────────────┐  │
│   │  Graph Explorer  │  │  Chat / Query   │  │
│   │  (live graph,    │  │  (streaming NL  │  │
│   │   node expand,   │  │   answers,      │  │
│   │   highlight)     │  │   result tables)│  │
│   └──────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────┘
                     │ HTTP / SSE
┌─────────────────────────────────────────────┐
│             FastAPI Backend                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │  /graph  │  │  /query  │  │  /query   │  │
│  │ overview │  │ (JSON)   │  │  /stream  │  │
│  │  stats   │  │          │  │   (SSE)   │  │
│  └──────────┘  └──────────┘  └───────────┘  │
│                     │                        │
│  ┌──────────────────────────────────────┐    │
│  │          SQLite Database             │    │
│  │  13 relational tables + graph_edges  │    │
│  └──────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

---

## Features

### 1. Graph Construction
- Ingests all 19 JSONL entity types from the SAP O2C dataset
- Builds a graph of **10 edge types** connecting entities:
  - `SOLD_TO` — SalesOrder → Customer
  - `FULFILLED_BY` — SalesOrder → Delivery
  - `BILLED_AS` — SalesOrder → BillingDocument
  - `BILLED_TO` — BillingDocument → Customer
  - `POSTS_TO` — BillingDocument → AccountingDocument
  - `CLEARED_BY` — AccountingDocument → PaymentDocument
  - `CANCELLED_BY` — BillingDocument → CancellationDocument
  - `CONTAINS_MATERIAL` — SalesOrder → Product
  - `SHIPS_FROM` — Delivery → Plant
  - `STORED_AT` — Product → StorageLocation

### 2. Graph Visualization
- Full O2C graph (466 nodes, 800+ edges) loads on startup
- Color-coded node types: Sales Orders (purple), Deliveries (teal), Billing Docs (orange), Accounting Docs (gold), Customers (blue), Payments (green), Products (indigo), Schedule Lines (pink)
- Click any node to inspect its metadata in the side panel
- Zoom / pan / fit controls
- After a query — highlighted nodes glow gold, others dim, camera animates to focus

### 3. Conversational Query Interface — Streaming
- Queries go through `POST /api/query/stream` (Server-Sent Events)
- Three-stage stream: `plan` → `result` → `token` (NL answer word by word) → `done`
- Uses **Gemini 2.0 Flash** (or Groq) for natural language answer generation
- Falls back to rule-based NL synthesizer if LLM is rate-limited — no errors shown to user
- Inline result rendering per intent: tables for top products, issue lists for broken flows, entity cards for lookups

### 4. Query Engine — Four Intents

| Intent | Example | What it does |
|--------|---------|--------------|
| `trace_flow` | "Show full journey for sales order 740509" | Walks sales order → schedule lines → delivery → billing → journal entry → payment |
| `top_products_by_billing` | "Top 10 products by revenue" | Aggregates billing items, joins products, sorts by net amount / invoice count / quantity |
| `find_broken_flows` | "Find data quality issues" | Checks 7 break types: billing without delivery, missing journal entries, amount mismatches, transactions on blocked partners, etc. |
| `lookup_entity` | "Look up customer 310000108" | Fetches any entity (customer, product, plant, sales order, delivery, billing doc) with related data |

### 5. Guardrails
- Out-of-scope queries ("What is the capital of France?") → rejected with explanation
- Mutation verbs (delete/update/create) → rejected
- Customer names without IDs → rejected with clarification request
- Unrecognized intents → rejected

### 6. Rule-Based Fast Path
High-frequency patterns skip the LLM entirely — zero latency, zero API cost:
- `"sales order \d+"` with flow keywords → `trace_flow`
- `"billing doc \d+"` with flow keywords → `trace_flow`
- `"top \d+ products"` → `top_products_by_billing`
- `"broken / data quality / issues"` → `find_broken_flows`
- `"look up customer/product/delivery \d+"` → `lookup_entity`

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── graph.py          # GET /api/graph/overview, /stats
│   │   │   ├── query.py          # POST /api/query, /api/query/stream (SSE)
│   │   │   ├── health.py         # GET /api/health
│   │   │   └── router.py
│   │   ├── db/
│   │   │   ├── models.py         # 13 SQLAlchemy ORM models + GraphEdge
│   │   │   ├── session.py        # SQLite engine, session factory
│   │   │   └── base.py
│   │   ├── ingestion/
│   │   │   ├── cli.py            # python -m app.ingestion.cli <dataset_root>
│   │   │   ├── ingest_jsonl.py   # Parses all 19 JSONL entity types
│   │   │   └── graph_builder.py  # Builds graph_edges from relational tables
│   │   ├── llm/
│   │   │   └── planner.py        # Rule-based + Gemini/Groq query plan generation
│   │   └── query/
│   │       ├── plans.py          # Pydantic models for 5 plan types
│   │       ├── validation.py     # Strict schema validation layer
│   │       ├── handlers.py       # SQL execution for each intent
│   │       └── execute.py        # Intent router
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx               # Layout, graph state, overview fetch on mount
│   │   ├── App.css
│   │   ├── components/
│   │   │   ├── GraphView.jsx     # Cytoscape graph, highlighting, zoom
│   │   │   ├── GraphView.css
│   │   │   ├── ChatPanel.jsx     # SSE streaming consumer, result rendering
│   │   │   └── ChatPanel.css
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js            # Proxies /api → localhost:8000
└── sap-order-to-cash-dataset/    # Source JSONL files (19 entity types)
```

---

## Local Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- A free API key from [Groq](https://console.groq.com) or [Google Gemini](https://ai.google.dev)

### Step 1 — Clone & install backend

```bash
git clone https://github.com/sreeganeshvemuri-byte/Graph-Based-Data-Modeling-and-Query-System.git
cd Graph-Based-Data-Modeling-and-Query-System

# Create virtualenv (recommended)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install fastapi "uvicorn[standard]" sqlalchemy pydantic python-dotenv
```

### Step 2 — Configure LLM API key

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and add one of:
```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
# OR
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxx
```

> The system works without an API key — the rule-based planner handles the most common queries and the NL summarizer uses a built-in fallback. An API key enables free-form natural language beyond the built-in patterns.

### Step 3 — Ingest the dataset & build graph

```bash
cd backend
PYTHONPATH=. python -m app.ingestion.cli \
  ../sap-order-to-cash-dataset/sap-o2c-data \
  --build-edges
```

This will:
- Create `data/app.db` (SQLite)
- Ingest all 19 JSONL entity types (~21,000 rows)
- Build 4,164 graph edges across 10 relationship types

Expected output:
```
Ingestion complete: total_rows_upserted=21393 skipped_due_to_missing_pk=0 total_errors=0
Canonicalized billing references: updated_rows=245
Building graph edges...
Ingestion finished.
```

### Step 4 — Start the backend

```bash
# From the backend/ directory
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify: `curl http://localhost:8000/api/health` → `{"status":"ok"}`

### Step 5 — Start the frontend

```bash
# In a new terminal, from the frontend/ directory
cd ../frontend
npm install
npm run dev
```

Open **http://localhost:5173**

---

## API Reference

### `GET /api/health`
```json
{"status": "ok"}
```

### `GET /api/graph/overview?max_edges=800`
Returns all graph nodes and edges for visualization. Supports `node_types` filter param.

### `GET /api/graph/stats`
Returns node/edge counts by type.

### `POST /api/query`
Synchronous — returns plan + result in one response.
```json
{ "query": "Show full journey for sales order 740509" }
```
Response:
```json
{
  "plan": { "intent": "trace_flow", "entity_id": "740509", ... },
  "result": { "path": { "nodes": [...], "edges": [...] } }
}
```

### `POST /api/query/stream`
Streaming SSE — use for the UI. Same request body as `/query`.

Events emitted in order:
```
data: {"type": "plan",   "payload": { ...query plan... }}
data: {"type": "result", "payload": { ...query result... }}
data: {"type": "token",  "payload": "word "}   ← repeats for each token
data: {"type": "done",   "payload": null}
```

---

## Example Queries

These work out of the box (rule-based, no LLM needed):

```
Show me the full journey for sales order 740509
Trace the full flow of billing document 90504274
Top 10 products by billing revenue
Top 5 products by invoice count
Find all data quality issues
Find deliveries with no sales order
Look up customer 310000108
Look up sales order 740506
```

These use the LLM (Gemini / Groq) for intent parsing:

```
Which products are associated with the highest number of billing documents?
Identify sales orders that have broken or incomplete flows
Are there any billing documents posted without a journal entry in fiscal year 2025?
Show me all transactions for blocked customers
Find billing documents where amounts don't match journal entries
```

---

## Technical Decisions

### Why SQLite + graph_edges table instead of a graph DB?
The dataset is small enough (~21K rows) that SQLite with indexed joins performs well. A dedicated graph DB (Neo4j, ArangoDB) would add operational overhead for negligible performance gain at this scale. The `graph_edges` table acts as an adjacency list — multi-hop traversals are just sequential joins.

### Why rule-based planner + LLM fallback?
The most common O2C queries follow predictable patterns (`show order X`, `trace billing Y`, `find issues`). Handling these with regex avoids LLM latency and cost entirely. The LLM handles everything else. This makes the system fast and reliable even when rate-limited.

### Why Server-Sent Events for streaming?
SSE is simpler than WebSockets for a unidirectional stream (server → client). It works over HTTP/1.1, needs no upgrade handshake, and is natively handled by the browser's `fetch` API with `ReadableStream`.

### Why validate LLM output with Pydantic?
The LLM output is treated as untrusted data. Before any SQL is executed, the JSON plan is validated against strict Pydantic models (`extra="forbid"`, enum literals for all intent/entity types). This ensures the system never executes malformed or injected queries.

---

## Dataset Summary

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
| Journal Entry Items (AR) | `journal_entry_items_accounts_receivable` | 409 |
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

**Total: ~21,393 rows across 19 entity types**

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key (free at ai.google.dev) | — |
| `GROQ_API_KEY` | Groq API key (free at console.groq.com) | — |
| `GEMINI_MODEL` | Gemini model name | `gemini-2.0-flash` |
| `GROQ_MODEL` | Groq model name | `llama3-8b-8192` |
| `APP_DB_PATH` | Custom SQLite path | `<repo_root>/data/app.db` |
