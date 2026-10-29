# CityActivi 每日搜寻接入实施计划

> **For agentic workers:** Execute inline task-by-task. Preserve existing database contents and collection configuration.

**Goal:** 每日搜寻输出结构化 JSON，接入现有活动列表，跨来源合并且保留详细信息与证据。

**Architecture:** 文件是可信本地生产端的交换格式；导入器验证 schema、事实证据及日期后调用统一存储函数。网络采集器复用同一合并入口。详细分析存入新增 JSON 补充表，来源 URL 存入别名表，现有事实/摘要版本和公开 API 保持兼容。

**Tech Stack:** Python、Pydantic、SQLAlchemy async、FastAPI、现有 HTML/JavaScript 页面。

## 实施顺序

- [ ] 1. 新增导入与去重回归测试：跨 URL 同事件、同 URL 重复导入、不同城市/日期不合并、冲突保留、缺证据拒绝、进行中多日活动。
- [ ] 2. 新增 `event_ingest.py` 数据契约、规范 URL 与确定性业务匹配、版本合并；新增 `EventSupplement` 和 `EventSourceAlias` 表及 Alembic 迁移。不删除旧版本。
- [ ] 3. 网络采集复用统一存储入口；公开 API 返回详细字段、来源和冲突；事实门禁与列表支持仍可参加的多日活动。
- [ ] 4. 新增 `import_events.py` CLI（dry-run / JSON报告 / inbox消费），worker 轮询挂载目录，Docker 使用同一数据库及只读 inbox。
- [ ] 5. 新增详情渲染脚本，展示技术看点、报名、费用、参与限制、交通估算及原文证据；跨日期活动在剩余日期可见。
- [ ] 6. 写入完整数据契约文档，更新 automation-3：原 Markdown/双推送/17:53 保持，追加 JSON 和 inbox 交付。以回读配置验证。
- [ ] 7. 运行原有 unittest、新增端到端导入/API 测试、py_compile、JS 渲染测试与 Docker 配置校验；独立代码审查后修正发现。

## 验收命令

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
.venv/bin/python -m py_compile backend/app/*.py tests/*.py
node --test tests/test_event_details.mjs
docker compose config --quiet
```

只使用临时数据库进行自动化验证；不向当前数据库写入测试活动。缺费用、讲厅或小时级时间不伪造，日期精度显式保存；关键事实缺失保留导入报告，不发布。
