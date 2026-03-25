#!/usr/bin/env python3
"""
Walk a dataset root and stream every folder that contains *.jsonl files.
Merges top-level keys across all JSONL in that folder (missing keys across
rows/files are handled via set union). Keeps only a few sample rows in memory.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKIP_DIR_NAMES = frozenset({".git", "__pycache__", ".venv", "node_modules"})


def iter_jsonl_dicts(path: Path):
    """Yield dict objects from a JSONL file, one line at a time."""
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                print(f"WARN: skip invalid JSON {path}:{line_no}", file=sys.stderr)
                continue
            if isinstance(obj, dict):
                yield obj
            else:
                print(
                    f"WARN: skip non-object line {path}:{line_no} ({type(obj).__name__})",
                    file=sys.stderr,
                )


def summarize_folder_streaming(folder: Path, sample_count: int) -> tuple[set[str], list[dict]]:
    """
    Single pass per file: always update keys; collect samples until sample_count.
    After samples are full, still scan remaining lines/files for keys only.
    """
    keys: set[str] = set()
    samples: list[dict] = []
    jsonl_files = sorted(folder.glob("*.jsonl"))
    for jf in jsonl_files:
        for obj in iter_jsonl_dicts(jf):
            keys.update(obj.keys())
            if len(samples) < sample_count:
                samples.append(obj)
    return keys, samples


def format_record(rec: dict) -> str:
    return json.dumps(rec, ensure_ascii=False, indent=2, sort_keys=True)


def table_label(root: Path, folder: Path) -> str:
    rel = folder.resolve().relative_to(root.resolve())
    if rel == Path("."):
        return root.name
    return rel.as_posix()


def discover_jsonl_directories(root: Path) -> list[Path]:
    """Each directory that directly contains at least one .jsonl file becomes one table."""
    root = root.resolve()
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in SKIP_DIR_NAMES and not d.startswith(".")
        )
        if any(name.endswith(".jsonl") for name in filenames):
            found.append(Path(dirpath))
    return sorted(found, key=lambda p: table_label(root, p).lower())


def write_report(
    root: Path,
    out_path: Path,
    sample_count: int,
) -> None:
    table_dirs = discover_jsonl_directories(root)
    lines: list[str] = []

    if not table_dirs:
        lines.append(f"No folders with *.jsonl found under {root.resolve()}")
    else:
        for folder in table_dirs:
            keys, samples = summarize_folder_streaming(folder, sample_count)
            label = table_label(root, folder)
            col_list = ", ".join(sorted(keys)) if keys else "(no dict keys found)"

            lines.append("")
            lines.append(f"Table: {label}")
            lines.append(f"Columns: {col_list}")
            lines.append("Sample rows:")
            if not samples:
                lines.append("  (no valid dict rows)")
            else:
                for i, row in enumerate(samples, 1):
                    lines.append(f"  --- row {i} ---")
                    for block_line in format_record(row).splitlines():
                        lines.append(f"  {block_line}")
            lines.append("")

    text = "\n".join(lines).strip() + "\n"
    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote {out_path.resolve()}")


def main() -> None:
    p = argparse.ArgumentParser(description="Summarize JSONL datasets by subfolder.")
    p.add_argument(
        "root",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Dataset root (walks nested folders for *.jsonl; default: .)",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("jsonl_dataset_summary.txt"),
        help="Output text file (default: jsonl_dataset_summary.txt)",
    )
    p.add_argument(
        "-n",
        "--samples",
        type=int,
        default=4,
        help="Number of sample rows per folder (default: 4, use 3–5)",
    )
    args = p.parse_args()
    n = max(3, min(5, args.samples))
    if args.samples != n:
        print(f"Note: clamping --samples to {n} (allowed range 3–5)", file=sys.stderr)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"Error: not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    write_report(root, args.output.resolve(), n)


if __name__ == "__main__":
    main()
