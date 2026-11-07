from __future__ import annotations

import argparse
from pathlib import Path

from .rag_pipeline import ingest_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest university source documents into the local semantic RAG index.")
    parser.add_argument("folder", type=Path)
    parser.add_argument("--university", required=True)
    parser.add_argument("--source-url")
    parser.add_argument("--version", default="1")
    args = parser.parse_args()
    for path in sorted(p for p in args.folder.rglob("*") if p.is_file()):
        try:
            source_id, count, changed = ingest_file(path, university=args.university, source_url=args.source_url, version=args.version)
            print(f"{path.name}: source={source_id[:12]} chunks={count} {'indexed' if changed else 'unchanged'}")
        except ValueError as exc:
            print(f"{path.name}: skipped ({exc})")


if __name__ == "__main__":
    main()
