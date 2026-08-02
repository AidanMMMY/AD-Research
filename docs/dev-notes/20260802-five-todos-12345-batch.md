# 2026-08-02 五项待办（FRED/打标/日期/IA中成本/学习P1+P2）统一收官 runbook

## 总览

用户"1、2、3、4、5全做"批准的五项待办，5 个并行子 agent 实施 + 主会话统一收尾。
5 commits（`aec591d`→`961180e`）已 push，Backend CI / Web CI / Deploy #1092 全绿，ECS 冒烟通过。

| # | 事项 | commit | 结果 |
|---|---|---|---|
| 1 | FRED 失效序列替换+回填 | `aec591d` | eu_cpi 换 Eurostat HICP；us_ism_pmi 退役；回填 47,032 行零失败 |
| 2 | 170 通用源学习中心打标 | `309473d` | +37 源（deep34/edu3），种子 256→293，生产已灌 |
| 3 | 非标准日期格式 | `1a62f9e` | 5 种 date-only 格式 + 4 测试，806 news 测试全绿 |
| 4 | IA 中成本四项 | `f9de310` | 情绪双页合并 + 组合 mock 下线 + 加密并入详情页 + 详情页四 tab |
| 5 | 学习 P1 收藏/已读 | `961180e` | user_article_state 表 + 3 API + 我的收藏 Tab |

## 1. FRED 序列（aec591d）

- **eu_cpi**：`CPALTT01EZM657N` 与预案候选 `CPALTT01EZM659N` **均被 FRED 整族下架**（OECD CPALTT01 欧元区家族 400）。换 Eurostat 直系 `CP0000EZ19M086NEST`（HICP Total，EA19，Index 2025=100，月度，1996-12 起，观测端 2026-06 活跃）。
  - **口径真相**：旧 657N 后缀实为"Growth rate previous period"（环比增速），registry 标签"指数"本来就标错了——新 id 正好是指数口径，属标签修正。
- **us_ism_pmi（NAPM）**：ISM 撤销 FRED 再分发授权，无同源替代。地区联储扩散指数（费城/纽约/达拉斯）口径是区域调查、0 中心，与 ISM 全国 PMI 50 荣枯线**不可比，不乱换**。从 SERIES_REGISTRY 退役（含注释）。生产库该 code 本就 0 行，无遗留。
- **生产回填**：`FredService(db).refresh(lookback_days=3650)` → written=47,032、series_count=35、failed=[]。eu_cpi 现有 119 行（2016-08→2026-06，最新值 103）。
- **下轮待办**：`eu_gdp`（NAEXKP01EZQ661S 停 2023-01）、`eu_unrate`（LRHUTTTTEZQ156S 停 2022-10）疑似同批 OECD 下架（API 不报错但静默停更）；生产库孤儿 code `global_djt`/`global_n225`（旧 registry 遗留，无人刷新）。

## 2. 170 源打标（309473d）

- 宁缺勿滥：170 源只打 37 个（enf 17 / ofc 17 / zhm 3），deep 34 / edu 3。
- **不打标的判断基准**（下次扩源参照）：大众快讯线（CNBC/NYT/CBS/PBS）、荐股营销（motleyfool/marketbeat）、监管执法与数据新闻稿（SEC/CFTC/FTC/FDIC/BEA——事实快讯非分析）、行业快讯 Dive 家族、科技汽车快讯、crypto 价格快讯 18 源全跳。
- 打标亮点：央行讲话系（fedspeeches/fedmonetary/bisspeeches/riksbank/dallasfed×3/fedtestimony/boj）、智库（cfr/cato/hoover/mckinsey/epi）、宏观 Substack 系（krugman/chartbook/sumner/braddelong/bonddad/nakedcapitalism/pensionpulse）、行业深度（semianalysis/miningcom/aerotime/breakingdefense）、深度媒体（twreporter/thenewslens/toyokeizai）；edu：finshots、moneymagau。
- 生产已 docker cp 热修灌种（256→293 精确一致），正式部署后代码一致无冲突。
- `test_seed_sources_exist_in_batch_tables` known 宇宙已纳入 EN_FIN/OFFICIAL/ZH_MEDIA 三表（enf_/ofc_/zhm_ 前缀映射）——**下次新批次表必须同步加 known，否则打标测试必红**。

## 3. 非标准日期格式（1a62f9e）

- `_parse_date` 新增 5 种 date-only 格式：`%B %d, %Y`（July 31, 2026，hoover/mckinsey）、`%a, %d %b %Y`（Fri, 31 Jul 2026，fca/fiercehealth）、`%d %b %Y`、`%d %B %Y`、`%Y-%m-%d`。
- 此前这 4 源日期解析失败回退抓取时间，每小时抓的新闻稿源约 1 小时误差。
- 新闻稿类源日期粒度到天即可，naive 返回交 `_extract_pub_date` 套 default_tz。测试在 `test_rss_timezone.py::TestNonStandardDateOnlyFormats`（4 项，含垃圾回退）。

## 4. IA 中成本四项（f9de310）

### 4a. 情绪双页合并
- `/sentiment` 双 Tab（全市场情绪/单标情绪），`/instrument-sentiment` 301 → `/sentiment?tab=instrument`（保留 `?code=`）。
- 切单标 Tab 后市场轮询 `enabled` 停止；菜单"单标情绪看板"移除。
- 详情页情绪空态加"前往分析"按钮 → `/sentiment?tab=instrument&code=<标的>`。

### 4b. 组合 mock 偏离度区块下线
- `Portfolio/index.tsx` 净删 54 行（buildMockDiff/DiffItem/diffColumns/usePoolList）。
- 留 TODO 注释：恢复条件=真实账户持仓聚合接口就绪后改后端实时 diff。
- **死 CSS 遗留**：`Portfolio/styles.css` 的 `.portfolio-diff-summary` 等 diff 专用样式未清，恢复时复用或另行清理。
- **死代码发现**：`web/src/components/DetailAIAnalysis.tsx` 全仓无引用（内含旧文案），建议随下轮死代码清理删除。

### 4c. CryptoDetail 并入详情页
- `/crypto/:code` → `LegacyCryptoRedirect` 301 → `/instruments/:code`。
- 移植：交易信号 tab → `CryptoSignalsModule`（TypeAwareModules，CRYPTO 分支=市场数据卡+信号表）。
- 弃：K线（InstrumentDetail 更强，后端同源 InstrumentDailyBar 表）、相关新闻（同 NewsListPanel）、AI 研究（同 ResearchService）。
- CryptoList 桌面行点击+移动端 QuickSheet 均改跳 `/instruments/:code`。

### 4d. 详情页四 tab 化
- market（默认）/ score / ai / news；tab 入 URL query `?tab=`，非法值回落 market，默认 tab `replace: true` 不污染历史栈。
- 盘点全仓 20+ 处 `/instruments/:code` 跳转均为整页跳转，无面板级锚点，无需兼容层。

### 遗留小项
- 单标 Tab 手动分析新标的后 URL `?code=` 不跟随更新（仅首次预填消费），如需地址栏可分享可后续加回写。

## 5. 学习 P1 收藏/已读（961180e）

详见 `20260802-learning-p1-bookmark-read.md`。要点：
- 迁移 `x5y7z9a1b3c5`（down=w4x6y8z0a2b4）：`user_article_state`（user_id+article_id 复合 PK，bookmarked_at/read_at 可空，取消置 NULL 不删行，已读不刷新首次时间戳）。
- API：POST bookmark（切换语义）/ POST read（幂等）/ GET bookmarks（分页，bookmarked_at DESC）；feed 每项追加 bookmarked/read 布尔（LEFT JOIN 当前用户，跨用户不泄漏）。
- 前端：NewsCard 可选 showBookmark（只知识库语境传）、已读标题 opacity 0.55、我的收藏 Tab、乐观更新集中 `useArticleState.ts`。
- **ECS 验证**：deploy 自动迁移 head=x5y7z9a1b3c5 ✅、news_source_meta=293 ✅、eu_cpi=103 ✅、learning 端点未登录 403 ✅。

## 6. 学习 P2 难度标签（00e65b7，P1 合并后接力）

- **后端**：`GET /learning/feed` 加可选 `difficulty=beginner|advanced`（feed 本就 JOIN meta 表，只加一个 where + 400 校验；注意 NULL 难度源会被过滤排除）；测试 +3 用例（含 difficulty×topic 组合）。
- **前端**：NewsCard 可选 `showDifficulty`（默认 false，/news 零变化；KnowledgeFeed/MyBookmarks 传 true），「入门」绿系/「进阶」橙琥珀系，颜色全走 theme.css token（`--color-success*`/`--color-warning*`，亮暗自适应）；KnowledgeFeed 主题 chips 下加难度筛选 chips（全部/入门/进阶），进 queryKey。
- **测试坑**：vitest.config `globals: false` 时 @testing-library 自动 cleanup 不生效，跨用例 DOM 残留会假阳性——测试文件需显式 `afterEach(cleanup)`。

## 7. 下轮候选闭环（837640c + 290443d，同日晚）

### 7a. eu_gdp 换 id / eu_unrate 退役
- 旧 id 停更实证：`NAEXKP01EZQ661S` 停 2023-01（且值 ~110 实为 OECD 季度**指数**，旧标签"百万欧元"本来错）、`LRHUTTTTEZQ156S` 停 2022-10。
- **FRED 上 Eurostat（source_id=61）共 7,924 条序列：HICP 7,598 条 + GDP 族，失业率 0 条**——这就是 eu_unrate 找不到替代的原因。
- eu_gdp → `CLVMEURSCAB1GQEA19`（Eurostat Real GDP EA19，季度 SA，百万链式 2010 欧元；最新 2026-04-01=2,896,609.2，选 EA19 与 eu_cpi 的 EZ19 保持一致）。
- eu_unrate → 退役：月度同胞 LRHUTTTTEZM156S 同死；唯一活跃的欧元区失业序列是世行**青年**失业率（年度/15-24 岁/ILO modeled，~16% vs 总体 ~6.5%）口径不可比。历史 26 行保留不刷新。前端 `HEADLINE_CODES.eu` + `MACRO_TERM_KEY_MAP` 同步摘掉（否则静默 4→3 卡降级）。
- 生产热修回填 47,019 行/34 序列/零失败；eu_gdp 40 行（2016-07→2026-04），重叠期 ON CONFLICT 覆盖无混单位。

### 7b. 孤儿码清理（裁决记录）
- `global_djt`：全仓零引用，**删 121 行**（停刷根因：4da9aca 把 FRED 海外指数移出 registry，yfinance 为唯一真源）。
- `global_n225`：前端 Dashboard/GlobalMarkets/Macro/termDictionary 四处引用且 yfinance 是活写入方（78 行新鲜到 7-31）——**只删 `source='fred'` 的 120 行 stale**（被 period 排名天然遮蔽，前端无感），保留 yfinance 行。
- **教训**：孤儿码先 grep 引用再动手；同一 code 可多 source 并存，删除要精确到 source。

### 7c. 前端死代码 + 体验小项
- `DetailAIAnalysis.tsx` 零引用删除（其 CSS 类仍被 InstrumentDetail 用，定义在 global/pages-detail.css，未动）；`Portfolio/styles.css` 整文件只剩 3 个 diff 死类，整文件删除 + 移除 import。
- 单标情绪 ingest 成功后 `?code=` 回写地址栏：`setSearchParams` 函数式构造（保留 tab 等既有参数，`replace: true`），守卫已相同则跳过（深链自动分析不多余触发），失败不回写。4 测试覆盖手动/深链/换标的/失败。

## 部署与运维备忘（本批新增）

- **`git rm` 会预暂存删除**——分批 commit 前先 `git status` 看暂存区，否则删除会混入下一个 commit（本批 FRED commit 踩到，已 reset 重做）。
- 多 agent 并行改同一工作树时，commit 顺序按"后端先行、前端随后、迁移殿后"，每个 commit 保证中间态可构建。
- Backend CI 全量 1572 测试约 6-8 分钟，Deploy 不等它（并行跑）——push 后盯三条线。

## 验证记录

- 本地：pytest 1572 passed / check:ci 绿 / vitest 35 passed
- CI：Backend CI 30733139713 / Web CI 30733139725 / Deploy 30733139722（#1092，update.sh exit 0）
- ECS：alembic head、seed 293、eu_cpi 回填、learning 403 守卫（见 §5）
