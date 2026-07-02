# Changelog — 2026-07-02

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

- [ ] Phase 4-9 6 个 agent 全部完成
- [ ] `alembic upgrade head` 一次成功（所有 phase migration 串行）
- [ ] `bash redeploy.sh` 构建无报错
- [ ] 容器启动后 `ps -ef | grep scheduler` 看到 APScheduler 线程
- [ ] `GET /api/v1/scheduler/jobs` 至少返回 **20+ 个 job**（含 news_coindesk、news_cointelegraph、fred_macro_daily、china_macro_daily、listing_events_daily、4 个新 phase 的 job）
- [ ] 手动调用各 phase 的 `refresh` 端点，能看到日志输出且数据落库
- [ ] 前端 6 个新页面（研报库 / 定期报告 / SEC 公告 / 微结构 / 商品期货 / 搜索热度）能正常打开、过滤、查看详情
