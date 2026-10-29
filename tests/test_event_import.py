import copy
import unittest
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.main import Base, Event, EventEnrichmentVersion, EventFactVersion
from backend.app.event_ingest import import_batch, upsert_event


def record(url="https://riscv.org/events/engineering", title="RISC-V 技术研讨会"):
    start = datetime.now(UTC) + timedelta(days=2)
    facts = dict(title=title, start_at=start.isoformat(), end_at=(start + timedelta(hours=4)).isoformat(),
                 timezone="Asia/Shanghai", city="深圳", venue="福田会展中心", organizer="技术社区",
                 canonical_url=url, technical_signal="RISC-V 编译器与系统软件")
    evidence = {key: {"source_url": url, "excerpt": str(value), "captured_at": datetime.now(UTC).isoformat()}
                for key, value in facts.items() if value}
    return {"facts": facts, "evidence": evidence,
            "enrichment": {"summary": "编译器与系统软件的技术分享", "takeaways": ["LLVM 工程实践"],
                           "why_worth": "有源码与部署案例", "relevance": "高含金量"},
            "details": {"highlights": ["指令集扩展"], "price_text": "官方未公开",
                        "transport": {"estimated": True, "plan": "地铁至会展中心"}},
            "source_name": "每日活动搜寻"}


def batch(items):
    return {"schema_version": 1, "producer": "gba-tech-events", "generated_at": datetime.now(UTC).isoformat(), "events": items}


class ImportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_import_replay_is_idempotent(self):
        payload = batch([record()])
        async with self.sessions() as session:
            first = await import_batch(session, payload)
            await session.commit()
            second = await import_batch(session, payload)
            self.assertEqual(first["inserted"], 1)
            self.assertTrue(second["replayed"])
            self.assertEqual(await session.scalar(select(func.count()).select_from(Event)), 1)

    async def test_cross_source_merge_retains_detail_and_primary_facts(self):
        first = record()
        second = copy.deepcopy(first)
        second["facts"]["canonical_url"] = "https://luma.com/engineering"
        second["evidence"] = {key: {**value, "source_url": "https://luma.com/engineering"}
                              for key, value in second["evidence"].items()}
        second["facts"]["venue"] = "待核实的另一个会场"
        async with self.sessions() as session:
            await import_batch(session, batch([first]))
            result = await import_batch(session, batch([second]))
            self.assertEqual(result["merged"], 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Event)), 1)
            event = await session.scalar(select(Event))
            fact = await session.get(EventFactVersion, event.current_fact_version_id)
            self.assertEqual(fact.venue, "福田会展中心")
            from backend.app.main import EventSupplement
            supplement = await session.get(EventSupplement, event.event_key)
            self.assertEqual(len(supplement.document["sources"]), 2)
            self.assertIn("venue", {entry["field"] for entry in supplement.document["conflicts"]})

    async def test_same_title_in_different_city_is_not_merged(self):
        first = record()
        second = copy.deepcopy(first)
        second["facts"].update(city="广州", canonical_url="https://luma.com/guangzhou")
        for entry in second["evidence"].values():
            entry["source_url"] = "https://luma.com/guangzhou"
        async with self.sessions() as session:
            result = await import_batch(session, batch([first, second]))
            self.assertEqual(result["inserted"], 2)

    async def test_missing_evidence_is_rejected_without_losing_valid_items(self):
        bad = record("https://luma.com/bad", "无证据的讲座")
        bad["evidence"].pop("venue")
        async with self.sessions() as session:
            result = await import_batch(session, batch([bad, record()]))
            self.assertEqual(result["rejected"], 1)
            self.assertEqual(result["inserted"], 1)
            self.assertIn("MISSING_EVIDENCE:venue", result["errors"][0]["reasons"])

    async def test_network_update_keeps_imported_enrichment(self):
        item = record()
        async with self.sessions() as session:
            await import_batch(session, batch([item]))
            fact = {**item["facts"], "start_at": datetime.fromisoformat(item["facts"]["start_at"]),
                    "end_at": datetime.fromisoformat(item["facts"]["end_at"])}
            await upsert_event(session, fact, {"summary": "网络通用摘要"}, item["evidence"],
                               source_name="普通爬虫", producer="network_collector")
            event = await session.scalar(select(Event))
            enrichment = await session.get(EventEnrichmentVersion, event.current_enrichment_version_id)
            self.assertEqual(enrichment.summary, item["enrichment"]["summary"])

    async def test_ongoing_multiday_event_is_publishable(self):
        item = record()
        item["facts"]["start_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        item["facts"]["end_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        item["details"]["registration_status"] = "open"
        async with self.sessions() as session:
            result = await import_batch(session, batch([item]))
            self.assertEqual(result["inserted"], 1)

    async def test_date_precision_never_claims_midnight_is_actual_time(self):
        item = record()
        item["facts"].pop("start_at")
        item["facts"].pop("end_at")
        item["facts"]["start_date"] = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
        item["facts"]["time_precision"] = "date"
        item["evidence"]["start_at"]["excerpt"] = item["facts"]["start_date"]
        async with self.sessions() as session:
            result = await import_batch(session, batch([item]))
            self.assertEqual(result["inserted"], 1)
            from backend.app.main import EventSupplement
            detail = await session.scalar(select(EventSupplement))
            self.assertEqual(detail.document["details"]["time_precision"], "date")

    async def test_private_links_and_empty_excerpts_are_not_evidence(self):
        item = record()
        item["evidence"]["venue"].update(source_url="http://127.0.0.1/internal", excerpt="")
        async with self.sessions() as session:
            result = await import_batch(session, batch([item]))
            self.assertEqual(result["rejected"], 1)

    async def test_reused_url_keeps_different_occurrences(self):
        first = record()
        second = copy.deepcopy(first)
        second["facts"]["start_at"] = (datetime.fromisoformat(first["facts"]["start_at"]) + timedelta(days=3)).isoformat()
        second["facts"]["end_at"] = (datetime.fromisoformat(first["facts"]["end_at"]) + timedelta(days=3)).isoformat()
        async with self.sessions() as session:
            result = await import_batch(session, batch([first, second]))
            self.assertEqual(result["inserted"], 2)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Event)), 2)

    async def test_invalid_timestamp_does_not_abort_batch(self):
        bad = record("https://luma.com/bad-time")
        bad["evidence"]["venue"]["captured_at"] = None
        async with self.sessions() as session:
            result = await import_batch(session, batch([bad, record()]))
            self.assertEqual(result["rejected"], 1)
            self.assertEqual(result["inserted"], 1)

    async def test_older_detail_does_not_replace_newer_summary(self):
        first = record()
        older = copy.deepcopy(first)
        older["enrichment"]["summary"] = "旧摘要"
        for entry in older["evidence"].values():
            entry["captured_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        async with self.sessions() as session:
            await import_batch(session, batch([first]))
            await import_batch(session, batch([older]))
            event = await session.scalar(select(Event))
            enrichment = await session.get(EventEnrichmentVersion, event.current_enrichment_version_id)
            self.assertEqual(enrichment.summary, first["enrichment"]["summary"])

    async def test_enrichment_bad_type_is_isolated(self):
        bad = record("https://luma.com/wrong-enrichment")
        bad["enrichment"]["commute_minutes"] = {"oops": 1}
        async with self.sessions() as session:
            report = await import_batch(session, batch([bad, record()]))
            self.assertEqual(report["rejected"], 1)
            self.assertEqual(report["inserted"], 1)

    async def test_date_to_minute_upgrade_merges_same_source(self):
        exact = record()
        date_only = copy.deepcopy(exact)
        start = datetime.fromisoformat(exact["facts"]["start_at"]).astimezone(ZoneInfo("Asia/Shanghai"))
        date_only["facts"].pop("start_at")
        date_only["facts"].pop("end_at")
        date_only["facts"].update(time_precision="date", start_date=start.date().isoformat())
        async with self.sessions() as session:
            await import_batch(session, batch([date_only]))
            for entry in exact["evidence"].values():
                entry["captured_at"] = datetime.now(UTC).isoformat()
            report = await import_batch(session, batch([exact]))
            self.assertEqual(report["merged"], 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Event)), 1)
            from backend.app.main import EventSupplement
            supplement = await session.scalar(select(EventSupplement))
            self.assertEqual(supplement.document["details"]["time_precision"], "minute")
            self.assertNotIn("end_date", supplement.document["details"])

    async def test_end_time_must_have_evidence(self):
        item = record()
        item["evidence"].pop("end_at")
        async with self.sessions() as session:
            result = await import_batch(session, batch([item]))
            self.assertEqual(result["rejected"], 1)

    async def test_rollback_leaves_no_events(self):
        async with self.sessions() as session:
            await import_batch(session, batch([record()]))
            await session.rollback()
        async with self.sessions() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Event)), 0)

    async def test_inbox_new_file_after_two_hundred_replays(self):
        from backend.app import import_events
        old = batch([record()])
        async with self.sessions() as session:
            await import_batch(session, old)
            await session.commit()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for index in range(200):
                (folder / f"{index:03}.json").write_text(json.dumps(old), encoding="utf8")
            (folder / "201.json").write_text(json.dumps(batch([record("https://luma.com/new", "新场次")])), encoding="utf8")
            with patch.object(import_events, "Session", self.sessions):
                reports = await import_events.consume_inbox(folder)
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0]["inserted"], 1)

    async def test_api_includes_ongoing_events_and_supplement(self):
        from backend.app import main
        item = record()
        item["facts"]["start_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        item["facts"]["end_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        async with self.sessions() as session:
            report = await import_batch(session, batch([item]))
            await session.commit()
        with patch.object(main, "Session", self.sessions):
            payload = await main.public_events(coverage_days=15)
            self.assertEqual(payload["total"], 1)
            self.assertEqual(payload["items"][0]["details"]["highlights"], ["指令集扩展"])
            self.assertEqual(payload["items"][0]["id"], report["event_keys"][0])

    async def test_network_time_upgrade_preserves_rich_data_and_syncs_precision(self):
        exact = record()
        date_only = copy.deepcopy(exact)
        start = datetime.fromisoformat(exact["facts"]["start_at"]).astimezone(ZoneInfo("Asia/Shanghai"))
        date_only["facts"].pop("start_at")
        date_only["facts"].pop("end_at")
        date_only["facts"].update(time_precision="date", start_date=start.date().isoformat())
        async with self.sessions() as session:
            await import_batch(session, batch([date_only]))
            for entry in exact["evidence"].values():
                entry["captured_at"] = datetime.now(UTC).isoformat()
            facts = {**exact["facts"], "start_at": datetime.fromisoformat(exact["facts"]["start_at"]),
                     "end_at": datetime.fromisoformat(exact["facts"]["end_at"])}
            action, key = await upsert_event(session, facts, {"summary": "普通摘要"}, exact["evidence"],
                                            source_name="爬虫", producer="network_collector")
            from backend.app.main import EventSupplement
            detail = await session.get(EventSupplement, key)
            self.assertEqual(action, "merged")
            self.assertEqual(detail.document["details"]["time_precision"], "minute")
            self.assertNotIn("end_date", detail.document["details"])
            self.assertEqual(detail.document["details"]["highlights"], ["指令集扩展"])


if __name__ == "__main__":
    unittest.main()
