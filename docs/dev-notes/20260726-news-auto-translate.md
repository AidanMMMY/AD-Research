# 2026-07-26 资讯入库自动 AI 翻译（非中文 → 中文）

## 背景与目标

用户需求：非中文资讯（yahoo/cnbc/marketwatch/ft/coindesk 等英文源）**落库的同时就自动 AI 翻译成中文**，不需要用户点击触发；同时**保留原版英文内容**；前端要有体验优秀的双语呈现形式。

此前平台只有手动翻译：详情页 Switch「AI 译本并排显示」→ 调 `POST /news/{id}/translate`（DeepSeek/MiniMax），结果缓存到 `news_article.translated_zh`。问题：

1. 需要用户手动触发，绝大多数英文文章永远没有译文；
2. 只翻正文不翻标题，列表页仍是英文标题；
3. 并排双栏在移动端体验差。

## 方案总览

```
crawler tick → _write_to_db()
    → normalizer.normalize()        （落库，原文 title/body 不动）
    → fetch_full_content_for_ids()  （已有：抓全文，120s 预算）
    → auto_translate_for_ids()      （新增：标题+正文翻译，90s 预算）
                                       ↓ 预算耗尽/失败的留给 ↓
APScheduler news_translate_10m（每 10 分钟）
    → run_translate_pending()       （drain：最新优先，每批 15 篇，600s 预算）
                                       ↓ 同时渐进回填历史英文文章
```

### 存储模型（双语）

| 字段 | 内容 |
|---|---|
| `title` / `body` / `full_content` | **原文，永不被翻译流程修改** |
| `title_zh`（新增列） | AI 中文标题（入库时自动填充） |
| `translated_zh`（已有列） | AI 中文正文 |
| `translation_generated_at` | 正文译文时间戳 |

- alembic 迁移：`r4s6t8u0v2w4_add_news_title_zh.py`（down_revision `q3r5s7t9u1v2`）
- 待翻译判定：`language NOT IN (zh 语系) AND (title_zh IS NULL OR translated_zh IS NULL)`——NULL 即待办，无需状态列

### 语言门

从「仅 `language == 'en'`」放宽为「所有非中文」。中文判定集合：
`zh / cn / zh-cn / zh-hans / zh-hant / zh-tw / zh-hk`（`is_chinese_language()`）。
未知/空语言按非中文处理（英文 RSS 源常不设 language，翻了无害，不翻才是问题）。

### 关键文件

| 文件 | 改动 |
|---|---|
| `app/services/news/translation_service.py` | 新增 `is_chinese_language()`、`_TITLE_TRANSLATION_SYSTEM`、`translate_title_if_needed()`、`auto_translate()`（**绝不抛异常**，爬虫写路径安全）；`translate()` 顺带补标题 |
| `app/services/news/scheduler_translate_news.py`（新） | `auto_translate_for_ids()`（ingest 钩子，时间预算内逐篇翻）+ `run_translate_pending()`（drain + 回填） |
| `app/services/news/scheduler_jobs.py` | `_write_to_db()` 在全文抓取后调用翻译钩子；新增 `run_translate_pending_job`（`@_record_etl("news_translate_10m")`） |
| `app/core/scheduler.py` | 注册 `news_translate_10m`（10 分钟，`max_instances=1`） |
| `app/config.py` | `news_translation_on_ingest`(true) / `news_translation_ingest_time_budget_sec`(90) / `news_translation_batch_size`(15) |
| `app/api/v1/news.py` | `_serialize_article` + event-signals 增加 `title_zh`；`_WORKER_META` 登记新 job |
| `app/models/news.py` | `title_zh` 列 |

### 前端 UX（设计决策）

**默认中文优先，原文一键可达**——替代原「并排双栏」：

- **列表页**（News/index.tsx）：标题渲染 `title_zh ?? title`；有译文时标题旁显示小「译」徽章（accent-dim 底色，10px），hover Tooltip 显示英文原标题
- **详情页**（News/detail.tsx）：
  - 标题：中文译文为主标题，英文原标题以 14px 灰色副标题形式置于下方（`.ad-detail-title__original`，读起来是出处而非第二标题）
  - 正文上方新增语言工具条（`.news-lang-toolbar`）：`Segmented [中文译文 | EN 原文]` 全文切换 + 右侧「AI 翻译 · 时间戳」
  - 默认选中「中文译文」；译文未就绪时**不出现空窗**——显示原文 + 顶部细条提示「中文译文尚未就绪，后台翻译中」+「立即翻译」按钮（触发原有手动 translate mutation 作兜底）
  - 切到「原文」时标题同步切回英文
  - `document.title` 同样中文优先
- 移除并排双栏视图及其 CSS（`.news-translation-pair*`，含移动端 override）

## 运维要点

- ** drain 任务即回填**：部署后 `news_translate_10m` 每 10 分钟自动按最新优先回填历史未翻译英文文章（每批 15 篇），无需手工脚本。想加速可临时调大 `news_translation_batch_size` 或手动执行：
  ```bash
  docker exec etf-backend python -c \
    "from app.services.news.scheduler_translate_news import run_translate_pending; print(run_translate_pending(50))"
  ```
- **健康页**：NewsHealth worker 网格新增「资讯自动翻译」行；ETLLog job_name=`news_translate_10m`
- **失败重试**：翻译失败不写字段（保持 NULL），下一 tick 自动重试，天然幂等
- **关闭开关**：`NEWS_TRANSLATION_ON_INGEST=false` 关闭入库即翻（drain 仍在跑）；drain 批量由 `NEWS_TRANSLATION_BATCH_SIZE` 控制
- **LLM**：走 `get_llm_provider()`（生产 MiniMax）。标题与正文各一次调用，标题 prompt 要求单行输出（服务端再兜底取第一行）
- **手动端点保留**：`POST /news/{id}/translate` 行为不变（现在顺带补 title_zh），作为老文章/失败的兜底；429/409/502 语义不变

## 部署步骤

1. `git push` 后 ECS `git pull`
2. `docker exec etf-backend alembic upgrade head`（应用 `r4s6t8u0v2w4`）
3. 重建 backend 镜像 + 前端 dist（dist 需 `npm run build` 后 docker cp 或镜像重 build）
4. 重启 backend（APScheduler 注册新 job）
5. 验证：找一篇新英文文章 → 详情页默认中文；`/news/health` worker 网格出现「资讯自动翻译」

## 测试

- `app/tests/news/test_translation.py`：22 个测试全绿（含新增 `TestAutoTranslate` 5 个：标题+正文填充 / 中文跳过 / 缺失文章 / LLM 失败不留残态 / 无正文仅标题）
- 2 个旧测试断言从 `call_count == 1` 更新为 `== 2`（标题+正文两次调用，行为变更有意为之）
- 前端 `tsc --noEmit` + `npm run build` 通过
