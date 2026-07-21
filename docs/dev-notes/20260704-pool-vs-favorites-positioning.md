# Pool / Favorites / Portfolio 定位与改造方案（K16）

> 编制日期：2026-07-04  
> 编制人：K16 子 agent（定位审计 + P0 落地）  
> 范围：AD-Research 平台「标的池 / 关注清单 / 投资组合 / 模拟组合 / 真实持仓」概念边界、用户期望、改造方案  
> 与其他 agent 的边界：明确不与 K5（移动端）、K6（术语/指标）、K11（全球市场）、K12（地缘政治）、K14（新手教学）、K15（学习平台化）冲突

> **注**：本文为 2026-07-04 的时点记录（K16 审计 + P0 落地），文中行号与具体文案已随后续迭代变化。后续进展（2026-07-21 核实）：P1「Portfolio Center」已落地为 `/portfolio` 页面（`web/src/pages/Portfolio/index.tsx`，路由注册于 `web/src/routes.tsx`，侧边栏「交易」分组「我的组合」，含目标池 vs 实际持仓偏离对比）；Dashboard 的"组合中心"chip 行在后续视觉重构中已移除，入口改为侧边栏；`PoolList` description 与 `helpPrompts.ts` pool_detail 措辞已被再次改写（现分别为"管理关注池与研究篮子…"与"管理一组标的的关注池/研究篮子成员"），方向与本文定位一致。

---

## 第一阶段：现状审计（只读）

### 1.1 概念清单

| 中文概念 | 英文 | 物理表 / 文件 | API 路由前缀 | 前端入口 |
|---|---|---|---|---|
| **关注清单 / 自选** | Favorites / Watchlist | `user_favorite`（`app/models/favorite.py`） | `/api/v1/favorites` | `/instruments` 详情页收藏按钮 + Dashboard "我的收藏" / "自选股动态" 卡 |
| **标的池** | Pool | `etf_pools` / `pool_member` / `pool_weight` / `pool_snapshot`（`app/models/pool.py`） | `/api/v1/pools` | `/pools`（侧边栏「标的池管理」）+ Dashboard "我的标的池" 卡 |
| **模拟交易账户** | Paper Trade | `paper_trade_account` / `paper_trade_order` / `paper_trade_position`（`app/models/trading.py`） | `/api/v1/paper-trading/...` | `/paper-trading`（侧边栏「模拟交易」） |
| **真实交易账户** | Live Trade | `live_trade_config` / `live_trade_order` / `live_trade_position` / `risk_rule`（`app/models/trading.py`） | `/api/v1/live-trading/...` | `/live-trading`（侧边栏「真实交易」） |

### 1.2 每个概念"现在能做什么"

#### Favorites（关注清单 / 自选）— 最轻量
- **API**：`GET /favorites`、`POST /favorites/{code}/toggle`、`POST /favorites/{code}/add`、`DELETE /favorites/{code}`、`GET /favorites/{code}/status`
- **核心目的**：记录"我感兴趣的标的"
- **关联**：触发 `/news/watchlist`（关注标的相关资讯聚合）、Dashboard 「自选股动态」新闻流
- **不涉及**：权重、目标、实际仓位、回测
- **后端实现**：`app/services/favorite_service.py`（4 个方法 + 1 个 status check）

#### Pool（标的池）— 中长期目标组合
- **API**（`/api/v1/pools`）：CRUD、成员增删、权重 CRUD、`/weights/suggest`（三种算法）、`/analytics`（分类分布 + 加权表现 + 再平衡提醒）、`/correlation`（60 日日收益相关系数矩阵）、`/snapshots`（创建 + 列表）
- **核心目的**：在**目标**层面管理一组标的，包括目标权重、算法建议、快照、相关性、再平衡提醒
- **不涉及**：真实下单、资金占用、账户余额、实际持仓
- **后端实现**：`app/services/pool_service.py` + `app/services/pool_enhancement_service.py`

#### Paper Trade（模拟组合）— 模拟账户实盘
- **API**（`/api/v1/paper-trading/...`）：账户管理（下单、看 P&L、自动交易）
- **核心目的**：用 USDT 余额跑模拟账户，验证策略
- **关联**：`signal.id` 可触发 `paper_trade_order`
- **UI**：`/paper-trading` 页面完整功能（创建账户、下单、看 positions、orders、P&L）

#### Live Trade（真实持仓）— 真实账户
- **API**（`/api/v1/live-trading/...`）：Binance API 凭证管理 + 下单 + 持仓 + 风控规则
- **核心目的**：在 Binance（testnet/mainnet）真实下单
- **UI**：`/live-trading` 页面

### 1.3 功能重叠 / 用户实际撞到的三类混淆

#### 混淆 A：Pool vs Favorites（最容易撞）
**现象**：
- Dashboard 同时出现「我的收藏」和「我的标的池」两个并列卡（`web/src/pages/Dashboard/index.tsx:554-653`），用户看到「这俩有啥区别？」
- PoolList 页面顶部 description：`"创建和管理自定义标的池，组织您关注的标的组合"`（`web/src/pages/PoolList/index.tsx:59`）—— 直接把 Pool 等同于「关注的标的组合」，这是错位
- 用户口语：「我想跟踪这组标的」「我看好这些」「我自选里加了 X」—— 自然落在 Favorites 上；但「我想给这组标的设目标权重」「我想按评分自动分配仓位」「我想监控再平衡」—— 自然落在 Pool 上

**撞点**：
- Pool 不能加仓 / 不能记录历史决策（`PoolMember.notes` 是 text 但前端基本没用）
- Favorites 加了之后**不能**被 Pool / Screen / Signal 直接"引用"—— Pool 选股必须从 `/screen` 或 `/scores` 重新挑
- 用户想"把自选导入到标的池"：当前**没有 API 也没有 UI**

#### 混淆 B：实际持仓 vs 目标权重（结构性缺失）
**现象**：
- 用户在 Pool 里设了"等权 / 评分加权 / 风险平价"的目标权重，Pool 算出"再平衡提醒"
- 但用户无法直接看到："我现在的 Paper Trade 账户里，实际仓位偏离这个目标权重多少"
- `/paper-trading` 页面看 positions，`/pools/:id` 页面看权重，**没有统一对比页**
- `app/services/pool_enhancement_service.py:759-811` 的 `_check_rebalance` 已经按"等股数"假设计算 actual_weight —— 这是**目标 vs 目标**（不是 vs 实际持仓）

**撞点**：
- 想做"目标 → 模拟账户"一键同步：当前需要**手抄**每个标的的目标 USDT 数量
- Live Trade 同样缺乏"对齐 Pool 目标"的引导

#### 混淆 C：模拟 / 真实持仓分离
**现象**：
- `/paper-trading` 和 `/live-trading` 是两个完全独立的页面
- 用户需要切换页面才能对比"我模拟赚了 vs 我实盘赚了"
- 没有任何一个"持仓中心"统一显示"所有账户当前持仓合计"

### 1.4 术语冲突实测

| 位置 | 当前用词 | 应该统一为 | 说明 |
|---|---|---|---|
| `web/src/pages/Dashboard/index.tsx:555` | "我的收藏" | "**关注清单**" | "收藏"语义偏向 Web 2.0，"关注"是金融行业通用 |
| `web/src/pages/Dashboard/index.tsx:503` | "自选股动态" | "**关注标的动态**" | "自选"在东方财富等老牌平台常用，但和「收藏」混用造成混淆 |
| `web/src/pages/PoolList/index.tsx:59` | "组织您关注的标的组合" | 删除或改为"管理您的目标组合" | 这句话让 Pool 看起来像 Favorites 增强版 |
| `web/src/pages/Dashboard/index.tsx:602` | "我的标的池" | 保持（Pool 的中文标准译法） | OK |
| `app/services/favorite_service.py:1` | "favorite/watchlist" | 顶部 docstring 应明确：「轻量关注清单 ≠ 投资组合」 | OK，待补 |
| `web/src/utils/termDictionary.ts:388-463` | 标的池 section | OK，K6 已建立术语 | 不动 |
| `web/src/utils/helpPrompts.ts:144` | "管理一组 ETF 的**持仓**和权重" | 应改为"管理一组 ETF 的**目标权重**和配置" | "持仓"一词在 Pool 上下文里是错的，Pool 是"目标"不是"实际" |

### 1.5 与其他 agent 的边界确认

- **K5（移动端）**：iOS App 设计阶段，本任务只动 web 端，不冲突
- **K6（术语/指标/算法）**：`termDictionary.ts` 已建立 K6 的术语表；K16 不修改任何术语条目，**只动 helpPrompts.ts 里 pool_detail 的措辞**（一处），并加 favorite_service.py 顶部注释
- **K11（全球市场）**：Dashboard `GlobalSnapshot` 是 K11 落地；K16 不动这段
- **K12（地缘政治）**：与本任务完全无交叉
- **K14（新手教学）**：`/learning` 路由、3 个 Dashboard chip、用户 Dropdown 中的"新手教程"项；K16 **不在 chip 行加自己的 entry**，避免视觉混淆
- **K15（学习平台化）**：`DailyLesson` 在 Dashboard 第 400 行；K16 不动它

K16 唯一的写入口是：
1. Dashboard 的 `.dashboard-side-stack` 第三张卡（仅 Portfolio Center 入口卡片）
2. Dashboard 的 K14 chip 行**下方**新建一行（明确与 K14 chip 行区分），作为 Portfolio Center 入口
3. `app/services/favorite_service.py` 顶部 docstring 扩写
4. `web/src/utils/helpPrompts.ts:144` 措辞微调（pool_detail prompt 中"持仓" → "目标权重"）
5. `PoolList/index.tsx:59` description 微调（避免"关注的标的组合"这种暧昧表述）

---

## 第二阶段：重新定位与改造方案

### 2.1 三大概念的新定位

| 概念 | 新定位 | 一句话定义 | 用户典型问题 |
|---|---|---|---|
| **Favorites / 关注清单** | 轻量观察列表 | 「我想持续看到这些标的的行情和新闻」 | "这只 ETF 不错，加个关注" |
| **Pool / 标的池** | 目标组合 | 「这是我的中长期配置计划，配多少权重由我说了算」 | "我想给自己定一个'消费 + 医药 + 科技'的目标组合" |
| **Portfolio / 投资组合** | 实际持仓中心 | 「我模拟 / 实盘账户里，现在**真的**持有啥」 | "我的模拟账户偏离目标权重多少？" |

### 2.2 改造范围

#### P0（K16 本次落地）
1. **术语统一（微调，非全量替换）**：
   - `PoolList/index.tsx:59` description 改写："管理你的目标组合——设定成员、权重、算法建议与再平衡提醒"
   - `helpPrompts.ts:144` "管理一组 ETF 的持仓和权重" → "管理一组 ETF 的**目标权重**和成员配置"
   - 在 `app/services/favorite_service.py` 顶部 docstring 扩写，明确"轻量观察列表 ≠ 投资组合"
2. **Dashboard 入口卡片**：
   - 在 K14 chip 行（Dashboard/index.tsx:363-397）**下方**、`DailyLesson`（400 行）**上方**之间，新增一行 `Portfolio Center` chip
   - **不**走侧边栏（避免和 K14 决策冲突，K14 已示范 off-menu 模式）
   - chip 文本：「我的组合 / 持仓中心」+ 图标 `WalletOutlined`，跳转 `/paper-trading`（临时目标，详细 Portfolio 页面是 P1）
   - chip 样式：与 K14 chip 行并列但**视觉分组**（新加一个 label "组合中心：" + 不同颜色）

> **为什么不在侧边栏加 `/portfolio` 项**：K14 已经在 routes.tsx:101 显式声明"不在左侧菜单，由 dashboard chip / 用户菜单进入"。K16 跟随同样的设计哲学，避免侧边栏再 +1 项。

#### P1（建议 K17+ 接手，本任务不落地）
- 新建 `web/src/pages/Portfolio/index.tsx`：聚合 Paper Trade + Live Trade 当前持仓
- 路由 `/portfolio`（**不在侧边栏**，从 Dashboard chip 进入）
- 「实际持仓 vs 目标 Pool」diff 卡片：如果用户给某个 Pool 设了目标权重，对比"该 Pool 的目标权重 vs 模拟账户该标的的实际市值占比"
- 新增路由 `pages/Portfolio` 的 entry 卡片样式与 Dashboard chip 行一致

#### P2（更长线，建议 K18+）
- "Pool → 模拟账户" 一键同步：点击「按此目标建仓」→ 后端按目标权重 + 模拟账户当前 cash 计算每个标的的买入数量 → 自动生成 paper_trade_order
- "Pool → 真实账户" 同理，但需要风控拦截（提示先看 max_order_value）

### 2.3 模块关系图（ASCII）

```
                            ┌────────────────────────────────────────┐
                            │   Dashboard  (首页看板)                │
                            └────────────────────────────────────────┘
                                              │
   ┌──────────────────────────────┬───────────┴────────────┬──────────────────────────────┐
   │ K14 chips: 新手教程/估值/回测 │ Portfolio chip: 我的组合│ K15 DailyLesson: 今日学习 3 分钟│
   └──────────────────────────────┴────────────┬────────────┴──────────────────────────────┘
                                              │ navigate('/paper-trading')  [P0 临时目标]
                                              ▼
                              ┌────────────────────────────────┐
                              │  Paper Trading  (模拟交易)      │   ← 当前的"组合中心"代理
                              │  · 多账户管理                  │
                              │  · 下单 / 看 P&L                │
                              │  · 持仓按账户分组                │
                              └────────────────────────────────┘
                                              │
                                              │  (P1 之后)
                                              ▼
                              ┌────────────────────────────────┐
                              │  Portfolio Center  (统一中心)    │
                              │  · 聚合 paper + live 持仓       │
                              │  · 实际持仓 vs 目标 Pool diff   │
                              │  · 一键「按目标建仓」            │
                              └────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════
侧边栏现有导航（K16 不动）：
  · /pools               → 标的池管理（**目标**组合；成员 / 权重 / 算法）
  · /instruments/:code   → 标的详情（带"加关注"按钮 → 写入 Favorites）
═══════════════════════════════════════════════════════════════════════
用户视角的 3 个心智模型：
  ① 关注清单 (Favorites)：  一次性 + 持续观察 → News 聚合、行情卡片
  ② 标的池   (Pool)：       中长期目标 → 算法建议、再平衡、快照
  ③ 实际持仓 (Portfolio)：  已下订单后的状态 → 跨账户聚合、P&L、再平衡执行
```

---

## 第三阶段：P0 落地清单（已实施）

| 文件 | 改动 | 与其他 agent 边界 |
|---|---|---|
| `web/src/pages/Dashboard/index.tsx` | 在 K14 chip 行（第 363-397 行）下方、K15 `DailyLesson`（第 400 行）上方新增"组合中心"chip 行 | 不动 K14 chip 行；不动 K15 DailyLesson；不动 GlobalSnapshot / StatCard |
| `web/src/utils/helpPrompts.ts` | pool_detail prompt 中"管理一组 ETF 的持仓和权重" → "管理一组 ETF 的**目标权重**和成员配置" | K6 的 `termDictionary.ts` 不动 |
| `app/services/favorite_service.py` | 顶部 docstring 扩写，明确 favorites 与 pool 职责分离 | 不动方法实现 |
| `web/src/pages/PoolList/index.tsx` | description 改写，避免"关注的标的组合"暧昧表述 | K6 的术语条目不动 |

---

## 第四阶段：验证

- `npx tsc --noEmit` 与 `npm run build` 通过
- 文件清单 + 行号详见 `K16_P0_REPORT.md`（待生成）
- 不 push 到 GitHub（遵循 no-push-without-explicit-approval.md）