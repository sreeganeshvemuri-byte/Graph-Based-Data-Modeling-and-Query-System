# Graph-Based Data Modeling & Query System

This repo is a full-stack monorepo scaffold:

- Backend: FastAPI + SQLite + SQLAlchemy + Pydantic
- Frontend: React + Vite

## Backend

1. `cd backend`
2. `pip install -r requirements.txt`
3. Start: `uvicorn app.main:app --reload --port 8000`
   - Or: `powershell ..\scripts\run_backend.ps1`

Health check:

- `GET http://localhost:8000/api/health`

## Frontend

1. `cd frontend`
2. `npm install`
3. Start: `npm run dev`
   - Or: `powershell ..\scripts\run_frontend.ps1`

Frontend should be available on:

- `http://localhost:5173`

