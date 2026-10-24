# 冗余模块工作量与拖累量化评估（多端重点）

> 日期：2026-10-25
> 角色：只读评估（HEAD 212a9ec，未改动任何源代码）
> 前置：站在 `docs/dev-notes/20261025-platform-slimming-review.md`（下称「瘦身报告」）结论上复核，不重抄
> 方法：git 历史量化 + 定点代码核验 + dev-notes/记忆库占比作为「AI 会话投入」代理指标

## 一、结论速览

1. **多端（native + ios）是「小体积、高税率」的拖累**：代码量只占产品代码 7.3%，却占近 30 天代码改动的 **22.3%**、占改密单一特性插入行的 **27.6%**、占 8/3-8/6 冲刺 commit 的 **33.3%**。拖累不在体积，在「每个横切特性都要 ×3 端复制 + 修竞态」的乘数效应。
2. **旧 `ios/ADResearch` 证据链完整，应立即归档（退役第一候选）**：全生命周期仅 3 个 commit，其中 2 个（66.7%）是 10-25 被后端改密特性倒逼的兼容补丁；目录内**连 .xcodeproj 都没有**（无法构建发布）；native 自己的 README:158-160 已写明「如确认废弃可另行删除」；全仓无任何 CI/脚本/编排引用它。
3. **瘦身报告的结论今天全部仍然成立**（逐条复核见第四节），包括旧 iOS 的 refresh 轮换缺陷（`AuthManager.swift:81` 只回写 access、不存轮换后的 refresh token，问题仍在）。
4. **research/ 五进程原型确认为死代码**：`orchestrator.py:46` 丢弃 `_interval`、`:84` 每 300 秒复活已退出 agent 的设计缺陷仍在；7-16 后再无功能 commit；主平台/Dockerfile/compose 零引用。
5. **核心后台（app/web/scheduler/celery/deploy）不可砍论据扎实**：生产 7 容器、scheduler 内 92 处 add_job、app 129K 行 + 124 个测试文件，Web 价值闭环全部依赖它。
6. **最划算的一刀**：归档 `ios/` 目录 + 在 AGENTS.md 写死「Swift 客户端只保留一套」规则，预计消除未来每次横切特性约 10-15% 的客户端税。

## 二、量化数据

### 2.1 代码规模（当前工作树）

| 模块 | 文件数 | 行数 | 测试 |
|---|---|---|---|
| app/（Python） | — | 129,362 | 124 个 test_*.py |
| web/src（TS/TSX） | — | 49,618 | 19 个测试文件 |
| native/（Swift） | 75 | 12,876 | 仅手工脚本 Tests/AuthFlowValidation/main.swift，无 XCTest、无 CI |
| ios/（Swift） | 14 | 1,180 | 同上（main.swift），**无 .xcodeproj** |
| research/（Python） | 9 | 557 | 无 |
| agent/（Python） | 22 | 9,827 | 无 |

native+ios 合计 14,056 行 = 产品代码（app+web+native+ios=193,036 行）的 **7.3%**。

### 2.2 Git 维护负担（2026-07-01 至今，全仓 530 commit / 全历史 739，即 72% 的历史发生在本窗口）

| 目录 | 触及 commit 数 | 插入+删除行 | 占全仓 churn 比例 |
|---|---|---|---|
| app | 238 | 114,688 + 7,835 | 25.8% |
| web | 205 | 113,475 + 44,697 | 33.4% |
| **native** | **17** | **14,274 + 648** | **3.1%** |
| **ios** | **2** | **461 + 15** | **0.1%** |
| research | 2 | 578 + 21 | 0.1% |
| agent | 12 | 11,272 + 455 | 2.5% |
| scripts | 64 | 12,400 + 539 | 2.7% |
| deploy | 48 | 1,018 + 319 | 0.3% |
| docs | 129 | 72,047 + 3,848 | 16.0%（其中 .html 镜像 36,129 行 > .md 26,088 行） |
| alembic | 43 | 5,112 + 323 | 1.1% |
| 全仓合计 | 530 | 412,538 + 61,784 | 100%（474,322 churn） |

注：commit 数按「触及该目录」计，跨目录 commit 会重复计入；行数按 `git log --numstat` 聚合。

### 2.3 近 30 天口径（2026-09-25 至今，全仓仅 14 commit）——拖累最直观的窗口

| 目录 | churn（行） | 占比 |
|---|---|---|
| app | 2,446 | 55.1% |
| web | 861 | 19.4% |
| **native** | **513** | **11.6%** |
| **ios** | **476** | **10.7%** |
| scripts / alembic | 61 / 83 | 3.2% |
| research / agent / deploy | 0 | 0% |

- **native+ios = 989 / 4,440 = 22.3% 的近 30 天代码改动**，全部来自 ee22869/0bcd07f 两个改密兼容 commit（14 个 commit 中占 2 个 = 14.3%）。
- 即：最近一个月里，**每 5 行代码改动就有 1 行花在两个零外部用户的原生客户端兼容上**。

### 2.4 单特性解剖：首登强制改密（ee22869 + 0bcd07f）

ee22869 全特性 3,028 插入行，分布：

| 端 | 插入行 | 占比 |
|---|---|---|
| app（后端） | 1,012 | 33.4% |
| web | 825 | 27.2% |
| **ios（旧客户端）** | **452** | **14.9%** |
| **native** | **385** | **12.7%** |
| docs / scripts / alembic | 354 | 11.7% |

- **Swift 两端合计 837 行 = 特性的 27.6%**，另加两端各一份手工验证脚本（126 + 105 行）。
- 三天后 0bcd07f 专门修「native 刷新回调覆盖改密令牌」竞态：native 109+11、ios 9+2 行——**这是多端复制本身制造的第二个 bug**，与瘦身报告预言的「三端同步成本」完全一致。

### 2.5 使用衰减与沉默期（是否存在持续使用的反向证据）

| 客户端 | 诞生 | 活跃窗口 | 沉默期 | 复活原因 |
|---|---|---|---|---|
| ios/ | 2026-06-28（6c494bb，脚手架） | 仅 1 天 | **119 天零 commit** | 10-25 被改密特性倒逼兼容 |
| native/ | 2026-08-03（523debd） | 8/3-8/5 三天冲刺 15 commit（0.1.0→0.4.0） | **80 天零 commit**（8/6-10/24，`git log --since=2026-08-06 --until=2026-10-24 -- native/ ios/` = 0） | 10-25 仅兼容 |

两个客户端在初始冲刺后**从未再产生任何有机功能迭代**，仅有的后期投入都是「别被后端锁死」的防御性适配。

### 2.6 AI 会话投入代理指标（dev-notes 与记忆库）

- dev-notes：134 个 .md / 1.55 MB（另有 86 个 html 镜像）。docs 目录占 7-1 以来 24% 的 commit（129/530）——文档即 AI 会话产出的直接痕迹。
- native/iOS 主题文档：20260628 三部曲（可行性 6.9KB + 产品规划 31.5KB + UX 设计 29.7KB = **68.1KB，占全部 md 字节 4.4%**，是 dev-notes 里最大的单一主题规划投入，且规划对象 119 天后被证明为弃子）；另有 20260803-overnight-delivery（native 章节约 40%）、20261024-first-login-password-policy（双端章节）、20261025-platform-slimming-review。
- 项目记忆库：71 条记忆，3 条 dedicated 于 native/macOS（4.2%），另有 1 条部分涉及。
- 合计口径：**native/ios 相关的会话产出约占文档字节 5%、代码近期 churn 22%**。token 消耗无法直接计量，以「commit/文档占比」代理（局限见第五节）。

## 三、瘦身报告结论逐条复核（今天是否仍成立）

| 瘦身报告论断 | 复核结果 | 证据 |
|---|---|---|
| 旧 iOS refreshTokenIfNeeded 只存新 access、不存轮换 refresh | **仍成立** | `ios/ADResearch/Services/Auth/AuthManager.swift:70-96`：第 81 行仅 `keychain.accessToken = response.accessToken`；对照 login（:48）与 changePassword（:59）均同时写 refreshToken。后端有 refresh 轮换时第二次刷新必然失效登出 |
| native 在 ee22869/0bcd07f 接入强制改密 = 实际持续投入 | **成立且被低估** | 见 2.4/2.5：0bcd07f 的竞态修复（native 109+11 行）正是多端复制的直接代价 |
| research/ 五进程编排器为文件型原型、interval 被丢弃、有重复拉起问题 | **仍成立** | `research/orchestrator.py:34-40` 声明 1800/3600/7200 秒间隔；`:46` `for name, fn, _interval in AGENTS` 弃用之；`:72-84` 对退出 agent 每 300 秒 respawn。全仓 Dockerfile/compose/app 零引用（grep 无命中） |
| agent 与主平台 CLS 双采集（同 endpoint 同参数） | **仍成立** | app 侧 `app/services/news/sources/cls.py:53` 用 `https://www.cls.cn/api/cache?name=telegraph&rn=20`（job `news_cls_5m`，scheduler_jobs.py:1284）；agent 侧 `agent/workers/cls.py:94-95` 用同一 `api/cache` + `roll/get_roll_list`。重叠源另有 reddit（app reddit.py vs agent reddit_finance + reddit_curl_cffi）、xueqiu；独有：stocktwits（TLS 指纹轮换 744b42a）、x、fed_intl、gov_china、eastmoney_news |
| native 无 XCTest/原生 CI、验证靠 `swiftc -parse` | **仍成立** | `.github/workflows/` grep `native|ios|swift` 零命中；native/ADResearch/README.md:155 的验证命令即 `swiftc -parse` 两趟 |
| 旧 ios 与主 native 不联动、native README 已声明可删 | **仍成立** | `native/ADResearch/README.md:158-160`「如确认废弃可另行删除」；ios/ 无 xcodeproj、无 CI、无外部引用 |
| 核心后台不可砍 | **论据更扎实** | 生产 7 容器（deploy/aliyun-ecs/docker-compose.yml）；`app/core/scheduler.py` 92 处 add_job 调用；停 scheduler/celery 页面数据将停滞（瘦身报告 §2.1 生产核验） |

## 四、分级处置建议

### 4.1 四级总表

| 模块 | 级别 | 一句话理由 |
|---|---|---|
| app/ web/ + scheduler + 双 Celery + deploy | **保留** | 产品本体与唯一数据链路 |
| agent/ | **收窄** | 生产 cron 在跑；按源合并去重（CLS/reddit/xueqiu），保独有源 |
| native/ADResearch（macOS 主体） | **收窄** | 有真实构建/菜单栏价值，但冻结 parity 追求，加契约冒烟 |
| native/ 内 iOS target | **归档（实验冻结）** | 从未真机验证，冻结对外承诺 |
| research/ | **归档** | 死原型，零引用，interval 缺陷未修 |
| ios/ADResearch（旧） | **退役（先归档后删）** | 无法构建、无使用、README 已判死刑 |

### 4.2 ios/ADResearch —— 退役（第一优先）

- **工作量证据**：全周期 3 commit / 1,195 插入行；其中 2 commit（10-25）+ 476 行（占其生命周期插入 39.9%）纯为改密兼容；119 天沉默期；无 xcodeproj（无法在 Xcode 打开构建，也不可能发布过）。
- **迁移成本**：≈0。后端兼容 shim 已随 ee22869 上线；全仓 grep 无 CI/脚本/编排引用 `ios/ADResearch`；瘦身报告与 native README 双重背书。
- **风险**：仅剩「所有者私藏使用」一种可能，而该目录无工程文件、无法构建，可能性极低。动手前让所有者口头确认一次即可。
- **回滚要点**：单独 commit 执行 `git rm -r ios/`（历史永在）；回滚 = `git checkout 0bcd07f -- ios/`。删除后 AGENTS.md 目录结构段同步移除该行，避免 AI 会话继续被误导。

### 4.3 native/ADResearch（macOS）—— 收窄为 companion

- **工作量证据**：17 commit / +14,274 行集中在 8/3-8/5；之后 80 天零有机投入；改密特性付出 494 行（385 兼容 + 109 竞态修复）。
- **保留理由**：菜单栏行情、⌘K、深链、本地提醒是 Web 给不了的桌面效率；有 DMG 构建记录（记忆库 20260804 条目）。
- **收窄动作**：功能冻结在「晨读/资讯/宏观/标的/评分」阅读路径；不再追 Web parity；下一步投入前先做一次真实 `xcodebuild` + 登录/refresh/研报解码三契约冒烟（手工 Codable 已两次漂移：b9d43d2、0bcd07f）。
- **决策门**：若未来 60 天仍无有机 commit（非兼容性）投入，降级为 Web-only 并归档。
- **回滚要点**：归档前打 tag（如 `native-0.4.0-final`）；深链 `alloyresearch://` 若被外部笔记引用需先盘点（仓内不可见）。

### 4.4 native/ 内 iOS target —— 归档（实验冻结）

共享 target 无真机、无 TestFlight、无发布证据。冻结 = 不再为 iOS 形态单独适配（macOS 优先），等待真机验证再解冻。成本几乎为零（同一 target，仅停止 iOS 专项投入）。

### 4.5 research/ —— 归档

- **证据**：9 文件 557 行；最后功能 commit 421130c（7-16），其后仅 630535a ruff 顺手清理；orchestrator 设计缺陷（:46/:84）从未修；主平台零引用。
- **迁移成本**：≈0（其价值已由 agent/overnight_research_v2 取代——见记忆库 20260719 条目）。
- **风险/回滚**：无消费者；回滚 = git 历史。建议同 ios/ 一起单独 commit 归档。

### 4.6 agent/ —— 收窄（按源合并，不可一刀切停）

- **证据**：12 commit / 11,272 行，7-8 月活跃维护（TLS 指纹轮换、镜像丢失双保险等真实生产事故修复）；生产 cron 每小时在跑（瘦身报告生产核验）。
- **合并清单**：CLS（与 `news_cls_5m` 同 endpoint，建议 agent 侧停此源）、reddit、xueqiu 归主平台；**保留** stocktwits（TLS 指纹抗 WAF）、x、fed_intl、gov_china、eastmoney_news 等独有源。
- **顺序**（strangler，同瘦身报告阶段 C）：主链路对等 → 双跑对账 → 迁告警/watchdog → 停对应 cron 项 → 快照回滚。下线任何源前先盘点 JSON 产物与仓库外消费者。

### 4.7 看似冗余但不可砍（验证瘦身报告论据）

| 对象 | 为什么不能砍 |
|---|---|
| APScheduler + 双 Celery worker | Web 全部行情/指标/评分/信号/公告的上游；scheduler.py 92 处 add_job；停了 API 在线但数据停滞 |
| deploy/aliyun-ecs 编排 + update.sh | 生产唯一部署入口，含迁移校验与镜像清理（20260805 满盘事故修复） |
| 多 provider LLM fallback 链 | 20260928 主备切换链已两次救场（MiniMax 额度耗尽自动兜底） |
| trafilatura→Jina→LLM 正文降级链 | 各层分别承担低延迟/自愈/可用性，补协调而非删层（瘦身报告 P1-4） |
| wewe-rss 容器 | 公众号采集通道，生产常驻（compose 第 6 个服务） |
| scripts/ 大杂烩 | 混有备份/恢复/watchdog 等关键工具，只能分类归档不能整体删 |
| dev-notes html 镜像 | 用户既定阅读习惯（记忆库明文规则）；但注意其占 docs 行数 churn 58%，是 token 成本可观测点 |

## 五、方法论与局限

1. **token 消耗为代理估算**：无法读取 AI 会话原始 token 计量，用三类代理——git churn（代码产出）、dev-notes 字节（文档产出）、记忆库条目占比（会话主题分布）。真实 token 还包括读代码/排障等未落盘部分，代理必然低估会话次数，但「方向与占比」稳健。
2. **commit 归属**：横切 commit（如 ee22869 同时触 app/web/native/ios/docs）在分目录统计中重复计数，因此各目录 commit 之和 > 总 commit 数；行数按 numstat 聚合无重复。
3. **近 30 天窗口仅 14 commit**，小样本放大了改密特性的占比；因此同时给出 7-1 以来（530 commit）的全窗口数据：全窗口 native+ios 仅占 churn 3.2%——结论不是「多端吃掉大盘」，而是「多端在近期横切特性上的税率极高且无对等用户价值」。
4. **「无使用」基于无遥测推断**：仓内证据（无 CI、无发布、沉默期、无 xcodeproj）强烈但非绝对；退役前按报告建议做一次所有者确认。
5. 生产运行态引用昨日瘦身报告的 ECS 只读核验（docker ps + cron），本日未重复登录生产。

## 六、执行清单（建议顺序）

1. 【退役】单独 commit `git rm -r ios/`；AGENTS.md 目录段删除对应行；后续横切特性预算立省约 15%（Swift 端一半）。
2. 【归档】单独 commit `git rm -r research/`（或移 attic/ 并在 AGENTS.md 标记）。
3. 【规则】AGENTS.md 增补：「Swift 客户端唯一实现 = native/ADResearch；新增横切契约改动只同步 Web + native，ios/ 不再同步」。
4. 【收窄】agent 停 CLS 源（与主平台 news_cls_5m 完全重复），按 4.6 清单逐源 strangler。
5. 【收窄】native 做一次真实 xcodebuild + 三契约冒烟，再决定 60 天观察窗是否启动。
