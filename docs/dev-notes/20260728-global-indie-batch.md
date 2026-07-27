# 20260728 全球英文独立源批次 (gind_) Runbook

> 关联文档：[20260728-global-indie-batch-integration.md](20260728-global-indie-batch-integration.md)（集成补丁）、
> [20260727-news-source-expansion.md](20260727-news-source-expansion.md)（前两波背景）。

## 1. 这波做了什么

资讯源扩充第三波：**104 个英文独立资讯源**，全部 ECS 实测存活，模块
`app/services/news/sources/global_indie_batch.py`，`source` 前缀 `gind_`，
10 个批次（o–x，每批 11 个、末批 5 个），每小时一轮。

与前两波及并行波次的关系：

| 波次 | 模块 | 前缀 | 数量 | 内容 |
|---|---|---|---|---|
| 1 | wechat2rss_batch / rss_simple | wechat_* | 90+13 | 公众号镜像 + 13 英文独立博客 |
| 2a | independent_batch | indie_ | 144 | CN/EN 独立博客 + 播客（批次 a–n） |
| 2b | global_rss_batch | global_ | 125 | 日德法韩西媒体 + 英文机构博客（a–l） |
| **3** | **global_indie_batch** | **gind_** | **104** | **英文独立博客/newsletter/研究机构（o–x）** |
| 3-并行 | asia_en_batch | （另一 agent） | — | 亚洲英文源；本波实测合格后移交 6 个亚洲源给它 |

**去重协调记录**：本波最初入选 110 个（含 pandaily / e27 /
dollarsandsense / fifthperson / safalniveshak / strongmoneyaustralia），
与并行 asia_en_batch 波次撞车；主会话裁决这 6 个亚洲源归 asia_en，
本波保留 3 个撞车美源（wallethacks / yetanothervalueblog /
krebsonsecurity）并补入 3 个实测合格备选（responsiblestatecraft /
budgetsaresexy / techsauce），最终 104。

## 2. 选源规则

- 只要独立声音：独立财经/宏观/科技博客、分析师 newsletter（Substack 自定义
  域名、Ghost、beehiiv）、dev.to/Hashnode 深度作者、独立研究机构评论、
  非营利调查新闻室。
- 排除：官方媒体、政府渠道、企业 PR、纯聚合站、营销漏斗站。
- 正文门槛：feed item 必须带真实正文（前 8 条平均 >100 词）。Quanta、
  Naked Capitalism（现为摘要 feed）、AVC（2024-05 停更）等因此淘汰。
- 时效门槛：最新一条 ≤150 天（季度/月度更新的高质量博客也纳入）。
- 网络门槛：以 ECS 实测为准；rsshub.app、*.substack.com 裸域名、blogspot、
  medium.com 主站已知不可达，均未采用。
- market 取值：全部 `us` / `crypto`。**不能用 `global`**——news API 的
  `_GLOBAL_MARKETS` 白名单是 `(cn_a, us, crypto)`，写 `global` 会导致前端
  默认筛选下文章不可见（global_rss 波的历史教训）。

## 3. 实测统计

- 5 轮实测共 **473 个候选 URL**（含同一源换址重试）：入选 **104**，
  移交 asia_en **6**，淘汰 **363**。
- 淘汰分类（按 URL 尝试计）：

| 原因 | 数量 |
|---|---|
| HTTP 403（Cloudflare/反爬拦截 ECS IP） | 104 |
| HTTP 404（feed 地址失效） | 79 |
| 返回非 RSS 内容（反爬挑战页/HTML） | 32 |
| 超时/不可达（GFW 或站点故障） | 14 |
| 其他 | 12 |
| DNS 解析失败（域名失效/被污染） | 11 |
| 正文过薄（均 25 词） | 4 |
| 正文过薄（均 73 词） | 4 |
| 正文过薄（均 14 词） | 4 |
| 正文过薄（均 53 词） | 3 |
| 正文过薄（均 16 词） | 3 |
| 正文过薄（均 13 词） | 3 |
| 正文过薄（均 56 词） | 2 |
| 停更（最新 207 天前） | 2 |
| 停更（最新 552 天前） | 2 |
| 正文过薄（均 66 词） | 2 |
| 正文过薄（均 81 词） | 2 |
| 正文过薄（均 46 词） | 2 |
| 正文过薄（均 76 词） | 2 |
| 正文过薄（均 38 词） | 2 |
| 正文过薄（均 68 词） | 2 |
| 停更（最新 882 天前） | 1 |
| 正文过薄（均 65 词） | 1 |
| 停更（最新 815 天前） | 1 |
| 停更（最新 1285 天前） | 1 |
| 停更（最新 587 天前） | 1 |
| 停更（最新 201 天前） | 1 |
| 停更（最新 2191 天前） | 1 |
| 停更（最新 616 天前） | 1 |
| 停更（最新 457 天前） | 1 |
| 停更（最新 651 天前） | 1 |
| 停更（最新 461 天前） | 1 |
| 正文过薄（均 61 词） | 1 |
| 停更（最新 2393 天前） | 1 |
| 正文过薄（均 24 词） | 1 |
| 正文过薄（均 20 词） | 1 |
| 正文过薄（均 22 词） | 1 |
| 正文过薄（均 79 词） | 1 |
| 正文过薄（均 62 词） | 1 |
| 正文过薄（均 30 词） | 1 |
| 停更（最新 258 天前） | 1 |
| 正文过薄（均 32 词） | 1 |
| 停更（最新 208 天前） | 1 |
| 停更（最新 223 天前） | 1 |
| 正文过薄（均 4 词） | 1 |
| 停更（最新 242 天前） | 1 |
| 正文过薄（均 26 词） | 1 |
| 正文过薄（均 35 词） | 1 |
| 停更（最新 492 天前） | 1 |
| 停更（最新 2293 天前） | 1 |
| 正文过薄（均 54 词） | 1 |
| 停更（最新 216 天前） | 1 |
| 正文过薄（均 21 词） | 1 |
| 停更（最新 357 天前） | 1 |
| 正文过薄（均 23 词） | 1 |
| 正文过薄（均 19 词） | 1 |
| 停更（最新 410 天前） | 1 |
| 停更（最新 280 天前） | 1 |
| 停更（最新 786 天前） | 1 |
| 停更（最新 158 天前） | 1 |
| 停更（最新 971 天前） | 1 |
| 正文过薄（均 49 词） | 1 |
| 正文过薄（均 47 词） | 1 |
| 停更（最新 243 天前） | 1 |
| 正文过薄（均 36 词） | 1 |
| 停更（最新 225 天前） | 1 |
| 正文过薄（均 55 词） | 1 |
| 停更（最新 5023 天前） | 1 |
| 停更（最新 781 天前） | 1 |
| 停更（最新 2162 天前） | 1 |
| 正文过薄（均 8 词） | 1 |
| 停更（最新 957 天前） | 1 |
| 停更（最新 1008 天前） | 1 |
| 停更（最新 1332 天前） | 1 |
| 正文过薄（均 41 词） | 1 |
| 正文过薄（均 72 词） | 1 |
| 停更（最新 685 天前） | 1 |
| 停更（最新 262 天前） | 1 |
| 停更（最新 2268 天前） | 1 |
| 正文过薄（均 18 词） | 1 |
| 停更（最新 1035 天前） | 1 |
| 停更（最新 255 天前） | 1 |
| 停更（最新 2147 天前） | 1 |
| 正文过薄（均 50 词） | 1 |
| 正文过薄（均 63 词） | 1 |
| 停更（最新 361 天前） | 1 |
| 正文过薄（均 15 词） | 1 |
| 正文过薄（均 69 词） | 1 |
| 停更（最新 330 天前） | 1 |
| 停更（最新 1351 天前） | 1 |
| 停更（最新 550 天前） | 1 |
| 停更（最新 693 天前） | 1 |
| 停更（最新 1939 天前） | 1 |

- 实测脚本：urllib + 浏览器 UA，校验 HTTP 200 → XML 可解析 → items>0 →
  正文词数 → 最新条目日期；候选清单与结果保留在 ECS `/tmp/gind_*`（临时）。

## 4. 入选源清单（104，按模块表顺序；实测时间为 2026-07-27/28）

| # | slug | 名称 | 类型 | 最新 | 正文均词数 |
|---|------|------|------|------|-----------|
| 1 | `sinocism` | Sinocism (Bill Bishop) | 宏观/地缘/中国观察 | 3天前 | 1424 |
| 2 | `chinatalk` | ChinaTalk (Jordan Schneider) | 宏观/地缘/中国观察 | 今日 | 6713 |
| 3 | `sinification` | Sinification | 宏观/地缘/中国观察 | 5天前 | 1793 |
| 4 | `merics` | MERICS | 宏观/地缘/中国观察 | 今日 | 1326 |
| 5 | `uncharted` | Uncharted Territories (Tomas Pueyo) | 宏观/地缘/中国观察 | 2天前 | 836 |
| 6 | `justsecurity` | Just Security | 宏观/地缘/中国观察 | 今日 | 3244 |
| 7 | `responsiblestatecraft` | Responsible Statecraft (Quincy Institute) | 宏观/地缘/中国观察 | 今日 | 1070 |
| 8 | `pluralistic` | Pluralistic (Cory Doctorow) | 政策/观点 newsletter | 今日 | 2960 |
| 9 | `betonit` | Bet On It (Bryan Caplan) | 政策/观点 newsletter | 4天前 | 345 |
| 10 | `natesilver` | Silver Bulletin (Nate Silver) | 政策/观点 newsletter | 今日 | 2026 |
| 11 | `gelliottmorris` | Strength In Numbers (G. Elliott Morris) | 政策/观点 newsletter | 今日 | 1287 |
| 12 | `hamiltonnolan` | How Things Work (Hamilton Nolan) | 政策/观点 newsletter | 1天前 | 1914 |
| 13 | `publicnotice` | Public Notice | 政策/观点 newsletter | 今日 | 1546 |
| 14 | `racketnews` | Racket News (Matt Taibbi) | 政策/观点 newsletter | 今日 | 203 |
| 15 | `publicnews` | Public (Michael Shellenberger) | 政策/观点 newsletter | 今日 | 722 |
| 16 | `richardhanania` | Richard Hanania's Newsletter | 政策/观点 newsletter | 今日 | 2689 |
| 17 | `persuasion` | Persuasion | 政策/观点 newsletter | 今日 | 1911 |
| 18 | `aporia` | Aporia | 政策/观点 newsletter | 今日 | 1238 |
| 19 | `unherd` | UnHerd | 政策/观点 newsletter | 今日 | 2512 |
| 20 | `thebulwark` | The Bulwark | 政策/观点 newsletter | 今日 | 725 |
| 21 | `areo` | Areo | 政策/观点 newsletter | 2天前 | 974 |
| 22 | `arcdigital` | Arc Digital | 政策/观点 newsletter | 16天前 | 635 |
| 23 | `thelever` | The Lever | 独立调查/评论媒体 | 1天前 | 350 |
| 24 | `dropsitenews` | Drop Site News | 独立调查/评论媒体 | 今日 | 3303 |
| 25 | `propublica` | ProPublica | 独立调查/评论媒体 | 今日 | 1689 |
| 26 | `palladium` | Palladium | 独立调查/评论媒体 | 6天前 | 4359 |
| 27 | `commoditycontext` | Commodity Context (Rory Johnston) | 经济/思想博客 | 2天前 | 477 |
| 28 | `volts` | Volts (David Roberts) | 经济/思想博客 | 5天前 | 10560 |
| 29 | `sustainabilitybynumbers` | Sustainability by Numbers (Hannah Ritchie) | 经济/思想博客 | 4天前 | 829 |
| 30 | `ageofinvention` | Age of Invention (Anton Howes) | 经济/思想博客 | 124天前 | 7579 |
| 31 | `itep` | ITEP (Just Taxes Blog) | 经济/思想博客 | 今日 | 710 |
| 32 | `employamerica` | Employ America | 经济/思想博客 | 今日 | 384 |
| 33 | `secondbest` | Second Best (Samuel Hammond) | 经济/思想博客 | 61天前 | 2633 |
| 34 | `overcomingbias` | Overcoming Bias (Robin Hanson) | 经济/思想博客 | 2天前 | 523 |
| 35 | `modeledbehavior` | Modeled Behavior | 经济/思想博客 | 12天前 | 606 |
| 36 | `lesswrong` | LessWrong (Curated) | 经济/思想博客 | 2天前 | 3080 |
| 37 | `dynomight` | Dynomight | 经济/思想博客 | 5天前 | >1500 |
| 38 | `themarginalian` | The Marginalian (Maria Popova) | 经济/思想博客 | 今日 | 1314 |
| 39 | `nesslabs` | Ness Labs (Anne-Laure Le Cunff) | 经济/思想博客 | 46天前 | 1820 |
| 40 | `yetanothervalueblog` | Yet Another Value Blog | 投资/量化博客 | 今日 | 566 |
| 41 | `alhambra` | Alhambra Investments (Jeff Snider) | 投资/量化博客 | 今日 | 2287 |
| 42 | `valueplays` | ValuePlays (Todd Sullivan) | 投资/量化博客 | 11天前 | 261 |
| 43 | `litquidity` | Litquidity (Exec Sum) | 投资/量化博客 | 今日 | 1245 |
| 44 | `quantifiableedges` | Quantifiable Edges (Rob Hanna) | 投资/量化博客 | 今日 | 262 |
| 45 | `smbtraining` | SMB Capital Trading Blog | 投资/量化博客 | 8天前 | 792 |
| 46 | `appeconomy` | App Economy Insights | 投资/量化博客 | 2天前 | 1120 |
| 47 | `asiancenturystocks` | Asian Century Stocks | 投资/量化博客 | 1天前 | 994 |
| 48 | `retirementresearcher` | Retirement Researcher (Wade Pfau) | 理财/退休博客 | 2天前 | 1428 |
| 49 | `looniedoctor` | Loonie Doctor | 理财/退休博客 | 27天前 | 1649 |
| 50 | `wallethacks` | Wallet Hacks (Jim Wang) | 理财/退休博客 | 10天前 | 1069 |
| 51 | `esimoney` | ESI Money | 理财/退休博客 | 今日 | 3150 |
| 52 | `moneywithkatie` | Money with Katie | 理财/退休博客 | 13天前 | 1951 |
| 53 | `meaningfulmoney` | Meaningful Money (Pete Matthew) | 理财/退休博客 | 5天前 | 1452 |
| 54 | `mrsmummypenny` | Mrs Mummypenny | 理财/退休博客 | 5天前 | 1125 |
| 55 | `moneytothemasses` | Money to the Masses | 理财/退休博客 | 今日 | 2039 |
| 56 | `budgetsaresexy` | Budgets Are Sexy | 理财/退休博客 | 14天前 | 809 |
| 57 | `newscientist` | New Scientist | 科学杂志 | 今日 | 317 |
| 58 | `wheresyoured` | Where's Your Ed At (Ed Zitron) | 科技/产品 newsletter | 2天前 | 6000 |
| 59 | `newcomer` | Newcomer (Eric Newcomer) | 科技/产品 newsletter | 3天前 | 767 |
| 60 | `exponentialview` | Exponential View (Azeem Azhar) | 科技/产品 newsletter | 今日 | 664 |
| 61 | `statecraft` | Statecraft (Santi Ruiz) | 科技/产品 newsletter | 40天前 | 5847 |
| 62 | `lenny` | Lenny's Newsletter | 科技/产品 newsletter | 今日 | 992 |
| 63 | `refactoring` | Refactoring (Luca Rossi) | 科技/产品 newsletter | 今日 | 667 |
| 64 | `producttalk` | Product Talk (Teresa Torres) | 科技/产品 newsletter | 4天前 | 668 |
| 65 | `benedicttevans` | Benedict Evans | 科技/产品 newsletter | 18天前 | 1668 |
| 66 | `eladgil` | Elad Gil | 科技/产品 newsletter | 98天前 | 2651 |
| 67 | `dhh` | DHH (37signals) | 科技/产品 newsletter | 今日 | 699 |
| 68 | `jasonfried` | Jason Fried (37signals) | 科技/产品 newsletter | 2天前 | 287 |
| 69 | `techsauce` | Techsauce (SEA) | 科技/产品 newsletter | 今日 | 502 |
| 70 | `daringfireball` | Daring Fireball (John Gruber) | 独立技术博客 | 今日 | 212 |
| 71 | `marcoorg` | Marco.org (Marco Arment) | 独立技术博客 | 116天前 | 565 |
| 72 | `pragmaticengineer` | The Pragmatic Engineer (Gergely Orosz) | 独立技术博客 | 4天前 | 1087 |
| 73 | `bytebytego` | ByteByteGo (Alex Xu) | 独立技术博客 | 今日 | 2097 |
| 74 | `charitywtf` | Charity Majors | 独立技术博客 | 18天前 | 2228 |
| 75 | `codinghorror` | Coding Horror (Jeff Atwood) | 独立技术博客 | 34天前 | 1529 |
| 76 | `macwright` | Tom MacWright | 独立技术博客 | 3天前 | 925 |
| 77 | `jimnielsen` | Jim Nielsen's Blog | 独立技术博客 | 今日 | 579 |
| 78 | `adactio` | Adactio (Jeremy Keith) | 独立技术博客 | 11天前 | 392 |
| 79 | `drewdevault` | Drew DeVault | 独立技术博客 | 4天前 | 730 |
| 80 | `lucumr` | Armin Ronacher's Thoughts | 独立技术博客 | 3天前 | 1424 |
| 81 | `xeiaso` | Xe Iaso | 独立技术博客 | 13天前 | 1159 |
| 82 | `endler` | Matthias Endler | 独立技术博客 | 54天前 | 2219 |
| 83 | `jakewharton` | Jake Wharton | 独立技术博客 | 11天前 | 821 |
| 84 | `hackingwithswift` | Hacking with Swift (Paul Hudson) | 独立技术博客 | 72天前 | 281 |
| 85 | `freecodecamp` | freeCodeCamp | 独立技术博客 | 2天前 | 2865 |
| 86 | `devtoben` | Ben Halpern (dev.to) | dev.to/Hashnode 作者 | 今日 | 189 |
| 87 | `hashnodetapas` | Tapas Adhikary (Hashnode) | dev.to/Hashnode 作者 | 6天前 | 1748 |
| 88 | `krebsonsecurity` | Krebs on Security | 安全/半导体 | 5天前 | 1179 |
| 89 | `troyhunt` | Troy Hunt | 安全/半导体 | 1天前 | 288 |
| 90 | `danielmiessler` | Daniel Miessler | 安全/半导体 | 4天前 | 650 |
| 91 | `trailofbits` | Trail of Bits Blog | 安全/半导体 | 14天前 | 1582 |
| 92 | `media404` | 404 Media | 安全/半导体 | 今日 | 832 |
| 93 | `theregister` | The Register | 安全/半导体 | 今日 | 1001 |
| 94 | `osnews` | OSNews | 安全/半导体 | 今日 | 209 |
| 95 | `itsfoss` | It's FOSS | 安全/半导体 | 今日 | 913 |
| 96 | `chipsandcheese` | Chips and Cheese | 安全/半导体 | 3天前 | 2169 |
| 97 | `fabricatedknowledge` | Fabricated Knowledge (Doug O'Laughlin) | 安全/半导体 | 32天前 | 3163 |
| 98 | `transformer` | Transformer (Shakeel Hashim) | AI 研究/分析 | 3天前 | 2041 |
| 99 | `interconnects` | Interconnects (Nathan Lambert) | AI 研究/分析 | 5天前 | 3787 |
| 100 | `aheadofai` | Ahead of AI (Sebastian Raschka) | AI 研究/分析 | 9天前 | 4251 |
| 101 | `lastweekinai` | Last Week in AI | AI 研究/分析 | 6天前 | 544 |
| 102 | `bairblog` | BAIR Blog (Berkeley) | AI 研究/分析 | 1天前 | 2370 |
| 103 | `unchained` | Unchained (Laura Shin) | Crypto 独立 | 今日 | 360 |
| 104 | `bitmexresearch` | BitMEX Research | Crypto 独立 | 4天前 | 876 |

## 5. 淘汰记录（363 个 URL 尝试，按原因聚合）

正文过薄/停更的代表：Naked Capitalism（摘要 feed）、Quanta、Undark、
Canary Media、The Diplomat、AVC（2024-05 停更）、Andrew Chen（停更）、
Get Rich Slowly（停更）、The Diff（feed 停滞 2022）、Margins（361 天）、
Asianometry（552 天）、Napkin Math（平台迁移 461 天）、NSHipster（208 天）、
Swift by Sundell（330 天）、Dan Wang（年度长文 207 天）、The Gradient（158 天）。

403/挑战页代表：Epsilon Theory、Felder Report、Macro Hive、Kitces、
Mr. Money Mustache、Afford Anything、JL Collins、Schneier、Joel on Software、
Roots of Progress、AEI、Brookings、Cato、The Block、Glassnode、Cal Newport、
Cafe Hayek、Angry Bear、Rest of World、East Asia Forum、Mercatus。

超时/DNS/不可达代表：FedGuy（超时）、Macro Tourist（超时）、Kuppy（DNS）、
Rachel by the Bay（IPv6 不可达）、Kevin Erdmann（No route to host）、
Can We Still Govern（DNS）、Stumbling and Mumbling（DNS）。

移交 asia_en_batch 的 6 个（实测合格，因主题归属移交）：Pandaily、
e27、DollarsAndSense、The Fifth Person、Safal Niveshak、Strong Money
Australia。

完整清单（URL + 实测返回）：

<details><summary>展开 363 行淘汰明细</summary>

| URL | 实测结果/原因 |
|---|---|
| http://highscalability.com/rss.xml | HTTP 404（feed 地址失效） |
| http://www.aaronsw.com/2002/feeds/pg.rss | HTTP 404（feed 地址失效） |
| https://aeon.co/feed.rss | 正文过薄（均 25 词） |
| https://affordanything.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://alephblog.com/feed/ | 超时/不可达（GFW 或站点故障） |
| https://allstarcharts.com/feed | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://alvarezquanttrading.com/blog/feed/ | 正文过薄（均 56 词） |
| https://andrewbatson.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://andrewchen.com/feed/ | 停更（最新 882 天前） |
| https://angrybearblog.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://apurplelife.com/feed/ | 正文过薄（均 65 词） |
| https://architectelevator.com/feed/ | HTTP 404（feed 地址失效） |
| https://asia.nikkei.com/rss/feed/nar | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://austinvernon.site/feed | HTTP 404（feed 地址失效） |
| https://austrianeconomists.typepad.com/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://avc.com/feed/ | 停更（最新 815 天前） |
| https://baselinescenario.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://blog.acolyer.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://blog.catalins.tech/rss.xml | DNS 解析失败（域名失效/被污染） |
| https://blog.cleancoder.com/atom.xml | 停更（最新 1285 天前） |
| https://blog.garrytan.com/feed | HTTP 404（feed 地址失效） |
| https://blog.samaltman.com/rss | HTTP 404（feed 地址失效） |
| https://blog.supplysideliberal.com/feed | HTTP 404（feed 地址失效） |
| https://blog.thinknewfound.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://blogs.cfainstitute.org/investor/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://boingboing.net/feed | 正文过薄（均 73 词） |
| https://boockreport.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://bothsidesofthetable.com/feed | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://bothsidesofthetable.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://cafehayek.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://calnewport.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://canadiancouchpotato.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://capitalmind.in/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://capx.co/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://caravanmagazine.in/rss | HTTP 404（feed 地址失效） |
| https://carnegieendowment.org/rss.xml | HTTP 404（feed 地址失效） |
| https://catalins.tech/rss.xml | HTTP 404（feed 地址失效） |
| https://cei.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://cepr.org/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://cheaptalk.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://chinabooksreview.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://chinaglobalsouth.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://chriscoyier.net/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://ciechanow.ski/atom.xml | 停更（最新 587 天前） |
| https://clubthrifty.com/feed/ | 停更（最新 201 天前） |
| https://corrode.dev/blog/rss | HTTP 404（feed 地址失效） |
| https://danwang.co/feed/ | 停更（最新 207 天前） |
| https://delong.typepad.com/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://dev.to/feed/lydiahallie | 停更（最新 2191 天前） |
| https://dividendcafe.com/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://drwealth.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://eatsleepbreathefi.com/feed/ | 停更（最新 616 天前） |
| https://ecfr.eu/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://economicprincipals.com/feed/ | 停更（最新 457 天前） |
| https://economicsone.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://economistsview.typepad.com/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://elements.benchmarkminerals.com/feed | DNS 解析失败（域名失效/被污染） |
| https://elidourado.com/feed/ | 停更（最新 651 天前） |
| https://epbmacroresearch.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://equitablegrowth.org/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://every.to/napkin-math/feed | 停更（最新 461 天前） |
| https://every.to/rss | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://evonomics.com/feed/ | 停更（最新 552 天前） |
| https://fasterthanli.me/index.xml | 停更（最新 207 天前） |
| https://fedguy.com/feed/ | 超时/不可达（GFW 或站点故障） |
| https://fee.org/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://feeds.kottke.org/main | 正文过薄（均 66 词） |
| https://fftt-llc.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://financialpanther.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://fivebooks.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://fleckensteincapital.com/feed/ | HTTP 404（feed 地址失效） |
| https://fullstackeconomics.com/feed/ | DNS 解析失败（域名失效/被污染） |
| https://geopoliticalfutures.com/feed/ | 正文过薄（均 81 词） |
| https://gorozen.com/feed | HTTP 404（feed 地址失效） |
| https://gorozen.com/feed/ | HTTP 404（feed 地址失效） |
| https://growthecon.com/feed | HTTP 404（feed 地址失效） |
| https://growthecon.com/feed/ | HTTP 404（feed 地址失效） |
| https://heatmap.news/feed | HTTP 404（feed 地址失效） |
| https://heatmap.news/rss.xml | HTTP 404（feed 地址失效） |
| https://hedgehogreview.com/rss | HTTP 404（feed 地址失效） |
| https://hunterwalk.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://hynek.me/articles/feed/ | HTTP 404（feed 地址失效） |
| https://hynek.me/rss.xml | HTTP 404（feed 地址失效） |
| https://insights.glassnode.com/rss/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://investmenttalk.co/feed | DNS 解析失败（域名失效/被污染） |
| https://investresolve.com/feed/ | 超时/不可达（GFW 或站点故障） |
| https://ivanhoff.com/feed/ | 正文过薄（均 61 词） |
| https://jamesclear.com/feed | 停更（最新 2393 天前） |
| https://jingdaily.com/feed/ | 其他 |
| https://jlcollinsnh.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://journeytolaunch.com/feed/ | 超时/不可达（GFW 或站点故障） |
| https://jwmason.org/slackwire/feed | HTTP 404（feed 地址失效） |
| https://jwmason.org/slackwire/feed/ | HTTP 404（feed 地址失效） |
| https://kentcdodds.com/blog/rss.xml | 正文过薄（均 24 词） |
| https://kottke.org/feed | HTTP 404（feed 地址失效） |
| https://kr-asia.com/feed | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://kuppycorner.com/feed | DNS 解析失败（域名失效/被污染） |
| https://leaddev.com/rss.xml | 正文过薄（均 20 词） |
| https://leerob.io/rss | HTTP 404（feed 地址失效） |
| https://lethain.com/atom.xml | HTTP 404（feed 地址失效） |
| https://linuxiac.com/feed/ | 正文过薄（均 22 词） |
| https://lo-victoria.com/rss.xml | 正文过薄（均 25 词） |
| https://lwn.net/headlines/rss | 正文过薄（均 79 词） |
| https://macro-ops.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://macrohive.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://macropolo.org/feed | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://macropolo.org/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://marketmonetarist.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://martin.kleppmann.com/feed.xml | HTTP 404（feed 地址失效） |
| https://mattlakeman.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://maynardpaton.com/feed/ | 正文过薄（均 62 词） |
| https://mbideepdives.com/feed | DNS 解析失败（域名失效/被污染） |
| https://mcfunley.com/feed | HTTP 404（feed 地址失效） |
| https://mebfaber.com/feed/ | 正文过薄（均 46 词） |
| https://merionwest.com/feed/ | 其他 |
| https://mises.org/rss.xml | 正文过薄（均 30 词） |
| https://mishtalk.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://moneyguy.com/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://muchmorewithless.co.uk/feed/ | 停更（最新 258 天前） |
| https://mwi.westpoint.edu/feed/ | 正文过薄（均 53 词） |
| https://nasawatch.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://nautil.us/feed | 正文过薄（均 32 词） |
| https://nedbatchelder.com/blog/rss.xml | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://nedbatchelder.com/rss.xml | HTTP 404（feed 地址失效） |
| https://nshipster.com/feed.xml | 停更（最新 208 天前） |
| https://nucleuswealth.com/feed/ | HTTP 404（feed 地址失效） |
| https://objective-see.org/blog.xml | HTTP 404（feed 地址失效） |
| https://oleb.net/blog/atom.xml | 停更（最新 223 天前） |
| https://ourworldindata.org/atom.xml | 正文过薄（均 16 词） |
| https://overreacted.io/rss.xml | 正文过薄（均 4 词） |
| https://patrickcollison.com/feed | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://perell.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://portfoliocharts.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://predictnow.ai/feed | 停更（最新 242 天前） |
| https://press.asimov.com/feed | HTTP 404（feed 地址失效） |
| https://press.asimov.com/rss | HTTP 404（feed 地址失效） |
| https://progress.institute/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://psyche.co/feed.rss | 正文过薄（均 26 词） |
| https://putanumonit.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://quartr.com/feed | HTTP 404（feed 地址失效） |
| https://quillette.com/feed/ | HTTP 404（feed 地址失效） |
| https://quillintelligence.com/feed/ | 正文过薄（均 35 词） |
| https://quincyinst.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://rachelbythebay.com/w/atom.xml | 超时/不可达（GFW 或站点故障） |
| https://raphlinus.github.io/feed.xml | 停更（最新 492 天前） |
| https://rauchg.com/rss | 其他 |
| https://restofworld.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://retireby40.org/feed/ | 超时/不可达（GFW 或站点故障） |
| https://rickferri.com/feed/ | 停更（最新 2293 天前） |
| https://risky.biz/feeds/risky-business-news/ | 正文过薄（均 54 词） |
| https://robertbryce.com/feed | HTTP 404（feed 地址失效） |
| https://robotwealth.com/feed/ | 正文过薄（均 73 词） |
| https://rodrik.typepad.com/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://rooseveltinstitute.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://rootsofprogress.org/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://rortybomb.wordpress.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://routetoretire.com/feed/ | 正文过薄（均 81 词） |
| https://samwho.dev/rss.xml | 停更（最新 216 天前） |
| https://santiagocapital.com/feed | 超时/不可达（GFW 或站点故障） |
| https://sarahtavel.com/feed | DNS 解析失败（域名失效/被污染） |
| https://scottaaronson.blog/?feed=rss2 | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://semianalysis.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://semilshah.com/feed/ | 超时/不可达（GFW 或站点故障） |
| https://semiwiki.com/feed/ | 正文过薄（均 66 词） |
| https://seths.blog/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://simplelivinginsuffolk.co.uk/feed/ | DNS 解析失败（域名失效/被污染） |
| https://sinopsis.cz/en/feed/ | 正文过薄（均 21 词） |
| https://sixfigureinvesting.com/feed/ | 停更（最新 357 天前） |
| https://skintdad.co.uk/feed/ | 正文过薄（均 76 词） |
| https://speedwellresearch.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://stenoresearch.com/feed | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://stumblingandmumbling.com/feeds/posts/default | DNS 解析失败（域名失效/被污染） |
| https://surfingcomplexity.blog/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://tailscale.com/blog/rss | HTTP 404（feed 地址失效） |
| https://technode.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://theblindspot.io/feed | HTTP 404（feed 地址失效） |
| https://theconversation.com/us/articles.atom | 正文过薄（均 23 词） |
| https://thecritic.co.uk/feed/ | 正文过薄（均 14 词） |
| https://thediplomat.com/feed/ | 正文过薄（均 19 词） |
| https://thedispatch.com/feed/ | 正文过薄（均 14 词） |
| https://theescapeartist.me/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://thefinancezombie.com/feed/ | 停更（最新 410 天前） |
| https://thefioneers.com/feed/ | 停更（最新 280 天前） |
| https://thefrugalcottage.com/feed/ | 停更（最新 786 天前） |
| https://thegradient.pub/rss/ | 停更（最新 158 天前） |
| https://theirrelevantinvestor.com/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://themacrocompass.com/feed | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://themacrotourist.com/feed | 超时/不可达（GFW 或站点故障） |
| https://themarketear.com/feed | HTTP 404（feed 地址失效） |
| https://themarketear.com/rss | HTTP 404（feed 地址失效） |
| https://thepointmag.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://thereformedbroker.com/feed/ | 停更（最新 971 天前） |
| https://thewire.in/rss | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://thezvi.wordpress.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://this-week-in-rust.org/atom.xml | 正文过薄（均 49 词） |
| https://tomtunguz.com/index.xml | 正文过薄（均 38 词） |
| https://tomtunguz.com/rss/ | HTTP 404（feed 地址失效） |
| https://tonsky.me/atom.xml | 正文过薄（均 13 词） |
| https://triviumchina.com/feed | 正文过薄（均 47 词） |
| https://undark.org/feed/ | 正文过薄（均 46 词） |
| https://uneasymoney.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://verdadcap.com/feed | HTTP 404（feed 地址失效） |
| https://waitbutwhy.com/feed | 停更（最新 243 天前） |
| https://waxy.org/feed/ | 正文过薄（均 16 词） |
| https://westhunt.wordpress.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://without.boats/blog/atom.xml | HTTP 404（feed 地址失效） |
| https://worksinprogress.co/feed | HTTP 404（feed 地址失效） |
| https://worksinprogress.co/feed.xml | HTTP 404（feed 地址失效） |
| https://worthwhile.typepad.com/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.9dashline.com/feed/ | HTTP 404（feed 地址失效） |
| https://www.advisorperspectives.com/rss | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.aei.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.albertbridgecapital.com/blog-feed | HTTP 404（feed 地址失效） |
| https://www.allthingsdistributed.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.andrewwilkinson.com/feed | 超时/不可达（GFW 或站点故障） |
| https://www.arnoldkling.com/blog/feed/ | 超时/不可达（GFW 或站点故障） |
| https://www.asianometry.com/feed | 停更（最新 552 天前） |
| https://www.aspistrategist.org.au/feed/ | 正文过薄（均 36 词） |
| https://www.atlanticcouncil.org/rss.xml | HTTP 404（feed 地址失效） |
| https://www.aussiefirebug.com/feed/ | 停更（最新 225 天前） |
| https://www.avanderlee.com/feed/ | 正文过薄（均 73 词） |
| https://www.bitsaboutmoney.com/archive/rss.xml | HTTP 404（feed 地址失效） |
| https://www.boomerandecho.com/feed/ | 正文过薄（均 55 词） |
| https://www.bradford-delong.com/feed | 其他 |
| https://www.brookings.edu/feed | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.brookings.edu/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.bruegel.org/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.canadianbudgetbinder.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.canarymedia.com/feed | 正文过薄（均 53 词） |
| https://www.caniretireyet.com/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.canwestillgovern.com/feed | DNS 解析失败（域名失效/被污染） |
| https://www.cato.org/blog/rss.xml | HTTP 404（feed 地址失效） |
| https://www.cato.org/rss | HTTP 404（feed 地址失效） |
| https://www.cbpp.org/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.ceps.eu/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.chathamhouse.org/rss | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.chinafile.com/rss | HTTP 404（feed 地址失效） |
| https://www.chinafile.com/rss.xml | 停更（最新 5023 天前） |
| https://www.choosefi.com/feed/ | 正文过薄（均 25 词） |
| https://www.ciphernews.com/feed/ | 其他 |
| https://www.city-journal.org/rss.xml | 正文过薄（均 13 词） |
| https://www.cnas.org/rss.xml | HTTP 404（feed 地址失效） |
| https://www.commentary.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.coppolacomment.com/feeds/posts/default | 停更（最新 781 天前） |
| https://www.crfb.org/rss.xml | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.crisisgroup.org/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.crossbordercapital.com/feed | 其他 |
| https://www.dealstreetasia.com/feed | 其他 |
| https://www.defensepriorities.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.doctorhousingbubble.com/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.donnywals.com/feed/ | 正文过薄（均 73 词） |
| https://www.eastasiaforum.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.epi.org/feed/ | 停更（最新 2162 天前） |
| https://www.epsilontheory.com/feed/ | HTTP 404（feed 地址失效） |
| https://www.epsilontheory.com/rss.xml | HTTP 404（feed 地址失效） |
| https://www.evergreengavekal.com/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.evidenceinvestor.com/feed/ | HTTP 404（feed 地址失效） |
| https://www.fdd.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.firstlinks.com.au/rss | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.foreignaffairs.com/rss.xml | 正文过薄（均 8 词） |
| https://www.foreignbrief.com/feed/ | 其他 |
| https://www.fpri.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.frugalwoods.com/feed/ | 停更（最新 957 天前） |
| https://www.fullstackeconomics.com/feed | 停更（最新 1008 天前） |
| https://www.garbageday.email/feed | HTTP 404（feed 地址失效） |
| https://www.geopoliticalmonitor.com/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.getrichslowly.org/feed/ | 停更（最新 1332 天前） |
| https://www.gmfus.org/rss.xml | 正文过薄（均 14 词） |
| https://www.gocurrycracker.com/feed/ | HTTP 404（feed 地址失效） |
| https://www.goodfinancialcents.com/feed/ | 其他 |
| https://www.hillelwayne.com/post/index.xml | 正文过薄（均 68 词） |
| https://www.hongkongfp.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.hoover.org/rss.xml | 正文过薄（均 41 词） |
| https://www.hudson.org/rss.xml | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.iiss.org/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.importantnotimportant.com/feed | HTTP 404（feed 地址失效） |
| https://www.independent.org/feed/ | 正文过薄（均 72 词） |
| https://www.ineteconomics.org/perspectives/blog/rss | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.interfluidity.com/feed | 停更（最新 685 天前） |
| https://www.internationalintrigue.io/feed | HTTP 404（feed 地址失效） |
| https://www.jessesquires.com/feed.xml | 停更（最新 262 天前） |
| https://www.joelonsoftware.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.joshwcomeau.com/rss.xml | 正文过薄（均 56 词） |
| https://www.julian.com/feed | HTTP 404（feed 地址失效） |
| https://www.kalzumeus.com/feed/ | 其他 |
| https://www.kennorton.com/feed | HTTP 404（feed 地址失效） |
| https://www.kevinerdmann.com/feed | 超时/不可达（GFW 或站点故障） |
| https://www.kitces.com/blog/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.kitces.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.kuppycorner.com/feed | DNS 解析失败（域名失效/被污染） |
| https://www.lawfaremedia.org/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.listenmoneymatters.com/feed/ | 停更（最新 2268 天前） |
| https://www.lowyinstitute.org/the-interpreter/rss | 正文过薄（均 18 词） |
| https://www.lykeion.com/feed | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.macrobusiness.com.au/feed/ | 正文过薄（均 68 词） |
| https://www.macroption.com/feed/ | HTTP 404（feed 地址失效） |
| https://www.makingsenseofcents.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.marctomarket.com/feed/ | HTTP 404（feed 地址失效） |
| https://www.mauldineconomics.com/frontlinethoughts/rss | HTTP 404（feed 地址失效） |
| https://www.mercatus.org/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.mrmoneymustache.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.mrtakoescapes.com/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.myownadvisor.ca/feed/ | 超时/不可达（GFW 或站点故障） |
| https://www.nakedcapitalism.com/feed | 正文过薄（均 13 词） |
| https://www.nateliason.com/feed | HTTP 404（feed 地址失效） |
| https://www.nationalreview.com/feed/ | 正文过薄（均 14 词） |
| https://www.nature.com/nature.rss | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.newslaundry.com/rss | HTTP 404（feed 地址失效） |
| https://www.newthingsunderthesun.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.newtraderu.com/feed/ | 其他 |
| https://www.oaktreecapital.com/rss | HTTP 404（feed 地址失效） |
| https://www.objc.io/feed.xml | 停更（最新 1035 天前） |
| https://www.omfif.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.omgubuntu.co.uk/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.patkua.com/blog/feed/ | 停更（最新 255 天前） |
| https://www.phenomenalworld.org/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.philosophicaleconomics.com/feed | 停更（最新 2147 天前） |
| https://www.phoronix.com/rss.php | 正文过薄（均 50 词） |
| https://www.piie.com/rss | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.piie.com/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.pointfree.co/blog/feed.xml | HTTP 404（feed 地址失效） |
| https://www.pragcap.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.projectoption.com/feed/ | HTTP 404（feed 地址失效） |
| https://www.prospectmagazine.co.uk/feed | HTTP 404（feed 地址失效） |
| https://www.publicbooks.org/feed | 超时/不可达（GFW 或站点故障） |
| https://www.quantamagazine.org/feed/ | 正文过薄（均 63 词） |
| https://www.quantstart.com/feed/ | 正文过薄（均 53 词） |
| https://www.rand.org/pubs/rss.xml | HTTP 404（feed 地址失效） |
| https://www.rand.org/rss.xml | HTTP 404（feed 地址失效） |
| https://www.readmargins.com/feed | 停更（最新 361 天前） |
| https://www.rstreet.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.rusi.org/rss.xml | HTTP 404（feed 地址失效） |
| https://www.saastr.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.savvynewcanadians.com/feed/ | 正文过薄（均 76 词） |
| https://www.schneier.com/feed/atom/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.science.org/rss/news_current.xml | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.scientificamerican.com/feed/ | HTTP 404（feed 地址失效） |
| https://www.semianalysis.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.shreyasdoshi.com/feed | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.spectator.co.uk/rss | HTTP 404（feed 地址失效） |
| https://www.spiked-online.com/feed/ | 正文过薄（均 15 词） |
| https://www.stimson.org/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.svpg.com/feed/ | 正文过薄（均 69 词） |
| https://www.swiftbysundell.com/feed.rss | 停更（最新 330 天前） |
| https://www.swyx.io/rss.xml | 正文过薄（均 25 词） |
| https://www.tawcan.com/feed/ | 正文过薄（均 38 词） |
| https://www.techdirt.com/feed.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.techinasia.com/feed | 正文过薄（均 16 词） |
| https://www.thearmchairtrader.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.theblock.co/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.thediff.co/feed | 停更（最新 1351 天前） |
| https://www.thefelderreport.com/feed | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.themeasureofaplan.com/feed/ | 停更（最新 550 天前） |
| https://www.themoneyillusion.com/feed | 停更（最新 693 天前） |
| https://www.thenewatlantis.com/feed | 停更（最新 1939 天前） |
| https://www.thenewhumanitarian.org/rss.xml | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.thepragmaticinvestor.com/feed | HTTP 404（feed 地址失效） |
| https://www.thewirechina.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.turingfinance.com/feed/ | 返回非 RSS 内容（反爬挑战页/HTML） |
| https://www.ukvalueinvestor.com/feed/ | HTTP 403（Cloudflare/反爬拦截 ECS IP） |
| https://www.variantperception.com/feed | HTTP 404（feed 地址失效） |
| https://www.variantperception.com/feed/ | HTTP 404（feed 地址失效） |
| https://www.whatsonweibo.com/feed/ | 其他 |
</details>

## 6. 运维要点

- **批次**：o–x 共 10 个 hourly job（`news_gind_o_60m` … `news_gind_x_60m`），
  每批 11 源串行 + 2s 礼貌间隔，单批约 30–60s。
- **无 LLM 营销过滤**：与 independent_batch 同先例（编辑策划源），写库直接
  进行，LLM 成本不随源数增长。
- **翻译**：全部 `language='en'`，`news_translate_10m` 自动拾取（翻译服务
  只排除中文变体）。
- **失败自愈**：单源失败仅记 warning，不影响批次内其他源；某源连续失败
  多天时先从本 runbook 的淘汰原因表对照（403/停更最常见），再决定换址
  或剔除。
- **健康格**：集成后 `_WORKER_META` 含 10 个 gind 条目，前端健康面板可见。
