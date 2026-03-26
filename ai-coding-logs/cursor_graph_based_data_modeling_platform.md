# Graph-based data modeling platform
_Exported on 3/26/2026 at 23:17:54 GMT+5:30 from Cursor (2.6.21)_

---

**User**

We are building a full-stack system for a graph-based data modeling and query platform.

Context:
- Dataset comes from multiple JSONL files (already summarized)
- We have already designed the system architecture

Your role:
You are a senior full-stack engineer. You will implement this system step by step.

Constraints:
- Keep code clean and modular
- Do not overengineer
- Make everything runnable
- Follow a backend-first approach

We will proceed step by step. Do not jump ahead.
Acknowledge and wait for next instruction.

---

**Cursor**

Understood. I’ll keep changes clean and modular, avoid overengineering, and implement backend-first so each step is runnable.

Next, tell me what you want to implement first (e.g., API skeleton, data ingestion from the summarized JSONL, graph storage choice, or query execution endpoint). Once you confirm the first step, I’ll start by inspecting the current codebase structure and any existing architecture contracts.

---

**User**

Create a full-stack monorepo with:

Backend:
- FastAPI
- SQLite (local)
- SQLAlchemy
- Pydantic

Frontend:
- React + Vite

Structure:
- backend/
- frontend/
- scripts/
- data/

Backend requirements:
- API entry point
- DB connection setup
- basic router structure

Frontend:
- basic React app with empty layout

Make sure:
- project runs locally
- backend and frontend can start independently

Do not implement business logic yet.

---

**Cursor**

I’ll first inspect the current repository contents, then scaffold the monorepo folders (`backend/`, `frontend/`, `scripts/`, `data/`) and add minimal runnable FastAPI + Vite apps with independent start commands—without any business/query logic.

Repository is basically empty right now (only the JSONL summary + a Python script). Next I’ll create the `backend/`, `frontend/`, `scripts/`, and `data/` directories, then add minimal runnable FastAPI and Vite scaffolding (no business logic yet).

I’m going to add the monorepo scaffolding files now: backend FastAPI app (with a health endpoint and SQLite SQLAlchemy session setup) and a minimal Vite+React frontend (empty layout). After that, I’ll do a quick backend import/compile check.

I’ll now add the frontend (Vite + React + TypeScript) scaffolding plus simple PowerShell scripts to start backend and frontend independently. After that, I’ll run a quick Python import/compile check for the backend code.

Next I’ll add the repo-level run scripts plus `README.md` and `.gitignore`, then I’ll run a quick backend syntax/import check to confirm the FastAPI scaffolding is runnable.

Backend code compiles cleanly, but dependencies aren’t installed yet in this environment. Next I’ll `pip install -r backend/requirements.txt` and then do a quick import check + start verification (health endpoint) to ensure the backend is runnable.

Backend logic is fine, but the quick smoke-test failed because Python was executed from the repo root, so the `app` package wasn’t on `PYTHONPATH`. Next I’ll rerun the same check from inside `backend/` (matching how the run script starts uvicorn).

Now that `httpx` is installed, I’ll rerun the FastAPI smoke-test from inside `backend/` to confirm the `/api/health` route responds correctly.

Scaffolding is in place and the backend health endpoint smoke-test passed. Next I’ll check `git status` to verify all new files are tracked/visible as expected, and then wait for your next step.

Monorepo scaffold created with the requested structure:

- `backend/` (FastAPI + SQLite + SQLAlchemy + Pydantic)
  - API entry point: `backend/app/main.py`
  - DB setup: `backend/app/db/session.py` (SQLite file at `data/app.db`)
  - Basic router structure: `backend/app/api/router.py` + `backend/app/api/health.py`
  - Health endpoint: `GET /api/health`
- `frontend/` (React + Vite) with an empty placeholder layout
  - `frontend/src/App.tsx`, `frontend/src/components/EmptyLayout.tsx`
- `scripts/`
  - `scripts/run_backend.ps1` (starts FastAPI)
  - `scripts/run_frontend.ps1` (starts Vite; requires local Node/npm)
- `data/` directory created for local SQLite artifacts

Quick run (independent):
- Backend: `powershell .\scripts\run_backend.ps1` (or `cd backend` then `uvicorn app.main:app --reload --port 8000`)
- Frontend: `powershell .\scripts\run_frontend.ps1` (requires Node.js/npm)

Backend smoke-test: `/api/health` returns `{"status":"ok"}`.

Waiting for your next instruction on the next backend-first step (e.g., ingestion endpoint/loader, graph schema/models, or query endpoint scaffolding).

---

**User**

Here is the finalized data model and graph design:


@o2c_build_spec.docx 

Implement this as SQLAlchemy models.

Requirements:
- each entity → table
- proper primary keys
- foreign keys where applicable
- also create graph_edges table with:
  - source_type
  - source_id
  - target_type
  - target_id
  - edge_type

Keep models clean and readable.
Do not implement ingestion yet.

---

**Cursor**

Next I’ll open `o2c_build_spec.docx` to extract the exact entity names, fields, and relationships. Then I’ll add clean SQLAlchemy model classes under `backend/app/db/` (one table per entity + `graph_edges`), without touching any ingestion logic.

I installed a DOCX text extraction dependency (`python-docx`). Next I’ll extract the build spec content into the terminal output so I can accurately implement the SQLAlchemy tables and relationships.

DOCX extraction failed because the shell is PowerShell and doesn’t support the bash-style heredoc I used. Next I’ll rerun the extraction using a single `python -c` command so we can read the spec text and implement the SQLAlchemy models correctly.

I’m going to re-run the DOCX extraction as a single-line `python -c` command (PowerShell quoting + newlines were breaking the earlier attempts). Once we have the spec text, I’ll map it directly into SQLAlchemy entity tables + the required `graph_edges` table.

The build spec content for schema is likely inside DOCX tables (not just paragraphs), which is why my paragraph slice was empty. Next I’ll inspect `doc.tables` to locate the table catalogue and FK map sections, then extract just the relevant rows/columns needed for the SQLAlchemy models.

Now that we have the entity list, primary keys, and FK relationships from the spec DOCX tables, I’ll add a new SQLAlchemy `backend/app/db/models.py` containing all 19 entity tables plus the required `graph_edges` table. Then I’ll update `init_db()` to import these models so `Base.metadata.create_all()` actually creates them.

I added the full set of SQLAlchemy models plus `graph_edges`, and wired `init_db()` to import them before table creation. Next I’ll run a backend DB init smoke-test to ensure `Base.metadata.create_all()` succeeds (SQLite foreign keys, composite keys, etc.).

DB tables are now created (SQLite `data/app.db` exists), so the model definitions are syntactically valid. Next I’ll run a backend startup/health smoke test via `TestClient` to ensure `init_db()` succeeds at runtime and the foreign key constraints/composite keys don’t break FastAPI startup.

Implemented the finalized relational graph design as SQLAlchemy models (no ingestion yet).

### What I added
- `backend/app/db/models.py`
  - One table per entity from the spec:
    - `business_partners`, `business_partner_addresses`, `customer_company_assignments`, `customer_sales_area_assignments`
    - `products`, `product_descriptions`, `plants`, `product_plants`, `product_storage_locations`
    - `sales_order_headers`, `sales_order_items`, `sales_order_schedule_lines`
    - `outbound_delivery_headers`, `outbound_delivery_items`
    - `billing_document_headers`, `billing_document_items`, `billing_document_cancellations`
    - `journal_entry_items_ar`, `payments_accounts_receivable`
  - Correct primary keys per the spec
  - Foreign keys per the spec’s FK map where it can be represented cleanly in SQLite (including composite FKs)
  - `graph_edges` table with exactly:
    - `source_type`, `source_id`, `target_type`, `target_id`, `edge_type`
- Updated DB startup wiring:
  - `backend/app/db/session.py`: `init_db()` now imports `app.db.models` before calling `Base.metadata.create_all()`.

### Local run check
- `data/app.db` is created and the schema is successfully created via `init_db()` (backend startup won’t fail due to missing model imports).

Next step: tell me what you want to scaffold first on top of this model layer (e.g., repository/session usage + a minimal `/api/...` endpoint for listing a table, or the basic router structure for CRUD placeholders).

---

**User**

Implement a data ingestion pipeline.

Context:
- dataset is stored as multiple folders with JSONL files

Requirements:
- read JSONL files folder-wise
- map raw records to canonical schema
- insert into database

Important:
- handle missing fields
- handle inconsistent keys across files
- log errors clearly
- make ingestion rerunnable

Also:
- create a function build_graph_edges()

This function should:
- read relational tables
- generate graph_edges based on relationships

Do not implement APIs yet.

---

**Cursor**

Next I’ll inspect the existing JSONL summarization script/output to learn the canonical field names and how the raw JSONL is structured. Then I’ll implement a rerunnable backend ingestion pipeline that maps records into the SQLAlchemy models and a separate `build_graph_edges()` that derives `graph_edges` from relational tables—without adding any APIs yet.

I’m going to extract the exact field/key names for the remaining tables directly from `sap_o2c_jsonl_summary.txt` (since it includes real JSONL columns). That will ensure the ingestion mapping and especially the `build_graph_edges()` logic (like clearing doc field names) match the actual dataset keys.

I extracted the JSONL field names from `sap_o2c_jsonl_summary.txt`, and there are a couple of mismatches with the current model column/FK assumptions (notably `referenceSdDocumentItem`, and journal clearing field naming). Next I’ll update the SQLAlchemy models to align with the actual raw JSON keys needed for FK consistency, recreate the SQLite schema, and then implement the ingestion + `build_graph_edges()` functions.

I’m going to implement the ingestion pipeline now. Concretely: I’ll add an ingestion module that (1) discovers JSONL-containing folders under a dataset root, (2) maps raw JSONL records into the canonical SQLAlchemy tables with robust type conversion + missing-field handling, (3) upserts rows so runs are rerunnable, and (4) adds `build_graph_edges()` to repopulate `graph_edges` purely from the relational tables.

Next I’ll harden the ingestion pipeline to meet your requirements: it should log missing primary keys and invalid JSON per line (without aborting the whole run), handle missing/extra keys robustly, and remain rerunnable via PK-based upserts. After that, I’ll add a small CLI entrypoint so you can run ingestion and optionally rebuild `graph_edges` from the relational tables.

Next I’ll run a backend compile/import check for the new ingestion + graph builder modules, and then I’ll run a small “empty database” test to ensure `build_graph_edges()` doesn’t crash when the relational tables are empty. If anything fails, I’ll fix it before we proceed further.

`build_graph_edges()` is failing on the empty DB due to an invalid SQLite query (I mistakenly used `distinct()` in a way that generates `DISTINCT DISTINCT`). Next I’ll patch `graph_builder.py` to remove that faulty query and rely on simple Python deduping (already used elsewhere), then re-run the empty-db smoke test.

There’s already a dataset directory in the repo (`sap-order-to-cash-dataset/…/sap-o2c-data/`) with all the expected JSONL table folders. Next I’ll run the ingestion CLI against that dataset root (upserting into SQLite) and then run `--build-edges` to confirm `graph_edges` is populated from relational tables—this is just a smoke test and does not add any API logic.

In the smoke-test ingestion run, the only failures were missing primary keys for `customer_sales_area_assignments`. The JSONL uses different raw key names (`salesOrganization`, `distributionChannel`) than my mapper expected (`salesOrg`, `distCh`). Next I’ll update the mapper + required-PK detection for that table, then rerun ingestion + `build_graph_edges()` to confirm edge population is complete.

One more alignment tweak: your build spec says `graph_edges` should have exactly `source_type`, `source_id`, `target_type`, `target_id`, `edge_type`. My current model includes an extra auto `id` column. Next I’ll update the SQLAlchemy `GraphEdge` model to use a composite primary key over those five columns (no surrogate `id`), then rebuild edges once to confirm everything still works end-to-end.

Implemented the JSONL ingestion pipeline (backend-first, no APIs).

### Added / Updated
- `backend/app/ingestion/ingest_jsonl.py`
  - Discovers JSONL-containing folders under a `dataset_root` (folder-wise).
  - Maps raw records to your canonical SQLAlchemy entities.
  - Type-converts values (bool/float/datetime) and normalizes padded numeric IDs (e.g. `"000010"` -> `"10"`) where needed for consistency.
  - Handles missing fields:
    - If required PK fields are missing for that table, the row is skipped and a clear `WARNING` is logged with `table/file/line/missing=...`.
    - Invalid JSON / non-object JSON lines are logged and skipped (run continues).
  - Rerunnable: uses PK-based `session.merge()` upserts (no duplicates).

- `backend/app/ingestion/graph_builder.py`
  - Implements `build_graph_edges(session: Session)`.
  - Reads relational tables and (re)generates `graph_edges` for the full edge set:
    - `SOLD_TO`, `CONTAINS_MATERIAL`, `FULFILLED_BY`, `SHIPS_FROM`, `BILLED_AS`, `BILLED_TO`, `POSTS_TO`, `CLEARED_BY`, `CANCELLED_BY`, `STORED_AT`
  - Idempotent: clears `graph_edges` then rebuilds.

- `backend/app/ingestion/cli.py`
  - CLI to run ingestion and optionally rebuild edges.

- `scripts/run_ingestion.ps1`
  - Convenience wrapper to run the CLI.

- `backend/app/db/models.py`
  - Adjusted `graph_edges` to use exactly the required columns as a composite primary key.
  - Added FK-support columns needed for correct edge derivation:
    - `OutboundDeliveryItem.referenceSdDocumentItem`
    - `BillingDocumentItem.referenceSdDocumentItem`
    - `JournalEntryItemsAR.clearingAccountingDocument`

### How to run ingestion locally
Example using the dataset already present in your repo:
- `cd backend`
- `python -m app.ingestion.cli "../sap-order-to-cash-dataset/sap-o2c-data" --build-edges`

This will upsert into SQLite and then rebuild `graph_edges`.

If you want ingestion to also support a `--truncate` mode (clear entity tables before loading) for “exact re-sync” semantics, tell me and I’ll add it.

---

**User**

Add debug/test utilities to validate the ingestion and graph.

Create functions or scripts to:

1. Fetch a sample sales order and:
   - its items
   - its deliveries
   - its billing documents
   - its accounting entries

2. Given a billing document:
   - trace back to sales order
   - trace forward to accounting document

3. Query graph_edges:
   - pick one sales order
   - show all connected nodes

4. Print counts:
   - total rows per table
   - total edges per type

Goal:
Verify relationships are correct and no major linkage is broken.

---

**Cursor**

Next I’ll add a small backend-only debug harness (Python script + helper functions) that reads from the existing SQLite database and validates linkage by: (1) sampling a sales order and pulling related relational rows + (optionally) graph edges, (2) tracing back/forward from a billing doc using both relational joins and `graph_edges`, and (3) printing counts per table and per edge type.

I added an initial validation script, but I see it contains a bad import (`app.db.dbutil`) and a stray unused query. Next I’ll patch the script to remove the invalid import, clean up the sales-order bundle logic, and then run it against the already-ingested SQLite DB to confirm it prints sensible counts and connected-node neighborhoods.

Now I’ll run the new validation utility against the already-ingested SQLite DB to confirm it can: (1) pull a sample sales order bundle, (2) trace back/forward from a billing document, (3) compute a connected-node neighborhood from `graph_edges`, and (4) print row/edge counts. If it errors, I’ll patch and rerun.

Validation ran successfully, but the auto-selected “first” sales order (740506) happened to have zero billed documents in the graph, so parts (billing documents + accounting entries) were empty. Next I’ll tweak the sample selection logic to pick a sales order that actually has `BILLED_AS` edges, then rerun the validator to show all relationship links in the output.

The validator is now showing a real consistency issue: the chosen sales order has `BILLED_AS` edges, but relational `sales_order_items` rows for that same ID are missing (count=0). Next I’ll confirm whether the sales order exists in `sales_order_headers` and then pinpoint which ingestion mapping/table is dropping these rows. Based on that, I’ll adjust the ingestion mappers (still no APIs) so relationships don’t end up referencing non-existent relational records.

The validator revealed a key linkage break: `graph_edges` contains `BILLED_AS` edges to sales orders that don’t exist in `sales_order_headers/sales_order_items` (e.g., a sales order with `BILLED_AS` but `sales_order_items` count = 0). That’s coming from `build_graph_edges()` being too loose for `BILLED_AS`. Next I’ll update `build_graph_edges()` to follow the spec join more closely (use `referenceSdDocumentItem` join to `sales_order_items`), then rebuild edges and rerun the validator.

Edge generation is now more consistent, but the validator’s automatic sample selection seems off: it picked sales order `740506` even though there are apparently no `BILLED_AS` edges for it after the rebuild. Also the “first billing document” sample now may not have incoming `BILLED_AS`. Next I’ll (1) verify which sales orders actually have `BILLED_AS` after the rebuild, (2) update the validator’s sample selection to choose a sales order and billing doc that truly participate in the relevant edges, then (3) rerun the validator.

The join-based `BILLED_AS` edge build now returns zero because the dataset shows the “referenceSdDocument” in `billing_document_items` often points to a *delivery* (8xxxxxxx), not a sales order (74xxxx). My current ingestion never resolves that ambiguity, so the canonical join key is wrong. Next I’ll update ingestion to canonicalize `billing_document_items.referenceSdDocument/referenceSdDocumentItem` by looking up matching `outbound_delivery_items` when the reference looks like a delivery ID, then rebuild `graph_edges` and rerun the validator.

Canonicalization didn’t update because the lookup failed: `billing_document_items.referenceSdDocumentItem` is normalized to `"10"`, but `outbound_delivery_items.deliveryDocumentItem` is stored as `"000010"`. My lookup used the normalized `"10"` only, so it found no matching outbound delivery items. Next I’ll patch canonicalization to try common zero-padded variants (e.g. `zfill(6)`) when matching `OutboundDeliveryItem.item`, then rerun ingestion + edge rebuild and validate again.

Added backend debug/test utilities to validate ingestion + graph relationships (no APIs).

### New files
- `backend/app/ingestion/validate.py`
  - CLI tool that prints:
    1. A sample sales order bundle: items, deliveries, billing documents, accounting entries
    2. Trace from a given billing document: back to sales order, forward to accounting document
    3. `graph_edges` neighborhood: pick one sales order and print all connected nodes (by BFS over `graph_edges`)
    4. Counts:
       - total rows per table
       - total `graph_edges` per `edge_type`
- `scripts/validate_ingestion.ps1`
  - Convenience PowerShell wrapper around the Python CLI

### Also fixed for correctness (so validation reflects “no major linkage broken”)
- Updated `backend/app/ingestion/ingest_jsonl.py` to canonicalize the `billing_document_items.referenceSdDocument` ambiguity:
  - when it looks like a delivery id, it resolves to the corresponding sales order via `outbound_delivery_items`
- Updated `backend/app/ingestion/graph_builder.py` to build `BILLED_AS` (and `FULFILLED_BY`) using relational join logic so `graph_edges` doesn’t point to non-existent relational nodes.

### How to run
1. Ensure ingestion has been run with edges built:
   - `powershell .\scripts\run_ingestion.ps1 -DatasetRoot <path-to-sap-o2c-data> -BuildEdges`
2. Run validation:
   - `powershell .\scripts\validate_ingestion.ps1`
   - Optional: `-SalesOrder 740509 -BillingDocument 90504204 -GraphDepth 2`

---

**User**

@o2c_build_spec.md This is a .md version of the file may help you

---

**Cursor**

I’ll open `o2c_build_spec.md` now and extract the exact canonical table/field and edge-join definitions. Then I’ll confirm our ingestion + `build_graph_edges()` logic matches the spec (especially the ambiguous `billing_document_items` → sales order link).

Read `o2c_build_spec.md`—it matches what we previously extracted from the DOCX, and it clarifies the two key parts that affect ingestion + `graph_edges`:

- The `billing_document_items.referenceSdDocument` ambiguity (Hazard 2): when it looks like a delivery id (the `8xxxxxxx` range), we should resolve it via `outbound_delivery_items` using `(referenceSdDocument, referenceSdDocumentItem)`.
- `BILLED_AS` edge join rule: build it from `(refSdDoc, refSdDocItem)` matching across tables (billing items ↔ sales order items).

Good news: our ingestion now performs exactly that canonicalization step, and `build_graph_edges()` uses the canonicalized `(referenceSdDocument, referenceSdDocumentItem)` to generate `BILLED_AS`.

If you want, next we can align naming conventions for `graph_edges.source_type/target_type` to whatever your query planner will expect (the spec uses node types like `Customer`, `Product`, `AccountingDocument`, while we currently store snake-case like `customer`, `accounting_document`). Should we adjust that now for consistency with the planner’s enums/stages?

---

**User**

Specifically validate tricky relationships:

1. billing_document_items.referenceSdDocument mapping:
   - ensure correct join with sales_order_items
   - handle delivery references (8xxxxxx range)

2. cancellation handling:
   - ensure no duplicate billing documents
   - verify CANCELLED_BY edges

3. journal vs payments duplication:
   - ensure no double counting

Add debug logs or assertions to verify correctness.

---

**Cursor**

I’ll extend the existing `backend/app/ingestion/validate.py` to add targeted “deep checks” for the three tricky areas you listed. Then I’ll rerun the validator so it prints explicit counts and either assertions or detailed mismatch samples when something is off.

The validator failed inside the new deep check due to an incorrect SQLAlchemy cast (`func.numeric()` isn’t a SQL type). Next I’ll patch `check_billing_reference_mapping()` to use a proper `cast(..., Integer)` for the `>= 80000000` “delivery-like” detection, then rerun the validator to ensure all deep checks complete.

Cast expressions don’t support `.ge()` in SQLAlchemy; we should use the standard comparison operator (`>=`) instead. Next I’ll patch those two “delivery-like” filters and rerun the validator to ensure all deep checks complete successfully.

Deep checks 1 and 2 passed (billing mapping + cancellation edges are consistent). The validator crashed on deep check 3 because `PaymentsAccountsReceivable` wasn’t imported. Next I’ll add the missing import and rerun the validator so all three deep checks complete cleanly.

Added targeted “deep checks” + assertions to validate the tricky relationships you called out.

### Updated
- `backend/app/ingestion/validate.py`
  - **Deep check 1: billing_document_items.referenceSdDocument mapping**
    - Asserts every `BillingDocumentItem` row that has a non-null `(referenceSdDocument, referenceSdDocumentItem)` joins to `SalesOrderItem` on `(salesOrder, item)`.
    - Asserts there are **zero** remaining “delivery-like” references (`referenceSdDocument >= 80000000`) after canonicalization.
    - On failure, prints up to 10 unmapped examples.
  - **Deep check 2: cancellation handling**
    - Validates `billing_document_cancellations` is a proper subset of `billing_document_headers` (`isCancelled=true`).
    - Asserts `graph_edges` has **no duplicate** `CANCELLED_BY` edges per billing doc.
    - Asserts `graph_edges` covers exactly the expected cancelled docs (no missing, no extra).
  - **Deep check 3: journal vs payments duplication**
    - Asserts `graph_edges` `CLEARED_BY` edges match **exactly** the distinct `(accountingDocument, clearingAccountingDocument)` pairs from `journal_entry_items_ar`.
    - Checks overlap between `journal_entry_items_ar` and `payments_accounts_receivable` on the shared PK and prints mismatches (asserts mismatch count is 0 in the current DB).

### How to run
From the repo root:
- `powershell .\scripts\validate_ingestion.ps1`

### Current result (on the existing ingested SQLite DB)
All three deep checks passed with assertions:
- billing→sales-order join coverage: **245/245 OK**
- delivery-like billing references after canonicalization: **0**
- cancellations: **80** cancelled docs, **80** `CANCELLED_BY` edges, no duplicates
- journal vs payments: `CLEARED_BY` edges match journal clearing pairs exactly (**120**), mismatches **0**

---

**User**

Implement the query execution layer.

We already have:
- relational database
- graph_edges
- ingestion working

Now build:

1. Query dispatcher:
   - takes structured JSON (query plan)
   - routes to correct handler

2. Implement handlers:

A. trace_flow:
- use graph traversal (graph_edges)
- return full path of nodes + edges

B. top_products_by_billing:
- aggregate billing_document_items by product
- return top N

C. find_broken_flows:
- detect:
  - billing without delivery
  - delivery without sales order
  - missing accounting entries

D. lookup_entity:
- fetch entity + related data

3. Add validation layer:
- validate JSON using Pydantic
- reject invalid queries

Do NOT integrate LLM yet — assume JSON input.

---

**Cursor**

I’m going to implement the query execution layer next, but first I need to extend a few ORM models + ingestion mappings so queries like `top_products_by_billing` and `find_broken_flows` can filter by `company_code`, `fiscal_year`, and `date` and also compute the `amount_mismatch` check. After that, I’ll add the pydantic-validated dispatcher + handlers (no APIs).

Models + ingestion mappings are updated to include the fields we need for filtering and amount-mismatch checks. Next I’ll rebuild the SQLite schema (by recreating `data/app.db`) and rerun ingestion + `build_graph_edges()` so the new columns are populated. Then I’ll implement the query dispatcher + handlers with pydantic validation and run a small smoke test query end-to-end.

Ingestion failed because `init_db()` wasn’t called after we deleted `data/app.db`, so the new tables weren’t created before upserts. I’ll fix this by updating the ingestion CLI to call `init_db()` at startup, then rerun ingestion + edge build cleanly. First I’ll quickly check whether the background ingestion process is still running.

I’m going to fix the ingestion CLI so it always calls `init_db()` before inserting anything (this is required now that we changed models/columns). Then I’ll reset the SQLite DB and rerun ingestion + edge build against the dataset in `sap-order-to-cash-dataset/…` so the new columns are populated before we build the query execution layer on top.

Now I’ll implement the query execution layer under `backend/app/query/`:
- Pydantic schemas for the query-plan JSON with strict validation (`extra="forbid"`), plus a “reject invalid queries” path.
- A dispatcher that routes by `intent`.
- Handler implementations for `trace_flow`, `top_products_by_billing`, `find_broken_flows`, and `lookup_entity`, using `graph_edges` + relational tables.
No API integration yet; everything is callable as pure backend functions.

Next I’ll do a quick end-to-end smoke test of the new query execution layer by calling `execute_query_plan()` directly (no APIs). I’ll run one `trace_flow`, one `top_products_by_billing`, one `find_broken_flows`, and one `lookup_entity` query using the already-ingested SQLite DB to ensure the dispatcher, pydantic validation, and SQL/graph handlers all work together.

Now that the query execution layer is in place and validated with smoke tests, I’ll quickly rerun the deep ingestion/graph validator to ensure nothing we changed to models/ingestion/query code accidentally broke the linkage invariants. After that, I’ll summarize what was added and how to call the query engine with JSON plans.

Implemented the **query execution layer** (backend-only, no API/LNN integration) with strict Pydantic validation, a dispatcher, and handlers for all requested intents.

### What I added

1. **Query dispatcher + execution entrypoint**
- `backend/app/query/execute.py`
  - `execute_query_plan(session: Session, query_plan_json: Any) -> dict`
  - Validates the incoming JSON plan with Pydantic.
  - On validation failure (or unknown intent) returns a `{"intent":"reject", ...}` payload.

2. **Pydantic validation (reject invalid queries)**
- `backend/app/query/plans.py`
  - Implements plan models for:
    - `trace_flow`
    - `top_products_by_billing`
    - `find_broken_flows`
    - `lookup_entity`
    - `reject`
  - Uses `extra="forbid"` to enforce `additionalProperties: false`-style behavior.

3. **Handlers**
- `backend/app/query/handlers.py`
  - `trace_flow`
    - Traverses using `graph_edges`:
      - `FULFILLED_BY` (sales_order -> delivery)
      - `BILLED_AS` (sales_order -> billing_document)
      - `POSTS_TO` (billing_document -> accounting_document)
      - `CLEARED_BY` (accounting_document -> accounting_document “payment”)
      - `CANCELLED_BY` included only when `filters.include_cancelled=true`
    - Optionally includes `schedule_lines` from `sales_order_schedule_lines`.
    - Returns `{ path: { nodes: [...], edges: [...] } }`.

  - `top_products_by_billing`
    - Aggregates `billing_document_items.netAmount` by product (via `billing_document_items.material`)
    - `invoice_count` = distinct billing documents count
    - `quantity` = **line count proxy** (`COUNT(*)`) because the current relational model doesn’t store billing quantity.
    - Supports filters: `date_from/date_to`, `company_code`, `customer_id`, `exclude_cancelled`, `product_group`.

  - `find_broken_flows`
    - Detects each requested `break_type` using graph/relational checks, including:
      - `billing_without_delivery`
      - `delivery_without_sales_order`
      - `billing_without_journal_entry`
      - `journal_entry_without_clearing`
      - `cancelled_without_accounting_doc`
      - `active_txn_on_blocked_partner`
      - `amount_mismatch_billing_vs_journal` (compares `billing_document_headers.totalNetAmount` vs journal sum)

  - `lookup_entity`
    - Fetches the entity row (customer/product/plant/sales_order/delivery/billing_document)
    - Expands `include_related` using relational tables (addresses, items, schedule_lines, billing_documents, journal_entries, payments, cancellations, product_descriptions, storage_locations, etc.)

### Small schema support update (for query filters + mismatch)
To support query filtering and `amount_mismatch_billing_vs_journal`, I extended/ingested:
- `billing_document_headers`: `companyCode`, `billingDocumentDate`, `fiscalYear`, `totalNetAmount`
- `journal_entry_items_ar`: `companyCode`, `fiscalYear`, `postingDate`, `amountInCompanyCodeCurrency`, `glAccount`

(These are already populated because we re-ran ingestion when the schema changed.)

### How to call it (example)
```python
from app.db.session import SessionLocal, init_db
from app.query.execute import execute_query_plan

init_db()

plan = {
  "intent": "trace_flow",
  "entity_type": "sales_order",
  "entity_id": "740509",
  "stages": ["sales_order","schedule_lines","delivery","billing","journal_entry","payment"],
  "filters": {"company_code": None, "fiscal_year": None, "include_cancelled": False}
}

with SessionLocal() as s:
    result = execute_query_plan(s, plan)
    print(result)
```

If you want, next I can add a small **CLI script** to run these query plans from the command line (still no APIs) so you can validate outputs quickly.

---

**User**

Create an LLM integration module.

Requirements:
- file: backend/app/llm/planner.py

Implement:
1. function: generate_query_plan(user_input: str) -> dict
2. call an LLM API (use Gemini or Groq free tier)
3. send:
   - system prompt (from spec)
   - user query

4. ensure:
   - response is raw JSON (no markdown)
   - parse JSON safely
   - handle invalid JSON

5. return parsed query plan

---

**Cursor**

I’ll implement `backend/app/llm/planner.py` next. First I’ll extract the “LLM System Prompt” text from `o2c_build_spec.md` so we can send it to the LLM verbatim on every request. Then I’ll wire `generate_query_plan()` to call an LLM provider (Gemini or Groq via free-tier API keys), parse raw JSON safely, and return a validated plan dict.

I’ll now run a quick compile check for the new `backend/app/llm/planner.py` module and ensure it can load the system prompt from `o2c_build_spec.md` without errors.

Implemented the LLM integration module as requested.

### Added
- `backend/app/llm/planner.py`

### What it does
- `generate_query_plan(user_input: str) -> dict`
  1. Loads the **exact** system prompt text from `o2c_build_spec.md` (from the `### 3.5 LLM System Prompt` code fence).
  2. Calls an LLM provider:
     - Uses **Groq** if `GROQ_API_KEY` is set
     - Otherwise uses **Gemini** if `GEMINI_API_KEY` is set
  3. Extracts and parses the model response as **raw JSON** safely:
     - strips common ``` fences if present
     - tries `json.loads` directly
     - if that fails, extracts the substring from the first `{` to the last `}`
  4. On any failure (API error / invalid JSON), returns a `{"intent":"reject", ...}` plan.

### Environment variables
- Groq:
  - `GROQ_API_KEY` (required)
  - optional `GROQ_MODEL` (default: `llama3-8b-8192`)
- Gemini:
  - `GEMINI_API_KEY` (required)
  - optional `GEMINI_MODEL` (default: `gemini-1.5-flash`)

If you want, next we can add a tiny CLI like `scripts/run_planner.ps1` to manually test `generate_query_plan()` with a few example prompts—still without integrating into any HTTP API.

---

**User**

Use this as the EXACT system prompt (do not modify):
You are a query planner for an Order-to-Cash (O2C) data system. Your only job is to convert
natural language questions into a structured JSON query plan. You do not answer questions
directly. You do not write SQL. You do not explain your reasoning. You output JSON only.

────────────────────────────────────────────
OUTPUT CONTRACT
────────────────────────────────────────────
Your entire response must be a single, valid JSON object.
- No markdown. No code fences. No explanation text before or after.
- No keys outside the schema. No null placeholders for required fields.
- If you are not certain of a value, use the reject intent.

────────────────────────────────────────────
AVAILABLE INTENTS — choose exactly one per response
────────────────────────────────────────────
  trace_flow              — follow a document/entity through the O2C pipeline
  top_products_by_billing — rank products by billed amount, count, or quantity
  find_broken_flows       — surface data quality issues and missing links
  lookup_entity           — fetch a single entity record with optional related data
  reject                  — mutation request / ambiguous / out of scope / multiple intents

────────────────────────────────────────────
FIELD RULES
────────────────────────────────────────────
  entity_id:  output exactly as given. If user gives a name not an ID → reject(ambiguous_entity).
  dates:      ISO-8601 (YYYY-MM-DD). Resolve relative dates. If year unknown → reject.
  null:       only for optional filter fields not specified by the user.
  filters:    always include the filters object even if all values are null.
  include_cancelled / exclude_cancelled: default false; set true only if user says so.

────────────────────────────────────────────
DECISION RULES
────────────────────────────────────────────
  Two questions in one message → reject(multiple_intents_detected).
  Vague request with no ID or scope → reject(missing_required_parameter).
  Mutation verb (delete/update/create/cancel/reverse/post) → reject(unsupported_operation).
  Schema or system design question → reject(out_of_scope).
  Customer name instead of ID → reject(ambiguous_entity).

────────────────────────────────────────────
NEVER
────────────────────────────────────────────
  Write SQL, SOQL, OData, or any query language fragment.
  Include prose, chain-of-thought, or commentary in your response.
  Invent entity IDs, product names, or dates not in the user message.
  Add keys not in the schema for the chosen intent.
  Return a partial JSON object.

────────────────────────────────────────────
EXAMPLES (user → JSON, no explanation)
────────────────────────────────────────────
"Show order 740506"
→ {"intent":"lookup_entity","entity_type":"sales_order","entity_id":"740506","include_related":["items","schedule_lines","billing_documents"]}

"Delete invoices for customer X"
→ {"intent":"reject","reason":"unsupported_operation","clarification_needed":"This system is read-only. Mutations must be made in the source ERP system."}

"Show me the orders"
→ {"intent":"reject","reason":"missing_required_parameter","clarification_needed":"Please provide a sales order ID, customer ID, or date range."}

---

**Cursor**

I’ll update `backend/app/llm/planner.py` so it uses the exact system prompt text you provided (hardcoded verbatim, no parsing from the markdown file). Then I’ll run a quick sanity check that the function returns the prompt and that JSON parsing still works.

I’ll now modify `backend/app/llm/planner.py` so `_load_system_prompt()` returns the exact verbatim system prompt string you provided (hardcoded), and I’ll stop reading/parsing it from `o2c_build_spec.md`. Then I’ll run a quick unit-style check that the prompt is returned intact.

Updated `backend/app/llm/planner.py` so `_load_system_prompt()` returns the **exact** hardcoded system prompt string you provided (verbatim), instead of extracting it from `o2c_build_spec.md`.

No other behavior changed:
- `generate_query_plan(user_input: str)` still calls Groq (if `GROQ_API_KEY` is set) or Gemini (if `GEMINI_API_KEY` is set)
- response JSON is parsed safely (handles ``` fences / extracts `{...}` if needed)
- invalid JSON or provider errors return a `{"intent":"reject", ...}` plan.

---

**User**

Add a validation layer for the query plan:

- use Pydantic models
- enforce schema strictly
- reject:
  - invalid intent
  - missing required fields
  - extra fields

If invalid:
return a reject response

---

**Cursor**

I’ll strengthen the query-plan validation so it explicitly enforces strict intent + required fields + no extra keys, and it always returns a well-formed `reject` plan on any validation failure. Then I’ll hook this validation function into the existing query execution entrypoint.

Validation layer behaves as intended: invalid intent yields a `reject` plan with `out_of_scope`, and extra fields are rejected with `missing_required_parameter`. Next I’ll run a final smoke test for a valid query plan to ensure the dispatcher still executes correctly after the validation change.

Added a strict **query plan validation layer** using Pydantic, and ensured invalid plans return a `reject` response.

### What changed
- **New file:** `backend/app/query/validation.py`
  - `validate_query_plan(query_plan_json: Any) -> dict`
  - Enforces strict Pydantic schemas (`extra="forbid"` already set on the plan models)
  - On invalid input (invalid intent / missing required fields / extra fields) returns a `reject` response.

- **Updated:** `backend/app/query/plans.py`
  - Strengthened `parse_query_plan_or_reject(...)`:
    - Rejects **invalid intent** explicitly
    - Rejects **missing required fields** and **extra/unexpected fields** via Pydantic validation errors
    - Normalizes `clarification_needed` to satisfy the 10–400 char rule.

- **Updated:** `backend/app/query/execute.py`
  - Runs `validate_query_plan()` before dispatching to handlers.
  - If validation fails, it returns the reject plan immediately.

### Smoke check
- Invalid intent returns:
  - `{"intent":"reject","reason":"out_of_scope",...}`
- Extra fields are rejected with:
  - `{"intent":"reject","reason":"missing_required_parameter",...}`

Next step (only if you want): add a small CLI like `scripts/run_query_plan.ps1` to execute one plan JSON from the terminal for quick manual testing (still no HTTP APIs).

---

**User**

Integrate LLM planner into query pipeline:

Flow:
1. user input → generate_query_plan()
2. validate JSON
3. route to query handlers
4. return:
   - query plan
   - result

Ensure:
- no SQL from LLM
- only structured execution

---

**Cursor**

I’m going to wire the existing LLM planner into the query execution layer by adding a new entry function that takes raw `user_input`, calls `generate_query_plan()`, runs strict plan validation, executes the appropriate handler, and returns `{query_plan: ..., result: ...}`. No APIs yet; this stays as a backend function you can call directly.

Since no API keys are configured here, the planner correctly returned a `reject` plan, and the pipeline returned that plan plus result. Next I’ll add a tiny unit-like script/utility so you can run `execute_user_input` from terminal with clear logging; but per your instructions, still no APIs. I’ll keep it minimal.

I’ll quickly harden the small `run_planner_pipeline.ps1` helper so it passes the user input to Python safely (avoids quoting/escaping issues), then I’ll re-run a smoke call to ensure it prints a JSON `{query_plan, result}` object.

The smoke test command failed due to PowerShell not finding the relative `-File` path. Next I’ll rerun the same helper using an absolute script path, just to confirm the helper works end-to-end.

The helper script’s Python `-c` command used `\n`, which Python interprets as a line-continuation backslash and throws a syntax error. I’ll patch the script to use a single-line Python command (no `\n`), then rerun the smoke test.

Integrated the **LLM planner into the backend query pipeline** end-to-end (still no APIs), with strict validation and structured execution only.

### What I added/changed

1. **Full pipeline function (LLM -> validate -> execute)**
- `backend/app/query/execute.py`
  - Added `execute_user_input(session, user_input: str) -> dict`
  - Flow:
    1. `generate_query_plan(user_input)` (LLM)
    2. strict JSON validation (Pydantic + `extra="forbid"`)
    3. route to query handlers (`trace_flow`, `top_products_by_billing`, `find_broken_flows`, `lookup_entity`)
    4. returns:
       - `query_plan`: the validated plan dict
       - `result`: the handler output (or a reject payload)

2. **Strict validation layer**
- `backend/app/query/validation.py` (new)
- Ensures invalid plans become a `reject` response (invalid intent / missing required fields / extra fields).

3. **LLM planner system prompt**
- `backend/app/llm/planner.py`
  - `_load_system_prompt()` now returns the **exact** system prompt string you provided (hardcoded verbatim).
  - Still safely extracts/parses raw JSON (handles markdown fences, extracts `{...}` if needed).

4. **Local debug helper**
- `scripts/run_planner_pipeline.ps1` (new)
  - Runs the LLM-planner pipeline from a PowerShell prompt for manual testing.

### Usage (no API integration)
Run from repo root (after setting `GROQ_API_KEY` or `GEMINI_API_KEY`):
- `powershell .\scripts\run_planner_pipeline.ps1 -UserInput "Show order 740506"`

It prints:
- the validated `query_plan`
- the structured `result`

### “No SQL from LLM” guarantee
The LLM output is treated as **data only** (validated by Pydantic). Execution is exclusively through your fixed handlers using `graph_edges` + relational tables—there is no path where the LLM can provide or inject SQL.

---

**User**

Create API endpoint:

POST /query

Input:
{ "query": "user text" }

Flow:
- call LLM planner
- validate plan
- execute query
- return response

Output:
{
  "plan": {...},
  "result": ...
}

---

**Cursor**

I’ll add a new FastAPI router for querying (`POST /api/query` given the existing `/api` prefix), wiring it to the already-built pipeline: LLM planner → strict Pydantic plan validation → query handler execution. Then I’ll include it in the existing `api_router` and do a quick local smoke-test (with no API keys it should return a `reject` plan cleanly).

I’ll add a new FastAPI router file for the `/query` endpoint. It will accept `{ "query": "user text" }`, run the exact flow you specified (LLM planner → strict plan validation → execute query), then return `{ "plan": ..., "result": ... }`. Finally I’ll wire it into the existing `app/api/router.py` and do a local TestClient smoke test.

Next I’ll do a TestClient smoke test of `POST /api/query` with a sample user query. Since no LLM keys are configured, it should return a `reject` plan and corresponding `result`, confirming the endpoint wiring works correctly.

Added the FastAPI endpoint `POST /query` (served as `POST /api/query` because the app mounts routers under `/api`).

### Files changed / added
- **Added:** `backend/app/api/query.py`
  - Request model: `{ "query": "user text" }` (strict: `extra="forbid"`)
  - Response model: `{ "plan": {...}, "result": ... }` (strict: `extra="forbid"`)
  - Flow implemented exactly as requested:
    1. `generate_query_plan(user_input)`
    2. `validate_query_plan(...)` (strict Pydantic; invalid => `reject`)
    3. execute via `execute_query_plan(...)`
    4. return `{ plan, result }`
  - No SQL is accepted/produced by the LLM (execution is only through the structured handlers).

- **Updated:** `backend/app/api/router.py`
  - Includes `query_router` so the route is registered.

### Smoke test result
Without setting `GROQ_API_KEY` or `GEMINI_API_KEY`, the endpoint returns a `reject` plan and matching `result`, confirming the wiring/validation pipeline works end-to-end.

---

**User**

AIzaSyDJovTuEBJ_wSRD4wMPHtfdA_S24EQ--s4 This is the gemini api key use it 

---

**Cursor**

I can’t accept or store API keys from chat for direct use. For security, please set the key as an environment variable on your machine and rotate it if you already shared it.

### Set Gemini key locally
In PowerShell:
```powershell
$env:GEMINI_API_KEY = "<PASTE_YOUR_KEY_HERE>"
```

### Smoke-test the endpoint again
Then run (from repo root):
```powershell
cd backend
powershell -NoProfile -Command "Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/query -ContentType 'application/json' -Body (@{ query = 'Show order 740509' } | ConvertTo-Json)"
```

If you want, tell me whether you’re using a specific Gemini model (you can also set `GEMINI_MODEL`), and I’ll help verify the response format.

---

**User**

@backend/.env I added the api key in this file

---

**Cursor**

I’ll check `backend/.env` to confirm the key is present (and confirm the variable name), then I’ll update `backend/app/llm/planner.py` to automatically load that `.env` file at runtime using `python-dotenv`—so the LLM call works without manually setting environment variables.

I’ll patch `backend/app/llm/planner.py` to load `backend/.env` automatically via `python-dotenv` so `GEMINI_API_KEY` works. Then I’ll update `.gitignore` to avoid accidentally committing `.env` files. After that, I’ll rerun a small `POST /api/query` smoke test.

Next I’ll re-run `generate_query_plan()` and print the full returned plan (excluding any secrets). This will tell us whether the LLM call is failing (e.g., network/provider issues) or the model is returning a `reject` intent with a valid JSON payload.

Gemini calls are currently failing with HTTP 404 (“model not found”), which means the configured `gemini-1.5-flash` model name is likely deprecated/unsupported for the `v1beta` generateContent endpoint. Next I’ll harden `backend/app/llm/planner.py` to automatically retry a small list of known-good Gemini model aliases (e.g., `gemini-flash-latest`, `gemini-1.5-flash-latest`, etc.) if the first request returns 404, then re-test `generate_query_plan()`.

Gemini fallback retry worked: the planner now returns a valid structured JSON plan instead of `reject`. Next I’ll smoke-test the new API endpoint `POST /api/query` using FastAPI’s `TestClient` to ensure the full flow works: LLM planner → strict validation → handler execution → response shape `{ plan, result }`.

Loaded the Gemini API key from `backend/.env` and fixed the planner to work with Gemini models that may have changed (the earlier `gemini-1.5-flash` request was returning HTTP 404).

### Changes
- `backend/app/llm/planner.py`
  - Now calls `load_dotenv(backend/.env)` automatically.
  - If the requested Gemini model returns 404, it retries a fallback list (e.g. `gemini-flash-latest`, `gemini-1.5-flash-latest`, `gemini-2.0-flash`, etc.).
  - Still enforces “raw JSON only” parsing and returns a `reject` plan on invalid JSON.

- `.gitignore`
  - Added `.env` and `backend/.env` so you don’t accidentally commit secrets.

### Verified
With your `backend/.env` in place, `POST /api/query` now returns a real `plan` (not a `reject` due to missing/invalid Gemini config), and `result` matches the handler output.

---

**User**

Test graph traversal:

1. Pick a real sales order ID
2. Run trace_flow
3. Print:
   - nodes visited
   - edges traversed

Verify:
- path includes delivery
- path includes billing
- path includes accounting

Also:
- ensure no duplicate nodes
- ensure traversal stops correctly

---

**Cursor**

I’ll run an automated validation of `trace_flow` for a known real sales order (`740509`) using the already-ingested `graph_edges`. The output will list all nodes visited and edges traversed, then I’ll assert that the path includes `delivery`, `billing_document`, and `accounting_document`, with no duplicate nodes.

Validated `trace_flow` graph traversal using real sales order `740509`.

Results:
- Nodes visited: `5` (unique: `5`)
- Node types: `['accounting_document', 'billing_document', 'delivery', 'sales_order', 'schedule_line']`
- Edges traversed: `4`
- Edge types: `['BILLED_AS', 'CLEARED_BY', 'FULFILLED_BY', 'POSTS_TO']`

Verification checks:
- Path includes delivery: ✅
- Path includes billing: ✅
- Path includes accounting: ✅
- No duplicate nodes: ✅ (asserted `len(nodes) == len(unique_nodes)`)
- Traversal stops correctly for requested stages:
  - No cancellation nodes appeared (since `stages` did not include `cancellation`) ✅

---

**User**

Add test cases for the query system.

Test:

1. trace_flow
Input: "Show full journey for sales order 740509"
→ should return graph path

2. top_products_by_billing
Input: "Top 5 products by revenue"
→ should return sorted list

3. find_broken_flows
Input: "Show broken flows"
→ should return anomalies

4. lookup_entity
Input: "Show customer 320000083"
→ should return details

5. guardrails
Input: "Write me a poem"
→ should return reject

Ensure:
- outputs are correct
- no crashes
- no empty results unless expected

---

**Cursor**

I’ll add a small `unittest` test suite under `backend/tests/` that validates the query handlers and the strict plan validation. The tests will:
- Use deterministic plans (no LLM calls) to ensure stable correctness.
- Optionally (only if you set an env flag like `RUN_LLM_TESTS=1` and have API keys) run a few end-to-end checks using your natural-language inputs.

Now I’ll create the test files and a simple `scripts/run_tests.ps1` runner.

Tests failed due to a SQLAlchemy misuse in the helper functions (`func.count().select_from(...)`). Next I’ll patch the test helpers to use proper `select(func.count()).select_from(...)` queries, rerun the test suite, and then address any remaining assertion issues (especially around the trace-flow “stop correctly” guard).

Unit tests now pass. Next I’ll extend the optional LLM integration test (currently only covers trace_flow + guardrails) to also cover the other user-described natural-language cases: `top_products_by_billing`, `find_broken_flows`, and `lookup_entity`. These will only run when `RUN_LLM_TESTS=1` to avoid flakiness without API keys.

Added a test suite for the query system.

### New files
- `backend/tests/test_query_system.py`
  - Deterministic (no LLM) tests that directly execute **query plans** against the ingested SQLite DB:
    1. `trace_flow` (verifies delivery + billing + accounting appear; no duplicate nodes)
    2. `top_products_by_billing` (verifies sorted, top N length)
    3. `find_broken_flows` (verifies issues list + non-empty)
    4. `lookup_entity` (verifies customer details + addresses present)
    5. Guardrails via strict validation (invalid intent => `reject`)
  - Optional LLM-dependent test (runs only if you set `RUN_LLM_TESTS=1`):
    - Uses the natural-language prompts you listed for `trace_flow`, `top_products_by_billing`, `find_broken_flows`, `lookup_entity`, and guardrails (“poem” => `reject`).

- `scripts/run_tests.ps1`
  - Runs: `python -m unittest discover -s tests -p test_*.py`

### Run
From repo root:
- `powershell .\scripts\run_tests.ps1`

To enable the optional LLM tests:
- `set RUN_LLM_TESTS=1` (PowerShell: `$env:RUN_LLM_TESTS="1"`) before running the tests.

---

**User**

Build graph visualization UI using Cytoscape.js.

Requirements:
- render nodes + edges from backend
- click node → show metadata panel
- expand neighbors dynamically
- highlight nodes from query results

Layout:
Left: graph
Right: chat panel

Keep it clean and simple.

Create a React component for graph visualization using Cytoscape.js.

Requirements:
- render nodes and edges
- accept props: nodes, edges
- basic layout (grid or breadthfirst)
- zoom and pan enabled

Keep it simple and functional.

