# 2026-07-31 评分排名只剩美股 — 全局 max 日期 vs 按市场日期不匹配

## 症状

用户报「评分排名只有美股个股，A股个股、ETF 去哪了？」——页面只剩 US 行，A股/CRYPTO 全消失。

## 根因（查询层 bug，每日复发的窗口期）

- 前端 `ScoreRanking` 调 `GET /api/v1/scores` 不带 `trade_date`。
- 后端 `ScoringService.get_scores`/`count_scores` 在未指定日期时取**全局** `max(trade_date)`。
- 写入侧 `calculate_daily_scores` 却是**按市场**各取最新指标日期计算：美股每晚收盘后推进，A股指标管道滞后约一天（7-30 的 A股指标实际 7-31 17:21 CST 才落库）。
- 于是每天美股日期超前（如 US=7-30、A股=7-29）到次日 A股指标补上前，全局 max=美股日期 → 查询只剩美股。**这是结构性每日窗口，不是一次性事故。**

## 修复（commit fb12896）

1. `app/services/scoring_service.py` 新增 `_latest_dates_by_market_subquery()`：按市场分组取各自最新评分日期；`get_scores`/`count_scores` 在 `trade_date is None` 时 join 该子查询（与写入侧对齐），输出补 `trade_date` 字段。
2. `app/api/v1/scoring.py` 响应级 `trade_date` 改为条目实际最新日期（多市场混合日期不再虚报全局 max）。
3. 回归测试 `test_get_scores_uses_latest_date_per_market`：A股 7-29 + 美股 7-30 场景两市场都必须出现。

## 验证

- 评分 36 测试全绿；全量后端 1194 passed（test_futures_pipeline 6 失败为既有问题，干净树复现，与本次无关）。
- ECS 等价 SQL 验证：修复后 A股 1550 + CRYPTO 22 + US 547（修复前仅 US 547）。
- 已在 ECS 手动触发一次 `run_score_calculation()`（幂等 UPSERT + redis 锁）：三市场评分全部推进到 2026-07-30，**线上即时恢复**；部署 fb12896 后窗口期不再复发。

## 排障要点（下次类似问题）

1. 先看写入侧和查询侧的"最新日期"语义是否一致——按市场写入 + 全局 max 查询是本类 bug 的温床。
2. A股指标管道天然滞后美股约一天，任何跨市场"取最新"的查询都要考虑这个时序差。
3. 验证手法：生产库直接 `SELECT market, max(trade_date), count(*) FROM etf_score GROUP BY market` 对比 API 返回。
