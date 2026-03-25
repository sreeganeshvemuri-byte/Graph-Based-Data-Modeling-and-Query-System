# Graph-Based Data Modeling & Query System

This repository is a full-stack monorepo:

- **Backend:** FastAPI + SQLite + SQLAlchemy + Pydantic
- **Frontend:** React + Vite + Cytoscape

## Why the app may look "not working"

The most common issue is that the database is empty (or the `data/` directory does not exist yet), so the API has nothing to return.

This repo now auto-creates `data/` on startup, but you still need to run **ingestion + graph edge build** once before meaningful queries work.

## Quickstart (End-to-End)

### 1) Backend setup

```bash
cd backend
pip install -r requirements.txt
```

### 2) Ingest dataset and build graph edges (required)

```bash
cd backend
python -m app.ingestion.cli ../sap-order-to-cash-dataset/sap-o2c-data --build-edges --log-level INFO
```

### 3) (Optional) Configure LLM provider

If no provider key is configured, the planner intentionally returns a guarded `reject` response.

- Set `GROQ_API_KEY` (optional `GROQ_MODEL`), or
- Set `GEMINI_API_KEY` (optional `GEMINI_MODEL`)

You can place these in `backend/.env`.

### 4) Run backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Health check:

- `GET http://localhost:8000/api/health`

### 5) Run frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

- `http://localhost:5173`

---

## Minimal diagnostics checklist

1. **Backend up?** `GET /api/health` returns 200.
2. **Data loaded?** Run tests: `cd backend && pytest -q`.
3. **Graph data present?** Query endpoint should return non-empty `result.path` for trace-flow queries.
4. **LLM configured?** Without API key, only guarded reject plans are expected.

## Notes

- DB path defaults to `data/app.db` (repo root) and can be overridden with `APP_DB_PATH`.
- PowerShell helper scripts are available under `scripts/` for Windows workflows.
