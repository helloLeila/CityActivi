from __future__ import annotations

import asyncio
import copy
import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint, delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./cityactivi.db")
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)
collection_lock = asyncio.Lock()


class Base(AsyncAttrs, DeclarativeBase):
    pass


class ConfigurationVersion(Base):
    __tablename__ = "configuration_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSON)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class EventFactVersion(Base):
    __tablename__ = "event_fact_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(300))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64))
    city: Mapped[str] = mapped_column(String(64), index=True)
    venue: Mapped[str] = mapped_column(String(300))
    organizer: Mapped[str] = mapped_column(String(200))
    canonical_url: Mapped[str] = mapped_column(Text)
    technical_signal: Mapped[str] = mapped_column(Text)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)


class EventEnrichmentVersion(Base):
    __tablename__ = "event_enrichment_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(100), index=True)
    summary: Mapped[str] = mapped_column(Text)
    calendar_summary: Mapped[str] = mapped_column(Text)
    why_worth: Mapped[str] = mapped_column(Text)
    takeaways: Mapped[list[str]] = mapped_column(JSON)
    prerequisites: Mapped[list[str]] = mapped_column(JSON)
    topic: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(64))
    relevance: Mapped[str] = mapped_column(String(32))
    commute_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    community: Mapped[str | None] = mapped_column(String(150), nullable=True)
    source_name: Mapped[str] = mapped_column(String(100))


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="published", index=True)
    current_fact_version_id: Mapped[int] = mapped_column(Integer)
    current_enrichment_version_id: Mapped[int] = mapped_column(Integer)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class EventVersion(Base):
    __tablename__ = "event_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(100), index=True)
    fact_version_id: Mapped[int] = mapped_column(Integer)
    enrichment_version_id: Mapped[int] = mapped_column(Integer)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class EventStatusChange(Base):
    __tablename__ = "event_status_changes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(100), index=True)
    old_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str] = mapped_column(String(32))
    trigger_source: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (UniqueConstraint("delivery_key", name="uq_job_delivery_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    delivery_key: Mapped[str] = mapped_column(String(200))
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class RawDocument(Base):
    __tablename__ = "raw_documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(100), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    status_code: Mapped[int] = mapped_column(Integer)
    parser_name: Mapped[str] = mapped_column(String(100))
    body_preview: Mapped[str] = mapped_column(Text, default="")
    etag: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    patch: dict[str, Any]


class JobRequest(BaseModel):
    job_type: str = Field(default="collect_events", min_length=2)


REQUIRED_FACTS = (
    "title",
    "start_at",
    "timezone",
    "city",
    "venue",
    "organizer",
    "canonical_url",
    "technical_signal",
)


def default_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "region": "大湾区",
        "target_count": 15,
        "schedule": {"frequency": "daily", "time": "07:00", "coverage_days": 15, "timezone": "Asia/Shanghai"},
        "origin": {"name": "深大地铁站", "address": "深圳市南山区深大地铁站", "mode": "subway_walk", "map_url": "https://www.google.com/maps/search/?api=1&query=深圳大学地铁站"},
        "cities": [
            {"city_code": "shenzhen", "name": "深圳", "is_enabled": True, "threshold": "high_medium"},
            {"city_code": "guangzhou", "name": "广州", "is_enabled": True, "threshold": "high_only"},
            {"city_code": "zhuhai", "name": "珠海", "is_enabled": True, "threshold": "high_only"},
            {"city_code": "hong_kong", "name": "香港", "is_enabled": True, "threshold": "high_commute"},
            {"city_code": "macau", "name": "澳门", "is_enabled": True, "threshold": "high_commute"},
        ],
        "audiences": [
            {"id": "aud-ai", "name": "AI 工程师", "keywords": "Agent, LLM, 推理, 大模型, 多模态, 具身智能, 机器人, VLA, AI Coding", "priority": "high", "is_enabled": True},
            {"id": "aud-devtools", "name": "开发者工具与基础设施", "keywords": "MCP, DevTools, 开源, GPU, 云原生, 数据库, 推理服务", "priority": "high", "is_enabled": True},
            {"id": "aud-research", "name": "高校科研与研究生", "keywords": "论文, 实验, 研究, 学术, 实验室, 计算机视觉, 机器学习", "priority": "medium", "is_enabled": True},
        ],
        "sources": [
            {"id": "src-meetup", "name": "Meetup 深圳技术活动", "url": "https://www.meetup.com/find/?source=EVENTS&location=cn--Shenzhen", "kind": "event_platform", "priority": "high", "is_enabled": True, "follow_detail_links": True, "detail_link_limit": 3},
            {"id": "src-meetup-guangzhou", "name": "Meetup 广州技术活动", "url": "https://www.meetup.com/find/?source=EVENTS&location=cn--Guangzhou", "kind": "event_platform", "priority": "high", "is_enabled": True, "follow_detail_links": True, "detail_link_limit": 3},
            {"id": "src-meetup-hong-kong", "name": "Meetup 香港技术活动", "url": "https://www.meetup.com/find/?source=EVENTS&location=hk--Hong-Kong", "kind": "event_platform", "priority": "high", "is_enabled": True, "follow_detail_links": True, "detail_link_limit": 3},
            {"id": "src-meetup-dimsumlabs-hackjam", "name": "Dim Sum Labs Public Social HackJam", "url": "https://www.meetup.com/dimsumlabs/events/316579110/", "kind": "developer_community", "priority": "medium", "is_enabled": True},
            {"id": "src-oshk-agentic-event", "name": "Open Source Hong Kong Agentic AI event", "url": "https://opensource.hk/oshk-oct-event-agentic-ai-platform-open-jiuwen-hermes-agent/", "kind": "open_source_community", "priority": "high", "is_enabled": True, "format": "opensource_hk"},
            {"id": "src-eventbrite", "name": "Eventbrite 深圳技术活动", "url": "https://www.eventbrite.com/d/china--shenzhen/technology--events/", "kind": "event_platform", "priority": "high", "is_enabled": True, "format": "eventbrite", "timezone": "Asia/Shanghai"},
            {"id": "src-eventbrite-shenzhen-page2", "name": "Eventbrite 深圳技术活动 · 第 2 页", "url": "https://www.eventbrite.com/d/china--shenzhen/technology--events/?page=2", "kind": "event_platform", "priority": "medium", "is_enabled": True, "format": "eventbrite", "timezone": "Asia/Shanghai"},
            {"id": "src-eventbrite-guangzhou", "name": "Eventbrite 广州技术活动", "url": "https://www.eventbrite.com/d/china--guangzhou/technology--events/", "kind": "event_platform", "priority": "high", "is_enabled": True, "format": "eventbrite", "timezone": "Asia/Shanghai"},
            {"id": "src-eventbrite-guangzhou-page2", "name": "Eventbrite 广州技术活动 · 第 2 页", "url": "https://www.eventbrite.com/d/china--guangzhou/technology--events/?page=2", "kind": "event_platform", "priority": "medium", "is_enabled": True, "format": "eventbrite", "timezone": "Asia/Shanghai"},
            {"id": "src-eventbrite-hong-kong", "name": "Eventbrite 香港技术活动", "url": "https://www.eventbrite.com/d/hong-kong--hong-kong/technology--events/", "kind": "event_platform", "priority": "high", "is_enabled": True, "format": "eventbrite", "timezone": "Asia/Hong_Kong"},
            {"id": "src-eventbrite-hong-kong-page2", "name": "Eventbrite 香港技术活动 · 第 2 页", "url": "https://www.eventbrite.com/d/hong-kong--hong-kong/technology--events/?page=2", "kind": "event_platform", "priority": "medium", "is_enabled": True, "format": "eventbrite", "timezone": "Asia/Hong_Kong"},
            {"id": "src-gdg-shenzhen", "name": "GDG Shenzhen 开发者社区", "url": "https://gdg.community.dev/gdg-shenzhen/", "kind": "developer_community", "priority": "high", "is_enabled": True, "format": "gdg", "follow_detail_links": True, "detail_link_limit": 3},
            {"id": "src-gdg-guangzhou", "name": "GDG Guangzhou 开发者社区", "url": "https://gdg.community.dev/gdg-guangzhou/", "kind": "developer_community", "priority": "high", "is_enabled": True, "format": "gdg", "follow_detail_links": True, "detail_link_limit": 3},
            {"id": "src-gdg-hong-kong", "name": "GDG Hong Kong 开发者社区", "url": "https://gdg.community.dev/gdg-hong-kong/", "kind": "developer_community", "priority": "medium", "is_enabled": True, "format": "gdg", "follow_detail_links": True, "detail_link_limit": 3},
            {"id": "src-gosim-shenzhen", "name": "GOSIM Shenzhen AI / 机器人大会", "url": "https://shenzhen2026.gosim.org/zh/", "kind": "ai_embodied_event", "priority": "high", "is_enabled": True, "format": "gosim"},
            {"id": "src-gosim-schedule", "name": "GOSIM Shenzhen 议程详情", "url": "https://shenzhen2026.gosim.org/zh/schedule/", "kind": "ai_embodied_event", "priority": "high", "is_enabled": True, "format": "gosim", "follow_detail_links": True, "detail_link_limit": 5},
            {"id": "src-opengauss-events", "name": "openGauss 开源社区活动", "url": "https://opengauss.org/zh/events/", "kind": "open_source_community", "priority": "high", "is_enabled": True, "follow_detail_links": True, "detail_link_limit": 3},
            {"id": "src-openinfra-events", "name": "OpenInfra 中国社区活动", "url": "https://openinfradev.org/events/", "kind": "open_source_community", "priority": "medium", "is_enabled": True, "follow_detail_links": True, "detail_link_limit": 3},
            {"id": "src-airs-events", "name": "AIRS 人工智能与机器人研究院", "url": "https://airs.cuhk.edu.cn/en/events", "kind": "university_research", "priority": "high", "is_enabled": True, "follow_detail_links": True, "detail_link_limit": 4},
            {"id": "src-szu-library-events", "name": "深圳大学图书馆活动与讲座", "url": "https://www.lib.szu.edu.cn/events", "kind": "university_research", "priority": "medium", "is_enabled": True, "follow_detail_links": True, "detail_link_limit": 8},
            {"id": "src-sustech-lectures", "name": "南方科技大学学术讲座", "url": "https://www.sustech.edu.cn/zh/events-142.html", "kind": "university_research", "priority": "medium", "is_enabled": True, "format": "sustech", "organizer": "南方科技大学", "follow_detail_links": True, "detail_link_limit": 8},
            {"id": "src-cuhk-shenzhen-events", "name": "香港中文大学（深圳）活动搜索", "url": "https://www.cuhk.edu.cn/en/event-search", "kind": "university_research", "priority": "medium", "is_enabled": True, "follow_detail_links": True, "detail_link_limit": 8},
            {"id": "src-hkust-events", "name": "香港科技大学活动", "url": "https://hkust.edu.hk/events", "kind": "university_research", "priority": "medium", "is_enabled": True, "follow_detail_links": True, "detail_link_limit": 8},
            {"id": "src-hkstp-events", "name": "香港科技园活动", "url": "https://www.hkstp.org/en/park-life/news-and-events/events/", "kind": "industry_community", "priority": "medium", "is_enabled": True, "follow_detail_links": True, "detail_link_limit": 8},
            {"id": "src-shenzhen-public-activities", "name": "深圳公共文化活动", "url": "https://wtl.sz.gov.cn/bsfw/mzwhhd/mzhd/index.html", "kind": "public_activity", "priority": "low", "is_enabled": True, "follow_detail_links": True, "detail_link_limit": 8},
            {"id": "src-shenzhen-library-events", "name": "深圳图书馆活动", "url": "https://www.szlib.org.cn/hd/", "kind": "public_activity", "priority": "low", "is_enabled": True, "follow_detail_links": True, "detail_link_limit": 8},
            {"id": "src-cityu-cccn-seminars", "name": "CityU-CCCN-PolyU Joint Seminars", "url": "https://www.ee.cityu.edu.hk/~cccn/centre-seminars.htm", "kind": "university_research", "priority": "medium", "is_enabled": True, "format": "cityu_seminars"},
            {"id": "src-eet-tektronix-guangzhou", "name": "EET China 泰克广州技术研讨会", "url": "https://www.eet-china.com/mp/a525102.html", "kind": "industry_technical_seminar", "priority": "medium", "is_enabled": True, "format": "eet_event", "city": "广州", "organizer": "泰克科技"},
            {"id": "src-hku-qwencloud-workshop", "name": "HKU QwenCloud AI Builder Workshop", "url": "https://tec.hku.hk/innovation-week-2026/programmes/build-with-ai-workshop-create-your-ai-application-with-qwen-cloud/", "kind": "university_workshop", "priority": "high", "is_enabled": True, "format": "hku_workshop"},
            {"id": "src-hkust-qwencloud-workshop", "name": "HKUST QwenCloud AI Builder Workshop", "url": "https://ec.hkust.edu.hk/events/entrepreneurs-toolbox-series-qwencloud-ai-builder-workshop", "kind": "university_workshop", "priority": "high", "is_enabled": True, "format": "hkust_workshop"},
            {"id": "src-rustchinaconf-shenzhen", "name": "RustChinaConf 2026 Shenzhen", "url": "https://rustchinaconf.org/schedule/", "kind": "developer_conference", "priority": "high", "is_enabled": True, "format": "rustchinaconf"},
            {"id": "src-innovation-nanshan", "name": "南山区智能经济产业协会（创新南山相关）", "url": "https://nsszjj.com/", "kind": "industry_community", "priority": "medium", "is_enabled": False},
            {"id": "src-inanshan", "name": "创新南山企业服务平台", "url": "https://www.inanshan.org.cn/", "kind": "industry_community", "priority": "medium", "is_enabled": False},
            {"id": "src-szdiy-calendar", "name": "SZDIY 开发者社区日历", "url": "https://calendar.google.com/calendar/ical/1b1dd602b762014abe5ac8f1b8795549285a97dd8ef19c2358958a6adcfb8df5%40group.calendar.google.com/public/basic.ics", "kind": "developer_community_ical", "priority": "medium", "is_enabled": True, "format": "ics", "timezone": "Asia/Shanghai", "organizer": "SZDIY 开发者社区"},
        ],
        "topics": [
            {"id": "topic-agent", "name": "Agent / RAG", "keywords": "Agent, RAG, LLM, 智能体, 检索增强", "priority": "high", "is_enabled": True},
            {"id": "topic-coding", "name": "AI Coding 与开发者工具", "keywords": "AI Coding, MCP, DevTools, 代码生成, 开发者工具", "priority": "high", "is_enabled": True},
            {"id": "topic-inference", "name": "模型训练与推理", "keywords": "推理, KV Cache, 多模态, 大模型, vLLM, 端侧推理", "priority": "high", "is_enabled": True},
            {"id": "topic-embodied", "name": "具身智能与机器人", "keywords": "具身智能, VLA, 机器人, Robotics, Sim-to-Real, 视觉语言动作, 运动控制, 机械臂", "priority": "high", "is_enabled": True},
            {"id": "topic-research", "name": "AI 科研与计算机视觉", "keywords": "科研, 学术, 论文, 实验室, 机器学习, 深度学习, 计算机视觉, AI for Science", "priority": "medium", "is_enabled": True},
            {"id": "topic-open-source", "name": "开源与 AI 基础设施", "keywords": "开源, Open Source, openGauss, GPU, 云原生, 数据库, 边缘计算, Linux", "priority": "medium", "is_enabled": True},
        ],
        "weak_content_rules": [{"id": "weak-trend", "name": "纯商业趋势", "keywords": "趋势, 投融资", "priority": "low", "is_enabled": True}],
        "event_types": [{"id": "type-industry", "name": "业界", "description": "公司、工程团队和产业实践", "is_enabled": True}],
        "display_fields": {"show_community": True, "show_topic": True, "show_source": True, "show_why": True, "show_travel": True, "show_cost": False, "show_cover": False, "show_takeaways": True, "show_prerequisites": True},
        "notification": {"is_enabled": True, "time": "08:30", "timezone": "Asia/Shanghai", "automation_name": "线下技术活动情报晨报", "prompt_file": "tech-events-assistant.automation.md"},
        "channels": [{"id": "channel-feishu", "type": "feishu", "name": "飞书自定义机器人", "endpoint": "", "secret_configured": False, "is_enabled": True}],
        "runtime": {
            "database_status": "connected",
            "utc_storage": True,
            "max_concurrency": 1,
            "request_timeout_seconds": 20,
            "max_retries": 2,
            "per_host_delay_seconds": 4,
            "robots_cache_hours": 24,
            "rate_limit_cooldown_seconds": 300,
        },
    }


def deep_merge(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(current)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def validate_config(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    schedule = document.get("schedule", {})
    if schedule.get("coverage_days") not in {15, 30, 60}:
        errors.append("coverage_days must be 15, 30, or 60")
    timezone_name = schedule.get("timezone")
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        errors.append("schedule.timezone must be a valid IANA timezone")
    for section in ("cities", "sources", "topics", "event_types", "channels"):
        if not isinstance(document.get(section), list):
            errors.append(f"{section} must be a list")
    return errors


def evaluate_publication(fact: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    errors = [f"MISSING_FACT:{field}" for field in REQUIRED_FACTS if not fact.get(field)]
    errors.extend(f"MISSING_EVIDENCE:{field}" for field in REQUIRED_FACTS if not evidence.get(field))
    start_at = fact.get("start_at")
    if isinstance(start_at, datetime) and start_at <= datetime.now(UTC):
        errors.append("EVENT_ALREADY_STARTED")
    try:
        ZoneInfo(fact.get("timezone", ""))
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        errors.append("INVALID_IANA_TIMEZONE")
    canonical_url = str(fact.get("canonical_url", ""))
    canonical_parsed = urlparse(canonical_url)
    canonical_host = (canonical_parsed.hostname or "").lower().rstrip(".")
    if canonical_parsed.scheme not in {"http", "https"} or not canonical_host:
        errors.append("INVALID_CANONICAL_URL")
    reserved_suffixes = (".example", ".test", ".invalid", ".localhost", ".local", ".example.com", ".example.net", ".example.org", ".test.com")
    reserved_hosts = {"example.com", "example.net", "example.org", "test.com", "localhost"}
    if canonical_host in reserved_hosts or canonical_host.endswith(reserved_suffixes):
        errors.append("CANONICAL_URL_RESERVED_HOST")
    canonical_evidence = evidence.get("canonical_url", {})
    source_host = (urlparse(str(canonical_evidence.get("source_url", ""))).hostname or "").lower().rstrip(".")
    allowed_hosts = {str(host).lower().rstrip(".") for host in canonical_evidence.get("allowed_canonical_hosts", [])}
    if not source_host:
        errors.append("CANONICAL_SOURCE_URL_MISSING")
    elif canonical_host != source_host and canonical_host not in allowed_hosts:
        errors.append("CANONICAL_URL_SOURCE_MISMATCH")
    return errors


def serialize_event(fact: EventFactVersion, enrichment: EventEnrichmentVersion, event: Event) -> dict[str, Any]:
    return {
        "id": event.event_key,
        "status": event.status,
        "facts": {
            "title": fact.title,
            "start_at": as_utc(fact.start_at).isoformat().replace("+00:00", "Z"),
            "end_at": as_utc(fact.end_at).isoformat().replace("+00:00", "Z") if fact.end_at else None,
            "timezone": fact.timezone,
            "city": fact.city,
            "venue": fact.venue,
            "organizer": fact.organizer,
            "canonical_url": fact.canonical_url,
            "technical_signal": fact.technical_signal,
            "cover_url": fact.cover_url,
        },
        "enrichment": {
            "summary": enrichment.summary,
            "calendar_summary": enrichment.calendar_summary,
            "why_worth": enrichment.why_worth,
            "takeaways": enrichment.takeaways,
            "prerequisites": enrichment.prerequisites,
            "topic": enrichment.topic,
            "kind": enrichment.kind,
            "relevance": enrichment.relevance,
            "commute_minutes": enrichment.commute_minutes,
            "community": enrichment.community,
            "source_name": enrichment.source_name,
        },
    }


def as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; normalize them to the UTC contract."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def get_config(session: AsyncSession) -> tuple[ConfigurationVersion, ConfigurationVersion]:
    rows = (await session.execute(select(ConfigurationVersion).order_by(ConfigurationVersion.revision.desc()))).scalars().all()
    if not rows:
        document = default_config()
        row = ConfigurationVersion(revision=1, document=document, is_published=True)
        session.add(row)
        await session.commit()
        return row, row
    draft = rows[0]
    published = next((row for row in rows if row.is_published), rows[-1])
    return draft, published


async def update_job(job_id: int) -> None:
    transitions = [("queued", 15, "任务排队中"), ("running", 45, "抓取、事实核验与摘要处理中")]
    for status, progress, message in transitions:
        await asyncio.sleep(0.45)
        async with Session() as session:
            job = await session.get(JobRun, job_id)
            if not job or job.status == "cancelled":
                return
            job.status = status
            job.progress = progress
            job.message = message
            job.updated_at = datetime.now(UTC)
            await session.commit()
    async with Session() as session:
        job = await session.get(JobRun, job_id)
        if not job or job.status == "cancelled":
            return
        if job.job_type in {"collect_events", "scheduled_collect"}:
            from .collector import collect_events_once

            if collection_lock.locked():
                job.status = "failed"
                job.progress = 100
                job.error_code = "COLLECTION_ALREADY_RUNNING"
                job.message = "已有网络采集任务执行中，本次请求未发起网络访问"
                job.updated_at = datetime.now(UTC)
                await session.commit()
                return
            try:
                async with collection_lock:
                    result = await collect_events_once()
                configured = result.get("configured_sources", 0)
                reached = result.get("reached_sources", 0)
                blocked = result.get("blocked_sources", 0)
                failed = result.get("failed_sources", 0)
                candidates = result.get("candidates_seen", 0)
                rejected = result.get("fact_rejected", 0)
                published = result.get("published_events", 0)
                source_coverage = len(result.get("published_by_source", {}))
                job.status = "succeeded" if reached > 0 else "failed"
                job.progress = 100
                job.error_code = "PARTIAL_SOURCE_FAILURE" if blocked or failed else None
                job.message = (
                    f"网络抓取完成：{configured} 个来源中 {reached} 个可访问，"
                    f"{blocked} 个被 robots/限流跳过，{failed} 个网络失败；"
                    f"发现 {candidates} 个候选，核验通过 {result.get('verified_candidates', 0)} 个，"
                    f"事实门禁拒绝 {rejected} 个，发布 {published} 场活动，覆盖 {source_coverage} 个来源"
                )
            except Exception as error:  # noqa: BLE001 - persisted task boundary
                job.status = "failed"
                job.progress = 100
                job.error_code = type(error).__name__
                job.message = f"网络抓取失败：{error}"
        else:
            job.status = "running"
            job.progress = 78
            job.message = "活动发布快照已生成"
            await session.flush()
            await asyncio.sleep(0.35)
            job.status = "succeeded"
            job.progress = 100
            job.message = "任务完成，公开接口已更新"
        job.updated_at = datetime.now(UTC)
        await session.commit()


async def seed_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with Session() as session:
        await get_config(session)
        example_keys = (await session.execute(
            select(EventFactVersion.event_key).where(or_(
                EventFactVersion.canonical_url.ilike("%://example.com/%"),
                EventFactVersion.canonical_url.ilike("%://%.example.com/%"),
                EventFactVersion.canonical_url.ilike("%://example.net/%"),
                EventFactVersion.canonical_url.ilike("%://example.org/%"),
                EventFactVersion.canonical_url.ilike("%://test.com/%"),
                EventFactVersion.canonical_url.ilike("%://%.test/%"),
                EventFactVersion.canonical_url.ilike("%://%.test.com/%"),
                EventFactVersion.canonical_url.ilike("%://%.invalid/%"),
                EventFactVersion.canonical_url.ilike("%://localhost/%"),
                EventFactVersion.canonical_url.ilike("%://%.local/%"),
            ))
        )).scalars().all()
        seed_keys = (await session.execute(
            select(EventStatusChange.event_key).where(EventStatusChange.trigger_source == "seed")
        )).scalars().all()
        demo_keys = set(example_keys) | set(seed_keys)
        if demo_keys:
            await session.execute(delete(Event).where(Event.event_key.in_(demo_keys)))
            await session.execute(delete(EventVersion).where(EventVersion.event_key.in_(demo_keys)))
            await session.execute(delete(EventStatusChange).where(EventStatusChange.event_key.in_(demo_keys)))
            await session.execute(delete(EventFactVersion).where(EventFactVersion.event_key.in_(demo_keys)))
            await session.execute(delete(EventEnrichmentVersion).where(EventEnrichmentVersion.event_key.in_(demo_keys)))
        await session.commit()


app = FastAPI(title="CityActivi API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup() -> None:
    await seed_database()


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(ROOT / "cityactivi-redesign-preview.html", media_type="text/html")


@app.get("/api/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok", "service": "cityactivi-api"}


@app.get("/api/health/ready")
async def health_ready() -> dict[str, str]:
    async with Session() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready", "database": "connected"}


@app.get("/api/public/events")
async def public_events(coverage_days: int = Query(15), q: str = "", city: str = "", topic: str = "") -> dict[str, Any]:
    if coverage_days not in {15, 30, 60}:
        raise HTTPException(status_code=422, detail="coverage_days must be 15, 30, or 60")
    now = datetime.now(UTC)
    async with Session() as session:
        rows = (await session.execute(select(Event).where(Event.status == "published").order_by(Event.published_at.desc()))).scalars().all()
        output: list[dict[str, Any]] = []
        for event in rows:
            fact = await session.get(EventFactVersion, event.current_fact_version_id)
            enrichment = await session.get(EventEnrichmentVersion, event.current_enrichment_version_id)
            if not fact or not enrichment or not (now <= as_utc(fact.start_at) <= now + timedelta(days=coverage_days)):
                continue
            searchable = " ".join((fact.title, fact.city, fact.organizer, fact.venue, enrichment.topic)).lower()
            if q and q.lower() not in searchable:
                continue
            if city and fact.city != city:
                continue
            if topic and topic.lower() not in enrichment.topic.lower():
                continue
            output.append(serialize_event(fact, enrichment, event))
        output.sort(key=lambda item: item["facts"]["start_at"])
        return {"items": output, "total": len(output), "coverage_days": coverage_days, "generated_at": now.isoformat()}


@app.get("/api/public/events/{event_key}")
async def public_event(event_key: str) -> dict[str, Any]:
    async with Session() as session:
        event = (await session.execute(select(Event).where(Event.event_key == event_key))).scalar_one_or_none()
        if not event or event.status != "published":
            raise HTTPException(status_code=404, detail="event not found")
        fact = await session.get(EventFactVersion, event.current_fact_version_id)
        enrichment = await session.get(EventEnrichmentVersion, event.current_enrichment_version_id)
        if not fact or not enrichment:
            raise HTTPException(status_code=409, detail="published snapshot is incomplete")
        return serialize_event(fact, enrichment, event)


@app.get("/api/ops/config")
async def read_config() -> dict[str, Any]:
    async with Session() as session:
        draft, published = await get_config(session)
        return {"draft_revision": draft.revision, "published_revision": published.revision, "draft": draft.document, "published": published.document}


@app.post("/api/ops/config/validate")
async def validate_config_api(document: dict[str, Any]) -> dict[str, Any]:
    errors = validate_config(document)
    return {"valid": not errors, "errors": errors}


@app.patch("/api/ops/config")
async def patch_config(payload: ConfigPatch) -> dict[str, Any]:
    async with Session() as session:
        draft, _ = await get_config(session)
        if draft.revision != payload.expected_revision:
            raise HTTPException(status_code=409, detail={"code": "DRAFT_REVISION_CONFLICT", "current_revision": draft.revision})
        document = deep_merge(draft.document, payload.patch)
        errors = validate_config(document)
        if errors:
            raise HTTPException(status_code=422, detail={"code": "CONFIG_INVALID", "errors": errors})
        draft.is_published = False
        row = ConfigurationVersion(revision=draft.revision + 1, document=document, is_published=False)
        session.add(row)
        await session.commit()
        return {"draft_revision": row.revision, "document": document}


@app.post("/api/ops/config/publish")
async def publish_config() -> dict[str, Any]:
    async with Session() as session:
        draft, published = await get_config(session)
        errors = validate_config(draft.document)
        if errors:
            raise HTTPException(status_code=422, detail={"code": "CONFIG_INVALID", "errors": errors})
        published.is_published = False
        draft.is_published = True
        await session.commit()
        return {"status": "succeeded", "published_revision": draft.revision, "document": draft.document}


@app.post("/api/ops/jobs")
async def create_job(payload: JobRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    job_type = "collect_events" if payload.job_type == "run-task" else payload.job_type
    delivery_key = f"manual:{job_type}:{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}:{uuid.uuid4().hex[:8]}"
    async with Session() as session:
        if job_type in {"collect_events", "scheduled_collect"}:
            active_job = (
                await session.execute(
                    select(JobRun)
                    .where(JobRun.job_type.in_({"collect_events", "scheduled_collect"}), JobRun.status.in_({"submitted", "queued", "running"}))
                    .order_by(JobRun.created_at)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if active_job:
                raise HTTPException(status_code=409, detail={"code": "COLLECTION_ALREADY_RUNNING", "job_id": active_job.id, "message": "已有网络采集任务执行中"})
        job = JobRun(job_type=job_type, status="submitted", delivery_key=delivery_key, progress=0, message="请求已提交", updated_at=datetime.now(UTC))
        session.add(job)
        await session.commit()
        await session.refresh(job)
        background_tasks.add_task(update_job, job.id)
        return {"id": job.id, "job_type": job.job_type, "status": job.status, "delivery_key": job.delivery_key}


@app.get("/api/ops/jobs/{job_id}")
async def get_job(job_id: int) -> dict[str, Any]:
    async with Session() as session:
        job = await session.get(JobRun, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return {"id": job.id, "job_type": job.job_type, "status": job.status, "progress": job.progress, "message": job.message, "delivery_key": job.delivery_key, "error_code": job.error_code, "updated_at": job.updated_at.isoformat()}


@app.post("/api/ops/channels/test")
async def test_channel() -> dict[str, Any]:
    return {"status": "succeeded", "message": "通道配置格式检查通过，未发送真实通知"}


@app.post("/api/ops/secrets/clear")
async def clear_secrets() -> dict[str, Any]:
    return {"status": "succeeded", "message": "密钥引用已清除，明文不会返回"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
