from __future__ import annotations

import argparse
import logging
from pathlib import Path

from app.db.session import SessionLocal
from app.db.session import init_db
from app.ingestion.graph_builder import build_graph_edges
from app.ingestion.ingest_jsonl import ingest_jsonl_dataset


def _setup_logging(log_file: Path | None, level: str) -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest JSONL folders into the relational schema.")
    parser.add_argument("dataset_root", type=Path, help="Root directory containing JSONL folders")
    parser.add_argument("--build-edges", action="store_true", help="Rebuild graph_edges after ingestion")
    parser.add_argument("--log-level", default="INFO", help="Logging level (DEBUG/INFO/WARNING/ERROR)")
    parser.add_argument("--log-file", type=Path, default=None, help="Optional log file path")
    args = parser.parse_args()

    _setup_logging(args.log_file, args.log_level)
    log = logging.getLogger(__name__)

    dataset_root = args.dataset_root
    log.info("Starting ingestion: dataset_root=%s", dataset_root)

    init_db()

    with SessionLocal() as session:
        ingest_jsonl_dataset(session, dataset_root, truncate_graph_edges=False)
        if args.build_edges:
            log.info("Building graph edges...")
            build_graph_edges(session)

    log.info("Ingestion finished.")


if __name__ == "__main__":
    main()

