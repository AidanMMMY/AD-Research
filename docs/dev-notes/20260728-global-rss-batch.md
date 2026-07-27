# 全球多语 RSS 源批次（第二波，agent B）— 125 源实测收录

日期：2026-07-28 ｜ 模块：`app/services/news/sources/global_rss_batch.py` ｜ Job：`news_global_rss_[a-l]_60m`（12 个批次，60m 间隔，每批 ≤11 源）

## 1. 语言构成

| 语言 | 源数 | 渠道构成 |
|---|---|---|
| 日语 (ja) | 7 | 财经媒体(ZUU online/ハフポスト日本版/Sirabee) + IT(Publickey) + 企业工程博客(ZOZO/freee/Money Forward) |
| 德语 (de) | 7 | 财经博客(Der Bank Blog/Finanzrocker) + 科技媒体(netzpolitik/t3n/Computerwoche/MobileGeeks/neunetz) |
| 法语 (fr) | 12 | 全国媒体(France24/BFMTV×2/Ouest-France/Valeurs/La Libre/Challenges/Courrier International) + 科技(next.ink/Clubic/Les Numériques/Developpez) |
| 韩语 (ko) | 8 | 综合媒体(조선일보/동아일보/오마이뉴스/노컷뉴스/SBS/전자신문) + 加密(토큰포스트/코인데스크코리아) |
| 西班牙语 (es) | 12 | 西语美洲+西班牙(La Nación/El Financiero/La Tercera/Expansión/eldiario/20minutos) + 科技博客(Xataka/El Blog Salmón/Microsiervos/Hipertextual/WWWhatsnew/Hiperderecho) |
| 中文 (zh) | 8 | 行业媒体(东方财富/爱范儿/钛媒体/雷峰网/创业邦/IT之家/Solidot/SegmentFault) |
| 英语 (en) | 71 | 央行研究(NY Fed/BoE/Atlanta Fed/NBER) + 智库(Bruegel 落选→Heritage/Tax Foundation/Pew/AEI 系) + 高校(LSE/Promarket/Wharton 落选) + 独立分析师(Grumpy Economist/Conversable Economist 等) + 工程团队博客(Cloudflare/Netflix/AWS/GitHub 等) |
| **合计** | **125** | |

## 2. 验收标准与实测方法

- 每源实测：httpx GET（Mozilla UA，30s 超时，失败重试 1 次）→ HTTP 200 → `parse_rss_items` 解析出 ≥1 条 → 前 10 条正文（content:encoded/description/atom:content 去 HTML）平均 >200 字符 → 最新一条发布时间在 30 天内。
- 3 波共测 573 个候选 URL：第一波 227、第二波 306、第三波 40（含备选 URL 与解析修复后复测）。
- 主要淘汰原因：本机网络对欧洲/日本大量站点 TCP 不可达（约占淘汰 40%）、正文仅标题/一句话摘要（约 30%，日本媒体尤其普遍）、404/403（约 25%）、停更（约 5%）。
- 与并行 agent 去重：其 `independent_batch.py`（144 源，已 commit 689acbc）有 7 个 URL 与本表重叠（abnormal_returns/alpha_architect/financial_samurai/jvns/lynalden/oblivious_investor/simonwillison），已从本表剔除，本表 132→125。
- 解析器修复（`rss_common.py`）：补齐 Atom 命名空间 title/summary/content 与 RSS 1.0 (RDF) item 解析——日本媒体（Impress Watch 系、ZDNet Japan 系）与工程博客（Go/Rust/Qiita/Publickey）依赖此修复。

## 3. 全量源清单（含实测证据）

### 日语（7）

| slug | 名称 | feed_url | items | 平均正文(字符) | 最新日期 |
|---|---|---|---|---|---|
| freee_dev | freee Developers Blog | https://developers.freee.co.jp/feed | 30 | 4337 | 2026-07-24 |
| huffpost_jp | ハフポスト日本版 | https://www.huffingtonpost.jp/feeds/index.xml | 30 | 1112 | 2026-07-27 |
| moneyforward_dev | Money Forward Developers | https://moneyforward-dev.jp/feed | 30 | 301 | 2026-07-23 |
| publickey | Publickey | https://www.publickey1.jp/atom.xml | 15 | 236 | 2026-07-27 |
| sirabee | Sirabee | https://sirabee.com/feed/ | 10 | 1277 | 2026-07-27 |
| zozo_tech | ZOZO Tech Blog | https://techblog.zozo.com/feed | 30 | 8736 | 2026-07-27 |
| zuuonline | ZUU online | https://zuuonline.com/feed | 30 | 1976 | 2026-07-27 |

### 德语（7）

| slug | 名称 | feed_url | items | 平均正文(字符) | 最新日期 |
|---|---|---|---|---|---|
| computerwoche | Computerwoche | https://www.computerwoche.de/rss/ | 20 | 7893 | 2026-07-27 |
| der_bank_blog | Der Bank Blog | https://www.der-bank-blog.de/feed/ | 50 | 244 | 2026-07-26 |
| finanzrocker | Finanzrocker | https://www.finanzrocker.net/feed/ | 10 | 520 | 2026-07-23 |
| mobilegeeks_de | MobileGeeks | https://www.mobilegeeks.de/feed/ | 10 | 7126 | 2026-07-27 |
| netzpolitik | netzpolitik.org | https://netzpolitik.org/feed/ | 25 | 8048 | 2026-07-27 |
| neunetz | neunetz | https://neunetz.com/feed/ | 15 | 10765 | 2026-07-10 |
| t3n | t3n Magazin | https://t3n.de/rss.xml | 20 | 233 | 2026-07-27 |

### 法语（12）

| slug | 名称 | feed_url | items | 平均正文(字符) | 最新日期 |
|---|---|---|---|---|---|
| bfm_eco | BFM Économie | https://www.bfmtv.com/rss/economie/ | 30 | 284 | 2026-07-27 |
| bfmtv | BFM TV | https://www.bfmtv.com/rss/news-24-7/ | 30 | 300 | 2026-07-27 |
| challenges | Challenges | https://www.challenges.fr/rss.xml | 50 | 278 | 2026-07-27 |
| clubic | Clubic | https://www.clubic.com/feed/rss | 50 | 224 | 2026-07-27 |
| courrierinter | Courrier International | https://www.courrierinternational.com/feed/all/rss.xml | 20 | 308 | 2026-07-27 |
| developpez | Developpez.com | https://www.developpez.com/rss.php | 20 | 457 | 2026-07-27 |
| france24 | France 24 | https://www.france24.com/fr/rss | 24 | 274 | 2026-07-27 |
| lalibre | La Libre Belgique | https://www.lalibre.be/rss | 100 | 208 | 2026-07-27 |
| lesnumeriques | Les Numériques | https://www.lesnumeriques.com/rss.xml | 40 | 354 | 2026-07-27 |
| next_ink | next.ink (ex-Next INpact) | https://next.ink/feed/ | 50 | 3183 | 2026-07-27 |
| ouestfrance | Ouest-France | https://www.ouest-france.fr/rss/une | 10 | 275 | 2026-07-27 |
| valeurs | Valeurs Actuelles | https://www.valeursactuelles.com/rss | 10 | 354 | 2026-07-27 |

### 韩语（8）

| slug | 名称 | feed_url | items | 平均正文(字符) | 最新日期 |
|---|---|---|---|---|---|
| chosun | 조선일보 | https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml | 100 | 224 | 2026-07-27 |
| coindeskkorea | 코인데스크코리아 | https://www.coindeskkorea.com/rss | 50 | 2926 | 2026-07-03 |
| donga | 동아일보 | https://rss.donga.com/total.xml | 50 | 451 | 2026-07-27 |
| etnews | 전자신문 | https://rss.etnews.com/Section901.xml | 30 | 249 | 2026-07-27 |
| nocutnews | 노컷뉴스 | https://rss.nocutnews.co.kr/nocutnews.xml | 21 | 1216 | 2026-07-27 |
| ohmynews | 오마이뉴스 | https://rss.ohmynews.com/rss/ohmynews.xml | 20 | 842 | 2026-07-27 |
| sbs_news | SBS 뉴스 | https://news.sbs.co.kr/news/TopicRssFeed.do?plink=RSSREADER | 11 | 1202 | 2026-07-27 |
| tokenpost | 토큰포스트 | https://www.tokenpost.kr/rss | 50 | 376 | 2026-07-27 |

### 西班牙语（12）

| slug | 名称 | feed_url | items | 平均正文(字符) | 最新日期 |
|---|---|---|---|---|---|
| 20minutos_es | 20minutos | https://www.20minutos.es/rss/ | 205 | 4348 | 2026-07-27 |
| elblogsalmon | El Blog Salmón | https://www.elblogsalmon.com/index.xml | 20 | 7241 | 2026-07-27 |
| eldiario | eldiario.es | https://www.eldiario.es/rss/ | 101 | 5892 | 2026-07-27 |
| elfinanciero_mx | El Financiero (MX) | https://www.elfinanciero.com.mx/rss/ | 100 | 3452 | 2026-07-27 |
| expansion | Expansión | https://e00-expansion.uecdn.es/rss/portada.xml | 66 | 211 | 2026-07-27 |
| hiperderecho | Derecho Digital | https://hiperderecho.org/feed/ | 100 | 9587 | 2026-07-21 |
| hipertextual | Hipertextual | https://hipertextual.com/feed | 15 | 4489 | 2026-07-27 |
| lanacion | La Nación (AR) | https://www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml | 96 | 3895 | 2026-07-27 |
| latercera | La Tercera | https://www.latercera.com/arc/outboundfeeds/rss/?outputType=xml | 100 | 2918 | 2026-07-27 |
| microsiervos | Microsiervos | https://microsiervos.com/index.xml | 15 | 2286 | 2026-07-27 |
| wwwhatsnew | WWWhatsnew | https://wwwhatsnew.com/feed/ | 10 | 7039 | 2026-07-27 |
| xataka | Xataka | https://www.xataka.com/index.xml | 26 | 5529 | 2026-07-27 |

### 中文（8）

| slug | 名称 | feed_url | items | 平均正文(字符) | 最新日期 |
|---|---|---|---|---|---|
| cyzone | 创业邦 | https://www.cyzone.cn/rss/ | 30 | 287 | 2026-07-27 |
| eastmoney_rss | 东方财富网 | https://rss.eastmoney.com/rss_partener.xml | 93 | 2927 | 2026-07-27 |
| ifanr | 爱范儿 | https://www.ifanr.com/feed | 20 | 5018 | 2026-07-27 |
| ithome_cn | IT之家 | https://www.ithome.com/rss/ | 60 | 829 | 2026-07-27 |
| leiphone | 雷峰网 | https://www.leiphone.com/feed | 20 | 5282 | 2026-07-27 |
| segmentfault | SegmentFault | https://segmentfault.com/feeds | 50 | 237 | 2026-07-24 |
| solidot | Solidot 奇客 | https://www.solidot.org/index.rss | 20 | 348 | 2026-07-27 |
| tmtpost | 钛媒体 | https://www.tmtpost.com/rss.xml | 19 | 3366 | 2026-07-27 |

### 英语（71）

| slug | 名称 | feed_url | items | 平均正文(字符) | 最新日期 |
|---|---|---|---|---|---|
| acquirers_multiple | The Acquirer's Multiple | https://acquirersmultiple.com/feed/ | 20 | 8885 | 2026-07-27 |
| american_compass | American Compass | https://americancompass.org/feed/ | 10 | 5340 | 2026-07-16 |
| android_dev | Android Developers Blog | https://android-developers.googleblog.com/feeds/posts/default | 25 | 7110 | 2026-07-27 |
| apple_ml | Apple Machine Learning Research | https://machinelearning.apple.com/rss.xml | 10 | 593 | 2026-07-27 |
| arstechnica | Ars Technica | https://feeds.arstechnica.com/arstechnica/index | 20 | 1096 | 2026-07-27 |
| automatic_earth | The Automatic Earth | https://www.theautomaticearth.com/feed | 10 | 420 | 2026-07-27 |
| aws_blog | AWS News Blog | https://aws.amazon.com/blogs/aws/feed/ | 20 | 6501 | 2026-07-27 |
| axios | Axios | https://api.axios.com/feed/top/ | 100 | 3462 | 2026-07-27 |
| bankunderground | Bank Underground (BoE) | https://bankunderground.co.uk/feed/ | 10 | 10173 | 2026-07-16 |
| brooker | Marc Brooker's Blog | https://brooker.co.za/blog/rss.xml | 162 | 4980 | 2026-07-19 |
| business_insider | Business Insider | https://www.businessinsider.com/rss | 20 | 5247 | 2026-07-27 |
| chainalysis_blog | Chainalysis Blog | https://www.chainalysis.com/blog/feed/ | 10 | 282 | 2026-07-24 |
| cloudflare_blog | Cloudflare Blog | https://blog.cloudflare.com/rss/ | 20 | 12965 | 2026-07-27 |
| cncf_blog | CNCF Blog | https://www.cncf.io/feed/ | 10 | 10309 | 2026-07-27 |
| contra_corner | David Stockman's Contra Corner | https://davidstockmanscontracorner.com/feed/ | 12 | 559 | 2026-07-24 |
| conversable_economist | Conversable Economist (Timothy Taylor) | https://conversableeconomist.com/feed/ | 10 | 5100 | 2026-07-24 |
| dropbox_tech | Dropbox.Tech | https://dropbox.tech/feed | 10 | 14939 | 2026-07-20 |
| econlib | EconLog / Econlib | https://www.econlib.org/feed/ | 10 | 10246 | 2026-07-24 |
| financial_post | Financial Post | https://financialpost.com/feed/ | 10 | 257 | 2026-07-27 |
| flyio_blog | Fly.io Blog | https://fly.io/blog/feed.xml | 40 | 10802 | 2026-07-24 |
| fortune | Fortune | https://fortune.com/feed/ | 10 | 6302 | 2026-07-27 |
| github_blog | The GitHub Blog | https://github.blog/feed/ | 10 | 8602 | 2026-07-23 |
| grumpy_economist | The Grumpy Economist (John Cochrane) | https://www.grumpy-economist.com/feed | 20 | 9708 | 2026-07-22 |
| guardian_business | The Guardian Business | https://www.theguardian.com/uk/business/rss | 40 | 543 | 2026-07-27 |
| hashicorp_blog | HashiCorp Blog | https://www.hashicorp.com/blog/feed.xml | 20 | 9569 | 2026-07-22 |
| heritage | Heritage Foundation | https://www.heritage.org/rss | 20 | 7884 | 2026-07-24 |
| heroku_blog | Heroku Blog | https://blog.heroku.com/feed | 150 | 5329 | 2026-07-16 |
| honeycomb_blog | Honeycomb Blog | https://www.honeycomb.io/feed/ | 50 | 260 | 2026-07-22 |
| incrementum | Incrementum | https://www.incrementum.li/en/feed/ | 10 | 3453 | 2026-07-27 |
| infoq_en | InfoQ | https://feed.infoq.com/ | 15 | 368 | 2026-07-27 |
| international_man | International Man (Doug Casey) | https://internationalman.com/feed/ | 10 | 7498 | 2026-07-24 |
| jamestown | Jamestown Foundation | https://jamestown.org/feed/ | 10 | 10493 | 2026-07-25 |
| jetbrains_blog | JetBrains Blog | https://blog.jetbrains.com/feed/ | 12 | 7448 | 2026-07-27 |
| koreatimes | The Korea Times | https://www.koreatimes.co.kr/www/rss/rss.xml | 5 | 888 | 2026-07-27 |
| kubernetes_blog | Kubernetes Blog | https://kubernetes.io/feed.xml | 50 | 10660 | 2026-07-14 |
| liberty_street | Liberty Street Economics (NY Fed) | https://libertystreeteconomics.newyorkfed.org/feed/ | 100 | 13454 | 2026-07-17 |
| lse_business | LSE Business Review | https://blogs.lse.ac.uk/businessreview/feed/ | 10 | 9026 | 2026-07-23 |
| martinfowler | Martin Fowler | https://martinfowler.com/feed.atom | 30 | 5847 | 2026-07-21 |
| meta_engineering | Engineering at Meta | https://engineering.fb.com/feed/ | 9 | 16080 | 2026-07-15 |
| mozilla_blog | Mozilla Blog | https://blog.mozilla.org/en/feed/ | 20 | 3244 | 2026-07-21 |
| msft_blog | Microsoft Blog | https://blogs.microsoft.com/feed/ | 10 | 9484 | 2026-07-22 |
| msft_research | Microsoft Research Blog | https://www.microsoft.com/en-us/research/feed/ | 10 | 9480 | 2026-07-13 |
| nber | NBER | https://back.nber.org/rss/new.xml | 31 | 1028 | 2026-07-27 |
| netflix_tech | Netflix TechBlog | https://netflixtechblog.com/feed | 10 | 17176 | 2026-07-17 |
| niskanen | Niskanen Center | https://www.niskanencenter.org/feed/ | 10 | 57995 | 2026-07-23 |
| nvidia_blog | NVIDIA Blog | https://blogs.nvidia.com/feed/ | 18 | 6085 | 2026-07-27 |
| nvidia_dev | NVIDIA Technical Blog | https://developer.nvidia.com/blog/feed/ | 100 | 559 | 2026-07-27 |
| pewresearch | Pew Research Center | https://www.pewresearch.org/feed/ | 100 | 280 | 2026-07-27 |
| postman_blog | Postman Blog | https://blog.postman.com/feed/ | 12 | 14474 | 2026-07-27 |
| project_syndicate | Project Syndicate | https://www.project-syndicate.org/rss | 20 | 304 | 2026-07-27 |
| promarket | ProMarket (Chicago Booth) | https://www.promarket.org/feed/ | 10 | 411 | 2026-07-27 |
| prometheus_blog | Prometheus Blog | https://prometheus.io/blog/feed.xml | 59 | 6131 | 2026-06-30 |
| quantocracy | Quantocracy | https://quantocracy.com/feed/ | 10 | 2054 | 2026-07-26 |
| realinvestmentadvice | Real Investment Advice (Lance Roberts) | https://realinvestmentadvice.com/feed/ | 20 | 9694 | 2026-07-27 |
| reason | Reason | https://reason.com/feed/ | 48 | 6222 | 2026-07-27 |
| rust_blog | Rust Blog | https://blog.rust-lang.org/feed.xml | 10 | 13148 | 2026-07-16 |
| scmp_business | SCMP Business | https://www.scmp.com/rss/4/feed | 50 | 498 | 2026-07-27 |
| slack_eng | Slack Engineering | https://slack.engineering/feed/ | 8 | 16353 | 2026-07-14 |
| sovereign_man | Sovereign Man (Simon Black) | https://www.sovereignman.com/feed/ | 50 | 5889 | 2026-07-27 |
| spectrum_ieee | IEEE Spectrum | https://spectrum.ieee.org/feeds/feed.rss | 30 | 9774 | 2026-07-25 |
| spotify_eng | Spotify Engineering | https://engineering.atspotify.com/feed/ | 5 | 231 | 2026-07-20 |
| stackoverflow_blog | The Stack Overflow Blog | https://stackoverflow.blog/feed/ | 40 | 1492 | 2026-07-24 |
| stripe_blog | Stripe Blog | https://stripe.com/blog/feed.rss | 10 | 208 | 2026-07-21 |
| taxfoundation | Tax Foundation | https://taxfoundation.org/feed/ | 20 | 232 | 2026-07-27 |
| technologyreview | MIT Technology Review | https://www.technologyreview.com/feed/ | 10 | 6786 | 2026-07-27 |
| thenewstack | The New Stack | https://thenewstack.io/feed/ | 26 | 6451 | 2026-07-27 |
| theverge | The Verge | https://www.theverge.com/rss/index.xml | 10 | 6975 | 2026-07-27 |
| vercel_blog | Vercel Blog | https://vercel.com/atom | 1380 | 1143 | 2026-07-27 |
| vox | Vox | https://www.vox.com/rss/index.xml | 10 | 10038 | 2026-07-27 |
| war_on_the_rocks | War on the Rocks | https://warontherocks.com/feed/ | 100 | 773 | 2026-07-27 |
| webkit_blog | WebKit Blog | https://webkit.org/feed/ | 10 | 16402 | 2026-07-22 |

## 4. 翻译管线多语言验证

**语言门**：`translation_service.is_chinese_language` 只排除中文变体，ja/de/fr/ko/es 全部进入翻译队列；`scheduler_translate_news._pending_translation_ids` 同样只排除中文——**无需改管线逻辑**。

**已改动**：系统 prompt 从"中英双语"扩展为多语言（"精通英语、日语、德语、法语、韩语、西班牙语等多种语言…原文可能是上述任意一种非中文语言"），正文/标题两个 prompt 同步；模块 docstring 同步更新。新增测试 `TestTranslationMultilingual` 锁定该行为。

**MiniMax 真实 smoke**（2026-07-28，本地 `.env` MiniMax key，取各源首条 title+body 走生产 `provider.chat` + 生产 prompt）：

| 语言 | 源 | 原文标题 | 中文标题 | 正文样例 |
|---|---|---|---|---|
| ja | ZUU online | 日々是相場［夕刊］―― 2026年7月27日（月） | 《日々是相場》晚刊 2026年7月27日（周一） | "日经平均 64,931.19日元 △320.04日元 汇率 1美元＝163.56日元…受原油价格下跌等因素影响，整体表现坚挺，但半导体股走弱…" —— 通顺中文，数字/代码保留，无 think 块 |
| de | netzpolitik.org | Forderungen nach CSD-Anschlag: Schamlose Heuchelei | CSD恐袭后的诉求：恬不知耻的虚伪 | "柏林克里斯托弗街日游行遭遇袭击后，人们深感震惊。然而，基民盟主要政客的反应很容易被揭穿不过是虚伪的表演而已…" —— 无乱码/无 think 块 |
| fr | next.ink | ☕️ OpenAI aurait mis une semaine à s'apercevoir que son agent avait attaqué Hugging Face | OpenAI 据称花了一周才察觉其智能体攻击了 Hugging Face | "7月21日，OpenAI发布了一份令人惊讶的公告：其旗下一个人工智能系统对Hugging Face策划发起了攻击…" —— 专名保留英文，无 think 块 |

## 5. 改动文件清单

| 文件 | 改动 |
|---|---|
| `app/services/news/sources/global_rss_batch.py` | 新增：125 源表 + 12 批次 + `GlobalRssBatchCrawler`（per-feed language/market，`source=global_{slug}`，10 items/feed，2s 礼让延迟） |
| `app/services/news/scheduler_jobs.py` | 新增 `_global_rss_batch_job` 工厂 + `GLOBAL_RSS_BATCH_JOBS`（12 job，不带营销过滤——专业媒体非营销自媒体，对齐 `_simple_rss_job`） |
| `app/core/scheduler.py` | 注册 12 个 `news_global_rss_*_60m` job（60m、max_instances=1、coalesce=True） |
| `app/api/v1/news.py` | `_WORKER_KEYWORDS` 加 `global_rss`；`_WORKER_META` 加 12 条健康网格 meta |
| `app/services/news/sources/rss_common.py` | 修复：Atom 命名空间 title/summary/content/updated 解析 + RSS 1.0 (RDF) item 解析（日本媒体/工程博客必需） |
| `app/services/news/translation_service.py` | 正文+标题 prompt 从"中英双语"扩展为多语言；docstring 同步 |
| `app/tests/news/test_global_rss_batch.py` | 新增 27 个测试：表完整性（唯一性/语言/市场/≥100/五语言覆盖/不与 wechat2rss 重叠）、批次分区、mock 抓取（per-feed source/language/market 映射、失败容错、未知批次）、解析器扩展（Atom/RDF）、调度接线、健康 meta、翻译多语言门 |

## 6. 测试结果

- `python -m pytest app/tests/news/` → **414 passed**（含新增 27）
- 调度接线自检：12 job 物化、函数名正确、health meta 齐全、`global_rss` 关键字命中

## 7. 部署建议

1. **常规 deploy 即可**：12 个 job 随 APScheduler 启动自动注册；首小时各批次陆续入库，`/news/health` 网格可见 `全球多语 RSS A-L 组`。
2. **翻译负载预警**：125 源 × 每批 10 条 × 每小时 → 日增量峰值理论 ~3 万条（实际远低于此，多数博客日更 <5 条）；非中文约 117 源全部进翻译队列。`news_translate_10m` 每 10 分钟一批（`news_translation_batch_size`），建议部署后 24h 观察 MiniMax 用量与队列积压（`title_zh IS NULL` 计数）；若积压可临时调大 batch_size 或缩短间隔。
3. **ECS 网络**：本机（家宽）对 heise/spiegel/lemonde/elpais 等欧洲站点 TCP 不可达导致落选；ECS（阿里云）国际出口通常更优，若后续想补这些源，可在 ECS 上复测 `/tmp/feeds_check` 风格脚本再扩表。
4. **日语全文源稀缺**：日本媒体 RSS 普遍只给一句话摘要（实测淘汰主因），本批仅 7 个日语源达标；后续可评估"摘要入库 + Jina 全文抓取补齐"策略放宽正文门槛（平台已有 `news_full_content_10m` 管线，摘要源正文会由 Jina 补齐后再触发重翻——`translation_is_stale` 机制已覆盖）。
5. **监控**：批次 job 失败会记 `etl_log`（`_record_etl`），健康页可见；单源挂掉不影响同批其他源（per-feed try/except + warning 日志）。建议每周扫一次 `news_article` 中 `global_*` 源 24h 零产出的源，淘汰/换 URL。
