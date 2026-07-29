# wechat2rss 三批（batch3）集成补丁说明

> 日期：2026-07-29
> 新模块：`app/services/news/sources/wechat2rss_batch3.py`（22 源，3 批次 `w3a`–`w3c`，每批 ≤8）
> 本文档给出主会话需要**串行**应用到 3 个共享文件的精确补丁。子 agent 未改动这些文件。
> 应用后 `app/tests/news/test_wechat2rss_batch3.py` 中 6 个 xfail 会自动转为通过（共 23 项全绿）。
> 达标数说明：目标 ≥40，两个公共镜像经三波开采后合格池枯竭，实收 **22**（实报不凑数，见 runbook §1/§4）。

---

## 1. `app/services/news/scheduler_jobs.py`

在二批 wechat2rss 段落（`WECHAT2B_BATCH_JOBS` 的 `globals()` 循环，约 520-521 行）之后、
`# ── Global multi-language RSS batches` 段落之前，插入以下完整代码块：

```python
# ── wechat2rss third-wave batches (added 2026-07-29) ──
#
# 22 more WeChat accounts — geo-economics / strategy / industry
# (consumer / gaming / finance-workplace) / tech commentary / depth
# journalism — all served by the bestblogs.dev public wechat2rss
# mirror (the xlab mirror's qualified pool was exhausted by waves
# 1/2; re-verified 2026-07-29, zero additions). Table, batching and
# job metadata live in
# app/services/news/sources/wechat2rss_batch3.py; evidence table in
# docs/dev-notes/20260729-wechat-batch3.md. The marketing filter
# stays on: this wave includes portal/weekly media where soft-ad
# posts do appear.


def _wechat3_batch_job(job_id: str, batch_key: str):
    """Build a ``run_*`` function crawling one third-wave wechat2rss batch."""

    @_record_etl(job_id)
    def _run() -> dict[str, int]:
        from app.services.news.filters import WechatMarketingFilter
        from app.services.news.sources.wechat2rss_batch3 import (
            Wechat2RssBatch3Crawler,
        )

        async def _go():
            crawler = Wechat2RssBatch3Crawler(batch_key)
            return await crawler.fetch_recent()

        try:
            articles = _run_async(_go())
        except Exception as exc:
            logger.exception("wechat2rss batch3 %s crawl failed: %s", batch_key, exc)
            return {
                "fetched": 0,
                "written": 0,
                "skipped": True,
                "skip_reason": f"crawl_error: {exc}",
            }

        if not articles:
            return {"fetched": 0, "written": 0, "skipped": True, "skip_reason": "no_articles"}

        try:
            marketing_filter = WechatMarketingFilter()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("wechat marketing filter init failed, passing through: %s", exc)
            marketing_filter = None

        filtered, rejected = _apply_marketing_filter(articles, marketing_filter)
        written = _write_to_db(filtered)
        return {
            "fetched": len(articles),
            "written": written,
            "rejected_marketing": rejected,
        }

    _run.__name__ = f"run_wechat3_{batch_key}_crawl"
    return _run


from app.services.news.sources.wechat2rss_batch3 import (  # noqa: E402
    WECHAT3_BATCH_JOBS,
)

for _job_id, _label, _batch in WECHAT3_BATCH_JOBS:
    globals()[f"run_wechat3_{_batch}_crawl"] = _wechat3_batch_job(_job_id, _batch)
```

注意点：
- 复用了同文件内已有的 `_record_etl` / `_run_async` / `_apply_marketing_filter` / `_write_to_db`，无需新增 import。
- 与一/二批共享 `WechatMarketingFilter`（LLM 判定结果有 24h 缓存，成本可控）。
- `WECHAT3_BATCH_JOBS` 定义在新模块内（与表同源，避免两处维护）；此处 import 并物化 job 函数。
- 函数名/批次键命名空间为 `wechat3_*` / `w3[a-c]`，与一批 `wechat2rss_*` / `a-i`、
  二批 `wechat2b_*` / `w2a-w2j`、独立源 `independent_*`、全球 RSS `global_rss_*` 均不冲突。

## 2. `app/core/scheduler.py`

在二批注册循环（`for job_id, label, batch in _news_jobs.WECHAT2B_BATCH_JOBS:` 块）之后插入：

```python
        # wechat2rss third-wave batches (2026-07-29) — generated in
        # ``scheduler_jobs.WECHAT3_BATCH_JOBS``, all hourly. jitter
        # spreads the three jobs away from the waves 1/2 ticks.
        for job_id, label, batch in _news_jobs.WECHAT3_BATCH_JOBS:
            fn = getattr(_news_jobs, f"run_wechat3_{batch}_crawl")
            scheduler.add_job(
                fn,
                trigger=IntervalTrigger(minutes=60, jitter=600),
                id=job_id,
                name=label,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
```

位置必须在 `try:` 块内（与一/二批同级的缩进），`except ImportError` 之前。
注意本批按任务要求使用 `IntervalTrigger(minutes=60, jitter=600)`（一/二批无 jitter，不 retroactively 改）。

## 3. `app/api/v1/news.py`

### 3a. `_WORKER_KEYWORDS`（`"wechat2b",` 之后）

```python
    "wechat2b",
    "wechat3_",
```

### 3b. `_WORKER_META`（二批 10 个 `news_wechat2b_*` 条目之后）

```python
    # wechat2rss third-wave batches (2026-07-29, 22 accounts)
    "news_wechat3_w3a_60m": {"label": "公众号三批 A 组 (8 号)", "schedule": "每 60 分钟"},
    "news_wechat3_w3b_60m": {"label": "公众号三批 B 组 (8 号)", "schedule": "每 60 分钟"},
    "news_wechat3_w3c_60m": {"label": "公众号三批 C 组 (6 号)", "schedule": "每 60 分钟"},
```

### 3c. `_WORKER_JOB_TO_SOURCE`

**不需要改动**。批次 job 写多个 source（每源 `wechat_{slug}`），与一/二批批次 job 一样不在该映射内
（该映射只服务单源 job 的 articles_24h 统计；批次 job 在健康面板按 etl_log 展示）。

## 4. 应用后验证清单

```bash
# 1. 单测全绿（23 项：17 通过 + 6 个原 xfail 转为通过）
poetry run pytest app/tests/news/test_wechat2rss_batch3.py -q

# 2. 批次 job 函数已生成
poetry run python -c "
from app.services.news import scheduler_jobs as sj
fns = [n for n in dir(sj) if n.startswith('run_wechat3_')]
print(len(fns), sorted(fns))
assert len(fns) == 3
"

# 3. 本地冒烟一个批次（真镜像，~15s）
poetry run python -c "
import asyncio
from app.services.news.sources.wechat2rss_batch3 import Wechat2RssBatch3Crawler
arts = asyncio.run(Wechat2RssBatch3Crawler('w3c', delay_seconds=0.5).fetch_recent())
print(len(arts), 'articles'); print(arts[0].source, arts[0].title[:30] if arts else '-')
"

# 4. 部署后：健康面板应出现 3 个 "公众号三批 X 组" 卡片；
#    etl_log 中 news_wechat3_w3a_60m 每小时一条 success。
```

## 5. 部署注意

- 无需新增环境变量、无需迁移、无需改动 wewe-rss。
- 全部 22 源挂在 bestblogs 镜像（`wechat2rss.bestblogs.dev`，BestBlogs 项目自建公共实例）：
  免费公共品，可用性不受我们控制。爬虫已带 2s inter-feed 礼貌延迟；若其失效，etl_log 会出现
  连续 failed，届时按 runbook §5 处理（下掉对应批次或替换镜像域名）。本批对 xlab 零依赖。
- `news_article.source_id` 已在迁移 `s5t7u9v1w3x5` 加宽到 500，镜像长 mp 链接安全。
- 本批只加 3 个每小时 job（jitter 600s 错峰），对 APScheduler 压力可忽略。

---

## 6. 集成执行记录（主会话，2026-07-29 23:10-23:20）

- ✅ §1-§3 三处补丁已全部应用（scheduler_jobs.py / scheduler.py / news.py `_WORKER_KEYWORDS` + `_WORKER_META`）
- ✅ `pytest test_wechat2rss_batch3.py`：23 项全绿（17 + 6 个原 xfail 转通过）
- ✅ `init_scheduler()` 实际运行验证：3 个 `news_wechat3_w3{a,b,c}_60m` job 注册成功
- ✅ commit `30b10dd` 已 push；Deploy run 30464645931 success（约 23:19 完成）
- ✅ ECS backend 容器内确认 3 job 已注册，首轮触发时间 2026-07-30 00:19~00:27（+08:00）
- ✅ ECS 冒烟 `w3a` 实抓 **80 篇 / 8 号全活**（每号 10 篇：地球知识局/南风窗/L先生/新牧尾笔/大李如山/星球研究所/非凡产研/游戏葡萄）
- ⏳ 首轮整点 etl_log 记录 + 健康面板 3 卡片待 00:30 后复核
- ⚠️ 注意：本机 SSH 用 `ssh ad-research`（~/.ssh/config 别名，root@47.239.13.111），
  直接 `ssh root@IP` 会 Permission denied；postgres 容器用户是 `etf` / 库 `ad_research`
