# 2026-07-28 资讯源扩充第二波：144 个独立非公众号源

> 背景：继 2026-07-27 公众号 100 源（90 wechat2rss 批量 + 8 wewe-rss + 2 单 feed）与 13 个英文独立源之后，再扩充 **144 个实测存活**的独立源，全部为非官方消息渠道（无官媒/政府/企业 PR，个人或小型独立团队），覆盖财经/商业/科技/地缘/人文。
>
> 选源标准与第一波一致：独立发言精神优先；官方媒体旗下 newsletter 不算独立（剔除《商业就是这样》=第一财经）；企业出品播客（知行小酒馆/无人知晓=有知有行、八分/没理想=看理想、跳岛=中信、谐星聊天会=单立人）一律不收。

## 1. 渠道构成

| 渠道 | 数量 | 说明 |
|---|---|---|
| 英文独立博客/Newsletter | 42 | macro/markets/tech/地缘/认知；Substack 自定义域名 + 自托管博客 |
| 英文独立播客 | 5 | 投资/商业类公开 RSS（libsyn/megaphone/art19） |
| 中文知名独立博客 | 7 | 阮一峰/月光/张鑫旭/唐巧/云风/虹线/王登科 |
| 中文独立播客 | 32 | 小宇宙 xyzfm CDN / Fireside / 喜马拉雅 / 荔枝 / 自托管 |
| 中文独立博客（chinese-independent-blogs 列表精选） | 58 | 按 tag 精选：创业/产品/投资/读书/认知/人文/生活方式，剔除纯技术博客 |
| **合计** | **144** | 全部实测存活（HTTP 200 + 有效 RSS/Atom + items>0 + 最新条目 30 天内） |

## 2. 渠道探测结论（为什么不含这些渠道）

- **RSSHub 公共实例（rsshub.app）**：本地与生产网络均连接超时（被墙/限流），放弃该渠道；知乎专栏/微博/B站 UP 主因此未纳入。
- **`*.substack.com` 裸域名**：全部连接超时（ACX、Krugman、Tooze、Kyla Scanlon、Marginal Revolution 式的 substack 域名均不可达）——所以第一批 13 源全部用自定义域名，本批同样只保留自定义域名 Substack（Slow Boring / BIG / Not Boring / The Defiant 等）。
- **blogspot / medium / typepad**：连接超时，对应源（Grumpy Economist、Mainly Macro、Arthur Hayes 等）放弃。
- **wechat2rss 剩余 ~300 号**：绝大多数为安全研究类，偏离平台主题；本次已凑够 144，未回补。
- **Cloudflare 403 挡掉**（The Racket、The Rebooting、The Irrelevant Investor、The Finance Buff 等）：UA 伪装后仍 403，放弃。
- **实测不新鲜/已停更**（>30 天无更新）：Fed Guy、Newfound Research、JL Collins、The Diff、老talk消息、电丸科技、商业WHY酱、泡腾VC、迟早更新、一天世界 等，未收录。

## 3. 144 源清单（含实测存活证据，实测时间 2026-07-27 23:5x 本地）

| # | slug | 名称 | 语言 | feed URL | items | 最新条目 |
|---|---|---|---|---|---|---|
| 1 | collabfund | Collaborative Fund (Morgan Housel) | en | https://collabfund.com/feed | 14 | 2026-07-27 |
| 2 | slowboring | Slow Boring | en | https://www.slowboring.com/feed | 20 | 2026-07-27 |
| 3 | stratechery | Stratechery | en | https://stratechery.com/feed | 10 | 2026-07-27 |
| 4 | notboring | Not Boring | en | https://www.notboring.co/feed | 20 | 2026-07-25 |
| 5 | generalist | The Generalist | en | https://www.generalist.com/feed | 20 | 2026-07-10 |
| 6 | platformer | Platformer | en | https://www.platformer.news/rss/ | 15 | 2026-07-24 |
| 7 | bigtechnology | Big Technology | en | https://www.bigtechnology.com/feed | 20 | 2026-07-20 |
| 8 | oneusefulthing | One Useful Thing | en | https://www.oneusefulthing.org/feed | 20 | 2026-07-23 |
| 9 | importai | Import AI | en | https://jack-clark.net/feed/ | 10 | 2026-07-27 |
| 10 | aisnakeoil | AI Snake Oil | en | https://www.normaltech.ai/feed | 20 | 2026-07-13 |
| 11 | bigstoller | BIG by Matt Stoller | en | https://www.thebignewsletter.com/feed | 20 | 2026-07-27 |
| 12 | lynalden | Lyn Alden | en | https://www.lynalden.com/feed/ | 10 | 2026-07-15 |
| 13 | alphaarchitect | Alpha Architect | en | https://alphaarchitect.com/feed/ | 5 | 2026-07-21 |
| 14 | priceactionlab | Price Action Lab | en | https://www.priceactionlab.com/Blog/feed | 20 | 2026-07-26 |
| 15 | abnormalreturns | Abnormal Returns | en | https://abnormalreturns.com/feed/ | 14 | 2026-07-27 |
| 16 | financialsamurai | Financial Samurai | en | https://www.financialsamurai.com/feed/ | 7 | 2026-07-27 |
| 17 | earlyretirementnow | Early Retirement Now | en | https://earlyretirementnow.com/feed/ | 10 | 2026-07-27 |
| 18 | farnamstreet | Farnam Street | en | https://fs.blog/feed/ | 20 | 2026-07-23 |
| 19 | intrinsicperspective | The Intrinsic Perspective | en | https://www.theintrinsicperspective.com/feed | 20 | 2026-07-24 |
| 20 | asteriskmag | Asterisk Magazine | en | https://asteriskmag.com/feed | 20 | 2026-07-21 |
| 21 | interconnected | Interconnected (Matt Webb) | en | https://interconnected.org/home/feed | 8 | 2026-07-24 |
| 22 | simonwillison | Simon Willison | en | https://simonwillison.net/atom/everything/ | 30 | 2026-07-26 |
| 23 | juliaevans | Julia Evans | en | https://jvns.ca/atom.xml | 20 | 2026-07-21 |
| 24 | danluu | Dan Luu | en | https://danluu.com/atom.xml | 128 | 2026-07-03 |
| 25 | thedefiant | The Defiant | en | https://thedefiant.io/feed | 100 | 2026-07-27 |
| 26 | popularinfo | Popular Information | en | https://popular.info/feed | 20 | 2026-07-27 |
| 27 | investmentmoats | Investment Moats | en | https://investmentmoats.com/feed | 10 | 2026-07-26 |
| 28 | financialhorse | Financial Horse | en | https://financialhorse.com/feed/ | 15 | 2026-07-26 |
| 29 | madfientist | Mad Fientist | en | https://www.madfientist.com/feed/ | 20 | 2026-06-29 |
| 30 | physicianonfire | Physician on FIRE | en | https://www.physicianonfire.com/feed/ | 20 | 2026-07-26 |
| 31 | whitecoatinvestor | The White Coat Investor | en | https://www.whitecoatinvestor.com/feed/ | 7 | 2026-07-27 |
| 32 | obliviousinvestor | Oblivious Investor | en | https://obliviousinvestor.com/feed/ | 10 | 2026-07-27 |
| 33 | retirementmanifesto | The Retirement Manifesto | en | https://www.theretirementmanifesto.com/feed/ | 10 | 2026-07-21 |
| 34 | millennialrevolution | Millennial Revolution | en | https://www.millennial-revolution.com/feed/ | 1 | 2026-07-21 |
| 35 | coachcarson | Coach Carson | en | https://www.coachcarson.com/feed/ | 10 | 2026-07-27 |
| 36 | heisenbergreport | Heisenberg Report | en | https://heisenbergreport.com/feed/ | 10 | 2026-07-27 |
| 37 | constructionphysics | Construction Physics | en | https://www.construction-physics.com/feed | 20 | 2026-07-25 |
| 38 | nintil | Nintil | en | https://nintil.com/rss.xml | 30 | 2026-07-11 |
| 39 | teachablemoment | A Teachable Moment | en | https://tonyisola.com/feed/ | 10 | 2026-07-25 |
| 40 | bellecurve | The Belle Curve | en | https://blairbellecurve.com/feed/ | 20 | 2026-07-24 |
| 41 | monevator | Monevator | en | https://monevator.com/feed/ | 12 | 2026-07-25 |
| 42 | firevlondon | FIRE v London | en | https://firevlondon.com/feed/ | 5 | 2026-07-19 |
| 43 | rationalreminder | Rational Reminder | en | https://rationalreminder.libsyn.com/rss | 441 | 2026-07-23 |
| 44 | investlikethebest | Invest Like the Best | en | https://feeds.megaphone.fm/investlikethebest | 589 | 2026-07-21 |
| 45 | chatwithtraders | Chat With Traders | en | https://chatwithtraders.libsyn.com/rss | 332 | 2026-07-22 |
| 46 | lexfridman | Lex Fridman Podcast | en | https://lexfridman.com/feed/podcast/ | 499 | 2026-06-30 |
| 47 | timferriss | The Tim Ferriss Show | en | https://rss.art19.com/tim-ferriss-show | 880 | 2026-07-22 |
| 48 | ruanyifeng | 阮一峰的网络日志 | zh | https://www.ruanyifeng.com/blog/atom.xml | 3 | 2026-07-27 |
| 49 | williamlong | 月光博客 | zh | https://www.williamlong.info/rss.xml | 10 | 2026-07-20 |
| 50 | zhangxinxu | 张鑫旭-鑫空间 | zh | https://www.zhangxinxu.com/wordpress/feed/ | 5 | 2026-07-23 |
| 51 | devtang | 唐巧的博客 | zh | https://blog.devtang.com/atom.xml | 20 | 2026-07-27 |
| 52 | codingnow | 云风的 BLOG | zh | https://blog.codingnow.com/atom.xml | 15 | 2026-07-24 |
| 53 | hongxian | 虹线 | zh | https://1q43.blog/feed | 10 | 2026-07-17 |
| 54 | greatdk | 王登科-DK博客 | zh | https://greatdk.com/feed | 10 | 2026-07-02 |
| 55 | mianji | 面基 | zh | https://feed.xyzfm.space/6hpdgggtxpxb | 164 | 2026-07-27 |
| 56 | qizhulou | 起朱楼宴宾客 | zh | https://feed.xyzfm.space/ahng8d9qlywl | 171 | 2026-07-21 |
| 57 | bannatie | 半拿铁 | 商业沉浮录 | zh | https://proxy.wavpub.com/caffebreve.xml | 226 | 2026-07-22 |
| 58 | sanwuhuan | 三五环 | zh | https://proxy.wavpub.com/35huan.xml | 224 | 2026-07-21 |
| 59 | luanfanshu | 乱翻书 | zh | https://feed.xyzfm.space/yxuruh3f9mc4 | 277 | 2026-07-09 |
| 60 | zhangxiaojun | 张小珺Jùn｜商业访谈录 | zh | https://feed.xyzfm.space/dk4yh3pkpjp3 | 150 | 2026-07-22 |
| 61 | taoban | 逃班｜Talking Band | zh | https://feed.xyzfm.space/yeuabxxl7ylm | 162 | 2026-07-12 |
| 62 | sv101 | 硅谷101 | zh | https://feeds.fireside.fm/sv101/rss | 254 | 2026-07-24 |
| 63 | kejizaozhidao | What's Next｜科技早知道 | zh | https://feeds.fireside.fm/guiguzaozhidao/rss | 424 | 2026-07-27 |
| 64 | shengdongjixi | 声东击西 | zh | https://feeds.fireside.fm/shengdongjixi/rss | 424 | 2026-07-16 |
| 65 | beiwanglu | 贝望录 | zh | http://www.ximalaya.com/album/42715423.xml | 266 | 2026-07-22 |
| 66 | storyfm | 故事FM | zh | https://feeds.storyfm.cn/storyfm.xml | 980 | 2026-07-24 |
| 67 | huzuohuyou | 忽左忽右 | zh | https://feed.xyzfm.space/cv4bkgpuglwp | 625 | 2026-07-24 |
| 68 | wenhuayouxian | 文化有限 | zh | https://s1.proxy.wavpub.com/weknownothing.xml | 351 | 2026-07-20 |
| 69 | daneimitan | 大内密谈 | zh | http://rss.lizhi.fm/rss/14275.xml | 1336 | 2026-07-26 |
| 70 | ritangongyuan | 日谈公园 | zh | http://www.ximalaya.com/album/5574153.xml | 843 | 2026-07-26 |
| 71 | genyuzhoujiehun | 跟宇宙结婚 | zh | http://rss.lizhi.fm/rss/1307862.xml | 526 | 2026-07-20 |
| 72 | mihuanchishu | 蜜獾吃书 | zh | https://www.ximalaya.com/album/64689453.xml | 206 | 2026-07-11 |
| 73 | penti | 喷嚏 | zh | https://feed.xyzfm.space/9unxvjbetgyu | 109 | 2026-07-25 |
| 74 | dongqiangxidiao | 东腔西调 | zh | https://www.ximalaya.com/album/41153937.xml | 321 | 2026-07-24 |
| 75 | wuliaozhai | 无聊斋 | zh | https://feed.xyzfm.space/njwyhpcjqn9t | 601 | 2026-07-26 |
| 76 | buheshiyi | 不合时宜 | zh | https://feed.xyzfm.space/ww7cqnybekty | 284 | 2026-07-24 |
| 77 | waidazhengzhao | 洪晃播客｜歪打正着 | zh | https://feed.xyzfm.space/tewruhycd3hp | 177 | 2026-07-22 |
| 78 | zonghengsihai | 纵横四海 | zh | https://www.ximalaya.com/album/67531569.xml | 86 | 2026-07-25 |
| 79 | laidoulai | 来都来了 | zh | http://www.ximalaya.com/album/31677988.xml | 284 | 2026-07-25 |
| 80 | heshiqitan | 核市奇谭 | zh | https://alioss.gcores.com/feeds/heshi.xml | 169 | 2026-07-17 |
| 81 | shenjiao | 深焦DeepFocus Radio | zh | https://www.ximalaya.com/album/37990930.xml | 320 | 2026-07-08 |
| 82 | tianzhen | 天真不天真 | zh | https://feed.xyzfm.space/mcklbwxjdvfu | 55 | 2026-07-27 |
| 83 | zitanzichang | 字谈字畅 | zh | https://www.thetype.com/typechat/feed/ | 285 | 2026-07-14 |
| 84 | bianjiaoliao | 边角聊 | zh | https://feed.xyzfm.space/ug6camnfa6bu | 219 | 2026-07-22 |
| 85 | jinjinledao | 津津乐道 | zh | http://www.ximalaya.com/album/3785430.xml | 601 | 2026-07-21 |
| 86 | zhankaijiangjiang | 展开讲讲 | zh | http://www.ximalaya.com/album/24672021.xml | 164 | 2026-07-10 |
| 87 | forecho | forecho 的独立博客 | zh | https://blog.forecho.com/atom.xml | 20 | 2026-07-24 |
| 88 | debuginn | Debug客栈 | zh | https://blog.debuginn.com/index.xml | 201 | 2026-07-13 |
| 89 | susheng | 素生 | zh | https://z.arlmy.me/atom.xml | 200 | 2026-07-26 |
| 90 | tumutanzi | 土木坛子 | zh | https://tumutanzi.com/feed | 5 | 2026-07-19 |
| 91 | life61 | 61's life | zh | https://61.life/feed.xml | 50 | 2026-07-03 |
| 92 | lenciel | Lenciel | zh | https://lenciel.com/feed.xml | 10 | 2026-07-08 |
| 93 | numb | 双绞麻痹 | zh | https://numb.tech/atom.xml | 20 | 2026-07-16 |
| 94 | maxos | maxOS | zh | https://maxoxo.me/rss/ | 15 | 2026-06-28 |
| 95 | ioerr | 读写错误 | zh | https://ioerr.github.io/index.xml | 12 | 2026-07-20 |
| 96 | gtdstudy | 学无止境@一点一滴 | zh | http://www.gtdstudy.com/index.xml | 4 | 2026-07-11 |
| 97 | skyue | SKYue's Home | zh | https://www.skyue.com/feed/ | 10 | 2026-07-12 |
| 98 | yinji | 印记 | zh | https://yinji.org/feed | 10 | 2026-07-03 |
| 99 | conge | conge | zh | https://conge.livingwithfcs.org/feed.xml | 10 | 2026-07-21 |
| 100 | leonhe | 远飞闲记 | zh | https://leonhe.cn/index.xml | 188 | 2026-07-09 |
| 101 | owenyoung | Owen的博客 | zh | https://www.owenyoung.com/feed | 50 | 2026-07-27 |
| 102 | lhcy | 林海草原 | zh | https://lhcy.org/feed | 10 | 2026-07-07 |
| 103 | kqh | 赫赫文王 | zh | https://kqh.me/index.xml | 10 | 2026-06-30 |
| 104 | macin | Macin | zh | https://macin.org/atom.xml | 20 | 2026-07-25 |
| 105 | jfsay | 静风说 | zh | https://www.jfsay.com/feed | 10 | 2026-07-22 |
| 106 | xianrenlife | 闲人Life | zh | https://www.xianrenlife.com/feeds/posts/default | 25 | 2026-07-11 |
| 107 | dongjunke | 东评西就 | zh | https://dongjunke.cn/atom.xml | 20 | 2026-07-23 |
| 108 | demochen | 特立独行的异类 | zh | https://demochen.com/atom.xml | 10 | 2026-07-22 |
| 109 | raymondhouch | 雷蒙三十 | zh | https://raymondhouch.com/feed/ | 10 | 2026-07-12 |
| 110 | chaoniulian | 骑行超过牛 | zh | https://www.chaoniulian.com/rss/ | 30 | 2026-07-26 |
| 111 | bluehe | 云心怀鹤 | zh | https://bluehe.cn/feed/ | 10 | 2026-07-04 |
| 112 | cosmopolite | Cosmos的博客 | zh | https://cosmo-polite.com/feed/ | 10 | 2026-07-26 |
| 113 | sehnsucht | Sehnsucht | zh | https://blog.sehnsucht.top/rss.xml | 102 | 2026-07-05 |
| 114 | kangaroogao | Maohang Gao's Blog | zh | https://kangaroogao.com/atom.xml | 20 | 2026-07-27 |
| 115 | jiangcl | 蒙需 | zh | https://jiangcl.com/feed | 5 | 2026-07-27 |
| 116 | citydatum | 橙树志 | zh | https://citydatum.cn/feed | 10 | 2026-07-27 |
| 117 | mingnify | 明立非 Mingnify | zh | https://mingnify.com/zh/blog/atom.xml | 20 | 2026-07-20 |
| 118 | whyya | 小陶持续精进 | zh | https://whyya.xyz/rss.xml | 97 | 2026-07-16 |
| 119 | jaketao | Jake Blog | zh | https://jaketao.com/feed/ | 20 | 2026-07-16 |
| 120 | giveanornot | 資工小廢物 JN | zh | https://blog.giveanornot.com/index.xml | 264 | 2026-07-22 |
| 121 | qingccl | QingCCL | zh | https://qingccl.com/rss.xml | 7 | 2026-07-01 |
| 122 | fengcan | 创见思考 | zh | https://www.fengcan.net/feed/ | 55 | 2026-07-26 |
| 123 | leesaitool | Arthur's Review | zh | https://blog.leesaitool.com/feed.xml | 27 | 2026-07-21 |
| 124 | wjd | 王佳冬中文博客 | zh | http://wjd.name/feed/ | 10 | 2026-07-18 |
| 125 | baicai | 白菜 | zh | https://blog.baicai.me/index.xml | 89 | 2026-07-01 |
| 126 | hutusi | 胡涂说 | zh | https://hutusi.com/feed.xml | 20 | 2026-07-11 |
| 127 | kanchuan | 陈看川博客 | zh | https://kanchuan.com/feed.xml | 20 | 2026-06-30 |
| 128 | wocai | kok的笔记本 | zh | https://wocai.de/index.xml/ | 82 | 2026-07-14 |
| 129 | xiaket | 年华转瞬 | zh | https://blog.xiaket.org/feed.xml | 10 | 2026-07-26 |
| 130 | wangjiezhe | 如鱼饮水 | zh | https://wangjiezhe.com/atom.xml | 20 | 2026-07-21 |
| 131 | mecll | 流浪天下 | zh | https://mecll.com/feed | 3 | 2026-07-15 |
| 132 | styunlen | 九仞之行 | zh | https://styunlen.cn/feed | 10 | 2026-07-08 |
| 133 | sion | 子虚栈 | zh | https://blog.si-on.top/atom.xml | 30 | 2026-07-21 |
| 134 | trumandu | TrumanDu 博客 | zh | http://blog.trumandu.top/atom.xml | 20 | 2026-07-01 |
| 135 | domon | Domon | zh | https://www.domon.cn/rss/ | 15 | 2026-07-04 |
| 136 | zhheo | 张洪Heo | zh | https://blog.zhheo.com/rss.xml | 20 | 2026-07-23 |
| 137 | taoshu | 涛叔 | zh | https://tao.zz.ac/feed.xml | 9 | 2026-07-22 |
| 138 | chegva | 安志合的学习博客 | zh | https://chegva.com/feed/ | 5 | 2026-07-25 |
| 139 | tianheg | 一大加贝 | zh | https://tianheg.co/index.xml | 20 | 2026-07-06 |
| 140 | ourai | 欧雷流 | zh | https://ourai.ws/atom.xml | 10 | 2026-07-01 |
| 141 | cyrusyip | 叶寻的博客 | zh | https://cyrusyip.org/zh-cn/index.xml | 161 | 2026-07-20 |
| 142 | lyunvy | Lyunvy's Blog | zh | https://blog.lyunvy.top/atom.xml | 54 | 2026-07-11 |
| 143 | cheshirex | 柴郡猫 | zh | https://www.cheshirex.com/feed | 10 | 2026-07-17 |
| 144 | hehysh | 十贰的小窝 | zh | https://hehysh.github.io/atom.xml | 20 | 2026-07-09 |

## 4. 改动文件

| 文件 | 改动 |
|---|---|
| `app/services/news/sources/independent_batch.py` | 新建：144 行源表 `INDEPENDENT_FEEDS`（slug/名称/URL/market/语言）+ `INDEPENDENT_BATCHES`（11 源/批 × 14 批 a–n）+ `IndependentBatchCrawler`（仿 Wechat2RssBatchCrawler，market/语言随行） |
| `app/services/news/scheduler_jobs.py` | 新增 `_independent_batch_job` 工厂 + `INDEPENDENT_BATCH_JOBS`（14 个 60m job，`news_indie_a_60m` … `news_indie_n_60m`）；**不走 LLM 营销过滤**（curated 编辑型源，与 13 个 INDEPENDENT_RSS_JOBS 同一先例，避免 LLM 成本随源数膨胀） |
| `app/core/scheduler.py` | 在 wechat2rss 注册循环后新增 INDEPENDENT_BATCH_JOBS 注册循环（60m 间隔） |
| `app/api/v1/news.py` | `_WORKER_KEYWORDS` 加 `indie_`；`_WORKER_META` 加 14 条健康网格标签 |
| `app/tests/news/test_independent_batch.py` | 新建：表完整性（唯一 slug/URL、格式、禁词、market/lang 白名单、http 白名单）、批次分区、≥100 源、与 wechat2rss 表无重叠、mock 抓取（per-feed source/market/lang 映射、失败隔离、未知批次）、调度接线（job 函数物化、批次覆盖、健康 meta、关键字）共 28 个用例 |

## 5. 测试结果

- `python -m pytest app/tests/news/test_independent_batch.py` → **28 passed**
- `python -m pytest app/tests/news/` → **387 passed**（无回归）
- 端到端直播抽样：batch a（英文博客）10/11 源取到 20 篇（Stratechery 429 限流瞬态，失败隔离生效）；batch f（中文播客）11/11 源取到 33 篇，market=cn_a / language=zh 正确，标题为真实单集标题。

## 6. 部署建议

1. 无需迁移/新环境变量，常规 deploy 即可；APScheduler 启动后 14 个新 job 自动注册。
2. 新 job 首次运行后，`/api/v1/news/health` 网格应出现"独立源 A–N 组"14 行；可用 `_WORKER_META` 标签核对。
3. 播客源单 feed 最大 ~1MB（故事FM 980 条），`max_items_per_feed=10` 截断后内存无压力；每批 11 源 × 2s 礼貌延迟，单批约 40–60s，60m 间隔不叠加（max_instances=1 + coalesce）。
4. 播客正文为 shownotes（含单集摘要），进入全文抓取管线时 enclosure 音频链接会被忽略，无需特殊处理。
5. 若后续想接 RSSHub 渠道，需自建 RSSHub 实例（公共实例不可达），再按本批同构模式加表即可。
