# 投资研究平台 — 美股 & AI 功能集成指南

> **项目**: Investment Research Platform (AD-Research)  
> **最后更新**: 2025-06-25  
> 最后核实更新：2026-07-21（LLM 默认已切换为 MiniMax / DeepSeek，Anthropic 相关描述已更新；前端页面更名与路由已同步现状）
> **覆盖**: 阶段1（美股数据管道）+ 阶段2（个股支持）+ 阶段3（AI Vibe Trading）

---

## 目录

1. [平台架构概览](#1-平台架构概览)
2. [环境配置](#2-环境配置)
3. [阶段1：美股数据管道](#3-阶段1美股数据管道)
4. [阶段2：个股支持](#4-阶段2个股支持)
5. [阶段3：AI Vibe Trading 研究层](#5-阶段3ai-vibe-trading-研究层)
6. [前端功能指南](#6-前端功能指南)
7. [API 参考](#7-api-参考)
8. [运维指南](#8-运维指南)
9. [常见问题](#9-常见问题)

---

## 1. 平台架构概览

### 技术栈

| 层级 | 技术 |
|------|------|
| **后端** | Python 3.12, FastAPI, SQLAlchemy 2.0, PostgreSQL 16, Redis 7 |
| **前端** | React 18, TypeScript 5, Vite 5, Ant Design 5.12 |
| **AI/LLM** | MiniMax (默认, minimax-m3) / DeepSeek (legacy, deepseek-v4-flash)，Anthropic Claude provider 保留但不在默认选择链；OpenAI 兼容 SDK + Redis缓存 |
| **图表** | lightweight-charts (K线), ECharts (曲线/雷达/热力图) |
| **数据源** | yfinance, Finnhub, Tiingo, FMP, ROIC.ai, Alpha Vantage |
| **部署** | Docker Compose (PG + Redis + Uvicorn), Nginx 反向代理 |

### 数据流架构

```
┌──────────────────────────────────────────────────────┐
│                    数据源层                            │
│  yfinance  │  Finnhub  │  Tiingo  │  FMP  │  ROIC.ai  │
└────────────────────┬─────────────────────────────────┘
                     │ ETL Pipeline (降级链)
                     ▼
┌──────────────────────────────────────────────────────┐
│                    存储层                              │
│  PostgreSQL: etf_info, instrument_daily_bar, etf_indicator,  │
│  research_note, sentiment_data, ai_chat_*              │
│  Redis: API缓存 + 分布式锁 + LLM响应缓存               │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│                    服务层                              │
│  指标计算 → 评分引擎 → 筛选 → 回测 → 信号生成          │
│  ResearchService (AI研报)                              │
│  SentimentService (情绪分析)                           │
│  ChatService (AI对话助手)                              │
└────────────────────┬─────────────────────────────────┘
                     │ REST API (/api/v1/*)
                     ▼
┌──────────────────────────────────────────────────────┐
│                    前端                                │
│  React 18 + Ant Design 5 + 颜色惯例切换(中/美)        │
│  AI页面: /research, /sentiment, /chat                 │
└──────────────────────────────────────────────────────┘
```

### 市场编码规范

| 市场 | 代码后缀 | 示例 | 交易时间 |
|------|---------|------|---------|
| A股上海 | `.SH` | `510050.SH` | 09:30-15:00 CST |
| A股深圳 | `.SZ` | `159915.SZ` | 09:30-15:00 CST |
| 美股 | `.US` | `SPY.US`, `AAPL.US` | 09:30-16:00 ET |
| 港股 | `.HK` | `2800.HK` | 09:30-16:00 HKT |
| 日股 | `.JP` | `1321.JP` | 09:00-15:00 JST |

### 调度任务一览

| 时间 (北京时间) | 任务 |
|----------------|------|
| 02:00 (周日) | 美股个股发现 (S&P 500) |
| 03:00 (周日) | 全市场ETF扫描 |
| 05:00 (每日) | 美股日线ETL |
| 05:30 (每日) | 美股指标计算 |
| 08:00 (每日) | A股指标计算 |
| 08:30 (每日) | 评分计算 |
| 09:00 (每日) | 交易信号生成 |
| 15:30 (每日) | A股日线ETL |
| 22:00 (周日) | 池周报生成 |

---

## 2. 环境配置

### 2.1 必需环境变量

```bash
# ---- 数据库 ----
DATABASE_URL=postgresql://etf:etf_research_password@localhost:5432/ad_research
REDIS_URL=redis://localhost:6379/0

# ---- 美股数据源 ----
# Finnhub (免费 60次/分): https://finnhub.io/register
FINNHUB_API_KEY=your_free_key

# 以下可选（降级链 & 阶段2）:
# Tiingo (免费 1000次/天): https://www.tiingo.com/account/token
TIINGO_API_KEY=
# FMP (免费 250次/天): https://site.financialmodelingprep.com/register
FMP_API_KEY=

# ---- AI/LLM (阶段3) ----
# 默认 MiniMax (OpenAI 兼容): https://platform.minimax.io/
MINIMAX_API_KEY=sk-...
# 国内端点改用 MINIMAX_CN_API_KEY；默认模型 minimax-m3，可用 MINIMAX_MODEL 覆盖
# LLM_PROVIDER=minimax|deepseek 显式选择；不设时优先 MiniMax，回退 DeepSeek
# LLM_PROVIDER=minimax
# DeepSeek (legacy): https://platform.deepseek.com/
DEEPSEEK_API_KEY=
# Anthropic Claude provider 仍保留在代码中 (ANTHROPIC_API_KEY)，但已不在默认选择链

# ---- 认证 ----
AUTH_SECRET_KEY=your-random-secret-key
AUTH_ADMIN_USERNAME=admin
AUTH_ADMIN_PASSWORD=your-secure-password
```

### 2.2 免费API额度汇总

| Provider | 免费额度 | 用途 | 注册链接 |
|----------|---------|------|---------|
| **yfinance** | ~2000次/时 | 美股EOD日线（主） | 无需注册 |
| **Finnhub** | 60次/分 | 实时报价、新闻情绪 | [finnhub.io/register](https://finnhub.io/register) |
| **Tiingo** | 1000次/天 | EOD降级链 | [tiingo.com/account/token](https://www.tiingo.com/account/token) |
| **FMP** | 250次/天 | S&P 500发现、基本面 | [site.financialmodelingprep.com](https://site.financialmodelingprep.com/register) |
| **ROIC.ai** | 5次/分 | 业绩会纪要 | [roic.ai/api](https://www.roic.ai/api) |
| **Alpha Vantage** | 25次/天 | 纪要+AI摘要（备） | [alphavantage.co](https://www.alphavantage.co/support/#api-key) |
| **MiniMax** | 按量付费 | AI研报/情绪/对话（默认） | [platform.minimax.io](https://platform.minimax.io/) |
| **DeepSeek** | 按量付费 | AI研报/情绪/对话（legacy 备选）、新闻清理 | [platform.deepseek.com](https://platform.deepseek.com/) |

**月度成本预估**: 数据 $0 + LLM 约 $5-15（视调用量，MiniMax/DeepSeek 单价均显著低于 Claude）

### 2.3 安装依赖

```bash
# Python 依赖由 Poetry 管理（pyproject.toml 已含 openai / anthropic SDK）
poetry install

# 前端依赖（react-markdown / remark-gfm 已在 web/package.json 中）
cd web && npm install
```

---

## 3. 阶段1：美股数据管道

### 3.1 新增文件清单

| 文件 | 说明 |
|------|------|
| `app/data/providers/finnhub_provider.py` | Finnhub数据Provider：实时报价、日线蜡烛图、公司新闻、~70只精选ETF |
| `app/data/providers/tiingo_provider.py` | Tiingo EOD Provider：30+年历史、调整价 |
| `app/data/providers/yfinance_provider.py` | **已扩展**：动态ticker映射、批量yf.download()、限速2s、单ticker降级 |
| `app/data/pipelines/us_etf.py` | `USDailyPipeline`：yfinance→Tiingo→Finnhub三级降级链 |
| `app/core/scheduler.py` | **已扩展**：新增 `run_us_etl()` 和 `run_us_indicator_calculation()` |
| `scripts/init_us_etfs.py` | 美股ETF种子数据脚本 |
| `alembic/versions/d3f4e5a6b7c8_*.py` | 新增 instrument_type/sector/industry/market_cap/country 列 |

### 3.2 美股ETF初始化

```bash
# 1. 预览要添加的ETF列表
python scripts/init_us_etfs.py

# 2. 实际写入数据库
python scripts/init_us_etfs.py --apply
```

**内置ETF列表** (70只精选): SPY, QQQ, IWM, DIA, VTI, VOO, IVV, XLK, XLF, XLV, XLE, SMH, SOXX, ARKK, BND, AGG, TLT, GLD, SLV, VNQ, 等。

### 3.3 手动运行US ETL

```bash
# 运行一次美股日线ETL
python -c "
from app.core.database import SessionLocal
from app.data.pipelines.us_etf import USDailyPipeline
db = SessionLocal()
pipeline = USDailyPipeline(db)
result = pipeline.run_with_retry()
print(f'success={result.success}, records={result.records}')
db.close()
"
```

### 3.4 前端改动

| 文件 | 改动 |
|------|------|
| `web/src/stores/settings.ts` | **新建**：Zustand+persist，管理 `colorConvention` (china/us) |
| `web/src/utils/color.ts` | **已扩展**：所有颜色函数接受 `convention` 参数 |
| `web/src/components/ReturnTag.tsx` | 读取settings store，传递convention |
| `web/src/components/KLineChart.tsx` | 蜡烛图颜色随convention动态切换 |
| `web/src/components/AppLayout.tsx` | Header增加 `Segmented` 颜色惯例切换按钮（红涨绿跌/绿涨红跌） |
| `web/src/pages/Screen/index.tsx` | 市场选择器从硬编码SH/SZ改为API动态获取 |

---

## 4. 阶段2：个股支持

### 4.1 新增文件清单

| 文件 | 说明 |
|------|------|
| `app/data/providers/fmp_provider.py` | FMP Provider：S&P 500列表、公司资料、三表(IS/BS/CF)、关键ratio、财报日历 |
| `app/data/pipelines/us_stock_discovery.py` | `USStockDiscoveryPipeline`：以 instrument_type="STOCK" upsert到 etf_info |
| `app/schemas/etf.py` | **已扩展**：新增 instrument_type/sector/industry/market_cap/country 字段 |
| `app/services/etf_service.py` | **已扩展**：支持 instrument_type 筛选 |

### 4.2 S&P 500 个股初始化

```bash
# 设置FMP Key后运行
export FMP_API_KEY=your_free_key

python -c "
from app.core.database import SessionLocal
from app.data.pipelines.us_stock_discovery import USStockDiscoveryPipeline
db = SessionLocal()
pipeline = USStockDiscoveryPipeline(db)
result = pipeline.run_with_retry()
print(f'success={result.success}, records={result.records}')
db.close()
"
```

**产出**: ~500只 S&P 500 成分股以 `instrument_type="STOCK"`, `market="US"` 写入 `etf_info`，与ETF共用日线/指标/评分基础设施。

### 4.3 前端改动

| 文件 | 改动 |
|------|------|
| `web/src/types/instrument.ts`（原 etf.ts，已更名） | 新增 instrument_type/sector/market_cap 字段 |
| `web/src/pages/InstrumentList/index.tsx`（原 ETFList，已更名，路由 /instruments） | 新增"类型"下拉筛选(ETF/个股) + Tag标签 + 规模列支持美股B/M/T显示 |

---

## 5. 阶段3：AI Vibe Trading 研究层

### 5.1 新增文件清单

```
app/services/llm/                    # LLM基础设施
├── base.py                          # LLMProvider 抽象基类
├── minimax_provider.py              # MiniMax 实现（默认，minimax-m3，OpenAI 兼容）
├── deepseek_provider.py             # DeepSeek 实现（legacy，deepseek-v4-flash）
├── anthropic_provider.py            # Claude 实现（保留，但不在默认选择链）
├── embedding_provider.py            # Embedding
├── llm_service.py                   # 缓存、限流、模板管理
└── __init__.py                      # get_llm_provider()：按 LLM_PROVIDER 环境变量选择

app/services/
├── research_service.py              # AI研报生成
├── sentiment_service.py             # 新闻情绪分析
└── chat_service.py                  # AI对话助手

app/api/v1/research.py               # AI REST端点（现约14个，含 /ai/status、流式聊天等）

app/models/research.py               # 4张新表 (ResearchNote, SentimentData,
                                     #   AIChatSession, AIChatMessage)

web/src/pages/ResearchNotes/         # AI研究笔记页面
web/src/pages/SentimentDashboard/    # 情绪仪表盘页面
web/src/pages/AIChat/               # AI对话助手页面
web/src/api/research.ts             # 研报+情绪API客户端
web/src/api/chat.ts                 # 聊天API客户端
```

### 5.2 LLM 技术选型

| 场景 | 模型 | 说明 | 用途 |
|------|------|------|------|
| **默认** | MiniMax minimax-m3 | OpenAI 兼容；`MINIMAX_API_KEY`（国内端点用 `MINIMAX_CN_API_KEY`），`MINIMAX_MODEL` 可覆盖 | 研报生成、情绪分类、日常对话 |
| **Legacy 备选** | DeepSeek deepseek-v4-flash | `DEEPSEEK_API_KEY`；新闻清理/情绪管线仍直接用 DeepSeekProvider | 同上 + 新闻管线 |
| **保留** | Claude Haiku 3.5 / Sonnet | `AnthropicProvider` 仍在代码中，但不在默认选择链 | 手动实例化使用 |
| **Embeddings** | all-MiniLM-L6-v2 (本地) | 免费 | 未来语义搜索 |

**月度成本预估**: $5-15 (Redis缓存后更低)

### 5.3 AI 功能指南

#### A. 研究笔记生成

```bash
# API方式生成研报
curl -X POST http://localhost:8000/api/v1/research/notes/generate \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"instrument_code": "SPY.US"}'

# 查询研报
curl http://localhost:8000/api/v1/research/notes/SPY.US \
  -H "Authorization: Bearer <token>"
```

**生成逻辑**:
1. 拉取近30天日线、最新指标(RSI/MA/MACD/波动率)、综合评分
2. 构建数据化Prompt → LLM生成2-3段中文研报
3. 解析JSON输出 (content/summary/sentiment/confidence)
4. 存储到 `research_note` 表

#### B. 情绪分析

```bash
# 触发新闻抓取+情绪分类
curl -X POST "http://localhost:8000/api/v1/research/sentiment/AAPL.US/ingest?days=3" \
  -H "Authorization: Bearer <token>"

# 查询情绪聚合
curl "http://localhost:8000/api/v1/research/sentiment/AAPL.US?days=7" \
  -H "Authorization: Bearer <token>"
```

**数据流**: Finnhub新闻 → LLM逐条分类(positive/negative/neutral + score) → 入库 → 聚合统计

#### C. AI对话助手

```bash
# 创建会话
curl -X POST http://localhost:8000/api/v1/research/chat/sessions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"

# 发送消息
curl -X POST http://localhost:8000/api/v1/research/chat/sessions/1/messages \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"content": "SPY最近表现怎么样？技术面怎么看？"}'
```

**数据感知机制**:
1. 用户消息中正则提取标的代码 (如 `SPY.US`)
2. 自动查询最新指标 + 评分数据
3. 作为System Prompt附件注入LLM上下文
4. AI回答引用的真实数据而非幻觉

### 5.4 前端AI页面

| 页面 | 路由 | 核心功能 |
|------|------|---------|
| **AI研究笔记** | `/research` | 输入代码→生成研报→Markdown全文查看→情绪badge/置信度 |
| **情绪仪表盘** | `/sentiment` | 情绪得分仪表、正/中/负面计数、可调回溯期Slider |
| **AI助手** | `/chat` | 左侧会话列表+右侧Markdown气泡、数据感知回答、Enter发送 |

### 5.5 成本控制

```bash
# .env — LLM 选择与模型覆盖
LLM_PROVIDER=minimax          # minimax | deepseek；不设则自动探测（MiniMax 优先）
MINIMAX_MODEL=minimax-m3      # 默认模型，可覆盖
```

```python
# app/services/llm/llm_service.py — 缓存TTL配置（仍然有效）
CACHE_TTL_VOLATILE = 3600   # 价格数据1小时
CACHE_TTL_STATIC = 86400    # 公司资料24小时
```

---

## 6. 前端功能指南

### 6.1 颜色惯例切换

平台支持 **中国惯例（红涨绿跌）** 和 **美国惯例（绿涨红跌）** 一键切换。

- 位置：顶部Header右侧 `Segmented` 控件
- 持久化：localStorage (`settings-storage`)
- 影响范围：K线蜡烛图颜色、ReturnTag、Dashboard、ScoreRanking等所有使用颜色函数的地方

### 6.2 市场选择器

- 筛选页 (`/screen`) 市场下拉框动态从API获取可用市场列表
- ETF列表页 (`/etfs`) 支持市场 + 分类 + 类型三维筛选
- 市场标签映射：`A股`→A股, `US`→美股, `HK`→港股, `JP`→日股

### 6.3 页面路由地图

```
/login              # 登录
/dashboard          # 首页看板
/instruments        # 标的列表（ETF/个股，支持类型筛选；旧 /etfs 重定向到此）
/instruments/:code  # 详情页（K线 + 指标 + AI分析Tab）
/stocks, /stocks/:code   # A股个股列表/详情
/screen             # 全市场筛选器
/pools              # 标的池管理
/pools/:id          # 池详情
/scores             # 评分排名
/research           # AI研究笔记
/instrument-sentiment  # 单标情绪看板（原 /sentiment 的 AI 情绪仪表盘）
/sentiment          # 市场情绪总览（后新增）
/chat               # AI助手
/news, /news/:id    # 资讯流与详情
/macro              # 宏观经济看板
/correlation        # 相关性分析
/comparison         # 收益对比
/sector-rotation    # 板块轮动
/scanner            # 全市场扫描
/notifications      # 推送配置
/strategies         # 策略管理
/backtests          # 回测管理
/signals            # 交易信号
/crypto             # 加密货币
/futures            # 商品期货
/paper-trading      # 模拟交易
/admin/users        # 用户管理（admin）
```

注：完整路由以 `web/src/routes.tsx` 为准，此处仅列主要页面。

---

## 7. API 参考

### 7.1 研究API (Phase 3 新增)

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/research/notes/generate` | 生成AI研报 |
| `GET` | `/api/v1/research/notes/{code}` | 查询研报列表 |
| `GET` | `/api/v1/research/sentiment/{code}` | 查询情绪聚合 (7天/可调) |
| `POST` | `/api/v1/research/sentiment/{code}/ingest` | 触发新闻情绪采集 |
| `POST` | `/api/v1/research/chat/sessions` | 创建AI对话会话 |
| `GET` | `/api/v1/research/chat/sessions` | 列出用户所有会话 |
| `DELETE` | `/api/v1/research/chat/sessions/{id}` | 删除会话 |
| `POST` | `/api/v1/research/chat/sessions/{id}/messages` | 发送消息 |
| `GET` | `/api/v1/research/chat/sessions/{id}/messages` | 获取历史消息 |
| `GET` | `/api/v1/research/ai/status` | LLM provider 状态（minimax/deepseek 可用性） |
| `GET` | `/api/v1/research/notes` | 查询全部研报列表 |
| `DELETE` | `/api/v1/research/notes/{note_id}` | 删除研报 |
| `GET` | `/api/v1/research/sentiment-data/aggregate` | 情绪聚合数据 |
| `POST` | `/api/v1/research/chat/sessions/{id}/messages/stream` | 流式发送消息 |

### 7.2 ETF API (扩展后)

`GET /api/v1/etfs` 新增查询参数：

| 参数 | 类型 | 说明 |
|------|------|------|
| `market` | string | 市场筛选 (A股/US/HK/JP) |
| `category` | string | 分类 |
| `instrument_type` | string | 类型 (ETF/STOCK) |
| `search` | string | 代码/名称搜索 |
| `page` | int | 页码 |
| `page_size` | int | 每页条数 |

### 7.3 响应模型

`ETFInfoResponse` 新增字段：
```json
{
  "code": "AAPL.US",
  "name": "Apple Inc.",
  "market": "US",
  "exchange": "NASDAQ",
  "instrument_type": "STOCK",
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "market_cap": 2800000000000.0,
  "country": "US",
  "currency": "USD",
  ...
}
```

---

## 8. 运维指南

### 8.1 数据库迁移

```bash
# 查看当前状态
python -m alembic current

# 执行所有待处理迁移
python -m alembic upgrade head

# 回滚一个版本
python -m alembic downgrade -1
```

### 8.2 常用运维脚本

```bash
# 美股ETF种子数据
python scripts/init_us_etfs.py           # 预览
python scripts/init_us_etfs.py --apply   # 写入

# 日线更新
python scripts/update_daily_data.py

# 数据补录
python scripts/catchup_data.py

# 数据完整性检查
python scripts/data_completeness_check.py
```

### 8.3 健康检查

```bash
# API健康检查
curl http://localhost:8000/health

# 验证数据源
python -c "
from app.data.providers.yfinance_provider import YFinanceProvider
p = YFinanceProvider()
print('yfinance health:', p.check_health())
"
```

### 8.4 Docker Compose 启动

```bash
docker-compose up -d
# PostgreSQL 16 + Redis 7 + Backend (Uvicorn on :8000)
```

---

## 9. 常见问题

### Q: yfinance报429/无数据？

A: yfinance是第三方库，Yahoo随时可能限流或改HTML。系统已内置三重降级链：
1. Tiingo (需 `TIINGO_API_KEY`, 1000次/天)
2. Finnhub (需 `FINNHUB_API_KEY`, 60次/分)
3. FMP (需 `FMP_API_KEY`, 250次/天)

### Q: LLM API费用会超预算吗？

A: 系统默认使用 MiniMax（minimax-m3），加上 Redis 缓存，成本远低于 Claude。如果未配置 `MINIMAX_API_KEY` / `DEEPSEEK_API_KEY`，AI 功能会自动跳过（不会 crash）。可通过 `GET /api/v1/research/ai/status` 查看各 provider 的可用性。

### Q: S&P 500个股发现只跑了一次？

A: 调度器每周日02:00自动运行。手动运行：
```bash
python -c "
from app.core.database import SessionLocal
from app.data.pipelines.us_stock_discovery import USStockDiscoveryPipeline
p = USStockDiscoveryPipeline(SessionLocal())
p.run_with_retry()
"
```

### Q: 颜色惯例切换后所有页面都生效了吗？

A: 以下组件已支持：
- ✅ KLineChart (蜡烛图颜色、成交量、MACD)
- ✅ ReturnTag (收益率标签)
- ✅ Dashboard, ScoreRanking, PoolDetail (通过ReturnTag)
- ❌ CorrelationHeatmap (待优化，热力图颜色通常与市场方向无关)

### Q: AI对话如何获取数据？

A: ChatService会自动正则匹配消息中的代码（如 `AAPL.US`），查询最新指标和评分，作为System Prompt附件。AI回答会引用真实数据而非生成幻觉。

---

## 版本历史

| 日期 | 变更 |
|------|------|
| 2025-06-25 | 初始版本：阶段1-3完整文档 |
| 2026-07-21 | 核实更新：LLM 默认切换为 MiniMax/DeepSeek（原 Anthropic 描述更新）；`ETFList`→`InstrumentList`、`types/etf.ts`→`instrument.ts` 更名同步；路由地图与 research API 列表按 `web/src/routes.tsx`、`app/api/v1/research.py` 现状修正；`anthropic_model`/`llm_monthly_budget` 配置项已从 `app/config.py` 移除的说明 |
