# AlloyResearch 非 Web 端与平台瘦身综合评估

> 日期：2026-10-25
> 方法：3 路只读代码/文档审计 + 主会话生产容器与 cron 只读核验
> 口径：用户补充的“荣誉”按“冗余”理解；“已实现”不等于已构建、已发布或有人使用

## 一、结论先行

**需要瘦身，但不应该把 Web 以外的服务一刀切废弃。**

建议采用“**Web 全功能主端 + 核心后台数据链路 + 可选 macOS companion**”的结构，优先退出重复原型和无消费者的平行链路，而不是按页面、router 或脚本数量砍业务。

| 对象 | 建议 | 核心理由 |
|---|---|---|
| Web + FastAPI + PostgreSQL + Redis + Nginx | 必须保留 | 在线产品与主数据链路 |
| APScheduler + 两个 Celery worker | 必须保留，按任务优化 | Web 的行情、指标、评分、公告等上游 |
| `native/ADResearch` macOS | 收窄为内部阅读/桌面效率 companion | 有真实试用证据和菜单栏/⌘K/深链价值，但不是 Web 全功能替代 |
| `native/ADResearch` iOS | 实验状态，冻结对外承诺 | 共享代码但无真机、发布、持续使用证据 |
| 旧 `ios/ADResearch` | 当前认证兼容收尾后优先归档 | 只有登录脚手架，与主 native 完全重复 |
| 独立 `research/` 五进程编排器 | 优先归档 | 文件型原型，非 Web 依赖，调度实现还有重复拉起问题 |
| `agent/` 独立采集 | 按源合并，不直接全停 | 生产 cron 正在运行；有重复源，也有抗 WAF 和独有覆盖 |
| overnight research | 只保留一套、按需运行 | 不是 Web 必需；有独立报告价值，也有独立 LLM 治理成本 |
| wewe-rss | 按公众号功能保留 | 可选采集通道，不是全站核心 |
| scripts/reports | 分类整理，不能整体删除 | 混有部署、备份、恢复等关键工具和一次性历史脚本 |
| 真实交易 | 做明确产品去留决策 | 高安全、高测试成本；不是重复功能，不能为瘦身删风控 |

**如果目标是最大限度降低客户端维护成本，且确认 macOS 也不再持续使用，可以进一步转为 Web-only 客户端。当前证据不足以把“无遥测”直接等同于“无用户”。**

## 二、实际有哪些非 Web 组成部分

### 2.1 生产在线与数据链路

2026-10-25 主会话通过 ECS 只读核验，实际常驻容器为：

- `alloyresearch-nginx`
- `alloyresearch-backend`
- `alloyresearch-celery-worker-indicator`
- `alloyresearch-celery-worker-cninfo`
- `alloyresearch-postgres`
- `alloyresearch-redis`
- `alloyresearch-wewe-rss`

独立采集 worker 由 `/etc/cron.d/ad-research-orchestrate` 每小时触发。当前容器清单中没有独立 `research` 五进程或 Hermes 常驻容器。

拓扑：

```text
Browser / native clients
        ↓ HTTPS
Nginx → FastAPI → PostgreSQL / Redis
                    ↓
       APScheduler → Celery indicator / cninfo+industry
                    ↓
              Web 数据与报告

宿主机 cron → agent 独立采集 → JSON / 静态报告 + 失败告警
手工按需 → overnight research → SQLite / Markdown / HTML
```

核心证据：

- 生产编排：`deploy/aliyun-ecs/docker-compose.yml`
- FastAPI/router/scheduler 生命周期：`app/main.py`
- Celery 队列：`app/core/celery_app.py`
- 调度任务：`app/core/scheduler.py`
- agent cron 与编排：`agent/scripts/setup_cron.sh`、`agent/scripts/orchestrate_v2.py`

**这些后台服务不是“Web 之外的附属品”。停掉 scheduler 或 Celery，API 可能仍在线，但页面数据会逐渐陈旧。**

### 2.2 原生客户端实际有两套 Swift 实现

#### A. `native/ADResearch`：现行共享应用

- SwiftUI 单 target，macOS 14+ / iOS 17+。
- 约 71 个应用 Swift 文件、12,284 物理行，14 个顶层分区、42 个 REST endpoint accessor。
- 有 macOS 三栏、菜单栏、⌘K、深链、本地提醒和 iOS Tab 外壳。
- 功能覆盖资讯、研报、标的、宏观、板块、情绪、资金流、评分、自选/池、学习等阅读型路径。
- 不覆盖 Web 的完整量化、交易、公告报告、AI Chat 和管理运维。
- 无第三方依赖是优点；无 XCTest/原生 CI、手工 Codable 契约和自定义 CLT 打包是主要维护风险。

功能与架构见 `native/ADResearch/README.md`、`App/AppState.swift`、`Core/Networking/Endpoints.swift`。

#### B. 旧 `ios/ADResearch`：登录脚手架

- 无 Xcode 工程，登录后仍是 `Text("Authenticated")` 占位页。
- 独立维护另一套认证、网络和 DTO；与主 native 不联动。
- 主 native README 已明确它是更早的未完工尝试：`native/ADResearch/README.md:159-162`。

**旧目录是最明确的目录级退役候选。**当前首登改密任务正在同时补两套客户端的兼容，目的是避免后端上线即锁死旧端，不代表应继续长期投资两套实现。

### 2.3 旁路采集与研究

- `agent/`：独立镜像、cron、网络、凭据、JSON 产物和 watchdog；与主 scheduler 有部分同源重复。
- `research/`：五进程文件型编排器，不进入生产镜像，未找到 Web 主链路调用。
- overnight v1/v2：另一套手动长任务研究系统，产出独立报告，不等于 Web AI note/digest/券商研报。
- Hermes：文档中的手工 agent 沙箱，不是在线服务依赖；当前生产容器列表未见其运行。

## 三、功能完备度与复杂度评价

### 3.1 Web 主平台

静态盘点约为 57 个页面 TSX、45 个 v1 router 文件、100 个受 Git 跟踪的 scripts 文件。范围确实膨胀，但路由核对没有发现高置信度的大批整页重复。

**问题更多是范围治理和平行实现，而不是“页面多所以都应删”。**

核心价值闭环应保留：

```text
行情 → 指标 → 评分 → 筛选 → 标的池 → 策略/回测/信号 → 报告
```

资讯、Daily Digest、AI ResearchNote、券商研报、CNInfo、SEC 各有独立数据和工作流，不应因名称相近而合并。

### 3.2 native macOS/iOS

macOS 源码广度较高，但仍是内部阅读型 companion，不是公开发行产品：

- 有所有者实际试用和 DMG 构建记录。
- 没有外部下载、活跃用户、TestFlight/App Store 或持续使用证据。
- 无自动化测试 target 和原生 CI；历史多为 `swiftc -parse`，不等于完整编译和真机验收。
- 手工 DTO 已发生过契约漂移导致研报解码失败；本次 `must_change_password` 再次证明三端同步成本。

**建议保留独有价值，不追求 Web 全 parity。**优先晨读、资讯、宏观、标的、菜单栏和桌面效率路径。

### 3.3 agent / research / overnight

- agent 工程化程度较高，有 cron、状态报告、失败告警和受控镜像，但又形成第二套采集运维面。
- `research/orchestrator.py` 声明 1800/3600/7200 秒间隔，却丢弃 interval；子进程退出后每 5 分钟被重新拉起，若常驻运行，实际采集节奏可能与设计不符。
- overnight v2 比旧编排器完整，但独立 LLM fallback、密钥、成本和报告治理仍与主平台分叉。

## 四、优先瘦身清单

### P0：先做无业务下线的风险止损

#### P0-1. 将 demo/synthetic 数据移出标准初始化

`scripts/init_demo_data.py` 生成随机价格、RSI、收益率、夏普等指标，README/AGENTS 仍把它列为“首次数据”步骤。`seed_all_demo_data.py` 还会生成随机 NAV、交易和共享池。

建议：

- 真实初始化文档改为真实数据源 ETL。
- demo 仅在显式 demo 模式和独立数据库运行。
- 先盘点现有 `is_synthetic`、demo 来源及派生评分；不得按日期批量删除，既有共享池和报告单独审查。

收益是降低数据可信度和排障风险，不是少几个文件。

#### P0-2. 隔离危险一次性写库脚本和硬编码凭据脚本

仓库仍有绕 Alembic 的手工 schema 修复、模块加载即写库的脚本，以及包含硬编码登录凭据、会调用真实刷新端点的手工测试脚本，例如 `scripts/test_refresh.py`。

建议：

- 不在报告或文档复制凭据；若曾真实有效，先轮换。
- 凭据改环境变量，手工测试移出常规脚本入口。
- 一次性写库脚本归档前核对备份、影响行、Alembic 状态和回滚方案。
- 保留仍被 runbook 引用的监控、备份和恢复工具。

#### P0-3. 暂停新增平行实现

在所有权收敛前，不再新增第三套客户端、第二套同级搜索/研究管线或旁路部署入口。新增功能必须先明确真实消费者、唯一数据/调度所有者、契约事实源、运行成本和退出条件。

### P1：生产核实后做结构收敛

#### P1-1. 客户端只保留一套 Swift 业务实现

1. 当前密码兼容收尾并验证。
2. 旧 `ios/ADResearch` 标记 legacy、停止入口和文档引导。
3. 确认无独立消费者后归档目录；Git 历史本身保留。
4. native 只聚焦 macOS companion；iOS 在真机验证前保持实验状态。
5. 逐步用后端 OpenAPI 做 DTO 生成或契约 smoke tests，优先登录、refresh rotation、强制改密和研报解码。

#### P1-2. agent 按源确定唯一所有者

CLS 已确认与主平台使用相同 endpoint 和参数，属于真实双采集；agent 的多 TLS profile 抗 WAF 能力又有价值。

建议把 agent 的获取能力变成主 crawler fallback 或统一 normalizer，而不是简单删掉。Fed/ECB 只合并精确重叠 feed，speeches/calendar/BIS/IMF 等独有覆盖单独评估。

生产已确认 agent cron 正在运行，因此下线前必须：

- 盘点 JSON、静态报告和仓库外消费者；
- 先迁移独有价值与告警；
- 停 cron 和对应 status 监控；
- 保留快照及回滚路径。

#### P1-3. 归档旧研究入口，overnight 只留一套

`research/` 五进程不是 Web 必需，且当前生产未见常驻容器，可优先做代码和文档归档评估。overnight 若报告仍有人读，保留 v2 按需运行，并统一主平台 LLM 成本治理；否则不安排常驻或周期运行。

不要误删 Web 主 app 内的 AI note/chat/digest/券商研报，它们不依赖上述旁路编排器。

#### P1-4. 资讯链路先去重和互斥，再谈删任务

- 入库只有 `(source, source_id)` 精确去重；已有 Simhash/`duplicate_of` 能力主要仍靠手工脚本。
- 翻译选择集未排除 `duplicate_of`。
- 即时正文抓取和 drain 都选 `full_content IS NULL`，最后 `force=True`，缺文章级 lease，可能重复抓取和覆盖。

建议先 dry-run 评估近似去重误杀率，再让高成本下游过滤重复文章；正文/翻译增加原子 claim/lease。

**不要删除 ingest+drain 或 trafilatura→Jina→LLM 降级链，它们分别承担低延迟、自愈和可用性。应补协调，不是删层。**

#### P1-5. 资讯源改为分级生命周期

从“源数量目标”转为：核心实时 / 低频价值 / 观察 / 退役。用当前生产数据评估增量、重复率、正文成功率、下游阅读和 LLM 成本，先降频再停调度，原始文章档案保留。

#### P1-6. 真实交易做明确产品决策

若平台核心是研究和模拟验证，可将真实交易降为可选模块、撤出默认菜单并关闭真实开关；若属于核心，则补齐风控配置到执行闭环、跨进程熔断和测试。任何情况下先确认真实账户、持仓、订单和 key，导出审计数据，不能为瘦身删除安全逻辑。

### P2：渐进降低认知成本

- 清理未接线 service、 deprecated wrapper、旧前端 API/hooks；先查脚本、测试和仓库外调用。
- 抽取 StrategyList/StrategyLibrary 的共享创建表单和参数映射，不合并两个不同职责页面。
- 将标准 DataFrame ETL 与自定义多阶段 Job 拆成窄接口，消除空 provider 和 `NotImplementedError` stub。
- Digest 通知伴随记录与组合报告列表分流，避免 `file_path=None` 和状态语义进入通用 ReportBrowser。
- 归档固定日期补数脚本、`redeploy2.sh` 等旁路入口和陈旧 pnpm lock；先核对 cron、alias 和 runbook。
- 全局搜索短期收窄为“页面导航”，或复用现有 instrument/news API；不要保留永久空 mock 造成已支持搜索的错觉。
- 核查 retail hot-symbols zset 是否真无消费者，再停调度观察；不能凭仓内无引用直接删。

## 五、不建议动的部分

- 不批量删除 Web 页面/router；名称相近不代表职责相同。
- 不合并 Favorites、Pool、Portfolio，三者分别是轻量关注、目标组合和实际持仓。
- 不把 Celery、scheduler、Redis 当成可随意关掉的附属服务。
- 不合并模拟交易与真实交易账务模型。
- 不删多 provider fallback、正文降级链、调度锁和备份/证书/site watchdog。
- 不批量删除 scripts、测试 mock、历史 runbook 或报告镜像；应分类归档。
- 不把“仓内无引用”直接等同于“生产零使用”，外部 notebook、Redis 消费者和手工流程可能不可见。

## 六、推荐执行顺序

### 阶段 A：无业务下线止损

- 修正 demo 初始化引导，隔离危险脚本和凭据。
- 标记旧 iOS、旧 research 入口和旁路部署脚本为 legacy。
- 建立功能/运行时清单：消费者、产物、成本、所有者、回滚方式。

### 阶段 B：先兼容，再收敛客户端

- 完成本次 Web、旧 iOS、native 的强制改密兼容。
- 做一次真实 macOS/iOS `xcodebuild` 和关键契约测试。
- 归档旧 iOS；根据实际使用决定 native macOS 保留为 companion 还是 Web-only。

### 阶段 C：strangler 方式合并平行链路

1. 新主链路功能对等。
2. 只读双跑或结果对比。
3. 迁移消费者和文档。
4. 停旧调度/入口。
5. 保留快照与回滚。
6. 一个完整业务周期无回归后删代码。

### 阶段 D：高成本可选模块决策

按四象限处理：高价值高复杂→保留并简化；低价值高复杂→优先退役；价值不确定→先停菜单/调度或降频；低价值低复杂→随维护清理。

## 七、最终建议

**推荐方案：Web 主端 + 核心后台 + 可选 macOS companion，退役旧 iOS 和旧 research 原型，agent 按源合并，overnight 按需单版本。**

不建议现在做的事：

- 为“只留 Web”而删除 scheduler/Celery/agent 的全部代码；
- 继续给两套 iOS 同时加功能；
- 追求 native 与 Web 全功能 parity；
- 在没有消费者和回滚证据时硬删数据、表或采集源。

最终退役门槛统一为：

```text
无消费者或替代链路已对等
+ 数据已导出
+ 依赖已盘点
+ 可回滚
+ 观察期无回归
```

缺少任何一项，都优先“停用/归档”，不要直接硬删除。

## 八、证据边界

- 本次生产核验只读查看了当前 `docker ps` 和 agent cron；未分析完整访问日志、数据库消费、账单或所有手工 shell 历史。
- 原生端无遥测，外部用户和持续活跃未知。
- 文件数、代码行和功能盘点是当前工作树静态快照，不代表可构建或已发布。
- 历史 dev-notes 中的成本和运行状态只代表各自记录日期，未当作当前实测。
