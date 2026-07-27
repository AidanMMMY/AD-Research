# 亚洲英文 RSS 批次（asia_en）Runbook

日期：2026-07-28 ｜ 执行：子 agent C（资讯源扩充第三轮）｜ 状态：**待主会话集成**（集成代码块见 [20260728-asia-en-batch-integration.md](20260728-asia-en-batch-integration.md)）

## 1. 结论

- **交付 176 个英文 RSS 源**，全部从生产 ECS（中国大陆网络）实测通过，分两批 16 组（a–p，每组 ≤11 个），每小时一轮。
- 候选 **664 个**，两轮实测通过 185 个；剔除 9 个（6 个编辑判断 + 3 个美源按主会话裁决归并行 `global_indie_batch` 波次）后定稿 **176** 个。
- **主会话裁决（2026-07-28）**：与 `gind_` 波次重叠的 9 个 URL 中，6 个亚洲源（Pandaily、e27、DollarsAndSense、Fifth Person、Safal Niveshak、Strong Money Australia）归本批次，3 个美源（Krebs on Security、Wallet Hacks、Yet Another Value Blog）归 `gind_` 批次。
- 淘汰 **479 个**（HTTP 403/404/超时/非 RSS/正文过短/停更），全部原因逐条记录在第 5 节。
- 与现有全部源（`sources/` 目录所有模块 + `scheduler_jobs.py` + 并行的 `global_indie_batch` / `wechat2rss_batch2`）**URL 零重叠**（测试内有回归守卫）。

### 1.1 与前三波的关系

| 波次 | 模块 | 规模 | 定位 |
|---|---|---|---|
| 1 | `independent_batch` | 144 | 中英独立博客/播客 |
| 2 | `global_rss_batch` | 125 | 多语种媒体（日德法韩西）+ 英文央行/智库/工程博客 |
| 2b | `wechat2rss_batch2` / `global_indie_batch`（并行） | — | 公众号镜像补波 / 英文独立声音（自定义域 newsletter 等） |
| **3（本波）** | **`asia_en_batch`** | **176** | **亚洲英文财经媒体 + 国际栏目 feed + 行业垂直 + 投资者博客** |

### 1.2 分布

| 类别 | 数量 |
|---|---|
| 亚洲英文财经媒体 | 45 |
| 国际媒体栏目 feed | 20 |
| 半导体/硬件 | 7 |
| 新能源/油气 | 12 |
| 生物医药 | 7 |
| 汽车 | 5 |
| 航运物流 | 9 |
| 大宗商品/矿业/农业 | 10 |
| 其他行业垂直（航天/防务/金融科技/零售/地产/监管等） | 18 |
| 智库/机构/地缘 | 7 |
| 个人投资者博客（自建站） | 36 |
| **合计** | **176** |

## 2. 验证方法（可复跑）

从本机 `scp` 上传候选清单与验证脚本到 ECS，全部实测在生产网络完成：

```bash
scp check_feeds.py candidates.txt ad-research:/tmp/
ssh ad-research 'python3 /tmp/check_feeds.py /tmp/candidates.txt'
```

`check_feeds.py`（stdlib only，16 并发 curl）对每个候选执行：

1. `curl -sS -L --max-time 15` + 浏览器 UA → 必须 HTTP 200；
2. 前 2KB 含 `<rss` / `<feed` / `<rdf` 标记；
3. `<item>` / `<entry>` ≥ 1；
4. 前 10 条目的 `content:encoded|content|description|summary` 去标签后**平均 ≥150 字符**（保证翻译管线有实质正文）；
5. 可解析日期时，最新条目距今 **≤60 天**。

脚本与本报告同源保存于 ECS `/tmp/check_feeds.py`（临时路径，重跑需从本机重新上传）。

### 2.1 淘汰原因统计（两轮合计 664 候选 → 479 淘汰）

| 原因 | 数量 | 说明 |
|---|---|---|
| HTTP 403（Cloudflare/WAF 拦中国大陆 IP） | 170 | Livemint、Business Standard、CleanTechnica、The Diplomat、FreightWaves 等 |
| HTTP 404（feed 已下线/改版） | 107 | Nikkei Asia、NHK World、FT/WSJ 栏目、Automotive News 等 |
| 连接超时/GFW 重置 | 35 | CNA、Taipei Times、Focus Taiwan、Bangkok Post、SCMP 其他版等 |
| HTTP 406 | 2 | 内容协商被拒（个别印度媒体） |
| 返回非 RSS（HTML） | 46 | AP hub、NPR 个别、Yonhap 等 |
| XML 无条目 | 7 | — |
| 正文过短（<150 字符） | 75 | 只发标题/一句话摘要的 feed |
| 停更（最新条目 >60 天） | 26 | Cheerful Egg、Fundoo Professor 等休眠博客 |
| 其他 HTTP 错误 | 11 | 5xx/3xx 异常等 |
| **合计** | **479** | |

## 3. 收录源清单（176，按类别）

> avg_body = 前 10 条目平均正文字符数；latest = 最新条目日期（验证日 2026-07-28，空值表示日期字段解析失败但其余检查全过）。

### 3.1 亚洲英文财经媒体（45）

| slug | 名称 | market | avg_body | 最新条目 | feed |
|---|---|---|---|---|---|
| asen_abc_au_business | ABC News Business (AU) | us | 152 | 2026-07-27 | https://www.abc.net.au/news/feed/51120/rss.xml |
| asen_chinadaily_biz | China Daily Business | cn_a | 1381 |  | https://www.chinadaily.com.cn/rss/bizchina_rss.xml |
| asen_cnbctv18 | CNBC-TV18 | us | 279 | 2026-07-27 | https://www.cnbctv18.com/commonfeeds/v1/cne/rss/latest.xml |
| asen_dailystar_bd | The Daily Star Business (BD) | us | 171 | 2026-07-28 | https://www.thedailystar.net/business/rss.xml |
| asen_dawn_business | Dawn Business (PK) | us | 4294 | 2026-07-27 | https://www.dawn.com/feeds/business/ |
| asen_dhakatribune_biz | Dhaka Tribune Business | us | 409 | 2026-07-27 | https://www.dhakatribune.com/feed/business |
| asen_et_economy | Economic Times Economy | us | 368 | 2026-07-27 | https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms |
| asen_et_industry | Economic Times Industry | us | 294 | 2026-07-27 | https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms |
| asen_et_markets | Economic Times Markets | us | 347 | 2026-07-27 | https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms |
| asen_gizmochina | Gizmochina | cn_a | 1388 | 2026-07-27 | https://www.gizmochina.com/feed/ |
| asen_japan_forward | Japan Forward | us | 272 | 2026-07-27 | https://japan-forward.com/feed/ |
| asen_lbo_lk | Lanka Business Online | us | 1340 | 2026-07-27 | https://www.lankabusinessonline.com/feed/ |
| asen_malay_mail_biz | Malay Mail Business | us | 1000 | 2026-07-28 | https://www.malaymail.com/feed/rss/money |
| asen_ndtv_profit | NDTV Profit | us | 160 | 2026-07-27 | https://feeds.feedburner.com/ndtvprofit-latest |
| asen_pandaily | Pandaily | cn_a | 1048 | 2026-07-27 | https://pandaily.com/feed/ |
| asen_straits_asia | The Straits Times Asia | us | 175 | 2026-07-28 | https://www.straitstimes.com/news/asia/rss.xml |
| asen_swarajya | Swarajya | us | 2130 | 2026-07-27 | https://swarajyamag.com/feed |
| asen_thaiger | The Thaiger | us | 1324 | 2026-07-27 | https://thethaiger.com/feed |
| asen_thenational_ae | The National (UAE) | us | 2592 | 2026-07-27 | https://www.thenationalnews.com/arc/outboundfeeds/rss/?outputType=xml |
| asen_vnexpress_biz | VnExpress Business | us | 152 | 2026-07-28 | https://e.vnexpress.net/rss/business.rss |
| asen_almonitor | Al-Monitor | us | 388 | 2026-07-27 | https://www.al-monitor.com/rss |
| asen_asiafinancial | Asia Financial | us | 3365 | 2026-07-27 | https://www.asiafinancial.com/rss |
| asen_astanatimes | The Astana Times | us | 2820 | 2026-07-27 | https://astanatimes.com/feed/ |
| asen_businesstoday_my | BusinessToday Malaysia | us | 333 | 2026-07-27 | https://www.businesstoday.com.my/feed/ |
| asen_bworldonline | BusinessWorld (PH) | us | 2523 | 2026-07-27 | https://www.bworldonline.com/feed/ |
| asen_cabar_asia | CABAR.asia | us | 1954 | 2026-06-01 | https://cabar.asia/en/feed |
| asen_cgtn_business | CGTN Business | cn_a | 1563 | 2026-07-27 | https://www.cgtn.com/subscribe/rss/section/business.xml |
| asen_conversation_au_biz | The Conversation AU Business | us | 5958 | 2026-07-27 | https://theconversation.com/au/business/articles.atom |
| asen_devpolicy | DevPolicy Blog (ANU) | us | 3423 | 2026-07-26 | https://devpolicy.org/feed/ |
| asen_e27 | e27 (SG Startups) | us | 3850 | 2026-07-27 | https://e27.co/feed/ |
| asen_economynext | EconomyNext (LK) | us | 637 | 2026-07-27 | https://economynext.com/feed/ |
| asen_insideretailasia | Inside Retail Asia | us | 1181 | 2026-07-27 | https://insideretail.asia/feed/ |
| asen_khaosod_en | Khaosod English | us | 1009 | 2026-07-27 | https://www.khaosodenglish.com/feed/ |
| asen_mothership | Mothership (SG) | us | 1239 | 2026-07-27 | https://mothership.sg/feed/ |
| asen_pakobserver | Pakistan Observer | us | 845 | 2026-07-27 | https://pakobserver.net/feed/ |
| asen_propakistani | ProPakistani (PK) | us | 637 | 2026-07-27 | https://propakistani.pk/feed/ |
| asen_rakyatpost | The Rakyat Post (MY) | us | 1305 | 2026-07-27 | https://www.therakyatpost.com/feed/ |
| asen_smartcompany | SmartCompany (AU) | us | 239 | 2026-07-27 | https://www.smartcompany.com.au/feed/ |
| asen_stackedhomes | Stacked Homes (SG Property) | us | 5567 | 2026-07-27 | https://stackedhomes.com/feed/ |
| asen_techjuice | TechJuice (PK) | us | 457 | 2026-07-27 | https://www.techjuice.pk/feed/ |
| asen_thaienquirer | Thai Enquirer | us | 5232 | 2026-07-27 | https://www.thaienquirer.com/feed/ |
| asen_toi_business | Times of India Business | us | 376 | 2026-07-27 | https://timesofindia.indiatimes.com/rssfeeds/1898055.cms |
| asen_vnexpress_news | VnExpress News | us | 157 | 2026-07-28 | https://e.vnexpress.net/rss/news.rss |
| asen_vulcanpost | Vulcan Post | us | 3894 | 2026-07-24 | https://vulcanpost.com/feed/ |
| asen_yourstory | YourStory (IN) | us | 2015 | 2026-07-27 | https://yourstory.com/feed |

### 3.2 国际媒体栏目 feed（20）

| slug | 名称 | market | avg_body | 最新条目 | feed |
|---|---|---|---|---|---|
| asen_dw_business | DW Business | us | 164 | 2026-07-27 | https://rss.dw.com/rdf/rss-en-bus |
| asen_dw_world | DW World | us | 184 | 2026-07-27 | https://rss.dw.com/rdf/rss-en-world |
| asen_fastcompany | Fast Company | us | 6101 | 2026-07-27 | https://www.fastcompany.com/rss |
| asen_france24_en | France 24 English | us | 358 | 2026-07-27 | https://www.france24.com/en/rss |
| asen_guardian_comment | The Guardian Opinion | us | 1555 | 2026-07-27 | https://www.theguardian.com/commentisfree/rss |
| asen_guardian_economics | The Guardian Economics | us | 919 | 2026-07-27 | https://www.theguardian.com/business/economics/rss |
| asen_guardian_env | The Guardian Environment | us | 894 | 2026-07-27 | https://www.theguardian.com/environment/rss |
| asen_guardian_money | The Guardian Money | us | 748 | 2026-07-27 | https://www.theguardian.com/uk/money/rss |
| asen_guardian_world | The Guardian World | us | 731 | 2026-07-27 | https://www.theguardian.com/world/rss |
| asen_irishtimes_biz | Irish Times Business | us | 2366 | 2026-07-27 | https://www.irishtimes.com/arc/outboundfeeds/rss/?outputType=xml |
| asen_moneyweek | MoneyWeek | us | 3174 | 2026-07-27 | https://moneyweek.com/feed/all |
| asen_nationalpost | National Post | us | 182 | 2026-07-27 | https://nationalpost.com/feed |
| asen_npr_business | NPR Business | us | 189 | 2026-07-27 | https://feeds.npr.org/1006/rss.xml |
| asen_npr_world | NPR World | us | 188 | 2026-07-27 | https://feeds.npr.org/1004/rss.xml |
| asen_nyt_world | NYT World | us | 165 | 2026-07-27 | https://rss.nytimes.com/services/xml/rss/nyt/World.xml |
| asen_eureporter | EU Reporter | us | 2858 | 2026-07-27 | https://www.eureporter.co/feed/ |
| asen_guardian_inequality | The Guardian Inequality | us | 1048 | 2026-07-27 | https://www.theguardian.com/inequality/rss |
| asen_guardian_tech | The Guardian Technology | us | 1236 | 2026-07-27 | https://www.theguardian.com/uk/technology/rss |
| asen_politico_eu | Politico Europe | us | 1030 | 2026-07-27 | https://www.politico.eu/feed/ |
| asen_cityam | City A.M. | us | 1716 | 2026-07-27 | https://www.cityam.com/feed/ |

### 3.3 半导体/硬件（7）

| slug | 名称 | market | avg_body | 最新条目 | feed |
|---|---|---|---|---|---|
| asen_eetimes | EE Times | us | 185 | 2026-07-27 | https://www.eetimes.com/feed/ |
| asen_semiengineering | Semiconductor Engineering | us | 4253 | 2026-07-27 | https://semiengineering.com/feed/ |
| asen_semiwiki | SemiWiki | us | 382 | 2026-07-27 | https://semiwiki.com/feed/ |
| asen_servethehome | ServeTheHome | us | 215 | 2026-07-27 | https://www.servethehome.com/feed/ |
| asen_tomshardware | Tom's Hardware | us | 1781 | 2026-07-27 | https://www.tomshardware.com/feeds/all |
| asen_techpowerup | TechPowerUp | us | 980 | 2026-07-27 | https://www.techpowerup.com/rss/news |
| asen_wccftech | Wccftech | us | 633 | 2026-07-27 | https://wccftech.com/feed/ |

### 3.4 新能源/油气（12）

| slug | 名称 | market | avg_body | 最新条目 | feed |
|---|---|---|---|---|---|
| asen_canarymedia | Canary Media | us | 305 | 2026-07-27 | https://www.canarymedia.com/rss |
| asen_electrek | Electrek | us | 273 | 2026-07-27 | https://electrek.co/feed/ |
| asen_oilprice | OilPrice.com | us | 492 | 2026-07-27 | https://oilprice.com/rss/main |
| asen_utilitydive | Utility Dive | us | 362 | 2026-07-27 | https://www.utilitydive.com/feeds/news/ |
| asen_windpower_monthly | Windpower Monthly | us | 166 | 2026-07-27 | https://www.windpowermonthly.com/rss |
| asen_drillingcontractor | Drilling Contractor | us | 453 | 2026-07-24 | https://www.drillingcontractor.org/feed/ |
| asen_marinetech | Marine Technology News | us | 275 | 2026-07-26 | https://www.marinetechnologynews.com/rss |
| asen_mercomindia | Mercom India | us | 280 | 2026-07-27 | https://www.mercomindia.com/feed/ |
| asen_oedigital | Offshore Engineer | us | 150 | 2026-07-27 | https://www.oedigital.com/rss |
| asen_powereng | Power Engineering | us | 5566 | 2026-07-24 | https://www.power-eng.com/feed/ |
| asen_powermag | POWER Magazine | us | 440 | 2026-07-24 | https://www.powermag.com/feed/ |
| asen_sustainabilitytimes | Sustainability Times | us | 361 | 2026-07-21 | https://www.sustainability-times.com/feed/ |

### 3.5 生物医药（7）

| slug | 名称 | market | avg_body | 最新条目 | feed |
|---|---|---|---|---|---|
| asen_biopharmadive | BioPharma Dive | us | 334 | 2026-07-27 | https://www.biopharmadive.com/feeds/news/ |
| asen_endpoints | Endpoints News | us | 200 | 2026-07-27 | https://endpts.com/feed/ |
| asen_fiercebiotech | Fierce Biotech | us | 158 |  | https://www.fiercebiotech.com/rss/xml |
| asen_fiercepharma | Fierce Pharma | us | 210 |  | https://www.fiercepharma.com/rss/xml |
| asen_healthcaredive | Healthcare Dive | us | 353 | 2026-07-27 | https://www.healthcaredive.com/feeds/news/ |
| asen_medcitynews | MedCity News | us | 305 | 2026-07-27 | https://medcitynews.com/feed/ |
| asen_statnews | STAT News | us | 464 | 2026-07-27 | https://www.statnews.com/feed/ |

### 3.6 汽车（5）

| slug | 名称 | market | avg_body | 最新条目 | feed |
|---|---|---|---|---|---|
| asen_autocar | Autocar | us | 8188 | 2026-07-27 | https://www.autocar.co.uk/rss |
| asen_driving_ca | Driving.ca | us | 260 | 2026-07-27 | https://driving.ca/feed |
| asen_gaadiwaadi | GaadiWaadi (IN) | us | 1495 | 2026-07-27 | https://gaadiwaadi.com/feed/ |
| asen_paultan | Paul Tan Automotive News | us | 1680 | 2026-07-27 | https://paultan.org/rss/ |
| asen_rushlane | RushLane (IN) | us | 227 | 2026-07-27 | https://www.rushlane.com/feed/ |

### 3.7 航运物流（9）

| slug | 名称 | market | avg_body | 最新条目 | feed |
|---|---|---|---|---|---|
| asen_container_news | Container News | us | 863 | 2026-07-27 | https://container-news.com/feed/ |
| asen_gcaptain | gCaptain | us | 182 | 2026-07-27 | https://gcaptain.com/feed/ |
| asen_loadstar | The Loadstar | us | 530 | 2026-07-27 | https://theloadstar.com/feed/ |
| asen_marinelink | MarineLink | us | 246 | 2026-07-27 | https://www.marinelink.com/rss |
| asen_porttechnology | Port Technology | us | 489 | 2026-07-27 | https://www.porttechnology.org/feed/ |
| asen_splash247 | Splash247 | us | 310 | 2026-07-27 | https://splash247.com/feed/ |
| asen_supplychaindive | Supply Chain Dive | us | 298 | 2026-07-27 | https://www.supplychaindive.com/feeds/news/ |
| asen_cimsec | CIMSEC | us | 415 | 2026-07-27 | https://cimsec.org/feed/ |
| asen_navalnews | Naval News | us | 2346 | 2026-07-27 | https://www.navalnews.com/feed/ |

### 3.8 大宗商品/矿业/农业（10）

| slug | 名称 | market | avg_body | 最新条目 | feed |
|---|---|---|---|---|---|
| asen_beefcentral | Beef Central (AU) | us | 224 | 2026-07-27 | https://www.beefcentral.com/feed/ |
| asen_chinimandi | ChiniMandi (Sugar) | us | 1192 | 2026-07-27 | https://www.chinimandi.com/feed/ |
| asen_dailycoffeenews | Daily Coffee News | us | 195 | 2026-07-27 | https://dailycoffeenews.com/feed/ |
| asen_gmk_center | GMK Center | us | 437 | 2026-07-27 | https://gmk.center/en/feed/ |
| asen_investingnews | Investing News Network | us | 6779 | 2026-07-27 | https://investingnews.com/feed/ |
| asen_marketherald | The Market Herald (AU) | us | 1300 | 2026-07-27 | https://themarketherald.com.au/feed/ |
| asen_naturalgasintel | Natural Gas Intel | us | 175 | 2026-07-27 | https://www.naturalgasintel.com/feed/ |
| asen_northernminer | The Northern Miner | us | 296 | 2026-07-27 | https://www.northernminer.com/feed/ |
| asen_srsrocco | SRSrocco Report | us | 301 | 2026-07-26 | https://srsroccoreport.com/feed/ |
| asen_wastedive | Waste Dive | us | 390 | 2026-07-27 | https://www.wastedive.com/feeds/news/ |

### 3.9 其他行业垂直（航天/防务/金融科技/零售/地产/监管等）（18）

| slug | 名称 | market | avg_body | 最新条目 | feed |
|---|---|---|---|---|---|
| asen_bankingdive | Banking Dive | us | 421 | 2026-07-27 | https://www.bankingdive.com/feeds/news/ |
| asen_defensenews | Defense News | us | 1689 | 2026-07-27 | https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml |
| asen_fooddive | Food Dive | us | 279 | 2026-07-27 | https://www.fooddive.com/feeds/news/ |
| asen_frontofficesports | Front Office Sports | us | 1062 | 2026-07-27 | https://frontofficesports.com/feed/ |
| asen_housedive | Construction Dive | us | 370 | 2026-07-27 | https://www.constructiondive.com/feeds/news/ |
| asen_housingwire | HousingWire | us | 1891 | 2026-07-27 | https://www.housingwire.com/feed/ |
| asen_hrdive | HR Dive | us | 330 | 2026-07-27 | https://www.hrdive.com/feeds/news/ |
| asen_marketingdive | Marketing Dive | us | 356 | 2026-07-27 | https://www.marketingdive.com/feeds/news/ |
| asen_marktechpost | MarkTechPost | us | 4421 | 2026-07-27 | https://www.marktechpost.com/feed/ |
| asen_retaildive | Retail Dive | us | 315 | 2026-07-27 | https://www.retaildive.com/feeds/news/ |
| asen_sportico | Sportico | us | 321 | 2026-07-27 | https://www.sportico.com/feed/ |
| asen_thedecoder | The Decoder | us | 432 | 2026-07-27 | https://the-decoder.com/feed/ |
| asen_theregreview | The Regulatory Review | us | 4305 | 2026-07-27 | https://www.theregreview.org/feed/ |
| asen_variety | Variety | us | 337 | 2026-07-27 | https://variety.com/feed/ |
| asen_venturebeat | VentureBeat | us | 7922 | 2026-07-27 | https://venturebeat.com/feed/ |
| asen_spacecom | Space.com | us | 1728 | 2026-07-27 | https://www.space.com/feeds/all |
| asen_spacepolicyonline | SpacePolicyOnline | us | 1532 | 2026-07-26 | https://spacepolicyonline.com/feed/ |
| asen_twz | The War Zone | us | 3409 | 2026-07-26 | https://www.twz.com/feed |

### 3.10 智库/机构/地缘（7）

| slug | 名称 | market | avg_body | 最新条目 | feed |
|---|---|---|---|---|---|
| asen_atlanticcouncil | Atlantic Council | us | 208 | 2026-07-27 | https://www.atlanticcouncil.org/feed/ |
| asen_fred_blog | FRED Blog (St. Louis Fed) | us | 994 | 2026-07-27 | https://fredblog.stlouisfed.org/feed/ |
| asen_aspistrategist | The Strategist (ASPI) | us | 210 | 2026-07-27 | https://www.aspistrategist.org.au/feed/ |
| asen_conversation_global_biz | The Conversation Business | us | 5934 | 2026-07-20 | https://theconversation.com/global/business/articles.atom |
| asen_coppolacomment | Coppola Comment | us | 4820 | 2026-07-26 | https://www.coppolacomment.com/feeds/posts/default |
| asen_defenseone | Defense One | us | 3458 | 2026-07-25 | https://www.defenseone.com/rss/all/ |
| asen_geopoliticalfutures | Geopolitical Futures | us | 451 | 2026-07-27 | https://geopoliticalfutures.com/feed/ |

### 3.11 个人投资者博客（自建站）（36）

| slug | 名称 | market | avg_body | 最新条目 | feed |
|---|---|---|---|---|---|
| asen_assi_sg | A Singaporean Stock Investor (ASSI) | us | 400 | 2026-07-21 | https://singaporeanstocksinvestor.blogspot.com/feeds/posts/default |
| asen_boringinvestor | The Boring Investor (SG) | us | 13745 | 2026-07-18 | https://boringinvestor.blogspot.com/feeds/posts/default |
| asen_dividendgrowth | Dividend Growth Investor | us | 117116 | 2026-07-25 | https://www.dividendgrowthinvestor.com/feeds/posts/default |
| asen_dollarsandsense | DollarsAndSense (SG) | us | 2169 | 2026-07-27 | https://dollarsandsense.sg/feed/ |
| asen_econbrowser2 | Macro Musings (David Beckworth) | us | 1134 | 2026-07-27 | https://macromusings.libsyn.com/rss |
| asen_econompic | EconomPic | us | 13389 | 2026-07-26 | https://econompicdata.blogspot.com/feeds/posts/default |
| asen_epchan | Quantitative Trading (Ernie Chan) | us | 31522 | 2026-07-25 | https://epchan.blogspot.com/feeds/posts/default |
| asen_europeandgi | European DGI | us | 284 | 2026-07-11 | https://europeandgi.com/feed/ |
| asen_fifthperson | The Fifth Person (SG) | us | 3869 | 2026-07-23 | https://fifthperson.com/feed/ |
| asen_forexlive | InvestingLive (ex-ForexLive) | us | 1521 | 2026-07-27 | https://investinglive.com/feed |
| asen_freefincal | freefincal | us | 434 | 2026-07-25 | https://freefincal.com/feed/ |
| asen_lt3000 | LT3000 (Lyall Taylor) | us | 24931 | 2026-07-05 | https://lt3000.blogspot.com/feeds/posts/default |
| asen_mebfaber | Meb Faber Research | us | 246 | 2026-07-02 | https://mebfaber.com/feed/ |
| asen_musings_markets | Musings on Markets (Damodaran) | us | 45703 | 2026-07-27 | https://aswathdamodaran.blogspot.com/feeds/posts/default |
| asen_myownadvisor | My Own Advisor | us | 498 | 2026-07-27 | https://www.myownadvisor.ca/feed/ |
| asen_providend | Providend (SG) | us | 3712 | 2026-07-22 | https://providend.com/feed/ |
| asen_quantstart | QuantStart | us | 501 |  | https://www.quantstart.com/feed/ |
| asen_retirementinvestingtoday | Retirement Investing Today | us | 404 | 2026-07-25 | https://www.retirementinvestingtoday.com/feeds/posts/default |
| asen_robotwealth | Robot Wealth | us | 400 | 2026-06-08 | https://robotwealth.com/feed/ |
| asen_routetoretire | Route to Retire | us | 430 | 2026-06-09 | https://www.routetoretire.com/feed/ |
| asen_safalniveshak | Safal Niveshak | us | 4140 | 2026-07-27 | https://www.safalniveshak.com/feed/ |
| asen_strongmoneyau | Strong Money Australia | us | 3468 | 2026-07-18 | https://strongmoneyaustralia.com/feed/ |
| asen_tawcan | Tawcan | us | 207 | 2026-07-27 | https://www.tawcan.com/feed/ |
| asen_thepoorswiss | The Poor Swiss | us | 5057 | 2026-07-21 | https://thepoorswiss.com/feed/ |
| asen_valuewalk | ValueWalk | us | 570 | 2026-06-29 | https://www.valuewalk.com/feed/ |
| asen_boomerandecho | Boomer & Echo (CA) | us | 295 | 2026-07-05 | https://www.boomerandecho.com/feed/ |
| asen_capitalspectator | The Capital Spectator | us | 1767 | 2026-07-27 | https://www.capitalspectator.com/feed/ |
| asen_dividendguy | The Dividend Guy Blog | us | 3073 | 2026-07-23 | https://www.thedividendguyblog.com/feed/ |
| asen_etftrends | ETF Trends | us | 442 | 2026-07-27 | https://www.etftrends.com/feed/ |
| asen_investinghaven | Investing Haven | us | 330 | 2026-07-24 | https://investinghaven.com/feed/ |
| asen_jagoinvestor | JagoInvestor (IN) | us | 384 | 2026-07-06 | https://www.jagoinvestor.com/feed/ |
| asen_looniedoctor | The Loonie Doctor (CA) | us | 2701 | 2026-06-30 | https://www.looniedoctor.ca/feed/ |
| asen_moneywehave | Money We Have (CA) | us | 3371 | 2026-06-16 | https://www.moneywehave.com/feed/ |
| asen_retirebeforedad | Retire Before Dad | us | 429 | 2026-07-23 | https://www.retirebeforedad.com/feed/ |
| asen_tradebrains | Trade Brains (IN) | us | 2516 | 2026-07-27 | https://tradebrains.in/feed/ |
| asen_treeofprosperity | Tree of Prosperity (SG) | us | 5313 | 2026-07-27 | https://treeofprosperity.blogspot.com/feeds/posts/default |

## 4. 实测通过但未收录（9）

### 4.1 按主会话裁决归并行 `global_indie_batch` 波次（3）

这 3 个美源 URL 实测通过，但主题上不属于亚洲，按 2026-07-28 主会话裁决由 `gind_` 批次收录，本批次让出避免双写：

| slug | 名称 |
|---|---|
| krebsonsecurity | Krebs on Security |
| wallethacks | Wallet Hacks |
| yetanothervalue | Yet Another Value Blog |

### 4.2 编辑判断剔除（6）

| slug | 名称 | 原因 |
|---|---|---|
| paultan2 | Paul Tan (feed) | 与 paultan 同站重复 URL，保留 /rss/ |
| xinhua_en | Xinhua English Business | 平均正文 157 字符偏标题党，且已有 xinhua 中文源 |
| krebson | Hackmanac | 探测残留项，非财经向 |
| eurogamer | Eurogamer | 消费向游戏媒体，超出财经/行业范围 |
| chinadaily_world | China Daily World | 综合世界新闻，财经信号弱（保留 chinadaily_biz/cgtn_business） |
| thehill | The Hill | 美国政治赛马新闻，财经信号弱 |

## 5. 淘汰记录（479，按原因分组）

### 5.1 第一轮（352 候选）淘汰明细

| slug | 名称 | HTTP | 原因 | feed |
|---|---|---|---|---|
| afr | Australian Financial Review | 404 | http 404 | https://www.afr.com/rss |
| aju_press | Aju Korea Daily | 200 | not rss/atom | https://www.ajudaily.com/rss/allArticle.xml |
| akipress | AKIpress | 404 | http 404 | https://en.akipress.com/rss.php |
| antara_biz | Antara News Business | 404 | http 404 | https://en.antaranews.com/rss/business.xml |
| arabian_business | Arabian Business | 405 | http 405 | https://www.arabianbusiness.com/feed |
| arabnews_econ | Arab News Economy | 403 | http 403 | https://www.arabnews.com/cat/3/feed |
| bangkok_post_biz | Bangkok Post Business | 451 | http 451 | https://www.bangkokpost.com/rss/data/business.xml |
| brecorder | Business Recorder (PK) | 404 | http 404 | https://www.brecorder.com/rss |
| bs_economy | Business Standard Economy | 403 | http 403 | https://www.business-standard.com/rss/economy-102.rss |
| bs_markets | Business Standard Markets | 403 | http 403 | https://www.business-standard.com/rss/markets-106.rss |
| business_standard | Business Standard | 403 | http 403 | https://www.business-standard.com/rss/home_page_top_stories.rss |
| businesstimes_sg | The Business Times (SG) | 200 | not rss/atom | https://www.businesstimes.com.sg/rss |
| cna_asia | CNA Asia | 200 | thin body avg=127 | https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6311 |
| cna_business | CNA Business | 200 | thin body avg=142 | https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6511 |
| dailyft_lk | Daily FT (LK) | 200 | not rss/atom | https://www.ft.lk/rss |
| edge_malaysia | The Edge Malaysia | 404 | http 404 | https://theedgemalaysia.com/rss |
| edge_sg | The Edge Singapore | 403 | http 403 | https://www.theedgesingapore.com/rss |
| equalocean | EqualOcean | 404 | http 404 | https://equalocean.com/rss |
| fe_economy | Financial Express Economy | 403 | http 403 | https://www.financialexpress.com/economy/feed/ |
| financial_express | Financial Express | 403 | http 403 | https://www.financialexpress.com/feed/ |
| focus_taiwan_biz | Focus Taiwan Business | 404 | http 404 | https://focustaiwan.tw/RSS/business.xml |
| gulfnews_biz | Gulf News Business | 404 | http 404 | https://gulfnews.com/rss/business |
| hindu_bl | The Hindu BusinessLine | 200 | thin body avg=125 | https://www.thehindubusinessline.com/feeder/default.rss |
| hindu_bl_economy | BusinessLine Economy | 200 | thin body avg=125 | https://www.thehindubusinessline.com/economy/feeder/default.rss |
| hindu_bl_markets | BusinessLine Markets | 200 | thin body avg=113 | https://www.thehindubusinessline.com/markets/feeder/default.rss |
| hkfp | Hong Kong Free Press | 403 | http 403 | https://hongkongfp.com/feed/ |
| inquirer_biz | Inquirer Business (PH) | 403 | http 403 | https://business.inquirer.net/feed |
| interest_nz | Interest.co.nz | 410 | http 410 | https://www.interest.co.nz/rss.xml |
| jakartaglobe_biz | Jakarta Globe Business | 403 | http 403 | https://jakartaglobe.id/rss/business |
| jakartapost_biz | The Jakarta Post Business | 404 | http 404 | https://www.thejakartapost.com/rss/business |
| japan_today | Japan Today | 403 | http 403 | https://japantoday.com/feed |
| khaleej_biz | Khaleej Times Business | 200 | not rss/atom | https://www.khaleejtimes.com/rss/business |
| korea_bizwire | The Korea Bizwire | 000 | http 000 | https://koreabizwire.com/feed |
| korea_herald_biz | The Korea Herald Business | 200 | no items | https://www.koreaherald.com/rss/020100000000.xml |
| korea_herald_nat | The Korea Herald National | 200 | no items | https://www.koreaherald.com/rss/020200000000.xml |
| korea_joongang | Korea JoongAng Daily | 404 | http 404 | https://koreajoongangdaily.joins.com/news/rss/ |
| kr_asia | KrASIA | 200 | not rss/atom | https://kr-asia.com/feed |
| livemint_companies | Mint Companies | 403 | http 403 | https://www.livemint.com/rss/companies |
| livemint_markets | Mint Markets | 403 | http 403 | https://www.livemint.com/rss/markets |
| livemint_news | Mint News | 403 | http 403 | https://www.livemint.com/rss/news |
| livemint_opinion | Mint Opinion | 403 | http 403 | https://www.livemint.com/rss/opinion |
| mainichi_en | The Mainichi (English) | 200 | not rss/atom | https://mainichi.jp/english/rss/etc/english.rss |
| manila_bulletin_biz | Manila Bulletin Business | 403 | http 403 | https://mb.com.ph/rss/business |
| moneycontrol_economy | Moneycontrol Economy | 200 | stale latest=2024-04-23 | https://www.moneycontrol.com/rss/economy.xml |
| moneycontrol_markets | Moneycontrol Markets | 200 | stale latest=2024-04-23 | https://www.moneycontrol.com/rss/marketreports.xml |
| moneycontrol_news | Moneycontrol Latest | 200 | stale latest=2024-04-23 | https://www.moneycontrol.com/rss/latestnews.xml |
| montsame | Montsame (MN) | 000 | http 000 | https://en.montsame.mn/rss |
| nation_thailand | The Nation Thailand Business | 200 | not rss/atom | https://www.nationthailand.com/rss/business |
| newscomau_finance | news.com.au Finance | 403 | http 403 | https://www.news.com.au/finance/feed |
| nhk_world | NHK World-Japan | 404 | http 404 | https://www3.nhk.or.jp/nhkworld/en/news/rss/ |
| nikkei_asia | Nikkei Asia | 200 | thin body avg=0 | https://asia.nikkei.com/rss/feed/nar |
| nst_biz | New Straits Times Business | 404 | http 404 | https://www.nst.com.my/rss/business |
| nzherald_business | NZ Herald Business | 200 | thin body avg=58 | https://www.nzherald.co.nz/arc/outboundfeeds/rss/section/business/?outputType=xml |
| philstar_biz | Philstar Business | 403 | http 403 | https://www.philstar.com/rss/business |
| rappler_biz | Rappler Business | 200 | not rss/atom | https://www.rappler.com/topic-rss/business/ |
| saigon_times | The Saigon Times | 200 | not rss/atom | https://english.thesaigontimes.vn/rss/Home/Business.rss |
| scoop_biz | Scoop Business (NZ) | 404 | http 404 | https://www.scoop.co.nz/newsbyrss/business.xml |
| sixth_tone | Sixth Tone | 200 | thin body avg=140 | https://www.sixthtone.com/rss |
| smh_business | SMH Business | 403 | http 403 | https://www.smh.com.au/rss/business.xml |
| standard_hk | The Standard (HK) | 200 | not rss/atom | https://www.thestandard.com.hk/rss/ |
| star_biz | The Star Business (MY) | 404 | http 404 | https://www.thestar.com.my/rss/business |
| straits_business | The Straits Times Business | 200 | thin body avg=147 | https://www.straitstimes.com/news/business/rss.xml |
| taipei_times_biz | Taipei Times Business | 404 | http 404 | https://www.taipeitimes.com/rss/business |
| taiwan_news | Taiwan News | 403 | http 403 | https://www.taiwannews.com.tw/rss/business |
| technode | TechNode | 403 | http 403 | https://technode.com/feed/ |
| tempo_biz | Tempo Business | 403 | http 403 | https://en.tempo.co/rss/business |
| theage_business | The Age Business | 200 | thin body avg=144 | https://www.theage.com.au/rss/business.xml |
| theweek_in | The Week (India) | 404 | http 404 | https://www.theweek.in/rss-feeds/business.html |
| timesca | The Times of Central Asia | 403 | http 403 | https://timesca.com/feed/ |
| todayonline | TODAY (SG) | 000 | http 000 | https://www.todayonline.com/feed |
| tribune_biz | Express Tribune Business | 200 | not rss/atom | https://tribune.com.pk/rss/business |
| vietnamnews | Vietnam News | 403 | http 403 | https://vietnamnews.vn/rss/economy.rss |
| vir_vietnam | Vietnam Investment Review | 404 | http 404 | https://vir.com.vn/rss/business.rss |
| yicai_global | Yicai Global | 404 | http 404 | https://www.yicaiglobal.com/rss/news |
| yonhap_biz | Yonhap News Business | 000 | http 000 | https://en.yna.co.kr/RSS/business.xml |
| yonhap_economy | Yonhap Economy | 000 | http 000 | https://www.yna.co.kr/rss/economy.xml |
| autoblog | Autoblog | 403 | http 403 | https://www.autoblog.com/rss.xml |
| autonews | Automotive News | 404 | http 404 | https://www.autonews.com/rss.xml |
| caranddriver | Car and Driver | 200 | thin body avg=105 | https://www.caranddriver.com/rss/all.xml/ |
| chargedevs | Charged EVs | 403 | http 403 | https://chargedevs.com/feed/ |
| fleetowner | FleetOwner | 403 | http 403 | https://www.fleetowner.com/rss.xml |
| greencarreports | Green Car Reports | 403 | http 403 | https://www.greencarreports.com/rss/all |
| motor1 | Motor1.com | 200 | thin body avg=81 | https://www.motor1.com/rss/news/all/ |
| ttac | The Truth About Cars | 406 | http 406 | https://www.thetruthaboutcars.com/feed/ |
| ttnews | Transport Topics | 200 | thin body avg=145 | https://www.ttnews.com/rss.xml |
| wardsauto | WardsAuto | 404 | http 404 | https://www.wardsauto.com/rss.xml |
| genengnews | GEN News | 403 | http 403 | https://www.genengnews.com/feed/ |
| mobihealthnews | MobiHealthNews | 403 | http 403 | https://www.mobihealthnews.com/rss.xml |
| pharmatimes | PharmaTimes | 403 | http 403 | https://www.pharmatimes.com/rss |
| adventuresincap | Adventures in Capitalism | 000 | http 000 | https://adventuresincapitalism.com/feed/ |
| allstarcharts | All Star Charts | 200 | not rss/atom | https://allstarcharts.com/feed/ |
| alvarezquant | Alvarez Quant Trading | 200 | stale latest=2026-05-12 | https://alvarezquanttrading.com/blog/feed/ |
| bankeronfire | Banker on FIRE | 404 | http 404 | https://bankeronfire.com/feed/ |
| barelkarsan | Barel Karsan | 404 | http 404 | https://www.barelkarsan.com/feeds/posts/default |
| basunivesh | BasuNivesh | 200 | thin body avg=118 | https://www.basunivesh.com/feed/ |
| behindthebalancesheet | Behind the Balance Sheet | 000 | http 000 | https://behindthebalancesheet.com/feed/ |
| bitsaboutmoney | Bits about Money | 404 | http 404 | https://www.bitsaboutmoney.com/feed/ |
| brooklyninvestor | Brooklyn Investor | 200 | stale latest=2026-04-03 | https://brooklyninvestor.blogspot.com/feeds/posts/default |
| budgetbabe | Budget Babe (SG) | 000 | http 000 | https://budgetbabe.com.sg/feed/ |
| canadiancouchpotato | Canadian Couch Potato | 403 | http 403 | https://canadiancouchpotato.com/feed/ |
| cheerfulegg | Cheerful Egg (SG) | 200 | stale latest=2026-05-10 | https://cheerfulegg.com/feed/ |
| contrarianedge | Contrarian Edge (Katsenelson) | 000 | http 000 | https://contrarianedge.com/feed/ |
| divhut | DivHut | 200 | stale latest=2026-05-26 | https://www.divhut.com/feed/ |
| drwealth | Dr Wealth (SG) | 403 | http 403 | https://drwealth.com/feed/ |
| epsilontheory | Epsilon Theory | 404 | http 404 | https://www.epsilontheory.com/feed/ |
| felderreport | The Felder Report | 000 | http 000 | https://felderreport.com/feed/ |
| fifteenhourworkweek | My 15 Hour Work Week (SG) | 403 | http 403 | https://my15hw.wordpress.com/feed/ |
| fundooprofessor | Fundoo Professor | 403 | http 403 | https://fundooprofessor.wordpress.com/feed/ |
| fxstreet | FXStreet News | 403 | http 403 | https://www.fxstreet.com/rss/news |
| genymoney | Gennymoney.ca | 000 | http 000 | https://genymoney.ca/feed/ |
| greenbackd | Greenbackd | 403 | http 403 | https://greenbackd.com/feed/ |
| heartlandboy | Heartland Boy (SG) | 000 | http 000 | https://heartlandboy.com/feed/ |
| humblestudent | Humble Student of the Markets | 200 | stale latest=2026-03-29 | https://humblestudentofthemarkets.com/feed/ |
| investingcaffeine | Investing Caffeine | 403 | http 403 | https://investingcaffeine.com/feed/ |
| investmentstab | Investment Stab (SG) | 000 | http 000 | https://www.investmentstab.com/feed |
| investquest | The InvestQuest (SG) | 000 | http 000 | https://www.investquest.com.sg/feed/ |
| investresolve | Resolve Asset Management | 000 | http 000 | https://investresolve.com/feed/ |
| itinvestor | IT Investor | 000 | http 000 | https://www.itinvestor.co.uk/feed/ |
| macroops | Macro Ops | 403 | http 403 | https://macro-ops.com/feed/ |
| macrotourist | The Macro Tourist | 000 | http 000 | https://themacrotourist.com/feed/ |
| milliondollarjourney | Million Dollar Journey | 404 | http 404 | https://www.milliondollarjourney.com/rss.htm |
| mrtako | Mr. Tako Escapes | 404 | http 404 | https://mrtakoescapes.com/feed/ |
| mysweetretirement | My Sweet Retirement (SG) | 403 | http 403 | https://mysweetretirement.com/feed/ |
| novelinvestor | Novel Investor | 403 | http 403 | https://novelinvestor.com/feed/ |
| oddballstocks | Oddball Stocks | 000 | http 000 | https://oddballstocks.com/feed/ |
| oldschoolvalue | Old School Value | 200 | stale latest=2026-02-10 | https://www.oldschoolvalue.com/feed/ |
| passiveincomepursuit | Passive Income Pursuit | 000 | http 000 | https://www.passiveincomepursuit.com/feeds/posts/default |
| philosophicalecon | Philosophical Economics | 200 | stale latest=2020-09-09 | https://philosophicaleconomics.com/feed/ |
| seeitmarket | See It Market | 403 | http 403 | https://www.seeitmarket.com/feed/ |
| sgtti | SG TTI | 200 | stale latest=2024-12-18 | https://sgtti.blogspot.com/feeds/posts/default |
| simplelivingsomerset | Simple Living in Somerset | 000 | http 000 | https://simplelivinginsomerset.co.uk/feed/ |
| stableinvestor | Stable Investor | 403 | http 403 | https://stableinvestor.com/feed/ |
| subramoney | Subramoney | 000 | http 000 | https://subramoney.com/feed/ |
| ukvalueinvestor | UK Value Investor | 403 | http 403 | https://www.ukvalueinvestor.com/feed/ |
| valueopportunity | Value And Opportunity | 403 | http 403 | https://valueandopportunity.com/feed/ |
| verdadcap | Verdad Advisers | 404 | http 404 | https://verdadcap.com/feed/ |
| vintagevalue | Vintage Value Investing | 403 | http 403 | https://www.vintagevalueinvesting.com/feed/ |
| slug | name | 000 | http 000 | url |
| agfunder | AgFunder News | 403 | http 403 | https://agfundernews.com/feed |
| agweb | AgWeb | 403 | http 403 | https://www.agweb.com/rss.xml |
| brownfieldag | Brownfield Ag News | 403 | http 403 | https://brownfieldagnews.com/feed/ |
| dailyfx | DailyFX | 403 | http 403 | https://www.dailyfx.com/feeds/market-news |
| farmprogress | Farm Progress | 200 | thin body avg=148 | https://www.farmprogress.com/rss.xml |
| fxempire | FX Empire | 404 | http 404 | https://www.fxempire.com/news/feed |
| kitco | Kitco News | 404 | http 404 | https://www.kitco.com/rss/gold.xml |
| mining_com | MINING.COM | 403 | http 403 | https://www.mining.com/feed/ |
| recyclingtoday | Recycling Today | 403 | http 403 | https://www.recyclingtoday.com/rss/ |
| worldgrain | World Grain | 403 | http 403 | https://www.world-grain.com/rss |
| cleantechnica | CleanTechnica | 403 | http 403 | https://cleantechnica.com/feed/ |
| energystorage | Energy Storage News | 403 | http 403 | https://www.energy-storage.news/feed/ |
| energyvoice | Energy Voice | 403 | http 403 | https://www.energyvoice.com/feed/ |
| hydroreview | Hydro Review | 403 | http 403 | https://www.hydroreview.com/feed/ |
| insideevs | InsideEVs | 200 | thin body avg=101 | https://insideevs.com/rss/news/all/ |
| offshorewind | OffshoreWIND.biz | 200 | thin body avg=105 | https://www.offshorewind.biz/feed/ |
| pv_magazine | pv magazine | 403 | http 403 | https://www.pv-magazine.com/feed/ |
| pvtech | PV Tech | 403 | http 403 | https://www.pv-tech.org/feed/ |
| reneweconomy | RenewEconomy | 403 | http 403 | https://reneweconomy.com.au/feed/ |
| rigzone | Rigzone | 403 | http 403 | https://www.rigzone.com/news/rss/rigzone_latest.aspx |
| aljazeera | Al Jazeera English | 200 | thin body avg=96 | https://www.aljazeera.com/xml/rss/all.xml |
| atlantic_all | The Atlantic | 403 | http 403 | https://www.theatlantic.com/feed/all/ |
| bbc_science | BBC Science & Environment | 200 | thin body avg=98 | https://feeds.bbci.co.uk/news/science_and_environment/rss.xml |
| bbc_tech | BBC Technology | 200 | thin body avg=94 | https://feeds.bbci.co.uk/news/technology/rss.xml |
| bbc_world | BBC World | 200 | thin body avg=111 | https://feeds.bbci.co.uk/news/world/rss.xml |
| cbc_business | CBC Business | 000 | http 000 | https://www.cbc.ca/webfeed/rss/rss-business |
| economist_asia | The Economist Asia | 200 | thin body avg=77 | https://www.economist.com/asia/rss.xml |
| economist_business | The Economist Business | 200 | thin body avg=76 | https://www.economist.com/business/rss.xml |
| economist_china | The Economist China | 200 | thin body avg=85 | https://www.economist.com/china/rss.xml |
| economist_finance | The Economist Finance & Economics | 200 | thin body avg=80 | https://www.economist.com/finance-and-economics/rss.xml |
| economist_intl | The Economist International | 200 | thin body avg=88 | https://www.economist.com/international/rss.xml |
| economist_leaders | The Economist Leaders | 200 | thin body avg=82 | https://www.economist.com/leaders/rss.xml |
| euronews_economy | Euronews Economy | 406 | http 406 | https://www.euronews.com/rss?level=theme&name=economy |
| forbes_money | Forbes Money | 404 | http 404 | https://www.forbes.com/money/feed/ |
| forbes_realestate | Forbes Real Estate | 404 | http 404 | https://www.forbes.com/real-estate/feed/ |
| foreignaffairs | Foreign Affairs | 200 | thin body avg=63 | https://www.foreignaffairs.com/rss.xml |
| foreignpolicy | Foreign Policy | 200 | thin body avg=65 | https://foreignpolicy.com/feed/ |
| ft_asia | FT Asia-Pacific | 200 | thin body avg=77 | https://www.ft.com/asia-pacific?format=rss |
| ft_comment | FT Opinion | 200 | thin body avg=78 | https://www.ft.com/comment?format=rss |
| ft_companies | FT Companies | 200 | thin body avg=83 | https://www.ft.com/companies?format=rss |
| ft_globalecon | FT Global Economy | 200 | thin body avg=64 | https://www.ft.com/global-economy?format=rss |
| ft_markets | FT Markets | 200 | thin body avg=76 | https://www.ft.com/markets?format=rss |
| ft_world | FT World | 200 | thin body avg=86 | https://www.ft.com/world?format=rss |
| globeandmail_biz | Globe and Mail Business | 200 | thin body avg=122 | https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/?outputType=xml |
| inc | Inc. | 200 | thin body avg=101 | https://www.inc.com/rss |
| npr_economy | NPR Economy | 200 | thin body avg=149 | https://feeds.npr.org/1017/rss.xml |
| nyt_business | NYT Business | 200 | thin body avg=142 | https://rss.nytimes.com/services/xml/rss/nyt/Business.xml |
| nyt_economy | NYT Economy | 200 | thin body avg=147 | https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml |
| politico_economy | Politico Economy | 404 | http 404 | https://rss.politico.com/economy.xml |
| quartz | Quartz | 200 | thin body avg=131 | https://qz.com/rss |
| telegraph_finance | The Telegraph Finance | 403 | http 403 | https://www.telegraph.co.uk/finance/rss.xml |
| thisismoney | This is Money | 404 | http 404 | https://www.thisismoney.co.uk/money/rss.html |
| trtworld | TRT World | 404 | http 404 | https://www.trtworld.com/rss |
| wapo_business | Washington Post Business | 200 | no items | https://feeds.washingtonpost.com/rss/business |
| wapo_economy | Washington Post Economy | 200 | no items | https://feeds.washingtonpost.com/rss/business/economy |
| wired | Wired | 200 | thin body avg=137 | https://www.wired.com/feed/rss |
| wsj_economy | WSJ Economy | 200 | stale latest=2025-01-24 | https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml |
| wsj_markets | WSJ Markets | 200 | stale latest=2025-01-27 | https://feeds.a.dj.com/rss/RSSMarketsMain.xml |
| wsj_world | WSJ World News | 200 | stale latest=2025-01-27 | https://feeds.a.dj.com/rss/RSSWorldNews.xml |
| blocksandfiles | Blocks & Files | 200 | thin body avg=65 | https://blocksandfiles.com/feed |
| digitimes | DigiTimes | 200 | not rss/atom | https://www.digitimes.com/rss/dailyNews.xml |
| hpcwire | HPCwire | 403 | http 403 | https://www.hpcwire.com/feed/ |
| aircargonews | Air Cargo News | 403 | http 403 | https://www.aircargonews.net/feed/ |
| freightwaves | FreightWaves | 403 | http 403 | https://www.freightwaves.com/feed |
| hellenicshipping | Hellenic Shipping News | 403 | http 403 | https://www.hellenicshippingnews.com/feed/ |
| logisticsmgmt | Logistics Management | 200 | not rss/atom | https://www.logisticsmgmt.com/rss |
| seatrade | Seatrade Maritime News | 200 | thin body avg=116 | https://www.seatrade-maritime.com/rss.xml |
| bis | BIS Publications | 404 | http 404 | https://www.bis.org/rss/pub.xml |
| brookings | Brookings Institution | 200 | not rss/atom | https://www.brookings.edu/feed/ |
| bruegel | Bruegel | 403 | http 403 | https://www.bruegel.org/rss.xml |
| carnegie | Carnegie Endowment | 404 | http 404 | https://carnegieendowment.org/rss/channel/207.xml |
| cfr_setser | Brad Setser (CFR) | 404 | http 404 | https://www.cfr.org/rss/experts/brad-w-setser.xml |
| chathamhouse | Chatham House | 403 | http 403 | https://www.chathamhouse.org/rss |
| csis | CSIS | 200 | stale latest=2016-03-03 | https://www.csis.org/rss.xml |
| eurointelligence | Eurointelligence | 200 | not rss/atom | https://www.eurointelligence.com/rss.xml |
| geopoliticalmonitor | Geopolitical Monitor | 200 | not rss/atom | https://www.geopoliticalmonitor.com/feed/ |
| imf_blog | IMF Blog | 403 | http 403 | https://www.imf.org/en/Blogs/rss |
| macroblog | Atlanta Fed Macroblog | 404 | http 404 | https://www.atlantafed.org/blogs/macroblog/rss.aspx |
| moderndiplomacy | Modern Diplomacy | 000 | http 000 | https://moderndiplomacy.eu/feed/ |
| piie | Peterson Institute | 403 | http 403 | https://www.piie.com/rss.xml |
| rand | RAND Corporation | 404 | http 404 | https://www.rand.org/pubs/rss.xml |
| stlouisfed_ote | St. Louis Fed On the Economy | 000 | http 000 | https://www.stlouisfed.org/on-the-economy/rss |
| voxeu | VoxEU (CEPR) | 403 | http 403 | https://cepr.org/voxeu/rss |
| worldbank_blogs | World Bank Blogs | 404 | http 404 | https://blogs.worldbank.org/en/rss |
| adbi | ADB Institute | 403 | http 403 | https://www.adb.org/adbi/rss |
| asiatimes | Asia Times | 403 | http 403 | https://asiatimes.com/feed/ |
| chinafile | ChinaFile | 404 | http 404 | https://www.chinafile.com/rss |
| eastasiaforum | East Asia Forum | 403 | http 403 | https://eastasiaforum.org/feed/ |
| lowy_interpreter | Lowy Interpreter | 200 | thin body avg=107 | https://www.lowyinstitute.org/the-interpreter/rss.xml |
| macropolo | MacroPolo | 200 | stale latest=2024-12-10 | https://macropolo.org/feed/ |
| thediplomat | The Diplomat | 200 | thin body avg=130 | https://thediplomat.com/feed/ |
| thinkchina | ThinkChina | 403 | http 403 | https://www.thinkchina.sg/feed |
| bleepingcomputer | BleepingComputer | 403 | http 403 | https://www.bleepingcomputer.com/feed/ |
| breakingdefense | Breaking Defense | 200 | thin body avg=125 | https://breakingdefense.com/feed/ |
| crunchbase_news | Crunchbase News | 403 | http 403 | https://news.crunchbase.com/feed/ |
| darkreading | Dark Reading | 200 | thin body avg=145 | https://www.darkreading.com/rss.xml |
| datanami | Datanami | 403 | http 403 | https://www.datanami.com/feed/ |
| finextra | Finextra | 403 | http 403 | https://www.finextra.com/rss/headlines.aspx |
| flightglobal | FlightGlobal | 403 | http 403 | https://www.flightglobal.com/rss/rss.aspx |
| gamesindustry | GamesIndustry.biz | 403 | http 403 | https://www.gamesindustry.biz/rss/gamesindustry.biz |
| pymnts | PYMNTS | 403 | http 403 | https://www.pymnts.com/feed/ |
| securityweek | SecurityWeek | 403 | http 403 | https://www.securityweek.com/feed/ |
| spacenews | SpaceNews | 403 | http 403 | https://spacenews.com/feed/ |
| thepaypers | The Paypers | 200 | not rss/atom | https://thepaypers.com/rss |
| therealdeal | The Real Deal | 403 | http 403 | https://therealdeal.com/feed/ |
| therecord | The Record | 403 | http 403 | https://therecord.media/feed |
| threetdprint | 3DPrint.com | 403 | http 403 | https://3dprint.com/feed/ |

### 5.2 第二轮（312 候选）淘汰明细

| slug | 名称 | HTTP | 原因 | feed |
|---|---|---|---|---|
| abscbn_business | ABS-CBN Business (PH) | 403 | http 403 | https://news.abs-cbn.com/rss/business |
| adaderana_biz | Ada Derana Biz (LK) | 404 | http 404 | http://bizenglish.adaderana.lk/rss.php |
| agbi | AGBI (Gulf Business) | 202 | http 202 | https://www.agbi.com/feed/ |
| aseanbriefing | ASEAN Briefing | 200 | not rss/atom | https://www.aseanbriefing.com/news/feed/ |
| asianbankingfinance | Asian Banking & Finance | 404 | http 404 | https://asianbankingandfinance.net/rss |
| asianinvestor | AsianInvestor | 404 | http 404 | https://www.asianinvestor.net/feed |
| asiaone | AsiaOne | 404 | http 404 | https://www.asiaone.com/rss |
| asiatechdaily | AsiaTechDaily | 403 | http 403 | https://www.asiatechdaily.com/feed/ |
| bne_intellinews | bne IntelliNews | 404 | http 404 | https://www.intellinews.com/rss |
| businesskorea | BusinessKorea | 403 | http 403 | http://www.businesskorea.co.kr/rss/allArticle.xml |
| businesstoday_in | Business Today (IN) | 200 | no items | https://www.businesstoday.in/rssfeeds/?id=4 |
| chinabriefing | China Briefing | 200 | not rss/atom | https://www.china-briefing.com/news/feed/ |
| chinamoneynetwork | China Money Network | 200 | not rss/atom | https://www.chinamoneynetwork.com/feed/ |
| daryo | Daryo (UZ) | 200 | not rss/atom | https://daryo.uz/en/rss |
| dealstreetasia | DealStreetAsia | 503 | http 503 | https://www.dealstreetasia.com/feed |
| deccanherald_biz | Deccan Herald Business | 200 | not rss/atom | https://www.deccanherald.com/rss/business |
| ecns | ECNS (China News EN) | 404 | http 404 | https://www.ecns.cn/rss/business.xml |
| ecobusiness | Eco-Business (SG) | 404 | http 404 | https://www.eco-business.com/rss/news/ |
| edgeprop_sg | EdgeProp Singapore | 403 | http 403 | https://www.edgeprop.sg/rss |
| entrackr | Entrackr (IN) | 404 | http 404 | https://entrackr.com/feed |
| eurasianet | Eurasianet | 404 | http 404 | https://eurasianet.org/rss.xml |
| fe_bd | Financial Express (BD) | 200 | not rss/atom | https://thefinancialexpress.com.bd/rss/business |
| financeasia | FinanceAsia | 500 | http 500 | https://www.financeasia.com/rss |
| fmt_business | Free Malaysia Today Business | 403 | http 403 | https://www.freemalaysiatoday.com/category/business/feed |
| fortuneindia | Fortune India | 404 | http 404 | https://www.fortuneindia.com/rss |
| fpj_biz | Free Press Journal Business | 200 | not rss/atom | https://www.freepressjournal.in/business/feed |
| globaltimes | Global Times | 404 | http 404 | https://www.globaltimes.cn/rss/outbound.xml |
| gma_money | GMA News Money (PH) | 404 | http 404 | https://www.gmanetwork.com/news/rss/money |
| greenqueen | Green Queen (HK) | 403 | http 403 | https://www.greenqueen.com.hk/feed/ |
| gulfbusiness | Gulf Business | 403 | http 403 | https://gulfbusiness.com/feed/ |
| healthcareasia | Healthcare Asia | 404 | http 404 | https://healthcareasiamagazine.com/rss |
| hindu_business | The Hindu Business | 200 | thin body avg=128 | https://www.thehindu.com/business/feeder/default.rss |
| hkbusiness | Hong Kong Business | 404 | http 404 | https://hongkongbusiness.hk/rss |
| ht_business | Hindustan Times Business | 403 | http 403 | https://www.hindustantimes.com/feeds/rss/business/rssfeed.xml |
| idbusinesspost | Indonesia Business Post | 404 | http 404 | https://indonesiabusinesspost.com/feed/ |
| inc42 | Inc42 (IN) | 404 | http 404 | https://inc42.com/feed/ |
| indiabriefing | India Briefing | 200 | not rss/atom | https://www.india-briefing.com/news/feed/ |
| insiderstories | The Insider Stories (ID) | 404 | http 404 | https://theinsiderstories.com/feed/ |
| insuranceasia | Insurance Asia | 404 | http 404 | https://insuranceasia.com/rss |
| interaksyon | Interaksyon (PH) | 403 | http 403 | https://interaksyon.philstar.com/feed |
| japannews_yomiuri | The Japan News | 000 | http 000 | https://japan-news.yomiuri.co.jp/feed/ |
| jingdaily | Jing Daily | 429 | http 429 | https://jingdaily.com/feed/ |
| koreabiomed | Korea Biomedical Review | 403 | http 403 | https://www.koreabiomed.com/feed/ |
| koreaittimes | Korea IT Times | 403 | http 403 | http://www.koreaittimes.com/rss/allArticle.xml |
| koreatechdesk | KoreaTechDesk | 403 | http 403 | https://www.koreatechdesk.com/feed/ |
| kun_uz | Kun.uz | 200 | not rss/atom | https://kun.uz/en/rss |
| kyodo | Kyodo News English | 404 | http 404 | https://english.kyodonews.net/rss/news.xml |
| macaubusiness | Macau Business | 404 | http 404 | https://www.macaubusiness.com/feed/ |
| malaysianreserve | The Malaysian Reserve | 403 | http 403 | https://themalaysianreserve.com/feed/ |
| manilastandard | Manila Standard | 202 | http 202 | https://manilastandard.net/feed/ |
| mingtiandi | Mingtiandi (Asia Real Estate) | 403 | http 403 | https://www.mingtiandi.com/feed/ |
| moneylife | Moneylife (IN) | 404 | http 404 | https://www.moneylife.in/feed |
| newindian_biz | New Indian Express Business | 404 | http 404 | https://www.newindianexpress.com/Business/rssfeed/?id=171&getXmlFeed=true |
| news18_business | News18 Business | 403 | http 403 | https://www.news18.com/commonfeeds/v1/eng/rss/business.xml |
| newsroom_nz | Newsroom (NZ) | 200 | thin body avg=147 | https://www.newsroom.co.nz/feed |
| onestepoffgrid | One Step Off The Grid (AU) | 403 | http 403 | https://onestepoffthegrid.com.au/feed/ |
| peopledaily_en | People's Daily Online Business | 404 | http 404 | http://en.people.cn/rss/business.xml |
| pna_business | Philippine News Agency Business | 403 | http 403 | https://www.pna.gov.ph/business/rss |
| profit_pk | Profit by Pakistan Today | 404 | http 404 | https://profit.pakistantoday.com.pk/feed/ |
| retailasia | Retail Asia | 404 | http 404 | https://retailasia.com/rss |
| rnz_business | RNZ Business (NZ) | 200 | thin body avg=108 | https://www.rnz.co.nz/rss/business.xml |
| sbr_sg | Singapore Business Review | 404 | http 404 | https://sbr.com.sg/rss |
| shine_biz | SHINE Business (Shanghai Daily) | 200 | not rss/atom | https://www.shine.cn/rss/biz |
| startupdaily_au | Startup Daily (AU) | 200 | thin body avg=120 | https://www.startupdaily.net/feed/ |
| stuff_business | Stuff Business (NZ) | 404 | http 404 | https://www.stuff.co.nz/rss/business |
| taiwanbusiness | Taiwan Business Topics | 403 | http 403 | https://topics.amcham.com.tw/feed/ |
| tbsnews | The Business Standard (BD) | 404 | http 404 | https://www.tbsnews.net/rss |
| techinasia | Tech in Asia | 200 | thin body avg=106 | https://www.techinasia.com/feed |
| technodeglobal | TechNode Global | 403 | http 403 | https://technode.global/feed/ |
| theasset | The Asset | 200 | thin body avg=85 | https://www.theasset.com/rss |
| thenews_biz | The News Business (PK) | 404 | http 404 | https://www.thenews.com.pk/rss/business |
| theprint | ThePrint (IN) | 200 | not rss/atom | https://theprint.in/feed/ |
| thewire_econ | The Wire Economy (IN) | 200 | not rss/atom | https://thewire.in/economy/feed |
| tradearabia | TradeArabia | 404 | http 404 | https://www.tradearabia.com/rss |
| trend_az | Trend News Agency | 404 | http 404 | https://en.trend.az/rss/business |
| tuoitre_biz | Tuoi Tre News Business | 000 | http 000 | https://tuoitrenews.vn/rss/business.rss |
| ubpost | The UB Post | 000 | http 000 | https://ubpost.mongolnews.mn/?feed=rss2 |
| vietnambriefing | Vietnam Briefing | 200 | not rss/atom | https://www.vietnam-briefing.com/news/feed/ |
| vietnaminsider | Vietnam Insider | 403 | http 403 | https://vietnaminsider.vn/feed/ |
| vietnamnet_biz | VietnamNet Business | 404 | http 404 | https://vietnamnet.vn/en/rss/business.rss |
| zawya | Zawya | 200 | not rss/atom | https://www.zawya.com/rss |
| autoevolution | autoevolution | 200 | not rss/atom | https://www.autoevolution.com/rss/news/ |
| autoexpress | Auto Express | 200 | thin body avg=84 | https://www.autoexpress.co.uk/rss |
| autoindustriya | AutoIndustriya (PH) | 403 | http 403 | https://www.autoindustriya.com/rss |
| automotivelogistics | Automotive Logistics | 404 | http 404 | https://www.automotivelogistics.media/feed |
| drive_au | Drive (AU) | 403 | http 403 | https://www.drive.com.au/feed/ |
| etauto | ETAuto | 200 | not rss/atom | https://auto.economictimes.indiatimes.com/rss |
| fleetnews | Fleet News (UK) | 410 | http 410 | https://www.fleetnews.co.uk/rss |
| greencarcongress | Green Car Congress | 000 | http 000 | https://www.greencarcongress.com/index.xml |
| motortrend | MotorTrend | 200 | not rss/atom | https://www.motortrend.com/feed/ |
| thedriven | The Driven (AU EV) | 403 | http 403 | https://thedriven.io/feed/ |
| torquenews | Torque News | 200 | stale latest=2020-10-22 | https://www.torquenews.com/rss.xml |
| 7circles | 7 Circles (UK) | 000 | http 000 | https://7circles.uk/feed/ |
| advisorperspectives | Advisor Perspectives | 403 | http 403 | https://www.advisorperspectives.com/rss |
| affordanything | Afford Anything | 403 | http 403 | https://affordanything.com/feed/ |
| aussiefirebug | Aussie Firebug | 200 | stale latest=2025-12-14 | https://www.aussiefirebug.com/feed/ |
| basehitinvesting | Base Hit Investing | 404 | http 404 | https://basehitinvesting.com/feed/ |
| canadianpm | Canadian Portfolio Manager | 403 | http 403 | https://www.canadianportfoliomanagerblog.com/feed/ |
| collegeinvestor | The College Investor | 403 | http 403 | https://thecollegeinvestor.com/feed/ |
| dividenddiplomats | Dividend Diplomats | 200 | stale latest=2026-05-20 | https://www.dividenddiplomats.com/feed/ |
| dividendwarrior | Dividend Warrior (SG) | 403 | http 403 | https://dividendwarrior.wordpress.com/feed/ |
| diyinvestoruk | DIY Investor (UK) | 404 | http 404 | https://diyinvestoruk.blogspot.com/feeds/posts/default |
| drvijaymalik | Dr. Vijay Malik (IN) | 403 | http 403 | https://www.drvijaymalik.com/feed/ |
| escapeartist | The Escape Artist (UK) | 403 | http 403 | https://theescapeartist.me/feed/ |
| etfstream | ETF Stream | 403 | http 403 | https://www.etfstream.com/feed/ |
| fff_sg | A Path to Forever Financial Freedom (SG) | 000 | http 000 | https://foreverfinancialfreedom.com/feed/ |
| financialmentor | Financial Mentor | 403 | http 403 | https://financialmentor.com/feed |
| financialpanther | Financial Panther | 403 | http 403 | https://financialpanther.com/feed/ |
| finumus | Finumus | 200 | not rss/atom | https://finumus.com/feed/ |
| getrichslowly | Get Rich Slowly | 200 | stale latest=2022-12-02 | https://www.getrichslowly.org/feed/ |
| indexology | Indexology (S&P DJI) | 403 | http 403 | https://www.indexologyblog.com/feed/ |
| irrelevantinvestor | The Irrelevant Investor | 200 | not rss/atom | https://theirrelevantinvestor.com/feed/ |
| maplemoney | Maple Money (CA) | 200 | stale latest=2024-04-02 | https://maplemoney.com/feed/ |
| mrmoneymustache | Mr. Money Mustache | 403 | http 403 | https://www.mrmoneymustache.com/feed/ |
| myinvestmentideas | My Investment Ideas (IN) | 200 | not rss/atom | https://myinvestmentideas.com/feed/ |
| passiveincomemd | Passive Income MD | 520 | http 520 | https://passiveincomemd.com/feed/ |
| pragcap | Pragmatic Capitalism | 403 | http 403 | https://www.pragcap.com/feed/ |
| reformedbroker | The Reformed Broker | 200 | stale latest=2023-11-29 | https://thereformedbroker.com/feed/ |
| suredividend | Sure Dividend | 403 | http 403 | https://www.suredividend.com/feed/ |
| topdowncharts | Topdown Charts | 404 | http 404 | https://www.topdowncharts.com/feed/ |
| ukdividendstocks | UK Dividend Stocks | 404 | http 404 | https://www.ukdividendstocks.com/feed/ |
| yourmoneyblueprint | Your Money Blueprint (NZ) | 404 | http 404 | https://yourmoneyblueprint.co.nz/feed/ |
| slug | name | 000 | http 000 | url |
| agriculture_com | Successful Farming | 403 | http 403 | https://www.agriculture.com/rss.xml |
| australianmining | Australian Mining | 403 | http 403 | https://www.australianmining.com.au/feed/ |
| bullionstar | BullionStar Blog (SG) | 200 | not rss/atom | https://www.bullionstar.com/blogs/bullionstar/feed/ |
| commodity_com | Commodity.com | 200 | stale latest=2022-05-03 | https://commodity.com/feed/ |
| dairyglobal | Dairy Global | 404 | http 404 | https://www.dairyglobal.net/feed/ |
| farms_com | Farms.com News | 000 | http 000 | https://www.farms.com/rss/news.xml |
| goldcore | GoldCore | 404 | http 404 | https://www.goldcore.com/us/feed/ |
| goldsilver_com | GoldSilver | 403 | http 403 | https://goldsilver.com/blog/feed/ |
| graincentral | Grain Central (AU) | 200 | thin body avg=115 | https://www.graincentral.com/feed/ |
| im_mining | International Mining | 000 | http 000 | https://im-mining.com/feed/ |
| juniormining | Junior Mining Network | 403 | http 403 | https://www.juniorminingnetwork.com/rss |
| metalminer | MetalMiner | 403 | http 403 | https://agmetalminer.com/feed/ |
| miningweekly | Mining Weekly (SA) | 404 | http 404 | https://www.miningweekly.com/rss/all |
| moneymetals | Money Metals | 403 | http 403 | https://www.moneymetals.com/news/rss |
| poultryworld | Poultry World | 404 | http 404 | https://www.poultryworld.net/feed/ |
| proactiveinvestors | Proactive Investors | 404 | http 404 | https://www.proactiveinvestors.com/rss |
| schiffgold | SchiffGold | 403 | http 403 | https://schiffgold.com/feed/ |
| seafoodsource | SeafoodSource | 404 | http 404 | https://www.seafoodsource.com/feed |
| smallcaps_au | Small Caps (AU) | 200 | thin body avg=148 | https://smallcaps.com.au/feed/ |
| sprudge | Sprudge (Coffee) | 403 | http 403 | https://sprudge.com/feed |
| steeltimesint | Steel Times International | 404 | http 404 | https://www.steeltimesint.com/rss |
| stockhead | Stockhead (AU) | 403 | http 403 | https://stockhead.com.au/feed/ |
| thepigsite | The Pig Site | 404 | http 404 | https://www.thepigsite.com/rss.php |
| worldgrain2 | World Grain | 403 | http 403 | https://www.world-grain.com/rss/rssfeed |
| carbonbrief | Carbon Brief | 403 | http 403 | https://www.carbonbrief.org/feed/ |
| cleanenergywire | Clean Energy Wire | 404 | http 404 | https://www.cleanenergywire.org/feed |
| climatehome | Climate Home News | 403 | http 403 | https://www.climatechangenews.com/feed/ |
| currentnews_uk | Current± (UK) | 200 | not rss/atom | https://www.current-news.co.uk/feed/ |
| drybulk | Dry Bulk | 403 | http 403 | https://www.drybulkmagazine.com/rss |
| energylivenews | Energy Live News (UK) | 403 | http 403 | https://www.energylivenews.com/feed/ |
| etenergyworld | ETEnergyWorld | 200 | not rss/atom | https://energy.economictimes.indiatimes.com/rss |
| fuelcellsworks | Fuel Cells Works | 200 | thin body avg=141 | https://fuelcellsworks.com/feed/ |
| globalminingreview | Global Mining Review | 403 | http 403 | https://www.globalminingreview.com/rss |
| h2view | H2 View | 403 | http 403 | https://www.h2-view.com/feed |
| naturalgasworld | Natural Gas World | 200 | not rss/atom | https://naturalgasworld.com/feed/ |
| renews | reNEWS (Renewables) | 200 | thin body avg=52 | https://renews.biz/feed/ |
| saurenergy | Saur Energy (IN) | 404 | http 404 | https://www.saurenergy.com/rss-feeds |
| solarpowerportal | Solar Power Portal (UK) | 404 | http 404 | https://www.solarpowerportal.co.uk/feed/ |
| worldcoal | World Coal | 403 | http 403 | https://www.worldcoal.com/rss |
| worldfertilizer | World Fertilizer | 403 | http 403 | https://www.worldfertilizer.com/rss |
| worldmaritimenews | World Maritime News | 200 | no items | https://worldmaritimenews.com/feed/ |
| worldpipelines | World Pipelines | 403 | http 403 | https://www.worldpipelines.com/rss |
| ap_business | AP Business (via hub) | 200 | not rss/atom | https://apnews.com/hub/business?output=1 |
| bbc_health | BBC Health | 200 | thin body avg=99 | https://feeds.bbci.co.uk/news/health/rss.xml |
| belfasttelegraph_biz | Belfast Telegraph Business | 200 | thin body avg=111 | https://www.belfasttelegraph.co.uk/business/rss |
| brusselstimes | The Brussels Times | 404 | http 404 | https://www.brusselstimes.com/rss.xml |
| cnbc_economy | CNBC Economy | 200 | thin body avg=141 | https://www.cnbc.com/id/20910258/device/rss/rss.html |
| cnbc_finance | CNBC Finance | 200 | thin body avg=131 | https://www.cnbc.com/id/10000664/device/rss/rss.html |
| euractiv | Euractiv | 403 | http 403 | https://www.euractiv.com/feed/ |
| express_finance | Express Finance | 404 | http 404 | https://www.express.co.uk/finance/rss |
| independent_biz | The Independent Business | 200 | thin body avg=92 | https://www.independent.co.uk/news/business/rss |
| marketwatch_realestate | MarketWatch Real Estate | 200 | thin body avg=145 | https://feeds.marketwatch.com/marketwatch/realtimeheadlines/ |
| mirror_money | Mirror Money | 200 | thin body avg=120 | https://www.mirror.co.uk/money/?service=rss |
| nyt_dealbook | NYT DealBook | 200 | thin body avg=137 | https://rss.nytimes.com/services/xml/rss/nyt/Dealbook.xml |
| nyt_energy | NYT Energy & Environment | 200 | thin body avg=144 | https://rss.nytimes.com/services/xml/rss/nyt/EnergyEnvironment.xml |
| nyt_tech | NYT Technology | 200 | thin body avg=133 | https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml |
| politico_business | Politico Business | 404 | http 404 | https://rss.politico.com/business.xml |
| rnz_world | RNZ World (NZ) | 200 | no items | https://www.rnz.co.nz/rss/world.xml |
| scotsman_biz | The Scotsman Business | 200 | thin body avg=111 | https://www.scotsman.com/business/rss |
| thelocal_de | The Local Germany | 404 | http 404 | https://www.thelocal.de/feed/ |
| thelocal_eu | The Local Europe | 404 | http 404 | https://www.thelocal.com/feed/ |
| ukipnews | The Standard (UK) | 200 | thin body avg=92 | https://www.standard.co.uk/rss |
| walesonline_biz | WalesOnline Business | 200 | thin body avg=58 | https://www.walesonline.co.uk/business/?service=rss |
| wapo_climate | Washington Post Climate | 301 | http 301 | https://feeds.washingtonpost.com/rss/business/climate-environment |
| wsj_tech | WSJ Tech | 200 | stale latest=2025-01-27 | https://feeds.a.dj.com/rss/RSSWSJD.xml |
| chipestimate | Chip Estimate | 404 | http 404 | https://www.chipestimate.com/rss.php |
| notebookcheck | Notebookcheck | 404 | http 404 | https://www.notebookcheck.net/RSS-Feed.138.0.html |
| videocardz | VideoCardz | 403 | http 403 | https://videocardz.com/rss |
| maritimeexecutive | The Maritime Executive | 404 | http 404 | https://maritime-executive.com/feed |
| shipandbunker | Ship & Bunker | 200 | thin body avg=104 | https://shipandbunker.com/rss |
| usni_news | USNI News | 403 | http 403 | https://news.usni.org/feed/ |
| 38north | 38 North | 403 | http 403 | https://www.38north.org/feed/ |
| adb_news | ADB News | 403 | http 403 | https://www.adb.org/rss/news |
| aei | American Enterprise Institute | 403 | http 403 | https://www.aei.org/feed/ |
| amro | AMRO (ASEAN+3) | 403 | http 403 | https://www.amro-asia.org/feed/ |
| asiasociety | Asia Society | 404 | http 404 | https://asiasociety.org/rss.xml |
| booth_review | Chicago Booth Review | 404 | http 404 | https://review.chicagobooth.edu/rss |
| cato | Cato Institute | 404 | http 404 | https://www.cato.org/rss |
| cfainstitute_blog | Enterprising Investor (CFA) | 200 | not rss/atom | https://blogs.cfainstitute.org/investor/feed/ |
| epi | Economic Policy Institute | 200 | thin body avg=138 | https://www.epi.org/feed/ |
| gatewayhouse | Gateway House (IN) | 403 | http 403 | https://www.gatewayhouse.in/feed/ |
| hbr | Harvard Business Review | 000 | http 000 | https://feeds.hbr.org/harvardbusiness |
| hinrich | Hinrich Foundation | 404 | http 404 | https://www.hinrichfoundation.com/feed/ |
| iiss | IISS | 403 | http 403 | https://www.iiss.org/rss.xml |
| ineteconomics | INET Economics | 403 | http 403 | https://www.ineteconomics.org/rss |
| insead_knowledge | INSEAD Knowledge | 403 | http 403 | https://knowledge.insead.edu/rss |
| iseas | ISEAS (SG) | 200 | not rss/atom | https://www.iseas.edu.sg/feed/ |
| larssyll | Lars P. Syll | 403 | http 403 | https://larspsyll.wordpress.com/feed/ |
| macrohive | Macro Hive | 403 | http 403 | https://macrohive.com/feed/ |
| mainlymacro | Mainly Macro (Wren-Lewis) | 200 | not rss/atom | https://mainlymacro.blogspot.com/feeds/posts/default |
| mckinsey_insights | McKinsey Insights | 200 | stale latest=2015-09-01 | https://www.mckinsey.com/insights/rss |
| mercatus | Mercatus Center | 403 | http 403 | https://www.mercatus.org/rss |
| mishtalk | MishTalk (Shedlock) | 403 | http 403 | https://mishtalk.com/feed |
| mitsloan | MIT Sloan Management Review | 403 | http 403 | https://sloanreview.mit.edu/feed/ |
| ninedashline | 9DashLine | 404 | http 404 | https://www.9dashline.com/feed/ |
| oecdecoscope | OECD Ecoscope | 403 | http 403 | https://oecdecoscope.blog/feed/ |
| orfonline | Observer Research Foundation (IN) | 403 | http 403 | https://www.orfonline.org/rss |
| pacforum | Pacific Forum | 403 | http 403 | https://pacforum.org/feed/ |
| rusi | RUSI | 404 | http 404 | https://rusi.org/rss.xml |
| rwer | Real-World Economics Review | 403 | http 403 | https://rwer.wordpress.com/feed/ |
| stanford_gsb | Stanford GSB Insights | 404 | http 404 | https://www.gsb.stanford.edu/insights/rss |
| stumblingmumbling | Stumbling and Mumbling | 403 | http 403 | https://stumblingandmumbling.typepad.com/stumbling_and_mumbling/atom.xml |
| themarketear | The Market Ear | 404 | http 404 | https://themarketear.com/rss |
| unescap | UNESCAP | 403 | http 403 | https://www.unescap.org/rss.xml |
| urban_institute | Urban Institute | 403 | http 403 | https://www.urban.org/rss.xml |
| voxdev | VoxDev | 404 | http 404 | https://voxdev.org/rss |
| weforum_agenda | WEF Agenda | 403 | http 403 | https://www.weforum.org/agenda/feed |
| wharton_knowledge | Knowledge at Wharton | 200 | thin body avg=124 | https://knowledge.wharton.upenn.edu/feed/ |
| aviationweek | Aviation Week | 200 | stale latest=2026-03-31 | https://aviationweek.com/rss.xml |
| nasaspaceflight | NASASpaceflight.com | 403 | http 403 | https://www.nasaspaceflight.com/feed/ |
| spacenews2 | SpaceNews | 403 | http 403 | https://spacenews.com/feed/ |

## 6. 运维要点

1. **集成**：按 `20260728-asia-en-batch-integration.md` 三个代码块粘贴（scheduler_jobs / scheduler / news.py），本波任务未改动任何共享文件。
2. **job 形态**：16 个 `news_asia_en_{a..p}_60m`，IntervalTrigger 60 分钟，`max_instances=1, coalesce=True`，沿用 2026-07-27 misfire 修复后的全局 `misfire_grace_time=300`。
3. **失败容忍**：单 feed 失败只记 warning，不影响同批其余 feed；未知 batch key 返回空列表（防御式）。
4. **正文兜底**：部分媒体（ABC、VnExpress、NDTV 等）RSS 只给 1–2 句摘要，现有 `news_full_content_10m` 全文抓取 job 会补正文；摘要 ≥150 字符已满足翻译管线最低输入。
5. **翻译**：全部 `language="en"`，`news_translate_10m` drain 自动处理；`market` 只写 `us`/`cn_a`，前端默认 "global" 筛选可见（`_GLOBAL_MARKETS = (cn_a, us, crypto)`）。
6. **健康面板**：`_WORKER_META` 16 条标签需同步（集成块 3b）；`_WORKER_KEYWORDS` 加 `asia_en` / `asen_`。
7. **降载**：如健康网格拥挤，可在 `asia_en_batch.py` 把 `_BATCH_SIZE` 调到 14（→13 批）并重跑集成块生成器，无需改 crawler。
8. **复验**：上线 2–4 周后用同一脚本对 176 个 URL 复跑（候选清单可从模块表直接导出），失败 ≥3 次的 feed 应从表中剔除并更新本 runbook。

## 7. 已知限制

- **Nikkei Asia、CNA、Bangkok Post、SCMP 其余栏目、WSJ/FT 栏目** 在中国大陆网络不可达或已下线 RSS——这是网络现实，非清单遗漏；如未来部署海外采集节点可复活（见 5.1 淘汰表）。
- 博客类源更新频率天然不均（周更/月更），health grid 的 `written=0` 不等于故障；建议以 7 天窗口观察。
- `asen_swarajya`（印度右翼立场杂志）、`asen_almonitor`（中东地缘）等带有编辑立场，AI 摘要/翻译会保留其观点色彩；展示层如需立场标注属后续产品决策。
