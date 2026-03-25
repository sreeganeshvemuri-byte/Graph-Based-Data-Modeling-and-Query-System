from fastapi import FastAPI

from app.api.router import api_router
from app.db.session import init_db

app = FastAPI(title="Graph-Based Data Modeling & Query System", version="0.1.0")

app.include_router(api_router, prefix="/api")


@app.on_event("startup")
def on_startup() -> None:
    init_db()

