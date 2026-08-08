"""Asia-focused English RSS batch crawler (third source-expansion wave).

Why this exists (2026-07-28, 资讯源扩充第三轮 — agent C)
---------------------------------------------------------
Complements ``global_rss_batch`` (125 multi-language feeds) and
``independent_batch`` (144 blogs/newsletters) with a **176-feed
English-language wave** aimed at depth rather than breadth of languages:

* **Asian English-language financial media** — India (ET, CNBC-TV18,
  NDTV Profit, YourStory), SEA (VnExpress, Malay Mail, BusinessWorld,
  Vulcan Post, e27, DollarsAndSense), South Asia (Dawn, Daily Star,
  EconomyNext), Gulf (The National, Al-Monitor), Central Asia (Astana
  Times, Eurasianet, CABAR), China English (China Daily, CGTN,
  Pandaily, Gizmochina), Australia/NZ (ABC, The Conversation,
  SmartCompany, Strong Money).
* **International media section feeds** beyond the markets/tech/crypto
  front pages already ingested — Guardian World/Money/Economics/
  Environment/Opinion, NPR Business, NYT World, DW, France 24 EN,
  Politico EU, City A.M.
* **English industry verticals** — semiconductors (Semiconductor
  Engineering, EE Times, TechPowerUp), new energy (Canary Media,
  Utility Dive, Electrek, POWER, Mercom), biopharma (Endpoints, STAT,
  Fierce, BioPharma Dive), automotive (Autocar, Paul Tan, Driving.ca),
  shipping & logistics (gCaptain, The Loadstar, Splash247, CIMSEC),
  commodities & mining (GMK Center, Investing News, Beef Central, NGI,
  Daily Coffee News), plus aerospace/defense/fintech/retail/HR/
  construction trades.
* **Self-hosted investor blogs** — Musings on Markets (Damodaran),
  LT3000, EconomPic, Ernie Chan, The Capital Spectator, plus Asian
  retail-investor voices (ASSI, Boring Investor, Tree of Prosperity,
  Fifth Person, Safal Niveshak, JagoInvestor, Trade Brains, Providend)
  and CA/UK/AU FIRE blogs.

Every feed in :data:`ASIA_EN_FEEDS` was live-verified **from the ECS
production server (mainland China network)** on 2026-07-28 in two
rounds (664 candidates → 185 passes → 176 after dedup/editorial cuts):
HTTP 200 with a browser UA, valid RSS/Atom marker, ≥1 item, average
body text of the first 10 items ≥150 chars, and the newest item within
60 days. Three additional passes were dropped because the parallel
``global_indie_batch`` wave claimed the same US-centric URLs first
(Krebs on Security, Wallet Hacks, Yet Another Value Blog — per the
2026-07-28 coordinator ruling the six Asia-focused overlaps stay
here). The two elimination rounds and per-feed rejection reasons are
recorded in ``docs/dev-notes/20260728-asia-en-batch.md``.

Design notes
------------
* **Table-driven**: one row per feed ``(slug, display_name, feed_url,
  market, language)`` — note the market-before-language order, unlike
  ``global_rss_batch``. Slugs carry the ``asen_`` prefix, which doubles
  as the article ``source`` so the News page / health grid can
  distinguish this wave (worker keyword ``asen_`` / ``asia_en``).
* **Batched jobs**: 176 feeds as 176 scheduler jobs would drown the
  health grid and amplify the APScheduler misfire problem (see the
  20260727 runbook §2). The table is sliced into
  :data:`ASIA_EN_BATCHES` groups (11 feeds each, 16 batches); one hourly scheduler
  job crawls one group sequentially with a polite inter-feed delay.
  :data:`ASIA_EN_BATCH_JOBS` (job_id, label, batch_key) is exported
  here so ``scheduler_jobs`` can register the same wave without
  duplicating batch geometry.
* **Market is ``us`` or ``cn_a`` — never ``global``**: the news API's
  ``_GLOBAL_MARKETS`` whitelist is ``(cn_a, us, crypto)`` and the
  frontend "global" filter expands to that same set, so articles
  written with market="global" are invisible in the default view
  (``app/api/v1/news.py::_expand_market_filter``). China English
  outlets use ``cn_a``; everything else uses ``us`` (same precedent as
  ``indie_monevator`` / ``global_indie_batch``).
* **Language is uniformly ``en``** — the translation drain picks the
  articles up automatically.
* **Selection rule**: no Substack / podcast-only / WeChat channels
  (assigned to other waves), no overlap with existing sources (URL
  dedup against every module under ``app/services/news/sources/`` and
  ``scheduler_jobs.py``), and no feeds whose bodies are
  headline-length.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.services.news.crawler.types import RawArticle
from app.services.news.sources.rss_common import parse_rss_items

logger = logging.getLogger(__name__)

# (slug, display_name, feed_url, market, language).
# slug doubles as article ``source`` (asen_ prefix).
ASIA_EN_FEEDS: list[tuple[str, str, str, str, str]] = [
    ("asen_abc_au_business", "ABC News Business (AU)", "https://www.abc.net.au/news/feed/51120/rss.xml", "us", "en"),
    ("asen_chinadaily_biz", "China Daily Business", "https://www.chinadaily.com.cn/rss/bizchina_rss.xml", "cn_a", "en"),
    ("asen_cnbctv18", "CNBC-TV18", "https://www.cnbctv18.com/commonfeeds/v1/cne/rss/latest.xml", "us", "en"),
    ("asen_dailystar_bd", "The Daily Star Business (BD)", "https://www.thedailystar.net/business/rss.xml", "us", "en"),
    ("asen_dawn_business", "Dawn Business (PK)", "https://www.dawn.com/feeds/business/", "us", "en"),
    ("asen_dhakatribune_biz", "Dhaka Tribune Business", "https://www.dhakatribune.com/feed/business", "us", "en"),
    ("asen_et_economy", "Economic Times Economy", "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms", "us", "en"),
    ("asen_et_industry", "Economic Times Industry", "https://economictimes.indiatimes.com/industry/rssfeeds/13352306.cms", "us", "en"),
    ("asen_et_markets", "Economic Times Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "us", "en"),
    ("asen_gizmochina", "Gizmochina", "https://www.gizmochina.com/feed/", "cn_a", "en"),
    ("asen_japan_forward", "Japan Forward", "https://japan-forward.com/feed/", "us", "en"),
    ("asen_lbo_lk", "Lanka Business Online", "https://www.lankabusinessonline.com/feed/", "us", "en"),
    ("asen_malay_mail_biz", "Malay Mail Business", "https://www.malaymail.com/feed/rss/money", "us", "en"),
    ("asen_ndtv_profit", "NDTV Profit", "https://feeds.feedburner.com/ndtvprofit-latest", "us", "en"),
    ("asen_pandaily", "Pandaily", "https://pandaily.com/feed/", "cn_a", "en"),
    ("asen_straits_asia", "The Straits Times Asia", "https://www.straitstimes.com/news/asia/rss.xml", "us", "en"),
    ("asen_swarajya", "Swarajya", "https://swarajyamag.com/feed", "us", "en"),
    ("asen_thaiger", "The Thaiger", "https://thethaiger.com/feed", "us", "en"),
    ("asen_thenational_ae", "The National (UAE)", "https://www.thenationalnews.com/arc/outboundfeeds/rss/?outputType=xml", "us", "en"),
    ("asen_vnexpress_biz", "VnExpress Business", "https://e.vnexpress.net/rss/business.rss", "us", "en"),
    ("asen_almonitor", "Al-Monitor", "https://www.al-monitor.com/rss", "us", "en"),
    ("asen_asiafinancial", "Asia Financial", "https://www.asiafinancial.com/rss", "us", "en"),
    ("asen_astanatimes", "The Astana Times", "https://astanatimes.com/feed/", "us", "en"),
    ("asen_businesstoday_my", "BusinessToday Malaysia", "https://www.businesstoday.com.my/feed/", "us", "en"),
    ("asen_bworldonline", "BusinessWorld (PH)", "https://www.bworldonline.com/feed/", "us", "en"),
    ("asen_cabar_asia", "CABAR.asia", "https://cabar.asia/en/feed", "us", "en"),
    ("asen_cgtn_business", "CGTN Business", "https://www.cgtn.com/subscribe/rss/section/business.xml", "cn_a", "en"),
    ("asen_conversation_au_biz", "The Conversation AU Business", "https://theconversation.com/au/business/articles.atom", "us", "en"),
    ("asen_devpolicy", "DevPolicy Blog (ANU)", "https://devpolicy.org/feed/", "us", "en"),
    ("asen_e27", "e27 (SG Startups)", "https://e27.co/feed/", "us", "en"),
    ("asen_economynext", "EconomyNext (LK)", "https://economynext.com/feed/", "us", "en"),
    ("asen_insideretailasia", "Inside Retail Asia", "https://insideretail.asia/feed/", "us", "en"),
    ("asen_khaosod_en", "Khaosod English", "https://www.khaosodenglish.com/feed/", "us", "en"),
    ("asen_mothership", "Mothership (SG)", "https://mothership.sg/feed/", "us", "en"),
    ("asen_pakobserver", "Pakistan Observer", "https://pakobserver.net/feed/", "us", "en"),
    ("asen_propakistani", "ProPakistani (PK)", "https://propakistani.pk/feed/", "us", "en"),
    ("asen_rakyatpost", "The Rakyat Post (MY)", "https://www.therakyatpost.com/feed/", "us", "en"),
    ("asen_smartcompany", "SmartCompany (AU)", "https://www.smartcompany.com.au/feed/", "us", "en"),
    ("asen_stackedhomes", "Stacked Homes (SG Property)", "https://stackedhomes.com/feed/", "us", "en"),
    ("asen_techjuice", "TechJuice (PK)", "https://www.techjuice.pk/feed/", "us", "en"),
    ("asen_thaienquirer", "Thai Enquirer", "https://www.thaienquirer.com/feed/", "us", "en"),
    ("asen_toi_business", "Times of India Business", "https://timesofindia.indiatimes.com/rssfeeds/1898055.cms", "us", "en"),
    ("asen_vnexpress_news", "VnExpress News", "https://e.vnexpress.net/rss/news.rss", "us", "en"),
    ("asen_vulcanpost", "Vulcan Post", "https://vulcanpost.com/feed/", "us", "en"),
    ("asen_yourstory", "YourStory (IN)", "https://yourstory.com/feed", "us", "en"),
    ("asen_dw_business", "DW Business", "https://rss.dw.com/rdf/rss-en-bus", "us", "en"),
    ("asen_dw_world", "DW World", "https://rss.dw.com/rdf/rss-en-world", "us", "en"),
    ("asen_fastcompany", "Fast Company", "https://www.fastcompany.com/rss", "us", "en"),
    ("asen_france24_en", "France 24 English", "https://www.france24.com/en/rss", "us", "en"),
    ("asen_guardian_comment", "The Guardian Opinion", "https://www.theguardian.com/commentisfree/rss", "us", "en"),
    ("asen_guardian_economics", "The Guardian Economics", "https://www.theguardian.com/business/economics/rss", "us", "en"),
    ("asen_guardian_env", "The Guardian Environment", "https://www.theguardian.com/environment/rss", "us", "en"),
    ("asen_guardian_money", "The Guardian Money", "https://www.theguardian.com/uk/money/rss", "us", "en"),
    ("asen_guardian_world", "The Guardian World", "https://www.theguardian.com/world/rss", "us", "en"),
    ("asen_irishtimes_biz", "Irish Times Business", "https://www.irishtimes.com/arc/outboundfeeds/rss/?outputType=xml", "us", "en"),
    ("asen_moneyweek", "MoneyWeek", "https://moneyweek.com/feed/all", "us", "en"),
    ("asen_nationalpost", "National Post", "https://nationalpost.com/feed", "us", "en"),
    ("asen_npr_business", "NPR Business", "https://feeds.npr.org/1006/rss.xml", "us", "en"),
    ("asen_npr_world", "NPR World", "https://feeds.npr.org/1004/rss.xml", "us", "en"),
    ("asen_nyt_world", "NYT World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "us", "en"),
    ("asen_eureporter", "EU Reporter", "https://www.eureporter.co/feed/", "us", "en"),
    ("asen_guardian_inequality", "The Guardian Inequality", "https://www.theguardian.com/inequality/rss", "us", "en"),
    ("asen_guardian_tech", "The Guardian Technology", "https://www.theguardian.com/uk/technology/rss", "us", "en"),
    ("asen_politico_eu", "Politico Europe", "https://www.politico.eu/feed/", "us", "en"),
    ("asen_cityam", "City A.M.", "https://www.cityam.com/feed/", "us", "en"),
    ("asen_eetimes", "EE Times", "https://www.eetimes.com/feed/", "us", "en"),
    ("asen_semiengineering", "Semiconductor Engineering", "https://semiengineering.com/feed/", "us", "en"),
    ("asen_semiwiki", "SemiWiki", "https://semiwiki.com/feed/", "us", "en"),
    ("asen_servethehome", "ServeTheHome", "https://www.servethehome.com/feed/", "us", "en"),
    ("asen_tomshardware", "Tom's Hardware", "https://www.tomshardware.com/feeds/all", "us", "en"),
    ("asen_techpowerup", "TechPowerUp", "https://www.techpowerup.com/rss/news", "us", "en"),
    ("asen_wccftech", "Wccftech", "https://wccftech.com/feed/", "us", "en"),
    ("asen_canarymedia", "Canary Media", "https://www.canarymedia.com/rss", "us", "en"),
    ("asen_electrek", "Electrek", "https://electrek.co/feed/", "us", "en"),
    ("asen_oilprice", "OilPrice.com", "https://oilprice.com/rss/main", "us", "en"),
    ("asen_utilitydive", "Utility Dive", "https://www.utilitydive.com/feeds/news/", "us", "en"),
    ("asen_windpower_monthly", "Windpower Monthly", "https://www.windpowermonthly.com/rss", "us", "en"),
    ("asen_drillingcontractor", "Drilling Contractor", "https://www.drillingcontractor.org/feed/", "us", "en"),
    ("asen_marinetech", "Marine Technology News", "https://www.marinetechnologynews.com/rss", "us", "en"),
    ("asen_mercomindia", "Mercom India", "https://www.mercomindia.com/feed/", "us", "en"),
    ("asen_oedigital", "Offshore Engineer", "https://www.oedigital.com/rss", "us", "en"),
    ("asen_powereng", "Power Engineering", "https://www.power-eng.com/feed/", "us", "en"),
    ("asen_powermag", "POWER Magazine", "https://www.powermag.com/feed/", "us", "en"),
    ("asen_sustainabilitytimes", "Sustainability Times", "https://www.sustainability-times.com/feed/", "us", "en"),
    ("asen_biopharmadive", "BioPharma Dive", "https://www.biopharmadive.com/feeds/news/", "us", "en"),
    ("asen_endpoints", "Endpoints News", "https://endpts.com/feed/", "us", "en"),
    ("asen_fiercebiotech", "Fierce Biotech", "https://www.fiercebiotech.com/rss/xml", "us", "en"),
    ("asen_fiercepharma", "Fierce Pharma", "https://www.fiercepharma.com/rss/xml", "us", "en"),
    ("asen_healthcaredive", "Healthcare Dive", "https://www.healthcaredive.com/feeds/news/", "us", "en"),
    ("asen_medcitynews", "MedCity News", "https://medcitynews.com/feed/", "us", "en"),
    ("asen_statnews", "STAT News", "https://www.statnews.com/feed/", "us", "en"),
    ("asen_autocar", "Autocar", "https://www.autocar.co.uk/rss", "us", "en"),
    ("asen_driving_ca", "Driving.ca", "https://driving.ca/feed", "us", "en"),
    ("asen_gaadiwaadi", "GaadiWaadi (IN)", "https://gaadiwaadi.com/feed/", "us", "en"),
    ("asen_paultan", "Paul Tan Automotive News", "https://paultan.org/rss/", "us", "en"),
    ("asen_rushlane", "RushLane (IN)", "https://www.rushlane.com/feed/", "us", "en"),
    ("asen_container_news", "Container News", "https://container-news.com/feed/", "us", "en"),
    ("asen_gcaptain", "gCaptain", "https://gcaptain.com/feed/", "us", "en"),
    ("asen_loadstar", "The Loadstar", "https://theloadstar.com/feed/", "us", "en"),
    ("asen_marinelink", "MarineLink", "https://www.marinelink.com/rss", "us", "en"),
    ("asen_porttechnology", "Port Technology", "https://www.porttechnology.org/feed/", "us", "en"),
    ("asen_splash247", "Splash247", "https://splash247.com/feed/", "us", "en"),
    ("asen_supplychaindive", "Supply Chain Dive", "https://www.supplychaindive.com/feeds/news/", "us", "en"),
    ("asen_cimsec", "CIMSEC", "https://cimsec.org/feed/", "us", "en"),
    ("asen_navalnews", "Naval News", "https://www.navalnews.com/feed/", "us", "en"),
    ("asen_beefcentral", "Beef Central (AU)", "https://www.beefcentral.com/feed/", "us", "en"),
    ("asen_chinimandi", "ChiniMandi (Sugar)", "https://www.chinimandi.com/feed/", "us", "en"),
    ("asen_dailycoffeenews", "Daily Coffee News", "https://dailycoffeenews.com/feed/", "us", "en"),
    ("asen_gmk_center", "GMK Center", "https://gmk.center/en/feed/", "us", "en"),
    ("asen_investingnews", "Investing News Network", "https://investingnews.com/feed/", "us", "en"),
    ("asen_marketherald", "The Market Herald (AU)", "https://themarketherald.com.au/feed/", "us", "en"),
    ("asen_naturalgasintel", "Natural Gas Intel", "https://www.naturalgasintel.com/feed/", "us", "en"),
    ("asen_northernminer", "The Northern Miner", "https://www.northernminer.com/feed/", "us", "en"),
    ("asen_srsrocco", "SRSrocco Report", "https://srsroccoreport.com/feed/", "us", "en"),
    ("asen_wastedive", "Waste Dive", "https://www.wastedive.com/feeds/news/", "us", "en"),
    ("asen_bankingdive", "Banking Dive", "https://www.bankingdive.com/feeds/news/", "us", "en"),
    ("asen_defensenews", "Defense News", "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml", "us", "en"),
    ("asen_fooddive", "Food Dive", "https://www.fooddive.com/feeds/news/", "us", "en"),
    ("asen_frontofficesports", "Front Office Sports", "https://frontofficesports.com/feed/", "us", "en"),
    ("asen_housedive", "Construction Dive", "https://www.constructiondive.com/feeds/news/", "us", "en"),
    ("asen_housingwire", "HousingWire", "https://www.housingwire.com/feed/", "us", "en"),
    ("asen_hrdive", "HR Dive", "https://www.hrdive.com/feeds/news/", "us", "en"),
    ("asen_marketingdive", "Marketing Dive", "https://www.marketingdive.com/feeds/news/", "us", "en"),
    ("asen_marktechpost", "MarkTechPost", "https://www.marktechpost.com/feed/", "us", "en"),
    ("asen_retaildive", "Retail Dive", "https://www.retaildive.com/feeds/news/", "us", "en"),
    ("asen_sportico", "Sportico", "https://www.sportico.com/feed/", "us", "en"),
    ("asen_thedecoder", "The Decoder", "https://the-decoder.com/feed/", "us", "en"),
    ("asen_theregreview", "The Regulatory Review", "https://www.theregreview.org/feed/", "us", "en"),
    ("asen_variety", "Variety", "https://variety.com/feed/", "us", "en"),
    ("asen_venturebeat", "VentureBeat", "https://venturebeat.com/feed/", "us", "en"),
    ("asen_spacecom", "Space.com", "https://www.space.com/feeds/all", "us", "en"),
    ("asen_spacepolicyonline", "SpacePolicyOnline", "https://spacepolicyonline.com/feed/", "us", "en"),
    ("asen_twz", "The War Zone", "https://www.twz.com/feed", "us", "en"),
    ("asen_atlanticcouncil", "Atlantic Council", "https://www.atlanticcouncil.org/feed/", "us", "en"),
    ("asen_fred_blog", "FRED Blog (St. Louis Fed)", "https://fredblog.stlouisfed.org/feed/", "us", "en"),
    ("asen_aspistrategist", "The Strategist (ASPI)", "https://www.aspistrategist.org.au/feed/", "us", "en"),
    ("asen_conversation_global_biz", "The Conversation Business", "https://theconversation.com/global/business/articles.atom", "us", "en"),
    ("asen_coppolacomment", "Coppola Comment", "https://www.coppolacomment.com/feeds/posts/default", "us", "en"),
    ("asen_defenseone", "Defense One", "https://www.defenseone.com/rss/all/", "us", "en"),
    ("asen_geopoliticalfutures", "Geopolitical Futures", "https://geopoliticalfutures.com/feed/", "us", "en"),
    ("asen_assi_sg", "A Singaporean Stock Investor (ASSI)", "https://singaporeanstocksinvestor.blogspot.com/feeds/posts/default", "us", "en"),
    ("asen_boringinvestor", "The Boring Investor (SG)", "https://boringinvestor.blogspot.com/feeds/posts/default", "us", "en"),
    ("asen_dividendgrowth", "Dividend Growth Investor", "https://www.dividendgrowthinvestor.com/feeds/posts/default", "us", "en"),
    ("asen_dollarsandsense", "DollarsAndSense (SG)", "https://dollarsandsense.sg/feed/", "us", "en"),
    ("asen_econbrowser2", "Macro Musings (David Beckworth)", "https://macromusings.libsyn.com/rss", "us", "en"),
    ("asen_econompic", "EconomPic", "https://econompicdata.blogspot.com/feeds/posts/default", "us", "en"),
    ("asen_epchan", "Quantitative Trading (Ernie Chan)", "https://epchan.blogspot.com/feeds/posts/default", "us", "en"),
    ("asen_europeandgi", "European DGI", "https://europeandgi.com/feed/", "us", "en"),
    ("asen_fifthperson", "The Fifth Person (SG)", "https://fifthperson.com/feed/", "us", "en"),
    ("asen_forexlive", "InvestingLive (ex-ForexLive)", "https://investinglive.com/feed", "us", "en"),
    ("asen_freefincal", "freefincal", "https://freefincal.com/feed/", "us", "en"),
    ("asen_lt3000", "LT3000 (Lyall Taylor)", "https://lt3000.blogspot.com/feeds/posts/default", "us", "en"),
    ("asen_mebfaber", "Meb Faber Research", "https://mebfaber.com/feed/", "us", "en"),
    ("asen_musings_markets", "Musings on Markets (Damodaran)", "https://aswathdamodaran.blogspot.com/feeds/posts/default", "us", "en"),
    ("asen_myownadvisor", "My Own Advisor", "https://www.myownadvisor.ca/feed/", "us", "en"),
    ("asen_providend", "Providend (SG)", "https://providend.com/feed/", "us", "en"),
    ("asen_quantstart", "QuantStart", "https://www.quantstart.com/feed/", "us", "en"),
    ("asen_retirementinvestingtoday", "Retirement Investing Today", "https://www.retirementinvestingtoday.com/feeds/posts/default", "us", "en"),
    ("asen_robotwealth", "Robot Wealth", "https://robotwealth.com/feed/", "us", "en"),
    ("asen_routetoretire", "Route to Retire", "https://www.routetoretire.com/feed/", "us", "en"),
    ("asen_safalniveshak", "Safal Niveshak", "https://www.safalniveshak.com/feed/", "us", "en"),
    ("asen_strongmoneyau", "Strong Money Australia", "https://strongmoneyaustralia.com/feed/", "us", "en"),
    ("asen_tawcan", "Tawcan", "https://www.tawcan.com/feed/", "us", "en"),
    ("asen_thepoorswiss", "The Poor Swiss", "https://thepoorswiss.com/feed/", "us", "en"),
    ("asen_valuewalk", "ValueWalk", "https://www.valuewalk.com/feed/", "us", "en"),
    ("asen_boomerandecho", "Boomer & Echo (CA)", "https://www.boomerandecho.com/feed/", "us", "en"),
    ("asen_capitalspectator", "The Capital Spectator", "https://www.capitalspectator.com/feed/", "us", "en"),
    ("asen_dividendguy", "The Dividend Guy Blog", "https://www.thedividendguyblog.com/feed/", "us", "en"),
    ("asen_etftrends", "ETF Trends", "https://www.etftrends.com/feed/", "us", "en"),
    ("asen_investinghaven", "Investing Haven", "https://investinghaven.com/feed/", "us", "en"),
    ("asen_jagoinvestor", "JagoInvestor (IN)", "https://www.jagoinvestor.com/feed/", "us", "en"),
    ("asen_looniedoctor", "The Loonie Doctor (CA)", "https://www.looniedoctor.ca/feed/", "us", "en"),
    ("asen_moneywehave", "Money We Have (CA)", "https://www.moneywehave.com/feed/", "us", "en"),
    ("asen_retirebeforedad", "Retire Before Dad", "https://www.retirebeforedad.com/feed/", "us", "en"),
    ("asen_tradebrains", "Trade Brains (IN)", "https://tradebrains.in/feed/", "us", "en"),
    ("asen_treeofprosperity", "Tree of Prosperity (SG)", "https://treeofprosperity.blogspot.com/feeds/posts/default", "us", "en"),
]

_BATCH_SIZE = 11
ASIA_EN_BATCHES: dict[str, list[tuple[str, str, str, str, str]]] = {
    chr(ord("a") + i): ASIA_EN_FEEDS[i * _BATCH_SIZE : (i + 1) * _BATCH_SIZE]
    for i in range((len(ASIA_EN_FEEDS) + _BATCH_SIZE - 1) // _BATCH_SIZE)
}

# (job_id, label, batch_key) — registered by scheduler_jobs, all hourly.
ASIA_EN_BATCH_JOBS: list[tuple[str, str, str]] = [
    (
        f"news_asia_en_{key}_60m",
        f"亚洲英文财经 RSS {key.upper()} 组",
        key,
    )
    for key in ASIA_EN_BATCHES
]


@dataclass(frozen=True)
class _Feed:
    slug: str
    display_name: str
    url: str
    market: str
    language: str


class AsiaEnBatchCrawler:
    """Sequentially crawl one batch of Asia-focused English feeds.

    Parameters
    ----------
    batch_key:
        Key into :data:`ASIA_EN_BATCHES` (``"a"`` …). Unknown keys
        yield an empty crawl (defensive — a config typo must never
        crash the scheduler).
    delay_seconds:
        Polite pause between feeds; several feeds are small blogs on
        shared infrastructure.
    """

    def __init__(
        self,
        batch_key: str,
        *,
        delay_seconds: float = 2.0,
        timeout_seconds: float = 25.0,
        max_items_per_feed: int = 10,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._batch_key = batch_key
        self._delay = float(delay_seconds)
        self._timeout = float(timeout_seconds)
        self._max_items = int(max_items_per_feed)
        self._client = client

    @property
    def feeds(self) -> list[_Feed]:
        rows = ASIA_EN_BATCHES.get(self._batch_key, [])
        return [
            _Feed(slug=s, display_name=n, url=u, market=m, language=l)
            for s, n, u, m, row in rows
        ]

    async def fetch_recent(self) -> list[RawArticle]:
        owns = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                )
            },
        )
        try:
            out: list[RawArticle] = []
            for feed in self.feeds:
                try:
                    resp = await client.get(feed.url)
                    resp.raise_for_status()
                    out.extend(
                        parse_rss_items(
                            resp.text,
                            source=feed.slug,
                            market=feed.market,
                            language=feed.language,
                            default_author=feed.display_name,
                            max_items=self._max_items,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "asia-en batch %s: feed %s failed: %s",
                        self._batch_key,
                        feed.slug,
                        exc,
                    )
                if self._delay > 0:
                    await asyncio.sleep(self._delay)
            return out
        finally:
            if owns:
                await client.aclose()
