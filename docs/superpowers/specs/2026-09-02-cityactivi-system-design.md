# CityActivi 系统详细设计

## 一、目标

本文档用于把已经确认的 CityActivi 页面原型转换成可以直接指导开发的系统设计。

当前原型是产品基线，以下内容保持不变：

- 活动页仍然由“日历概览 + 下方活动详情”组成。
- 日历概览上方增加“未来15天活动简述”，它与日历和下方详情使用同一批已发布活动数据。
- 配置页仍然保留现有五个栏目和主要操作位置。
- 配置项仍然在当前卡片内部展开编辑，不改成右侧抽屉或居中弹窗。
- 现有主要文案、信息结构和操作流程不删除。
- 活动详情不依赖封面图，不突出报名人数。
- 活动详情重点展示主办方、地点、活动价值、收获和提前准备。

第一版同时建设公开活动站和一套独立的运营后台。当前原型中的配置页面就是运营后台的UI基线，以下五个栏目和已有字段全部保留：

1. 搜寻范围
2. 时间与地点
3. 主题偏好
4. 展示字段
5. 推送与自动化

运营后台与公开活动站使用不同访问入口和权限，但共用同一套排版、颜色、控件和设计令牌。大模型密钥、数据库连接、抓取并发数等技术参数放进原型现有的“推送与自动化”栏目，使用当前页面已有的区块、卡片、表单和行内编辑样式，不增加第六个左侧导航。

所有改动遵守两条硬约束：

- **UI视觉不重做**：不改变现有页面宽度、栏目顺序、导航位置、卡片编辑方式和主要操作位置。
- **字段不丢失**：原型已经出现的配置字段全部进入正式数据模型和接口，不允许在开发过程中以“暂不支持”为理由删除。

## 二、产品设计边界

### 2.1 活动页

活动页只展示已经完成抓取、合并、总结和核验的活动结果，包含：

- 从周一开始排列的活动日历。
- 日历上方的未来15天活动简述，按含金量和开始时间列出重点活动。
- 根据配置动态生成的15天、30天或60天范围切换。
- 根据已配置城市、主题和活动类型生成的筛选条件。
- 日历下方的信息型活动详情列表。
- 跳转到活动官方原文或正式报名入口的链接。

活动页不负责修改抓取来源、主题规则、推送通道或运行计划。

### 2.2 独立运营后台

运营后台使用独立地址，例如 `/ops/`，登录后才能访问。它直接实现当前原型的配置页面，用于决定：

- 系统去哪里找活动。
- 哪些活动值得收录。
- 搜索哪些城市和日期。
- 活动页展示哪些内容。
- 结果在什么时间推送到哪些通道。
- 大模型使用哪个服务和模型。
- 抓取任务使用多少并发、超时和重试次数。
- 当前数据库连接是否可用，以及待应用的连接配置。

点击“编辑”后，只展开当前卡片。其他卡片不进入编辑状态，也不自动滚动页面。

独立运营后台并不等于重新设计一套后台模板。不能引入传统业务系统常见的顶部深色栏、复杂表格、侧边抽屉和大面积统计卡片。当前原型的视觉层级、留白、浅色背景和行内编辑继续作为实现标准。

### 2.3 访问与权限边界

第一版采用单一运营角色，但系统预留权限字段：

- 公开活动站无需登录，只提供只读活动数据。
- 运营后台必须登录，才能读取配置状态和保存草稿。
- 密钥类字段只能写入、替换或清除，不能读取明文。
- 数据库连接修改、密钥清除和立即运行任务需要再次确认。
- 所有发布、密钥修改和运行参数修改都写入审计记录。

### 2.4 不允许关闭的固定规则

以下规则是系统质量底线，不允许通过运营配置关闭：

- 活动必须具有可核验的标题、开始时间、城市、主办方和技术说明。
- 已经开始或结束的活动不进入新的正式结果。
- 大模型生成的文字不能覆盖原文中的事实字段。
- 密钥保存后不能通过前端再次读取明文。
- 每条正式活动必须保留其来源和证据。

## 三、技术结构

```text
浏览器
  ├─ 公开活动站 /                 Vue 3 + TypeScript
  └─ 独立运营后台 /ops/           Vue 3 + TypeScript
                ↓ HTTPS
Nginx 统一入口
  ├─ 提供两个前端的静态文件
  ├─ 转发 /api/public/*
  └─ 转发 /api/ops/*
                ↓
FastAPI 应用服务
  ├─ 公开活动接口
  ├─ 运营配置与发布接口
  ├─ 登录、权限与审计
  ├─ 推送通道和密钥管理
  ├─ 系统运行参数管理
  └─ 任务创建与状态查询
                ↓
PostgreSQL
  ├─ 产品配置、活动和任务数据
  ├─ 大模型调用与证据数据
  └─ 运行参数、审计和推送记录
                ↑
Python 后台任务系统
  ├─ Scheduler 定时调度器
  ├─ Worker 后台任务执行器
  ├─ 固定来源采集器
  ├─ 智能探索 Agent
  ├─ 内容提取、去重和合并
  ├─ 大模型总结与事实核验
  └─ 页面发布和消息推送
                ↓
外部服务
  ├─ 活动网站和官方页面
  ├─ 大模型 API
  ├─ 地图路线 API
  └─ 飞书、Server酱和通用 Webhook
```

### 3.1 技术栈及中文含义

| 技术名称 | 中文解释 | 在本项目中的作用 | Java 开发类比 |
| --- | --- | --- | --- |
| Vue 3 | 前端页面框架 | 实现活动页和配置页 | 浏览器端界面框架 |
| TypeScript | 带静态类型的 JavaScript | 定义前端数据类型并减少运行错误 | 类似 Java 的编译期类型检查 |
| Vite | 前端构建工具 | 本地启动、热更新和生产打包 | 类似前端项目的构建运行器 |
| Vue Router | Vue 路由工具 | 管理活动页和配置页地址 | 类似 Controller 路由表 |
| Pinia | Vue 状态管理工具 | 管理配置草稿、筛选条件和页面共享状态 | 类似应用级状态服务 |
| FastAPI | Python Web 开发框架 | 提供前后端接口 | 作用类似 Spring Boot 的 Web 层 |
| Pydantic | Python 数据模型与校验工具 | 校验接口参数和大模型结构化输出 | 类似 DTO 加 Bean Validation |
| SQLAlchemy | Python 数据库访问和对象映射工具 | 查询、写入数据库和管理事务 | 更接近 JPA/Hibernate，不完全等于 MyBatis |
| Alembic | 数据库结构迁移工具 | 记录并执行数据库表结构升级 | 类似 Flyway 或 Liquibase |
| PostgreSQL | 关系型数据库 | 保存配置、任务、活动和证据 | 使用方式与 Java 项目中的 MySQL/PostgreSQL 类似 |
| Nginx | Web服务器和反向代理 | 提供 HTTPS、前端静态文件和接口转发 | 部署入口，不承担业务逻辑 |
| Docker Compose | 多服务容器编排文件 | 一次启动前端、后端、任务进程和数据库 | 类似可执行的本地部署清单 |

### 3.2 建议的代码仓库结构

```text
CityActivi/
  apps/
    public-web/              公开活动站 Vue 应用
    ops-console/             独立运营后台 Vue 应用
  packages/
    ui/                      两个前端共享的基础控件和设计令牌
    api-types/               根据后端接口生成的 TypeScript 类型
  services/
    api/                     FastAPI 接口服务
    worker/                  抓取、总结、核验和推送任务
    scheduler/               定时创建任务
  migrations/               Alembic 数据库迁移脚本
  deploy/
    nginx/                   Nginx 配置
    systemd/                 可选的 Linux 服务配置
  docker-compose.yml
  .env.example
```

公开活动站和运营后台是两个独立构建产物，因此可以分别部署、缓存和限制权限。两者通过 `packages/ui` 共用颜色、字体、间距、输入框、按钮和配置卡片组件，从代码层保证UI不会在实现时走样。

### 3.3 公开活动站前端

公开活动站使用 Vue 3 的组合式API和 TypeScript：

- Vue Router 管理活动首页、活动详情和404页面。
- Pinia 只保存日期范围、城市、主题等筛选状态，不把服务器活动数据长期复制到全局状态。
- 活动列表通过后端分页接口读取；日期范围或筛选改变时取消旧请求，避免结果闪烁。
- 日历和详情列表使用相同内容容器宽度。
- 15天、30天和60天切换只查询对应范围，不一次把60天全部塞进首屏。
- 活动详情中的原文链接直接跳转标准原文地址，不增加多余的“打开详情”按钮。

### 3.4 独立运营后台前端

运营后台同样使用 Vue 3 和 TypeScript，但拥有独立路由、登录状态和权限校验：

- 每个原型栏目对应一个路由状态，但视觉上仍使用现有左侧栏目切换。
- 每张配置卡片维护自己的编辑草稿，保存失败只影响当前卡片。
- 页面级草稿状态记录哪些栏目尚未发布。
- 离开页面前如果存在未保存的卡片内容，显示轻量确认提示。
- 接口返回字段校验错误时，错误映射到具体卡片和输入项。
- 所有选择器使用后端提供的可选值，不允许依赖前端写死城市和来源。
- 技术参数沿用相同的 `section-block`、`setting-row`、配置卡片和行内展开样式。

### 3.5 FastAPI 应用服务

FastAPI 后端按领域拆分，不把所有逻辑写进接口文件：

```text
app/
  api/                       HTTP 路由和权限检查
  schemas/                   Pydantic 请求、响应和大模型结构
  models/                    SQLAlchemy 数据库模型
  repositories/              数据库查询和写入
  services/                  配置发布、活动查询、推送等业务逻辑
  security/                  登录、会话、加密和审计
  settings/                  启动配置和运行参数
```

各层职责：

- `api` 只负责接收请求、检查权限和返回响应。
- `schemas` 定义字段类型、必填规则和枚举值。
- `repositories` 只处理数据库，不调用大模型或网页。
- `services` 负责事务边界和业务流程。
- `security` 负责密码哈希、会话、密钥加密和敏感操作确认。

后端根据 OpenAPI 接口说明自动生成前端 TypeScript 类型，避免前端把 `coverageDays` 写成字符串、后端却按整数处理。

### 3.6 定时调度器与后台任务执行器

第一版不引入 Celery、Redis、Temporal 或 DBOS。任务状态直接保存在 PostgreSQL：

- Scheduler 定时调度器每分钟检查应该启动的助手配置。
- 到达计划时间后，在 `job_runs` 中创建一条等待任务。
- Worker 使用 PostgreSQL 的行锁安全领取任务。
- 任务记录租约时间和心跳，Worker 异常退出后其他 Worker 可以重新领取。
- 每个步骤保存状态、开始时间、完成时间、重试次数和错误摘要。
- 发布和推送使用幂等编号，防止任务重试生成重复活动或重复消息。

领取任务使用 PostgreSQL 的 `FOR UPDATE SKIP LOCKED` 机制：多个 Worker 可以并行读取任务，但同一条任务只会被其中一个 Worker 锁定并执行。这相当于使用数据库实现一个轻量任务队列，适合第一版和单台阿里云服务器。

### 3.7 网页采集技术

- `httpx`：异步发送 HTTP 请求，优先处理普通静态页面。
- `BeautifulSoup`：解析 HTML 并提取标题、正文、链接和结构化数据。
- `Playwright`：只在必须执行 JavaScript 才能看到内容时启动浏览器。
- 每个来源使用独立采集器，实现统一的发现、抓取和解析接口。
- 页面正文、响应状态、抓取时间、内容哈希和解析器版本全部保存。
- Playwright 按需执行，避免在低配置服务器上长期占用大量内存。

### 3.8 大模型调用层

大模型调用使用供应商官方 Python SDK，并通过项目内部适配层统一：

```text
活动证据
  → Prompt 模板
  → 模型适配器
  → Pydantic 结构校验
  → 证据引用检查
  → 保存 llm_runs
```

适配层屏蔽不同供应商在模型名称、接口地址和返回结构上的差异。业务代码只调用“总结活动”“判断类型”“补充搜索计划”等明确能力，不直接到处调用某一家模型SDK。

每次调用保存提示词版本、模型、输入内容哈希、输出、耗时、Token数量、估算费用、错误和重试次数。大模型温度默认使用低值，保证同一活动多次处理时结果相对稳定。

### 3.9 PostgreSQL 与 SQLAlchemy

后端使用 SQLAlchemy 2.x 风格模型和事务，数据库驱动使用 `asyncpg`：

- 时间统一保存为带时区的 `timestamptz`。
- 主键使用 UUID，避免不同任务或服务生成冲突编号。
- 配置快照、模型结构化输出等变化较快的数据使用 `jsonb`。
- 经常筛选和关联的字段使用普通列，不能把所有数据都塞进 JSON。
- 活动发布时间、开始时间、城市、状态和标准原文地址建立索引。
- Alembic 管理每次字段新增、约束修改和索引变化。

### 3.10 Nginx 与部署

Nginx 是外部唯一入口：

- `/` 提供公开活动站。
- `/ops/` 提供独立运营后台。
- `/api/public/` 转发公开只读接口。
- `/api/ops/` 转发需要登录的运营接口。
- `/assets/` 使用长期缓存，HTML 不使用长期缓存。
- 统一处理 HTTPS、请求大小和基础限流。

Docker Compose 运行 PostgreSQL、API、Worker、Scheduler 和 Nginx。前端在构建阶段生成静态文件，不需要常驻 Node.js 进程。对于配置较低的服务器，Worker 默认单进程，网页抓取并发可在运营后台调整，Playwright 浏览器数量设置独立上限。

### 3.11 Python 后端具体落地方式

本节把前面的 Python 技术选型落实为可以直接创建文件和编写代码的结构。Python 在本项目中不是“把所有事情写在一个脚本里”，而是分为接口服务、定时调度、后台执行、网页采集、活动处理、大模型分析、通勤计算和推送适配几个边界。

#### 3.11.1 三个常驻进程各自负责什么

| 进程 | 启动入口 | 只负责什么 | 不负责什么 |
| --- | --- | --- | --- |
| API进程 | `services/api/app/main.py` | 登录、配置、公开活动查询、任务创建和状态查询 | 不在HTTP请求中执行网页抓取或大模型长任务 |
| Scheduler进程 | `services/scheduler/app/main.py` | 每分钟检查到期计划，并创建唯一的 `job_runs` | 不抓网页、不调用模型、不发送消息 |
| Worker进程 | `services/worker/app/main.py` | 领取任务，执行抓取、提取、合并、总结、通勤、评分、发布和推送 | 不接收公网请求，不修改运营配置 |

API收到“立即运行”请求时，只在数据库中创建等待任务并立即返回 `job_id`。真正的处理由 Worker 完成，前端通过任务接口查看进度。这样不会因为网页加载慢或模型响应慢而让浏览器请求超时。

#### 3.11.2 Python目录和模块职责

```text
services/
  api/
    app/
      main.py                         FastAPI应用入口
      core/
        settings.py                   环境变量和启动配置
        errors.py                     统一错误代码
        logging.py                    脱敏日志配置
      db/
        session.py                     SQLAlchemy异步连接和会话
        models/                        数据库模型
        migrations/                    Alembic迁移配置
      api/
        deps.py                        登录用户、数据库会话等依赖
        routes/
          public_events.py             活动页公开接口
          ops_config.py                配置草稿和发布接口
          ops_jobs.py                  任务和步骤接口
          ops_channels.py              推送通道接口
          ops_runtime.py               模型、抓取和数据库运行配置接口
      schemas/                         Pydantic请求和响应模型
      repositories/                    只负责数据库读写
      services/                        配置、发布、查询和权限业务逻辑
      security/                        密码、会话、密钥和审计
  scheduler/
    app/
      main.py                          调度循环入口
      scheduler_service.py             到期计划和幂等创建任务
  worker/
    app/
      main.py                          Worker循环入口
      runtime/
        claim.py                        领取任务和租约续期
        step_runner.py                  步骤状态、重试和心跳
      pipeline/
        run_activity_job.py             一次完整活动任务编排
        models.py                       任务内部数据结构
      sources/
        base.py                         固定来源统一接口
        luma.py                         Luma采集器
        meetup.py                       Meetup采集器
        academic.py                     高校或实验室页面采集器
        discovery_agent.py              可选的智能探索补漏
      extraction/
        html_cleaner.py                 HTML正文清洗
        event_parser.py                 标题、时间、地点等事实提取
        normalizer.py                   时间、城市、主办方标准化
      analysis/
        prompts/                         Prompt模板和版本
        llm_client.py                    大模型适配器
        summary_service.py               摘要、分类和证据核验
        scoring.py                       确定性评分
      commute/
        map_client.py                    高德或Google Maps适配器
        route_service.py                 通勤计算和结果保存
      publishing/
        event_publisher.py               发布活动版本
        calendar_query.py                日历和15天简述查询
      notifications/
        base.py                           推送通道接口
        feishu.py                         飞书适配器
        serverchan.py                     Server酱适配器
```

依赖方向固定为：

```text
路由 routes
  → 应用服务 services
    → 仓储 repositories / 外部客户端 clients
      → SQLAlchemy会话或外部HTTP服务
```

路由文件不能直接写复杂 SQL；仓储不能调用大模型；大模型客户端不能直接修改活动表。违反这个边界，后面更换数据库、模型服务或来源网站时会产生连锁修改。

#### 3.11.3 启动配置和环境变量

服务器级配置使用环境变量或服务器外部文件，不能从浏览器直接传入 Python 进程。Pydantic Settings负责读取、类型转换和启动校验：

```python
# services/api/app/core/settings.py
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "CityActivi"
    environment: str = "production"
    database_url: str
    session_cookie_name: str = "cityactivi_session"
    runtime_socket_path: str = "/run/cityactivi/runtime.sock"
    public_base_url: str = "https://cityactivi.example.com"
    api_request_timeout_seconds: int = Field(default=30, ge=5, le=120)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`database_url`和运行时密钥只在进程启动时读取，禁止放入 `config_versions.config_json`。运营后台修改数据库连接时，写入服务器外部的受保护配置，由 Runtime Controller应用，不通过普通业务表间接改变当前连接。

#### 3.11.4 SQLAlchemy异步会话和事务

```python
# services/api/app/db/session.py
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import get_settings


settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_recycle=1800,
)
session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
```

业务服务显式控制事务，不把一个包含外部网络调用的长流程放进事务：

```python
async def create_run(session: AsyncSession, profile_id, config_version_id, key):
    async with session.begin():
        run = JobRun(
            profile_id=profile_id,
            config_version_id=config_version_id,
            idempotency_key=key,
            status="queued",
        )
        session.add(run)
    return run.id
```

这段代码只负责写入“任务已经创建”。网页、地图和模型调用在事务提交后执行；调用结束后再用短事务把结果写回。Java开发者可以把它理解为：Controller只创建任务，Service划分事务，Repository封装持久化，外部HTTP调用不占着数据库事务不放。

#### 3.11.5 配置接口如何保证保存后仍是完整 JSON

配置请求分为“局部修改”和“完整存储”两个概念。前端可以只提交一个卡片，但后端必须按版本号读取完整草稿、深层合并、校验全量结构，再写回完整 JSON：

```python
async def patch_config(
    session: AsyncSession,
    profile_id,
    patch: ConfigPatch,
    expected_version: int,
) -> ConfigVersion:
    async with session.begin():
        draft = await config_repo.lock_draft(session, profile_id)
        if draft.version_number != expected_version:
            raise ConfigVersionConflict()

        merged = merge_config(draft.config_json, patch.model_dump(exclude_unset=True))
        complete = ConfigDocument.model_validate(merged)
        draft.config_json = complete.model_dump(mode="json")
        draft.schema_version = complete.schema_version
        draft.checksum = sha256_json(draft.config_json)
        return draft
```

`ConfigDocument`必须使用必填根字段和明确的子模型，不能使用 `dict[str, Any]` 代替全部校验：

```python
from datetime import time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ScheduleConfig(BaseModel):
    frequency: Literal["daily", "weekdays", "weekly_monday"]
    time: time
    coverage_days: Literal[15, 30, 60]
    timezone: str = Field(pattern=r"^[A-Za-z_]+/[A-Za-z_]+$")


class CityConfig(BaseModel):
    id: UUID
    city_code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=80)
    country_code: str = Field(min_length=2, max_length=2)
    include_threshold: Literal["high", "medium", "all"]
    max_commute_minutes: int = Field(ge=0, le=300)
    search_priority: Literal["high", "medium", "low"]
    is_enabled: bool
    sort_order: int = Field(ge=1)


class ConfigDocument(BaseModel):
    schema_version: int = 1
    region: str = Field(min_length=1, max_length=100)
    target_count: int = Field(ge=1, le=100)
    hide_expired: bool
    schedule: ScheduleConfig
    origin: OriginConfig
    cities: list[CityConfig] = Field(min_length=1)
    audiences: list[AudienceConfig] = Field(min_length=1)
    sources: list[SourceConfig] = Field(min_length=1)
    discovery: DiscoveryConfig
    topics: list[TopicConfig] = Field(min_length=1)
    weak_content_rules: list[WeakContentRuleConfig] = Field(min_length=1)
    event_types: list[EventTypeConfig] = Field(min_length=1)
    sort: SortConfig
    preferences: PreferencesConfig
    display_fields: DisplayFieldsConfig
    output: OutputConfig
    channel_routes: list[ChannelRouteConfig] = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")
```

实际代码中每个列表项都应继续定义对应的 Pydantic 模型。`extra="forbid"`防止前端拼错字段后被静默忽略；旧版本升级时用显式迁移函数补字段，而不是在接口层临时拼默认值。

#### 3.11.6 Scheduler如何创建不重复的任务

Scheduler每分钟读取启用的 `assistant_profiles` 和正式配置中的运行时间。到达时间后，在事务中使用唯一幂等键创建 `job_runs`：

```python
async def tick(session: AsyncSession, now: datetime) -> None:
    due_profiles = await profile_repo.list_due(session, now)
    for profile in due_profiles:
        scheduled_key = f"{profile.id}:{now.date().isoformat()}:{profile.schedule_time}"
        await run_service.create_if_absent(
            session=session,
            profile=profile,
            idempotency_key=scheduled_key,
        )
```

数据库必须对 `job_runs.idempotency_key` 建唯一约束。Scheduler重复运行、服务器重启或同一分钟执行两次时，第二次插入只得到“已存在”，不能生成第二个任务。Scheduler不读取草稿，只使用已经发布的配置。

#### 3.11.7 Worker如何领取任务和恢复任务

Worker使用短事务锁定一条等待任务，并写入租约。SQLAlchemy写法如下：

```python
async def claim_one(session: AsyncSession, worker_id: str, now: datetime):
    async with session.begin():
        stmt = (
            select(JobRun)
            .where(
                JobRun.status == "queued",
                or_(
                    JobRun.lease_expires_at.is_(None),
                    JobRun.lease_expires_at < now,
                ),
            )
            .order_by(JobRun.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        run = (await session.execute(stmt)).scalar_one_or_none()
        if run is None:
            return None
        run.status = "running"
        run.lease_owner = worker_id
        run.lease_expires_at = now + timedelta(minutes=5)
        run.heartbeat_at = now
        return run
```

Worker每30秒续租一次；步骤结束、失败或任务完成时更新心跳。进程崩溃后租约过期，其他 Worker可以重新领取。重新领取不能从第一步盲目开始，而是读取 `job_steps`：已经成功的步骤跳过，失败步骤从允许重试的位置继续。

#### 3.11.8 步骤执行器和重试策略

所有任务步骤通过同一个执行器运行，避免每个模块自己实现一套错误处理：

```python
async def run_step(
    session: AsyncSession,
    run_id: UUID,
    step_name: str,
    handler: Callable[[], Awaitable[None]],
    max_attempts: int,
) -> None:
    step = await step_repo.get_or_create(session, run_id, step_name)
    if step.status == "succeeded":
        return

    for attempt in range(step.attempt_count + 1, max_attempts + 1):
        await step_repo.mark_running(session, step, attempt)
        try:
            await handler()
        except RetryableError as error:
            await step_repo.mark_retrying(session, step, error)
            if attempt == max_attempts:
                raise
            await asyncio.sleep(backoff_seconds(attempt))
        except NonRetryableError as error:
            await step_repo.mark_failed(session, step, error)
            raise
        else:
            await step_repo.mark_succeeded(session, step)
            return
```

网络超时、429、模型临时不可用属于可重试错误；字段缺失、网页结构变化、权限错误属于不可自动重试错误。每次重试使用同一个 `run_id` 和 `step_name`，推送步骤还必须使用 `batch_key` 防止消息重复。

#### 3.11.9 固定来源抓取和智能探索如何组合

固定来源是主路径，智能探索是补漏路径，二者产生的候选统一进入 `event_candidates`：

```python
class ActivitySource(Protocol):
    source_id: UUID

    async def discover(self, task: SearchTaskInput) -> list[DiscoveredLink]: ...

    async def fetch(self, url: str) -> RawPage: ...

    async def parse(self, page: RawPage) -> ExtractedEvent: ...
```

每个固定来源适配器只能处理自己的网站规则，不能修改全局配置。Worker按以下顺序执行：

1. 读取任务快照中的 `sources` 和 `cities`。
2. 调用已启用固定来源的 `discover`，保存每条 `search_tasks`。
3. 对发现的链接先用 `httpx`抓取，只有页面依赖 JavaScript时才使用 Playwright。
4. 固定来源不足 `max_leads_per_run` 或配置允许智能探索时，调用 `discovery_agent`补充线索。
5. 智能探索只能返回候选网址和理由，不能直接返回可发布活动。
6. 所有网址经过同一套抓取、事实提取、证据保存、去重和核验流程。

智能探索不需要 LangChain、LangGraph或其他 Agent 框架。第一版只需要一个带工具白名单的 Python 服务：搜索工具、打开网页工具、提取链接工具和保存候选工具。工具调用次数、允许域名和最大线索数由配置控制。

#### 3.11.10 网页事实提取的输入输出

事实提取器只负责“网页上写了什么”，不负责判断“值不值得去”：

```python
class ExtractedEvent(BaseModel):
    title: str
    start_at: datetime
    end_at: datetime | None = None
    timezone: str
    city_code: str
    venue_name: str
    venue_address: str | None = None
    organizer_name: str
    community_name: str | None = None
    canonical_url: HttpUrl
    registration_url: HttpUrl | None = None
    description_text: str
    agenda: list[AgendaItem]
    field_evidence: list[FieldEvidence]
```

解析器必须同时返回字段证据，例如 `start_at` 对应网页中的日期文本和 DOM 路径。没有标题、开始时间、城市、主办方或标准原文链接的候选不能进入正式发布；结束时间、报名链接、费用和封面是可选字段，可以明确为空。

#### 3.11.11 去重、合并和分类标签的 Python边界

去重服务不接收模型自由文本作为最终事实，只接收标准化候选：

```python
class CandidateMatcher:
    def build_identity_key(self, event: ExtractedEvent) -> str:
        return stable_hash(
            normalize_text(event.organizer_name),
            event.city_code,
            event.start_at.isoformat(),
            normalize_text(event.venue_name),
        )

    def decide(self, left: ExtractedEvent, right: ExtractedEvent) -> MatchDecision:
        if left.canonical_url == right.canonical_url:
            return MatchDecision.same_event(score=1.0)
        score = weighted_similarity(left, right)
        if score >= 0.90:
            return MatchDecision.same_event(score=score)
        if score >= 0.70:
            return MatchDecision.needs_review(score=score)
        return MatchDecision.different(score=score)
```

合并服务选择字段时按来源可信顺序执行，冲突字段保留冲突证据；大模型不能替换标题、时间、地点和主办方。分类服务输出 `category_labels`：每个标签必须包含编码、中文名称、是否主分类、置信度和证据编号，并且编码必须存在于任务快照的 `event_types`中。分类标签不是前端根据标题猜出来的颜色或文字。

#### 3.11.12 大模型调用的 Python适配层

业务代码只依赖能力接口，不依赖具体厂商：

```python
class LlmClient(Protocol):
    async def structured_completion(
        self,
        *,
        purpose: str,
        prompt_version: str,
        input_text: str,
        response_model: type[BaseModel],
    ) -> BaseModel: ...
```

`summary_service.py`负责：

1. 从 `raw_documents`和`event_evidence`组装清洗后的证据文本。
2. 根据任务用途选择固定 Prompt版本。
3. 调用模型适配器并要求结构化输出。
4. 用 Pydantic校验字段类型、数组长度和证据编号。
5. 检查 `calendar_summary`、`why_worth`、`takeaways`和`prerequisites`是否都有证据引用。
6. 将输入哈希、模型、Prompt版本、Token、耗时、原始输出和校验结果写入 `llm_runs`。

模型可以生成分析和归纳，不能生成事实字段。分类标签和摘要生成成功后仍要经过证据核验；校验失败只重试一次，并把校验错误传回模型，第二次仍失败就拒绝发布该候选。

#### 3.11.13 通勤时间计算的 Python实现

通勤计算由独立 `RouteClient`完成，发布活动前执行：

```python
class RouteClient(Protocol):
    async def calculate(
        self,
        *,
        origin: Coordinates,
        destination: Coordinates,
        mode: str,
    ) -> RouteResult: ...


class RouteResult(BaseModel):
    provider: Literal["amap", "google_maps"]
    mode: str
    duration_seconds: int = Field(ge=0)
    distance_meters: int = Field(ge=0)
    route_url: HttpUrl | None = None
```

`route_service.py`的固定顺序：

1. 读取活动地点坐标和任务快照中的出发点坐标。
2. 没有坐标时写入 `commute_status=unavailable`，不猜测分钟数。
3. 写入 `commute_status=calculating`后调用地图接口。
4. 成功后把秒数、分钟数、距离、方式、服务商、路线地址和计算时间写入活动版本。
5. 失败后写入 `failed`、错误码和脱敏错误，不阻塞其他活动。
6. 使用城市配置的最大通勤时间参与收录判断和排序。

通勤结果保存到 `event_versions`，不是只存在 Python内存或缓存中。这样活动详情、日历、15天简述和推送消息都能使用同一份计算结果。

#### 3.11.14 活动发布、日历查询和15天简述

活动发布服务只接收完成事实核验、分类、通勤和评分的候选。发布事务需要同时完成：

```text
创建或锁定 events 主记录
  → 创建 event_versions 内容版本
  → 写入 event_evidence 证据关系
  → 更新 events.current_version_id
  → 提交事务
```

提交后才允许推送。公开查询服务只查询 `events.current_version_id`指向的活动版本：

- `calendar_query.py`按日期生成从周一开始的日期格，返回城市、标题、分类标签、质量等级和通勤分钟数。
- `calendar_query.py`的 `get_brief(days=15)`查询未来15天活动，按高含金量优先、开始时间升序生成 `calendar_summary`列表。
- `event_query.py`返回下方详情列表所需的完整字段，但不返回原始网页全文、密钥和内部模型输出。
- `filter_query.py`从启用的城市、活动分类标签和技术主题生成动态筛选项。

三类查询都必须使用同一时间区间、同一时区和同一发布版本条件。前端不能用一份活动数据渲染日历、另一份本地数组渲染分类标签。

#### 3.11.15 推送适配器和幂等处理

推送通道统一为：

```python
class NotificationChannel(Protocol):
    channel_type: str

    async def send(self, message: NotificationMessage) -> DeliveryResult: ...
```

飞书、Server酱和通用 Webhook各自实现协议。Worker先在 `notification_deliveries`中创建唯一 `batch_key`，再调用外部服务；如果进程在发送后、写成功状态前崩溃，重试时先查询对方支持的幂等能力或使用相同批次键，不能无条件重复发送。

推送消息只读取公开活动版本中的标题、时间、地点、主办方、分类标签、为什么值得去和报名链接。密钥由 `secret_values`在发送时解密到内存，发送完成后不写日志、不写任务快照。

#### 3.11.16 Python测试分层

第一版至少建立以下测试层，不用真实密钥、真实地图额度或真实推送：

| 测试层 | 测试对象 | 示例 |
| --- | --- | --- |
| 单元测试 | 纯函数和领域服务 | 配置合并、日期范围、去重分数、分类校验、评分 |
| 解析器测试 | 固定网页 fixture | Luma、Meetup和高校页面的标题、时间、地点、链接提取 |
| 数据库集成测试 | PostgreSQL临时数据库 | 配置版本、任务租约、唯一幂等键、活动版本发布 |
| 外部服务契约测试 | Mock HTTP响应 | 地图、模型、飞书和Server酱错误映射 |
| 流程测试 | 完整 Worker pipeline | 固定来源→提取→合并→总结→通勤→发布→推送 |
| API测试 | FastAPI TestClient | 草稿保存、版本冲突、公开日历和15天简述接口 |

测试文件按行为命名，例如 `test_config_patch_persists_complete_json.py`、`test_calendar_brief_returns_fifteen_days.py`、`test_category_labels_require_evidence.py`。所有网络客户端必须通过依赖注入替换为 fake；测试不能访问真实活动网站或发送真实消息。

#### 3.11.17 Python依赖、启动和开发命令

Python项目使用 `pyproject.toml` 管理依赖，不把依赖版本散落在多个脚本中。第一版运行环境使用 Python 3.12或更高版本，正式部署时锁定完整依赖文件：

```toml
[project]
name = "cityactivi-server"
requires-python = ">=3.12"
dependencies = [
  "fastapi",
  "uvicorn[standard]",
  "pydantic",
  "pydantic-settings",
  "sqlalchemy[asyncio]",
  "asyncpg",
  "alembic",
  "httpx",
  "beautifulsoup4",
  "playwright",
  "cryptography",
  "argon2-cffi"
]

[project.optional-dependencies]
dev = [
  "pytest",
  "pytest-asyncio",
  "respx",
  "ruff",
  "mypy"
]
```

本地第一次启动顺序：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m playwright install chromium
alembic upgrade head
uvicorn app.main:app --app-dir services/api --reload
python -m services.scheduler.app.main
python -m services.worker.app.main
pytest
```

生产环境不使用 `--reload`。API、Scheduler和Worker分别作为独立进程运行；Docker Compose负责进程编排，systemd负责服务器重启后的自动拉起。数据库迁移由发布脚本在启动新版本前执行，禁止应用进程启动时偷偷修改表结构。

## 四、运营配置

本章是独立运营后台的完整配置模块。当前原型中的五个配置栏目全部归入本章；技术配置也放在现有“推送与自动化”栏目内部，不另建第六个主栏目。每个配置项都必须有保存位置、校验规则、实际生效对象和生效时间。

### 配置总规则：保存、发布和生效

#### 三种配置状态

| 状态 | 中文含义 | 是否影响正式任务 |
| --- | --- | --- |
| 草稿 | 在配置页保存、但尚未发布的修改 | 不影响 |
| 已发布版本 | 当前正式生效的完整配置 | 影响下一次任务 |
| 任务快照 | 某次任务启动时复制的配置副本 | 只影响该次任务 |

在卡片内点击“保存”，只更新草稿。点击页面顶部“发布更新”，后端才会校验整份配置并生成一个新的正式版本。

#### 为什么需要任务快照

假设每天07:00的任务已经开始，07:05又修改并发布了城市配置：

- 07:00启动的任务继续使用启动时的旧配置。
- 新发布的配置不会在任务中途插入。
- 下一次任务使用07:05发布的新配置。

这样可以避免同一次任务前半段搜索深圳、后半段突然变成搜索上海。

#### 发布操作

保留原型顶部现有操作位置：

- `预览页面`：使用当前草稿中的展示配置预览页面，不触发真实抓取。
- `发布更新`：发布配置，下一次定时任务使用新版本。
- `发布并立即运行`：作为“发布更新”的附加菜单，发布后立即创建一次任务。

如果校验失败，系统直接标出具体栏目、卡片和字段，不清空其他已经填写的内容。

#### 多窗口同时编辑

每个草稿保存一个版本号。如果另一个浏览器窗口已经先发布，当前窗口不能静默覆盖，而是提示：

- 当前正式版本已经更新。
- 哪些配置项发生了变化。
- 用户可以重新载入正式版本，再决定是否保留自己的草稿修改。



### 1. 搜寻范围

#### 1.1 基本范围

| 配置项 | 控件形式 | 默认值 | 实际作用 |
| --- | --- | --- | --- |
| 检索区域 | 下拉选择 | 大湾区 | 用于页面标题，并推荐一组城市 |
| 目标数量 | 下拉选择 | 12场 | 排序后最多发布多少场活动 |

“大湾区”只是一套城市预设，不是写死的搜索范围。选择后可以自动建议深圳、广州、香港、珠海和澳门，但运营人员可以删除、增加和重新排序城市。

#### 1.2 目标人群

每个目标人群都是一张可以新增、编辑、停用和删除的配置卡片。

| 字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 名称 | 是 | 例如“AI工程师”“研究生”“开源维护者” |
| 匹配关键词 | 是 | 例如 Agent、LLM、论文、DevTools |
| 优先级 | 是 | 高、中、低 |
| 是否启用 | 是 | 停用后保留配置，但不参与新任务 |

目标人群关键词只参与相关度评分，不能单独证明活动值得收录。活动本身仍然必须有明确议程或技术说明。

#### 1.3 公开来源

公开来源不再写死成 Luma、Meetup 等固定数组，而是由运营人员维护的来源卡片。

| 字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 来源名称 | 是 | 例如 Luma、某高校活动页、某开源社区官网 |
| 来源类型 | 是 | 活动平台、社区/项目、学术机构、公司活动、其他 |
| 采集方式 | 是 | 直接页面、站内检索、仅用于发现 |
| 公开入口 | 视采集方式而定 | 活动列表页、站点首页或搜索入口 |
| 覆盖城市 | 是 | 从已经配置的城市中多选 |
| 搜索优先级 | 是 | 高、中、低 |
| 是否启用 | 是 | 是否参与下一次任务 |

三种采集方式：

- **直接页面**：抓取一个明确的活动列表页或主办方页面。
- **站内检索**：在指定网站内，根据城市、主题和日期生成搜索条件。
- **仅用于发现**：只把搜索结果当作线索，必须继续找到活动官方原文才能收录。

来源的“搜索优先级”只控制先搜索谁、分配多少搜索次数，不代表该来源的事实一定更可信。

#### 1.4 智能探索

智能探索放在现有“公开来源”区域下面，不增加新的左侧导航栏目。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| 是否启用 | 启用 | 固定来源之外，是否允许 Agent 补充搜索 |
| 每次最多发现线索 | 30条 | 控制搜索范围和大模型费用 |
| 优先网站 | 空 | 运营人员希望优先查找的网站 |
| 禁止网站 | 空 | 不允许作为证据的网站 |
| 必须找到官方原文 | 固定启用 | 没有官方或可信原文的线索不能发布 |

智能探索 Agent 可以：

- 根据配置生成新的搜索组合。
- 搜索网页。
- 打开候选页面。
- 寻找活动官方页面和报名入口。
- 判断多个页面是否可能描述同一场活动。

智能探索 Agent 不可以：

- 直接把搜索摘要发布成活动。
- 自己编写标题、时间、地点和主办方。
- 绕过固定核验规则。
- 直接修改运营配置。

### 2. 时间与地点

#### 2.1 自动运行时间

| 配置项 | 可选值 | 实际作用 |
| --- | --- | --- |
| 运行频率 | 每天、工作日、每周一 | 决定什么时候创建抓取任务 |
| 运行时间 | 例如07:00、08:00、18:30 | 使用配置时区解释 |
| 时区 | 默认 Asia/Shanghai | 决定任务触发和页面时间显示 |
| 覆盖天数 | 7、15、30、60天 | 从运行当天00:00开始搜索未来活动 |

生产代码必须删除原型中写死的 `2026-08-20` 日期。每次任务都根据真实运行时间和配置时区计算日期范围。

#### 2.2 交通出发点

| 字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 起点名称 | 是 | 例如“深大地铁站” |
| 具体地址 | 是 | 用于地图检索和人工确认 |
| 经纬度 | 系统生成 | 用户选中地图地点后保存 |
| 常用出行方式 | 是 | 公共交通、驾车、步行或骑行 |
| 地图服务 | 是 | 中国大陆优先高德地图，其他区域可以配置 Google Maps |

通勤信息必须来自地图路线接口，保存以下结果：

- 预计通勤时长。
- 路线距离。
- 出行方式。
- 使用的地图服务。
- 计算时间。

不再使用原型中的固定偏移量模拟通勤时长。

#### 2.3 城市与收录门槛

城市改成真正可以新增、编辑、停用和删除的配置卡片，不再固定只有深圳、广州、珠海、香港和澳门。

| 字段 | 说明 |
| --- | --- |
| 城市 | 使用标准城市名称和内部唯一编号 |
| 收录门槛 | 仅高含金量、高和中含金量、不收录 |
| 最大通勤时长 | 可选，例如90分钟 |
| 搜索优先级 | 决定该城市获得多少搜索资源 |
| 是否启用 | 是否参与下一次任务 |

如果活动地点无法解析经纬度，系统不会因为缺少通勤数据直接删除高质量活动，而是显示“暂未计算通勤”，再按城市收录门槛判断。

### 3. 主题偏好

#### 3.1 优先主题

每个主题包含：

- 主题名称。
- 匹配关键词。
- 高、中、低优先级。
- 是否启用。

主题配置同时影响搜索计划、活动相关度评分、活动页筛选项和活动标签，但最终标签必须有活动原文支持。

#### 3.2 降权规则

每条降权规则包含名称、匹配关键词、扣分程度和启用状态。

降权不是直接删除。例如一场活动标题包含“行业趋势”，但议程中有完整的模型部署和性能优化实践，它仍然可以通过技术深度获得较高分数。

#### 3.3 活动类型

活动类型用于定义活动页右侧标签和筛选项，例如：

- 业界：公司、工程团队和产业实践。
- 学术：论文、实验室和研究分享。
- 开源：开源项目、社区和维护者活动。

运营人员可以新增类型，但系统只有在原文证据支持时才给活动添加该类型。

#### 3.4 排序规则

第一排序和第二排序支持：

- 日期与开始时间。
- 技术相关度。
- 通勤距离。

两个排序字段不能相同。分数完全相同时，使用开始时间和活动唯一编号保证结果稳定。

#### 3.5 固定技术要求

活动必须包含可核验的技术主题、议程或工程内容。纯招聘、纯商业宣传和没有技术内容的趋势活动，不能只因为命中关键词而进入正式列表。

### 4. 展示字段

#### 4.1 固定字段

以下四项不能关闭：

- 日期与时间。
- 活动标题。
- 地点。
- 主办方。

任何固定字段无法核验时，该候选活动不能正式发布。

#### 4.2 可选字段

现有可选字段全部保留：

- 社区。
- 技术方向。
- 来源。
- 为什么值得去。
- 通勤估算。
- 报名人数。
- 费用。
- 原文链接。
- 活动封面。
- 你会收获什么。
- 提前准备。

展示配置只影响页面输出，不应反向破坏搜索和评分。例如关闭“通勤估算”的页面展示，不代表城市规则不能继续使用通勤时长进行筛选。

#### 4.3 活动摘要详细度

| 选项 | 页面效果 |
| --- | --- |
| 完整摘录 | 原文内容足够时至少展示三行有效信息 |
| 标准摘要 | 展示一至两句话 |
| 只显示一句 | 只保留最关键的一句事实摘要 |

“为什么值得去”是详情页最重要的分析区，应尽量回答：

- 主办方为什么可信或具有代表性。
- 活动议程是否有真正的技术深度。
- 参加者能够获得什么实际结果。
- 最适合哪类人参加。

“你会收获什么”和“提前准备”必须根据议程生成具体条目，不能使用“拓展视野”“了解前沿”等空泛表达。

#### 4.4 缺失字段处理

启用“自动隐藏未知值”后：

- 没有封面就不渲染图片区域。
- 没有费用就不显示费用行。
- 没有报名人数就不显示报名信息。
- 不使用“暂无”“待补充”等占位内容撑开页面。

### 5. 推送与自动化

#### 5.1 推送通道

每个推送通道是一张可独立编辑的配置卡片。

| 字段 | 说明 |
| --- | --- |
| 通道名称 | 例如“技术活动群”“个人微信” |
| 通道类型 | 飞书、Server酱、通用 Webhook |
| 推送地址 | 飞书 Webhook 或服务地址 |
| 密钥 | 飞书签名密钥或 Server酱 SendKey |
| 是否启用 | 是否参与下一次推送 |
| 推送范围 | 全部入选活动或只推送高含金量活动 |

同一种通道可以配置多个，例如两个不同的飞书群。

每个通道都必须提供：

- 测试连接。
- 启用或停用。
- 清除密钥。
- 删除通道。
- 查看最近一次测试或推送结果。

停用只停止推送，不删除地址和密钥。清除密钥需要二次确认。保存后，前端只能看到“已配置密钥”，不能重新获取密钥明文。

#### 5.2 自动化状态

原型现有状态摘要改成真实数据，显示：

- 自动化名称。
- 当前运行计划。
- Prompt文件及当前提示词版本。
- 最近更新时间。
- 当前生效的配置版本。
- 最近一次运行时间和结果。
- 下一次计划运行时间。

“本地预检”在生产环境中改为“运行预检”，但保持原有按钮位置。预检检查：

- 配置字段是否完整。
- 已启用来源是否可以访问。
- 地图服务是否可用。
- 大模型是否可以调用。
- 已启用推送通道是否可以发送测试消息。

预检不抓取正式活动，也不向活动页发布结果。

原型中的“重新生成自动化”按钮保留原位置和名称。生产环境点击后执行：

1. 根据当前已发布配置重新生成标准化任务定义。
2. 固化本次使用的 Prompt 版本和模型任务说明。
3. 重新计算下一次运行时间。
4. 校验 Scheduler 是否已经加载新定义。
5. 返回新任务定义版本、更新时间和下一次运行时间。

Prompt文件不再作为唯一真实配置来源。数据库中的已发布配置和任务定义版本是正式依据，Prompt文件只作为可查看、可审计和可导出的生成结果。

#### 5.3 大模型服务配置

大模型配置放在“推送与自动化”栏目中，位于自动化状态下方，继续使用现有 `section-block` 和 `setting-row` 样式。

| 字段 | 控件 | 默认建议 | 生效方式 |
| --- | --- | --- | --- |
| 服务名称 | 输入框 | 主总结模型 | 仅用于后台识别 |
| 服务商 | 下拉选择 | 已实现的模型适配器 | 下一次模型调用生效 |
| 接口地址 | 输入框 | 服务商默认地址 | 下一次模型调用生效 |
| 模型名称 | 可搜索选择或输入 | 由服务商提供 | 下一次模型调用生效 |
| API密钥 | 密码输入框 | 无 | 保存后只显示已配置 |
| 请求超时 | 数字选择 | 60秒 | 下一次模型调用生效 |
| 输出最大长度 | 数字选择 | 由任务类型设置默认值 | 下一次模型调用生效 |
| 温度 | 数字选择 | 0.2 | 控制输出随机性 |
| 单次任务费用上限 | 金额输入 | 运营人员设置 | 超限后停止非必要调用 |
| 备用模型 | 可选选择 | 无 | 主模型连续失败后使用 |
| 是否启用 | 开关 | 启用 | 控制该模型服务是否可用 |

每个模型配置卡片提供：

- 测试连接：发送最小测试请求，不包含活动隐私数据。
- 测试结构化输出：检查模型能否按 Pydantic 规定格式返回。
- 替换密钥：只允许覆盖，不能读取原密钥。
- 清除密钥：二次确认后删除加密值。
- 查看最近成功时间、平均耗时和最近错误。

模型配置保存到 `model_providers`，API密钥保存到独立的 `secret_values`。活动任务快照只保存模型配置编号和模型名称，不包含密钥明文。

#### 5.4 网页抓取运行参数

抓取参数与大模型配置并列显示，字段全部使用选择器或有上下限的数字输入，避免误填导致服务器失控。

| 字段 | 默认建议 | 允许范围 | 说明 |
| --- | ---: | ---: | --- |
| 普通网页并发数 | 4 | 1至16 | 同时使用 httpx 抓取的页面数 |
| 浏览器并发数 | 1 | 0至3 | 同时运行的 Playwright 浏览器页面数 |
| 单页请求超时 | 20秒 | 5至120秒 | 单次网页请求最长等待时间 |
| 最大重试次数 | 2 | 0至5 | 临时网络错误的重试次数 |
| 同域名最小间隔 | 1.5秒 | 0.5至30秒 | 防止短时间请求同一网站过多 |
| 单页最大体积 | 5MB | 1至20MB | 超过限制时停止下载正文 |
| JavaScript页面回退 | 启用 | 开关 | 普通抓取无内容时是否尝试 Playwright |
| 代理地址 | 空 | 可选 | 仅在明确配置代理时使用 |
| 自定义 User-Agent | 系统默认 | 可选 | 网页请求标识，不允许伪装浏览器安全信息 |

修改并保存后写入 `system_settings`，新领取的任务使用新参数，已经在执行的网页请求不被中途取消。

为防止低配置服务器失控，后端还保留不可突破的安全上限。例如运营页面即使提交普通网页并发100，后端也会拒绝，而不是相信前端校验。

#### 5.5 数据库连接配置

运营后台提供数据库连接卡片，但数据库连接不能只保存在 PostgreSQL 自身。原因是：一旦当前数据库无法连接，API就无法从数据库读取“应该连接哪个数据库”。这属于启动自依赖问题。

因此数据库配置采用两层设计：

```text
运营后台数据库卡片
  → 测试候选连接
  → 保存到服务器外部待应用配置
  → Runtime Controller 应用
  → 重启 API、Worker、Scheduler
  → 健康检查
  → 成功确认或自动回滚
```

数据库卡片字段：

| 字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 连接名称 | 是 | 例如“CityActivi生产数据库” |
| 主机地址 | 是 | PostgreSQL服务器域名或内网地址 |
| 端口 | 是 | 默认5432 |
| 数据库名称 | 是 | 例如 `cityactivi` |
| 用户名 | 是 | 应用专用数据库账户 |
| 密码 | 是 | 只写字段，保存后不回显 |
| SSL模式 | 是 | disable、prefer、require、verify-full |
| 连接池大小 | 是 | 默认5，控制常驻连接数 |
| 最大临时连接 | 是 | 默认5，控制高峰附加连接数 |
| 连接超时 | 是 | 默认10秒 |
| 应用状态 | 系统显示 | 当前生效、待应用、应用失败、已回滚 |

按钮及行为：

- `测试连接`：使用候选配置执行连接、`SELECT 1`、数据库版本检查和必要扩展检查，不修改当前连接。
- `保存待应用`：把候选配置加密写入服务器配置目录，不立即中断系统。
- `应用并重启`：调用只监听本机 Unix Socket 的 Runtime Controller。
- `撤销待应用`：删除尚未生效的候选配置。
- `恢复上一版本`：恢复最近一次确认成功的运行配置。

Runtime Controller 是一个很小的本机运行控制服务，不暴露公网端口，只负责：

- 写入 `/etc/cityactivi/runtime.env`，文件权限设为仅服务账户可读。
- 保存上一版可用配置。
- 重启 API、Worker 和 Scheduler。
- 调用健康检查接口。
- 健康检查失败时恢复上一版并再次重启。

数据库密码既不写入业务数据库，也不进入 Git、日志、接口响应和任务快照。

#### 5.6 技术配置在现有UI中的位置

左侧导航仍然只有原型现有五项。“推送与自动化”内部按以下顺序纵向排列：

1. 推送通道。
2. 自动化状态。
3. 大模型服务。
4. 网页抓取参数。
5. 数据库连接。

新增内容使用和现有页面完全相同的标题行、设置行、配置卡片、状态文字和按钮层级。默认只展示配置摘要；点击当前卡片的“编辑”后在原位置展开常用字段，低频字段放进卡片内部的“更多设置”。

不允许为了容纳技术字段做以下改动：

- 不增加新的左侧导航。
- 不改成表格密集型后台。
- 不使用右侧抽屉或全屏弹窗。
- 不删除原来的推送、自动化状态和预检内容。
- 不改变顶部“预览页面”和“发布更新”的位置。

#### 5.7 产品配置与技术配置的生效差异

| 配置类型 | 保存位置 | 是否进入活动任务快照 | 生效时间 |
| --- | --- | --- | --- |
| 搜寻、城市、主题、展示 | `config_versions` | 是 | 发布后的下一任务 |
| 推送通道路由 | `config_versions`和通道表 | 是，不包含密钥 | 发布后的下一任务 |
| 大模型模型选择 | `model_providers`和快照引用 | 是，不包含密钥 | 下一次模型调用 |
| 抓取并发和超时 | `system_settings` | 任务记录参数版本 | 新领取的任务 |
| 主数据库连接 | 服务器运行配置文件 | 否 | 应用并重启成功后 |

技术配置不会混入普通运营配置版本的 JSON 中，但都在同一个运营后台页面完成管理。这样既保持原型的统一体验，也避免数据库连接、密钥等服务器级配置被错误复制到每一次任务快照。

### 配置结果与合并规则

#### 配置作用映射

| 首页内容 | 来自哪个配置 |
| --- | --- |
| 日期范围切换 | 覆盖天数 |
| 日历中的城市文字 | 已启用城市 |
| 主题筛选 | 已启用主题和已发布活动中的实际主题 |
| 活动类型筛选 | 已启用活动类型 |
| 活动数量上限 | 目标数量 |
| 详情展示字段 | 展示字段开关 |
| 为什么值得去的长度 | 摘要详细度 |
| 高含金量标记 | 含金量分数和可信度 |
| 通勤时间 | 出发点、地图计算结果和展示开关 |
| 日历上方的未来15天活动简述 | `output.calendar_brief_days`、`output.calendar_brief_limit` 和活动版本 `calendar_summary` |
| 日历右侧活动分类标签 | 已启用 `event_types` 和活动版本 `category_labels` |

如果配置覆盖60天，首页提供15天、30天和60天三个范围。首页不能选择超过后台实际抓取范围的日期。

日历默认紧凑展示，展开和收起只改变页面显示，不重新抓取数据。日历上方的活动简述默认取未来15天；如果运营配置覆盖范围为30天或60天，用户切换日历范围后，简述接口可以按当前范围重新返回，但默认首屏仍为15天。

#### 配置合并规则

“配置合并”指把系统默认值、当前正式配置和本次草稿修改整理成一份完整的新版本，它与活动去重不是一回事。

优先顺序：

```text
系统字段默认值
  < 当前已经发布的完整配置
  < 本次草稿修改
```

具体规则：

- 普通对象按字段进行深层合并。
- 目标人群、来源、城市、主题和通道等列表项按唯一编号合并。
- 不使用数组位置判断同一项。
- 新增、修改、停用和删除都是明确操作。
- 用户已经删除的默认来源，系统升级后不能悄悄重新添加。
- 发布时保存一份完整配置，不只保存本次修改的几个字段。
- 推送密钥只通过通道编号引用，不写进任务配置快照。
- 任务启动时复制已发布配置，运行中不再动态合并新配置。

## 五、一次活动的完整处理流程

本章描述一场活动从任务创建到活动页发布、通知发送和失败恢复的完整生命周期。搜索计划、网页抓取、事实提取、去重合并、大模型总结、证据核验、评分、发布和推送都是同一条流程中的阶段，不拆成平级产品模块。

### 流程总览和阶段状态

```text
等待执行
  → 发现活动线索
  → 抓取网页
  → 提取事实字段
  → 去重和合并
  → 大模型总结
  → 证据核验
  → 通勤时间计算
  → 含金量评分与排序
  → 发布活动页
  → 推送通知
  → 完成
```

| 阶段 | 具体工作 | 失败处理 |
| --- | --- | --- |
| 等待执行 | 等待后台任务进程领取 | 执行进程异常后可以重新领取 |
| 发现线索 | 根据配置生成查询并发现候选网址 | 单个来源失败不影响其他来源 |
| 抓取网页 | 下载活动页面正文 | 临时网络错误自动重试 |
| 提取字段 | 提取标题、时间、地点、主办方和议程 | 保留原网页和失败原因 |
| 去重合并 | 判断不同页面是否是同一活动 | 字段冲突进入核验 |
| 大模型总结 | 生成价值、收获和准备内容 | 输出格式错误时重试一次 |
| 证据核验 | 检查总结是否有原文支持 | 不合格内容拒绝发布 |
| 通勤计算 | 根据出发点、活动坐标和出行方式调用地图路线接口 | 标记不可用，不伪造时间 |
| 评分排序 | 根据正式配置计算分数 | 使用确定性计算，不让模型随意给分 |
| 发布活动 | 写入正式活动版本 | 使用数据库事务避免发布一半 |
| 推送通知 | 向各个启用通道发送 | 推送失败不撤销已发布活动 |

### 阶段 1：生成任务快照、搜索计划与候选发现

系统根据本次任务的配置快照生成有限数量的搜索任务，不会把所有城市、主题、人群和来源直接全部相乘，否则查询数量会失控。

生成顺序：

1. 根据来源优先级分配搜索次数。
2. 把相近主题关键词合成主题组。
3. 根据城市和来源能力生成搜索任务。
4. 加入本次任务的日期范围。
5. 达到来源搜索预算或候选数量上限后停止扩展。
6. 保存实际使用过的搜索条件，方便后续排查。

一条内部搜索任务示例：

```text
城市：深圳
主题：Agent、RAG、MCP
活动类型：业界、开源
日期：2026-09-03 至 2026-09-17
来源：Luma
```

修改并发布城市、主题、来源或覆盖天数后，下一次任务会自动重新生成搜索计划，不需要修改 Python 代码。

### 阶段 2：抓取网页、提取事实与原文证据

候选网址进入处理队列后，先完成网页抓取和事实字段提取，再允许大模型参与分析。处理顺序固定如下：

1. 读取 `search_tasks` 中的候选网址和来源配置。
2. 先使用 `httpx` 请求普通静态页面，记录请求地址、响应状态、响应头、正文大小和抓取时间。
3. 如果正文为空、页面依赖 JavaScript 或页面只返回应用壳，再按来源配置决定是否使用 Playwright。
4. 对页面正文进行 HTML 清洗，移除导航、广告、重复页脚和无关脚本。
5. 优先读取标题、发布时间、JSON-LD、Open Graph、结构化活动字段和正文中的议程。
6. 把原始正文、清洗正文、结构化数据、内容哈希和解析器版本保存到 `raw_documents`。
7. 将提取结果写入 `event_candidates`，字段包括标题、开始时间、结束时间、地点、城市、主办方、活动描述、议程、原文链接和报名链接。
8. 每个提取字段都创建对应的 `event_evidence` 候选引用，保存原文片段和所在位置。

事实字段的处理规则：

| 字段 | 提取要求 | 缺失时的处理 |
| --- | --- | --- |
| 标题 | 使用页面标题或官方活动标题 | 缺失则拒绝候选 |
| 开始时间 | 解析日期、时间和活动时区 | 缺失或无法解析则进入核验 |
| 结束时间 | 优先官方结束时间 | 缺失可以为空，不自行推测 |
| 城市 | 从地点地址或来源城市规则解析 | 无法确定城市则不发布 |
| 地点 | 保存场地名称和详细地址 | 只有线上活动时记录线上地点类型 |
| 主办方 | 优先页面明确声明的组织者 | 缺失则进入核验 |
| 议程 | 保留演讲、工作坊、主题和时间段 | 没有议程但有技术正文，标记议程不完整 |
| 原文链接 | 归一化为标准原文地址 | 缺失则拒绝候选 |
| 报名链接 | 优先官方报名入口 | 缺失不影响发布，但隐藏报名入口 |

页面抓取和事实提取完成后，系统才进入去重、合并和大模型处理阶段。

### 阶段 3：活动去重与多来源合并

#### 判断是不是同一场活动

按以下顺序判断：

1. 来源相同，并且来源内部活动编号相同。
2. 标准原文地址相同。
3. 主办方、城市、开始时间相同，标题高度相似。
4. 标题高度相似，开始时间相差不超过90分钟，地点距离较近。

前两种可以直接认定。后两种计算重复可信度：高可信度自动合并，中等可信度进入核验，低可信度保留为不同活动。

#### 事实来源可信顺序

默认顺序：

```text
主办方官方网站
  > 官方报名页面
  > 可信活动平台
  > 社区转发页面
  > 搜索结果摘要
```

运营配置中的“来源优先级”控制搜索资源，不改变事实可信顺序。即使某个转载来源设置为高优先级，也不能覆盖主办方官网公布的活动时间。

#### 不同字段怎么合并

| 字段 | 合并规则 |
| --- | --- |
| 标题 | 优先使用官方完整标题，其他标题作为别名保留 |
| 开始和结束时间 | 优先官方时间，保存时区和冲突证据 |
| 地点 | 优先官方精确地址，合并后再进行地图解析 |
| 主办方 | 统一名称用于去重，同时保留原始显示名称 |
| 报名链接 | 优先真正的官方报名入口 |
| 议程 | 合并不重复的议程项目，并保留各自证据 |
| 主题和活动类型 | 合并有证据支持的分类，删除没有证据的猜测 |
| 活动描述 | 原文分别保存，页面摘要根据全部有效证据重新生成 |

标题、时间、地点和主办方发生冲突时，不能交给大模型随意选择。系统必须进入核验流程，或者暂不发布。

### 阶段 4：大模型总结与证据核验

系统把页面内容分为三类：

| 类型 | 中文含义 | 示例 |
| --- | --- | --- |
| 原文提取 | 网页中直接出现 | “9月18日19:00开始” |
| 计算得出 | 根据事实计算 | “从深大地铁站预计42分钟” |
| 大模型分析 | 模型根据议程进行判断 | “适合了解基本 RAG 流程的工程师” |

大模型接收清洗后的网页证据，并按照固定结构返回：

- 活动摘要。
- 日历上方使用的未来15天活动简述。
- 为什么值得参加。
- 可以获得什么。
- 需要提前准备什么。
- 技术主题标签。
- 活动类型判断。
- 活动分类标签及主分类标记。
- 每一项判断引用了哪些证据。

标题、时间、地点和主办方不能从大模型生成结果中取值。

活动详情中的事实性陈述，至少80%必须能够关联到保存的网页证据。大模型可以在“为什么值得去”等分析区域进行归纳，但不能把推测写成原文事实。

### 阶段 5：通勤时间计算与可达性判断

通勤计算是发布前的固定处理步骤，不是前端打开活动卡片后临时计算。它使用任务快照中的出发点和城市配置，对每一场已经完成去重、合并和事实核验的活动执行一次路线计算。

执行顺序：

1. 检查活动是否有可解析的场地坐标；线上活动记录 `commute_status=unavailable`，不调用路线接口。
2. 读取任务快照中的出发点名称、经纬度、出行方式和地图服务。
3. 将活动坐标、出发点坐标、出行方式和活动版本编号写入待计算记录，状态设为 `calculating`。
4. 调用已配置的高德地图或 Google Maps 路线接口，记录请求时间、服务商、返回状态和脱敏响应摘要。
5. 成功时保存预计分钟数、原始秒数、距离、出行方式、路线地址、出发点坐标快照和计算时间，状态改为 `succeeded`。
6. 因配额、网络、坐标或服务错误失败时保存错误代码，状态改为 `failed` 或 `unavailable`，不能用固定偏移量猜测分钟数。
7. 按城市配置的 `max_commute_minutes` 和 `include_threshold` 判断活动是否满足收录门槛；缺少通勤结果时按明确的城市规则处理，不静默放宽门槛。

通勤结果必须随活动版本保存，不能只保存在缓存中。出发点或地图服务配置发生变化后，下一次任务重新计算；历史活动版本继续保留当时的计算结果，保证页面和通知可追溯。

### 阶段 6：含金量评分与排序

默认满分100分：

| 评分项 | 默认分值 |
| --- | ---: |
| 主题相关度 | 30分 |
| 议程技术深度 | 20分 |
| 主办方可信度 | 15分 |
| 目标人群匹配 | 15分 |
| 是否有具体收获 | 10分 |
| 证据完整度 | 10分 |

降权规则根据严重程度扣10至30分。

默认判断：

- 高含金量：总分不低于80，并且事实可信度不低于0.8。
- 中含金量：总分65至79。
- 低于65：默认不进入正式活动页。

活动最终是否收录，还要继续应用对应城市的收录门槛和通勤规则。

### 阶段 7：异常处理、重试与恢复

异常处理属于一次活动的完整生命周期，不单独作为平级产品模块。每个阶段都要保存状态、错误代码、重试次数和可恢复位置。

#### 自动重试规则

| 错误类型 | 是否重试 | 默认策略 |
| --- | --- | --- |
| 网络连接中断 | 是 | 最多2次，逐渐延长等待 |
| HTTP 429限流 | 是 | 优先使用对方返回的等待时间 |
| HTTP 500至599 | 是 | 最多2次 |
| HTTP 401或403 | 否 | 标记凭证或权限错误 |
| HTTP 404 | 否 | 标记来源页面失效 |
| 网页结构变化 | 否自动重试 | 保存原文并标记解析器异常 |
| 大模型超时 | 是 | 重试一次，可切换备用模型 |
| 大模型结构错误 | 是 | 带校验错误重试一次 |
| 推送临时失败 | 是 | 独立重试，不撤销活动 |
| 数据库事务冲突 | 是 | 短暂等待后重试事务 |

重试必须从失败的具体阶段继续，不重新执行已经成功的所有阶段。每次重试使用相同的任务编号和步骤编号，避免产生重复活动和重复消息。

#### 故障隔离

- 某一个来源抓取失败，不能取消其他来源的任务。
- 某一场活动总结失败，不能阻止其他候选活动继续处理。
- 推送失败不能撤销已经发布的活动。
- 地图服务失败时，活动仍可根据城市和质量规则判断，但通勤字段标记不可用。
- 大模型完全不可用时，不发布缺少分析字段的新活动；已经存在的已发布活动仍可访问。
- 原始网页保留到处理结束，解析失败时可以重新运行解析器，不需要重新访问网页。

#### 数据库配置应用失败

- 候选连接测试失败时禁止保存为待应用版本。
- 重启后健康检查必须同时验证 API、数据库查询和 Worker 心跳。
- 健康检查超时后 Runtime Controller 自动恢复上一版配置。
- 回滚成功和失败都写入审计日志和运行配置修订表。
- 如果自动回滚也失败，Nginx继续提供静态错误页，服务器保留完整控制日志供命令行修复。

#### 接口错误如何回到流程

接口返回错误时，前端必须根据字段路径把错误显示在当前配置卡片内；后台任务错误则显示在任务步骤详情中。错误信息至少包含错误代码、可读说明、任务编号或请求编号和是否可以重试。

## 六、数据库详细设计

### 6.1 数据库字段统一规则（PostgreSQL）

- 所有业务主键使用 `uuid`。
- 所有时间使用 `timestamptz`，即带时区时间。
- 金额使用 `numeric(12,4)`，不使用浮点数。
- 经纬度使用 `numeric(10,7)`。
- 状态字段第一版使用受约束的 `varchar`，避免数据库枚举升级困难。
- 创建时间和更新时间统一使用 `created_at`、`updated_at`。
- 可搜索的固定事实使用普通列，配置快照和模型输出使用 `jsonb`。
- 密钥不使用普通 `text` 保存，统一进入加密密钥表。

### 6.2 谁可以登录运营后台（`ops_users`）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid | 主键 | 运营用户编号 |
| `email` | varchar(255) | 非空、唯一 | 登录账号 |
| `password_hash` | text | 非空 | Argon2id 密码哈希，不保存原密码 |
| `display_name` | varchar(100) | 非空 | 页面显示名称 |
| `role` | varchar(32) | 非空、默认 operator | 预留管理员和运营角色 |
| `is_active` | boolean | 非空、默认 true | 是否允许登录 |
| `last_login_at` | timestamptz | 可空 | 最近成功登录时间 |
| `created_at` | timestamptz | 非空 | 创建时间 |
| `updated_at` | timestamptz | 非空 | 更新时间 |

索引：`email` 唯一索引，`is_active` 普通索引。

### 6.3 登录状态和会话有效期（`ops_sessions`）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid | 主键 | 会话编号 |
| `user_id` | uuid | 外键、非空 | 关联运营用户 |
| `token_hash` | text | 非空、唯一 | 会话令牌哈希 |
| `csrf_hash` | text | 非空 | 防跨站请求令牌哈希 |
| `ip_address` | inet | 可空 | 登录IP |
| `user_agent` | text | 可空 | 浏览器标识 |
| `last_seen_at` | timestamptz | 非空 | 最近活动时间 |
| `expires_at` | timestamptz | 非空 | 到期时间 |
| `revoked_at` | timestamptz | 可空 | 主动退出或撤销时间 |
| `created_at` | timestamptz | 非空 | 创建时间 |

索引：`token_hash` 唯一索引，`user_id, expires_at` 组合索引。

### 6.4 一套活动助手的基本信息（`assistant_profiles`）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid | 主键 | 活动助手编号 |
| `slug` | varchar(80) | 非空、唯一 | URL和系统识别名称 |
| `name` | varchar(120) | 非空 | 例如“线下技术活动情报晨报” |
| `region_label` | varchar(100) | 非空 | 页面展示区域名称 |
| `timezone` | varchar(64) | 非空 | 默认 Asia/Shanghai |
| `published_config_id` | uuid | 可空、外键 | 当前正式配置版本 |
| `draft_config_id` | uuid | 可空、外键 | 当前草稿版本 |
| `is_active` | boolean | 非空、默认 true | 是否允许定时创建任务 |
| `created_by` | uuid | 外键、非空 | 创建人 |
| `created_at` | timestamptz | 非空 | 创建时间 |
| `updated_at` | timestamptz | 非空 | 更新时间 |

### 6.5 配置草稿、正式版本和发布记录（`config_versions`）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid | 主键 | 配置版本编号 |
| `profile_id` | uuid | 外键、非空 | 所属活动助手 |
| `version_number` | integer | 非空 | 同一助手内递增版本号 |
| `status` | varchar(20) | 非空 | draft、published、archived |
| `base_version_id` | uuid | 可空、外键 | 草稿基于哪个正式版本创建 |
| `schema_version` | integer | 非空 | 配置JSON结构版本 |
| `config_json` | jsonb | 非空 | 完整、标准化配置 |
| `checksum` | char(64) | 非空 | 配置内容 SHA-256 校验值 |
| `change_summary` | text | 可空 | 本次发布说明 |
| `created_by` | uuid | 外键、非空 | 创建人 |
| `published_by` | uuid | 可空、外键 | 发布人 |
| `published_at` | timestamptz | 可空 | 发布时间 |
| `created_at` | timestamptz | 非空 | 创建时间 |
| `updated_at` | timestamptz | 非空 | 更新时间 |

约束和索引：

- `profile_id, version_number` 唯一。
- 同一 `profile_id` 只能有一个状态为 draft 的当前草稿。
- 发布后禁止修改 `config_json`，只能创建下一版本。
- `config_json` 建 GIN 索引只用于后台诊断，不作为主要业务查询方式。

### 6.6 配置里到底保存哪些内容（完整 `config_json`）

`config_versions.config_json` 必须保存一份完整配置，不能只保存本次修改的字段，也不能使用空对象或空数组代替已经定义的配置项。前端可以用 `PATCH` 提交局部修改，但后端合并后写入数据库的 `config_json` 必须包含下面所有根字段和数组对象字段。

| 根字段 | 必须包含的子字段 | 数据用途 |
| --- | --- | --- |
| `schema_version` | 配置结构版本号 | 让后端按版本执行配置迁移 |
| `region` | 区域名称 | 页面标题和城市预设识别 |
| `target_count` | 目标数量 | 正式活动最多发布数量 |
| `hide_expired` | 是否隐藏过期活动 | 首页结果过滤 |
| `schedule` | `frequency`、`time`、`coverage_days`、`timezone` | 定时运行和搜索日期范围 |
| `origin` | 名称、地址、经纬度、出行方式、地图服务、地图地址 | 通勤时间计算 |
| `cities` | `id`、城市编号、名称、收录门槛、最大通勤时长、搜索优先级、启用状态、排序 | 城市检索和通勤筛选 |
| `audiences` | `id`、名称、关键词、优先级、启用状态、排序 | 目标人群匹配 |
| `sources` | `id`、名称、来源类型、采集方式、入口地址、覆盖城市、搜索优先级、启用状态、排序 | 固定来源抓取 |
| `discovery` | 启用状态、最大线索数、优先网站、禁止网站、必须找到官方原文 | 智能探索边界 |
| `topics` | `id`、名称、关键词、优先级、启用状态、排序 | 搜索、评分和筛选标签 |
| `weak_content_rules` | `id`、名称、关键词、扣分分值、启用状态、排序 | 低质量活动降权 |
| `event_types` | `id`、编码、名称、定义、启用状态、排序 | 活动分类标签和筛选 |
| `sort` | 第一排序、第二排序 | 活动列表稳定排序 |
| `preferences` | 中文标题偏好、隐藏未知值 | 展示偏好 |
| `display_fields` | 原型中的全部字段开关 | 详情页字段显示 |
| `output` | 摘要详细度、日历简述范围、推送样式、时间格式、时区模式、日历城市/分类/通勤开关 | 首页和推送输出 |
| `channel_routes` | `id`、通道编号、名称、通道类型、推送范围、启用状态、排序 | 推送路由 |

以下是第一版可以直接作为数据库种子、Pydantic默认值和前端初始状态的完整配置实例：

```json
{
  "schema_version": 1,
  "region": "大湾区",
  "target_count": 12,
  "hide_expired": true,
  "schedule": {
    "frequency": "daily",
    "time": "07:00",
    "coverage_days": 15,
    "timezone": "Asia/Shanghai"
  },
  "origin": {
    "name": "深大地铁站",
    "address": "深圳市南山区深大地铁站",
    "latitude": 22.5333000,
    "longitude": 113.9364000,
    "travel_mode": "transit",
    "map_provider": "amap",
    "map_url": "https://uri.amap.com/marker?position=113.9364,22.5333&name=深大地铁站"
  },
  "cities": [
    {
      "id": "11111111-1111-4111-8111-111111111111",
      "city_code": "shenzhen",
      "name": "深圳",
      "country_code": "CN",
      "include_threshold": "medium",
      "max_commute_minutes": 90,
      "search_priority": "high",
      "is_enabled": true,
      "sort_order": 1
    },
    {
      "id": "22222222-2222-4222-8222-222222222222",
      "city_code": "guangzhou",
      "name": "广州",
      "country_code": "CN",
      "include_threshold": "medium",
      "max_commute_minutes": 120,
      "search_priority": "high",
      "is_enabled": true,
      "sort_order": 2
    },
    {
      "id": "33333333-3333-4333-8333-333333333333",
      "city_code": "hong_kong",
      "name": "香港",
      "country_code": "HK",
      "include_threshold": "high",
      "max_commute_minutes": 150,
      "search_priority": "medium",
      "is_enabled": true,
      "sort_order": 3
    },
    {
      "id": "44444444-4444-4444-8444-444444444444",
      "city_code": "zhuhai",
      "name": "珠海",
      "country_code": "CN",
      "include_threshold": "high",
      "max_commute_minutes": 150,
      "search_priority": "medium",
      "is_enabled": true,
      "sort_order": 4
    }
  ],
  "audiences": [
    {
      "id": "51111111-1111-4111-8111-111111111111",
      "name": "AI工程师",
      "keywords": ["Agent", "LLM", "RAG", "MCP", "模型部署"],
      "priority": "high",
      "is_enabled": true,
      "sort_order": 1
    },
    {
      "id": "52222222-2222-4222-8222-222222222222",
      "name": "开源维护者",
      "keywords": ["开源", "GitHub", "贡献者", "维护者", "社区"],
      "priority": "high",
      "is_enabled": true,
      "sort_order": 2
    },
    {
      "id": "53333333-3333-4333-8333-333333333333",
      "name": "研究生与研究人员",
      "keywords": ["论文", "实验室", "研究分享", "学术", "方法"],
      "priority": "medium",
      "is_enabled": true,
      "sort_order": 3
    }
  ],
  "sources": [
    {
      "id": "61111111-1111-4111-8111-111111111111",
      "name": "Luma",
      "source_type": "event_platform",
      "collection_method": "direct_page",
      "entry_url": "https://lu.ma/discover",
      "covered_cities": ["shenzhen", "guangzhou", "hong_kong", "zhuhai"],
      "search_priority": "high",
      "is_enabled": true,
      "sort_order": 1
    },
    {
      "id": "62222222-2222-4222-8222-222222222222",
      "name": "Meetup",
      "source_type": "event_platform",
      "collection_method": "site_search",
      "entry_url": "https://www.meetup.com/find/",
      "covered_cities": ["shenzhen", "guangzhou", "hong_kong"],
      "search_priority": "medium",
      "is_enabled": true,
      "sort_order": 2
    },
    {
      "id": "63333333-3333-4333-8333-333333333333",
      "name": "高校与实验室活动页",
      "source_type": "academic_institution",
      "collection_method": "direct_page",
      "entry_url": "https://www.szu.edu.cn/",
      "covered_cities": ["shenzhen", "guangzhou"],
      "search_priority": "medium",
      "is_enabled": true,
      "sort_order": 3
    },
    {
      "id": "64444444-4444-4444-8444-444444444444",
      "name": "开源社区官方活动页",
      "source_type": "community_project",
      "collection_method": "official_only_discovery",
      "entry_url": "https://github.com/explore",
      "covered_cities": ["shenzhen", "guangzhou", "hong_kong", "zhuhai"],
      "search_priority": "medium",
      "is_enabled": true,
      "sort_order": 4
    }
  ],
  "discovery": {
    "is_enabled": true,
    "max_leads_per_run": 30,
    "preferred_domains": ["lu.ma", "meetup.com", "github.com", "szu.edu.cn"],
    "blocked_domains": ["example-spam.invalid"],
    "require_official_source": true
  },
  "topics": [
    {
      "id": "71111111-1111-4111-8111-111111111111",
      "name": "Agent与智能体工程",
      "keywords": ["Agent", "智能体", "工具调用", "MCP", "工作流"],
      "priority": "high",
      "is_enabled": true,
      "sort_order": 1
    },
    {
      "id": "72222222-2222-4222-8222-222222222222",
      "name": "大模型应用与RAG",
      "keywords": ["LLM", "RAG", "向量数据库", "Prompt", "评测"],
      "priority": "high",
      "is_enabled": true,
      "sort_order": 2
    },
    {
      "id": "73333333-3333-4333-8333-333333333333",
      "name": "开源工程与开发者工具",
      "keywords": ["开源", "DevTools", "GitHub", "SDK", "基础设施"],
      "priority": "medium",
      "is_enabled": true,
      "sort_order": 3
    }
  ],
  "weak_content_rules": [
    {
      "id": "81111111-1111-4111-8111-111111111111",
      "name": "纯招聘活动",
      "keywords": ["招聘", "岗位介绍", "面试", "人才招募"],
      "penalty_points": 25,
      "is_enabled": true,
      "sort_order": 1
    },
    {
      "id": "82222222-2222-4222-8222-222222222222",
      "name": "缺少技术议程的宣传活动",
      "keywords": ["品牌发布", "产品宣传", "商务交流", "闭门交流"],
      "penalty_points": 20,
      "is_enabled": true,
      "sort_order": 2
    }
  ],
  "event_types": [
    {
      "id": "91111111-1111-4111-8111-111111111111",
      "code": "industry",
      "name": "业界",
      "description": "公司、工程团队和产业实践活动",
      "is_enabled": true,
      "sort_order": 1
    },
    {
      "id": "92222222-2222-4222-8222-222222222222",
      "code": "academic",
      "name": "学术",
      "description": "论文、实验室和研究方法分享活动",
      "is_enabled": true,
      "sort_order": 2
    },
    {
      "id": "93333333-3333-4333-8333-333333333333",
      "code": "open_source",
      "name": "开源",
      "description": "开源项目、社区和维护者活动",
      "is_enabled": true,
      "sort_order": 3
    }
  ],
  "sort": {
    "primary": "start_time",
    "secondary": "relevance"
  },
  "preferences": {
    "prefer_chinese_title": true,
    "hide_unknown": true
  },
  "display_fields": {
    "community": true,
    "topic": true,
    "source": true,
    "why": true,
    "travel": true,
    "registered": false,
    "cost": false,
    "source_link": true,
    "cover": false,
    "takeaways": true,
    "prerequisites": true
  },
  "output": {
    "summary_length": "full",
    "calendar_brief_days": 15,
    "calendar_brief_limit": 12,
    "calendar_show_city": true,
    "calendar_show_category_labels": true,
    "calendar_show_commute": true,
    "push_style": "key_content",
    "time_format": "24h",
    "timezone_mode": "assistant"
  },
  "channel_routes": [
    {
      "id": "a1111111-1111-4111-8111-111111111111",
      "channel_id": "b1111111-1111-4111-8111-111111111111",
      "channel_name": "技术活动飞书群",
      "channel_type": "feishu",
      "delivery_scope": "high_value",
      "is_enabled": true,
      "sort_order": 1
    },
    {
      "id": "a2222222-2222-4222-8222-222222222222",
      "channel_id": "b2222222-2222-4222-8222-222222222222",
      "channel_name": "个人Server酱",
      "channel_type": "serverchan",
      "delivery_scope": "all",
      "is_enabled": true,
      "sort_order": 2
    }
  ]
}
```

字段规则：

- 上例中的 UUID 是初始化种子编号示例；新建配置项由后端生成真正的 UUID，不能由数组位置充当身份。
- `blocked_domains` 中的 `example-spam.invalid` 只是用于说明字段结构的不可解析示例，生产初始化时应删除该条目，不能把它当成真实来源规则。
- `channel_routes` 只保存通道编号和路由规则；飞书 Webhook、飞书签名密钥、Server酱 SendKey等密钥必须保存在 `secret_values`，不能写入 `config_json`。
- `origin.latitude`、`origin.longitude`必须来自地图选点结果；如果用户更换出发点，不能继续使用旧坐标。
- 允许为空的字段必须在 Pydantic 模型中明确声明为可空，例如活动结束时间、封面地址、报名人数和费用；配置章节中的必填字段不能用空字符串代替。
- 后端启动时校验根字段集合、数组对象字段集合和 `schema_version`。缺少字段时先用版本化默认值补齐并生成迁移记录，禁止静默丢字段。

### 6.7 大模型、推送和地图密钥的加密存储（`secret_values`）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid | 主键 | 密钥编号 |
| `scope` | varchar(40) | 非空 | model、channel、map 等用途 |
| `name` | varchar(120) | 非空 | 后台识别名称 |
| `ciphertext` | bytea | 非空 | AES-256-GCM 加密内容 |
| `nonce` | bytea | 非空 | 加密随机数 |
| `key_version` | integer | 非空 | 主加密密钥版本 |
| `fingerprint` | varchar(32) | 非空 | 用于识别是否替换，不可反推原文 |
| `created_by` | uuid | 外键、非空 | 创建人 |
| `rotated_at` | timestamptz | 可空 | 最近轮换时间 |
| `last_used_at` | timestamptz | 可空 | 最近使用时间 |
| `created_at` | timestamptz | 非空 | 创建时间 |

主加密密钥来自服务器环境，不保存到数据库。数据库泄露时，攻击者不能仅凭 `secret_values` 解密API密钥。

### 6.8 使用哪一个大模型服务（`model_providers`）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid | 主键 | 模型配置编号 |
| `name` | varchar(120) | 非空 | 运营后台显示名称 |
| `provider_type` | varchar(40) | 非空 | 模型适配器类型 |
| `base_url` | text | 非空 | API接口地址 |
| `model_name` | varchar(160) | 非空 | 模型名称 |
| `secret_id` | uuid | 外键、非空 | API密钥引用 |
| `timeout_seconds` | integer | 非空 | 请求超时 |
| `max_output_tokens` | integer | 非空 | 最大输出Token数 |
| `temperature` | numeric(3,2) | 非空 | 输出随机程度 |
| `job_budget` | numeric(12,4) | 可空 | 单任务费用上限 |
| `fallback_provider_id` | uuid | 可空、外键 | 备用模型配置 |
| `is_enabled` | boolean | 非空 | 是否允许调用 |
| `last_test_status` | varchar(20) | 可空 | 最近测试结果 |
| `last_test_at` | timestamptz | 可空 | 最近测试时间 |
| `last_error` | text | 可空 | 最近错误摘要 |
| `created_at` | timestamptz | 非空 | 创建时间 |
| `updated_at` | timestamptz | 非空 | 更新时间 |

### 6.9 抓取和系统运行参数（`system_settings`）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `key` | varchar(120) | 主键 | 例如 `crawler.http_concurrency` |
| `category` | varchar(40) | 非空 | crawler、runtime、map 等分类 |
| `value_json` | jsonb | 非空 | 参数值 |
| `value_type` | varchar(20) | 非空 | integer、boolean、string、object |
| `revision` | integer | 非空 | 每次修改递增 |
| `updated_by` | uuid | 外键、非空 | 修改人 |
| `applied_at` | timestamptz | 可空 | 实际生效时间 |
| `created_at` | timestamptz | 非空 | 创建时间 |
| `updated_at` | timestamptz | 非空 | 更新时间 |

数据库连接密码不进入该表。

### 6.10 数据库连接切换和回滚记录（`runtime_config_revisions`）

该表只保存数据库配置的非敏感摘要和应用结果，完整连接配置保存在服务器外部加密文件。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid | 主键 | 修订编号 |
| `config_type` | varchar(32) | 非空 | 第一版为 database |
| `revision` | integer | 非空、唯一 | 运行配置版本 |
| `status` | varchar(24) | 非空 | pending、testing、applied、failed、rolled_back |
| `host_masked` | varchar(255) | 非空 | 脱敏主机地址 |
| `database_name` | varchar(100) | 非空 | 数据库名称 |
| `username_masked` | varchar(100) | 非空 | 脱敏用户名 |
| `ssl_mode` | varchar(20) | 非空 | SSL模式 |
| `config_checksum` | char(64) | 非空 | 外部配置文件校验值 |
| `test_result` | jsonb | 可空 | 延迟、版本和检查结果 |
| `previous_revision_id` | uuid | 可空、外键 | 上一个可回滚版本 |
| `created_by` | uuid | 外键、非空 | 操作人 |
| `tested_at` | timestamptz | 可空 | 测试时间 |
| `applied_at` | timestamptz | 可空 | 应用时间 |
| `created_at` | timestamptz | 非空 | 创建时间 |

### 6.11 一次完整的自动化运行（`job_runs`）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid | 主键 | 任务编号 |
| `profile_id` | uuid | 外键、非空 | 所属助手 |
| `config_version_id` | uuid | 外键、非空 | 使用的正式配置版本 |
| `trigger_type` | varchar(20) | 非空 | scheduled、manual、publish_run |
| `status` | varchar(24) | 非空 | 当前任务状态 |
| `current_step` | varchar(40) | 可空 | 当前执行阶段 |
| `config_snapshot` | jsonb | 非空 | 启动时完整配置快照 |
| `runtime_revision` | integer | 非空 | 抓取运行参数版本 |
| `idempotency_key` | varchar(160) | 非空、唯一 | 防止重复创建任务 |
| `scheduled_for` | timestamptz | 非空 | 计划时间 |
| `started_at` | timestamptz | 可空 | 实际开始时间 |
| `finished_at` | timestamptz | 可空 | 完成时间 |
| `lease_owner` | varchar(120) | 可空 | 当前领取任务的Worker |
| `lease_expires_at` | timestamptz | 可空 | 任务租约过期时间 |
| `heartbeat_at` | timestamptz | 可空 | Worker最近心跳 |
| `attempt_count` | integer | 非空、默认0 | 整体领取次数 |
| `result_stats` | jsonb | 非空、默认空对象 | 抓取、候选、发布和推送数量 |
| `error_code` | varchar(80) | 可空 | 最终错误代码 |
| `error_message` | text | 可空 | 脱敏错误摘要 |
| `created_at` | timestamptz | 非空 | 创建时间 |
| `updated_at` | timestamptz | 非空 | 更新时间 |

索引：`status, scheduled_for`、`profile_id, created_at desc`、`lease_expires_at`。

### 6.12 一次运行里的每个处理步骤（`job_steps`）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid | 主键 | 步骤编号 |
| `job_id` | uuid | 外键、非空 | 所属任务 |
| `step_name` | varchar(40) | 非空 | discovering、fetching 等 |
| `status` | varchar(20) | 非空 | pending、running、completed、failed |
| `attempt_number` | integer | 非空 | 当前步骤第几次执行 |
| `input_refs` | jsonb | 非空 | 输入记录编号 |
| `output_stats` | jsonb | 非空 | 输出统计 |
| `started_at` | timestamptz | 可空 | 开始时间 |
| `finished_at` | timestamptz | 可空 | 完成时间 |
| `error_code` | varchar(80) | 可空 | 错误代码 |
| `error_message` | text | 可空 | 脱敏错误摘要 |

唯一约束：`job_id, step_name, attempt_number`。

### 6.13 一次具体的搜索请求（`search_tasks`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | uuid | 搜索任务编号 |
| `job_id` | uuid | 所属任务 |
| `source_item_id` | uuid | 配置快照中的来源编号 |
| `city_code` | varchar(32) | 城市标准编号 |
| `logical_query` | jsonb | 城市、主题、日期等结构化条件 |
| `rendered_query` | text | 实际发送给来源的查询内容 |
| `priority` | integer | 执行优先级 |
| `status` | varchar(20) | 执行状态 |
| `candidate_count` | integer | 发现的候选数量 |
| `started_at` | timestamptz | 开始时间 |
| `finished_at` | timestamptz | 完成时间 |
| `error_message` | text | 错误摘要 |

### 6.14 抓取到的网页原文和清洗结果（`raw_documents`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | uuid | 网页记录编号 |
| `job_id` | uuid | 所属任务 |
| `search_task_id` | uuid | 来源搜索任务，可空 |
| `source_item_id` | uuid | 来源配置编号 |
| `url` | text | 实际请求地址 |
| `canonical_url` | text | 页面声明或系统归一化后的标准地址 |
| `http_status` | integer | HTTP响应状态 |
| `content_type` | varchar(120) | 内容类型 |
| `content_hash` | char(64) | 正文哈希，用于避免重复解析 |
| `response_headers` | jsonb | 经过过滤的响应头 |
| `raw_body_gzip` | bytea | 有体积上限的压缩原文 |
| `extracted_text` | text | 清洗后的正文 |
| `structured_data` | jsonb | JSON-LD等结构化数据 |
| `language` | varchar(16) | 页面语言 |
| `parser_version` | varchar(40) | 使用的解析器版本 |
| `fetched_at` | timestamptz | 抓取时间 |
| `error_message` | text | 抓取或解析错误 |

索引：`canonical_url`、`content_hash`、`job_id, fetched_at`。

### 6.15 从网页提取出的候选活动（`event_candidates`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | uuid | 候选活动编号 |
| `job_id` | uuid | 所属任务 |
| `status` | varchar(24) | extracted、merged、verified、rejected |
| `title` | text | 原始优选标题 |
| `normalized_title` | text | 去重用标准标题 |
| `start_at` | timestamptz | 开始时间 |
| `end_at` | timestamptz | 结束时间，可空 |
| `timezone` | varchar(64) | 活动时区 |
| `city_code` | varchar(32) | 城市编号 |
| `venue_name` | text | 场地名称 |
| `venue_address` | text | 详细地址 |
| `latitude` | numeric(10,7) | 纬度 |
| `longitude` | numeric(10,7) | 经度 |
| `organizer_name` | text | 主办方显示名称 |
| `community_name` | text | 所属社区或项目，可空 |
| `normalized_organizer` | text | 去重用主办方名称 |
| `canonical_url` | text | 标准原文地址 |
| `registration_url` | text | 报名地址 |
| `description_text` | text | 合并前事实描述 |
| `agenda_json` | jsonb | 议程结构 |
| `category_labels` | jsonb | 活动分类标签候选及其置信度 |
| `topic_labels` | text[] | 技术主题标签候选 |
| `source_keys` | jsonb | 各来源内部活动编号 |
| `duplicate_group_key` | varchar(160) | 疑似重复分组 |
| `fact_confidence` | numeric(4,3) | 事实可信度 |
| `extracted_data` | jsonb | 其他提取字段 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

### 6.16 一场活动的主记录（`events`）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | uuid | 主键 | 一场逻辑活动的稳定编号 |
| `identity_key` | varchar(180) | 非空、唯一 | 去重后稳定身份键 |
| `canonical_url` | text | 可空、唯一 | 标准原文地址 |
| `current_version_id` | uuid | 可空、外键 | 当前公开版本 |
| `status` | varchar(20) | 非空 | active、cancelled、expired、hidden |
| `first_seen_at` | timestamptz | 非空 | 首次发现时间 |
| `last_seen_at` | timestamptz | 非空 | 最近一次仍存在的时间 |
| `created_at` | timestamptz | 非空 | 创建时间 |
| `updated_at` | timestamptz | 非空 | 更新时间 |

### 6.17 一场活动某一次确认后的内容版本（`event_versions`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | uuid | 活动版本编号 |
| `event_id` | uuid | 稳定活动编号 |
| `job_id` | uuid | 生成该版本的任务 |
| `version_number` | integer | 同一活动递增版本 |
| `content_hash` | char(64) | 内容未变化时避免创建新版本 |
| `title` | text | 活动标题 |
| `start_at`、`end_at` | timestamptz | 开始和结束时间 |
| `timezone` | varchar(64) | 活动时区 |
| `city_code`、`city_name` | varchar | 城市编号和显示名称 |
| `venue_name`、`venue_address` | text | 场地和地址 |
| `latitude`、`longitude` | numeric | 经纬度 |
| `organizer_name` | text | 主办方 |
| `community_name` | text | 所属社区，可空 |
| `event_type` | varchar(64) | 兼容字段，保存主分类编码 |
| `category_labels` | jsonb | 活动分类标签数组，供首页标签、筛选和排序使用 |
| `topic_labels` | text[] | 技术主题标签 |
| `summary` | text | 活动摘要 |
| `calendar_summary` | text | 日历上方未来15天简述使用的短摘要 |
| `why_worth` | jsonb | 为什么值得去的结构化内容 |
| `takeaways` | jsonb | 收获列表 |
| `prerequisites` | jsonb | 提前准备列表 |
| `canonical_url` | text | 标准原文地址 |
| `registration_url` | text | 报名入口 |
| `cost_text` | text | 官方费用说明，可空 |
| `cover_url` | text | 官方有效封面，可空 |
| `commute_status` | varchar(24) | pending、calculating、succeeded、unavailable、failed |
| `commute_origin_name` | text | 本次计算使用的出发点名称 |
| `commute_origin_latitude`、`commute_origin_longitude` | numeric(10,7) | 出发点坐标快照 |
| `commute_origin_config_version_id` | uuid | 计算时使用的配置版本 |
| `commute_provider` | varchar(32) | amap、google_maps等路线服务 |
| `commute_minutes` | integer | 通勤分钟数，可空 |
| `commute_duration_seconds` | integer | 路线服务返回的原始秒数，可空 |
| `commute_distance_meters` | integer | 通勤距离，可空 |
| `commute_mode` | varchar(24) | 出行方式，可空 |
| `commute_route_url` | text | 可选的路线查看地址 |
| `commute_calculated_at` | timestamptz | 最近一次成功或失败计算时间 |
| `commute_error_code` | varchar(80) | 计算失败代码，可空 |
| `quality_score` | numeric(5,2) | 含金量总分 |
| `quality_level` | varchar(16) | high、medium、low |
| `fact_confidence` | numeric(4,3) | 事实可信度 |
| `published_at` | timestamptz | 发布时间 |
| `created_at` | timestamptz | 创建时间 |

唯一约束：`event_id, version_number`。主要索引：`start_at`、`city_code, start_at`、`quality_level, start_at`、`topic_labels` GIN 索引。

`category_labels` 的保存结构固定为数组，每个标签必须能回指配置中的 `event_types.id` 或对应的原文证据：

```json
[
  {
    "code": "industry",
    "name": "业界",
    "kind": "event_type",
    "is_primary": true,
    "confidence": 0.94,
    "evidence_ids": ["e1111111-1111-4111-8111-111111111111"]
  },
  {
    "code": "open_source",
    "name": "开源",
    "kind": "event_type",
    "is_primary": false,
    "confidence": 0.88,
    "evidence_ids": ["e2222222-2222-4222-8222-222222222222"]
  }
]
```

约束：`code` 必须来自已启用的活动类型；`name` 是页面显示文本；`is_primary=true` 的标签最多一个；`confidence` 必须在0到1之间；没有原文证据支持的标签不能进入公开版本。`event_type` 只作为兼容和主分类查询字段，首页展示以 `category_labels` 为准。

`calendar_summary` 不是 `summary` 的截断结果。它由大模型根据已经核验的标题、议程、主办方和地点生成，限制为1至3句、80至220个中文字符，用于日历上方“未来15天活动简述”区域；没有通过证据核验就不能写入公开活动版本。

### 6.18 活动字段对应的网页原文证据（`event_evidence`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | uuid | 证据编号 |
| `event_version_id` | uuid | 关联活动版本 |
| `raw_document_id` | uuid | 关联原始网页 |
| `field_name` | varchar(80) | title、start_at、category_labels、calendar_summary、why_worth 等 |
| `claim_text` | text | 页面中使用的事实或结论 |
| `source_excerpt` | text | 支撑该字段的原文片段 |
| `source_locator` | jsonb | CSS路径、JSON-LD路径或段落位置 |
| `evidence_type` | varchar(20) | extracted、derived、generated |
| `confidence` | numeric(4,3) | 该证据可信度 |
| `is_primary` | boolean | 是否为该字段主要证据 |
| `created_at` | timestamptz | 创建时间 |

索引：`event_version_id, field_name`、`raw_document_id`。

### 6.19 一次大模型调用及其结果（`llm_runs`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | uuid | 调用编号 |
| `job_id` | uuid | 所属任务 |
| `candidate_id` | uuid | 关联候选活动，可空 |
| `purpose` | varchar(40) | summary、classification、discovery 等 |
| `provider_id` | uuid | 模型配置编号 |
| `model_name` | varchar(160) | 实际模型名称 |
| `prompt_version` | varchar(40) | 提示词版本 |
| `input_hash` | char(64) | 输入内容哈希 |
| `input_tokens` | integer | 输入Token数 |
| `output_tokens` | integer | 输出Token数 |
| `latency_ms` | integer | 调用耗时 |
| `estimated_cost` | numeric(12,6) | 估算费用 |
| `status` | varchar(20) | running、succeeded、failed |
| `raw_output` | jsonb | 原始结构化响应 |
| `validated_output` | jsonb | 校验通过后的输出 |
| `error_code` | varchar(80) | 错误代码 |
| `error_message` | text | 脱敏错误摘要 |
| `started_at` | timestamptz | 开始时间 |
| `finished_at` | timestamptz | 完成时间 |

### 6.20 推送到哪里以及推送规则（`notification_channels`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | uuid | 通道编号 |
| `profile_id` | uuid | 所属助手 |
| `name` | varchar(120) | 通道显示名称 |
| `channel_type` | varchar(32) | feishu、serverchan、webhook |
| `endpoint_secret_id` | uuid | 加密推送地址引用 |
| `signing_secret_id` | uuid | 签名密钥或SendKey引用，可空 |
| `delivery_scope` | varchar(24) | all、high_value |
| `is_enabled` | boolean | 是否启用 |
| `last_test_status` | varchar(20) | 最近测试状态 |
| `last_test_at` | timestamptz | 最近测试时间 |
| `last_error` | text | 最近错误摘要 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

### 6.21 每一条消息是否真正送达（`notification_deliveries`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | uuid | 推送记录编号 |
| `job_id` | uuid | 所属任务 |
| `channel_id` | uuid | 目标通道 |
| `batch_key` | varchar(160) | 幂等推送编号，唯一 |
| `status` | varchar(20) | pending、sent、retrying、failed |
| `attempt_count` | integer | 已尝试次数 |
| `payload_hash` | char(64) | 推送内容哈希 |
| `response_status` | integer | 对方HTTP状态 |
| `response_excerpt` | text | 脱敏响应摘要 |
| `next_retry_at` | timestamptz | 下次重试时间 |
| `sent_at` | timestamptz | 成功时间 |
| `error_message` | text | 错误摘要 |
| `created_at` | timestamptz | 创建时间 |
| `updated_at` | timestamptz | 更新时间 |

### 6.22 每个活动来源是否健康（`source_health`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `profile_id` | uuid | 所属助手 |
| `source_item_id` | uuid | 配置中的来源编号 |
| `last_job_id` | uuid | 最近任务 |
| `last_success_at` | timestamptz | 最近成功时间 |
| `consecutive_failures` | integer | 连续失败次数 |
| `average_latency_ms` | integer | 平均响应时间 |
| `last_http_status` | integer | 最近HTTP状态 |
| `parser_status` | varchar(20) | healthy、degraded、broken |
| `last_error` | text | 最近错误摘要 |
| `updated_at` | timestamptz | 更新时间 |

主键使用 `profile_id, source_item_id` 组合键。

### 6.23 谁在什么时候改了什么（`audit_logs`）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | uuid | 审计编号 |
| `actor_user_id` | uuid | 操作人 |
| `action` | varchar(80) | publish_config、replace_secret 等 |
| `resource_type` | varchar(60) | config、channel、runtime 等 |
| `resource_id` | uuid | 被操作记录，可空 |
| `before_json` | jsonb | 修改前脱敏摘要 |
| `after_json` | jsonb | 修改后脱敏摘要 |
| `ip_address` | inet | 操作IP |
| `request_id` | varchar(80) | 关联请求编号 |
| `created_at` | timestamptz | 操作时间 |

审计日志只记录密钥“已设置、已替换、已清除”，不能记录密钥值。

### 6.24 这些数据之间怎么关联

```text
ops_users
  ├─ ops_sessions
  ├─ config_versions.created_by / published_by
  └─ audit_logs

assistant_profiles
  ├─ config_versions
  ├─ job_runs
  ├─ notification_channels
  └─ source_health

job_runs
  ├─ job_steps
  ├─ search_tasks
  ├─ raw_documents
  ├─ event_candidates
  ├─ llm_runs
  └─ notification_deliveries

events
  └─ event_versions
       └─ event_evidence
            └─ raw_documents
```

删除规则：

- 正式配置、任务、活动版本、证据、模型调用和审计日志不做物理级联删除。
- 运营页面的“删除来源”表示在新配置中删除该项，不删除历史任务快照。
- 删除推送通道前检查是否存在发送中的记录；历史推送记录保留通道名称快照。
- 活动下架通过状态字段实现，不删除历史版本和证据。

### 6.25 哪些写入必须一次完成

| 操作 | 必须在同一数据库事务中完成的内容 |
| --- | --- |
| 发布配置 | 写入新版本、更新助手正式版本指针、写审计日志 |
| 创建任务 | 写任务、配置快照和幂等键 |
| 发布活动 | 创建或更新稳定活动、写活动版本、写证据、更新当前版本指针 |
| 保存模型密钥 | 写加密密钥、更新模型引用、写审计日志 |
| 创建推送 | 写推送记录和唯一批次编号 |

外部网络调用不能放在长数据库事务中。正确顺序是先保存待执行状态，提交事务，再调用外部服务，最后用短事务更新结果。

## 七、接口设计

### 7.1 公开活动接口

| 请求方式和地址 | 中文用途 |
| --- | --- |
| `GET /api/public/events` | 按日期、城市、主题、分类标签和含金量查询活动详情 |
| `GET /api/public/events/{eventId}` | 获取活动详情和标准原文链接 |
| `GET /api/public/filters` | 获取当前活动页可用的动态筛选项 |
| `GET /api/public/calendar` | 获取指定日期范围内的日历格和日历活动摘要 |
| `GET /api/public/calendar/brief` | 获取放在日历上方的未来15天活动简述 |

公开接口只返回已经发布的活动版本，不返回原始网页全文、运营配置、密钥状态、内部评分明细和模型原始输出。所有接口的活动对象都必须包含主办方、地点、城市、分类标签和通勤状态；详情接口再按展示配置补充收获、提前准备和其他可选字段。

#### 7.1.1 日历上方的未来15天活动简述

首页加载时先调用 `GET /api/public/calendar/brief?days=15`，返回结果渲染到日历组件上方。它不是活动详情列表的替代品，而是帮助用户在不逐张打开活动的情况下快速了解未来两周值得关注的活动。

请求参数：

| 参数 | 是否必填 | 规则 |
| --- | --- | --- |
| `days` | 否 | 只能是15、30或60；默认15；不能超过后台已发布的 `schedule.coverage_days` |
| `city` | 否 | 城市编号，可重复传入 |
| `category` | 否 | 活动分类编码，例如 `industry`、`academic`、`open_source` |
| `topic` | 否 | 技术主题编码或关键词 |
| `limit` | 否 | 默认取 `output.calendar_brief_limit`，不能超过 `target_count` |

返回结构：

```json
{
  "title": "未来15天活动简述",
  "range": {
    "days": 15,
    "start_date": "2026-09-04",
    "end_date": "2026-09-18",
    "timezone": "Asia/Shanghai"
  },
  "total_count": 8,
  "items": [
    {
      "event_id": "e1111111-1111-4111-8111-111111111111",
      "date": "2026-09-10",
      "date_label": "9月10日 周四",
      "title": "Agent工程实践与工具调用分享",
      "city_name": "深圳",
      "venue_name": "深圳大学科技楼",
      "organizer_name": "深圳开发者社区",
      "community_name": "Agent Builders Community",
      "category_labels": [
        {
          "code": "industry",
          "name": "业界",
          "is_primary": true
        },
        {
          "code": "open_source",
          "name": "开源",
          "is_primary": false
        }
      ],
      "topic_labels": ["Agent与智能体工程", "MCP"],
      "quality_level": "high",
      "calendar_summary": "围绕Agent工具调用、MCP接入和工程落地展开，适合希望把智能体从演示推进到可运行系统的开发者。",
      "commute": {
        "status": "succeeded",
        "minutes": 42,
        "distance_meters": 18500,
        "mode": "transit",
        "provider": "amap"
      },
      "canonical_url": "https://example.com/events/agent-practice",
      "registration_url": "https://example.com/events/agent-practice/register"
    }
  ]
}
```

实现规则：

- `items` 按含金量降序、开始时间升序排列；相同分数再按活动编号稳定排序。
- `calendar_summary`必须来自已核验的活动版本，不能在公开接口请求时临时调用大模型。
- 简述中允许出现分析性内容，但主办方、城市、地点、日期、分类和主题必须使用数据库事实字段。
- 没有通勤结果时仍返回 `commute.status`，前端显示“暂未计算”或“路线不可用”，不返回伪造的分钟数。
- 没有图片不影响该接口，接口不返回空的图片占位字段。

如果后台配置的 `schedule.coverage_days` 是15，接口只允许请求15天；如果配置为30，允许请求15天或30天；如果配置为60，允许请求15天、30天或60天。请求超过已发布覆盖范围时返回 `CALENDAR_RANGE_NOT_AVAILABLE`，不偷偷返回部分结果。

#### 7.1.2 日历格接口

`GET /api/public/calendar?days=15`服务日历本体，返回从周一开始的日期数组。每个日期格只返回日历所需的紧凑信息，不返回完整详情正文：

```json
{
  "week_starts_on": "monday",
  "range_days": 15,
  "timezone": "Asia/Shanghai",
  "days": [
    {
      "date": "2026-09-10",
      "weekday": "周四",
      "events": [
        {
          "event_id": "e1111111-1111-4111-8111-111111111111",
          "title": "Agent工程实践与工具调用分享",
          "city_name": "深圳",
          "start_time": "19:00",
          "category_labels": [
            {"code": "industry", "name": "业界", "is_primary": true},
            {"code": "open_source", "name": "开源", "is_primary": false}
          ],
          "quality_level": "high",
          "commute_minutes": 42,
          "detail_url": "/events/e1111111-1111-4111-8111-111111111111"
        }
      ]
    }
  ]
}
```

日历组件上方显示 `calendar/brief` 的简述；日历格显示 `calendar` 的日期、城市、标题、分类标签和通勤分钟数；点击日历活动直接跳转活动详情页，不增加多余的中间按钮。下方详情列表继续调用 `GET /api/public/events`，因此“日历概览 + 活动简述 + 下方活动详情”使用同一批已发布活动数据，不会出现三个区域内容不一致。

#### 7.1.3 活动详情返回字段

`GET /api/public/events/{eventId}`至少返回：

| 字段 | 返回内容 |
| --- | --- |
| `event_id`、`title` | 稳定活动编号和标题 |
| `start_at`、`end_at`、`timezone` | 活动时间 |
| `city_name`、`venue_name`、`venue_address` | 城市和具体地点 |
| `organizer_name`、`community_name` | 主办方和所属社区 |
| `category_labels`、`topic_labels` | 分类标签和技术主题标签 |
| `summary`、`calendar_summary` | 详情摘要和日历简述 |
| `why_worth` | 为什么值得去 |
| `takeaways` | 参加后可以获得什么 |
| `prerequisites` | 提前准备目录 |
| `commute` | 通勤状态、时长、距离、方式和地图服务 |
| `canonical_url`、`registration_url` | 原文和报名链接 |

分类标签是右侧标签的唯一数据来源，不再从标题文字或前端硬编码推断。通勤对象的 `status`、`minutes`、`distance_meters`、`mode`、`provider` 和 `calculated_at` 与 `event_versions` 中的同名字段保持一致。

#### 7.1.4 活动页筛选接口返回值

`GET /api/public/filters` 返回活动页的动态筛选项，分类标签直接来自已发布活动版本和已启用的运营配置：

```json
{
  "date_ranges": [15],
  "cities": [
    {"code": "shenzhen", "name": "深圳", "event_count": 6}
  ],
  "categories": [
    {"code": "industry", "name": "业界", "event_count": 5},
    {"code": "academic", "name": "学术", "event_count": 2},
    {"code": "open_source", "name": "开源", "event_count": 4}
  ],
  "topics": [
    {"name": "Agent与智能体工程", "event_count": 5},
    {"name": "大模型应用与RAG", "event_count": 4}
  ],
  "quality_levels": ["high", "medium"]
}
```

`date_ranges` 由当前配置的 `coverage_days` 截断；`categories` 的名称、编码和数量不能由前端写死。分类筛选条件传入 `calendar/brief`、`calendar` 和 `events` 时使用同一套编码，避免日历和下方详情筛选出不同结果。

### 7.2 运营登录接口

| 请求方式和地址 | 中文用途 |
| --- | --- |
| `POST /api/ops/auth/login` | 校验账号密码并建立安全会话 |
| `POST /api/ops/auth/logout` | 撤销当前会话 |
| `GET /api/ops/auth/me` | 获取当前运营用户信息 |
| `POST /api/ops/auth/change-password` | 修改当前用户密码并撤销其他会话 |

登录成功后使用 `HttpOnly`、`Secure`、`SameSite=Lax` Cookie 保存会话，浏览器JavaScript不能读取会话令牌。

### 7.3 运营配置接口

| 请求方式和地址 | 中文用途 |
| --- | --- |
| `GET /api/ops/profiles/{id}/config` | 获取当前正式配置、草稿和版本号 |
| `PATCH /api/ops/profiles/{id}/config` | 保存草稿字段或配置卡片 |
| `POST /api/ops/profiles/{id}/validate` | 校验完整草稿但不发布 |
| `POST /api/ops/profiles/{id}/publish` | 创建新的正式配置版本 |
| `POST /api/ops/profiles/{id}/publish-and-run` | 发布并立即创建任务 |
| `GET /api/ops/profiles/{id}/versions` | 查看历史版本 |
| `POST /api/ops/profiles/{id}/versions/{versionId}/restore` | 从历史版本创建新草稿 |
| `GET /api/ops/profiles/{id}/preview` | 使用草稿展示配置生成预览数据 |

`PATCH` 请求必须携带草稿版本号。版本不一致时返回 HTTP 409，前端显示冲突而不是覆盖。

### 7.4 任务接口

| 请求方式和地址 | 中文用途 |
| --- | --- |
| `POST /api/ops/profiles/{id}/runs` | 使用当前正式配置立即创建任务 |
| `GET /api/ops/jobs` | 分页查询任务历史 |
| `GET /api/ops/jobs/{jobId}` | 查询任务步骤、进度和错误 |
| `POST /api/ops/jobs/{jobId}/cancel` | 取消尚未发布的任务 |
| `POST /api/ops/jobs/{jobId}/retry` | 从允许重试的失败步骤重新执行 |
| `GET /api/ops/jobs/{jobId}/search-tasks` | 查看该任务实际生成的搜索条件 |

立即运行请求使用客户端生成的幂等键。用户连续点击按钮不会创建多个相同任务。

### 7.5 推送通道接口

| 请求方式和地址 | 中文用途 |
| --- | --- |
| `POST /api/ops/channels` | 新增推送通道 |
| `PATCH /api/ops/channels/{id}` | 修改名称、类型、范围和启用状态 |
| `POST /api/ops/channels/{id}/replace-secret` | 替换地址或签名密钥 |
| `POST /api/ops/channels/{id}/clear-secret` | 二次确认后清除密钥 |
| `POST /api/ops/channels/{id}/test` | 发送测试消息 |
| `DELETE /api/ops/channels/{id}` | 删除推送通道 |

### 7.6 大模型和抓取参数接口

| 请求方式和地址 | 中文用途 |
| --- | --- |
| `GET /api/ops/model-providers` | 获取脱敏后的模型配置列表 |
| `POST /api/ops/model-providers` | 新增模型配置 |
| `PATCH /api/ops/model-providers/{id}` | 修改非密钥参数 |
| `POST /api/ops/model-providers/{id}/replace-key` | 写入或替换API密钥 |
| `POST /api/ops/model-providers/{id}/test` | 测试连接和结构化输出 |
| `GET /api/ops/system-settings/crawler` | 获取抓取参数和修订版本 |
| `PATCH /api/ops/system-settings/crawler` | 校验并保存抓取参数 |

### 7.7 数据库运行配置接口

| 请求方式和地址 | 中文用途 |
| --- | --- |
| `GET /api/ops/runtime/database` | 获取脱敏后的当前和待应用状态 |
| `POST /api/ops/runtime/database/test` | 测试候选数据库连接 |
| `POST /api/ops/runtime/database/stage` | 保存待应用配置 |
| `POST /api/ops/runtime/database/apply` | 调用本机控制服务应用并重启 |
| `POST /api/ops/runtime/database/discard` | 撤销待应用配置 |
| `POST /api/ops/runtime/database/rollback` | 恢复上一版成功配置 |

这些接口不返回数据库密码。应用和回滚需要重新输入当前运营密码或一次性确认口令。

### 7.8 状态与诊断接口

| 请求方式和地址 | 中文用途 |
| --- | --- |
| `GET /api/ops/health/summary` | 获取数据库、模型、地图、来源和推送状态 |
| `POST /api/ops/preflight` | 执行完整运行预检 |
| `GET /api/ops/sources/health` | 获取每个来源的成功率和解析状态 |
| `GET /api/ops/audit-logs` | 查询发布和敏感操作记录 |

`GET` 表示读取数据，`POST` 表示创建或执行操作，`PATCH` 表示局部修改，`DELETE` 表示删除。

### 7.9 接口错误格式

所有接口使用统一错误结构：

```json
{
  "code": "CONFIG_VERSION_CONFLICT",
  "message": "正式配置已经被其他会话更新",
  "field_errors": [
    {
      "path": "sources.4.url",
      "message": "来源地址不可访问"
    }
  ],
  "request_id": "请求追踪编号"
}
```

前端根据 `path` 把错误显示到原型当前卡片内。页面顶部只显示简短总览，不用一条通用 Toast 代替具体错误。

## 八、英文术语说明

| 英文 | 中文解释 |
| --- | --- |
| API | 应用程序接口，前端和后端通过它交换数据 |
| Agent | 可以选择搜索、打开网页等工具并围绕目标行动的模型执行单元 |
| LLM | Large Language Model，大语言模型 |
| Prompt | 提示词，发给大模型的任务说明、约束和输出格式 |
| SDK | Software Development Kit，服务厂商提供的调用代码包 |
| Worker | 后台任务执行进程，负责抓取、总结和推送 |
| Scheduler | 定时调度器，负责按计划创建后台任务 |
| Webhook | 系统向指定网络地址主动发送消息的机制 |
| SendKey | Server酱用来识别消息接收账户的发送密钥 |
| Draft | 草稿，尚未影响正式任务的配置 |
| Published | 已发布，下一次任务正式使用的配置 |
| Snapshot | 快照，某次任务使用的完整、不可变配置副本 |
| Canonical URL | 标准原文地址，一场活动最正式或最可信的页面 |
| Evidence | 证据，支撑某个字段或结论的网页原文 |
| Confidence | 可信度，表示系统对判断可靠程度的数值 |
| Candidate | 候选活动，尚未完成核验和正式发布 |
| Normalize | 标准化，把不同网页的数据转换成统一格式 |
| Deduplicate | 去重，判断多个网页是否描述同一场活动 |
| Merge | 合并，把同一活动的多个来源和证据整理成一条记录 |
| Idempotency | 幂等，同一个操作重试多次也只产生一次最终结果 |
| Backoff | 退避重试，失败后逐渐延长等待时间 |
| UUID | 通用唯一编号，用来稳定识别配置项和数据记录 |
| UTC | 世界协调时间，UTC+8表示比世界协调时间快8小时 |
| OpenAPI | 接口说明标准，FastAPI自动生成，前端据此生成类型 |
| ORM | 对象关系映射，把Python对象和数据库表对应起来 |
| JSONB | PostgreSQL可检索的JSON字段类型 |
| GIN Index | PostgreSQL倒排索引，适合数组和JSONB查询 |
| CSRF | 跨站请求伪造，攻击者诱导浏览器提交非本人操作 |
| Argon2id | 专门用于安全保存密码哈希的算法 |
| AES-256-GCM | 带完整性校验的对称加密算法，用于加密密钥 |
| Unix Socket | 同一台服务器上进程之间通信的本地套接字文件 |
| Runtime Controller | 本机运行控制服务，负责安全应用服务器启动配置 |
| SSL | 加密网络连接，数据库连接也可以启用 |
| Connection Pool | 数据库连接池，复用已有连接，避免每次重新建立 |
| Token | 大模型处理文本时使用的计量单位，不等同于汉字数量 |
| HttpOnly Cookie | 浏览器脚本无法读取的Cookie，用于降低会话被窃取风险 |
| Idempotency Key | 幂等键，确保重复请求不会重复创建任务或推送 |

## 九、验收标准

### 9.1 运营配置

- 第一版存在独立 `/ops/` 运营后台，并且必须登录才能访问。
- 运营后台沿用当前原型UI，不替换成通用后台模板。
- 原型五个栏目全部通过后端接口真实保存，不增加第六个左侧导航。
- 搜寻范围保留检索区域、目标数量、目标人群、公开来源和固定核验条件。
- 时间与地点保留频率、运行时间、覆盖天数、交通出发点和城市收录门槛。
- 主题偏好保留优先主题、固定技术要求、降权规则、活动类型、两级排序和输出取舍。
- 展示字段保留4个固定字段、11个可选字段、摘要详细度、推送样式、时间格式、时区和隐藏未知值。
- 推送与自动化保留推送通道、自动化状态、运行预检和重新生成能力。
- 目标人群、来源、城市、主题、活动类型和通道支持新增、编辑、停用和删除。
- 发布配置后生成不可修改的新版本。
- 运行中的任务不受新发布配置影响。
- 输入错误时在当前卡片内提示，不打开抽屉或弹窗。
- 可以配置、测试、停用、清除和删除多个飞书或 Server酱通道。
- 同一视觉体系下增加大模型服务、网页抓取参数和数据库连接区块。
- 大模型密钥和数据库密码保存后不能回显。
- 数据库连接支持测试、保存待应用、应用、健康检查和失败回滚。

### 9.2 UI不变验收

- 左侧栏目名称、顺序、数量和主要点击区域与原型一致。
- 顶部品牌、页面切换、预览和发布操作位置与原型一致。
- 配置卡片正常状态和行内编辑状态与原型交互一致。
- 新技术字段只复用已有控件和样式，不创建抽屉、传统表格或全屏表单。
- 桌面端使用相同内容宽度和对齐基线；移动端按已有响应式规则收缩。
- 使用桌面和移动端截图进行视觉回归对比，确认不是借实现之名重新设计页面。

### 9.3 搜索与处理

- 固定来源和智能探索都读取同一份任务配置快照。
- 修改城市、主题、来源和覆盖天数后，下一次任务自动生效，不需要修改代码。
- 多来源发现同一活动时只发布一条活动，同时保留所有有效证据。
- 固定事实不能只来自大模型生成文本。
- 活动分类标签必须来自已启用的 `event_types`，并且至少有一条网页证据；前端不允许根据标题自行猜分类。
- 活动发布前必须完成通勤计算或明确记录 `unavailable` / `failed` 状态，不能用固定值填充通勤分钟数。

### 9.4 活动页

- 日历从周一开始，并在活动中标明城市。
- 日历上方显示未来15天活动简述，简述与下方详情使用同一活动版本。
- 日历和下方详情列表宽度一致。
- 根据配置提供15天、30天和60天范围，但不超过实际搜索范围。
- 日历活动对象包含分类标签、标签主次关系和通勤状态；分类标签可以作为筛选条件。
- 通勤计算成功时展示分钟数、出行方式和距离；计算失败时展示明确状态，不显示虚构时间。
- 高含金量活动具有明确视觉重点，但不增加大量边框和卡片。
- 缺少图片或可选字段时不留下空白区域。
- 桌面端和移动端没有内容裁切、重叠和文字溢出。

### 9.5 技术配置与运行

- 普通网页并发、浏览器并发、超时和重试参数由后台真实控制 Worker。
- 每次大模型调用可以追踪到模型配置、提示词版本、耗时、Token和费用。
- 技术参数修改具有修订号，任务记录实际使用的参数版本。
- Runtime Controller 不监听公网端口，数据库配置文件权限正确。
- 数据库配置应用失败时自动恢复上一版可用配置。
- API、Worker和Scheduler重启后可以恢复未完成任务，不丢失状态。

### 9.6 稳定性与安全

- 重试失败步骤不会重复创建活动或重复发送消息。
- 单个来源或推送通道失败不影响其他成功结果。
- 密钥不会出现在接口响应、日志、网页源码和任务配置快照中。
