# 2026-07-27 资讯源扩容 +13 独立英文源 / wewe-rss 公众号设施 / APScheduler misfire P0

> 关联：`docs/dev-notes/20260726-news-auto-translate.md`（AI 翻译部署与两个生产坑）
> 提交：`17aea40`（13 源 + wewe-rss）、`076452a`（misfire P0）、`930d3b9`（stale 重翻）

---

## 1. 本次交付内容

### 1.1 新增 13 个独立英文资讯源

全部走 `SimpleRssCrawler` 子类（`app/services/news/sources/rss_simple.py`），统一 `market="us"`、`language="en"`，落库后自动进入全文抓取 + AI 翻译管线。

| 源 | 作者/定位 | slug | 调度 |
|---|---|---|---|
| Wolf Street | Wolf Richter，金融/地产/央行 | `wolfstreet` | 30m |
| Calculated Risk | Bill McBride，宏观/地产数据 | `calculatedrisk` | 30m |
| A Wealth of Common Sense | Ben Carlson，资管/行为金融 | `awealthofcommonsense` | 30m |
| Of Dollars and Data | Nick Maggiulli，数据化个人理财 | `ofdollarsanddata` | 30m |
| Marginal Revolution | Tyler Cowen，经济学博客 | `marginalrevolution` | 30m |
| The Big Picture | Barry Ritholtz，市场评论 | `ritholtz` | 30m |
| Net Interest | Marc Rubinstein，金融机构深度 | `netinterest` | 60m |
| Doomberg | 能源/工业匿名深度 | `doomberg` | 60m |
| Apricitas | Joey Politano，美国经济数据 | `apricitas` | 60m |
| Noahpinion | Noah Smith，经济/科技评论 | `noahpinion` | 60m |
| Econbrowser | James Hamilton，宏观计量 | `econbrowser` | 60m |
| The Overshoot | Matt Klein，全球宏观 | `theovershoot` | 60m |
| Quantpedia | 量化策略研究聚合 | `quantpedia` | 120m |

**注意**：Substack 自定义域名会 301（`xxx.substack.com/feed` → `netinterest.co`、`newsletter.doomberg.com`、`apricitas.io`、`noahpinion.blog`），feed URL 直接写最终域名。`BaseCrawler` 已 `follow_redirects=True`，但写最终 URL 省一跳。

### 1.2 工厂模式注册调度

`app/services/news/scheduler_jobs.py`：

- `INDEPENDENT_RSS_JOBS` 表（job_id → crawler 类路径）
- `_simple_rss_job(job_id, crawler_class_path)` 工厂生成模块级函数并 `globals()` 物化——`app/core/scheduler.py` 循环注册，**加新源只需往表里加一行**
- health worker 网格（`app/api/v1/news.py`）同步加了 13 个 `_WORKER_META` + `_WORKER_JOB_TO_SOURCE` 映射

### 1.3 wewe-rss 公众号基础设施

`deploy/aliyun-ecs/docker-compose.yml` 新增 `wewe-rss` 服务（`cooderl/wewe-rss-sqlite:latest`）：

- 容器名 `alloyresearch-wewe-rss`，SQLite 存储，无需额外 DB 容器
- 管理 UI 只绑 `127.0.0.1:4000`（不暴露公网）
- backend 通过 `WECHAT_RSS_BASE_URL`（默认 `http://wewe-rss:4000`）+ `WECHAT_RSS_FEED_MAP`（`feed_id:slug:display_name,...`）对接
- 当前已用 `docker run` 手动起了一个同名容器，下次 deploy 时 compose 会直接 adopt

---

## 2. P0：APScheduler misfire_grace_time 默认值导致全站定时任务静默丢 tick

### 2.1 现象

用户反馈"翻译已部署但前端看不到中文"。排查发现：

- `news_translate_10m`、`news_full_content_10m`、`sentiment_batch_30s`、`news_article_categorization_1m` 以及 7-21 上线的十余个 RSS 源，**在 `etl_log` 里一行记录都没有**——从未执行过一次
- 仅 ingest 内联路径翻译了 13 篇（非中文文章覆盖 0.09%）
- backend 日志里有大量 `Run time of job ... was missed by` misfire 记录

### 2.2 根因

APScheduler 3.x `misfire_grace_time` **默认 1 秒**。平台 ~45 个 interval job 全部对齐 5/10 分钟边界（同一秒触发），调度线程按注册顺序逐个处理 due job，排到 1 秒以后的 job 被判定 misfire **静默丢弃**——每个 tick 都如此，永远轮不到后注册的 job。

### 2.3 修复

`app/core/scheduler.py`：

```python
scheduler = BackgroundScheduler(
    executors={"default": ThreadPoolExecutor(max_workers=5)},
    job_defaults={"misfire_grace_time": 300, "coalesce": True},
)
```

- `misfire_grace_time=300`：拥挤 tick 允许迟到 5 分钟执行，而不是永久丢弃
- `coalesce=True`：多次错过合并为一次执行，防积压雪崩

### 2.4 部署后验证（ECS）

- `news_translate_10m` 首次 etl_log 记录：17:04:48 UTC，`success`，15 条/批
- 翻译计数从 21/17 涨到 56/42 并持续增长
- 因积压 ~1.39 万非中文文章，按 15 条/10 分钟需 ~6 天消化；已用 `docker exec -d` 起了一个 6 小时批量 drain（日志 `/tmp/translate_bulk_drain.log`，在容器内）加速

### 2.5 批量 drain 手动操作（备查）

```bash
ssh ad-research
docker exec -d alloyresearch-backend python -c "
import time, json
from app.services.news.scheduler_translate_news import run_translate_pending
deadline = time.time() + 6*3600
total = 0; rounds = 0
with open('/tmp/translate_bulk_drain.log', 'w') as f:
    while time.time() < deadline:
        r = run_translate_pending(batch_size=15)
        rounds += 1; total += r.get('written', 0)
        f.write(json.dumps({'round': rounds, 'result': r, 'total_written': total}) + '\n')
        f.flush()
        if r.get('fetched', 0) == 0: break
        time.sleep(20)
"
# 查看进度
docker exec alloyresearch-backend tail -3 /tmp/translate_bulk_drain.log
```

---

## 3. 微信公众号接入（双通道）

### 3.1 通道 A：wechat2rss 公共镜像（已上线，无需扫码）✅

排查发现候选 10 个独立号中有 2 个已被公共索引服务
[wechat2rss](https://wechat2rss.xlab.app)（免费列表 ~300 个号）收录，
直接以标准 RSS 接入（commit `b31fc0c`）：

| 公众号 | source | feed | 调度 |
|---|---|---|---|
| 猫笔刀 | `wechat_maobidao` | `wechat2rss.xlab.app/feed/33d986…81.xml` | 60m |
| 思想钢印 | `wechat_sixianggangyin` | `wechat2rss.xlab.app/feed/a55006…2ea.xml` | 60m |

特点：`description` 为空、全文在 `content:encoded`，
`parse_rss_items` 原生优先取 `content:encoded`，无需特殊处理；
中文内容直接进库，不走翻译管线。2026-07-27 部署冒烟：
两源各 20 篇落库，正文 1600-4500 字全文。

**风险**：公共服务，可用性不受我们控制；失效时 etl_log 会出现
连续 failed，届时把对应 job 下掉或迁移到通道 B。

### 3.2 通道 B：自建 wewe-rss（等用户一次性扫码）

其余 8 个候选号（智谷趋势 / 远川研究所 / 沧海一土狗 / 付鹏的财经世界 /
李迅雷金融与投资 / 聪明的投资者 / 宁南山 / 晚点LatePost）**不在**
wechat2rss 免费列表，必须走自建 wewe-rss：

1. 用户本地开隧道：`ssh -L 4000:localhost:4000 ad-research`
2. 浏览器打开 `http://localhost:4000/dash`，用微信扫二维码登录微信读书
3. 在管理页添加公众号，记录每个号的 `feed_id`
4. 在 ECS `/data/ad-research/deploy/aliyun-ecs/.env` 追加：
   ```
   WECHAT_RSS_FEED_MAP="feed_id_1:wechat_zhigu:智谷趋势,feed_id_2:wechat_yuanchuan:远川研究所,..."
   ```
5. `docker restart alloyresearch-backend`，验证 `etl_log` 出现
   `news_wechat_zeping_15m` 成功记录且 `wechat_{slug}` 源落库

后端采集代码（`wechat_zeping.py` + feed_map 逐 feed 分发）已就绪，
扫码后纯配置接入，无需改代码。

> feeddd 已于 2023 年关闭，不要再用；wechat2rss 付费版可自定义订阅，
> 是通道 B 之外的备选（要花钱，优先自建）。

---

## 4. 排障速查

| 症状 | 查法 | 处理 |
|---|---|---|
| 新源不落库 | `SELECT * FROM etl_log WHERE job_name='news_xxx_30m' ORDER BY start_time DESC;` | 无记录→检查 scheduler 注册；有 error→看 error_msg |
| 翻译不涨 | `etl_log` 里 `news_translate_10m` 是否每 10 分钟一条 success | 无记录→misfire 复发（检查 `misfire_grace_time`）；有记录但 written=0→查 MiniMax key/余额 |
| 译文是旧摘要 | `full_content_fetched_at > translation_generated_at` | stale 检测会自动 force 重翻，drain 一轮即修复 |
| 前端看不到中文 | 文章 `title_zh`/`translated_zh` 是否有值 | 有值→前端缓存/nginx；无值→翻译管线问题，往上查 |

---

## 5. 决策日志

- **工厂模式注册 RSS job**：13 个源若各写一段 `def run_xxx():` 会让 scheduler_jobs.py 膨胀且极易漏注册；表驱动 + `globals()` 物化保证"加表即注册"。
- **misfire 300s 而非更长**：5 分钟足够消化最坏情况的对齐抖动；给太长会在 backend 重启前把大量过期 job 补跑，拖慢启动。
- **手动 docker run 起 wewe-rss 而不等 deploy**：compose 文件已含服务定义，容器名一致，下次 deploy compose 会直接接管，无需手动迁移。
