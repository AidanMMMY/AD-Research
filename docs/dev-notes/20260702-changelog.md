# Changelog — 2026-07-02

> 最后核实更新：2026-07-21（文末增补「2026-07 重大变更」一节）

> 本日新增：宏观数据接入完成 + 5 类新数据源 pipeline 上线 + B-8 调度器激活 + 数据源地图。

---

## 数据源

### ➕ 宏观数据（Phase 2 上线，部署激活）
- FRED：美国 GDP / CPI / 失业率 / 收益率曲线 / M2 等 **24 个 series**，每日 03:00 Asia/Shanghai 拉取
- BEA：美国 NIPA 表，PID/固定资本，每周拉取
- China macro：akshare `macro_china_*` 系列（GDP/CPI/PPI/M2/PMI/SHIBOR/RRR），周一至周五 09:30
- 新表：`macro_indicator`（unique 约束 `(code, region, period, source)`）
- API：`GET /api/v1/macro/indicators-list`、`/latest`、`/codes`、`/refresh-china`

### ➕ Phase 4：东方财富研报
- 通过 akshare `stock_research_report_em` 抓取券商研报（含标题/券商/行业/发布日期/评级/PDF 链接）
- DeepSeek 摘要：`summary`（200 字）+ `key_points`（JSON 数组 3-5 条）+ `target_price`（如披露）
- 新表：`research_reports`（unique 约束 `(ts_code, title, publish_date)`）
- 调度：每日 18:00 拉取 + 每 2 小时补摘要
- API：`GET /api/v1/research-reports`

### ➕ Phase 5：cninfo 巨潮定期报告
- 范围：**沪深 300 + 中证 500 = 800 家公司**，**2026 年**（用户确认 B 档，**不回填**）
- 数据：报告 metadata + PDF 文本提取（pdfplumber）
- 新表：`cninfo_reports`（unique 约束 `announcement_id`）
- 存储：PDF 文件落 `/data/ad-research/cninfo_pdfs/{ts_code}/{announcement_id}.pdf`（磁盘预估 ~30GB/年）
- 调度：每日 17:00 拉取
- API：`GET /api/v1/cninfo-reports`

### ➕ Phase 6：SEC EDGAR
- 范围：**S&P 500 成分股**（约 500 家）
- 数据：10-K / 10-Q / 20-F filing metadata（accession number, primary document, filing date, XBRL 财务指标）
- 强制 User-Agent：`AD-Research research@example.com`（SEC 政策）
- 限速：10 req/sec（强制 0.11s 间隔）
- 新表：`sec_filings`（unique 约束 `accession_number`）
- 调度：每周六 06:00 UTC 拉取
- API：`GET /api/v1/sec-filings`

### ➕ Phase 7：akshare 微结构数据
- 4 类数据：
  - **龙虎榜**（`stock_lhb_detail_em`）
  - **沪深港通资金流**（`stock_hsgt_fund_flow_summary_em` / `stock_hsgt_individual_em` / `stock_hsgt_hold_stock_em`）
  - **融资融券**（`stock_margin_underlying_info_szse` / `stock_margin_underlying_info_sse`）
  - **限售解禁**（`stock_restricted_release_list_em`）
- 4 个新表：`lhb_records` / `hsgt_flows` / `margin_balances` / `restricted_releases`
- 调度：每日 18:30 拉取（限售解禁每周一 09:00 刷新 60 天日程）
- API：`GET /api/v1/microstructure/{lhb,hsgt,margin,restricted-releases,summary}`

### ➕ Phase 8：商品期货
- 覆盖：**上期所 (SHFE) / 大商所 (DCE) / 郑商所 (CZCE) / 中金所 (CFFEX) / 能源中心 (INE)**，约 70 个主力合约
- 数据：日 K + 结算价 + 持仓量 + 仓单
- 2 个新表：`futures_contracts`（合约列表）+ `futures_daily_bars`（日 K）
- 调度：每日 16:30 拉日 K；每月 1 号 03:00 刷合约列表
- API：`GET /api/v1/futures/{contracts,daily,dashboard,leaderboard}`

### ➕ Phase 9：搜索指数
- Google Trends：`pytrends` 库，**强制 60s/req** 限速（Google 反爬严格）
- 百度指数：akshare `search_index_baidu`（**如可用**）+ 备用 HTML scrape 代理
- 关键词维护：`app/data/static/search_keywords.json`（A 股大盘 / 热门个股 / 宏观主题 3 大类）
- 新表：`search_trends`（unique `(keyword, region, source, trade_date)`）
- 调度：每日 03:00 Asia/Shanghai，每天限前 5-10 个关键词轮转覆盖
- API：`GET /api/v1/search-trends`

---

## 部署 / 运维

### B-8：APScheduler 调度器激活
- 之前发现 `ENABLE_SCHEDULER` 环境变量未设，scheduler 实际从未启动，所有 cron 任务形同虚设
- **修复**：
  - `deploy/aliyun-ecs/.env` 增加 `ENABLE_SCHEDULER=true`
  - `deploy/aliyun-ecs/docker-compose.yml` 增加 `ENABLE_SCHEDULER` 注入
  - 同步补充 `FRED_API_KEY` / `BEA_API_KEY` / `BLS_API_KEY` / `XUEQIU_COOKIE` env
- 验证：重启 backend 后 `GET /api/v1/scheduler/jobs` 应返回 18+ 个 job

### 文档
- 新增 `docs/20260702-data-source-map.md`：所有数据源全景表
- 新增 `docs/20260702-changelog.md`：本文档
- 后续待补：`docs/dev-notes/20260702-*.md`（具体 phase 实现细节）由 6 个 phase 任务完成后由各 agent 补全

---

## 已知遗留

- ⏳ BLS API key 待用户注册（链接：https://data.bls.gov/registrationEngine/）
- ⏳ 雪球 Cookie 待用户填入 `.env`（`XUEQIU_COOKIE`）
- ⏳ Phase 4-9 6 个 agent 仍在后台运行中，完成后需要：
  1. 一次完整的 alembic 迁移（4-9 各自带 migration）
  2. 一次 `bash redeploy.sh` 重新构建镜像
  3. 启动后端并验证 `GET /api/v1/scheduler/jobs` 返回值
  4. 触发各 phase 手动 refresh 端点验证数据落库
- ⏳ Changelog 表格里的"调度频率"列将在 phase agent 完成后核对实际 cron 配置后补全

---

## 验收清单

- [x] Phase 4-9 6 个 agent 全部完成
- [x] `alembic upgrade head` 一次成功（所有 phase migration 串行）
  - 服务器从 `1c9321d3cb37` 升级到 `e2f3a4b5c6d7`（head）
  - 9 个 phase migration + 2 个 merge migration 全部跑通
- [x] `bash redeploy.sh` 构建无报错（镜像重建后 alembic 自动升级）
- [x] 容器启动后 `[Scheduler] Started on worker pid=11` 出现在 uvicorn 日志
- [x] 6 个新 phase 端点全部上线：
  - `GET /api/v1/research-reports` → 401（需登录）
  - `GET /api/v1/cninfo-reports` → 401
  - `GET /api/v1/sec-filings` → 401
  - `GET /api/v1/microstructure/summary` → 401
  - `GET /api/v1/futures/dashboard` → **200**（空数据，符合预期）
  - `GET /api/v1/search-trends/dashboard` → 401
- [x] `ENABLE_SCHEDULER=true` + `FRED_API_KEY` 已注入容器 env
- [x] 前端 6 个新页面路由已注册（`/research-reports`, `/cninfo-reports`, `/sec-filings`, `/microstructure`, `/futures`, `/search-trends`）

## 后端测试覆盖

- Phase 4 (research_reports): 15 passed
- Phase 5 (cninfo_reports): 19 passed
- Phase 6 (sec_filings): 16 passed
- Phase 7 (microstructure): 14 passed
- Phase 9 (search_trends): 12 passed
- **总计: 76 passed**

---

## 2026-07 重大变更（2026-07-21 补记，基于 git log 归纳）

> 7 月共 260+ 提交，以下按主题归纳里程碑；详细过程见各 `docs/dev-notes/202607*.md`。

### 全球市场与地缘事件（07-04 ~ 07-12）
- K11 全球市场 P0：FRED 新增 7 个 global series（DXY/Brent/WTI/黄金/SP500/USDJPY/DGS30）、前端 `/global` 页（GlobalMarkets）+ Dashboard 全球区块
- 地缘事件体系：`event_category` 扩展 `geopolitics/central_bank/election/trade_war/sanction`，`/news` 支持按类目过滤；GlobalMarkets 页落地「重大政治/地缘事件」小卡 + AI Help 上下文注入；07-12 事件窗口由 24h 扩为最近 7 天
- 全球市场指数 yfinance + akshare 采集（`global_indices_fetcher.py`，Phase 5d/6a，每日 16:00）；`/macro/indices/global` 端点（07-09）

### 新手教学系统（07-04 起，K6/K14/K15）
- OnboardingTour（后扩为 6 步、`data-onboard` 真实 DOM 锚定、a11y Skip Tour + focus restore）、ContextHint、novice/pro mode、`learningMode`（默认开启）、StatExplainer、PageHeader `tutorial` slot、`/learning` 情景教程页、DailyLesson 组件、术语词典 `relatedTerms`

### 数据与管线（07-07 ~ 07-21）
- 微信公众号 wewe-rss 接入（`wechat_zeping` 源 + AI 营销过滤，每 15 分钟）
- ETF 持仓三线采集（Eastmoney F10 + cninfo PDF + Tushare）+ 季度历史 + 覆盖度统计页
- cninfo 覆盖从 HS300+CS500 扩至全量 A 股 3,209 只 + 全量回填；PDF 批量下载/文本提取 Celery 任务
- 市场资金流（Plan C，`market_fund_flow` 表 + FundFlow 页）；复权因子历史（`adj_factor_history`）回填
- Celery worker 引入（07-12，长任务剥离 API 进程），后拆为 `indicator` / `cninfo` / `celery` 三队列
- 指标计算 SQL 后端（`INDICATOR_BACKEND=sql`）+ `code_prefix` 分片并行补齐；07-21 性能优化（bars CTE 改 LATERAL LIMIT，chunk 128s→<2s）
- 板块轮动：GICS → 申万 2021 行业指数官方回报（Phase 3）+ 官方/等权对照
- 指标正确性系统性修复（前复权、百分比口径、风险维度、RS、Crypto、年化；见 `20260718-*` 审计与 `20260721-*` 交叉核实报告）

### 策略与回测（07-16）
- 参数优化（`optimization_engine.py`）、横截面回测、通用组合策略

### 前端与体验（07-05 ~ 07-21）
- 视觉重构 Phase 4-7（inline style 清理 + 38 个页面级 CSS）→ 密度系统（compact/comfortable/spacious）→ **07-21 全站视觉统一重构（6915438）**；注意工作区仍有未提交的后续视觉改动（`AuroraBackground.tsx` / `GlassCard.tsx` 已删除）
- Dashboard v8 市场指挥中心（07-20）；此前经历市场脉搏分组、自选股/标的池卡片化等多轮重构
- ⌘K 命令面板 + 全局搜索、Core Web Vitals 监控（`/api/v1/stats/web-vitals`）、深色模式跟随系统、数据导出 CSV/Excel、K 线前复权切换、/favorites 自选股页

### LLM 与 AI（07-11 ~ 07-19）
- **LLM Provider 全平台从 DeepSeek 切换到 MiniMax**（`LLM_PROVIDER` env，DeepSeek 保留为 legacy；07-11）
- overnight-research 20 小时连续研究 worker（`agent/`，07-18）+ 新闻爬虫扩展 + embedding + RAG（07-19）

### 安全与运维（07-16 ~ 07-20）
- refresh token 轮换透传、API 鉴权收敛、pools IDOR 修复（07-20）
- ETL 监控 + stuck 清理 + 多市场 freshness + status_report staleness（07-19）；每小时磁盘检查任务
- 部署加固：healthcheck start_period 覆盖 alembic 大列 ALTER、orphan 清理、4 个隐藏 tripwire runbook、nginx SSE 修复、compose 治理（07-19~20）
