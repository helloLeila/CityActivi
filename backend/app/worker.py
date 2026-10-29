from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from .main import JobRun, Session, update_job
from .import_events import consume_inbox, ensure_tables


async def worker_loop() -> None:
    await ensure_tables()
    while True:
        try:
            reports = await consume_inbox()
            for report in reports:
                print({key: report[key] for key in ("file", "inserted", "merged", "rejected", "error") if key in report}, flush=True)
        except Exception as error:
            print({"event_import_error": type(error).__name__}, flush=True)
        job_id = None
        async with Session() as session:
            job = (await session.execute(select(JobRun).where(JobRun.status == "submitted", JobRun.job_type == "scheduled_collect").order_by(JobRun.created_at).limit(1))).scalar_one_or_none()
            if job:
                job.status = "queued"
                job.updated_at = datetime.now(UTC)
                job_id = job.id
                await session.commit()
        if job_id is not None:
            await update_job(job_id)
        else:
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(worker_loop())
