# 2026-07-29 资讯翻译 drain 吞吐修复（韩文文章无译文事件）

## 事件

生产详情页一篇 `global_nocutnews` 韩文文章标题/正文均为原文，无任何中文翻译痕迹。

## 根因（双因，均已修复）

1. **drain 吞吐饥饿（主因）**：`auto_translate_for_ids` 串行处理，每篇 title+body 两次 LLM 调用 ~12.6s，吞吐 ~285 篇/h；近 48h 非中文流入 ~240/h，且 tick 经常顶满 600s 预算（etl_log duration 多次 >600s）丢 tick，几乎无盈余清 backlog。`_pending_translation_ids` 按 `published_at desc` 取最新 50 篇，错过窗口的文章饥饿数天。实测积压：全历史非中文 25,972 篇中 title_zh 仅 6,003 / translated_zh 仅 5,116（backlog ~20k）；7-27 批次 8 篇 nocutnews 短文 2 天后仍未翻，而 7-29 11:48 新批次 15 分钟即翻——典型饥饿特征。
2. **30s 慢调用守卫丢弃已完成响应（次因）**：`translation_service._call_llm_with_retry` 在调用完成后 `elapsed > 30s` 即丢弃结果——token 已消耗、行未更新、下个 tick 重试再丢弃。MiniMax 在多 drain 并发时服务端排队，实测单次 30-160s，长文（10k+ chars 覆盖率仅 26% vs 短文 53%）被永久卡死。

## 已排除的非根因

- 正文翻译功能不存在 → 存在（`translated_zh`，2026-07-27 已支持全文 ≤30k 字符）。
- 语言检测漏韩语 → `language='ko'` 正常入库，drain 过滤正确。
- `ai_cleanup_status='failed'` 导致跳过 → drain 不过滤该字段；48h 仅 192 篇 failed 且 158 已有 title_zh。
- 详情页未渲染译文 → `web/src/pages/News/detail.tsx` 中文优先 + 中文/原文 Segmented 切换 + "翻译进行中"提示均已在位。
- drain 卡死 → etl_log 每 10 分钟 success。

## 改动

| 文件 | 改动 |
|---|---|
| `app/services/news/translation_service.py` | 30s 硬编码守卫 → `_MAX_LLM_CALL_SEC = 240.0`（覆盖实测 160s 上限 + 余量；SDK client timeout 兜底） |
| `app/services/news/scheduler_translate_news.py` | `auto_translate_for_ids` 改 ThreadPoolExecutor 并发（每任务独立 DB session，SQLAlchemy session 非线程安全）；预算耗尽停止提交、已提交任务跑完 |
| `app/config.py` | `news_translation_batch_size` 50→200；新增 `news_translation_concurrency = 4`（env `NEWS_TRANSLATION_CONCURRENCY`） |
| `app/tests/news/test_translation.py` | +4 个 `TestAutoTranslateForIds` 测试（stats 聚合/预算截断/worker 异常/空批与开关） |

无 alembic 迁移（无 schema 变更）。前端无改动。

## 验证

- `pytest app/tests/news/` 509 passed；`test_translation.py` 30 passed、`test_summary.py` 16 passed。
- 注意：测试 mock 时间时不能 patch 全局 `time.monotonic`（ThreadPoolExecutor 内部依赖），需替换被测模块的 `time` 引用。

## 部署后运维

- 无需手动回填：drain 自动 newest-first 清 ~20k backlog，预计 1-3 天（取决于 MiniMax 限流）；卡的 11 篇 nocutnews 会自动补上。
- 观察 etl_log `news_translate_10m` 的 records_count/duration；若 429 明显增多，将 `NEWS_TRANSLATION_CONCURRENCY` 降到 2-3。
- 成本：backfill ~20k 篇 ×（title ~0.2k + body ~4-8k tokens）≈ 一次性 80-160M tokens；稳态 = 每日流入 ~4.4-5.7k 篇。
- 若 MiniMax 排队成为瓶颈，可评估关闭 m3 think 模式（须先实测验证 API 参数存在，不要猜）。
