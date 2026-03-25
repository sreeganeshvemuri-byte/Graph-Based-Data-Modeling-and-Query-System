from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base


def _db_path() -> Path:
    """
    Resolve SQLite path and ensure parent directory exists.

    Defaults to <repo_root>/data/app.db but can be overridden with APP_DB_PATH.
    """
    db_path_env = os.environ.get("APP_DB_PATH")
    if db_path_env:
        db_path = Path(db_path_env).expanduser().resolve()
    else:
        # backend/app/db/session.py -> backend/app/db -> backend/app -> backend -> repo root
        repo_root = Path(__file__).resolve().parents[3]
        db_path = repo_root / "data" / "app.db"

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


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
