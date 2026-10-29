"""Versioned local data import and shared, conservative cross-source event merging."""
from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import re
import unicodedata
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import StatementError

from .main import (
    REQUIRED_FACTS, Event, EventEnrichmentVersion, EventFactVersion, EventImportBatch,
    EventSourceAlias, EventStatusChange, EventSupplement, EventVersion, as_utc, evaluate_publication,
)


def public_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            return False
        if host in {"localhost", "example.com", "example.net", "example.org", "test.com"} or \
                host.endswith((".local", ".localhost", ".test", ".invalid", ".example", ".example.com", ".example.net", ".example.org")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return "." in host
    except ValueError:
        return False


def normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    query = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}]
    # Preserve fragments: some public seminar calendars identify events by anchor.
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/",
                       urlencode(sorted(query)), parsed.fragment))


def normalized_text(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKC", value).casefold() if char.isalnum())


def city_key(value: str) -> str:
    key = normalized_text(value).removesuffix("市")
    return {"shenzhen": "深圳", "guangzhou": "广州", "zhuhai": "珠海", "hongkong": "香港",
            "macau": "澳门", "macao": "澳门", "澳門": "澳门", "廣州": "广州"}.get(key, key)


def parse_time(value: str | datetime) -> datetime:
    if not isinstance(value, (str, datetime)) or not value:
        raise ValueError("INVALID_DATETIME")
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("DATETIME_REQUIRES_OFFSET")
    return parsed.astimezone(UTC)


class FactsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    start_at: str | None = None
    end_at: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    time_precision: Literal["minute", "date"] = "minute"
    timezone: str
    city: str = Field(min_length=1, max_length=64)
    venue: str = Field(min_length=1, max_length=300)
    organizer: str = Field(min_length=1, max_length=200)
    canonical_url: str
    technical_signal: str = Field(min_length=1, max_length=5000)


class ImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: FactsInput
    evidence: dict[str, dict[str, Any]]
    enrichment: "EnrichmentInput" = Field(default_factory=lambda: EnrichmentInput())
    details: dict[str, Any] = Field(default_factory=dict)
    source_name: str = Field(default="每日活动搜寻", max_length=100)


class EnrichmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str | None = Field(default=None, max_length=10000)
    calendar_summary: str | None = Field(default=None, max_length=1000)
    why_worth: str | None = Field(default=None, max_length=5000)
    takeaways: list[str] | None = None
    prerequisites: list[str] | None = None
    topic: str | None = Field(default=None, max_length=150)
    kind: str | None = Field(default=None, max_length=64)
    relevance: str | None = Field(default=None, max_length=32)
    commute_minutes: int | None = Field(default=None, ge=0, le=3000)
    community: str | None = Field(default=None, max_length=150)


def validate_item(raw: dict[str, Any]) -> tuple[dict, dict, dict, dict, str]:
    item = ImportItem.model_validate(raw)
    facts = item.facts.model_dump(exclude_none=True)
    zone = ZoneInfo(facts["timezone"])
    precision = facts.pop("time_precision")
    first_date = facts.pop("start_date", None)
    last_date = facts.pop("end_date", None)
    if precision == "date":
        if not first_date or facts.get("start_at") or facts.get("end_at"):
            raise ValueError("DATE_PRECISION_REQUIRES_DATES_ONLY")
        if last_date and last_date < first_date:
            raise ValueError("INVALID_EVENT_INTERVAL")
        facts["start_at"] = datetime.combine(first_date, time.min, zone).astimezone(UTC)
        # Exclusive upper bound for date-level filtering; never rendered as an actual closing time.
        facts["end_at"] = datetime.combine((last_date or first_date) + timedelta(days=1), time.min, zone).astimezone(UTC)
    else:
        facts["start_at"] = parse_time(facts.get("start_at", ""))
        facts["end_at"] = parse_time(facts["end_at"]) if facts.get("end_at") else None
    if city_key(facts["city"]) not in {"深圳", "广州", "珠海", "香港", "澳门"}:
        raise ValueError("CITY_OUT_OF_SCOPE")
    facts["city"] = city_key(facts["city"])
    if not public_url(facts["canonical_url"]):
        raise ValueError("INVALID_PUBLIC_URL")
    evidence = copy.deepcopy(item.evidence)
    evidence_fields = (*REQUIRED_FACTS, "end_at") if item.facts.end_at or item.facts.end_date else REQUIRED_FACTS
    for field in evidence_fields:
        entry = evidence.get(field, {})
        if not entry:
            raise ValueError(f"MISSING_EVIDENCE:{field}")
        if not public_url(str(entry.get("source_url", ""))) or not str(entry.get("excerpt", "")).strip():
            raise ValueError(f"INVALID_EVIDENCE:{field}")
        captured = parse_time(entry.get("captured_at", ""))
        if captured > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError(f"FUTURE_EVIDENCE:{field}")
        if field == "canonical_url" and normalize_url(entry["source_url"]) != normalize_url(facts["canonical_url"]):
            raise ValueError("CANONICAL_EVIDENCE_MUST_BE_PRIMARY_PAGE")
        # Importers cannot authorize unrelated canonical hosts by supplying an allowlist.
        entry.pop("allowed_canonical_hosts", None)
    errors = evaluate_publication(facts, evidence)
    if errors:
        raise ValueError(";".join(errors))
    details = copy.deepcopy(item.details)
    if details.get("is_online") is True:
        raise ValueError("OFFLINE_ONLY")
    for field in ("registration_url",):
        if details.get(field) and not public_url(str(details[field])):
            raise ValueError(f"INVALID_PUBLIC_URL:{field}")
    for field in ("highlights",):
        if field in details and (not isinstance(details[field], list) or any(not isinstance(x, str) for x in details[field])):
            raise ValueError(f"INVALID_DETAIL:{field}")
    if "transport" in details and not isinstance(details["transport"], dict):
        raise ValueError("INVALID_DETAIL:transport")
    if details.get("registration_status") in {"closed", "cancelled"}:
        raise ValueError("NOT_PARTICIPATABLE")
    details["time_precision"] = precision
    if precision == "date":
        details["start_date"] = first_date.isoformat()
        details["end_date"] = (last_date or first_date).isoformat()
    for field in ("title", "venue", "organizer", "technical_signal"):
        facts[field] = facts[field].strip()
        if facts[field] in {"", "官方未公开", "未核实", "未知", "待定"}:
            raise ValueError(f"MISSING_FACT:{field}")
    return facts, item.enrichment.model_dump(exclude_none=True), evidence, details, item.source_name


def occurrence_key(fact: dict) -> str:
    return "|".join((normalized_text(fact["title"]), normalized_text(fact["organizer"]),
                     city_key(fact["city"]), as_utc(fact["start_at"]).isoformat()))


def identity_matches(left: dict, right: EventFactVersion, details: dict, right_details: dict) -> bool:
    if any(normalized_text(str(left[key])) != normalized_text(str(getattr(right, key))) for key in ("title", "organizer")):
        return False
    if city_key(left["city"]) != city_key(right.city):
        return False
    # Date-only inputs are not sufficient to merge separate sessions of the same series.
    if details.get("time_precision") == "date" or right_details.get("time_precision") == "date":
        return False
    return as_utc(left["start_at"]) == as_utc(right.start_at)


async def upsert_event(session, fact: dict, enrichment: dict, evidence: dict, *, source_name: str,
                       producer: str, details: dict | None = None) -> tuple[str, str]:
    if session.bind.dialect.name == "postgresql":
        # A transaction-scoped lock also serializes CLI and worker ingests across processes.
        await session.execute(text("SELECT pg_advisory_xact_lock(17350141)"))
    details = copy.deepcopy(details or {})
    url = normalize_url(fact["canonical_url"])
    # A listing or organizer may reuse a URL for a different dated/city occurrence.
    url_hash = hashlib.sha256((url + "|" + occurrence_key(fact)).encode()).hexdigest()
    alias = await session.get(EventSourceAlias, url_hash)
    existing = await session.scalar(select(Event).where(Event.event_key == alias.event_key)) if alias else None
    rows = (await session.execute(select(Event, EventFactVersion).join(
        EventFactVersion, Event.current_fact_version_id == EventFactVersion.id))).all()
    if not existing:
        matches = []
        for event, current in rows:
            supplement = await session.get(EventSupplement, event.event_key)
            other_details = supplement.document.get("details", {}) if supplement else {}
            same_base = city_key(fact["city"]) == city_key(current.city) and all(
                normalized_text(fact[field]) == normalized_text(getattr(current, field)) for field in ("title", "organizer"))
            precision_changed = (details.get("time_precision", "minute") == "date") != (other_details.get("time_precision", "minute") == "date")
            same_local_day = as_utc(fact["start_at"]).astimezone(ZoneInfo(fact["timezone"])).date() == as_utc(current.start_at).astimezone(ZoneInfo(current.timezone)).date()
            same_url_occurrence = normalize_url(current.canonical_url) == url and same_base and (
                as_utc(fact["start_at"]) == as_utc(current.start_at) or (precision_changed and same_local_day))
            if same_url_occurrence or identity_matches(fact, current, details, other_details):
                matches.append(event)
        if len(matches) > 1:
            raise ValueError("AMBIGUOUS_EVENT_IDENTITY")
        existing = matches[0] if matches else None
    event_key = existing.event_key if existing else url_hash[:32]
    supplement = await session.get(EventSupplement, event_key)
    document = copy.deepcopy(supplement.document if supplement else {"details": {}, "sources": [], "conflicts": []})
    document.setdefault("details", {})
    document.setdefault("sources", [])
    document.setdefault("conflicts", [])
    current = await session.get(EventFactVersion, existing.current_fact_version_id) if existing else None
    merged_fact = {key: getattr(current, key) for key in REQUIRED_FACTS} if current else dict(fact)
    if current:
        merged_fact.update(end_at=current.end_at, cover_url=current.cover_url)
    primary = not current or normalize_url(current.canonical_url) == url
    newest = max((parse_time(value["captured_at"]) for value in evidence.values() if value.get("captured_at")),
                 default=datetime.now(UTC))
    prior_newest = max((parse_time(value["captured_at"]) for value in (current.evidence if current else {}).values()
                        if value.get("captured_at")), default=datetime.min.replace(tzinfo=UTC))
    precision_downgrade = current and document["details"].get("time_precision", "minute") == "minute" and details.get("time_precision") == "date"
    update_primary = primary and newest >= prior_newest and not precision_downgrade
    if current and not primary:
        for key in ("venue", "start_at", "end_at", "organizer", "timezone"):
            left, right = fact.get(key), getattr(current, key)
            if isinstance(left, datetime) and isinstance(right, datetime):
                left, right = as_utc(left).isoformat(), as_utc(right).isoformat()
            if left and right and str(left) != str(right):
                conflict = {"field": key, "current": str(right), "incoming": str(left), "source_url": url}
                if conflict not in document["conflicts"]:
                    document["conflicts"].append(conflict)
    if update_primary:
        merged_fact.update(fact)
        document["details"]["time_precision"] = details.get("time_precision", "minute")
        if document["details"]["time_precision"] == "minute":
            document["details"].pop("start_date", None)
            document["details"].pop("end_date", None)
    old_enrichment = await session.get(EventEnrichmentVersion, existing.current_enrichment_version_id) if existing else None
    values = dict(summary="", calendar_summary="", why_worth="", takeaways=[], prerequisites=[],
                  topic=fact["technical_signal"][:150], kind="技术活动", relevance="中高含金量",
                  commute_minutes=None, community=fact["city"], source_name=source_name)
    if old_enrichment:
        values.update({key: getattr(old_enrichment, key) for key in values})
    # Generic crawler summaries must not replace an imported detailed account.
    detailed = producer != "network_collector"
    last_detail_at = parse_time(document["detailed_verified_at"]) if document.get("detailed_verified_at") else datetime.min.replace(tzinfo=UTC)
    accept_details = detailed and newest >= last_detail_at
    allow_enrichment = not document.get("has_detailed_import") or accept_details
    if allow_enrichment:
        values.update({key: value for key, value in enrichment.items() if key in values and value not in (None, "", [])})
        values["source_name"] = source_name
    if accept_details:
        for key, value in details.items():
            if value not in (None, "", []):
                # Date precision belongs to the selected primary facts, not another platform's copy.
                if key not in {"time_precision", "start_date", "end_date"} or update_primary:
                    document["details"][key] = value
        document["has_detailed_import"] = True
        document["detailed_verified_at"] = newest.isoformat()
    source = {"url": url, "name": source_name, "producer": producer, "verified_at": newest.isoformat(),
              "evidence": evidence}
    sources = [entry for entry in document["sources"] if entry["url"] != url]
    old_source = next((entry for entry in document["sources"] if entry["url"] == url), None)
    sources.append(source if not old_source or source["verified_at"] >= old_source["verified_at"] else old_source)
    document["sources"] = sources
    document["conflicts"] = document["conflicts"][-100:]
    if not supplement:
        supplement = EventSupplement(event_key=event_key, document=document)
        session.add(supplement)
    else:
        supplement.document = document
    if not alias:
        session.add(EventSourceAlias(url_hash=url_hash, normalized_url=url, event_key=event_key))
    new_fact = EventFactVersion(event_key=event_key, **{key: merged_fact[key] for key in REQUIRED_FACTS},
                               end_at=merged_fact.get("end_at"), cover_url=merged_fact.get("cover_url"),
                               evidence=evidence if update_primary else current.evidence)
    new_enrichment = EventEnrichmentVersion(event_key=event_key, **values)
    session.add_all([new_fact, new_enrichment])
    await session.flush()
    if existing:
        existing.current_fact_version_id = new_fact.id
        existing.current_enrichment_version_id = new_enrichment.id
        # Importing a secondary listing cannot revive a cancelled event.
        if existing.status == "published" or update_primary:
            existing.status = "published"
    else:
        existing = Event(event_key=event_key, status="published", current_fact_version_id=new_fact.id,
                         current_enrichment_version_id=new_enrichment.id)
        session.add(existing)
        session.add(EventStatusChange(event_key=event_key, old_status=None, new_status="published",
                                     trigger_source=producer, evidence=evidence))
    session.add(EventVersion(event_key=event_key, fact_version_id=new_fact.id, enrichment_version_id=new_enrichment.id))
    await session.flush()
    return ("merged" if current else "inserted"), event_key


async def import_batch(session, payload: dict) -> dict:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or \
            payload.get("producer") != "gba-tech-events" or not isinstance(payload.get("events"), list):
        raise ValueError("INVALID_BATCH_SCHEMA")
    if len(payload["events"]) > 200:
        raise ValueError("BATCH_TOO_LARGE")
    parse_time(payload.get("generated_at", ""))
    if session.bind.dialect.name == "sqlite":
        connection = await session.connection()
        driver = connection.sync_connection.connection.driver_connection
        # sqlite legacy transaction control does not start BEGIN for SELECT/SAVEPOINT.
        # Start an actual outer transaction so dry-run rollback also undoes released savepoints.
        if not driver.in_transaction:
            await connection.exec_driver_sql("BEGIN")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if session.bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(17350141)"))
    previous = await session.get(EventImportBatch, digest)
    if previous:
        return {**previous.report, "replayed": True}
    report = {"digest": digest, "inserted": 0, "merged": 0, "rejected": 0, "replayed": False, "errors": [], "event_keys": []}
    for index, raw in enumerate(payload["events"]):
        try:
            facts, enrichment, evidence, details, name = validate_item(raw)
            async with session.begin_nested():
                action, key = await upsert_event(session, facts, enrichment, evidence, details=details,
                                               source_name=name, producer="gba-tech-events")
            report[action] += 1
            report["event_keys"].append(key)
        except (ValueError, ValidationError, TypeError, KeyError, StatementError) as error:
            report["rejected"] += 1
            # Do not echo arbitrary input or validation payloads to logs.
            reason = "INVALID_RECORD_SCHEMA" if isinstance(error, (ValidationError, StatementError)) else str(error).split(";")
            report["errors"].append({"index": index, "reasons": reason if isinstance(reason, list) else [reason]})
    session.add(EventImportBatch(digest=digest, report=report))
    await session.flush()
    return report
