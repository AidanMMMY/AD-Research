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

### 3.3 公众号规模化：100 个源达成（2026-07-27 晚）

/goal「公众号扩充不少于 100 个，大半独立」的执行记录。最终 **100 个公众号源**：

| 通道 | 数量 | 内容 |
|---|---|---|
| wewe-rss 自建（用户扫码） | 8 | 智谷趋势/远川研究所/沧海一土狗/付鹏的财经世界/李迅雷金融与投资/聪明投资者/北纬的日常/晚点LatePost |
| wechat2rss 单 feed | 2 | 猫笔刀、思想钢印 |
| wechat2rss 批量表 | 90 | 财经/商业/科技/地缘/独立随笔，见 `wechat2rss_batch.py` 的 `WECHAT2RSS_FEEDS` |

**wewe-rss 8 个号的接入流程**（实际执行版）：

1. AuthCode：wewe-rss 未显式设置时为默认 `123567`（官方文档未写，实测）。
2. tRPC API（dash 前端走的协议，可直接 curl）：
   - `POST /trpc/platform.getMpInfo?batch=1`，body `{"0":{"wxsLink":"<文章URL>"}}`，
     header `Authorization: 123567` → 返回 `{id: MP_WXS_*, name, cover, intro, updateTime}`
   - `POST /trpc/feed.add?batch=1`，body `{"0":{id,mpName,mpCover,mpIntro,updateTime,status:1}}`
   - `POST /trpc/feed.refreshArticles?batch=1`，body `{"0":{"mpId":"MP_WXS_*"}}`
3. **wewe-rss 代理（weread.111965.xyz）会抖动**：同一 MP 的文章接口
   时而有数据时而 `[]`（微信读书限流），刷新要多轮重试，容器自带
   CRON `35 */1 * * *` 会兜底。
4. feed.add 需间隔 10s+（README 明确警告添加过频会被封控 24h）。
5. 后端接入：`.env` 写 `WECHAT_RSS_FEED_MAP="feed_id:slug:显示名,..."`，
   **改 env 必须 `docker compose up -d backend` 重建容器**（restart 不重读 env）。
6. 手动 docker run 起的 wewe-rss 容器，compose 默认 URL 是
   `http://wewe-rss:4000`（服务名），需
   `docker network connect --alias wewe-rss <network> alloyresearch-wewe-rss`
   加别名；已处理，compose 文件含服务定义后下次 deploy 自动 adopt。

**事故记录（改 env 重建 backend 引发）**：`docker compose up -d backend`
同时重建了 postgres 连接配置，新容器 DB 认证失败
（DB 密码是数据卷初始化时的旧值，与当前 .env 的占位密码不一致）。
修复：进 postgres 容器执行
`ALTER USER etf WITH PASSWORD '<.env 里的 POSTGRES_PASSWORD>'` 对齐。
**教训：ecs 上 .env 密码与 DB 实际密码可能漂移，改容器前先看
`docker inspect alloyresearch-postgres` 的创建时间与 .env 修改时间。**

**wechat2rss 批量（90 号）设计**：
- 表驱动 `WECHAT2RSS_FEEDS`（slug/显示名/feed_hash），9 个批次 job
  （a-i，每批 ~11 号）而非 90 个 job——避免重蹈 misfire P0 的对齐拥挤。
- 选号规则：独立发声（无官媒/政府/企业 PR），财经/商业/科技/地缘优先，
  安全类仅保留地缘价值号（威胁棱镜/APT观察等）。
- 复用营销过滤器（`WechatMarketingFilter`）。

**挖掘失败记录**：曾尝试从已入库公众号正文中正则提取出链
（`mp.weixin.qq.com/s`）做图谱发现——微信公众号文章不允许外链，
正文里几乎没有出链，0 命中，此路不通。搜狗/百度/Bing/DDG 对 curl
全反爬，WebFetch 也被 antispider 拦，文章 URL 只能人工提供。

**死源处理（同日二次修订）**：首跑冒烟发现 90 号里 2 个死源——
卢瑟经济学安生杂谈（列表里两个 hash 均 404，号已注销）和
碳基体（RSS 有效但 0 条目，号已停更）。已原位替换为
全频带阻塞干扰 / 回忆飘如雪（均为活跃独立个人号，20 条/feed）。
其余 13 个首跑未落库的源 feed 健康（各 20 条），系首跑批次内
单 feed 失败容错跳过，下个整点 tick 自愈。

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
