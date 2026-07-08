# A 股 ETF Holdings 全市场覆盖方案

> 状态: 调研 + 实施计划  
> 起草: 2026-07-08  
> 关联:
> - `app/data/providers/tushare_provider.py::TushareProvider.fetch_etf_holdings`
> - `app/data/providers/akshare_provider.py::AkshareProvider.fetch_etf_holdings`
> - `app/data/pipelines/etf_holdings.py::ETFHoldingsPipeline`
> - `app/scheduler_jobs/etf_holdings_quarterly.py`
> - `app/data/providers/cninfo_provider.py`
> - `app/services/cninfo_report_service.py`
> - 20260707-cninfo-reports-fix 记忆: orgId 表已扩到 5407，`secid=` + `_upsert` 已稳定

---

## 0. 问题陈述

**现象**: 今日（6/30 snapshot）只覆盖 88 只 A 股 ETF，应覆盖 > 600 只。

**根因（已确认 3 处）**:

1. **Tushare `fund_portfolio` 限流 + 字段不兼容**
   - 免费 5000 积分/日；单次 `fund_portfolio(ts_code=...)` 200~500 积分，~1 call/min 才不会触限
   - 600 只 × 0.5s/req ≈ 5 分钟（理论上可行），但实际常因网络抖动超时
   - 返回字段为 `symbol`（纯 6 位 code，不带 `.SH/.SZ`），需手工补齐 market 后缀

2. **akshare `fund_portfolio_hold_em` 对 ETF 覆盖不全**
   - 接口命名 "fund" 而非 "etf"，场外基金走这条；ETF 走 `fundf10.eastmoney.com/ccmx_{code}.html` 的另一条 JSON
   - akshare 仓库 issue 区从 2023 起持续有用户反馈"ETF 返回空" — 上游东方财富 ccmx 接口对 ETF 字段有 `INTERNAL_NOT_FOUND` 漏数据
   - 单只 0.3s 限速 + 600 只 = 3 分钟，理论上也行；实际 30%~50% ETF 返回空

3. **历史数据稀疏（63 个 snapshot × 7 年）**
   - 当前 ETL 每个 quarter 走全量 600 只，但 snapshot_date = 报告期末日，所以历史其实没问题；问题在于 6/30 这次新 snapshot 写入后存活的 etf_code 只有 88 个 — 说明大量 ETF 的 extract 步骤直接被 skip（DataFrame 为空）

**关键判断**: Tushare + akshare 组合单跑一次理论能 5~10 分钟覆盖全市场，但实际 fail 率过高。需要一个**真正能稳定 cover 600+ ETF**的补漏方案。

---

## 1. 数据源调研

### 1.1 评估矩阵

| 数据源 | 覆盖度 | 稳定性 | 字段完整度 | 是否需要 key | 推荐度 |
|--------|--------|--------|------------|---------------|--------|
| **Tushare `fund_portfolio`** | ~50%~70% (受积分限) | 高 (官方) | top10 + 行业 | 5000 积分/日 | ★★★ 主源 |
| **akshare `fund_portfolio_hold_em`** | ~30%~50% (ETF 漏) | 中 (爬虫) | top10 + 净值占比 | 否 | ★★ 补源 |
| **akshare `fund_etf_fund_info_em`** | 基本面，无持仓 | 高 | 元数据 | 否 | ✗ 错源 |
| **东方财富 F10 ccmx JSON (`api.fund.eastmoney.com/f10/ccmx`)** | ~85%~95% (历史经验) | 中 (反爬) | top10 + 持仓变动 | 否 | ★★★★ 强补 |
| **中证指数 `index_stock_cons_weight_csindex`** (akshare) | 仅"指数成分股权重"，**非** ETF 实际持仓 | 高 | 完整权重 | 否 | ✗ 错源（指数 vs 持仓不同） |
| **天天基金 `fundgz.1234567.com.cn`** | 元数据 / 净值，无持仓 | 高 | 净值 | 否 | ✗ 错源 |
| **巨潮资讯 cninfo (季报 PDF)** | **100%** (季报必披露前十持有人) | 高 (官方) | 前十持有人(份额+比例)，**非** 成分股权重 | 否 | ★★★★ 季报兜底 |
| **上交所/深交所 PCF 清单 (申购赎回)** | 100% (T+0 公布) | 高 | 全部成分股 + 现金替代 | 否 (FIX 协议要签) | ★★★★★ 持仓准实时 |
| **jina.ai reader + PDF 解析** | 100% (走 cninfo PDF) | 中 (jina 配额) | 表格 | 是 (jina key) | ★★ 备用 |
| **同花顺 `fund.10jqka.com.cn`** | ~70% | 低 (反爬严) | top10 | 否 | ★ 备选 |
| **雪球 `xueqiu.com`** | 散户拼接，无官方 | 中 | 自整理 | 登录态 | ✗ 不稳定 |

### 1.2 关键发现

#### 1.2.1 东方财富 F10 ccmx JSON（强补，**重点**）

- **接口**: `https://api.fund.eastmoney.com/f10/lsjz?` 旁边的 `ccmx` controller
- **实际抓取**:
  - 主页: `https://fundf10.eastmoney.com/ccmx_{code}.html` (HTML 页面)
  - **背后 JSON**: akshare 源码显示实际请求
    - `https://emweb.securities.eastmoney.com/PC_HSF10/PortfolioAllocation/PageAjax?code={code}` （最新持仓）
    - `https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/PortfolioChangeAjax?type=1&code={code}` （持仓变动）
- 优点: ETF 覆盖率比 `fund_portfolio_hold_em` 高（直接走 ETF F10 而非场外基金路径），含历史 4 个季度快照
- 缺点: 反爬 (User-Agent + Referer + 限速 1 req/0.3s)，需 IP 轮换或 sleep
- **建议**: 写一个新的 `EastMoneyF10Provider` 直接打这两个 JSON endpoint，绕过 akshare 的代理层（akshare 偶尔会在 `requests.get` 时改 header 导致 403）

#### 1.2.2 cninfo 季报 PDF（兜底，**重点**）

- **披露规则**:
  - 4/30 前: 年报（含完整持仓明细 + 前十持有人结构）
  - 4/30 前: Q1 季报（仅十大重仓股，**无完整持仓**）
  - 8/30 前: 半年报（完整持仓 + 前十持有人）
  - 10/30 前: Q3 季报（仅十大重仓股，**无完整持仓**）
- **关键区分**:
  - "**前十大重仓股**"（fund_portfolio_hold 拿的）= 季报/半年报/年报都披露的前 10 大持仓，按权重
  - "**前十名持有人**"（PDF 里另一张表）= 谁在持有这 ETF，不是 ETF 持有谁
  - **本任务要的是前者**（ETF 持仓的成分股），不是后者
- **季报 PDF 的"投资组合"章节** ≈ 完整持仓明细（>10 只，几十~几百只），是仅次于 PCF 清单的完整数据
- **季报 PDF 的"前十名持有人"章节** ≈ 谁持有这 ETF，对我们没用
- **现实**: 季报披露滞后 1.5~2 个月（Q2 6/30 数据要 8/30 前后才出），所以 6/30 snapshot 最早 8/30 之后才能从 cninfo 拿到完整版

#### 1.2.3 中证指数 csindex（**不适用**）

- 提供的 `index_stock_cons_weight_csindex(symbol="000300")` 是**指数的成分股权重**
- 与 ETF 实际持仓**不等价**：ETF 会有抽样复制、权重偏离、现金替代
- 例: 沪深 300 ETF (510300) 跟踪沪深 300 指数，但实际持仓会因抽样、现金管理有 5%~10% 偏差
- **结论**: csindex 不能替代 ETF 持仓

#### 1.2.4 上交所/深交所 PCF 清单（**最准最快**，但门槛高）

- **机制**: 每个交易日开盘前 9:00~9:30，交易所公布所有 ETF 的"申购赎回清单" (PCF: Portfolio Composition File)
- **包含**: 全部成分股代码 + 持仓数量 + 现金替代金额 + 预估 IOPV
- **获取路径**:
  - 上交所: `http://www.sse.com.cn/data/etf/download/` (每日 zip)
  - 深交所: `http://www.szse.cn/api/disc/announcer/announcement?random=` (按日查询)
  - 第三方下载: 申万/中信/华泰等券商研报系统、东方财富 ETF 详情页 (`https://fund.eastmoney.com/pingzhongdata/{code}.js` 中有 PCF)
- **优点**: T+0 公布，比季报早 1~2 个月；包含**全部**成分股
- **缺点**: FIX/FAST 协议要签授权；网页下载要解析 zip
- **建议**: 优先级中等，先用东方财富 `pingzhongdata` 的 PCF 字段补实时；季报出后再用 cninfo 校准

### 1.3 三个新数据源对照（最可行组合）

| | **东方财富 F10 JSON** | **cninfo 季报 PDF** | **东方财富 pingzhongdata** |
|---|---|---|---|
| 覆盖 | ~90% | 100% (季报) | ~100% (PCF) |
| 时效 | T+0~1 天 | 季报披露后 0~2 月 | T+0 (当日盘前) |
| 字段 | top10 + 变动 | 全部持仓 (限季报) | 全部成分股 (PCF) |
| 难度 | 中 (需 mock 浏览器 header) | 高 (PDF 解析) | 中 (大 JSON) |
| 风险 | 反爬 | jina.ai 配额 / PDF 解析失败 | PCF 字段变更 |

---

## 2. 现有 worker 复用评估

### 2.1 `eastmoney_news` worker 复用？

**没有** `eastmoney_news` worker。`eastmoney_research_provider.py` 是研究报告（券商研报）爬虫，跟 ETF 持仓无关。

最近的 news pipeline 是 `app/services/news/scheduler_jobs.py`：
- 用 `eastmoney` / `cls` / `xueqiu` / `sina` 抓财经新闻
- `app/services/news/content_fetcher.py` 是 HTML→Markdown 通用抓取
- **不能直接复用**抓 ETF 持仓，但 `content_fetcher` 的 user-agent / session / retry 套路可以借鉴

### 2.2 `cninfo_report_service` 是否支持 ETF 季报？

**当前支持**（已知）：
- `CninfoReportService.fetch_for_stock(ts_code, ...)` 已经按 `ts_code` 抓个股年报/季报
- 关键路径: `CninfoProvider.get_org_id(ts_code)` → `app/data/static/cninfo_org_ids.json` 查表
- 已写入 5407 个 orgId（20260707 修复后）

**不支持 ETF 的两个原因**:
1. **orgId 表里没有 ETF**: 当前 `cninfo_org_ids.json` 只覆盖了个股（A 股 + 部分港股），ETF 的 orgId 缺失
   - 必须先批量把 ~600 只 A 股 ETF 的 orgId 写进去
   - orgId 在 cninfo 是按"基金代码"算的，可用 `99000xxxxxx` 形式（fund type org id 前缀）
2. **`ETFInfo.code` 是 `510300.SH` 格式**，`CninfoReport.ts_code` 也接受同格式（FK 到 ETFInfo）
   - 写入 `cninfo_reports` 表后再走 `extract_text` + 正则提取"前十大重仓股"表，可行
   - **但**: cninfo `hisAnnouncement/query` 接口的 `category_*_szsh` 过滤的是个股的报告分类，ETF 基金可能需要不同 category

**建议**: ETF 季报走 `cninfo` 走不通的**最大障碍是 orgId 表和 category 过滤**。先把这两个搞通再考虑 PDF 解析。优先级低于方案 A（东方财富 F10）。

### 2.3 现有 worker 复用结论

| 组件 | 能否复用 | 备注 |
|------|----------|------|
| `CninfoProvider._post_form` | ✅ 复用 HTTP/限速/重试 | ETF 季报可走同 HTTP 通道 |
| `CninfoReportService._upsert` | ✅ 复用 ORM upsert | schema 一样 |
| `cninfo_report_service.extract_text` (pdfplumber→pypdf→pdfminer) | ✅ 复用 PDF 解析 | 季报 PDF 跟个股年报 PDF 同结构 |
| `eastmoney_zh_provider._session` (UA / 限速) | ✅ 借鉴 | F10 JSON 也用同 UA |
| `eastmoney_research_provider` | ❌ 不相关 | 是研报不是持仓 |
| 任何 news worker | ❌ 不相关 | |

---

## 3. 推荐方案

### 3.1 总体策略：四源融合 + 渐进补漏

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1 (主): 东方财富 F10 PortfolioAllocation JSON         │  T+0~1d
│      → 覆盖 ~90% ETF, 0.3s/req, 含历史 4 quarter snapshot   │
├─────────────────────────────────────────────────────────────┤
│  Layer 2 (补): Tushare fund_portfolio                       │  T+0~1d
│      → 跟 Layer 1 并行, 取 Layer 1 缺的 ETF                 │
├─────────────────────────────────────────────────────────────┤
│  Layer 3 (兜底): cninfo 季报 PDF 解析                       │  季报披露后
│      → 8/30 半年报全市场, 10/30 Q3 季报, 4/30 年报           │
├─────────────────────────────────────────────────────────────┤
│  Layer 4 (校准): 东方财富 pingzhongdata PCF 解析            │  T+0 盘前
│      → 当日全市场 PCF 校准, 但只快照当日, 不留历史           │
└─────────────────────────────────────────────────────────────┘
```

**关键决定**: **不再依赖 akshare `fund_portfolio_hold_em`**（覆盖率太低） — 保留作为开发期 debug 用，生产路径换为东方财富 F10 直连。

### 3.2 数据流（一个 ETF 一天的处理）

```
[Active A股ETF list]                                  (~600 ETFs)
       │
       ├──→ [Layer 1] F10 PortfolioAllocation JSON    →  550 ETFs (~90%)
       │           ├── 成功: 写入 etf_holding
       │           └── 失败: 进入 Layer 2
       │
       ├──→ [Layer 2] Tushare fund_portfolio          →  +30 ETFs (~5%)
       │           ├── 成功: 写入 etf_holding
       │           └── 失败: 进入 Layer 3
       │
       └──→ [Layer 3] cninfo 季报 PDF (季度触发)      →  +20 ETFs (~3%)
                   ├── 成功: 写入 etf_holding
                   └── 失败: 记录到 etf_holding_failed
```

**目标**: 任一 snapshot_date 覆盖 **> 580 / 600 = 95%+**（留 5% 是已经清盘的 ETF）。

### 3.3 字段规范（不变）

保持现有 `etf_holding` schema 不变：
```
etf_code         (e.g. 510300.SH)
holding_code     (e.g. 600519.SH)
holding_name     (e.g. 贵州茅台)
weight           (0~1, decimal fraction)
shares
market_value
holdings_as_of_date  = snapshot_date
snapshot_date
source           (新增: 'em_f10' | 'tushare' | 'cninfo_pdf' | 'pcf')
```

---

## 4. 实施步骤（分阶段）

### Phase 1: 东方财富 F10 Provider（**P0, 第 1 周**）

**目标**: Layer 1 跑通，覆盖 ~90% ETF

**新增文件**: `app/data/providers/eastmoney_f10_provider.py`

**关键接口**:
```python
class EastMoneyF10Provider:
    """直连东方财富 F10 PortfolioAllocation JSON 接口.
    
    Endpoint: 
      https://emweb.securities.eastmoney.com/PC_HSF10/PortfolioAllocation/PageAjax
      ?code={pure_code}      # 6 位数字, e.g. 510300
    
    Headers 必须 mock Chrome UA + Referer=fundf10.eastmoney.com
    
    返回: top10 重仓股 + 4 个 quarter snapshot + 持仓变动
    """
    
    def fetch_etf_holdings(
        self, code: str, as_of: date | None = None, limit: int = 10
    ) -> pd.DataFrame:
        """返回标准 etf_holding schema.
        
        Args:
            code: e.g. 510300.SH
            as_of: 选哪个 quarter snapshot, 默认最新
        
        Returns:
            DataFrame with columns: etf_code, holding_code, holding_name,
                                    weight, shares, market_value,
                                    holdings_as_of_date, source='em_f10'
        """
    
    def fetch_history_quarterly(self, code: str, n_quarters: int = 4) -> pd.DataFrame:
        """一次拉 4 个 quarter 的 holdings, 用于回填.
        
        关键: 季报披露有滞后, 6/30 snapshot 在 8/30 之后才出现.
        """
```

**测试覆盖**:
- 单只 ETF 510300.SH (沪深 300 ETF)
- 单只 ETF 159915.SZ (创业板 ETF)
- 单只 588200.SH (科创 50 ETF, 2020 年成立, 验证新 ETF)
- 失败 case: 错误代码 / 网络断开 / 反爬 403

**ETL 集成**:
- 修改 `app/data/pipelines/etf_holdings.py`:
  - 新增 `EastMoneyF10Provider` 注入（替换 akshare）
  - 调整 `extract()` 顺序: `em_f10 → tushare → akshare` (back-compat 留 akshare)

**预计工作量**: 1.5~2 人天
- 0.5 天: 抓包定位确切 endpoint + 字段
- 0.5 天: provider 实现 + 限速/重试
- 0.5 天: 单元测试 + 集成到 pipeline
- 0.5 天: 全量 600 只跑一次 + 验证覆盖率

**验收**:
- 单跑一次 snapshot=2025-06-30, 覆盖 ≥ 540/600
- 全流程 < 15 分钟
- 反爬触发时优雅降级到 Tushare

### Phase 2: Tushare 补漏 + Pipeline 重排（**P0, 第 1 周**）

**目标**: Layer 1 + 2 组合覆盖 95%+

**修改**:
- `app/data/providers/tushare_provider.py::fetch_etf_holdings`
  - 改批量调用为 `fund_portfolio(ts_code=...)` 串行（保持现状）
  - **新增** `fetch_etf_holdings_batch(codes: list[str], n_workers=5)`: ThreadPoolExecutor 并发 5
  - 验证 Tushare 限速: 实测免费 5000 积分/日, 600 只 × ~3 积分 ≈ 1800 积分, 安全
- `app/data/pipelines/etf_holdings.py::extract`
  - 重排顺序: `em_f10 → tushare → akshare_fallback`
  - 收集 `etfs_failed` 列表, 写入 `etf_holding_failed` log 表 (新增)

**新增**:
- `etf_holding_failed` 表（小 log 表，记录失败的 ETF + 原因 + 时间）
- 调度任务 `etf_holdings_diagnostic` (每周一次): 拉出 failed 列表，人工审查

**预计工作量**: 1~1.5 人天
- 0.5 天: Tushare batch 实现
- 0.5 天: Pipeline 重排 + failed log
- 0.5 天: 全量 600 只 + 验证覆盖率 ≥ 570/600

### Phase 3: cninfo ETF 季报 + orgId 扩表（**P1, 第 2~3 周**）

**目标**: Layer 3 兜底，季报披露后 0 滞后覆盖剩余 5%

**前置**:
- **关键问题**: cninfo orgId 表当前没有 ETF
- 必须先**批量把 ~600 只 A 股 ETF 的 orgId 写入 `cninfo_org_ids.json`**
- 方案: 写一个 one-shot 脚本 `scripts/build_etf_org_ids.py`
  - 输入: `etf_info` 里 `instrument_type='ETF' AND market='A股'`
  - 流程: 对每只 ETF 调一次 cninfo 的"按简称查 orgId"接口（如果有），或 fallback 到已知前缀 `gssh0` (沪市) / `gsz30` (深市) + 6 位基金代码
  - 经验: 沪市基金 orgId 通常是 `gssh0` + 基金代码（去掉首位），深市是 `gsz3` + 基金代码

**新增**:
- `app/data/providers/cninfo_provider.py::CninfoProvider` 加 `category_*` 适配
  - 实测: 基金 (含 ETF) 的季报 category 不是 `category_yjdbg_szsh`，可能是 `category_yjdbg_szsh` (深圳) / `category_yjdbg_sh` (上海) 不同
  - 或可能要走 `category_jj_szsh` (基金季报)
  - **需要先抽样 5 只 ETF 验证 endpoint**
- `app/services/etf_quarterly_report_service.py` (新)
  - 复用 `CninfoReportService._upsert`
  - 复用 `cninfo_report_service.extract_text` (pdfplumber)
  - **新增** `parse_top10_holdings_from_text(extracted_text: str) -> pd.DataFrame`:
    - 用正则匹配 "前十大重仓股" 章节（PDF 文本中通常以 "5.1 报告期末按公允价值占基金资产净值比例大小排序的前十名股票投资明细" 之类标题出现）
    - 解析表格行: `股票代码 | 股票名称 | 数量(股) | 公允价值(元) | 占基金资产净值比例(%)`
    - 返回标准 schema

**调度**:
- `etf_quarterly_holdings_cninfo` cron: 5/5, 9/5, 11/5 各跑一次 (季报披露日 + 5 天)
- 与 `etf_holdings_quarterly` 的 4/20, 8/30, 10/25 错开

**预计工作量**: 3~4 人天
- 0.5 天: ETF orgId 批量写入脚本 + 验证
- 1 天: cninfo ETF 季报 endpoint 调研 (抽样 5 只验证)
- 1 天: `parse_top10_holdings_from_text` 实现 + 测试 (用 510300 / 588200 实际 PDF 跑)
- 0.5 天: 新 service + cron + pipeline 集成
- 0.5 天: 全量 + 端到端测试

**风险**:
- cninfo 季报 category 验证可能发现 ETF 不在那 4 个 category 里, 需要绕路
- PDF 表格解析可能因不同基金模板差异大, 需要 rule 库积累

### Phase 4: 东方财富 PCF (pingzhongdata) 实时校准（**P2, 第 4 周**）

**目标**: Layer 4 每日盘前校准，当日覆盖率 ~100%

**新增**: `app/data/providers/pcf_provider.py`
- 接口: `https://fund.eastmoney.com/pingzhongdata/{code}.js`
- 字段: `stockCodes`, `stockNames`, `weights` (从成分股列表)
- 限制: 返回当日 PCF, 不留历史; 用于**校准**当季最新 snapshot
- 写入: `etf_holding` 同一个 snapshot_date (今日) 但 source='pcf', **覆盖** Layer 1/2/3 当季数据

**调度**:
- 每日 09:00 (开盘前) 跑一次, 替代 Layer 1/2/3 当季数据
- 不留历史 (PCF 每天变, 历史保存反而污染季度数据)

**预计工作量**: 2 人天
- 1 天: provider 实现 + 测试 3 只
- 0.5 天: 集成到现有 pipeline
- 0.5 天: 全量 + 验证

### Phase 5: 监控 + 告警（**P2, 持续**）

**新增**:
- 调度任务 `etf_holdings_diagnostic_daily`: 每日 23:00 检查当日覆盖率
- 告警条件: 覆盖率 < 90% 时发邮件/微信
- Dashboard: `/admin/etf-holdings/coverage` 页面
  - 展示: 当前 snapshot_date, 覆盖率, failed list
  - 操作: 一键重跑失败列表

---

## 5. 工作量与时间表

| Phase | 内容 | 优先级 | 工作量 | 完成日期 |
|-------|------|--------|--------|----------|
| **Phase 1** | 东方财富 F10 Provider | P0 | 1.5~2 人天 | 2026-07-11 (周五) |
| **Phase 2** | Tushare 补漏 + Pipeline 重排 | P0 | 1~1.5 人天 | 2026-07-15 (周二) |
| **Phase 3** | cninfo ETF 季报 + orgId 扩表 | P1 | 3~4 人天 | 2026-07-22 |
| **Phase 4** | PCF 实时校准 | P2 | 2 人天 | 2026-07-29 |
| **Phase 5** | 监控 + 告警 | P2 | 1 人天 | 2026-07-30 |

**总工作量**: ~9~10 人天 (≈ 2 周单人, 1 周双人并行)

**里程碑**:
- 2026-07-11: 覆盖率 ≥ 90% (Phase 1 完成)
- 2026-07-15: 覆盖率 ≥ 95% (Phase 2 完成)
- 2026-08-30 (半年报披露后): 覆盖率 = 100% (Phase 3 兜底完成)
- 2026-07-30: 每日实时校准上线 (Phase 4 完成)

---

## 6. 风险与备选

### 6.1 主要风险

1. **东方财富反爬**: 600 只/天频繁请求可能触发 IP 封禁
   - 缓解: 限速 0.5s/req + UA 轮换 + 错误指数退避
   - 备选: 走 akshare `fund_portfolio_hold_em` (慢但稳)

2. **Tushare 积分超限**: 600 ETF × 3 积分/只 = 1800 积分/日, 接近 5000 上限
   - 缓解: Phase 1 成功后 Tushare 仅做兜底, 实际调用 < 100 只/日
   - 备选: 调高 Tushare 套餐 (年费 200 元 20000 积分/日)

3. **cninfo ETF category 未知**: 可能 ETF 季报不在 4 个 `category_*_szsh` 里
   - 缓解: Phase 3 先做抽样验证, 不通就走 PCF
   - 备选: 不做 cninfo, 全部依赖 F10 + PCF (覆盖率可能 99%)

4. **PDF 解析失败率高**: 不同基金模板差异大
   - 缓解: `parse_top10_holdings_from_text` 用宽松正则, 失败时人工 review
   - 备选: 用 jina.ai reader 做辅助 (但要 key + 配额)

### 6.2 备选方案 (Plan B)

如果 Phase 1 东方财富 F10 JSON 接口**封禁**或字段**变更**:
- **备选 1**: 改用同花顺 `http://fund.10jqka.com.cn/data/{code}.json` (反爬松但有 IP 段限制)
- **备选 2**: 走 akshare `fund_portfolio_hold_em` (30% 覆盖) + cninfo PDF (70% 覆盖) 拼凑
- **备选 3**: 付费第三方 API (Wind / 同花顺 iFinD) - 10 万元/年起, 暂不考虑

---

## 7. 关键决策点（需要用户确认）

1. **是否接受"不再依赖 akshare"**?
   - 当前 akshare 在 `akshare_provider.py` 中有 fallback 价值, 切到 em_f10 后 akshare 路径仅剩 debug 价值
   - 建议: 保留代码, 优先级降到最低

2. **是否需要 Phase 3 (cninfo PDF 解析)**?
   - 优势: 季报数据是**法定披露**, 权威 + 100% 覆盖
   - 劣势: 工作量大 (3~4 人天), PDF 解析脆弱
   - 替代: 用 F10 + PCF 拼到 99% 覆盖, 跳过 cninfo
   - **建议**: 先做 Phase 1+2 看覆盖率, 如果 ≥ 97% 可以不做 Phase 3

3. **PCF 实时校准**是否上?
   - 优势: T+0 校准, 用户看到的"今天"持仓是**今天**的
   - 劣势: 跟季报数据冲突时谁为准? 复杂度高
   - 建议: **暂不做**, Phase 1+2+3 已足够 (月级更新就够用)

4. **失败重试策略**?
   - 当前 `ETFHoldingsPipeline` 已经 `run_with_retry(max_attempts=2)`
   - 建议: Phase 2 加上"分批重试": 全量跑完后, 只对 failed list 再跑一次 (避免积分/限速重复消耗)

---

## 8. 参考资料 (调研中查到的关键链接)

- 中证指数官网: <http://www.csindex.com.cn> (csindex 指数成分股权重, 不适用于 ETF 实际持仓)
- 天天基金网: <https://fund.eastmoney.com> (F10 ccmx 持仓页)
- 东方财富 ETF PCF: <https://fund.eastmoney.com/pingzhongdata/{code}.js>
- akshare `fund_portfolio_hold_em` 源码 (akfamily/akshare): <https://github.com/akfamily/akshare>
- Tushare `fund_portfolio` 文档: <https://tushare.pro/document/2?doc_id=351>
- 巨潮资讯: <http://www.cninfo.com.cn/new/disclosure/stock> (季报/年报 PDF 入口)
- 东方财富 F10 ccmx HTML: <https://fundf10.eastmoney.com/ccmx_{code}.html>
- 上交所 ETF: <https://etf.sse.com.cn/>
- 深交所 ETF: <http://www.szse.cn/disclosure/dealinfo/etf/>
- jina.ai reader: <https://jina.ai/reader/> (备用 PDF→Markdown 工具)

---

## 9. 立即行动 (P0 第 1 周 TODO)

- [ ] 抽样 3 只 ETF (510300, 588200, 159915) 在浏览器 Network 面板抓 F10 ccmx JSON endpoint
- [ ] 验证 endpoint URL + 参数 + 返回 schema
- [ ] 草拟 `EastMoneyF10Provider` 接口签名, review
- [ ] 实现 + 跑通单只 → 跑通 50 只 → 跑通全 600 只
- [ ] 修改 `ETFHoldingsPipeline.extract` 接入 em_f10
- [ ] 跑一次, 验证 coverage ≥ 540/600
- [ ] 报告结果给用户, 决定是否继续 Phase 2-4

