# 评估：将「自选股」与「标的池 / 组合」自动联动

> 作者：Claude Code 评估会话（产品/UX 设计评审）
> 日期：2026-07-09
> 状态：建议稿，未实施，无代码改动

---

## 1. Executive Verdict（一段话结论）

**不建议**按原提案（"加入标的池 / 组合即自动加入自选股"）落地。原因是自选股在当前数据模型里是一个**持久化的、轻量的、带主键的 `user_favorite` 表**（`app/models/favorite.py`），且服务层的 docstring 已经明确写死边界：

> `UserFavorite` 是**轻量级关注清单**，定位明确区别于平台上的其他"标的聚合"概念……如果未来要让 Favorites 一键导入到 Pool / Paper Trade，请在 **PoolService** 或 **PaperTradingService** 中新增专门的"导入"端点，不要在本服务里堆砌。 (`app/services/favorite_service.py:5-22`)

把"加入池"做成隐式副作用，会污染自选股、让用户的关注列表失去可解释性，并且会在 CSV 批量导入、AI 自动建池、共享池等场景里**让用户失去对自己列表的控制**。

**推荐**改成显式的"计算视图 + 来源过滤"模型（详见 §4）：自选股页面把"我手动加的"和"来自池 / 组合的"用 `source` 字段区分开，用户在池详情页可以一键**把整个池推送到自选**（带确认弹窗），而不是反过来由系统自动写。

---

## 2. 用户提案的 Pros（公平起见）

提案者想要解决一个**真实的痛点**：在 ETF 详情页点 ★ 加入自选 → 再到 Pool 详情页手动把它加进 Pool → 再到 PaperTrade 下一笔单，三套流程都要重复"找代码 → 搜 → 添加"，对一名日常用户来说确实繁琐。所以提案背后有几个合理的动机：

| 维度 | 为什么提案看上去合理 |
|---|---|
| **降低摩擦** | 一次添加，多处生效，符合"最少惊讶"原则。Robinhood / Webull 等券商的 watchlist 默认就是"我关注的任何标的"，隐式扩展到组合也是常见的。 |
| **跟住重要标的** | 用户既然把某标的加入 Pool，说明它在长期跟踪范围内；那它**也确实应该**实时盯盘 → 自选股恰好是实时盯盘的入口（`Favorites/index.tsx` 用了 `useMarketStream`）。 |
| **一致语义** | "我拥有的 / 我关注的"通常是一棵 set 的超集，把这三层概念桥接起来，数据上看更整洁。 |
| **避免遗忘** | 用户在 Pool 里加了一个标的，但忘了加自选，结果它就不在 Dashboard 的"自选股动态"里显示，新闻聚合也漏掉。自动联动能堵这个洞。 |

---

## 3. 用户提案的 Cons / Risks（这里真正值得讨论的地方）

### 3.1 语义陷阱：方向"反过来也成立"的幻觉

> "加入标的池 / 组合 → 自动加入自选股；反向不要求。"

听起来"反向不要求"很宽松，但实际操作里**这两个方向在多个场景下是反过来的**：

1. **临时回测 / 一次性筛选**：用户跑了一个 50 只 ETF 的回测池，跑完就扔。这种池里的标的**不该**出现在自选。
2. **AI 研究附带的小池**：用户问 AI "帮我筛 5 只红利 ETF"，AI 创建一个临时池。50% 的情况下用户根本不会去看这些标的，凭什么它们进自选？
3. **共享 / 模板池**：M21-3 引入了 `user_id IS NULL` 的 shared legacy pool（`app/models/pool.py:39-49`），admin / 模板池可能包含用户根本不想跟踪的代码。
4. **手动管理下的反向**：用户先在自选里删除了 X，又发现 X 在 Pool 池 Y 里 → 此时 X 是要"复活"还是保持已删？提案只规定了单向 auto-add，但删除时的对称性问题悬而未决。

### 3.2 删除的"半边对称"困境

提案说"反向不要求"，但没说**删除**怎么做：

- 用户从 Pool 移除 X → 自选里 X 要不要跟着删？
  - **删** → 用户的"自选"语义被 Pool 状态绑架。一个月后用户回头看自选，发现好多标的莫名其妙消失了。
  - **不删** → 标注不清楚，列表里会出现"为什么这个标的还在自选"的死链。

无论是哪种，结果都是**自选股的"语义"不再稳定**。

### 3.3 数据模型：自选股是**表**，不是**视图**

代码里（`app/models/favorite.py`）：

```python
class UserFavorite(Base):
    __tablename__ = "user_favorite"
    id = Column(String(50), primary_key=True, comment="Composite key: username_etf_code")
    username = Column(String(50), ForeignKey("users.username", ondelete="CASCADE"))
    etf_code = Column(String(20), ForeignKey("etf_info.code", ondelete="CASCADE"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

是独立持久化的表，**不是** `UNION(PoolMember, PaperTradePosition)` 的视图。要按提案动，就要：
- 在 `PoolService.add_member` 和 `PaperTradingService.place_order` 里**反向注入**写 `user_favorite` 的代码；
- 或者改前端，在"自选"页面拼一个内存里的 UNION，但这样持久化、`is_favorite()` 校验、News 聚合（`app/api/v1/news.py:328`）全都得重写。

无论哪种，**触面都很大**。

### 3.4 跨场景副作用矩阵

| 触发场景 | 当前行为 | 提案落地后行为 | 风险 |
|---|---|---|---|
| 单条 add 到 Pool | PoolMember +1 | PoolMember +1，UserFavorite +1（首次） | 可接受 |
| 池成员手工移除 | PoolMember 软删 | PoolMember 软删；UserFavorite 是否联动删？ | 见 §3.2 |
| **CSV 批量导入到池** | 不支持（API 只有 `POST /pools/{id}/members` 单条） | 如果未来支持，500 个代码一次写，500 条 UserFavorite 同时产生 | 用户可能完全没意识到自己"订阅"了 500 只标的，News 聚合、Dashboard top 10 全被打乱 |
| **AI 自动建池** | 不存在（`research_service.generate_pool_review` 只读池，不建池） | 未来一旦 AI 建池，半夜用户发现自选多了 20 个陌生标的 | 信任危机 |
| **共享池（NULL owner）** | 普通用户可读、不能写成员 | 共享池的成员如果被 admin 加了，自动写到普通用户自选 → leak | 严重隐私问题 |
| **跨用户添加** | 不支持 | 如果提案做了"按池统一加"，会把 admin 的操作反映到所有人的自选 | 破坏隔离 |
| **PaperTrading BUY** | 持仓 +1 | 持仓 +1，UserFavorite +1 | 用户买了一笔冷门测试仓，凭什么要订阅它？ |
| **LiveTrading BUY** | 真实下单 | 自选也加了 | 真金白银已经说明意图，"再加一道"反而画蛇添足 |

### 3.5 UX 一致性：Dashboard 的"自选股"卡片会失控

`web/src/pages/Dashboard/index.tsx:369`：

```typescript
const { favorites, count: favCount, isLoading: favLoading } = useFavorites(10);
// Favorites news: pull each favorite's news, dedup, sort by recency.
const { data: favoritesNews, isLoading: favNewsLoading } = useQuery({
  queryKey: ['dashboard-favorites-news', favorites?.map((f: any) => f.etf_code).join(',')],
```

Dashboard 顶部有个"自选股动态"卡片，自动取前 10 个 favorites 拉新闻。如果 auto-add 落地：
- 用户的 5 个手动自选会被淹没在 100 个来自池/组合的代码里；
- Dashboard 新闻聚合 API 会被放大倍数调用（`/api/v1/news?favorites=true` 的下游成本）；
- `isConnected` SSE 连接数（`useMarketStream(codes)`）也会爆掉。

### 3.6 审计 / 可解释性

用户问"为什么 510300 在我的自选里？"：
- **手动加**：能回溯到具体时间和地点。
- **从池 X 加的**：用户已经不记得当初为什么要建池 X。
- **从 PaperTrade 的某笔单加的**：用户根本不记得这笔单。

`user_favorite` 表没有 `source` / `origin` / `origin_id` 字段，加进去以后**完全无法溯源**。这跟合规和"为什么我有这个标的"的 UX 矛盾。

### 3.7 性能

`UserFavorite` 是按 `(username, etf_code)` 唯一约束存的，500 个池成员一次性写 → 500 行 INSERT，**还要校验每个 ETF 是否存在**（`add_favorite` 里已经有 `ETFInfo.code` 的查询）。N+1 风险 + 唯一键冲突 + 事务开销都不小。

而且所有"自选"的入口（News、Dashboard、Favorites 页）都假设它的 size 是个位数到几十个量级，**几百个的 favorites 会让 SSE 流、News 聚合、分类折叠分组全部退化**（`Favorites/index.tsx:127-138` 的 `grouped` 是按 category 内存分组的）。

---

## 4. 推荐方案（详细说明）

### 4.1 核心思路：**显式 + 可解释 + 视图层合并**

把自选股页（`Favorites/index.tsx`）**保持**轻量、独立、用户控制，但加一个**"来源（source）"维度**：
- `source = "manual"` — 用户手动 ★ 加入
- `source = "pool:<id>"` — 来自某个池（如果用户在池详情页点过"全部加入自选"）
- `source = "portfolio:<id>"` — 来自某个组合
- `source = "auto"` — 系统推断（**默认关闭**，未来可作为高级开关）

实现要点：

1. **`user_favorite` 表新增 `source` 字段**（`VARCHAR(50)`），可空，nullable，**没有 alembic migration 风险**（加列即可，老行是 NULL = manual）。
2. **不自作主张写** `user_favorite`。改由用户在 Pool 详情页 / Portfolio 详情页主动触发一个"添加全部成员到自选"的按钮，**带确认弹窗**：
   ```
   ┌─ 添加 27 个标的到「我的自选股」？ ─────┐
   │ 来自「标的池 / 红利 ETF 组合」           │
   │ 这些标的会出现在自选股列表、实时盯盘     │
   │ 和自选股新闻聚合中。                     │
   │                          [取消] [确认]   │
   └─────────────────────────────────────────┘
   ```
3. **在 Pool 成员表上做"虚拟视图"**：自选股页面查询时，**额外**把"当前用户的所有池成员的 etf_code"作为一个**只读的虚拟集合**返回，前端按"手动 vs 来源"分组：
   - **手动组**（真正的 `UserFavorite` 记录）
   - **来源组**（来自每个池 / 组合，每组一个 collapse panel，标注来源和数量）
   - 合并去重（同一个 etf_code 在多处出现时，**优先显示手动记录**，并标注"也在池 X / 组合 Y 中"）

这个方案的优点：
- ✅ 不写隐式副作用。
- ✅ 用户的所有"我的关注"一目了然（手动 + 来源分布）。
- ✅ 删除语义清晰（用户从 Pool 移除标的，**来源组的虚拟视图里这一行消失**，但手动组不受影响；如果该标的没有手动记录，整个就从自选里消失，符合"它确实不在任何地方了"的直觉）。
- ✅ 性能好：视图层合并是查询时 UNION，不需要持久化到 `user_favorite`，行数不膨胀。

### 4.2 备选 A：**只显式，不视图化**（最小改动）

不改数据模型。在 Pool 详情页加一个按钮"★ 添加全部成员到自选" → 调用现有的 `favoriteApi.add(code)` 一个一个加。**简单、直白、不动架构**。缺点：CSV 批量导入、AI 自动建池这类用例没有被特别处理（要靠用户每次手动按）。

### 4.3 备选 B：**跟踪模式开关**（高级用户向）

在用户设置里加一个 `auto_track_in_favorites: bool`：
- 默认 `false`，行为不变。
- 用户设为 `true` 后，所有手动加入 Pool / 下 PaperTrade 单的标的自动写入 `user_favorite`，`source` 字段写来源。

这样**专业用户能享受自动联动，普通用户不被影响**。代价是要在所有写入路径（`PoolService.add_member`、`PaperTradingService.place_order`、`LiveTradingService.place_order`）加钩子。

### 4.4 我会选哪个

**首选 §4.1**（视图层合并 + 显式入口）。如果工程量太大或产品想快上，**次选 §4.2**（只加一个按钮）。**§4.3 暂时不做**，因为它本质上是提案的另一种实现，但只对高级用户开；考虑到 `FavoriteService` 现有的 docstring 明确禁止在 favorites 那边堆逻辑，**§4.3 会让那个 docstring 变成谎言**，文档/代码一致性会变差。

---

## 5. 边角案例 & 待澄清问题

1. **共享池（`user_id IS NULL`）**：M21-3 后这类池对所有用户可见。普通用户能不能"添加整个共享池到自选"？如果是，那 admin 后台改共享池成员时，**所有用户的自选视图都会跟着变**——这没问题，反而是个 feature（"我现在关注的是行业模板池 X"）。
2. **M21-3 owner-scoping**：共享池能不能被"推送"到某用户？提议**不要**做强制推送——只能由用户自己从 Pool 详情页按按钮触发。
3. **删除的传播**：
   - 用户从 Pool 移除 X，且 X 在自选是手动加入的 → 保持自选不变，但**在 X 行上加一个 tag "已从池 Y 移除"**。
   - 用户从 Pool 移除 X，且 X 在自选**只**是 pool-source → 直接从自选视图里消失。
4. **数量上限**：`useFavorites(200)` 是 Favorites 页的上限。视图化方案下，**虚拟组的成员数不受 200 限制**，但手动组仍然限 200。需要前端加分页或"显示全部来源"。
5. **News 聚合**：当前 `/api/v1/news?favorites=true` 走 `user_favorite` 表（`news.py:328`）。视图化后，需要让 News 聚合 API 也支持"包含所有池成员"，否则用户加了 50 个池成员到自选视图，News 却只跟踪手动那 5 个。**这是 §4.1 必须连带改动的地方**。
6. **AI 流式聊天 + favorites**：`chat_service` / `useAIHelp` 在对话里直接引用自选股编号。如果虚拟视图上线，AI 应该看到"用户的所有关注（含来源）"，但短期内可以让 AI 仅看手动 favorites（保守起见）。
7. **合规 / 隐私**：自选股是用户行为数据；隐式 auto-add 涉及到"在用户没有明确同意的情况下记录了兴趣点"。在用户协议严格的场景（如香港券商合规），**视图化方案比 auto-add 更安全**——因为它不持久化"用户曾经看过 X"的额外证据。
8. **iOS / 移动端**：当前 `web/src/pages/Favorites/index.tsx` 是 web 端，平台还有 `ios/` 目录。视图化方案在移动端需要重新做折叠 UI；auto-add 方案反而对移动端"无感"（因为用户看不到细节），但这是**用体验差换工程便宜**，不值得。

---

## 6. 若采用 §4.1 方案，需要改的文件清单

> **以下仅为变更面估算，不在本次评估中执行。**

### 后端
- `app/models/favorite.py` — 加 `source` 列（nullable VARCHAR(50)），生成 alembic migration。
- `app/services/favorite_service.py`
  - `add_favorite` 增加 `source` 参数（默认 `"manual"`）。
  - 新增 `list_favorites_with_sources(username)` 方法，返回手动 + 各来源池成员的合并去重集合（UNION query）。
- `app/api/v1/favorites.py` — `/api/v1/favorites` 返回结构扩展，加 `by_source: { manual: [...], pool: {pool_id: [...]} }`。
- `app/api/v1/news.py:328` — News 聚合 endpoint 也使用合并后的集合（手动 + 池成员 UNION）。
- `app/api/v1/pools.py:107` — 新增 `POST /api/v1/pools/{pool_id}/add-all-to-favorites` 端点（带确认语义）。
- `app/api/v1/paper_trading.py` — 同上，新增强制同步端点（按账户、按 order、或按时间范围）。

### 前端
- `web/src/pages/Favorites/index.tsx`
  - 重构数据获取（按 source 分组）。
  - 加"来源"折叠面板，每组标注来源（池名 / 组合名 + 跳转链接）。
  - 在每个来源组里加"查看来源"按钮跳转到 Pool/Portfolio 详情。
  - 空状态文案改为："你还没有手动添加自选股。打开 [我的标的池]，一键把池成员推送到自选。"
- `web/src/pages/PoolDetail/index.tsx` — 在 PageHeader 加 "★ 添加全部到自选" 按钮。
- `web/src/pages/PaperTrading/index.tsx` — 在 Positions 表上方加 "★ 订阅所有持仓到自选" 按钮（弹窗确认）。
- `web/src/pages/Dashboard/index.tsx:369-400` — 调整 Dashboard "自选股动态" 卡片，让它显示手动 + 来源的两段，或者只显示手动（保守）。
- `web/src/api/favorite.ts` — 扩展 schema 字段。
- `web/src/types/favorite.ts` — 类型同步扩展。

### 测试
- `app/tests/news/test_news.py` — News 聚合测试加上"虚拟来源"的 case。
- 新增 `app/tests/test_favorite_sources.py` — 测试 source 字段、UNION 逻辑。
- `app/tests/test_pool.py:436` — 共享池成员在自选视图中的可见性测试。

### 文档
- `docs/dev-notes/20260707-系统平台功能逻辑说明手册.md` — 更新"自选股 / 标的池 / 组合"边界图。
- 用户手册 / FAQ 加一句："自选股页现在会合并显示你手动添加的标的 + 你订阅的池成员"。

### 数据迁移
- Alembic migration：给 `user_favorite` 加 `source VARCHAR(50) NULL`，老行 `source = NULL`（解释为 manual，向后兼容）。

---

## 7. 一句话总结

提案的动机是对的——用户确实希望"加进池的标的能跟住"——但**隐式写自选股的实现路径是错的**：它会让 `FavoriteService` 失去现有的"轻量 / 用户控制 / 与 Pool 解耦"语义，并且会在批量导入、AI 建池、共享池、跨用户场景里持续制造边角 bug。

**正确做法**是：保留自选股**独立** + 让自选股页面**按来源分组显示**（手动 vs 来自池 X / 组合 Y）+ 在 Pool / Portfolio 详情页提供**显式的一键推送按钮**。这样既缓解了用户的摩擦感，又不破坏数据语义边界。