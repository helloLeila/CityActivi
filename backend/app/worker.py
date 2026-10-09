from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from .main import JobRun, Session, update_job


async def worker_loop() -> None:
    while True:
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
