# AD-Research — 数据源地图

> 全平台所有数据来源的依赖、限速、覆盖范围、维护状态全景。
> 最后更新：2026-07-02
> 最后核实更新：2026-07-21

---

## 1. 数据源总览

| # | 数据源 | 类别 | 覆盖市场 | 接入方式 | Token 依赖 | 限速 | 调度频率 |
|---|---|---|---|---|---|---|---|
| 1 | Tushare Pro | K 线 / 财务 | A 股 + ETF | pip + Pro API | TUSHARE_TOKEN | 200/min（积分制） | 每日 |
| 2 | akshare | 全市场聚合 | A 股 / 港股 / 期货 / 宏观 | pip 免费 | 无 | 各源不同 | 每日 |
| 3 | Finnhub | ETF 列表 / 美股基础 | US | HTTP | FINNHUB_API_KEY | 60/min | 每周 |
| 4 | Tiingo | K 线（美股） | US | HTTP | TIINGO_API_KEY | 50/hour, 500/月 | 每日 + 回填 |
| 5 | FMP | 基本面 / 列表发现 | US | HTTP | FMP_API_KEY | 250/day | 每周 / 按需 |
| 6 | yfinance | K 线（兜底） | Global | pip 免费 | 无 | 频繁易限流 | 兜底 |
| 7 | 新浪财经（美股） | K 线（最终兜底） | US | akshare 库 | 无 | 视源 | 每日兜底 |
| 8 | Binance Public | 加密货币 K 线 | Crypto | HTTP 公开 | 无 | 1200/min | 每日 |
| 9 | FRED | 美国宏观 | US | HTTP | FRED_API_KEY | 120/min | 每日 |
| 10 | BEA | 美国宏观（⚠️ 未接入，仅预留 Key） | US | — | BEA_API_KEY | — | — |
| 11 | BLS | 美国劳工统计（⚠️ 未接入，仅预留 Key） | US | — | BLS_API_KEY (可选) | — | — |
| 12 | 东方财富研报 | 券商研报 | A 股 | akshare 库 | 无 | 视源 | 每日 |
| 13 | 巨潮 cninfo | 上市公司公告 / 定期报告 | A 股 | HTTP 公开 | 无 | 600/hour | 每日 |
| 14 | SEC EDGAR | 美股 10-K/10-Q | US | HTTP | 无（UA 必填） | 10/sec | 每周 |
| 15 | 百度指数 / Google Trends | 情绪代理 | CN/US | pytrends + akshare | 无 | 60s/req | 每日 |
| 16 | 中金所/3 交易所 | 商品期货 | CN | akshare 库 | 无 | 视源 | 每日 |
| 17 | 雪球 | 散户讨论 / 社交 | A 股 | HTTP + Cookie | XUEQIU_COOKIE | 视 Cookie | 5 min |
| 18 | 新浪财经 / 新华财经 / Yahoo / CNBC / Reddit | 财经新闻 | Global | RSS | 无 | 公开 | 5 min |
| 19 | CoinDesk / Cointelegraph | 加密货币新闻 | Crypto | RSS | 无 | 公开 | 5 min |
| 20 | 巨潮公告 | 公告流 | A 股 | HTTP 公开 | 无 | 公开 | 10 min |

---

## 2. 数据存储 / 持久化位置

| 用途 | 路径 | 备份策略 |
|---|---|---|
| PostgreSQL 数据 | `/data/docker/volumes/aliyun-ecs_postgres_data/_data` | 阿里云数据盘 120GB |
| Redis 缓存 + 锁 | `/data/docker/volumes/aliyun-ecs_redis_data/_data` | 同上 |
| Web 构建产物 | `/data/docker/volumes/aliyun-ecs_web_dist` | 镜像内含，部署覆盖 |
| 定期报告 PDF | `/data/ad-research/cninfo_pdfs/{ts_code}/{announcement_id}.pdf` | 同上 |
| 静态资源 | `app/data/static/*.json` | 镜像内含 |

---

## 3. Token 维护清单

> 所有 Token 统一存放在 `/opt/ad-research/deploy/aliyun-ecs/.env`，**不得提交到 Git**。
> 部署时通过 docker-compose `${VAR:-}` 注入到容器内。

| Token | 申请地址 | 申请门槛 | 当前状态 |
|---|---|---|---|
| TUSHARE_TOKEN | https://tushare.pro/register | 注册即有免费档 | ✅ 已配置 |
| FINNHUB_API_KEY | https://finnhub.io/register | 注册即有 | ✅ 已配置 |
| TIINGO_API_KEY | https://www.tiingo.com/account/token | 注册即有 | ✅ 已配置 |
| FMP_API_KEY | https://site.financialmodelingprep.com | 注册即有 | ✅ 已配置 |
| MINIMAX_API_KEY / MINIMAX_CN_API_KEY | https://platform.minimax.io | 注册即有 | ✅ 默认 LLM（`app/services/llm/`） |
| DEEPSEEK_API_KEY | https://platform.deepseek.com | 注册即有 | ✅ 已配置（legacy 备选 LLM） |
| FRED_API_KEY | https://fred.stlouisfed.org/docs/api/api_key.html | 2 分钟自助 | ✅ 已配置 |
| BEA_API_KEY | https://apps.bea.gov/API/signup/ | 注册即有 | ✅ 已配置 |
| BLS_API_KEY | https://data.bls.gov/registrationEngine/ | 注册即有 | ⏳ 待用户注册 |
| XUEQIU_COOKIE | 浏览器登录后导出 | 需要登录态 | ⏳ 待用户填入 |

---

## 4. 已知问题

参考 `docs/dev-notes/20260627-data-source-known-issues.md`。新增已知问题待 phase 4-9 完成后补全。

---

## 5. 维护者指引

- **新增数据源**：必须在 `app/data/providers/` 新建 provider 类 + `app/config.py` 配 Token + `docker-compose.yml` 注入 env + 更新本表第 1 节。
- **停用数据源**：把 provider 类的 cron job 从 `app/core/scheduler.py` 移除，本表第 1 节标 `🔴 停用`。
- **限速变更**：当上游调整限速时，必须更新 provider 内的 `time.sleep(...)`、本表第 1 节限速列、相关测试。
