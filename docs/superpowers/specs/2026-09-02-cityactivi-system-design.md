# CityActivi System Design

## 1. Document Purpose

This document converts the approved CityActivi prototype into an implementation-ready design. The existing prototype is the product baseline. Its activity page, five configuration sections, copy, primary navigation, inline editing pattern, and core user flow remain unchanged.

The five prototype configuration sections are the product's **operations configuration**:

1. 搜寻范围
2. 时间与地点
3. 主题偏好
4. 展示字段
5. 推送与自动化

There is no separate operations console in the first release. Model credentials, crawler concurrency, database connections, and infrastructure retry limits are technical deployment settings and do not appear in the prototype configuration page.

## 2. Product Boundary

### 2.1 Activity Page

The activity page displays processed activity results only. It contains:

- A calendar overview starting on Monday.
- A configured time-range switch such as 15, 30, or 60 days.
- Dynamic filters derived from configured cities, topics, and activity types.
- A detailed activity list below the calendar.
- Direct links to the canonical activity or registration page.

It does not edit search rules, sources, prompts, or notification channels.

### 2.2 Configuration Page

The configuration page controls what the assistant searches, how it judges activities, what it displays, and where it sends results. Editing remains inline inside the current configuration card. It does not use a side drawer or a modal for routine editing.

### 2.3 Fixed Product Rules

The following rules cannot be disabled by operations configuration:

- An activity must have a verifiable title, start time, city, organizer, and technical description.
- Expired activities are not newly published.
- A generated summary cannot override factual source fields.
- Secrets are never returned to the browser after saving.
- Every published activity retains its source evidence.

## 3. Technical Architecture

```text
Vue 3 frontend
  -> FastAPI HTTP API
  -> PostgreSQL
  -> Python scheduler and workers
       -> configured source collectors
       -> intelligent discovery Agent
       -> extraction and normalization
       -> duplicate detection and field merge
       -> LLM structured summary
       -> evidence validation and scoring
       -> publication and notification
```

### 3.1 Selected Stack

| Technology | Chinese meaning | Responsibility | Java analogy |
| --- | --- | --- | --- |
| Vue 3 | 前端框架 | Activity and configuration pages | Similar role to a browser-side UI framework |
| TypeScript | 带类型的 JavaScript | Frontend data contracts and safer refactoring | Java-like static type checking for frontend code |
| Vite | 前端构建工具 | Local development and production bundle | Similar role to a fast frontend build runner |
| Pinia | Vue 状态管理 | Draft configuration and shared page state | Similar to an application-scoped state service |
| FastAPI | Python Web framework | HTTP API and request handling | Similar role to Spring Boot controllers |
| Pydantic | 数据模型与校验 | Validate API and LLM structured output | Similar to DTO plus Bean Validation |
| SQLAlchemy | Python database toolkit/ORM | Database queries and transactions | Closer to JPA/Hibernate than MyBatis |
| Alembic | 数据库迁移工具 | Version database schema changes | Similar to Flyway or Liquibase |
| PostgreSQL | 关系型数据库 | Configurations, activities, evidence, jobs | Similar usage to MySQL/PostgreSQL in Java systems |
| Nginx | Web and reverse-proxy server | HTTPS entry, static files, API forwarding | Deployment gateway, not application code |
| Docker Compose | Multi-container deployment description | Start frontend, API, worker, and database | Similar to an executable local deployment manifest |

## 4. Configuration Lifecycle

### 4.1 Three States

| State | Meaning | Affects search jobs |
| --- | --- | --- |
| Published | 当前正式版本 | Yes |
| Draft | 页面中尚未发布的修改 | No |
| Job snapshot | 某次任务启动时复制的完整配置 | Only that job |

Saving an inline card updates the draft. Clicking `发布更新` validates the complete draft and creates a new immutable published version. A running job continues using its original snapshot. A later job uses the newly published version.

### 4.2 Publish Actions

The existing top-right action keeps its position and gains real behavior:

- `发布更新`: publish configuration; the next scheduled job uses it.
- Secondary menu `发布并立即运行`: publish and create a new job immediately.
- `预览页面`: render the activity page using current draft display settings without changing search results.

If validation fails, the page stays on the current section and marks the exact card and field. Valid cards are not discarded.

### 4.3 Concurrent Editing

Each draft carries a `version_number`. Publishing checks whether the underlying published version has changed. If another session published first, the API returns a conflict and shows which configuration items changed. The system never silently overwrites a newer version.

## 5. Operations Configuration: 搜寻范围

### 5.1 Basic Range

| Field | Type | Default | Execution effect |
| --- | --- | --- | --- |
| 检索区域 | Preset selector | 大湾区 | Supplies a display name and suggested city list |
| 目标数量 | Selector | 12 | Maximum published results after ranking |

A region is a preset, not a permanent city rule. Selecting 大湾区 suggests Shenzhen, Guangzhou, Hong Kong, Zhuhai, and Macau. Operations users may then remove, add, or reorder cities.

### 5.2 Target Audience Cards

Each target audience card contains:

| Field | Required | Description |
| --- | --- | --- |
| Name | Yes | Human-readable audience, such as AI engineer |
| Keywords | Yes | Terms used for relevance matching |
| Priority | Yes | High, medium, or low contribution to scoring |
| Enabled | Yes | Disabled cards remain stored but do not affect jobs |

Audience keywords do not directly prove that an activity is relevant. They contribute to candidate scoring only after the activity has a verifiable agenda or technical description.

### 5.3 Public Source Cards

Each source becomes a real editable collection item instead of a hardcoded row.

| Field | Required | Options or behavior |
| --- | --- | --- |
| Name | Yes | Luma, a university page, a community site, etc. |
| Source type | Yes | Activity platform, community/project, academic, company, other |
| Collection mode | Yes | Direct page, site search, discovery only |
| Entry URL | Yes for direct/site search | Public source address |
| Covered cities | Yes | Multi-select from configured cities |
| Priority | Yes | Controls task order and search budget, not factual trust |
| Enabled | Yes | Whether the source participates in new jobs |

Collection modes:

- `direct_page`: fetch a known list or organizer page.
- `site_search`: search within the configured domain using generated queries.
- `discovery_only`: use the source as a clue; publishing still requires a canonical source page.

### 5.4 Intelligent Discovery

Intelligent discovery appears below public sources inside the same section. It is not a new navigation item.

| Field | Default | Meaning |
| --- | --- | --- |
| Enabled | On | Allow the Agent to find activities missed by fixed sources |
| Maximum candidates | 30 | Maximum discovery clues per run |
| Allowed domains | Empty | Optional domains the Agent may prioritize |
| Blocked domains | Empty | Domains that cannot become evidence |
| Official-source required | On, fixed | Candidate cannot publish without a canonical page |

The Agent may generate search queries, search, open pages, and identify canonical pages. It cannot directly create a published activity or write final factual values.

## 6. Operations Configuration: 时间与地点

### 6.1 Automation Schedule

| Field | Options | Behavior |
| --- | --- | --- |
| Frequency | Daily, weekdays, weekly Monday | Creates jobs according to local timezone |
| Run time | Configured time options | Stored as local wall-clock time |
| Timezone | Asia/Shanghai by default | Used for scheduling and display |
| Coverage days | 7, 15, 30, 60 | Search window beginning at run-day 00:00 |

The implementation must remove the prototype's hardcoded reference date. Every job calculates its window from the actual execution time and stored timezone.

### 6.2 Commute Origin

| Field | Required | Description |
| --- | --- | --- |
| Origin name | Yes | Display name such as 深大地铁站 |
| Address | Yes | Searchable address |
| Coordinates | Generated | Latitude and longitude returned by map provider |
| Travel mode | Yes | Transit, driving, walking, cycling |
| Map provider | Yes | Amap for mainland China; Google may be selected for supported regions |

The system stores coordinates after address selection. Commute time comes from a map-routing API and includes provider, calculation time, duration, distance, and travel mode. It must not use simulated fixed offsets.

### 6.3 City Rule Cards

Cities are editable collection items, not fixed Shenzhen/Guangzhou rows.

| Field | Description |
| --- | --- |
| City | Standard city identifier and display name |
| Inclusion threshold | High only, high and medium, or excluded |
| Maximum commute | Optional duration limit |
| Priority | Search allocation priority |
| Enabled | Participate in future jobs |

A commute limit is applied after venue coordinates are available. Missing coordinates do not automatically reject an otherwise high-confidence activity; the activity is marked `commute unavailable` and evaluated by its city threshold.

## 7. Operations Configuration: 主题偏好

### 7.1 Priority Topics

Each topic includes name, keywords, priority, and enabled state. Topics drive query planning, relevance scoring, page filters, and labels. They do not replace evidence extraction.

### 7.2 Weak-Content Rules

Each rule includes name, matching terms, penalty level, and enabled state. A match lowers the score but does not automatically delete an activity when strong technical agenda evidence exists.

### 7.3 Activity Types

Activity type cards define the filter vocabulary shown on the activity page, such as industry, academic, and open source. A type may include a description and matching hints. The backend classifies an event only when evidence supports the classification.

### 7.4 Sorting

Supported sort dimensions are date/start time, technical relevance, and commute distance. The primary and secondary dimensions cannot be identical. Final deterministic tie-breakers are start time and event ID.

### 7.5 Fixed Technical Rule

The existing fixed rule remains: a candidate must include a verifiable technical topic or agenda. Generic business, recruitment, or trend content cannot pass only because it matches a configured keyword.

## 8. Operations Configuration: 展示字段

### 8.1 Fixed Fields

Date/time, title, location, and organizer remain mandatory. If any cannot be verified, the candidate is not published.

### 8.2 Optional Fields

Community, technical direction, source, why it is worth attending, commute, registration count, cost, source link, cover, takeaways, and prerequisites remain individually configurable.

Configuration changes presentation only. Turning off `commute` does not stop route calculation if commute is used for filtering. Turning off `source` does not remove evidence records.

### 8.3 Summary Detail

| Option | Activity page output |
| --- | --- |
| Full excerpt | At least three meaningful lines when source material is sufficient |
| Standard summary | One to two sentences |
| One line | A compact factual sentence |

`Why worth attending` is the primary analysis block. It should identify organizer credibility, agenda depth, practical outcome, and audience fit. `Takeaways` and `Prerequisites` must be concrete lists, not generic model language.

### 8.4 Missing Values

When automatic hiding is enabled, absent optional fields do not render placeholders or empty layout regions. The page does not reserve image space when no valid cover exists.

## 9. Operations Configuration: 推送与自动化

### 9.1 Channel Cards

| Field | Description |
| --- | --- |
| Channel name | User-defined recognizable name |
| Channel type | Feishu, ServerChan, generic Webhook |
| Endpoint | Webhook URL or service endpoint |
| Secret | Feishu signature secret or ServerChan SendKey |
| Enabled | Whether future jobs send to this channel |
| Delivery scope | All selected results or high-value results only |

One profile may have multiple channels of the same type. Every channel supports `test connection`, `disable`, `clear secret`, and `delete`. Clearing a secret requires explicit confirmation; disabling a channel retains its settings.

After saving, the API returns only `secret_configured: true/false`. It never returns the saved secret text.

### 9.2 Automation Status

The current summary shows automation name, schedule, active configuration version, last run, next run, and last result. `本地预检` becomes `运行预检` in production and checks configuration validity, source reachability, map provider, model access, and enabled notification channels without publishing activities.

## 10. Activity Page Behavior Derived from Configuration

| Activity-page element | Configuration source |
| --- | --- |
| Date range selector | Published coverage days |
| Calendar city labels | Enabled city rules |
| Topic filter | Enabled priority topics discovered in published events |
| Type filter | Enabled activity types |
| Result limit | Target count |
| Detail fields | Display fields |
| Summary length | Summary detail option |
| High-value marker | Scoring threshold and confidence |
| Commute display | Origin, route result, and display toggle |

If coverage is 60 days, the page offers 15, 30, and 60-day views. It cannot show a range longer than the published search coverage. The calendar initially displays a compact range and provides smooth expand/collapse without rerunning the search.

## 11. Job Workflow

```text
PENDING
  -> DISCOVERING
  -> FETCHING
  -> EXTRACTING
  -> MERGING
  -> SUMMARIZING
  -> VERIFYING
  -> RANKING
  -> PUBLISHING
  -> NOTIFYING
  -> COMPLETED
```

| State | Responsibility | Recoverable failure behavior |
| --- | --- | --- |
| PENDING | Job waits for worker | Another worker may claim it after lease expiry |
| DISCOVERING | Build queries and candidate URLs | Failed source does not stop other sources |
| FETCHING | Download public pages | Retry transient network errors |
| EXTRACTING | Parse factual fields | Store failure reason and raw document |
| MERGING | Detect duplicates and combine evidence | Conflicts go to verification |
| SUMMARIZING | Generate structured analysis | Retry once; never fabricate missing facts |
| VERIFYING | Check claims against evidence | Reject or mark candidate for review |
| RANKING | Apply published scoring rules | Deterministic calculation |
| PUBLISHING | Create event versions | Database transaction prevents partial publication |
| NOTIFYING | Send configured messages | Failure does not roll back published activities |

## 12. Search Planning

The planner reads the immutable job snapshot and produces bounded tasks. It does not create the full Cartesian product of every city, topic, audience, and source.

Planning order:

1. Allocate a search budget by enabled source and priority.
2. Group similar topic keywords into one query group.
3. Generate queries per city and source capability.
4. Apply the configured date window.
5. Stop discovery when the source budget or candidate limit is reached.
6. Record every generated query for later diagnosis.

Example logical query:

```text
city=深圳
topics=[Agent, RAG, MCP]
activity_types=[业界, 开源]
date_window=2026-09-02..2026-09-16
source=Luma
```

The displayed query text may vary by source, but the logical parameters remain stored and auditable.

## 13. Configuration Merge

Configuration merge means producing a complete validated published version. It is separate from event deduplication.

Precedence:

```text
schema defaults
  < existing published configuration
  < current draft changes
```

Rules:

- Nested objects use field-level deep merge.
- Collection items use stable UUIDs, never array positions.
- Creating, updating, disabling, and deleting are explicit operations.
- A deleted user item is not silently restored from a later default catalog.
- Secrets are referenced by channel ID and are not embedded in configuration snapshots.
- Publishing writes a complete normalized document, not a patch.
- Jobs copy the published document into `job_runs.config_snapshot`.

## 14. Event Duplicate Detection and Field Merge

### 14.1 Identity Checks

Duplicate checks run in this order:

1. Same source and external event ID.
2. Same normalized canonical URL.
3. Same organizer, city, and start time with highly similar normalized title.
4. Similar title with start time within 90 minutes and geographically close venue.

The third and fourth checks create a duplicate score. A high score merges automatically; a middle score requires verification; a low score keeps separate events.

### 14.2 Source Trust

Default factual trust order:

```text
organizer official page
  > official registration page
  > recognized activity platform
  > community repost
  > search result snippet
```

Source priority configured by operations controls search effort. It does not override factual trust. A high-priority repost cannot replace a conflicting organizer-official start time.

### 14.3 Field Merge Rules

| Field | Merge behavior |
| --- | --- |
| Title | Prefer official complete title; retain aliases for search |
| Start/end time | Prefer official timestamp; store timezone and conflict evidence |
| Venue | Prefer precise official address; geocode after merge |
| Organizer | Normalize names but retain original display value |
| Registration URL | Prefer canonical official registration destination |
| Agenda | Combine non-duplicate agenda items with evidence links |
| Topics/types | Union supported classifications; remove unsupported guesses |
| Description | Preserve source text separately; generate a new summary from evidence |

Conflicting mandatory fields are never silently chosen by the LLM. They enter verification or remain unpublished.

## 15. Evidence and LLM Output

Each displayed statement is classified as:

- `EXTRACTED`: directly present in source material.
- `DERIVED`: calculated from extracted facts, such as commute time.
- `GENERATED`: model analysis, such as audience fit or prerequisites.

The LLM receives normalized source evidence and returns a Pydantic-validated object:

```text
summary
why_worth_attending[]
takeaways[]
prerequisites[]
topic_labels[]
activity_type
evidence_references[]
```

Mandatory facts are not accepted from generated output. At least 80% of factual claims displayed in the detail page must resolve to stored evidence. Generated judgment is allowed only in clearly analytical fields.

## 16. Scoring

Default score out of 100:

| Dimension | Weight |
| --- | ---: |
| Topic relevance | 30 |
| Agenda technical depth | 20 |
| Organizer credibility | 15 |
| Audience fit | 15 |
| Concrete takeaways | 10 |
| Evidence completeness | 10 |

Weak-content rules apply penalties from 10 to 30 points. `High value` requires score at least 80 and confidence at least 0.8. `Medium value` defaults to 65-79. City inclusion rules then decide whether the event may publish.

## 17. Core Data Model

| Table | Purpose |
| --- | --- |
| assistant_profiles | One activity assistant and its identity |
| config_versions | Draft and immutable published configurations |
| job_runs | Job state, timing, statistics, and configuration snapshot |
| raw_documents | Downloaded page content and metadata |
| event_candidates | Unpublished normalized candidates |
| events | Stable logical event identity |
| event_versions | Published event content versions |
| event_evidence | Field/claim-to-source evidence links |
| llm_runs | Model input hash, output, token usage, cost, and status |
| notification_channels | Channel metadata and encrypted secret reference |
| notification_deliveries | Per-channel delivery status and retry history |

## 18. Main API

| Method and path | Purpose |
| --- | --- |
| `GET /api/profiles/{id}/config` | Load published configuration and current draft |
| `PATCH /api/profiles/{id}/config` | Save draft field or collection-item changes |
| `POST /api/profiles/{id}/publish` | Validate and publish a new version |
| `POST /api/profiles/{id}/run` | Create an immediate job using published config |
| `GET /api/jobs/{jobId}` | Query state, progress, failures, and statistics |
| `GET /api/events` | Query calendar/list results with dynamic filters |
| `GET /api/events/{eventId}` | Load detail, evidence-backed analysis, and source link |
| `POST /api/channels` | Create a notification channel |
| `POST /api/channels/{id}/test` | Send a safe test message |
| `POST /api/channels/{id}/clear-secret` | Remove saved secret explicitly |
| `DELETE /api/channels/{id}` | Delete channel after confirmation |

## 19. Error Handling

- Source failures are isolated; one source cannot cancel the complete run.
- HTTP 429 and temporary 5xx failures retry with exponential backoff.
- Permanent 4xx errors disable automatic retry and appear in run details.
- Parser failures preserve raw documents for diagnosis.
- LLM invalid structured output retries once with validation errors.
- Notification failures retry independently and do not remove published events.
- Job steps use idempotency keys so retries cannot create duplicate events or messages.

## 20. English Glossary

| Term | Chinese explanation |
| --- | --- |
| API | 应用程序接口，前后端通过它交换数据 |
| Agent | 可选择搜索、打开网页等工具并按目标行动的模型执行单元 |
| LLM | Large Language Model，大语言模型 |
| Prompt | 发给模型的任务说明、约束和输出格式 |
| SDK | Software Development Kit，厂商提供的调用代码包 |
| Worker | 后台执行抓取、总结、推送任务的进程 |
| Scheduler | 按时间创建任务的调度器 |
| Webhook | 系统向指定网络地址主动发送消息的机制 |
| SendKey | ServerChan 用于识别接收账户的发送密钥 |
| Draft | 草稿，尚未影响正式任务的配置 |
| Published | 已发布，下一次任务正式使用的配置 |
| Snapshot | 快照，某次任务使用的完整不可变配置副本 |
| Canonical URL | 标准原文地址，代表活动的官方或首选页面 |
| Evidence | 支撑字段或结论的网页证据 |
| Confidence | 可信度，系统对某个判断可靠程度的数值表达 |
| Candidate | 候选活动，尚未通过完整核验和发布 |
| Normalize | 标准化，把不同来源的数据转换为统一格式 |
| Deduplicate | 去重，判断多个页面是否描述同一个活动 |
| Merge | 合并，把同一活动的多来源证据组合为一条记录 |
| Idempotency | 幂等，同一操作重试多次也只产生一次最终效果 |
| Backoff | 退避重试，失败后逐渐延长等待时间 |
| UUID | 通用唯一标识符，用于稳定识别配置项和数据记录 |
| UTC | 世界协调时间，`UTC+8` 表示比UTC快8小时 |

## 21. Acceptance Criteria

### Configuration

- All five prototype sections persist through backend APIs.
- Every collection card supports create, edit, enable/disable, and delete where applicable.
- Publishing creates a new immutable version and does not mutate running jobs.
- Invalid fields identify the exact inline card without opening a drawer or modal.
- Multiple Feishu and ServerChan channels can be configured, tested, disabled, cleared, and removed.

### Search and Processing

- Fixed sources and intelligent discovery both obey the published configuration snapshot.
- Changing cities, topics, sources, or coverage affects the next job without code changes.
- Duplicate activities from multiple sources result in one event with retained evidence.
- Mandatory facts are never sourced only from generated model text.

### Activity Page

- Calendar starts on Monday and includes city labels.
- Calendar and detail list use the same content width.
- Configured 15/30/60-day ranges are available without exceeding search coverage.
- High-value activities are visually prominent without adding excessive cards or borders.
- Missing images and optional values do not leave empty layout areas.
- Desktop and mobile layouts have no clipping, overlap, or hidden core content.

### Reliability

- Re-running a failed step does not duplicate events or notifications.
- A failed source or notification channel does not cancel unrelated successful work.
- Secrets never appear in API responses, logs, HTML, or configuration snapshots.

