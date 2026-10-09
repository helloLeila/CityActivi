from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .main import ConfigurationVersion, JobRun, Session, get_config


async def scheduler_loop() -> None:
    while True:
        try:
            async with Session() as session:
                _, published = await get_config(session)
                schedule = published.document.get("schedule", {})
                timezone_name = schedule.get("timezone", "Asia/Shanghai")
                local_now = datetime.now(ZoneInfo(timezone_name))
                configured_time = str(schedule.get("time", "07:00"))[:5]
                delivery_key = f"scheduled_collect:{published.revision}:{local_now.date().isoformat()}"
                if local_now.strftime("%H:%M") == configured_time:
                    exists = (await session.execute(select(JobRun).where(JobRun.delivery_key == delivery_key))).scalar_one_or_none()
                    if not exists:
                        session.add(JobRun(job_type="scheduled_collect", status="submitted", delivery_key=delivery_key, progress=0, message="请求已提交", created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
                        await session.commit()
        except Exception:
            # Scheduler errors are retried on the next minute; no tight retry loop.
            pass
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(scheduler_loop())
