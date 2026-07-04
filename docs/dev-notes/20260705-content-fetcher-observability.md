# 2026-07-05 — ContentFetcher AI 清理可观测性 (M22-3)

## 背景

`ContentFetcher._clean_with_ai`（`app/services/news/content_fetcher.py`）之前有
"假装成功" 的静默降级问题：

- 任何 LLM 异常都被 `except Exception: return content` 吞掉；
- `DeepSeekProvider.is_available=False` 时直接 return 原始 Jina markdown；
- `max_tokens` 太短 / 返回 <100 字符也被静默丢弃；
- scheduler 仍写 `success=N failed=0`，前端不知道 AI 没工作。

第一阶段 (commit `9f5a78b`) 已经把模型切到 `deepseek-v4-flash`。
本阶段 (M22-3) 在不动 LLM 调用本身的前提下，把"AI 没工作"这件事
做成**线上可见** + **有数据可查** + **有告警能跳**。

## 设计决策

### 1. 新增 2 列，不动现有字段

`news_article` 表新增：

| 列 | 类型 | 默认 | 含义 |
| --- | --- | --- | --- |
| `ai_cleaned_at` | `TIMESTAMPTZ NULL` | `NULL` | 上次 AI 清理尝试时间 |
| `ai_cleanup_status` | `VARCHAR(16) NULL` | `NULL` | 枚举 `cleaned` / `skipped` / `failed` / `not_attempted` |

**字段默认值 = NULL，不设 `DEFAULT 'not_attempted'`** —— 让 `NULL` 明确
表示"scheduler 没去 fetch 这篇"，跟"fetch 了但 AI 没工作"区分开。

加索引 `ix_news_article_ai_cleanup_status`，方便 ops 跑
`WHERE ai_cleanup_status = 'failed'` 报警查询。

### 2. 三种 AI 路径全部写状态

`_clean_with_ai` 重构成返回 `(cleaned_text, status)`：

| 路径 | 触发条件 | status | 落库 |
| --- | --- | --- | --- |
| 成功 | DeepSeek 返回 ≥100 字符 | `cleaned` | LLM 输出 |
| 跳过 | `is_available=False` | `skipped` | 原始 Jina |
| 失败 | DeepSeek 抛异常 / 返回 <100 字符 | `failed` | 原始 Jina |

失败路径**带 `exc_info=True`** 记 stack trace，方便排障（之前的
`logger.warning("... %s", e)` 丢栈）。

### 3. 健康检查加聚合

`GET /api/v1/news/health` 新增 `ai_cleanup_24h` block：

```json
{
  "ai_cleanup_24h": {
    "total": 1234,
    "cleaned": 1100,
    "skipped": 100,
    "failed": 30,
    "cleaned_pct": 97.3,
    "alert_threshold_pct": 70.0,
    "alert": false
  }
}
```

阈值通过 `news_ai_cleanup_alert_pct` 环境变量配置（默认 70.0）。
**`cleaned_pct` 的分母只算 `cleaned + failed`，跳过 `skipped`** —
DeepSeek 完全没配置的本地环境不应该报警。

### 4. 前端三条 Alert

`pages/News/detail.tsx` 在正文上方加条件 antd `Alert`：

| 状态 | 颜色 | 文案 |
| --- | --- | --- |
| `failed` | red (error) | "AI 清理失败，DeepSeek 调用异常" |
| `skipped` | blue (info) | "该篇未经 AI 清理，DeepSeek 当前不可用" |
| `null` / `not_attempted` | yellow (warning) | "该篇尚未抓取正文" |
| `cleaned` | — | 不显示（默认） |

`pages/NewsHealth/index.tsx` 加 `AI 清理 (近 24h)` 卡片：

- 4 个 `Statistic`：已清理 / 跳过 / 失败 / 清理成功率
- 当 `alert=true` 时，顶部多一条红色 `Alert`："AI 清理失败率过高"

### 5. 类型 + 测试

- `web/src/types/news.ts`：`NewsArticle` / `NewsHealthResponse`
  加可选字段（前端 `?` 兼容）。
- `app/tests/news/test_content_fetcher.py` 加 6 个测试：
  3 个 AI path (cleaned / skipped / failed) + 1 个 short-body 边界 +
  1 个 dict 透出 + 1 个 health endpoint。

## 文件清单

### 新增
- `alembic/versions/2026_07_05_add_ai_cleanup_obs.py` — alembic 迁移 (≤32 字符)
- `docs/dev-notes/20260705-content-fetcher-observability.md` — 本文档

### 修改
- `app/models/news.py` — `NewsArticle` 加 2 列
- `app/config.py` — `news_ai_cleanup_alert_pct: float = 70.0`
- `app/services/news/content_fetcher.py` — `_clean_with_ai` 重构 + 状态写回
- `app/services/news/scheduler_fetch_full_content.py` — 加 `ai_cleaned/ai_skipped/ai_failed` 计数
- `app/api/v1/news.py` — `_article_to_dict` 透出 2 字段 + health 加 `ai_cleanup_24h`
- `web/src/types/news.ts` — 类型补字段
- `web/src/pages/News/detail.tsx` — AI cleanup Alert banner
- `web/src/pages/NewsHealth/index.tsx` — admin 24h 卡片
- `app/tests/news/test_content_fetcher.py` — 6 个新测试

## 验证

### 本地 (开发机)

```bash
alembic upgrade head && alembic downgrade -1 && alembic upgrade head
# INFO [alembic.runtime.migration] Running upgrade ... -> 2026_07_05_add_ai_cleanup_obs, add ...
# INFO [alembic.runtime.migration] Running downgrade ... -> ..., add ...
# INFO [alembic.runtime.migration] Running upgrade ... -> 2026_07_05_add_ai_cleanup_obs, add ...

python -m pytest app/tests/news/ app/tests/test_news_dedup.py
# ================= 246 passed, 50 warnings in 75.83s ==================
```

### 全量 pytest

新闻相关 246 个测试全过。其他目录（paper_trading / risk_control /
attribution）的失败是 `2026_07_05_add_user_id_to_8_business_tables` 引
起的 `paper_trade_account.user_id NOT NULL` 约束问题 + paper_trading
service 测试自己的 `provider` mock 问题，**与本 PR 无关**，会在另一
个 sprint 里修。

## 回滚步骤

如果线上发现 bug，按以下顺序回滚：

### 1. 回退代码

```bash
git revert <commit_hash>   # 撤销整个 PR
# 或更精准：
git revert -n <commit_hash>
git reset HEAD
# 手动保留 alembic 迁移 (见下方)
```

### 2. 回退 schema (如果上一步保留了 alembic 文件)

```bash
alembic downgrade -1
# INFO [alembic.runtime.migration] Running downgrade
#   2026_07_05_add_ai_cleanup_obs -> 2026_07_05_add_user_id_to_8_business_tables
```

### 3. 如果只想回滚代码不改 schema

- `git checkout HEAD~1 -- app/services/news/content_fetcher.py app/services/news/scheduler_fetch_full_content.py app/api/v1/news.py app/models/news.py app/config.py`
- alembic 迁移保留（列还在但没人写），不会有副作用
- 前端回退 `git checkout HEAD~1 -- web/src/types/news.ts web/src/pages/News/detail.tsx web/src/pages/NewsHealth/index.tsx`

## 与第一阶段的关系

| commit | 内容 |
| --- | --- |
| `9f5a78b` | 模型 `deepseek-v4-pro` → `deepseek-v4-flash` (修真模型名) |
| `9224db9` | **本 PR**: 加 ai_cleanup 状态字段 + 前端 Alert + 健康聚合 + 告警 |

第一阶段解决"模型名是假的"问题，第二阶段解决"AI 失败没人知道"
问题。两者独立，可以单独回滚。
