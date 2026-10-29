# 每日活动搜寻 → CityActivi 数据接入

## 数据流与运行

当前本机已接通项目默认 SQLite `cityactivi.db`，原 4 条记录保留，首次导入新增 2 条。日常自动化在该项目目录调用本机 `.venv/bin/python -m backend.app.import_events --inbox data/event-inbox`，与本地 API 共用数据库；不需要 Docker 才能使用。下面 Docker 命令属于另一部署选项，使用前须明确数据库迁移和运行方式。

每日搜寻继续生成 Markdown 和执行原有飞书/Server 酱推送，同时从同一份已核验事实生成 JSON。JSON 写入项目的 `data/event-inbox/`；worker 约每 5 秒扫描，调用与网络采集相同的合并入口。文件和导入收据保留，重复批次不重复新增活动。

```sh
docker compose up -d --build db api worker
docker compose exec -T worker python -m backend.app.import_events --inbox /app/data/event-inbox
```

打开 `http://localhost:8000/`。源文件 `data/event-inbox/2026-10-18-gba-tech-events.json` 是已核验的真实首批数据，包含 RISC-V 深圳峰会及广州腾讯云开发者沙龙。没有把历史 Markdown 全量机械转换为事实。

本机直接运行时必须给 CLI、API 和 worker 配置相同的 `DATABASE_URL`。Docker 数据库与已有本地 SQLite 是不同存储，禁止自动猜测数据库或把一份写入当成另一份已更新。

```sh
.venv/bin/python -m backend.app.import_events path/to/batch.json --dry-run
.venv/bin/python -m backend.app.import_events path/to/batch.json
```

`--dry-run` 回滚所有活动和收据写入；启动时可以补建缺失表。退出码 0 表示全部接受或同批次重放，1 表示部分记录拒绝，2 表示文件/批次契约无效。错误报告包含索引和原因，不输出输入正文。网络采集不会自动重复运行。

## JSON 契约

顶层字段固定为：`schema_version: 1`、`producer: "gba-tech-events"`、`generated_at`（有 UTC offset 的 ISO 时间）和 `events` 数组。单文件不超过 2 MiB，单批最多 200 条。

每条记录：

- `facts`：`title`、`timezone`、`city`、`venue`、`organizer`、`canonical_url`、`technical_signal`。
- 精确时间：`time_precision: "minute"`（默认）、`start_at`，可选 `end_at`；时间必须带 offset。
- 仅日期：`time_precision: "date"`、`start_date: "YYYY-MM-DD"`，可选 `end_date`（含结束当天）。不能同时填 `start_at/end_at`；内部采用当地日期边界排序，页面明确显示时刻未公开。
- `evidence`：八个必备事实字段各自对应 `{source_url, excerpt, captured_at}`。时间无小时精度时 `start_at` 的证据写日期原文；提供结束时间/日期时还必须有 `end_at` 证据。`captured_at` 带 offset。`canonical_url` 证据必须来自主活动页。证据是可信本地生产端的核验记录，导入器验证形状、公开链接与时间有效性，不声称重新联网证明文本真伪。
- `source_name`：公开发布方/主办方名称。
- `enrichment`：可选 `summary`、`calendar_summary`、`why_worth`、`takeaways`（字符串数组）、`prerequisites`（字符串数组）、`topic`、`kind`、`relevance`、`commute_minutes`（非负整数或 null）、`community`。
- `details`：可选 `chinese_explanation`、`highlights`（字符串数组）、`duration_text`、`price_text`、`registration_url`、`registration_status`（`open/unknown`；`closed/cancelled` 当前不发布）、`participation`、`recommendation`、`recommendation_reason`、`transport`。
- `transport`：`estimated`、`plan`、`one_way_time`、`one_way_cost`、`round_trip_time`。默认以估算显示；明确有交通运营方依据时才填写 `estimated: false`。交通预测不回填主活动事实。

费用和参与方式未知时在详情使用“官方未公开”或“未核实”；关键事实缺失不能用这些占位词冒充有效值。JSON 不能含密钥、数据库地址、Webhook 或个人登录态。

## 合并规则

1. URL 移除追踪参数，保留语义 query 和活动 fragment。结合标题、主办方、城市与开始时间识别场次；同一 URL 换日期的场次保持分开。
2. 跨 URL 仅在规范化标题、主办方、城市和精确 UTC 开始时间完全相等时合并。相似标题不做自动模糊合并；日期精度不足的跨站候选保守分开。
3. 同一来源、同名同主办方同城同日的日期记录可补全为精确时刻；多个匹配发生歧义时拒绝并报告。
4. 跨站地点等事实冲突保留主来源，保存冲突信息及来源证据。旧 captured_at 不覆盖新事实或详细摘要；普通网络采集不覆盖已有详细摘要。
5. 存储保留原事实版本、摘要版本和活动键。新增补充表、来源别名表及批次收据表，不删除原活动。
6. 列表依据结束边界保留尚未结束的多日活动，并在其剩余当地日期显示；未知报名状态不会被误标为已保证入场。

自动匹配采用保守规则，无法保证所有中英文别名、不同平台标题或改期活动都自动归并。来源冲突和拒绝原因用于后续核对；禁止为追求数量降低证据门槛。

## 故障与验收

- 单条字段异常：拒绝该条，继续处理合法条目；导入报告持久保存。
- 格式损坏文件：不执行活动写入，不阻断其他文件。
- worker 未运行：文件仍保存在 inbox；启动后消费，不报告已经入库。
- API 与 worker 使用同一数据库。新增表由现有启动机制创建；使用 Alembic 部署的环境执行 `alembic upgrade head`，不要对未纳入 Alembic 的旧库直接执行初始建表迁移。
- 验证命令见 README。自动化测试使用临时内存库，不写生产活动或测试假数据到真实库。
