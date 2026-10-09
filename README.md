# CityActivi 本地动态版本

## 1. 运行

```bash
docker compose up --build
```

打开 `http://localhost:8000/`。API 文档位于 `http://localhost:8000/docs`。

## 2. 已落地的契约

- 活动事实与摘要分别存储在 `event_fact_versions`、`event_enrichment_versions`。
- 发布前必须核验 `title`、`start_at`、`timezone`、`city`、`venue`、`organizer`、`canonical_url`、`technical_signal`。
- 封面可选，缺失或加载失败不会阻断发布。
- 配置覆盖天数只允许 `15`、`30`、`60`。
- 调度与活动时间使用 IANA 时区；数据库保存 UTC 时间。
- 任务状态统一为 `submitted`、`queued`、`running`、`succeeded`、`failed`、`cancelled`。
- 推送任务使用 `delivery_key`，活动状态变化写入 `event_status_changes`。
- v1 不包含容量、报名人数和容量进度条。

## 3. 网络抓取安全策略

抓取器面向公开活动详情页运行，默认每天按配置时区执行一次。它不使用登录态、Cookie、验证码绕过或代理池；事实字段只能来自抓取到的公开页面，未核验的候选不会进入公开活动接口。

### 3.1 请求节流

- 来源按配置顺序串行抓取，默认全局并发为 `1`。
- 同一时间只允许一个网络采集任务；重复点击“立即运行任务”会返回 `COLLECTION_ALREADY_RUNNING`，不会新增网络请求。
- 同一主机的请求之间至少间隔 `4` 秒，并加入 `0.4` 到 `1.2` 秒随机抖动。
- `robots.txt` 缓存 `24` 小时；每个来源首次抓取前先读取并遵守 `User-agent` 和 `Crawl-delay`。
- 仅允许公开 HTTP(S) 地址；`localhost`、内网域名、本地或保留 IP 地址会被拒绝。
- 重定向最多跟随 `3` 跳，每一跳重新进行公开地址检查、`robots.txt` 检查和主机限速。
- 单个响应体超过 `3 MiB` 时停止解析并记录 `response_too_large`。

### 3.2 错误和封禁处理

- `401`、`403`：立即停止该主机的本轮请求，并进入 `1` 小时冷却；不会重复撞击被拒绝的站点。
- `429`：读取 `Retry-After`（支持秒数和 HTTP 日期），进入最长 `5` 分钟冷却；本轮不立即重试。
- `5xx`、`408`、`425`：最多进行 `2` 次有抖动的指数退避重试。
- 网络错误：最多进行 `2` 次有界重试，仍失败则记录 `network_error`。
- `robots.txt` 返回拒绝、读取失败或重定向到不安全地址时，当前来源跳过并记录原因；不会把拒绝当成可抓取。

### 3.3 条件请求和重复运行

- 每个来源保存 `ETag`、`Last-Modified`、内容哈希、HTTP 状态码、解析器版本和抓取时间。
- 下一次运行只从最近一条正文抓取记录读取条件请求头；`304 Not Modified` 只写轻量审计记录，不重复下载和解析正文。
- `304` 记录不会遮住上一条带 ETag 的正文记录，后续运行仍然可以继续发条件请求。
- 解析器版本升级会自然跳过旧版本的条件缓存，重新获取正文，避免旧解析结果被错误复用。

### 3.4 发布失败处理

- 抓取失败、被限速、被 `robots.txt` 拒绝或事实字段不完整时，只记录 `raw_documents` 审计信息，不发布活动。
- 发布门禁要求八个事实字段和对应证据全部存在：`title`、`start_at`、`timezone`、`city`、`venue`、`organizer`、`canonical_url`、`technical_signal`。
- 启动时不写入示例活动，并清理历史 `seed` 与示例/测试域名活动；canonical URL 必须与抓取来源同主机，或在该来源的 `canonical_hosts` 中显式允许，保留域名及其子域永不发布。
- 每轮抓取先构建最多 12 条已核验候选池，再按事实完整度、来源优先级、城市缺口、开始时间、技术相关性和来源多样性排序；每个启用城市默认最多发布 4 条，最终总数仍受 `target_count` 限制。
- `collect_events_once()` 返回稳定结果协议，包含已配置/可访问/阻止/失败来源数、发现与核验候选数、按城市/来源发布数及逐项拒绝原因。
- 任务状态统一落库为 `submitted`、`queued`、`running`、`succeeded`、`failed`、`cancelled`；失败任务可从任务接口定位具体错误码。

### 3.5 来源范围

正式配置覆盖 34 个来源、其中 32 个启用：Meetup 深圳/广州/香港及 Dim Sum Labs HackJam，Eventbrite 深圳/广州/香港及各自第 2 页，GDG Shenzhen/Guangzhou/Hong Kong，GOSIM 首页与议程，RustChinaConf，Open Source Hong Kong，CityU-CCCN-PolyU 研讨会，EET China 泰克广州研讨会，HKU/HKUST QwenCloud 工作坊，openGauss、OpenInfra、AIRS、深圳大学图书馆、南方科技大学、香港中文大学（深圳）、香港科技大学、香港科技园、深圳公共文化活动页、深圳图书馆以及 SZDIY 公开 ICS 日历。

不同来源使用对应解析器：Eventbrite 读取公开 `window.__SERVER_DATA__` 活动结果，GDG 读取公开 `__NEXT_DATA__` 活动数据，CityU 解析研讨会表格，Open Source Hong Kong、EET China、HKU 和 HKUST 使用活动详情解析器，RustChinaConf 解析公开议程，南方科技大学从公开日历跳转到未来讲座详情页，SZDIY 读取公开 ICS。所有解析器都会经过八个事实字段门禁；列表标题、只有日期没有地点的记录不会直接发布。事件跨来源以 `canonical_url` 去重，公开接口按配置的 15/30/60 天窗口过滤。

创新南山相关产业入口暂时保留为关闭来源：南山区智能经济产业协会入口当前公开证书状态不稳定，创新南山企业服务平台暂未提供稳定的活动详情接口。robots 明确拒绝的入口仍会记录为跳过，运行时不会伪装、绕过或重复撞击来源。

## 4. 预览限制

本地浏览器展示页继续保留原型中的五个配置栏目和详情内容。真实数据来自 FastAPI 与 PostgreSQL；若只双击 HTML 文件，浏览器无法访问 API，这是浏览器的 `file://` 安全边界。请使用上面的 Docker 命令启动后访问 HTTP 地址。

## 5. 本地验证

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python -m py_compile backend/app/*.py tests/*.py
docker compose config
```
