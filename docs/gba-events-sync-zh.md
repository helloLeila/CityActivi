# GBA 技术活动数据同步说明（中文）

本文说明如何把每日生成的湾区技术活动 JSON 手动导入 CityActivi，以及如何判断同步是否成功、排查 502、worker、数据库和文件问题。

## 一、项目和文件位置

CityActivi 固定项目目录：

```text
/Users/leila/.codex/visualizations/2026/09/04/01a06aaa-a4a6-7763-a1b1-977a6fb6b5df
```

项目内重要目录：

```text
data/event-inbox/     活动 JSON 收件箱
scripts/              项目脚本
backend/              FastAPI、worker、导入器代码
static/               页面静态资源
docker-compose.yml    db、api、scheduler、worker、nginx 服务定义
```

手动同步脚本现在位于项目内：

```text
/Users/leila/.codex/visualizations/2026/09/04/01a06aaa-a4a6-7763-a1b1-977a6fb6b5df/scripts/sync-gba-events-to-cityactivi.mjs
```

脚本的职责是复制和导入已经核验好的 JSON。它不负责联网搜索、活动真实性判断、Markdown 生成或网页发布。

## 二、数据文件是什么

每日活动搜索会生成两份文件：

```text
YYYY-MM-DD-gba-tech-events.md
YYYY-MM-DD-gba-tech-events.json
```

Markdown 是给人阅读和推送的清单。JSON 是给 CityActivi 导入器消费的事实交换文件，包含：

- 活动名称、时间、城市、地点、主办方；
- 公开来源 URL；
- 原文摘录和抓取时间；
- 技术主题、活动摘要、报名和参与限制；
- 交通估算、推荐理由等补充信息。

JSON 的日期必须对应真实生成日期。不能把 10 月 26 日的旧 JSON 直接改名成 10 月 29 日，否则会把旧数据伪装成新批次。

## 三、启动 CityActivi

进入项目目录：

```bash
cd /Users/leila/.codex/visualizations/2026/09/04/01a06aaa-a4a6-7763-a1b1-977a6fb6b5df
```

首次构建或修改了 CityActivi 程序代码时：

```bash
docker compose up --build -d
```

平时只是重新启动已经构建好的服务时：

```bash
docker compose up -d
```

检查服务：

```bash
docker compose ps -a
```

正常应看到以下服务处于 `Up`，数据库通常还会显示 `healthy`：

```text
db
api
nginx
scheduler
worker
```

网页入口：

```text
http://localhost:8080/
```

API 入口：

```text
http://localhost:8000/
```

API 健康检查：

```bash
curl http://localhost:8000/api/health/live
curl http://localhost:8000/api/health/ready
```

预期结果分别类似：

```json
{"status":"ok","service":"cityactivi-api"}
```

```json
{"status":"ready","database":"connected"}
```

## 四、手动同步一份 JSON

假设今天生成的文件位于当前工作区：

```text
/Users/leila/.codex/worktrees/cc23/helloLeila/2026-10-29-gba-tech-events.json
```

执行：

```bash
node /Users/leila/.codex/visualizations/2026/09/04/01a06aaa-a4a6-7763-a1b1-977a6fb6b5df/scripts/sync-gba-events-to-cityactivi.mjs \
  /Users/leila/.codex/worktrees/cc23/helloLeila/2026-10-29-gba-tech-events.json
```

脚本会按以下顺序执行：

1. 检查输入文件存在且扩展名为 `.json`。
2. 将文件复制到项目的 `data/event-inbox/`。
3. 如果目标文件已存在，自动生成 `-v2`、`-v3` 等版本。
4. 检查 Docker Compose 中是否有正在运行的 `worker`。
5. 有 Docker worker 时，执行容器内的导入器。
6. 没有 Docker worker 时，尝试使用项目 `.venv` 的本地导入器。
7. 输出复制路径和导入结果。

脚本不会覆盖旧 JSON。脚本会去掉输入文件名末尾已有的版本后缀，因此把 `2026-10-29-gba-tech-events-v2.json` 再次传入时，不会生成 `v2-v2`。

## 五、如何判断同步成功

同步命令后面加上退出码检查：

```bash
node /Users/leila/.codex/visualizations/2026/09/04/01a06aaa-a4a6-7763-a1b1-977a6fb6b5df/scripts/sync-gba-events-to-cityactivi.mjs \
  /path/to/2026-10-29-gba-tech-events.json
echo "exit=$?"
```

成功时通常能看到：

```text
Copied ... -> .../data/event-inbox/2026-10-29-gba-tech-events.json
CityActivi import completed via Docker worker.
exit=0
```

`exit=0` 表示脚本没有报错退出。

导入器输出 `[]` 不一定表示失败。导入器会隐藏已经导入过的 `replayed=true` 记录；因此：

```text
[] + CityActivi import completed + exit=0
```

通常表示批次已被识别，但没有新增记录，可能是 worker 已经先消费，或活动之前已经导入。

以下情况表示需要排查：

- 出现 `CityActivi sync failed`；
- 没有出现 `Copied`；
- 没有出现 `CityActivi import completed`；
- 退出码不是 0；
- 输出中出现 `rejected` 或 `error`；
- 目标 inbox 没有生成对应 JSON。

检查文件：

```bash
ls -lt /Users/leila/.codex/visualizations/2026/09/04/01a06aaa-a4a6-7763-a1b1-977a6fb6b5df/data/event-inbox
```

检查 worker：

```bash
docker compose logs --tail=200 worker
```

检查 API：

```bash
curl -s 'http://localhost:8000/api/public/events?coverage_days=60'
```

## 六、502 错误排查

浏览器出现 `502 Bad Gateway` 时，通常表示 Nginx 在运行，但连不上 API。先看服务状态：

```bash
docker compose ps -a
```

再看 API 日志：

```bash
docker compose logs --tail=200 api
```

看 Nginx 日志：

```bash
docker compose logs --tail=200 nginx
```

如果日志出现类似：

```text
connect() failed (113: Host is unreachable) while connecting to upstream
upstream: "http://172.20.0.x:8000/"
```

通常是 API 容器重建后内部 IP 变化，而旧 Nginx 仍缓存了旧地址。先重启 Nginx：

```bash
docker compose restart nginx
```

再检查 API：

```bash
curl http://localhost:8000/api/health/live
```

如果 API 已正常返回，再刷新：

```text
http://localhost:8080/
```

如果 API 是 `Exited` 或 `Restarting`，优先查看 `api` 日志，不要反复重启 Nginx。

## 七、worker 没有导入时的排查

确认 worker 是否运行：

```bash
docker compose ps worker
```

确认容器内收件箱是否挂载：

```bash
docker compose exec worker ls -lt /app/data/event-inbox
```

确认 worker 日志：

```bash
docker compose logs --tail=200 worker
```

如果需要手动调用容器内导入器：

```bash
docker compose exec -T worker \
  python -m backend.app.import_events \
  --inbox /app/data/event-inbox
```

如果导入器返回 `rejected` 或 `error`，保留 JSON 文件，不要删除；先根据错误修正数据契约。

## 八、什么时候需要重新 build

修改 CityActivi 镜像内代码时需要：

```bash
docker compose up --build -d
```

包括：

- `backend/` Python 代码；
- `static/` 前端资源；
- `cityactivi-redesign-preview.html`；
- `requirements.txt`；
- `Dockerfile`。

以下变化不需要重新 build：

- 新增活动 JSON；
- 修改活动 Markdown；
- 修改宿主机上的自动化配置；
- 修改宿主机上的同步脚本；
- 重启已经构建好的容器。

平时启动使用：

```bash
docker compose up -d
```

不要随意使用：

```bash
docker compose down -v
```

因为 `-v` 会删除 PostgreSQL 数据卷，可能清除已经导入的活动数据。

## 九、自动化任务和手动脚本的关系

`automation-3` 负责：

- 搜索网页；
- 核验活动；
- 生成当天 Markdown；
- 生成当天 JSON；
- 按配置推送飞书和 Server 酱；
- 调用本文件说明的同步脚本。

同步脚本负责：

- 复制当天 JSON；
- 防止覆盖历史批次；
- 调用 Docker worker 或本地导入器；
- 输出成功、重放或错误状态。

判断“今天是否真的同步”，至少要同时确认：

1. 今天的 JSON 文件存在，例如 `2026-10-29-gba-tech-events.json`；
2. JSON 已进入 `data/event-inbox/`；
3. worker 导入命令退出码为 0；
4. API 或网页能返回仍在展示窗口内的活动。

网页能打开只代表 Nginx/API 链路正常，不代表今天的活动数据已经生成或导入。
