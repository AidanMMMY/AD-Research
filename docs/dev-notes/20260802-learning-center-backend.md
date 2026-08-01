# 学习中心后端（方案 B MVP）落地 — 2026-08-02

> 背景：分析文档（learning-section-analysis，2026-08-01）推荐方案 B——把 `/learning` 扩建为学习中心。本 runbook 记录**后端部分**的落地：news_source_meta 表 + 239 源打标种子 + wechat category 接通 + `/learning/feed` & `/learning/topics` API。前端知识 feed 区另案。
> 未 commit / 未 push（等用户确认）。

## 1. 数据层：news_source_meta 表

- 模型：`app/models/news_source_meta.py`（`NewsSourceMeta`）
  - `source` String(200) PK —— 与 `news_article.source` 对齐
  - `content_type` String(20) —— `deep`（深度分析/研究）| `edu`（科普教育）；快讯源不打标、不入库
  - `topic` String(40) 可空 —— `allocation` / `valuation` / `macro` / `industry` / `psychology` / `tools` / `research`（兜底深度类）
  - `difficulty_default` String(10) 可空 —— `beginner` / `advanced`；NULL=混合/不确定
  - `display_group` String(60)、`note` String(200) 可空（运营维护用，note 统一放源显示名）
- 迁移：`alembic/versions/w4x6y8z0a2b4_add_news_source_meta.py`，down_revision=`v3w5x7y9z1a3`，upgrade/downgrade 往返已验证（dev Postgres）。**迁移只建表不灌数据**。
- 已登记：`app/models/__init__.py` re-export + `alembic/env.py` import。
- 设计约束：不改 `news_article` 结构、不回填历史数据——API 层 join（feed 只看近 N 天）。

## 2. 种子数据：239 源打标

- 文件：`app/services/news/source_meta_seed.py`（`SOURCE_META_SEED` list[dict] + `seed_source_meta(db)` 幂等函数——先查已有主键再插缺失行，等价 ON CONFLICT DO NOTHING，Postgres/SQLite 通吃，不覆盖运营手改）。
- 手动入口：`scripts/seed_news_source_meta.py`（`--dry-run` 只打印分布）。
- 打标规则：**宁可保守**，拿不准不打标；打标基于批次表源名/备注的常识判断。wechat batch2/3 行内 category 映射：macro→macro、strategy→valuation、industry→industry、tech/business→research/industry 酌定。
- 分布：

| 维度 | 分布 |
|---|---|
| content_type | deep 167 / edu 72 |
| topic | allocation 63 / macro 55 / research 49 / industry 47 / valuation 20 / psychology 5 / tools 0 |
| difficulty | beginner 73 / advanced 56 / NULL 110 |

- 覆盖：wechat×3 批次 + wewe-rss 8 账号（zhigu/yuanchuan/canghai/fupeng/lixunlei/congming/latepost，beiwei 性质不明跳过）+ zhx 播客 26 + zhb 3 + indie 34 + gind 33 + global 18 + asen 35 + rss_simple 16。独立爬虫（新华/财联社/华尔街见闻/SEC/cninfo…）全快讯不打标；en_fin/official/zh_media 三批（扩源冲刺在跑）本次未纳入，后续可补。
- **防手滑**：测试 `test_seed_sources_exist_in_batch_tables` 断言每个种子 slug 都能在批次表/rss_simple/wewe-rss 已知账号里找到——新增种子必须先过此测试（打错 source 则 join 永远为空）。

## 3. wechat category 接通落库

- 此前 batch2/3 行内 category 只在表里做文档用途（"not persisted"）。本次接通：`rss_common.parse_rss_items` 新增 `default_category` 参数（条目自带 `<category>` 优先，否则回落源级分类），batch2/3 crawler 传 `default_category=feed.category` → `RawArticle.extra["category"]` → `normalizer._derive_category` 已认 → `news_article.category`。两个 crawler 的 docstring 已同步。
- 新文章入库即带 macro/strategy/industry/tech/business 标签；历史数据不回填。

## 4. API

- 路由：`app/api/v1/learning.py`，注册于 `app/main.py`（prefix `/api/v1/learning`，JWT 必填）。
- `GET /learning/feed`：参数 `topic` / `content_type` / `days`(默认90,≤365) / `page` / `page_size`；`news_article` JOIN `news_source_meta`，只返回打标源近 N 天文章；排序 `importance DESC NULLS LAST, published_at DESC`；响应结构与 `/news` 列表一致（items/page/page_size/total/total_pages + days），列表项复用 `_article_to_dict` 并附加 `importance` / `content_type` / `topic` / `difficulty_default`。非法 topic/content_type 返回 400。
- `GET /learning/topics`：各主题近 `days` 天计数；返回全部 7 主题（零计数也返回，Tab 列表稳定）+ total。

示例（`GET /api/v1/learning/feed?topic=macro&page_size=2`）：

```json
{
  "items": [
    {
      "id": 12345, "source": "wechat_zepinghongguan", "source_id": "...",
      "url": "https://mp.weixin.qq.com/s/...", "title": "...",
      "title_zh": null, "summary_zh": "……", "importance": 4,
      "content_type": "deep", "topic": "macro", "difficulty_default": null,
      "published_at": "2026-08-01T12:00:00+00:00", "market": "cn_a",
      "symbols": [], "...": "（其余字段与 /news 列表项一致）"
    }
  ],
  "page": 1, "page_size": 2, "total": 137, "total_pages": 69, "days": 90
}
```

`GET /api/v1/learning/topics` →

```json
{
  "days": 90,
  "topics": [
    {"topic": "allocation", "count": 812},
    {"topic": "valuation", "count": 153},
    {"topic": "macro", "count": 137},
    {"topic": "industry", "count": 220},
    {"topic": "psychology", "count": 18},
    {"topic": "tools", "count": 0},
    {"topic": "research", "count": 305}
  ],
  "total": 1645
}
```

## 5. 测试

- `app/tests/news/test_learning_feed.py`（23 个）：模型 CRUD、种子合法性/唯一性/slug 存在性/幂等、feed 过滤（未打标源不出现、90 天窗口、topic/content_type、非法参数 400）、importance 优先排序、分页、topics 计数（含零计数主题）、wechat category 链路（parse_rss_items default_category 回落/条目优先/crawler 传参/_derive_category 末端）。
- `poetry run pytest app/tests/news/ -q` → **776 passed**（含既有 753，无回归）。

## 6. 部署 / 后续 TODO

1. ECS 部署后：`alembic upgrade head` 建表 → `python3 scripts/seed_news_source_meta.py` 灌种子（幂等，可重复跑）。
2. 前端 `/learning` 知识 feed 区（主题 Tab + 复用 NewsCard 模式）另案，是前端主要工作量。
3. 运营调整归类：直接 SQL UPDATE `news_source_meta` 即可，种子函数不会覆盖已有行。
4. en_fin（enf_*）/ official（ofc_*）/ zh_media（zhm_*）三批新源后续可补打标（多为快讯/行业新闻，预计增量小）。
