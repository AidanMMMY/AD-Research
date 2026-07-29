# 2026-07-30 中文博客批次（D1 / zhb）集成记录

## 背景

「中文圈 ≥100 独立思考资讯源」goal 的最后一波（D1）。前两波已落地：

- D2 公众号三批 22 源（`wechat3_*`，commit 30b10dd）
- D3 中文播客 40 源（`zhx_*`，commit c463b38）

本波 D1 补 **38 个中文博客/独立评论站/中文国际媒体/社区精选 feed**，
62 + 38 = **100**，达成"不少于 100 个"目标（投资界 wewe-rss 重加后将成第 101 个）。

## 实测过程（2026-07-29/30，全部从生产 ECS 用浏览器 UA 验证）

约 280 个候选，验证项：HTTP 200、有效 RSS/Atom、最新条目 ≤14 天（喵神月更明确保留）。

### 淘汰记录（防止下次重踩）

- **停更**：kenengba 可能吧（2026-04）、xbeta 善用佳软（2025-05）、t9t（2025-11）、
  frankcui（2025-10）、apprcn 反斗限免（2026-04）、v2fy（2026-06）
- **已被既有表覆盖**：IT之家、Solidot（`global_rss_batch.py` 174/177 行）——实测鲜活但剔除保零重叠
- **无原生 RSS（ECS 实测返回 HTML/403/空）**：煎蛋、极客公园、品玩、果壳、一财、
  华尔街见闻、智通财经、联合早报、HK01、东森、中央社、ForesightNews、Odaily、
  优设、T客邦、数位时代、天下杂志（Cloudflare）
- **BBC 中文只有 simp 主索引新鲜**；world/china/business/science 子频道 2011-2014 年停更，勿加
- 新浪博客 RSS 全灭（16/16 FAIL，D1 agent 已验证）

### 38 源清单（slug → feed）

| 分组 | 源 |
|---|---|
| 独立博客 | coolshell 酷壳、macshuo MacTalk、iplaysoft 异次元、appinn 小众软件、biaodianfu 标点符、techug、aisixiang 爱思想、xueqiuhots 雪球热帖、onevcat 喵神（月更） |
| 聚合/垂直 | cnblogs 博客园、gcores 机核、cnbeta、digitaling 数英、oschina 开源中国、qbitai 量子位、it199 199IT、yunyingpai 运营派 |
| 中文国际媒体 | ftchinese、rfichinese、dwchinese、bbcchinese（仅 simp 索引）、theinitium 端传媒 |
| 台湾/英文视角 | technews 科技新报、ithometw iThome、sixthtone（en）、whatsonweibo（en） |
| 中文加密 | blocktempo 動區動趨、zombit 桑幣區識（market=crypto） |
| 科学 | pansci 泛科学 |
| V2EX | 9 个官方 tab feed（all/tech/creative/play/apple/jobs/deals/city/qna） |

## 集成改动（与 zhx 波同模式）

1. `app/services/news/sources/zh_blog_batch.py` — ZH_BLOG_FEEDS(38) / ZH_BLOG_BATCHES(a-d, ≤10) /
   ZH_BLOG_BATCH_JOBS(`news_zhb_{a-d}_60m`) / ZhBlogBatchCrawler（复用 rss_common + 浏览器 UA）
2. `app/services/news/scheduler_jobs.py` — `_zhb_batch_job` 工厂（无营销过滤）+ globals() 物化
3. `app/core/scheduler.py` — ZH_BLOG_BATCH_JOBS 注册循环（60m + jitter 600）
4. `app/api/v1/news.py` — `_WORKER_KEYWORDS` 加 `"zhb_"` + 4 条 `_WORKER_META`
5. `app/tests/news/test_zh_blog_batch.py` — 21 测试（零重叠 vs 全部 7 张既有表、分批、
   爬虫 mock、crypto market 保留、调度接线）

## 验证

- 本地 `pytest app/tests/news/` 575 passed
- 本地 `init_scheduler()` 后 4 个 `news_zhb_*` job 注册成功
- ECS 部署 + 冒烟见本文件末尾执行记录（部署后补）
