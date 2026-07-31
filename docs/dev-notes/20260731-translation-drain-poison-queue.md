# 2026-07-31 资讯翻译 drain 假死 — 毒丸行堵队列 + written 统计虚报

## 症状

用户报「为什么资讯还是没有中文翻译？」—— 详情页一篇韩文文章（source=global_nocutnews）标题和正文全是韩文，没有中文翻译。预期非中文文章自动获得中文翻译（至少 title_zh）。

## 根因（两个 bug 叠加，drain 假死多天）

### 数据证据

- `news_translate_10m` etl_log 每 tick `success / records_count=200`，看似健康。
- 但 `translation_generated_at` 实际新增翻译只有 ~200 篇/小时 ≈ 刚好覆盖新入库流量（~240/小时，且主要由 ingest 内联路径完成），**drain 对积压的贡献≈0**。
- 每 tick 耗时仅 15~68s —— 200 行 × 4 并发真翻译需要 ~600s，说明 tick 内几乎没有真实 LLM 调用。
- 复现 drain 的选取查询（`published_at DESC LIMIT 200`）：top-200 pending 里 **174 行 investing + 22 行 seekingalpha 是无正文行**（`body` 和 `full_content` 全空，title_zh 已有）——这些行永远不可能翻译正文。
- 积压：title_zh 缺失共 **18,710 行**（3-7 天 5,606 + >7 天 13,040），最近 24h 只有 17 行缺失（新文章由 ingest 路径即时翻译，掩盖了 drain 假死）。

### Bug 1：选取逻辑没有排除"永远翻译不了"的行（毒丸堵队列）

`scheduler_translate_news._pending_translation_ids` 只按 `title_zh IS NULL OR translated_zh IS NULL` 选取，`published_at DESC LIMIT 200`。无正文行（付费墙源 investing/seekingalpha 只入库标题）每 tick 稳定占据窗口顶部，**同一个 200 行批次被反复选中**，窗口后的 18.7k 真实积压永远进不了批次。drain 处于假死状态。

### Bug 2：written 统计把"缓存命中"计成"新翻译"（掩盖 Bug 1）

`auto_translate_for_ids` 旧逻辑 `result.get("translated") or result.get("title_zh")` 中，`title_zh` 键返回的是**缓存值**（`translate_title_if_needed` 对已翻译标题直接返回现值）——毒丸行每 tick 都被计为 translated=1，于是 etl_log 漂亮地显示 `written=200 success`，实际一篇没翻。监控完全失效。

### 次要：MiniMax 422 sensitive 无标记机制

后端日志 24h 内仅 6 次 `output new_sensitive (1027)` 错误，量小，但旧代码对这类**确定性失败**没有任何跳过机制 —— 同类毒丸日积月累会再次堵满窗口（6/天 → 约 33 天填满 200 窗口）。

## 修复（本地 commit，未 push）

1. **`app/services/news/scheduler_translate_news.py`**
   - `_pending_translation_ids`：新增两个守卫 —— (a) 正文翻译分支要求 `body`/`full_content` 至少一个非空（仅缺标题的行仍保留，标题总能翻）；(b) `translation_attempts < _MAX_TRANSLATION_ATTEMPTS(5)`。
   - `auto_translate_for_ids` 统计口径：只有 `translated`（新正文）或 `title_new`（新标题）才计入 `translated`。
   - `run_translate_pending` 返回键 `skipped` → `skip_count`：`_record_etl` 把真值 `skipped` 视为"整轮跳过"并清零 records_count，会再次隐藏真实进度。
2. **`app/services/news/translation_service.py`**
   - 新增 `_MAX_TRANSLATION_ATTEMPTS = 5` 和 `TranslationSensitiveError(RuntimeError)`；`_call_llm_with_retry` 检测错误消息含 `sensitive` 时抛该异常（确定性拒绝，不再静默返回 None）。
   - `auto_translate` 重写返回值契约：`translated`/`title_new` 只表示**本次新产出**；无事可做的行返回 `skipped=True, reason="nothing_to_do"`。
   - 新增 `_record_attempt_outcome`：失败 +1（sensitive 直接置 MAX），成功清零（给未来 stale 重翻留预算）。
3. **`app/models/news.py` + 迁移 `u7v9w1x3y5z7`**：`news_article.translation_attempts INTEGER NOT NULL DEFAULT 0`。
4. **测试** `app/tests/news/test_translation.py`：+9 个用例（选取守卫 ×5、计数器 ×3、返回值契约 ×2、sensitive 分类 ×2，其中聚合统计的旧用例按新契约更新）。

## 验证

- 翻译 42 测试全绿；news 目录 590 全绿；全量后端见 commit message。
- ECS 只读 SQL 模拟新 WHERE：pending 19,917 → 18,911（排除 ~1,006 无正文行）；新 top-200 窗口 **145/200 下一 tick 即可获得新中文标题**（修复前 0/200）。
- 预计 drain 速度 ~960 篇/小时（1200 产能 − 240 新流量），**18.7k 标题积压约 20 小时清完**，无需手动回填。

## 部署清单（push 后）

1. 部署会自动跑 `alembic upgrade head`（迁移 `u7v9w1x3y5z7`）——确认 backend 启动日志无迁移报错。
2. 观察 etl_log：`news_translate_10m` 的 `records_count` 应从恒 200 变为真实值（初期 100~200，随积压清空逐渐降到新流量水平 ~40/tick），`start_time` 间隔保持 10 分钟。
3. 验证 SQL：
   ```sql
   SELECT count(*) FROM news_article
   WHERE language NOT IN ('zh','cn','zh-cn','zh-hans','zh-hant','zh-tw','zh-hk')
     AND title_zh IS NULL;
   ```
   应每小时下降 ~960。一天后仍不降 → 查 backend 日志 `auto body translation failed`。
4. 被 sensitive 永久跳过的行：`SELECT source, count(*) FROM news_article WHERE translation_attempts >= 5 GROUP BY source` —— 量级小则接受，大则考虑换非敏感词供应商重翻（手动 `UPDATE ... SET translation_attempts=0` 复位）。

## 排障要点（下次类似问题）

1. **etl_log 的 records_count 是 job 自报的** —— 统计口径 bug 会让监控完全失真。排障第一步永远是拿独立数据源对账（这里是 `translation_generated_at` 的 hourly count）。
2. newest-first + LIMIT 的 drain 队列必须保证"选出来的都能被处理掉"，否则头部毒丸行会让整个队列假死。任何 drain 都要问：失败 N 次后怎么办？
3. tick 耗时是最便宜的健全性信号：200 行真翻译 ~600s vs 实际 15s，一眼假。
4. `_record_etl` 对返回 dict 的 `skipped` 键有特殊语义（整轮跳过、records 清零），job 返回dict 时不要用它装"跳过条数"。
