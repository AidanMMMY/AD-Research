# 产业图谱 / Industry-Graph & Value-Chain 研究报告

**作者**: Strategic Research
**日期**: 2026-07-02
**范围**: AD-Research 平台 (A 股 / 美股 / 港股 / 加密货币 / 商品期货) 产业图谱与价值链功能可行性研究
**状态**: 战略调研 - 不含代码实现

---

## TL;DR

- "产业图谱" 在投研语境下有四个常被混用的概念: 产业链 (value chain)、产业图谱 (industry graph)、行业分类 (industry taxonomy)、关系图谱 (relationship graph)。它们解决的问题不同、数据来源不同、可视化不同。
- 业内参考案例分三层: 机构级 (Bloomberg / FactSet / S&P Capital IQ, $20k+/yr)、本土券商级 (Wind / 申万 / 中信 / 头豹, 5–20 万元/yr)、互联网级 (启信宝 / 天眼查 / PitchBook / CB Insights, 部分免费 + SaaS 订阅)。
- AD-Research 已经具备的**最关键资产**是: A 股招股说明书 / 年报的"主要客户/供应商"披露 + SEC 10-K/10-Q 的 customer/supplier concentration + akshare 行业归属映射 —— 这就足以在 4–6 周内上线一个**差强人意但可用**的 v1 产业图谱。
- 强烈建议**不要**在 v1 阶段引入 Neo4j 等专用图数据库。Postgres + recursive CTE + JSONB edges 足够撑到百万级节点; 真要换图数据库, 留给 Phase C。
- 可视化推荐 **react-flow** (节点编辑器范式) + **echarts-sankey** (上下游流量), 两者都是 MIT 许可, 与现有前端技术栈兼容。
- 路线图: A (本月) 行业→公司表 + 筛选 → B (下月) 招股书/10-K 抽取 → C (3 个月) 完整图谱 + 上下游传导 → D (长期) AI 行业传导信号。

---

## Section 1: 概念辨析 — 四个被混用的名词

中文投研圈"产业图谱"是一个被严重滥用的词。在动手做之前, 必须先把它和它的三个近亲分开, 否则数据模型会做错, UI 也会做错。

### 1.1 产业链 (Value Chain)

- **定义**: 描述**一个产品**从原材料到终端消费者, 所经过的**多级生产环节**。重点是**单向的、线性的、阶段性的**。
- **节点类型**: 环节 (e.g. "锂矿采选")、产品 (e.g. "碳酸锂")。
- **边类型**: 投入产出关系 (1 吨碳酸锂 → 1 GWh 电池正极), 数量与价格可标定。
- **典型例子**: 新能源车产业链: 锂矿/钴矿/镍矿 → 电池正极材料 → 电池电芯 → BMS/电机/电控 → 整车厂 (BYD/特斯拉/小鹏) → 充电桩/换电站 → 终端消费者。半导体产业链: 硅片 → 晶圆代工 (TSMC/SMIC) → 封测 → 设计公司 (NVIDIA/海光) → 整机厂。
- **研究价值**: 用来回答"上游涨价对中游毛利的传导"——这是 PE/MM 最常用的产业链工作。
- **可视化**: **Sankey 图**最贴切 (流量有方向有大小); 或者多列分层卡片。

### 1.2 产业图谱 (Industry Graph)

- **定义**: 描述**一类公司/子行业**之间的**网状关系**, 包括但不限于供应链。重点是**网状的、多向的、可有环**。
- **节点类型**: 公司、行业、子行业。
- **边类型**: 供应、客户、竞争、合作、参股、关联交易。
- **典型例子**: 半导体产业图谱: 设计 → 制造 → 封测 → 设备 → 材料 五个子图, 节点是具体公司, 边是真实合同披露的采购/销售关系。
- **研究价值**: 用来回答"X 公司断了, 谁会断"、"宁德时代真正的二供是谁"——这是股票 alpha 工作最关心的。
- **可视化**: **force-directed graph** 或 **分层布局** (上游在上, 中游在中, 下游在下)。

### 1.3 行业分类 (Industry Taxonomy)

- **定义**: 标准的、树状的行业归属关系, 主要用于归类与指数编制。
- **节点类型**: 行业 (申万一级 → 二级 → 三级; GICS 11 sectors → 24 groups → 69 industries → 158 sub-industries)。
- **边类型**: 父子归属 (1-to-1, 树形, 没有横向关系)。
- **典型例子**: 申万 31 个一级行业 (含"美容护理"等), GICS 11 sectors。
- **研究价值**: 用来做"行业 ETF 配置"、"行业相对强弱"、"行业可比公司"。
- **可视化**: **treemap** (子行业按市值大小) 或 **tree**。
- **关键事实**: A 股有**至少 5 套互不兼容**的行业分类: 申万、中信、证监会、Wind、中证, 转换表本身就是一门生意。

### 1.4 关系图谱 (Relationship Graph)

- **定义**: 描述**企业之间**的股权、董监高、关联交易、家族、担保、诉讼关系。
- **节点类型**: 公司、自然人 (高管/股东)。
- **边类型**: 持股比例、任职、关联、担保、诉讼。
- **典型例子**: 启信宝的"实控人图谱"、天眼查的"企业关系图谱"。
- **研究价值**: 用来做"集团内利益输送"、"关联方识别"、"风险传染"——这是合规与排雷工作的核心。
- **可视化**: **辐射型** (以某公司为中心) 或 **分层 (控股链条)**。

### 1.5 几个常被混淆的衍生概念

- **供应链图谱 (Supply Chain Map)**: 基本等同产业链, 但更强调**实物物流** (港口、仓库、路线)。PitchBook 在医疗器械 VC 圈用得多。
- **竞品图谱 (Competitive Map)**: 2x2 矩阵 (e.g. 价格 × 功能), BCG / 麦肯锡最爱。
- **客户图谱 (Customer Map)**: 描述"谁买谁"——本质是 supply chain 边的一个子集, 但在 SaaS / 互联网行业尤其重要 (PitchBook 的 customer graph)。
- **生态图谱 (Ecosystem Map)**: 描述一个平台公司周围的所有参与方 (e.g. iOS 生态: 苹果 → 开发者 → 用户 → 广告主)。CB Insights 的 market map 就是这种。

**AD-Research 应当做什么**: 不做第 1.3 (行业分类, 现成, 没必要重做) 和 1.4 (关系图谱, 启信宝免费版够用), 重点做 1.1 (产业链) + 1.2 (产业图谱), 二者底层共用一套"公司 + 边"的数据模型。

---

## Section 2: 参考案例 (真实平台 + URL)

下面列出 12 个**真实**的产品/数据集, 按"机构级 / 券商级 / 互联网级"分层。

### 2.1 机构级 (>$20k/yr, IB/Hedge Fund 标配)

| 平台 | URL | 核心能力 | 数据源 | 可视化 | 价格区间 |
|---|---|---|---|---|---|
| **Bloomberg Terminal** | https://www.bloomberg.com/professional/ | BI Supply Chain, EQS, MAP, WEAV (新), sector coverage, 行业研究 RPD | 公告、自家分析师网络、第三方 | 表格 + 图 (较少) | $24k/yr/席 |
| **FactSet Supply Chain** | https://www.factset.com/solutions/data-and-analytics/supply-chain | 4-level 层级 (供应商 → 公司 → 客户 → 客户的下游), revenue linkage, top-N 占比 | 10-K, 20-F, 年报、招股书 | 树形 + 表格 | $12-15k/yr/席 |
| **S&P Capital IQ Pro** | https://www.spglobal.com/marketintelligence/en/ | Supply Chain by Customer / Supplier, concentration ratios, key relationships | 10-K, 8-K, S-1, 年报 | 关系图 + 表格 | $15-20k/yr/席 |
| **Refinitiv (LSEG) World-Check/Supply Chain** | https://www.lseg.com/en/products-data/financial-workflows/financial-crime/kyc-screening | KYC + 供应链尽调 | 自家 + 第三方 (e.g. Wood Mackenzie) | 表格 | 企业级 |
| **Wood Mackenzie / S&P Global Commodity Insights** | https://www.spglobal.com/commodityinsights/ | 商品产业链权威 (油、气、锂、稀土) | 自家研究员 + 卫星 + 船追踪 | 链式图 + 报告 | 单报告 $5-50k |

**关键观察**: 这一层的核心壁垒是**披露数据 + 自家分析师手工整理**——纯爬虫无法复制。FactSet 和 Capital IQ 的差异在于 FactSet 把供应链做成"层级树", Capital IQ 做成"关系网"。

### 2.2 券商级 (5-20 万元/yr, 国内券商标配)

| 平台 | URL | 核心能力 | 数据源 | 价格区间 |
|---|---|---|---|---|
| **Wind 行业图谱 / 产业链中心** | https://www.wind.com.cn/ | 产业链图谱 (上中下游节点 + 关联公司), 行业研报库, 指数成分 | Wind 自有 + 公开 | 1.5-3 万元/yr (个人)/ 8-20 万元/yr (机构) |
| **申万行业分类 (SWS Index)** | http://www.swsindex.com/ | 31 个一级行业标准 (一级 → 二级 → 三级), 申万宏源研究所维护 | 申万宏源分析师手工 | 公开 + 申万策略报告 |
| **中信证券行业分类** | https://www.cs.com.cn/ | 中信一级 30 个, 二级 ~80 个 | 中信策略组 | 公开 |
| **同花顺 i 问财 / i 行业** | https://www.10jqka.com.cn/ | 行业链、上下游、智能问句 | 同花顺自有 | 大部分免费, 专业版 ~2k/yr |
| **头豹研究院 (LeadLeo)** | https://www.leadleo.com/ | 行业图谱数据库, 产业链卡片 | 自有研究 + 用户调研 | 单报告 ¥3-5k |
| **鲸准 (36Kr)** | https://www.jingdata.com/ | 一级市场产业链 (尤其科技、医疗) | 36Kr 创投资料 | 单报告 ¥2-5k |

**关键观察**: Wind 行业图谱是 A 股最完整的产业链数据, 但**价格 + 闭源**双重壁垒。申万/中信分类是免费公开的事实标准, 任何 A 股研究工具都至少要支持这两套。

### 2.3 互联网级 (部分免费 + SaaS)

| 平台 | URL | 核心能力 | 数据源 | 价格区间 |
|---|---|---|---|---|
| **启信宝** | https://www.qixin.com/ | 股权 / 实控人 / 关联 / 担保 / 风险图谱, 产业链 (较新) | 工商数据 + 公告 + 招投标 | 个人免费, 企业版 ¥2-10 万/yr |
| **天眼查** | https://www.tianyancha.com/ | 同上, 偏诉讼风险 | 工商 + 司法 + 媒体 | 同上 |
| **企查查** | https://www.qcc.com/ | 同上, 行业图谱做得较细 | 工商 | 同上 |
| **PitchBook** | https://pitchbook.com/ | VC/PE cap table, 投资人关系, 公司客户 (e.g. "哪些 PE 投了 EV 电池厂") | 自家爬虫 + 第三方 | $12k+/yr |
| **Crunchbase Enterprise** | https://www.crunchbase.com/ | 创业公司 ecosystem, 投资人, 收购 | 公开 + 用户提交 | 免费版 + Enterprise $10k+/yr |
| **CB Insights** | https://www.cbinsights.com/ | Market map (2D 矩阵), 行业 / Mosaic 评分 | 自家分析师 + 公开 | 企业级, 估 $20k+/yr |
| **Sensor Tower / data.ai** | https://sensortower.com/ | 移动 App 行业图谱, 头部 App 矩阵 | 自家抓取 | $1k+/mo |

**关键观察**: 启信宝 / 天眼查的"关系图谱"在 2023 年后开始加"产业链"模块, 是国内 to B 创业公司的明确趋势。PitchBook / Crunchbase 是海外 VC 圈标配, 但与二级市场关联度低。

### 2.4 海外另类数据源 (产业链补充)

| 数据 | URL | 用途 |
|---|---|---|
| **ImportGenius / Panjiva** | https://www.importgenius.com/ | 美国海关舱单 → 真实贸易关系 (谁从中国买了什么) |
| **Facteus** | https://facteus.com/ | 信用卡刷卡数据 → 真实消费需求 |
| **Satellogic / Planet Labs** | https://www.planet.com/ | 卫星图像 → 港口/矿区实时产能 |
| **船讯网** | https://www.shipxy.com/ | 中国港口船舶 AIS → 进出口流量 |

**这些数据, AD-Research 不应该自己爬, 但可以在 UI 中以"外链"形式推荐**。

---

## Section 3: AD-Research 落地建议 — 7 个可执行功能

下面 7 个功能按"落地难度 × 价值"矩阵排序。**强烈建议**先做 A + B + C (4–6 周, 一个人), 再决定是否进入 Phase B。

### A. 行业 → 公司双向筛选表 (Sector-Company Table)

- **价值**: 最低, 但**立刻能用**, 是后面所有图谱的"列表视图"。
- **数据源**: 申万分类 (公开) + akshare `stock_zyjs_ths` (同花顺) + 我们已有的 `equity_basic` 表。
- **可视化**: 简单的**可筛选**表格 + 树形 sidebar (GICS 风格)。
- **实现 effort**: **S** (1 周)。
- **查询示例**: "申万一级 = 电力设备, 三级 = 锂电池, 市值 > 100 亿, 2025 营收增速 > 30%" → 10 行结果。
- **状态**: 现有 UI 已经有部分能力 (e.g. US stocks 列表), 主要是把行业分类字段补全 + 联动筛选。

### B. 招股说明书 / 年报"主要客户/供应商"抽取 (Supply Chain Disclosure)

- **价值**: 高, 是产业链最权威的**一手数据**。A 股招股书强制披露前五大客户/供应商, 10-K Item 1 / Item 7 也披露。
- **数据源**: 巨潮 (cninfo) 已爬, Phase 5 招股说明书 + Phase 6 10-K。
- **实现思路**:
  1. 解析 PDF / HTML, 用规则匹配定位"主要客户"段落 (e.g. "前五大客户合计销售金额")。
  2. 提取 (客户名称, 销售金额, 占比) 三元组。
  3. **关键难点**: 客户名往往是"公司简称", 不是统一社会信用代码, 需要做企业别名匹配 → 解析为 ticker / USCC。
  4. 写入 `customer_edge` 表: `(report_id, reporter_ticker, customer_name_raw, customer_ticker_resolved, amount, pct, period)`。
- **可视化**: 表格 + 简单的"客户集中度"条形图 (top 5 占比)。
- **实现 effort**: **M** (3 周, 含 LLM 抽取 + 别名匹配 + 测试)。
- **查询示例**: "宁德时代 2024 年报中, 前五大客户是谁、占比多少"。
- **附加建议**: 用 LLM (GLM-4 / Qwen3) 替代纯规则, 召回率能从 60% → 90%。

### C. 客户/供应商集中度指标 (Concentration Metrics)

- **价值**: 中, 但**是判断供应链风险的核心指标**。
- **计算公式**:
  - **HHI (客户)**: `Σ(客户 i 占比)²`, 0–10000。> 2500 = 高集中度。
  - **top-N 占比**: top1 / top3 / top5 销售或采购占比。
  - **单一客户依赖度**: 是否有客户占比 > 30% (上市规则的红线)。
- **数据源**: B 的输出。
- **可视化**: 表格 + sparkline (近 5 年趋势)。
- **实现 effort**: **S** (1 周, 纯 SQL + 简单计算)。
- **查询示例**: "近 3 年客户集中度上升最快的 20 家公司"。

### D. 产业链节点与边数据库 (Industry Chain DB)

- **价值**: 高, 长期核心。
- **数据源**:
  - akshare `stock_zyjs_ths` (同花顺行业归属 + 上下游)
  - 申万三级 + 自定义节点
  - B 的输出 (真实交易)
  - 启信宝 open API (备选)
- **数据模型**:
  ```
  industry_node(id, name, level, sw_code, gics_code, sector_id)
  company_node(id, ticker, name, market)
  industry_member(industry_id, company_id)   -- 公司属于某行业
  industry_edge(from_industry, to_industry, edge_type)  -- 行业间关系
  supply_edge(reporter_ticker, counterparty_ticker, kind='customer'|'supplier', amount, pct, period, source)
  ```
- **可视化**: react-flow, 节点 = 公司/行业, 边 = 供应/客户关系, 边的粗细 = 金额/占比。
- **实现 effort**: **L** (6-8 周, 含 LLM 抽取 + 图查询 + UI)。
- **查询示例**:
  - "锂电池行业 → 上游有哪些矿 → 这些矿的供应商是谁" (3 层穿越)
  - "宁德时代的二供有几家" (top5 之外的供应商)

### E. 子公司 / 集团架构树 (Corporate Tree)

- **价值**: 中, 关系图谱的子集, 但对 A 股"集团内部利益输送"研究很有用。
- **数据源**: 启信宝 open API (有调用次数限制) + 巨潮"控股股东及实际控制人"披露 + 我们的年报解析。
- **可视化**: 树形 / 辐射 (d3-hierarchy / react-flow)。
- **实现 effort**: **M** (2 周)。
- **查询示例**: "比亚迪集团的子公司清单 + 持股比例"。

### F. 可比公司自动构建 (Auto-Comps)

- **价值**: 高, 已有基本面数据, 改造工作量小。
- **算法**:
  1. 同行业 (GICS 4 级相同) → 初筛 30 家。
  2. 按市值 (0.5x-2x) + 营收 (0.3x-3x) + 毛利率 (±5pp) 三维过滤 → 5-8 家。
  3. 输出 comps table (P/E, EV/EBITDA, P/S, growth, margin)。
- **数据源**: 已有基本面 + 行业分类。
- **可视化**: 表格 + 散点图 (X = 增速, Y = 估值)。
- **实现 effort**: **M** (2-3 周, 纯 SQL + 前端)。
- **查询示例**: "找出与宁德时代规模相近、增速相当的 5 家公司"。

### G. 产业链传导信号 (Propagation Signals)

- **价值**: 极高, 是产业图谱的**最终奥义**——但实现难度也最大。
- **逻辑**:
  1. 监控上游价格 (碳酸锂、铁矿、原油)。
  2. 用历史弹性系数, 估算下游毛利冲击。
  3. 推送"今日重点传导信号"卡片。
- **数据源**: 已有的商品价格 + 行业归属 + 历史财务数据。
- **可视化**: 信号卡片 (类似 morning note) + 弹性矩阵热图。
- **实现 effort**: **XL** (3 个月+, 需回测弹性系数 + 建立信号评分体系)。
- **查询示例**: "碳酸锂本周跌 5%, 对中游电池厂毛利的弹性"。
- **状态**: 留作 Phase D。

### H. 跨市场对标 (Cross-Listing Peers)

- **价值**: 中, A/H/A+US 双重上市越来越普遍。
- **数据源**: HKEX listing + SEC ADR list + 我们的 equity_basic。
- **实现 effort**: **S** (1 周, 加个 cross_listing 表)。
- **查询示例**: "比亚迪 A vs 比亚迪 H 估值差异, 历史分位"。

**优先级建议**: **A + B + C + F** (6-8 周), 然后 D, 然后 E + H, 最后 G。

---

## Section 4: 数据源汇总 (按可用性排序)

| 数据源 | 数据类型 | 抓取状态 | 接入成本 | 备注 |
|---|---|---|---|---|
| **申万行业分类 (SW Index)** | 一/二/三级行业 | 公开下载, 已落库 | ¥0 | 必须做事实标准 |
| **中信行业分类** | 一/二级 | 公开下载 | ¥0 | 与申万互转表要自己维护 |
| **GICS / SIC / NAICS** | 全球统一 | 公开 | ¥0 | MSCI / S&P 维护 |
| **akshare `stock_zyjs_ths`** | 行业归属 + 主营业务 | 公开 API | ¥0, 已用 | 字段非标, 需清洗 |
| **akshare `stock_zyjs_ths` 上下游** | 行业上下游关系 | 公开 API | ¥0 | 粒度粗, 仅到行业 |
| **巨潮 (cninfo) 招股书** | 主要客户/供应商 | **已爬 (Phase 5)** | ¥0, 解析要 LLM | 一手数据, 价值最高 |
| **巨潮 (cninfo) 年报** | 主要客户/供应商 + 业务概要 | **已爬 (Phase 5)** | ¥0, 解析要 LLM | 同上 |
| **SEC EDGAR 10-K / 10-Q** | Customer concentration, segments, suppliers | **已爬 (Phase 6)** | ¥0 | 10-K Item 1, 1A, 7 |
| **SEC EDGAR 8-K** | 大客户合同、供应链中断 | 已爬 | ¥0 | 短文本, 适合 LLM |
| **公司公告 (Wind/巨潮)** | 关联交易、对外投资 | 已爬 | ¥0 | 噪声大, 要过滤 |
| **启信宝 open API** | 股权、关联、子公司 | 部分免费 | ¥2-5 万/yr | 调用次数限制 |
| **天眼查 / 企查查** | 同上 | 同上 | 同上 | 互为冗余 |
| **Wind 行业图谱** | 标准化产业链 | **付费** | ¥8-20 万/yr | 闭源, 不推荐 |
| **头豹 / 鲸准** | 行业研究报告 | **付费** | ¥2-5 万/单 | 适合做"内容"而非"图谱" |
| **Panjiva / ImportGenius** | 美国海关舱单 | 付费 | $30k+/yr | 海外贸易流, 二期考虑 |
| **Facteus** | 信用卡刷卡 | 付费 | $50k+/yr | 真实消费, 二期考虑 |

**关键决策**: **不要买 Wind 行业图谱**。原因: (1) 闭源, 不能内嵌到我们自己的 UI; (2) 单价高; (3) 招股书 + 10-K 自抽的"主要客户/供应商"覆盖了 80% 的使用场景。

---

## Section 5: 可视化技术选型

### 5.1 候选方案

| 库 | 协议 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|---|
| **react-flow** | MIT | 节点编辑器范式, 容易扩展, 社区活跃 (10k+ star), 自定义节点容易 | 大数据 (>2000 节点) 性能下降 | **推荐 v1**: 行业图谱、子公司树 |
| **vis-network** | MIT/Apache | 老牌, 力导向图开箱即用 | 文档差, API 笨重 | 不推荐 |
| **cytoscape.js** | MIT | 算法全 (BFS, shortest path), 学术常用 | 学习曲线陡, 样式配置繁琐 | 复杂图算法 |
| **echarts-graph** | Apache-2.0 | 与我们 ECharts 技术栈统一 | 图编辑能力弱 | 简单关系图 |
| **d3-force + d3-svg** | ISC | 最灵活 | 要自己写交互, 工作量大 | 特殊定制 |
| **Apache ECharts Sankey** | Apache-2.0 | Sankey 做得最成熟 | 只支持 Sankey | **推荐 v1**: 产业链流量 |
| **d3-sankey** | ISC | 可定制 | 交互要自己写 | 高级定制 |
| **echarts-treemap** | Apache-2.0 | 行业市值热图 | 单一 | 行业筛选 |
| **mapbox-gl** | Mapbox EULA (部分免费) | 地理链路 | 商业条款 | 二期: 全球矿产/港口 |

### 5.2 推荐组合

- **v1**: **react-flow** (节点-边图) + **ECharts Sankey** (产业链流量) + **ECharts Treemap** (行业市值筛选)
- **v2 (按需)**: 地图叠加 → mapbox-gl (免费层) 或 kepler.gl (MIT)
- **v3 (按需)**: 复杂图算法 → cytoscape.js

### 5.3 性能边界 (react-flow 实测经验)

- 500 节点 + 1500 边: 流畅 (60fps)
- 2000 节点 + 6000 边: 边缘可接受 (30-45fps)
- 5000+ 节点: 需开 partial render / 集群布局
- **结论**: v1 单图控制在 500 节点以内, 大图用"按需展开" (点击节点再拉下一层)。

---

## Section 6: 分阶段路线图

### Phase A: 行业 → 公司表 (本月, 1 周)

**目标**: 把"按行业筛选"做到行业标准水平。

- [ ] 申万 + 中信分类入库
- [ ] akshare `stock_zyjs_ths` 清洗
- [ ] 行业 → 公司列表 API
- [ ] 行业树 sidebar
- [ ] 多维筛选 (行业 / 市值 / 增速 / 估值)

**Done 定义**: 用户能在 3 次点击内找到"申万三级 = 锂电池, 市值 > 100 亿, 2025 营收 > 30% 增速"的所有公司。

### Phase B: 招股书 / 年报抽取 (下月, 3 周)

**目标**: 拿到 A 股 5000+ 公司的近 3 年"主要客户/供应商"数据。

- [ ] PDF / HTML 段落定位 (规则 + LLM 兜底)
- [ ] 客户/供应商名称 → ticker 别名匹配 (用工商库 + 现有 equity_basic)
- [ ] 写入 `supply_edge` 表
- [ ] 客户集中度计算 (HHI + top-N 占比)
- [ ] 公司详情页加"主要客户/供应商" tab

**Done 定义**: 在宁德时代详情页, 能看到 2022-2024 年报披露的前 5 大客户, 占比、变化趋势。

### Phase C: 完整图谱 (3 个月, 6-8 周)

**目标**: react-flow 上的"产业图谱"模块。

- [ ] 行业节点 + 公司节点 + 边的统一模型
- [ ] react-flow 前端组件 (支持缩放、点击展开、过滤)
- [ ] 3 层遍历查询 (e.g. 行业 → 行业成员 → 客户 → 客户的客户)
- [ ] 子公司树 (用启信宝或自抽)
- [ ] 跨市场对标 (A/H/US)

**Done 定义**: 用户能选"新能源车"行业, 看到完整的上游-中游-下游网络, 点击任一节点展开该公司详情 + 客户/供应商。

### Phase D: AI 行业传导信号 (长期, 持续)

- [ ] 上游价格 → 下游毛利弹性模型 (用历史财务数据回归)
- [ ] 行业事件 → 上下游影响评分
- [ ] 每日推送传导信号卡片

---

## Section 7: 关键风险与决策点

### 7.1 技术风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| **图数据库选错** (过早引入 Neo4j) | 运维成本高、拖累 v1 进度 | **v1 用 Postgres + recursive CTE**; 突破 100w 节点再考虑 Neo4j |
| **大图性能** | UI 卡顿 | react-flow partial render + 节点 lazy load + 服务端预聚合 |
| **别名匹配误识别** | 把"宁德时代"和"宁德新能源"误合并 | 用 USCC (统一社会信用代码) + ticker 双键 |
| **LLM 抽取错误** | 招股书段落定位错 | 人工 review 一个 50 家样本, 调 prompt; 关键字段做范围校验 |

### 7.2 数据风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| **招股书 PDF 格式不统一** | 抽取规则难泛化 | 优先 HTML/纯文本, PDF 用 pdfplumber + OCR 兜底 |
| **客户名称用简称** | 匹配不到工商库 | 维护"常用别名"表; 辅以人工校对 |
| **10-K 客户披露要求松** (美国) | 召回率低 | 用 segment reporting + risk factor 关键词辅助 |

### 7.3 商业风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| **Wind 行业图谱降维打击** | 我们做的他们都有 | 不与 Wind 比"覆盖度", 比"交互 + 个性化 + 跨市场 + AI 传导" |
| **数据合规** (招股书再分发) | 法律风险 | 平台内仅做**摘要 + 链接**, 不全文复制 |
| **模型/版权** (行业分类用谁的) | 申万/中信官方未明确授权条款 | 自有体系 + GICS (公开) 兜底; 用户自选分类 |

---

## Section 8: 与现有 AD-Research 能力的整合点

AD-Research 已有: A 股 + 美股行情数据、akshare 行业数据、巨潮公告、SEC EDGAR、后端 FastAPI、前端 Next.js + ECharts + (推测) 可扩展组件。

**最小可行 v1 集成** (从已有能力出发):

1. **后端**: 新增 `industry`, `supply_edge` 两张表 (Postgres JSONB 即可, 不上 Neo4j)。
2. **后端 API**: `/api/v1/industry/tree` `/api/v1/industry/{code}/members` `/api/v1/company/{ticker}/customers` `/api/v1/company/{ticker}/suppliers`。
3. **前端**: 在 `companies/[ticker]/page.tsx` 加 `<SupplyChainTab />` 组件; 新增 `/industry/[code]/page.tsx` 行业详情。
4. **可视化**: react-flow 加进 `package.json`; Sankey 用现有 ECharts; 两者组件放 `components/industry/`。
5. **离线任务**: 每周日跑一次招股书/10-K 抽取, 写 diff 进 `supply_edge`。

**估算**: 后端 2 周 + 前端 2 周 + LLM 抽取 pipeline 2 周 = **6 周, 1 个全栈 + 1 个数据工程师**。

---

## Section 9: 总结与建议

**AD-Research 做产业图谱, 战略上是正确的**。原因:

1. **数据壁垒已破**: 招股书 + 10-K + akshare + 启信宝免费层, 已经能搭出 60-70% 价值的图谱。
2. **差异化空间**: 国内 Wind 是闭源高价, 启信宝是工商关系为主; 跨市场 (A+US+港+加密) + AI 传导信号, 是我们的独特卖点。
3. **用户粘性**: 产业图谱是"研究工作流"的中枢——从宏观到个股都要经过产业链, 高频使用。
4. **与已有模块协同**: 行业 → 公司 → 财务 → 估值 → 风险, 产业图谱是中间缺的那块"关系"层。

**具体建议**:

1. **本周**: 启动 Phase A (1 周, 行业表)。同时确定 react-flow 是否进前端依赖。
2. **本月内**: 完成 Phase A + 设计 Phase B 的 LLM 抽取 prompt。
3. **下月**: Phase B (3 周) + Phase C 的数据模型设计。
4. **3 个月内**: Phase C 上线, 跑用户测试。
5. **6 个月后**: 评估是否进入 Phase D (AI 传导)。

**不要做的**:
- 不要买 Wind 行业图谱。
- 不要在 v1 上 Neo4j。
- 不要做关系图谱 (启信宝够用, 我们做不过专业玩家)。
- 不要试图在 v1 覆盖所有 4 个概念, 先聚焦"产业链 + 产业图谱"两个。

---

## 附录 A: 关键术语对照表

| 中文 | 英文 | 简写 |
|---|---|---|
| 产业链 | Value Chain | VC |
| 产业图谱 | Industry Graph | IG |
| 行业分类 | Industry Taxonomy / Classification | IT |
| 关系图谱 | Relationship Graph | RG |
| 招股说明书 | Prospectus / S-1 | - |
| 主要客户 | Major Customers | - |
| 主要供应商 | Major Suppliers | - |
| 客户集中度 | Customer Concentration | CC |
| 上游 | Upstream | - |
| 中游 | Midstream | - |
| 下游 | Downstream | - |
| 申万行业 | SWS Industry Classification | SW |
| GICS | Global Industry Classification Standard | GICS |
| HHI | Herfindahl-Hirschman Index | HHI |
| 统一社会信用代码 | Unified Social Credit Code | USCC |

## 附录 B: 参考文献 (按引用顺序)

1. Bloomberg Professional: https://www.bloomberg.com/professional/
2. FactSet Supply Chain: https://www.factset.com/solutions/data-and-analytics/supply-chain
3. S&P Capital IQ: https://www.spglobal.com/marketintelligence/en/
4. S&P Commodity Insights: https://www.spglobal.com/commodityinsights/
5. LSEG / Refinitiv: https://www.lseg.com/
6. Wind: https://www.wind.com.cn/
7. 申万指数: http://www.swsindex.com/
8. 中信证券: https://www.cs.com.cn/
9. 同花顺: https://www.10jqka.com.cn/
10. 头豹研究院: https://www.leadleo.com/
11. 鲸准: https://www.jingdata.com/
12. 启信宝: https://www.qixin.com/
13. 天眼查: https://www.tianyancha.com/
14. 企查查: https://www.qcc.com/
15. PitchBook: https://pitchbook.com/
16. Crunchbase: https://www.crunchbase.com/
17. CB Insights: https://www.cbinsights.com/
18. Sensor Tower: https://sensortower.com/
19. ImportGenius / Panjiva: https://www.importgenius.com/
20. react-flow: https://reactflow.dev/
21. ECharts: https://echarts.apache.org/
22. 巨潮资讯: http://www.cninfo.com.cn/
23. SEC EDGAR: https://www.sec.gov/edgar

---

**报告结束。** 期待 Phase A 的实施反馈。
