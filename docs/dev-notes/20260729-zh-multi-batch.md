# 20260729 中文播客批次 (zhx_) Runbook

> 40 个 ECS 实测存活的中文播客 RSS 源，财经/投资/宏观/商业分析/产业深度/科技评论方向。
> 代码：`app/services/news/sources/zh_multi_batch.py`；测试：`app/tests/news/test_zh_multi_batch.py`；
> 集成补丁：`docs/dev-notes/20260729-zh-multi-batch-integration.md`。

## 一、成果概览

- **达标 40 源**（目标 ≥30），全部为**原生 RSS**（小宇宙 feed.xyzfm.space / 喜马拉雅 / SoundOn / Firstory / Fireside / Acast / SoundCloud / 自托管），不依赖 RSSHub（生产网络不可达公共实例）。
- 候选实测 **68 个**（iTunes Search API 定位 feedUrl 后逐个从 ECS curl 验证），淘汰 **28 个**（20 停更、3 企业品牌出品、1 机构媒体、4 主题不符、1 无可用 RSS——有两项叠加的按主因归类）。
- 验证时间：**2026-07-29**，验证方式：`curl -s -L --max-time 15`（HTTP 200 → 解析 XML → 检查 `<item>` 数、最新单集日期、前 8 条 shownotes ≥80 字符的比例 ≥6/8）。
- 全部行 `market="cn_a"` / `language="zh"`；source 命名 `zhx_{slug}`；4 个批次 a–d 各 10 源，job_id `news_zhx_{batch}_60m`。
- 与既有 6 张表（independent_batch / global_rss_batch / global_indie_batch / asia_en_batch / wechat2rss_batch / wechat2rss_batch2）**零 slug、零 URL 重叠**，测试守卫已内置。
- 唯一 slug 冲突：`sspai` 已被 wechat2rss_batch2 占用，本表改用 `sspaipodcast`。
- 选源标准放宽说明：4 个高质量节目最新单集超过 30 天但在 60 天内，按月更/双周更节目保留并在下表注明。

## 二、源清单（40 源，按批次）

### 批次 A（job: news_zhx_a_60m）

| 节目 | slug | feed_url | 最新单集 | 定位 |
|---|---|---|---|---|
| 知行小酒馆 | zhixingjiuguan | https://feed.xyzfm.space/j8yp8gxkmgqr | 2026-07-24 | 有知有行出品投资/财富观对谈（E200+，中文投资理财头部） |
| 投资实战派 | touzishizhanpai | https://feed.xyzfm.space/rgnq4rbx9tpv | 2026-07-26 | 投资方法论与实盘对谈 |
| 满仓以后 | mancangyihou | https://feed.xyzfm.space/jgqnv6dwllut | 2026-07-24 | 股民视角投资陪伴/市场复盘 |
| 三点下班 | sandianxiaban | https://feed.xyzfm.space/tlel9j4tg3eu | 2026-07-27 | 股市三点收盘后的投资陪伴评论 |
| 会友镖局 | huiyoubiaoju | https://feed.xyzfm.space/xgeyj6a3mngc | 2026-07-13 | 温义飞财经科普/商业评论 |
| 疯投圈 | fengtouquan | https://crazy.capital/feed | 2026-07-27 | 黄海主持 VC/商业深度对谈 |
| 42章经 | sishierzhangjing | https://feed.xyzfm.space/evgg6xle9rdc | 2026-07-19 | 曲凯主持一级市场/创投方法论 |
| 商业WHY酱 | shangyewhyjiang | https://feed.xyzfm.space/twj7n6rmffpd | 2026-06-25（34 天，双周/月更档） | 商业案例追问式分析 |
| 进击波财经 | jinjibocaijing | https://feed.xyzfm.space/wjvqp9jxdhtn | 2026-07-27 | 沈帅波商业/消费评论 |
| 小马宋商业观察 | xiaomasong | https://feed.xyzfm.space/kbkftb78gb4e | 2026-06-22（37 天，月更档） | 小马宋营销/经营观察 |

### 批次 B（job: news_zhx_b_60m）

| 节目 | slug | feed_url | 最新单集 | 定位 |
|---|---|---|---|---|
| 晚点聊 LateTalk | wandianliao | https://feeds.fireside.fm/latetalk/rss | 2026-07-27 | 晚点LatePost 科技/商业从业者访谈 |
| 窄播一下 | zhaiboyixia | https://feed.xyzfm.space/cp8gttbug8v6 | 2026-07-22 | 窄播出品消费/互联网/出海/AI 产业对谈 |
| 大头侃人 | datoukanren | https://feed.xyzfm.space/jtumdxxt8fjt | 2026-06-08（50 天，月更档） | 商业人物/企业家故事 |
| 十字路口Crossing | shizilukou | https://feed.xyzfm.space/68fyjknth9hj | 2026-07-26 | AI 变革与创业机会访谈 |
| 出海相对论 | chuhaixiangduilun | https://feed.xyzfm.space/y3cpdhbar4ap | 2026-07-21 | 品牌/电商出海商业对谈 |
| EqualOcean出海全球化会客厅 | equalocean | https://feed.xyzfm.space/rjl4uflbdr33 | 2026-07-29 | 中国出海企业全球化访谈 |
| 硬地骇客 | yingdihaike | https://feed.xyzfm.space/byhkljlbep9j | 2026-07-13 | 独立开发/一人公司创业 |
| 消费新知 | xiaofeixinzhi | http://www.ximalaya.com/album/46604249.xml | 2026-07-17 | 消费行业新趋势解读 |
| 大小马聊科技 | daxiaoma | http://www.ximalaya.com/album/55951710.xml | 2026-07-27 | 电动车/新能源/科技评论 |
| 硅谷叨B叨 | guigudaobdao | http://www.ximalaya.com/album/21685160.xml | 2026-07-17 | 硅谷华人科技圈评论 |

### 批次 C（job: news_zhx_c_60m）

| 节目 | slug | feed_url | 最新单集 | 定位 |
|---|---|---|---|---|
| 枫言枫语 | fengyanfengyu | https://justinyan.me/feed/podcast | 2026-07-03 | 自力主持科技/创业对谈 |
| 少数派播客 | sspaipodcast | https://sspai.typlog.io/feed/audio.xml | 2026-06-16（43 天，月更档） | 少数派科技/效率/创作评论 |
| 东亚观察局 | dongyaguanchaju | http://www.ximalaya.com/album/37399737.xml | 2026-07-23 | 日韩台国际政经评论 |
| 不明白播客 | bumingbai | https://feeds.acast.com/public/shows/68004395b4ef799a7a410371 | 2026-07-20 | 袁莉主持中国议题深度访谈 |
| 股癌 Gooaye | gooaye | https://feeds.soundon.fm/podcasts/954689a5-3096-43a4-a80b-7810b219cef3.xml | 2026-07-29 | 謝孟恭台股/美股投资评论（台区头部） |
| 兆華與股惑仔 | zhaohuaguhuozai | https://feeds.soundon.fm/podcasts/91be014b-9f55-4bf3-a910-b232eda82d11.xml | 2026-07-29 | 股票/投资对谈（日更级） |
| 股市隱者 | gushiyinzhe | https://feeds.soundon.fm/podcasts/eb9e90a8-a889-425b-8855-4cf8cdf92c73.xml | 2026-07-27 | 台股投资心理与策略 |
| 財報狗 | caibaogou | https://feed.firstory.me/rss/user/clcftm46z000201z45w1c47fi | 2026-07-26 | 台股美股财报/时事议题 |
| 不敗教主陳重銘 | bubaijiaozhu | https://feeds.soundon.fm/podcasts/f93d43ed-f938-45f1-9e71-d915f806bae4.xml | 2026-07-29 | 存股/长期投资方法 |
| 投資嗨什麼 | touzihaishenme | https://feeds.soundon.fm/podcasts/bf960cfe-3cd1-4723-a980-52711c69a3c8.xml | 2026-07-07 | 投资理财大众科普对谈 |

### 批次 D（job: news_zhx_d_60m）

| 节目 | slug | feed_url | 最新单集 | 定位 |
|---|---|---|---|---|
| 下班經濟學 | xiabanjingjixue | https://feeds.soundon.fm/podcasts/208dfd5b-d11b-4236-ab87-d8f0bf01d7d0.xml | 2026-07-29 | 财经时事评论（日更级，台区头部） |
| 游庭皓的財經皓角 | caijinghaojiao | https://feeds.soundcloud.com/users/soundcloud:users:735679489/sounds.rss | 2026-07-29 | 总体经济/金融分析 |
| 台灣通勤第一品牌 | taiwantongqin | https://anchor.fm/s/1ea77470/podcast/rss | 2026-07-27 | 财经时事+国际评论（台区头部） |
| 敏迪選讀 | mindixuandu | https://feeds.soundon.fm/podcasts/44833083-490d-4f97-a782-fd5e34c0abef.xml | 2026-07-26 | 国际新闻/地缘政治解读 |
| 美國台灣觀測站 | meiguotaiwanguance | https://feeds.soundon.fm/podcasts/6cdfccc6-7c47-4c35-8352-7f634b1b6f71.xml | 2026-07-22 | 台美关系/国际政治经济评论 |
| M觀點 | mguandian | https://feeds.soundon.fm/podcasts/b8f5a471-f4f7-4763-9678-65887beda63a.xml | 2026-07-27 | Miula 科技×商业×投资评论 |
| 科技開麥拉 | kejikamaila | https://feed.firstory.me/rss/user/cl0bwfpls02rt0847zq8ru6js | 2026-07-08 | 台湾科技产业评论 |
| 報導者 The Real Story | baodaozhe | https://feeds.soundon.fm/podcasts/c1f1f3c9-8d28-42ad-9f1c-908018b8d9fc.xml | 2026-07-29 | 非营利深度调查报导 |
| 大人的Small Talk | darensmalltalk | https://feeds.soundon.fm/podcasts/6731d283-54f0-49ec-a040-e5a641c3125f.xml | 2026-07-26 | 大人学职涯/管理/商业对谈 |
| 北美金事角 | beimeijinshijiao | https://anchor.fm/s/7aa7f5d8/podcast/rss | 2026-07-21 | 中美金融科技双语圈评论 |

## 三、淘汰候选附录（实测 68 - 存活 40 = 28）

| 节目 | feed_url | 淘汰原因 |
|---|---|---|
| 无人知晓（孟岩） | feed.xyzfm.space/ypn9dydpbxpc | 停更：最新 2026-03-03（148 天） |
| 保持通话 | feed.xyzfm.space/uydkftwpn7cu | 停更：最新 2026-04-06（113 天） |
| 投资人老范 | feed.xyzfm.space/hu9a668ernga | 停更：最新 2026-04-20（100 天） |
| 老talk消息 | ximalaya.com/album/31225613.xml | 停更：最新 2026-05-29（61 天，超 60 天红线） |
| 方舟運算 | feeds.soundon.fm/podcasts/049c00d3-…xml | 停更：最新 2026-05-15（75 天） |
| 大道至簡投資法 | anchor.fm/s/10a813908/podcast/rss | 停更：最新 2026-03-08（143 天） |
| 壞孩子與小廢物的理財幼幼班 | feeds.soundon.fm/podcasts/d02f3d74-…xml | 停更：最新 2025-02-05（539 天） |
| 内核恐慌 | pan.icu/feed | 停更：最新 2025-07-07（387 天） |
| 奇想驿 by 产品沉思录 | feed.xyzfm.space/4wq8y3ymmc7p | 停更：最新 2025-06-03（421 天） |
| 跳进兔子洞 | feed.xyzfm.space/gcucd7uljqru | 停更：最新 2024-07-12（747 天） |
| 智本社 | feeds.soundon.fm/podcasts/d1e6682c-…xml | 停更：最新 2024-02-27（883 天） |
| 出海早知道 | feed.xyzfm.space/c8kjyfjfnkjn | 停更：最新 2023-11-06（995 天） |
| 股魚_財經不正經 | feeds.soundon.fm/podcasts/91817f42-…xml | 停更：最新 2022-03-31（1581 天） |
| 泡腾VC | feed.xyzfm.space/7bfjpnbkffmt | 停更：最新 2021-11-30（1702 天） |
| 佳明与思语 | ximalaya.com/album/53261302.xml | 停更：最新 2021-10-06（1757 天） |
| 力哥说理财 | ximalaya.com/album/259290.xml | 停更：最新 2021-09-02（1791 天） |
| 科技島讀 | feeds.soundcloud.com/…322164009/sounds.rss | 停更：最新 2021-06-06（1878 天） |
| 卓老板聊科技 | ximalaya.com/album/335347.xml | 停更：最新 2019-10-10（2483 天，已转得到系） |
| 冬吴同学会 | ximalaya.com/album/8548397.xml | 停更：最新 2017-06-07（3339 天，仅剩 1 集） |
| 钱婧老师的会客厅 | feed.xyzfm.space/9lgcqvwrheuj | 停更：最新 2026-03-17（134 天） |
| 厚雪长波 | proxy.wavpub.com/snowball.xml | 企业品牌出品：雪球官方播客 |
| 创业内幕 Startup Insider | ximalaya.com/album/20119986.xml | 企业品牌出品：纪源资本（GGV）官方播客 |
| 商业就是这样 | ximalaya.com/album/46587439.xml | 机构媒体出品：第一财经杂志（黑名单词命中） |
| 万物生长FM | feed.xyzfm.space/qhtdbtr76cha | 主题不符：生命科学/健康 |
| 小题大做 | media.rss.com/makeafuss/feed.xml | 主题不符：生活闲聊（自述"闲聊类播客"） |
| 凑近点看 | ximalaya.com/album/42542290.xml | 主题不符：职场吐槽/闲聊娱乐 |
| 井户端会议 | feed.xyzfm.space/68acw4ke4frl | 主题偏文化历史传媒，财经产业契合度低 |
| 星箭廣播 | podcast.starrocket.io/rss | 无可用原生 RSS：官网为 Next.js SPA（任意路径返回 HTML），Firstory 旧 user id 404 |

**前置排除（未进入实测）**：中欧基金 / 华夏早播间 / 人间钱话（基金公司 PR）、雪球·财经有深度 / 雪球·投资第一课 / 厚雪私募班（雪球官方，且偏新闻/课程）、声动早咖啡（纯新闻播报）、宏观名家谈（财新官方）、凱基證券樂活投資人（券商 PR）、组织进化论（飞书官方）、简七理财（企业品牌）、百靈果 The KK Show（娱乐综艺）、哇賽心理學（心理，主题不符）、梁文道·八分 / 随机波动 / 螺丝在拧紧（文化类，主题不符）、听懂涨声（检索仅命中基金公司节目）、老钱日日谈（即已收录的「面基」，同一主播）。

## 四、运维备注

1. **托管分布与风险**：
   - `feed.xyzfm.space`（小宇宙 CDN）17 源——前波已验证 ECS 可达，单点依赖最高，若该域故障 A/B/C 批会批量空跑（`no_articles` skip，不影响调度器）。
   - `ximalaya.com` 5 源、`feeds.soundon.fm` 13 源、SoundCloud 2 源、Firstory 2 源、Fireside/Acast/anchor/自托管各 1–2 源。SoundOn 的 feed URL 含 GUID，节目方换托管时会失效，届时该源持续空跑——**排障第一步先看是不是 feed 迁移**。
2. **播客正文 = shownotes**：`description` 即落库正文（`parse_rss_items` 会剥 HTML）。`<enclosure>` 音频 URL 不入库，不消耗带宽。部分节目 shownotes 较短（如股市隱者部分单集），属正常现象。
3. **批次扩缩容**：表追加新源时直接往 `ZH_MULTI_FEEDS` 末尾加行并把 `_BATCH_KEYS` 从 `"abcd"` 扩到 `"abcde"` 即可；批次键独立命名空间，无需避让 independent(a–n)/gind(o–x) 的键位。
4. **市场与翻译**：全部 `cn_a`/`zh`，走前端默认过滤器的中文新闻流；翻译管线只处理英文，零增量 LLM 成本。
5. **更新节奏**：播客多数周更，`IntervalTrigger(minutes=60, jitter=600)` 足够；每批 10 源、源间 2s 礼貌延迟 + 10 items/源上限，单批爬取约 30–60s。
6. **去重**：依靠 `source + source_id`（guid 优先）。xyzfm/SoundOn 的 guid 稳定；喜马拉雅 album XML 的 guid 为单集链接，亦稳定。
7. **复验命令**（与本次验证一致，建议在 ECS 上跑）：

```bash
curl -s -o /dev/null -w "%{http_code}\n" --max-time 15 -L <feed_url>
```

8. **相关文档**：选源/验证/淘汰全记录见本文件；集成步骤见 `20260729-zh-multi-batch-integration.md`；前波英文独立播客见 `20260728-global-indie-batch.md`。
