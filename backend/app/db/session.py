from __future__ import annotations

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base


def _db_path() -> Path:
    # backend/app/db/session.py -> backend/app/db -> backend/app -> backend -> repo root
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "data" / "app.db"


DB_URL = f"sqlite:///{_db_path()}"

# SQLite needs this for multithreaded FastAPI usage.
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite://") else {}

engine = create_engine(DB_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    # Import models so Base.metadata knows about all tables.
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
