from __future__ import annotations

import hashlib
import ipaddress
import json
import random
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib import robotparser
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncio
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from .main import (
    REQUIRED_FACTS,
    Event,
    EventEnrichmentVersion,
    EventFactVersion,
    EventStatusChange,
    EventVersion,
    RawDocument,
    Session,
    as_utc,
    evaluate_publication,
    get_config,
)

TECHNICAL_TERMS = re.compile(r"\b(ai|artificial intelligence|ml|machine learning|deep learning|llm|agent|rag|mcp|python|javascript|typescript|rust|cloud|data|database|devops|kubernetes|gpu|web|software|developer|engineering|robotics|robot|embodied|computer vision|multimodal|inference|open source|opensource|vla|sim-to-real|research|science|seminar|technology|tech|analytics|algorithmic|edtech|electronics|innovation|trading|技术|开发|工程|数据|模型|算法|云原生|数据库|开源|推理|机器人|具身智能|计算机视觉|多模态|科研|学术|实验室|论文|大模型|端侧|边缘计算|自动驾驶|智能制造|无人机|运动控制|机械臂)\b", re.I)
TECHNICAL_CJK_TERMS = re.compile(r"(人工智能|机器学习|深度学习|大模型|智能体|机器人|具身智能|计算机视觉|多模态|推理|开发者|技术|工程|数据|模型|算法|云原生|数据库|开源|科研|学术|实验室|论文|端侧|边缘计算|自动驾驶|智能制造|无人机|运动控制|机械臂|网页设计|互动程序)")
MAX_RESPONSE_BYTES = 3 * 1024 * 1024
USER_AGENT = "CityActiviBot/0.1 (+public event calendar; contact via project owner)"
PARSER_NAME = "json_ld_event_v3"
ROBOTS_CACHE_SECONDS = 24 * 60 * 60
DEFAULT_HOST_DELAY_SECONDS = 4.0
JITTER_MIN_SECONDS = 0.4
JITTER_MAX_SECONDS = 1.2
MAX_RETRIES = 2
MAX_REDIRECTS = 3
MAX_RETRY_AFTER_SECONDS = 300
FORBIDDEN_COOLDOWN_SECONDS = 60 * 60
RATE_LIMIT_COOLDOWN_SECONDS = 5 * 60
MAX_DETAIL_LINKS = 12
CANDIDATE_SAFETY_FACTOR = 3
DEFAULT_CITY_QUOTA = 4
DEFAULT_CANDIDATE_POOL_TARGET = DEFAULT_CITY_QUOTA * CANDIDATE_SAFETY_FACTOR
CANONICAL_HOSTS_BY_FORMAT = {"opensource_hk": {"www.meetup.com", "meetup.com"}}
TRANSIENT_STATUS_CODES = {408, 425, 500, 502, 503, 504, 520, 521, 522, 524}
DETAIL_PATH_HINTS = re.compile(r"/(?:event|events|node|content|article|post|e)[/_-]?[a-z0-9-]*", re.I)
DETAIL_TEXT_HINTS = re.compile(r"(活动|讲座|研讨|论坛|学术|科研|开发者|机器人|具身|人工智能|\bAI\b|\bseminar\b|\bworkshop\b|\bconference\b|\bmeetup\b|\bevent\b)", re.I)
DETAIL_EXCLUDE_PATHS = re.compile(r"/(?:speaker|speakers|sponsor|sponsors|venue|ticket|tickets|contact|about)(?:/|$)", re.I)


def _technical_signal(text: str) -> str:
    matches = TECHNICAL_TERMS.findall(text) + TECHNICAL_CJK_TERMS.findall(text)
    return "；".join(dict.fromkeys(matches))


class CrawlPolicy:
    def __init__(self) -> None:
        self.last_request_at: dict[str, float] = {}
        self.robots: dict[str, tuple[float, robotparser.RobotFileParser, float]] = {}
        self.blocked_until: dict[str, float] = {}
        self.denial_reasons: dict[str, str] = {}
        self.lock = asyncio.Lock()

    @staticmethod
    def host_key(url: str) -> str:
        parsed = urlparse(url)
        return (parsed.netloc or parsed.path).lower()

    async def wait_for_host(self, url: str, minimum_delay: float = DEFAULT_HOST_DELAY_SECONDS) -> None:
        host = self.host_key(url)
        async with self.lock:
            elapsed = time.monotonic() - self.last_request_at.get(host, 0)
            delay = max(0.0, minimum_delay - elapsed) + random.uniform(JITTER_MIN_SECONDS, JITTER_MAX_SECONDS)
            if delay:
                await asyncio.sleep(delay)
            self.last_request_at[host] = time.monotonic()

    def cooldown_remaining(self, url: str) -> float:
        return max(0.0, self.blocked_until.get(self.host_key(url), 0.0) - time.time())

    def mark_blocked(self, url: str, seconds: float, reason: str) -> None:
        host = self.host_key(url)
        self.blocked_until[host] = max(self.blocked_until.get(host, 0.0), time.time() + seconds)
        self.denial_reasons[host] = reason

    async def allowed(self, client: httpx.AsyncClient, url: str) -> tuple[bool, float]:
        parsed = urlparse(url)
        if not _is_safe_public_url(url):
            self.denial_reasons[self.host_key(url)] = "unsafe_url"
            return False, 2.0
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        host = self.host_key(url)
        remaining = self.cooldown_remaining(url)
        if remaining:
            self.denial_reasons[host] = "host_cooldown"
            return False, DEFAULT_HOST_DELAY_SECONDS
        cached = self.robots.get(host)
        if cached and time.time() - cached[0] < ROBOTS_CACHE_SECONDS:
            parser, crawl_delay = cached[1], cached[2]
            return parser.can_fetch(USER_AGENT, url), crawl_delay
        self.denial_reasons.pop(host, None)
        parser = robotparser.RobotFileParser()
        parser.set_url(robots_url)
        crawl_delay = DEFAULT_HOST_DELAY_SECONDS
        try:
            await self.wait_for_host(robots_url, minimum_delay=DEFAULT_HOST_DELAY_SECONDS)
            response = await client.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=10)
            if response.status_code == 404:
                parser.parse([])
            elif response.status_code >= 400:
                parser.parse(["User-agent: *", "Disallow: /"])
                self.denial_reasons[host] = f"robots_http_{response.status_code}"
            else:
                parser.parse(response.text.splitlines())
                crawl_delay = max(DEFAULT_HOST_DELAY_SECONDS, float(parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*") or DEFAULT_HOST_DELAY_SECONDS))
        except (httpx.HTTPError, ValueError):
            parser.parse(["User-agent: *", "Disallow: /"])
            self.denial_reasons[host] = "robots_unavailable"
        self.robots[host] = (time.time(), parser, crawl_delay)
        allowed = parser.can_fetch(USER_AGENT, url)
        if not allowed and host not in self.denial_reasons:
            self.denial_reasons[host] = "robots_denied"
        return allowed, crawl_delay


policy = CrawlPolicy()


def _is_safe_public_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith((".local", ".internal")):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return address.is_global


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())


async def _request_with_redirects(
    client: httpx.AsyncClient,
    source_url: str,
    headers: dict[str, str],
) -> tuple[httpx.Response | None, str, str | None]:
    current_url = source_url
    request_headers = dict(headers)
    visited: set[str] = set()
    for _ in range(MAX_REDIRECTS + 1):
        if current_url in visited:
            return None, current_url, "redirect_loop"
        visited.add(current_url)
        allowed, crawl_delay = await policy.allowed(client, current_url)
        if not allowed:
            return None, current_url, policy.denial_reasons.get(policy.host_key(current_url), "robots_denied")
        await policy.wait_for_host(current_url, minimum_delay=crawl_delay)
        response = await client.get(current_url, headers=request_headers, follow_redirects=False)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response, current_url, None
        location = response.headers.get("Location")
        if not location:
            return response, current_url, None
        next_url = urljoin(current_url, location)
        if not _is_safe_public_url(next_url):
            return None, next_url, "unsafe_redirect"
        current_url = next_url
        request_headers.pop("If-None-Match", None)
        request_headers.pop("If-Modified-Since", None)
    return None, current_url, "redirect_limit"


def _json_ld_nodes(soup: BeautifulSoup) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    def visit(candidate: Any) -> None:
        if isinstance(candidate, list):
            for item in candidate:
                visit(item)
            return
        if not isinstance(candidate, dict):
            return
        types = candidate.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if any("event" in str(item).lower() for item in types):
            nodes.append(candidate)
        for key in ("@graph", "itemListElement"):
            nested = candidate.get(key)
            if isinstance(nested, list):
                for item in nested:
                    visit(item.get("item") if isinstance(item, dict) and "item" in item else item)
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue
        visit(payload)
    return nodes


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or value.get("addressLocality") or value.get("streetAddress") or "").strip()
    return str(value or "").strip()


def _parse_datetime(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    raw = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_ics_datetime(value: str, tz_name: str = "Asia/Shanghai") -> datetime | None:
    raw = value.strip().split(":", 1)[-1]
    if raw.endswith("Z"):
        raw = raw[:-1]
        tz = UTC
    else:
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = UTC
    try:
        if len(raw) == 8:
            parsed = datetime.strptime(raw, "%Y%m%d").replace(hour=9, tzinfo=tz)
        else:
            parsed = datetime.strptime(raw[:15], "%Y%m%dT%H%M%S").replace(tzinfo=tz)
    except ValueError:
        return None
    return parsed.astimezone(UTC)


def _unfold_ics(body: str) -> list[str]:
    lines: list[str] = []
    for line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def _parse_ics_candidates(body: str, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in _unfold_ics(body):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            if current:
                events.append(current)
            current = None
        elif current is not None and ":" in line:
            key, value = line.split(":", 1)
            base_key, *parameters = key.split(";")
            normalized = value.replace("\\n", " ").replace("\\,", ",").strip()
            current[base_key.upper()] = normalized
            for parameter in parameters:
                if parameter.upper().startswith("CN="):
                    current[f"{base_key.upper()}_CN"] = parameter.split("=", 1)[1].strip('"')
    output: list[dict[str, Any]] = []
    source_city = _city_from_text(f"{source.get('name', '')} {source_url}")
    default_timezone = source.get("timezone") or ("Asia/Hong_Kong" if source_city == "香港" else "Asia/Macau" if source_city == "澳门" else "Asia/Shanghai")
    for item in events:
        title = item.get("SUMMARY", "").strip()
        description = item.get("DESCRIPTION", "").strip()
        location = item.get("LOCATION", "").strip()
        organizer = item.get("ORGANIZER_CN", "").strip() or item.get("ORGANIZER", "").strip()
        organizer = re.sub(r"^CN=", "", organizer, flags=re.I).split(":", 1)[0].strip() or source.get("organizer", "")
        event_url = item.get("URL", "").strip() or source_url
        city = _city_from_text(" ".join((location, title, description, source.get("name", "")))) or source_city
        start_at = _parse_ics_datetime(item.get("DTSTART", ""), default_timezone)
        technical_signal = _technical_signal(f"{title} {description}")
        if not (title and start_at and location and organizer and city and technical_signal):
            continue
        output.append({
            "title": title,
            "start_at": start_at,
            "timezone": default_timezone,
            "city": city,
            "venue": location,
            "organizer": organizer,
            "canonical_url": event_url if event_url.startswith("http") else source_url,
            "technical_signal": technical_signal,
            "description": description,
            "source_name": source.get("name", "公开来源"),
            "source_url": source_url,
        })
    return output


def _city_from_text(text: str) -> str | None:
    aliases = {"深圳": ("深圳", "shenzhen", "shen zhen", "shenzhen city", "nanshan", "南山"), "广州": ("广州", "guangzhou", "guang zhou", "guangdong", "canton"), "珠海": ("珠海", "zhuhai"), "香港": ("香港", "hong kong", "hongkong", "hong kong s.a.r.", "kowloon", "wan chai", "north point"), "澳门": ("澳门", "macau", "macao")}
    lowered = text.lower()
    for city, names in aliases.items():
        if any(name.lower() in lowered for name in names):
            return city
    return None


def _candidate_from_json_ld(node: dict[str, Any], source: dict[str, Any], source_url: str) -> dict[str, Any] | None:
    location = node.get("location") or {}
    address = location.get("address") if isinstance(location, dict) else ""
    location_text = " ".join(filter(None, [_text(location), _text(address)]))
    title = _text(node.get("name"))
    description = BeautifulSoup(_text(node.get("description")), "html.parser").get_text(" ", strip=True)
    canonical_url = _text(node.get("url"))
    if canonical_url and not canonical_url.startswith("http"):
        canonical_url = urljoin(source_url, canonical_url)
    city = _city_from_text(" ".join([location_text, title, description])) or _city_from_text(source_url)
    start_at = _parse_datetime(node.get("startDate"))
    organizer = _text(node.get("organizer"))
    technical_signal = _technical_signal(f"{title} {description}")
    if not (title and canonical_url and city and location_text and organizer and start_at and technical_signal):
        return None
    if not _is_safe_public_url(canonical_url):
        return None
    timezone = "Asia/Hong_Kong" if city == "香港" else "Asia/Macau" if city == "澳门" else "Asia/Shanghai"
    return {"title": title, "start_at": start_at, "timezone": timezone, "city": city, "venue": location_text, "organizer": organizer, "canonical_url": canonical_url, "technical_signal": technical_signal, "description": description, "source_name": source.get("name", "公开来源"), "source_url": source_url}


def _extract_js_assignment(body: str, assignment: str) -> Any | None:
    marker = f"{assignment} = "
    position = body.find(marker)
    if position < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(body[position + len(marker):])
    except json.JSONDecodeError:
        return None
    return value


def _eventbrite_city(event: dict[str, Any], source: dict[str, Any], source_url: str) -> str | None:
    pieces: list[str] = []
    for location in event.get("locations") or []:
        if isinstance(location, dict):
            pieces.append(str(location.get("name", "")))
    venue = event.get("primary_venue") or {}
    address = venue.get("address") if isinstance(venue, dict) else {}
    if isinstance(address, dict):
        pieces.extend(str(address.get(key, "")) for key in ("city", "region", "localized_address_display", "localized_area_display"))
    pieces.extend((str(event.get("name", "")), str(source.get("name", "")), source_url))
    return _city_from_text(" ".join(pieces))


def _parse_eventbrite_candidates(body: str, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    payload = _extract_js_assignment(body, "window.__SERVER_DATA__")
    if not isinstance(payload, dict):
        return []
    results = (((payload.get("search_data") or {}).get("events") or {}).get("results")) or []
    output: list[dict[str, Any]] = []
    for event in results:
        if not isinstance(event, dict) or event.get("is_cancelled"):
            continue
        date_value = str(event.get("start_date", "")).strip()
        time_value = str(event.get("start_time", "09:00")).strip() or "09:00"
        timezone_name = str(event.get("timezone") or source.get("timezone") or "Asia/Shanghai")
        try:
            local_start = datetime.fromisoformat(f"{date_value}T{time_value}:00" if len(time_value) == 5 else f"{date_value}T{time_value}").replace(tzinfo=ZoneInfo(timezone_name))
        except (ValueError, ZoneInfoNotFoundError):
            continue
        start_at = local_start.astimezone(UTC)
        title = str(event.get("name") or "").strip()
        venue = event.get("primary_venue") or {}
        address = venue.get("address") if isinstance(venue, dict) else {}
        address_text = str((address or {}).get("localized_address_display") or (address or {}).get("localized_area_display") or "").strip()
        venue_name = str(venue.get("name") or "").strip() if isinstance(venue, dict) else ""
        location_text = " · ".join(part for part in (venue_name, address_text) if part)
        city = _eventbrite_city(event, source, source_url)
        organizer_id = str(event.get("primary_organizer_id") or "").strip()
        organizer = f"Eventbrite organizer #{organizer_id}" if organizer_id else str(source.get("organizer") or "Eventbrite")
        tags = " ".join(str(item.get("display_name", "")) for item in event.get("tags", []) if isinstance(item, dict))
        summary = str(event.get("summary") or event.get("full_description") or "").strip()
        searchable = f"{title} {tags} {summary}"
        technical_signal = _technical_signal(searchable)
        if "Science & Technology" in tags and not technical_signal:
            technical_signal = "technology"
        canonical_url = str(event.get("url") or "").strip()
        if not (title and start_at and city and location_text and organizer and canonical_url and technical_signal):
            continue
        if not _is_safe_public_url(canonical_url):
            continue
        output.append({"title": title, "start_at": start_at, "timezone": timezone_name, "city": city, "venue": location_text, "organizer": organizer, "canonical_url": canonical_url, "technical_signal": technical_signal, "description": summary or tags, "source_name": source.get("name", "Eventbrite"), "source_url": source_url})
    return output


def _parse_gdg_candidates(body: str, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    script = soup.select_one("#__NEXT_DATA__")
    if not script:
        return []
    try:
        payload = json.loads(script.string or script.get_text())
        page = payload["props"]["pageProps"]
        chapter = page.get("chapterData", {})
        events = page.get("prerenderData", {}).get("upcomingEvents", {}).get("results", [])
    except (TypeError, KeyError, json.JSONDecodeError):
        return []
    output: list[dict[str, Any]] = []
    city = _city_from_text(f"{chapter.get('chapter_location', '')} {source.get('name', '')} {source_url}")
    for event in events:
        if not isinstance(event, dict):
            continue
        start_at = _parse_datetime(event.get("start_date"))
        title = str(event.get("title") or "").strip()
        canonical_url = str(event.get("url") or "").strip()
        description = BeautifulSoup(str(event.get("description") or event.get("description_short") or ""), "html.parser").get_text(" ", strip=True)
        technical_signal = _technical_signal(f"{title} {description}")
        # GDG publishes the venue only after the event page is finalized. Do not infer one from the chapter city.
        if not (start_at and title and canonical_url and city and technical_signal):
            continue
        if not _is_safe_public_url(canonical_url):
            continue
        output.append({"title": title, "start_at": start_at, "timezone": "Asia/Hong_Kong" if city == "香港" else "Asia/Shanghai", "city": city, "venue": "", "organizer": source.get("name", "GDG"), "canonical_url": canonical_url, "technical_signal": technical_signal, "description": description, "source_name": source.get("name", "GDG"), "source_url": source_url})
    return output


def _parse_gosim_candidates(body: str, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    date_match = re.search(r"深圳南山伊敦酒店\s*(20\d{2})年(\d{1,2})月(\d{1,2})-(\d{1,2})日", page_text)
    if not date_match:
        date_match = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})-(\d{1,2})日", page_text)
    if not date_match:
        return []
    year, month, day, _ = (int(value) for value in date_match.groups())
    start_at = datetime(year, month, day, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(UTC)
    title = "GOSIM Shenzhen 2026"
    canonical_url = "https://shenzhen2026.gosim.org/zh/"
    technical_signal = _technical_signal(page_text)
    if not technical_signal:
        return []
    return [{"title": title, "start_at": start_at, "timezone": "Asia/Shanghai", "city": "深圳", "venue": "深圳南山伊敦酒店", "organizer": "GOSIM", "canonical_url": canonical_url, "technical_signal": technical_signal, "description": page_text[:1600], "source_name": source.get("name", "GOSIM"), "source_url": source_url}]


def _parse_sustech_detail_candidates(body: str, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    title_node = soup.select_one("h1, .event-title, .event-main h2, .event-main h3")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    match = re.search(r"时间：\s*(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日\s*(\d{1,2}):(\d{2})", page_text)
    venue_match = re.search(r"地点：\s*(.+?)(?=\s+(?:主办|演讲人|演讲|时间|地点)：|$)", page_text)
    speaker_match = re.search(r"演讲人：\s*(.+?)(?=\s+(?:时间|地点|主办|演讲)：|$)", page_text)
    if not title or not match:
        return []
    year, month, day, hour, minute = (int(value) for value in match.groups())
    start_at = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Shanghai")).astimezone(UTC)
    venue = venue_match.group(1).strip() if venue_match else ""
    speaker = speaker_match.group(1).strip() if speaker_match else ""
    technical_signal = _technical_signal(f"{title} {page_text}")
    if not (venue and technical_signal):
        return []
    return [{"title": title, "start_at": start_at, "timezone": "Asia/Shanghai", "city": "深圳", "venue": venue, "organizer": source.get("organizer", "南方科技大学"), "canonical_url": source_url, "technical_signal": technical_signal, "description": f"演讲人：{speaker}。{page_text[-1200:]}", "source_name": source.get("name", "南方科技大学"), "source_url": source_url}]


def _sustech_detail_links(body: str, source_url: str, limit: int) -> list[str]:
    soup = BeautifulSoup(body, "html.parser")
    links: list[str] = []
    for event_node in soup.select(".added-event"):
        date_value = str(event_node.get("data-time") or "")
        try:
            event_date = datetime.fromisoformat(date_value).date()
        except ValueError:
            continue
        if event_date < datetime.now(ZoneInfo("Asia/Shanghai")).date():
            continue
        holder = event_node.find_next("input", attrs={"type": "hidden"})
        if not holder or not holder.get("value"):
            continue
        href = urljoin(source_url, str(holder.get("value")))
        if href not in links and _is_safe_public_url(href):
            links.append(href)
        if len(links) >= limit:
            break
    return links


def _labeled_value(soup: BeautifulSoup, label: str) -> str:
    parts = [part.strip() for part in soup.stripped_strings if part.strip()]
    for index, part in enumerate(parts):
        match = re.match(rf"^{re.escape(label)}\s*[:：]\s*(.+)$", part)
        if match:
            return match.group(1).strip()
        if part.rstrip(":： ") == label and index + 1 < len(parts):
            return parts[index + 1]
    return ""


def _parse_oshk_candidates(body: str, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    title_node = soup.select_one("h1")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    date_value = _labeled_value(soup, "Date")
    time_value = _labeled_value(soup, "Time")
    venue = _labeled_value(soup, "Venue")
    date_match = re.search(r"(?:\w+,\s*)?(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})", date_value)
    time_match = re.search(r"(\d{1,2}):(\d{2})\s*[–—-]\s*\d{1,2}:\d{2}", time_value)
    if not (title and date_match and time_match and venue):
        return []
    try:
        local_start = datetime.strptime(
            f"{date_match.group(1)} {date_match.group(2)} {date_match.group(3)} {time_match.group(1)}:{time_match.group(2)}",
            "%d %B %Y %H:%M",
        ).replace(tzinfo=ZoneInfo("Asia/Hong_Kong"))
    except ValueError:
        return []
    registration_url = next(
        (anchor.get("href", "") for anchor in soup.select("a[href*='meetup.com/'][href*='/events/']")),
        source_url,
    )
    technical_signal = _technical_signal(f"{title} {page_text}")
    if not technical_signal or not _is_safe_public_url(registration_url):
        return []
    return [{
        "title": title,
        "start_at": local_start.astimezone(UTC),
        "timezone": "Asia/Hong_Kong",
        "city": "香港",
        "venue": venue,
        "organizer": "Open Source Hong Kong",
        "canonical_url": registration_url,
        "technical_signal": technical_signal,
        "description": page_text[:1200],
        "source_name": source.get("name", "Open Source Hong Kong"),
        "source_url": source_url,
    }]


def _parse_cityu_seminar_candidates(body: str, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    output: list[dict[str, Any]] = []
    date_pattern = re.compile(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"(\d{1,2}),\s*(20\d{2}),\s*\w+,\s*(\d{1,2}):(\d{2})\s*(am|pm)",
        re.I,
    )
    for row in soup.select("table tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        event_text = cells[0].get_text(" ", strip=True)
        date_match = date_pattern.search(event_text)
        if not date_match:
            continue
        try:
            local_start = datetime.strptime(
                f"{date_match.group(1)} {date_match.group(2)} {date_match.group(3)} "
                f"{date_match.group(4)}:{date_match.group(5)} {date_match.group(6)}",
                "%B %d %Y %I:%M %p",
            ).replace(tzinfo=ZoneInfo("Asia/Hong_Kong"))
        except ValueError:
            continue
        remainder = event_text[date_match.end():].strip(" ,;:-")
        title = re.split(r"\s+Dr\.?\s+", remainder, maxsplit=1)[0].strip()
        venue = re.split(r"\s+Zoom\s+ID", cells[1].get_text(" ", strip=True), maxsplit=1, flags=re.I)[0].strip(" ,")
        technical_signal = _technical_signal(event_text)
        if not (title and venue and technical_signal):
            continue
        output.append({
            "title": title,
            "start_at": local_start.astimezone(UTC),
            "timezone": "Asia/Hong_Kong",
            "city": "香港",
            "venue": venue,
            "organizer": source.get("organizer", "CityU-CCCN-PolyU Joint Seminars"),
            "canonical_url": f"{source_url}#event-{local_start.date().isoformat()}",
            "technical_signal": technical_signal,
            "description": event_text,
            "source_name": source.get("name", "CityU-CCCN-PolyU Joint Seminars"),
            "source_url": source_url,
        })
    return output


def _parse_eet_event_candidates(body: str, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    title_node = soup.select_one("h1")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    date_match = re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日\s*(\d{1,2}):(\d{2})", page_text)
    venue = _labeled_value(soup, "地点")
    if not (title and date_match and venue):
        return []
    local_start = datetime(
        int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)),
        int(date_match.group(4)), int(date_match.group(5)), tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    technical_signal = _technical_signal(page_text)
    if not technical_signal:
        return []
    return [{
        "title": title,
        "start_at": local_start.astimezone(UTC),
        "timezone": "Asia/Shanghai",
        "city": source.get("city", "广州"),
        "venue": venue,
        "organizer": source.get("organizer", "泰克科技"),
        "canonical_url": source_url,
        "technical_signal": technical_signal,
        "description": page_text[:1200],
        "source_name": source.get("name", "EET China"),
        "source_url": source_url,
    }]


def _parse_rustchinaconf_candidates(body: str, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    if not re.search(r"October\s+15[–-]17,\s*2026", page_text, re.I):
        return []
    venue_match = re.search(r"Aden Hotel Shenzhen Nanshan\s*\(8 Guishan Road, Shekou\)", page_text, re.I)
    if not venue_match:
        return []
    local_start = datetime(2026, 10, 16, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    technical_signal = _technical_signal(page_text)
    if not technical_signal:
        return []
    return [{
        "title": "RustChinaConf 2026 · Shenzhen",
        "start_at": local_start.astimezone(UTC),
        "timezone": "Asia/Shanghai",
        "city": "深圳",
        "venue": venue_match.group(0),
        "organizer": source.get("organizer", "Rust Chinese Community"),
        "canonical_url": source_url,
        "technical_signal": technical_signal,
        "description": page_text[:1200],
        "source_name": source.get("name", "RustChinaConf"),
        "source_url": source_url,
    }]


def _parse_hku_workshop_candidates(body: str, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    title_node = soup.select_one("h1")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    date_match = re.search(r"(?:Day\s+\d+\s+)?(\d{1,2})/(\d{1,2})/(20\d{2})", page_text)
    time_match = re.search(r"(\d{1,2}):(\d{2})\s*AM\s*[-–]\s*\d{1,2}:\d{2}\s*PM", page_text, re.I)
    venue_match = re.search(r"(LE\d+,\s*LG\d+/F\s*[-–]\s*LE\d+,\s*Library Extension Building,\s*Main Campus)", page_text, re.I)
    if not (title and date_match and time_match and venue_match):
        return []
    try:
        local_start = datetime(
            int(date_match.group(3)), int(date_match.group(2)), int(date_match.group(1)),
            int(time_match.group(1)), int(time_match.group(2)), tzinfo=ZoneInfo("Asia/Hong_Kong"),
        )
    except ValueError:
        return []
    technical_signal = _technical_signal(f"{title} {page_text}")
    if not technical_signal:
        return []
    return [{
        "title": title,
        "start_at": local_start.astimezone(UTC),
        "timezone": "Asia/Hong_Kong",
        "city": "香港",
        "venue": venue_match.group(1),
        "organizer": "HKU Techno-Entrepreneurship Core",
        "canonical_url": source_url,
        "technical_signal": technical_signal,
        "description": page_text[:1200],
        "source_name": source.get("name", "HKU QwenCloud Workshop"),
        "source_url": source_url,
    }]


def _parse_hkust_workshop_candidates(body: str, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    page_text = soup.get_text(" ", strip=True)
    title_node = soup.select_one("h1")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    date_match = re.search(r"(\d{1,2})\s+October\s+(20\d{2})", page_text, re.I)
    time_match = re.search(r"(\d{1,2}):(\d{2})\s*[-–]\s*\d{1,2}:\d{2}", page_text)
    venue_match = re.search(r"(The BASE,\s*Room\s*1520A,\s*1/F Academic Building\s*\(Lifts 29-30\))", page_text, re.I)
    if not (title and date_match and time_match and venue_match):
        return []
    try:
        local_start = datetime(
            int(date_match.group(2)), 10, int(date_match.group(1)),
            int(time_match.group(1)), int(time_match.group(2)), tzinfo=ZoneInfo("Asia/Hong_Kong"),
        )
    except ValueError:
        return []
    technical_signal = _technical_signal(f"{title} {page_text}")
    if not technical_signal:
        return []
    return [{
        "title": title,
        "start_at": local_start.astimezone(UTC),
        "timezone": "Asia/Hong_Kong",
        "city": "香港",
        "venue": venue_match.group(1),
        "organizer": "HKUST Entrepreneurship Center",
        "canonical_url": source_url,
        "technical_signal": technical_signal,
        "description": page_text[:1200],
        "source_name": source.get("name", "HKUST QwenCloud Workshop"),
        "source_url": source_url,
    }]


def _parse_candidates(body: str, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    if source.get("format") == "ics" or "BEGIN:VCALENDAR" in body[:1000]:
        return _parse_ics_candidates(body, source, source_url)
    if source.get("format") == "eventbrite":
        return _parse_eventbrite_candidates(body, source, source_url)
    if source.get("format") == "gdg":
        return _parse_gdg_candidates(body, source, source_url)
    if source.get("format") == "gosim":
        return _parse_gosim_candidates(body, source, source_url)
    if source.get("format") == "sustech":
        return _parse_sustech_detail_candidates(body, source, source_url)
    if source.get("format") == "opensource_hk":
        return _parse_oshk_candidates(body, source, source_url)
    if source.get("format") == "cityu_seminars":
        return _parse_cityu_seminar_candidates(body, source, source_url)
    if source.get("format") == "eet_event":
        return _parse_eet_event_candidates(body, source, source_url)
    if source.get("format") == "rustchinaconf":
        return _parse_rustchinaconf_candidates(body, source, source_url)
    if source.get("format") == "hku_workshop":
        return _parse_hku_workshop_candidates(body, source, source_url)
    if source.get("format") == "hkust_workshop":
        return _parse_hkust_workshop_candidates(body, source, source_url)
    soup = BeautifulSoup(body, "html.parser")
    candidates = [_candidate_from_json_ld(node, source, source_url) for node in _json_ld_nodes(soup)]
    parsed = [candidate for candidate in candidates if candidate]
    if parsed:
        return parsed
    return _parse_html_event_cards(soup, source, source_url)


def _parse_html_event_cards(soup: BeautifulSoup, source: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
    """Fallback for public listing/detail pages that omit JSON-LD Event nodes."""
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for time_node in soup.select("time[datetime], [data-start-date], [data-event-date]"):
        raw_start = time_node.get("datetime") or time_node.get("data-start-date") or time_node.get("data-event-date") or ""
        start_at = _parse_datetime(raw_start) or _parse_ics_datetime(raw_start)
        if not start_at:
            continue
        card = time_node
        for _ in range(4):
            if card.parent is None:
                break
            card = card.parent
            text = card.get_text(" ", strip=True)
            if len(text) >= 40:
                break
        title_node = card.select_one("[itemprop='name'], h1, h2, h3, h4, [class*='title'], a")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        if len(title) < 8:
            continue
        link_node = card.select_one("a[href]") or soup.select_one("link[rel='canonical']")
        canonical_url = urljoin(source_url, link_node.get("href", "")) if link_node and link_node.get("href") else source_url
        location_node = card.select_one("[itemprop='location'], [itemprop='address'], [class*='location'], [class*='venue']")
        location = location_node.get_text(" ", strip=True) if location_node else ""
        card_text = card.get_text(" ", strip=True)
        city = _city_from_text(" ".join((location, card_text, source.get("name", "")))) or _city_from_text(source_url)
        organizer_node = card.select_one("[itemprop='organizer'], [class*='organizer'], [class*='host']")
        organizer = organizer_node.get_text(" ", strip=True) if organizer_node else source.get("organizer", "")
        technical_signal = _technical_signal(f"{title} {card_text}")
        if not (city and location and organizer and technical_signal and _is_safe_public_url(canonical_url)):
            continue
        key = f"{canonical_url}|{start_at.isoformat()}|{title}"
        if key in seen:
            continue
        seen.add(key)
        output.append({"title": title, "start_at": start_at, "timezone": "Asia_Hong_Kong" if city == "香港" else "Asia_Macau" if city == "澳门" else "Asia/Shanghai", "city": city, "venue": location, "organizer": organizer, "canonical_url": canonical_url, "technical_signal": technical_signal, "description": card_text[:1200], "source_name": source.get("name", "公开来源"), "source_url": source_url})
    return output


def _discover_detail_links(body: str, source_url: str, limit: int = MAX_DETAIL_LINKS) -> list[str]:
    """Find a small, same-host set of likely event detail pages from a listing page."""
    soup = BeautifulSoup(body, "html.parser")
    source_host = urlparse(source_url).netloc.lower()
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = urljoin(source_url, str(anchor.get("href", "")).strip())
        text = anchor.get_text(" ", strip=True)
        parsed = urlparse(href)
        if not _is_safe_public_url(href) or parsed.netloc.lower() != source_host or href in seen:
            continue
        if "#" in href:
            continue
        if href.split("#", 1)[0].rstrip("/") == source_url.split("#", 1)[0].rstrip("/"):
            continue
        path = parsed.path.lower()
        if DETAIL_EXCLUDE_PATHS.search(path):
            continue
        if path.endswith((".jpg", ".jpeg", ".png", ".gif", ".css", ".js", ".pdf", ".zip")):
            continue
        score = 0
        if DETAIL_PATH_HINTS.search(path):
            score += 3
        if DETAIL_TEXT_HINTS.search(text):
            score += 3
        if re.search(r"20\d{2}|\d{1,2}月|\d{1,2}[-/]\d{1,2}", text):
            score += 2
        if score < 3:
            continue
        seen.add(href)
        ranked.append((score, href))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [href for _, href in ranked[:limit]]


def _make_event_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _canonical_url_allowed(candidate: dict[str, Any], source: dict[str, Any]) -> bool:
    canonical = urlparse(str(candidate.get("canonical_url", "")))
    if not _is_safe_public_url(str(candidate.get("canonical_url", ""))) or not canonical.hostname:
        return False
    hostname = canonical.hostname.lower().rstrip(".")
    reserved_suffixes = (".example", ".test", ".invalid", ".localhost", ".local", ".example.com", ".example.net", ".example.org", ".test.com")
    reserved_hosts = {"example.com", "example.net", "example.org", "test.com", "localhost"}
    if hostname in reserved_hosts or hostname.endswith(reserved_suffixes):
        return False
    source_host = urlparse(str(candidate.get("source_url", ""))).hostname
    allowed_hosts = {str(host).lower().rstrip(".") for host in source.get("canonical_hosts", [])}
    allowed_hosts.update(CANONICAL_HOSTS_BY_FORMAT.get(str(source.get("format", "")), set()))
    return hostname == (source_host or "").lower().rstrip(".") or hostname in allowed_hosts


def _candidate_rank(candidate: dict[str, Any], source: dict[str, Any]) -> tuple[int, int, float, int]:
    completeness = sum(bool(candidate.get(field)) for field in REQUIRED_FACTS)
    confidence = {"high": 3, "medium": 2, "low": 1}.get(str(source.get("priority", "medium")).lower(), 0)
    start_at = candidate.get("start_at")
    days_until = max(0.0, (start_at - datetime.now(UTC)).total_seconds() / 86400) if isinstance(start_at, datetime) else float("inf")
    relevance = len(str(candidate.get("technical_signal", "")).split("；"))
    return completeness, confidence, -days_until, relevance


def _build_candidate_pool(
    candidates: list[tuple[dict[str, Any], dict[str, Any]]],
    limit: int,
    enabled_cities: list[str],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    by_city: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for candidate, source in candidates:
        by_city.setdefault(str(candidate.get("city", "")), []).append((candidate, source))
    for city_candidates in by_city.values():
        city_candidates.sort(key=lambda item: _candidate_rank(item[0], item[1]), reverse=True)
    city_order = [city for city in enabled_cities if city in by_city]
    city_order.extend(sorted(city for city in by_city if city not in city_order))
    pool: list[tuple[dict[str, Any], dict[str, Any]]] = []
    while len(pool) < limit:
        added = False
        for city in city_order:
            if by_city[city]:
                pool.append(by_city[city].pop(0))
                added = True
                if len(pool) >= limit:
                    break
        if not added:
            break
    return pool


def _select_candidates(
    pool: list[tuple[dict[str, Any], dict[str, Any]]],
    total_limit: int,
    city_quotas: dict[str, int],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    city_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    remaining = list(pool)
    while remaining and len(selected) < total_limit:
        eligible = [
            item for item in remaining
            if city_counts.get(str(item[0].get("city", "")), 0) < city_quotas.get(str(item[0].get("city", "")), 0)
        ]
        if not eligible:
            break

        def rank(item: tuple[dict[str, Any], dict[str, Any]]) -> tuple[float, ...]:
            candidate, source = item
            city = str(candidate.get("city", ""))
            source_name = str(candidate.get("source_name", source.get("name", "")))
            quota = max(1, city_quotas.get(city, 1))
            city_gap = -(city_counts.get(city, 0) / quota)
            base = _candidate_rank(candidate, source)
            return (*base[:2], city_gap, *base[2:], -source_counts.get(source_name, 0))

        chosen = max(eligible, key=rank)
        remaining.remove(chosen)
        selected.append(chosen)
        city = str(chosen[0].get("city", ""))
        source_name = str(chosen[0].get("source_name", chosen[1].get("name", "")))
        city_counts[city] = city_counts.get(city, 0) + 1
        source_counts[source_name] = source_counts.get(source_name, 0) + 1
    return selected


def _empty_collection_result() -> dict[str, Any]:
    return {
        "configured_sources": 0,
        "reached_sources": 0,
        "blocked_sources": 0,
        "failed_sources": 0,
        "candidates_seen": 0,
        "verified_candidates": 0,
        "fact_rejected": 0,
        "published_events": 0,
        "published_by_city": {},
        "published_by_source": {},
        "blocked_source_names": [],
        "failed_source_names": [],
        "rejection_reasons": {},
    }


async def _fetch_source(client: httpx.AsyncClient, source: dict[str, Any], session) -> tuple[int, list[dict[str, Any]]]:
    source_url = str(source.get("url", "")).strip()
    source_name = source.get("name", "公开来源")
    if not _is_safe_public_url(source_url):
        session.add(RawDocument(source_name=source_name, source_url=source_url, content_hash="", status_code=400, parser_name="unsafe_source_url", body_preview="source URL must be a public HTTP(S) URL", fetched_at=datetime.now(UTC)))
        return 400, []
    remaining = policy.cooldown_remaining(source_url)
    if remaining:
        session.add(RawDocument(source_name=source_name, source_url=source_url, content_hash="", status_code=429, parser_name="host_cooldown", body_preview=f"host cooling down for {round(remaining)} seconds", fetched_at=datetime.now(UTC)))
        return 429, []
    latest = (await session.execute(select(RawDocument).where(RawDocument.source_url == source_url, RawDocument.parser_name == PARSER_NAME).order_by(RawDocument.fetched_at.desc()))).scalars().first()
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/ld+json"}
    if latest and latest.etag and not source.get("follow_detail_links"):
        headers["If-None-Match"] = latest.etag
    if latest and latest.last_modified and not source.get("follow_detail_links"):
        headers["If-Modified-Since"] = latest.last_modified
    response: httpx.Response | None = None
    final_url = source_url
    denial_reason: str | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response, final_url, denial_reason = await _request_with_redirects(client, source_url, headers)
        except httpx.HTTPError:
            if attempt == MAX_RETRIES:
                session.add(RawDocument(source_name=source_name, source_url=source_url, content_hash="", status_code=599, parser_name="network_error", body_preview="request failed after bounded retries", fetched_at=datetime.now(UTC)))
                return 599, []
            await asyncio.sleep(min(30, 2**attempt + random.uniform(0.5, 1.5)))
            continue
        if denial_reason:
            status_code = _denial_status_code(denial_reason)
            session.add(RawDocument(source_name=source_name, source_url=source_url, content_hash="", status_code=status_code, parser_name=denial_reason, body_preview=f"request skipped: {denial_reason}", fetched_at=datetime.now(UTC)))
            return status_code, []
        if response is None:
            continue
        if response.status_code == 304:
            session.add(RawDocument(source_name=source_name, source_url=source_url, content_hash=latest.content_hash if latest else "", status_code=304, parser_name="conditional_not_modified", body_preview="", etag=latest.etag if latest else None, last_modified=latest.last_modified if latest else None, fetched_at=datetime.now(UTC)))
            return 304, []
        if response.status_code in {401, 403}:
            policy.mark_blocked(source_url, FORBIDDEN_COOLDOWN_SECONDS, f"http_{response.status_code}")
            session.add(RawDocument(source_name=source_name, source_url=source_url, content_hash="", status_code=response.status_code, parser_name="access_denied", body_preview="source denied the collector; host cooldown applied", fetched_at=datetime.now(UTC)))
            return response.status_code, []
        if response.status_code == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            policy.mark_blocked(source_url, min(MAX_RETRY_AFTER_SECONDS, max(RATE_LIMIT_COOLDOWN_SECONDS, retry_after or 0.0)), "http_429")
            session.add(RawDocument(source_name=source_name, source_url=source_url, content_hash="", status_code=429, parser_name="rate_limited", body_preview="rate limit received; host cooldown applied", fetched_at=datetime.now(UTC)))
            return 429, []
        if response.status_code in TRANSIENT_STATUS_CODES and attempt < MAX_RETRIES:
            await asyncio.sleep(min(60, 2**attempt + random.uniform(1.0, 2.5)))
            continue
        break
    if response is None:
        return 599, []
    if len(response.content) > MAX_RESPONSE_BYTES:
        digest = hashlib.sha256(response.content).hexdigest()
        session.add(RawDocument(source_name=source_name, source_url=source_url, content_hash=digest, status_code=response.status_code, parser_name="response_too_large", body_preview="response exceeds 3 MiB safety limit", etag=response.headers.get("ETag"), last_modified=response.headers.get("Last-Modified"), fetched_at=datetime.now(UTC)))
        return 413, []
    body = response.text
    digest = hashlib.sha256(response.content).hexdigest()
    listing_changed = latest is None or latest.content_hash != digest
    session.add(RawDocument(source_name=source_name, source_url=source_url, content_hash=digest, status_code=response.status_code, parser_name=PARSER_NAME, body_preview=body[:2000], etag=response.headers.get("ETag"), last_modified=response.headers.get("Last-Modified"), fetched_at=datetime.now(UTC)))
    if response.status_code >= 400:
        return response.status_code, []
    candidates = _parse_candidates(body, source, final_url)
    if source.get("follow_detail_links") and (listing_changed or not candidates):
        detail_limit = int(source.get("detail_link_limit", MAX_DETAIL_LINKS))
        detail_links = _sustech_detail_links(body, final_url, detail_limit) if source.get("format") == "sustech" else _discover_detail_links(body, final_url, detail_limit)
        for detail_url in detail_links:
            detail_status, detail_candidates = await _fetch_detail_source(client, source, detail_url, session)
            if detail_status < 400:
                candidates.extend(detail_candidates)
    return response.status_code, candidates


async def _fetch_detail_source(client: httpx.AsyncClient, source: dict[str, Any], detail_url: str, session) -> tuple[int, list[dict[str, Any]]]:
    """Fetch one discovered detail page under the same robots, cooldown and size limits."""
    source_name = source.get("name", "公开来源")
    if not _is_safe_public_url(detail_url):
        return 400, []
    response, final_url, denial_reason = await _request_with_redirects(client, detail_url, {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/ld+json"})
    if denial_reason or response is None:
        return 451 if denial_reason and denial_reason.startswith("robots") else 400, []
    if response.status_code >= 400:
        return response.status_code, []
    if len(response.content) > MAX_RESPONSE_BYTES:
        return 413, []
    body = response.text
    digest = hashlib.sha256(response.content).hexdigest()
    session.add(RawDocument(source_name=source_name, source_url=detail_url, content_hash=digest, status_code=response.status_code, parser_name=PARSER_NAME, body_preview=body[:2000], etag=response.headers.get("ETag"), last_modified=response.headers.get("Last-Modified"), fetched_at=datetime.now(UTC)))
    return response.status_code, _parse_candidates(body, source, final_url)


def _source_status_bucket(status_code: int) -> str:
    if 200 <= status_code < 400:
        return "reached"
    if status_code in {401, 403, 429, 451}:
        return "blocked"
    return "failed"


def _denial_status_code(reason: str) -> int:
    if reason == "host_cooldown":
        return 429
    if reason == "robots_denied":
        return 451
    if reason == "robots_unavailable" or reason.startswith("robots_http_"):
        return 503
    return 400


async def collect_events_once() -> dict[str, Any]:
    async with Session() as session:
        _, published_config = await get_config(session)
        sources = [source for source in published_config.document.get("sources", []) if source.get("is_enabled", source.get("enabled", True))]
        result = _empty_collection_result()
        result["configured_sources"] = len(sources)
        result["rejection_reasons"] = {}
        verified: list[tuple[dict[str, Any], dict[str, Any], int]] = []
        seen_event_keys: set[str] = set()
        enabled_city_names = [str(city.get("name", "")) for city in published_config.document.get("cities", []) if city.get("is_enabled", city.get("enabled", True))]
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "CityActivi/0.1 (+public event collector)"}) as client:
            for source in sources:
                try:
                    status_code, candidates = await _fetch_source(client, source, session)
                except httpx.HTTPError:
                    result["failed_sources"] += 1
                    result["failed_source_names"].append(source.get("name", "公开来源"))
                    continue
                bucket = _source_status_bucket(status_code)
                if bucket == "reached":
                    result["reached_sources"] += 1
                elif bucket == "blocked":
                    result["blocked_sources"] += 1
                    result["blocked_source_names"].append(source.get("name", "公开来源"))
                else:
                    result["failed_sources"] += 1
                    result["failed_source_names"].append(source.get("name", "公开来源"))
                result["candidates_seen"] += len(candidates)
                for candidate in candidates:
                    event_key = _make_event_key(candidate["canonical_url"])
                    if event_key in seen_event_keys:
                        result["rejection_reasons"]["DUPLICATE_CANDIDATE"] = result["rejection_reasons"].get("DUPLICATE_CANDIDATE", 0) + 1
                        continue
                    seen_event_keys.add(event_key)
                    allowed_canonical_hosts = list(source.get("canonical_hosts", [])) + list(CANONICAL_HOSTS_BY_FORMAT.get(str(source.get("format", "")), set()))
                    evidence = {field: {"source_url": candidate["source_url"], "canonical_url": candidate["canonical_url"], "captured_at": datetime.now(UTC).isoformat(), "status_code": status_code, "allowed_canonical_hosts": allowed_canonical_hosts} for field in REQUIRED_FACTS}
                    if not _canonical_url_allowed(candidate, source):
                        result["fact_rejected"] += 1
                        reason = "CANONICAL_URL_NOT_ALLOWLISTED"
                        result["rejection_reasons"][reason] = result["rejection_reasons"].get(reason, 0) + 1
                        continue
                    gate_errors = evaluate_publication(candidate, evidence)
                    if gate_errors:
                        result["fact_rejected"] += 1
                        for reason in gate_errors:
                            result["rejection_reasons"][reason] = result["rejection_reasons"].get(reason, 0) + 1
                        continue
                    if enabled_city_names and candidate.get("city") not in enabled_city_names:
                        result["fact_rejected"] += 1
                        reason = "CITY_NOT_CONFIGURED"
                        result["rejection_reasons"][reason] = result["rejection_reasons"].get(reason, 0) + 1
                        continue
                    verified.append((candidate, source, status_code))
        result["verified_candidates"] = len(verified)
        target_count = max(0, int(published_config.document.get("target_count", 15)))
        city_quotas = {
            str(city.get("name", "")): max(0, int(city.get("target_count", city.get("quota", DEFAULT_CITY_QUOTA))))
            for city in published_config.document.get("cities", [])
            if city.get("is_enabled", city.get("enabled", True))
        }
        pool = _build_candidate_pool(
            [(candidate, source) for candidate, source, _ in verified],
            DEFAULT_CANDIDATE_POOL_TARGET,
            enabled_city_names,
        )
        if len(pool) < len(verified):
            result["rejection_reasons"]["CANDIDATE_POOL_LIMIT"] = len(verified) - len(pool)
        selected = _select_candidates(pool, target_count, city_quotas)
        selected_keys = {_make_event_key(candidate["canonical_url"]) for candidate, _ in selected}
        selected_by_city: dict[str, int] = {}
        for candidate, _ in selected:
            city = str(candidate.get("city", ""))
            selected_by_city[city] = selected_by_city.get(city, 0) + 1
        for candidate, _ in pool:
            if _make_event_key(candidate["canonical_url"]) in selected_keys:
                continue
            city = str(candidate.get("city", ""))
            reason = "CITY_QUOTA" if selected_by_city.get(city, 0) >= city_quotas.get(city, 0) else "TOTAL_TARGET_LIMIT"
            result["rejection_reasons"][reason] = result["rejection_reasons"].get(reason, 0) + 1
        status_by_key = {_make_event_key(candidate["canonical_url"]): status_code for candidate, _, status_code in verified}
        for candidate, source in selected:
            event_key = _make_event_key(candidate["canonical_url"])
            status_code = status_by_key[event_key]
            allowed_canonical_hosts = list(source.get("canonical_hosts", [])) + list(CANONICAL_HOSTS_BY_FORMAT.get(str(source.get("format", "")), set()))
            evidence = {field: {"source_url": candidate["source_url"], "canonical_url": candidate["canonical_url"], "captured_at": datetime.now(UTC).isoformat(), "status_code": status_code, "allowed_canonical_hosts": allowed_canonical_hosts} for field in REQUIRED_FACTS}
            existing = (await session.execute(select(Event).where(Event.event_key == event_key))).scalar_one_or_none()
            fact = EventFactVersion(event_key=event_key, title=candidate["title"], start_at=candidate["start_at"], timezone=candidate["timezone"], city=candidate["city"], venue=candidate["venue"], organizer=candidate["organizer"], canonical_url=candidate["canonical_url"], technical_signal=candidate["technical_signal"], evidence=evidence)
            enrichment = EventEnrichmentVersion(event_key=event_key, summary=candidate["description"][:1200] or f"围绕{candidate['technical_signal']}展开。", calendar_summary=f"{candidate['technical_signal']} · {candidate['organizer']}", why_worth=f"公开详情页包含可核验的技术主题：{candidate['technical_signal']}。", takeaways=["查看公开议程与技术主题", "记录适合继续深挖的工程方法"], prerequisites=["阅读活动原文议程", "确认地点和开始时间"], topic=candidate["technical_signal"], kind="网络抓取", relevance="中高含金量", commute_minutes=None, community=candidate["city"], source_name=candidate["source_name"])
            session.add_all([fact, enrichment])
            await session.flush()
            if existing:
                old_status = existing.status
                existing.current_fact_version_id = fact.id
                existing.current_enrichment_version_id = enrichment.id
                existing.status = "published"
            else:
                existing = Event(event_key=event_key, status="published", current_fact_version_id=fact.id, current_enrichment_version_id=enrichment.id, published_at=datetime.now(UTC))
                session.add(existing)
                old_status = None
            await session.flush()
            session.add(EventVersion(event_key=event_key, fact_version_id=fact.id, enrichment_version_id=enrichment.id, published_at=datetime.now(UTC)))
            session.add(EventStatusChange(event_key=event_key, old_status=old_status, new_status="published", trigger_source="network_collector", evidence=evidence, observed_at=datetime.now(UTC)))
            result["published_events"] += 1
            result["published_by_city"][candidate["city"]] = result["published_by_city"].get(candidate["city"], 0) + 1
            source_name = str(candidate.get("source_name") or source.get("name") or "公开来源")
            result["published_by_source"][source_name] = result["published_by_source"].get(source_name, 0) + 1
        await session.commit()
        return result
