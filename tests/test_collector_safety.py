import unittest

import httpx

from backend.app import collector
from backend.app.main import evaluate_publication


class CollectorSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_redirects_are_rechecked_and_followed_boundedly(self) -> None:
        requests: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            if request.url.path == "/robots.txt":
                return httpx.Response(404, request=request)
            if request.url.path == "/start":
                return httpx.Response(302, headers={"Location": "/final"}, request=request)
            return httpx.Response(200, text="ok", request=request)

        policy = collector.CrawlPolicy()
        original_policy = collector.policy
        collector.policy = policy

        async def fast_wait(*_args, **_kwargs) -> None:
            return None

        policy.wait_for_host = fast_wait  # type: ignore[method-assign]
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                response, final_url, denial = await collector._request_with_redirects(client, "https://example.com/start", {"User-Agent": collector.USER_AGENT})
        finally:
            collector.policy = original_policy

        self.assertEqual(response.status_code if response else None, 200)
        self.assertEqual(final_url, "https://example.com/final")
        self.assertIsNone(denial)
        self.assertEqual(requests, ["https://example.com/robots.txt", "https://example.com/start", "https://example.com/final"])

    async def test_rate_limit_is_not_immediately_retried(self) -> None:
        requests: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(str(request.url))
            if request.url.path == "/robots.txt":
                return httpx.Response(404, request=request)
            return httpx.Response(429, headers={"Retry-After": "120"}, request=request)

        policy = collector.CrawlPolicy()
        original_policy = collector.policy
        collector.policy = policy

        async def fast_wait(*_args, **_kwargs) -> None:
            return None

        policy.wait_for_host = fast_wait  # type: ignore[method-assign]
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                response, final_url, denial = await collector._request_with_redirects(client, "https://example.com/events", {"User-Agent": collector.USER_AGENT})
        finally:
            collector.policy = original_policy

        self.assertEqual(response.status_code if response else None, 429)
        self.assertEqual(final_url, "https://example.com/events")
        self.assertIsNone(denial)
        self.assertEqual(requests, ["https://example.com/robots.txt", "https://example.com/events"])
        policy.mark_blocked(final_url, 120, "http_429")
        self.assertGreater(policy.cooldown_remaining(final_url), 100)

    async def test_unavailable_robots_is_not_mislabeled_as_denied(self) -> None:
        policy = collector.CrawlPolicy()
        original_policy = collector.policy
        collector.policy = policy

        async def fast_wait(*_args, **_kwargs) -> None:
            return None

        policy.wait_for_host = fast_wait  # type: ignore[method-assign]
        try:
            def handler(request: httpx.Request) -> httpx.Response:
                raise httpx.ConnectError("proxy unavailable", request=request)

            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                allowed, _ = await policy.allowed(client, "https://example.com/events")
        finally:
            collector.policy = original_policy

        self.assertFalse(allowed)
        self.assertEqual(policy.denial_reasons[policy.host_key("https://example.com/events")], "robots_unavailable")

    def test_private_and_local_urls_are_rejected(self) -> None:
        self.assertFalse(collector._is_safe_public_url("http://127.0.0.1:8000/events"))
        self.assertFalse(collector._is_safe_public_url("http://localhost/events"))
        self.assertFalse(collector._is_safe_public_url("http://192.168.1.10/events"))
        self.assertTrue(collector._is_safe_public_url("https://example.com/events"))
        self.assertEqual(collector._parse_retry_after("120"), 120.0)

    def test_collection_result_contract_is_stable(self) -> None:
        self.assertEqual(
            set(collector._empty_collection_result()),
            {
                "configured_sources", "reached_sources", "blocked_sources", "failed_sources",
                "candidates_seen", "verified_candidates", "fact_rejected", "published_events",
                "published_by_city", "published_by_source", "blocked_source_names",
                "failed_source_names", "rejection_reasons",
            },
        )

    def test_canonical_urls_require_source_host_or_explicit_allowlist(self) -> None:
        source = {"url": "https://publisher.org/events", "name": "Publisher"}
        candidate = {"source_url": source["url"], "canonical_url": "https://publisher.example/events/1"}
        candidate["canonical_url"] = "https://publisher.org/events/1"
        self.assertTrue(collector._canonical_url_allowed(candidate, source))
        candidate["canonical_url"] = "https://events.example.com/demo"
        self.assertFalse(collector._canonical_url_allowed(candidate, source))
        candidate["canonical_url"] = "https://www.meetup.com/publisher/events/1"
        source["format"] = "opensource_hk"
        self.assertTrue(collector._canonical_url_allowed(candidate, source))
        self.assertIn("CANONICAL_URL_RESERVED_HOST", evaluate_publication(
            {"canonical_url": "https://events.example.com/demo", "timezone": "Asia/Shanghai"},
            {"canonical_url": {}},
        ))
        self.assertIn("CANONICAL_SOURCE_URL_MISSING", evaluate_publication(
            {"canonical_url": "https://publisher.org/events/1", "timezone": "Asia/Shanghai"},
            {"canonical_url": {}},
        ))
        self.assertIn("INVALID_IANA_TIMEZONE", evaluate_publication(
            {"canonical_url": "https://publisher.org/events/1", "timezone": ""},
            {"canonical_url": {"source_url": "https://publisher.org/events/1"}},
        ))

    def test_candidate_selection_respects_city_quota_and_source_diversity(self) -> None:
        now = collector.datetime.now(collector.UTC)
        source_a = {"name": "Publisher A", "priority": "high"}
        source_b = {"name": "Publisher B", "priority": "medium"}
        candidates = [
            ({"city": "深圳", "source_name": "Publisher A", "start_at": now, "technical_signal": "Agent"}, source_a),
            ({"city": "深圳", "source_name": "Publisher A", "start_at": now, "technical_signal": "LLM"}, source_a),
            ({"city": "广州", "source_name": "Publisher B", "start_at": now, "technical_signal": "AI"}, source_b),
        ]
        pool = collector._build_candidate_pool(candidates, 12, ["深圳", "广州"])
        selected = collector._select_candidates(pool, 2, {"深圳": 1, "广州": 1})
        self.assertEqual({candidate[0]["city"] for candidate in selected}, {"深圳", "广州"})

    def test_detail_discovery_excludes_non_event_links(self) -> None:
        body = """
        <a href="/zh/speakers/ai-researcher/">AI Researcher</a>
        <a href="/zh/sponsors/ai-company/">AI Company</a>
        <a href="/zh/schedule/agentic-ai-summit/">Agentic AI Summit</a>
        <a href="/zh/schedule/#tracks">Tracks</a>
        """
        links = collector._discover_detail_links(body, "https://shenzhen2026.gosim.org/zh/schedule/", limit=10)
        self.assertEqual(links, ["https://shenzhen2026.gosim.org/zh/schedule/agentic-ai-summit/"])

    def test_public_ics_events_are_parsed_with_fact_fields(self) -> None:
        body = """BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;TZID=Asia/Shanghai:20261016T190000\nSUMMARY:深圳 Agent 工程实践夜\nLOCATION:深圳 南山科技园\nORGANIZER;CN=AI Builders Shenzhen:mailto:test@example.com\nURL:https://example.com/events/agent-night\nDESCRIPTION:Agent LLM 推理与工程实践\nEND:VEVENT\nEND:VCALENDAR\n"""
        candidates = collector._parse_candidates(body, {"name": "SZDIY", "format": "ics", "timezone": "Asia/Shanghai"}, "https://example.com/calendar.ics")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["organizer"], "AI Builders Shenzhen")
        self.assertEqual(candidates[0]["city"], "深圳")

    def test_html_listing_fallback_uses_visible_event_card(self) -> None:
        body = """
        <article><h2><a href="/events/robotics">具身智能机器人工作坊</a></h2>
          <time datetime="2026-10-18T14:00:00+08:00">10月18日</time>
          <div class="location">深圳大学城</div><div class="organizer">深圳机器人社区</div>
          <p>VLA 机器人 视觉语言动作与机械臂</p>
        </article>
        """
        candidates = collector._parse_candidates(body, {"name": "公开活动页"}, "https://example.com/events")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["venue"], "深圳大学城")
        self.assertEqual(candidates[0]["city"], "深圳")

    def test_eventbrite_server_data_parser_extracts_public_event_facts(self) -> None:
        body = '''<script>window.__SERVER_DATA__ = {"search_data":{"events":{"results":[{"name":"AI Agent Workshop","start_date":"2026-10-08","start_time":"19:00","timezone":"Asia/Shanghai","url":"https://www.eventbrite.com/e/agent-workshop-tickets-1","primary_organizer_id":"123","primary_venue":{"name":"南山科技园","address":{"city":"深圳市","localized_address_display":"深圳市南山区科技园"}},"locations":[{"name":"Shenzhen"}],"tags":[{"display_name":"Science & Technology"},{"display_name":"Agent"}],"summary":"LLM and agent engineering"}]}}}};</script>'''
        candidates = collector._parse_candidates(body, {"name": "Eventbrite 深圳", "format": "eventbrite"}, "https://www.eventbrite.com/d/china--shenzhen/technology--events/")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["city"], "深圳")
        self.assertIn("Eventbrite organizer #123", candidates[0]["organizer"])

    def test_sustech_detail_parser_keeps_only_complete_fact_pages(self) -> None:
        body = '''<main class="event-main"><h1>人工智能与热管理材料研究发展</h1><div>时间：2026年10月06日 14:00</div><div>地点：工学院南楼 813 会议室</div><div>演讲人：张三</div><p>人工智能、材料、机器学习与工程研究</p></main>'''
        candidates = collector._parse_candidates(body, {"name": "南方科技大学", "format": "sustech", "organizer": "南方科技大学"}, "https://www.sustech.edu.cn/zh/events/10270.html")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["venue"], "工学院南楼 813 会议室")

    def test_gosim_public_page_produces_one_complete_conference_fact(self) -> None:
        body = "<main>GOSIM Shenzhen 2026 相约深圳 深圳南山伊敦酒店 2026年10月16-17日 与开源 AI、机器人、边缘系统和开发者基础设施领域的建设者相聚</main>"
        candidates = collector._parse_candidates(body, {"name": "GOSIM Shenzhen", "format": "gosim"}, "https://shenzhen2026.gosim.org/zh/schedule/")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["venue"], "深圳南山伊敦酒店")
        self.assertEqual(candidates[0]["canonical_url"], "https://shenzhen2026.gosim.org/zh/")

    def test_cityu_seminar_parser_extracts_updated_topic_and_unique_event_url(self) -> None:
        body = """<table><tr><td>October 9, 2026, Friday, 4:30pm Graph Intelligence for Blockchain: From Complex Network Analysis to Agentic AI Dr Bishenghui Tao, Hong Kong Metropolitan University</td><td>FYW-3316, CityU Zoom ID: 859 8869 4437</td></tr></table>"""
        source_url = "https://www.ee.cityu.edu.hk/~cccn/centre-seminars.htm"
        candidates = collector._parse_candidates(body, {"name": "CityU seminars", "format": "cityu_seminars"}, source_url)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["title"], "Graph Intelligence for Blockchain: From Complex Network Analysis to Agentic AI")
        self.assertEqual(candidates[0]["start_at"].isoformat(), "2026-10-09T08:30:00+00:00")
        self.assertEqual(candidates[0]["canonical_url"], f"{source_url}#event-2026-10-09")

    def test_oshk_parser_reads_date_time_and_meetup_registration_link(self) -> None:
        body = """<h1>OSHK Oct event – Agentic AI Platform Open Jiuwen &amp; Hermes Agent</h1><p>Date: Thursday, 8 October 2026</p><p>Time: 19:00–21:00</p><p>Venue: Le Bureau, Central, Hong Kong</p><a href="https://www.meetup.com/opensourcehk/events/316553747/">Register</a><p>AI agents and open-source inference</p>"""
        candidates = collector._parse_candidates(body, {"name": "OSHK", "format": "opensource_hk"}, "https://opensource.hk/event")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["start_at"].isoformat(), "2026-10-08T11:00:00+00:00")
        self.assertEqual(candidates[0]["canonical_url"], "https://www.meetup.com/opensourcehk/events/316553747/")

    def test_hku_and_hkust_workshop_parsers_extract_local_start_time(self) -> None:
        hku = """<h1>QwenCloud AI Builder Workshop</h1><p>Day 2 13/10/2026</p><p>09:30AM - 12:30 PM</p><p>LE6, LG2/F – LE6, Library Extension Building, Main Campus</p><p>Qwen Cloud vision and multimodal AI</p>"""
        hkust = """<h1>ENTREPRENEURS' TOOLBOX SERIES: QWENCLOUD AI BUILDER WORKSHOP</h1><p>14 October 2026 (Wed)</p><p>14 Oct 2026 13:30 - 16:30</p><p>The BASE, Room 1520A, 1/F Academic Building (Lifts 29-30)</p><p>Qwen models, AI Skill and AI Agent</p>"""
        hku_candidates = collector._parse_candidates(hku, {"name": "HKU", "format": "hku_workshop"}, "https://tec.hku.hk/workshop")
        hkust_candidates = collector._parse_candidates(hkust, {"name": "HKUST", "format": "hkust_workshop"}, "https://ec.hkust.edu.hk/workshop")
        self.assertEqual(hku_candidates[0]["start_at"].isoformat(), "2026-10-13T01:30:00+00:00")
        self.assertEqual(hkust_candidates[0]["start_at"].isoformat(), "2026-10-14T05:30:00+00:00")

    def test_eet_and_rustchinaconf_parsers_extract_future_events(self) -> None:
        eet = """<h1>泰克先进测试技术研讨会-广州站（10月13日）</h1><p>时间：2026年10月13日 9:00-16:40</p><p>地点：广州粤海喜来登酒店 7楼钻石厅</p><p>AI高速互联总线和具身机器人测试</p>"""
        rust = """<h1>RustChinaConf 2026</h1><p>October 15–17, 2026 · Shenzhen, China</p><p>Aden Hotel Shenzhen Nanshan (8 Guishan Road, Shekou)</p><p>Rust AI, inference, Agent and production systems</p>"""
        eet_candidates = collector._parse_candidates(eet, {"name": "EET", "format": "eet_event", "city": "广州"}, "https://www.eet-china.com/mp/a525102.html")
        rust_candidates = collector._parse_candidates(rust, {"name": "RustChinaConf", "format": "rustchinaconf"}, "https://rustchinaconf.org/schedule/")
        self.assertEqual(eet_candidates[0]["start_at"].isoformat(), "2026-10-13T01:00:00+00:00")
        self.assertEqual(rust_candidates[0]["start_at"].isoformat(), "2026-10-16T01:30:00+00:00")


if __name__ == "__main__":
    unittest.main()
