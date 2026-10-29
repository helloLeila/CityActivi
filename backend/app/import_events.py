"""Local file/inbox bridge. Uses the same DATABASE_URL as API, worker and scheduler."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError

from .event_ingest import import_batch
from .main import Base, Session, engine

DEFAULT_INBOX = Path(__file__).resolve().parents[2] / "data" / "event-inbox"
MAX_BYTES = 2 * 1024 * 1024


def load_payload(path: Path) -> dict:
    if path.is_symlink() or path.stat().st_size > MAX_BYTES:
        raise ValueError("UNSAFE_OR_OVERSIZED_IMPORT_FILE")
    with path.open("rb") as stream:
        content = stream.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("OVERSIZED_IMPORT_FILE")
    return json.loads(content)


async def ensure_tables() -> None:
    # create_all only adds missing tables; no startup seed cleanup or live-data deletion.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def consume_inbox(directory: Path | None = None) -> list[dict]:
    directory = directory or Path(os.getenv("CITYACTIVI_EVENT_INBOX", str(DEFAULT_INBOX)))
    reports = []
    if not directory.is_dir():
        return reports
    # Replayed and invalid files do not consume the per-poll import budget.
    imported = 0
    for path in sorted(directory.glob("*.json")):
        try:
            payload = await asyncio.to_thread(load_payload, path)
            async with Session() as session:
                report = await import_batch(session, payload)
                await session.commit()
                if not report["replayed"]:
                    reports.append({"file": path.name, **report})
                    imported += 1
                    if imported >= 200:
                        break
        except (ValueError, OSError):
            # A malformed file must not stop later valid files or expose its contents.
            reports.append({"file": path.name, "error": "INVALID_IMPORT_FILE"})
    return reports


async def run(args) -> int:
    await ensure_tables()
    try:
        if args.inbox:
            reports = await consume_inbox(Path(args.inbox))
            print(json.dumps(reports, ensure_ascii=False, indent=2))
            return int(any(item.get("rejected") or item.get("error") for item in reports))
        payload = load_payload(Path(args.path))
        async with Session() as session:
            report = await import_batch(session, payload)
            if args.dry_run:
                await session.rollback()
            else:
                await session.commit()
            print(json.dumps({**report, "dry_run": args.dry_run}, ensure_ascii=False, indent=2))
            return int(report["rejected"] > 0)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--inbox", help="Consume JSON files, retaining original files and persistent receipts")
    group.add_argument("path", nargs="?", help="One schema_version=1 JSON batch")
    parser.add_argument("--dry-run", action="store_true", help="Validate and simulate merging, rolling back all event writes")
    args = parser.parse_args()
    if args.inbox and args.dry_run:
        parser.error("--dry-run requires one file")
    try:
        raise SystemExit(asyncio.run(run(args)))
    except (ValueError, OSError, SQLAlchemyError):
        parser.exit(2, "导入失败：文件格式或数据契约无效，未记录原始内容。\n")


if __name__ == "__main__":
    main()
