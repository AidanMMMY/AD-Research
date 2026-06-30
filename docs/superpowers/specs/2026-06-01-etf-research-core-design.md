# 子项目2：ETF 投研核心 — 详细设计文档

**版本：** v1.0  
**日期：** 2026-06-01  
**状态：** 设计完成，待实现  
**前置依赖：** 子项目1（数据基础设施）已完成

---

## 一、概述

### 1.1 目标

在子项目1的数据基础设施之上，构建ETF投研核心能力，实现从"数据"到"洞察"的自动化转换。核心目标：

1. **综合评分系统** — 为每只ETF计算多维度综合得分，支持横向对比
2. **全市场筛选排名** — 基于多条件灵活筛选和排序
3. **标的池增强** — 权重配置、池内分析、快照记录
4. **报告生成引擎** — 定期自动生成研究报告（先实现4个核心模块）

### 1.2 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 架构模式 | **混合模式** | 评分预计算（数据稳定）+ 筛选实时（条件多变）+ 报告异步（耗时长） |
| 评分计算 | 日终预计算，百分位排名法 | 1486只ETF全量评分，预计算避免每次查询重复计算 |
| 权重配置 | 可配置模板（JSONB） | 支持保守/均衡/进取三套预置模板，用户可自定义 |
| 筛选排名 | 实时SQL查询 | 条件组合太多，无法预存所有组合 |
| 报告生成 | 异步后台任务（APScheduler） | 生成耗时不阻塞API请求，支持定时自动触发 |
| 报告内容 | v1简化版4模块 | 先实现核心功能，v2扩展相关性和配置建议 |
| 报告格式 | HTML + Markdown | HTML用于直接查看，Markdown用于存档 |

### 1.3 范围边界

**P0（本期实现）：**
- 评分系统（含3套预置权重模板）
- 筛选排名（多条件组合）
- 池增强（权重配置 + 池内分析 + 快照）
- 报告引擎（4核心模块：概览/收益/风险/评分）

**P1（后续扩展）：**
- 板块轮动分析
- 全市场自动扫描（发现新上市/退市ETF）
- 报告推送（邮件/企业微信）
- 相关性矩阵嵌入报告
- 配置建议模块

---

## 二、整体架构

### 2.1 模块关系图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          子项目1：数据基础设施 ✅                         │
│  etf_info │ instrument_daily_bar │ etf_indicator │ etf_pools │ pool_member     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
    ┌───────────────┐     ┌───────────────────┐   ┌──────────────────┐
    │ 综合评分系统   │     │ 全市场筛选排名     │   │ 标的池增强        │
    │ (预计算)       │     │ (实时查询)         │   │                  │
    ├───────────────┤     ├───────────────────┤   ├──────────────────┤
    │ ScoreTemplate │     │ ScoreFilterService│   │ PoolWeightConfig │
    │ ScoreCalculator│     │ RankingService    │   │ PoolAnalytics    │
    │ → etf_score   │     │ → 实时SQL查询      │   │ PoolSnapshot     │
    └───────┬───────┘     └───────────────────┘   └────────┬─────────┘
            │                                              │
            └──────────────────────┬───────────────────────┘
                                   │
                                   ▼
                      ┌──────────────────────┐
                      │   报告生成引擎        │
                      │   (异步后台任务)       │
                      ├──────────────────────┤
                      │ ReportTemplate       │
                      │ ReportGenerator      │
                      │ ReportService        │
                      │ → reports/ 目录       │
                      │ → report_metadata 表  │
                      └──────────┬───────────┘
                                 │
                                 ▼
                      ┌──────────────────────┐
                      │   输出                │
                      │  HTML / Markdown / API│
                      └──────────────────────┘
```

### 2.2 计算策略矩阵

| 功能 | 计算时机 | 存储方式 | 查询性能 | 灵活性 |
|------|----------|----------|----------|--------|
| 综合评分 | 日终 08:00 | `etf_score` 表 | 毫秒级 | 权重模板可切换 |
| 筛选排名 | API请求时 | 实时SQL | 亚秒级 | 条件任意组合 |
| 池内分析 | API请求时 | 实时SQL聚合 | 亚秒级 | 实时反映最新数据 |
| 报告生成 | 定时/手动触发 | 文件系统 | N/A | 异步不阻塞 |

---

## 三、模块详细设计

### 3.1 综合评分系统

#### 3.1.1 职责

为每只ETF计算多维度综合得分，支持多组权重模板对比。

#### 3.1.2 数据流

```
etf_indicator (最新数据)
    │
    ▼
ScoreCalculator 读取所有活跃ETF的指标
    │
    ├── 对每个权重模板：
    │   ├── 按维度分组计算百分位排名（0-100）
    │   ├── 根据 direction 调整方向
    │   ├── 维度分 = Σ(指标百分位 × 子权重)
    │   └── 综合分 = Σ(维度分 × 维度权重)
    │
    ▼
etf_score 表（UPSERT，每个模板每日一行）
```

#### 3.1.3 百分位评分算法

```python
# 伪代码
def calculate_score(indicators: list, template: ScoreTemplate) -> dict:
    scores = {}
    for dimension, config in template.dimensions.items():
        # 1. 提取该维度所有指标值
        values = [getattr(ind, config.metric) for ind in indicators]
        values = [v for v in values if v is not None]
        if not values:
            continue

        # 2. 计算百分位排名 (0-100)
        percentile = rankdata(values, method='average') / len(values) * 100

        # 3. 根据方向调整
        if config.direction == 'desc':  # 越低越好（如波动率）
            percentile = 100 - percentile

        # 4. 计算维度得分
        dimension_score = percentile * config.weight
        scores[dimension] = round(dimension_score, 2)

    # 5. 综合得分
    composite = sum(scores.values())
    return {**scores, 'composite': round(composite, 2)}
```

#### 3.1.4 预置权重模板

| 维度 | 指标 | 保守型 | 均衡型 | 进取型 | 方向 |
|------|------|--------|--------|--------|------|
| 收益能力 | return_1m, return_3m, return_1y | 20% | 30% | 40% | asc |
| 风险控制 | volatility_20d, max_drawdown_1y | 35% | 25% | 15% | desc |
| 风险调整收益 | sharpe_1y | 30% | 25% | 25% | asc |
| 流动性 | avg_amount_20d | 10% | 10% | 10% | asc |
| 趋势强度 | rsi14 | 5% | 10% | 10% | asc |

#### 3.1.5 排名计算

- **全市场排名**：所有活跃ETF按综合分降序排名
- **分类内排名**：按 `category` 分组后组内排名
- 排名每日重新计算，历史排名保留在 `etf_score` 表中

---

### 3.2 全市场筛选排名

#### 3.2.1 职责

基于多条件组合实时筛选ETF，支持动态排序。

#### 3.2.2 筛选条件

```python
class ScreenFilter(BaseModel):
    # 基础筛选
    market: Optional[str] = None           # "SH" | "SZ"
    category: Optional[str] = None         # 分类名称
    sub_category: Optional[str] = None     # 子分类名称

    # 指标范围筛选
    rsi_min: Optional[float] = None
    rsi_max: Optional[float] = None
    sharpe_min: Optional[float] = None
    sharpe_max: Optional[float] = None
    volatility_max: Optional[float] = None
    volatility_min: Optional[float] = None
    return_1m_min: Optional[float] = None
    return_1m_max: Optional[float] = None
    return_3m_min: Optional[float] = None
    return_3m_max: Optional[float] = None
    return_1y_min: Optional[float] = None
    return_1y_max: Optional[float] = None
    amount_min: Optional[float] = None     # 日均成交额门槛（万元）

    # 评分筛选
    score_min: Optional[float] = None
    score_max: Optional[float] = None
    template_id: Optional[int] = None      # 评分模板ID（使用指定模板的评分）

    # 排序
    sort_by: str = "composite_score"       # 排序字段
    order: Literal["asc", "desc"] = "desc"
    limit: int = 50                        # 返回数量
    offset: int = 0                        # 分页偏移
```

#### 3.2.3 实现策略

使用子查询获取每只ETF的最新指标，然后应用 WHERE 条件和 ORDER BY：

```sql
-- 核心查询模式
WITH latest_indicators AS (
    SELECT DISTINCT ON (etf_code) *
    FROM etf_indicator
    ORDER BY etf_code, trade_date DESC
)
SELECT i.*, s.composite_score, s.rank_overall, info.name, info.category
FROM latest_indicators i
LEFT JOIN etf_info info ON i.etf_code = info.code
LEFT JOIN etf_score s ON i.etf_code = s.etf_code
    AND s.trade_date = (SELECT MAX(trade_date) FROM etf_score)
    AND s.template_id = :template_id
WHERE info.status = 'active'
  AND (:market IS NULL OR info.market = :market)
  AND (:category IS NULL OR info.category = :category)
  AND (:sharpe_min IS NULL OR i.sharpe_1y >= :sharpe_min)
  AND (:volatility_max IS NULL OR i.volatility_20d <= :volatility_max)
  ...
ORDER BY CASE WHEN :order = 'desc' THEN s.composite_score END DESC NULLS LAST
LIMIT :limit OFFSET :offset
```

#### 3.2.4 预置筛选条件

提供常用筛选条件预设：

| 预设名称 | 条件 |
|----------|------|
| 高夏普低波动 | sharpe_min=1.0, volatility_max=30% |
| 趋势强势 | rsi_min=60, return_1m_min=5% |
| 价值洼地 | rsi_max=40, return_1y_max=0% |
| 流动性充足 | amount_min=1000万 |
| 跨境机会 | market 包含 QDII |

---

### 3.3 标的池增强

#### 3.3.1 职责

在子项目1基础池功能之上，增加投研所需的权重管理和分析能力。

#### 3.3.2 权重配置

**目标权重**（用户手动设置）：
- 用户在池管理界面为每只ETF设置目标权重（0-100%）
- 池内所有目标权重之和为100%
- 修改后自动记录 `updated_at`

**建议权重**（系统自动计算）：

| 算法 | 计算方式 | 适用场景 |
|------|----------|----------|
| 等权 equal | 100% / N | 分散配置，不偏好任何标的 |
| 评分加权 score | weight_i = score_i / Σ(score) | 偏好高分标的 |
| 风险平价 risk_parity | weight_i ∝ 1 / volatility_i | 控制组合波动 |

**再平衡提示**：
- 当实际持仓权重偏离目标权重超过阈值（默认10%）时标记
- 实际权重基于ETF市值或用户输入的持仓金额计算

#### 3.3.3 池内分析

**分类分布**：
- 按 `category` 分组统计ETF数量和权重占比
- 输出饼图数据格式

**相关性矩阵**：
- 使用 `AnalysisService.correlation_matrix()` 计算池内ETF的相关性
- 返回相关系数矩阵 + 标签

**池整体表现**（加权平均）：
- return_1m/3m/1y：按目标权重加权平均
- volatility_20d：考虑协方差矩阵的组合波动率
- sharpe_1y：组合夏普
- max_drawdown：组合回撤

**多池对比**：
- 支持2-5个池的并行对比
- 对比维度：收益曲线、回撤、夏普、分类分布

#### 3.3.4 快照机制

- **触发**：日终 20:00 自动触发 + API手动触发
- **内容**：池成员列表 + 当前权重 + 最新指标数据（JSONB存储）
- **用途**：历史持仓回溯、池表现追踪
- **保留策略**：保留最近90天快照，更早的按月归档

---

### 3.4 报告生成引擎

#### 3.4.1 职责

定期自动生成研究报告，替代手工报告。

#### 3.4.2 v1 报告内容（4核心模块）

参照用户手工报告风格，先做4个模块：

**模块1：概览**
- 池内ETF总数、总市值、合计成交额
- 当日涨跌统计
- 分类分布（饼图数据）
- 实时行情快照表（含分类标签颜色）

**模块2：收益分析**
- 各周期收益表（1周/1月/3月/6月/1年/持有期）
- 收益TOP5 / 末位5
- 分类平均收益

**模块3：风险分析**
- 波动率、最大回撤表
- 风险等级标注（高/中高/中/低）
- 高波动品种提示

**模块4：综合评分**
- 评分排名表（含可视化进度条）
- 分项得分明细
- 分类内最佳ETF

#### 3.4.3 报告类型与频率

| 类型 | 频率 | 内容 | 触发方式 |
|------|------|------|----------|
| 池周报 | 每周日 22:00 | 4核心模块 | APScheduler |
| 池日报 | 每日 20:00 | 概览 + 行情快照 | APScheduler |
| 全市场周报 | 每周日 22:30 | 全市场TOP20 + 异常信号 | v2 |
| 手动报告 | 按需 | 用户指定模块 | API调用 |

#### 3.4.4 异步生成流程

```
触发（定时/手动）
    │
    ▼
创建 report_metadata（status="pending"）
    │
    ▼
投递后台任务（APScheduler JobStore）
    │
    ▼
立即返回 {report_id, status: "pending"}
    │
    ║ 后台执行
    ▼
更新 status="running"
    │
    ▼
查询池成员 + 最新指标 + 评分数据
    │
    ▼
按模块组装 HTML（Jinja2模板渲染）
    │
    ▼
写入 reports/pool_weekly_2026-06-01_pool_1.html
    │
    ▼
更新 status="done", file_path, finished_at
```

#### 3.4.5 HTML 模板结构

```
app/templates/reports/
├── base.html              # 基础布局（CSS + 页头页脚）
│   └── 复用手工报告风格（蓝白主色调、卡片布局、进度条）
├── components/
│   ├── overview.html      # 概览模块
│   ├── returns.html       # 收益分析
│   ├── risk.html          # 风险分析
│   ├── scoring.html       # 综合评分
│   └── correlation.html   # 相关性（v2预留）
├── pool_weekly.html       # 池周报主模板（组合上述模块）
└── market_weekly.html     # 全市场周报（v2预留）
```

#### 3.4.6 状态查询

客户端轮询生成状态：

```
GET /api/v1/reports/{id}/status
→ { "status": "running", "progress": 60, "estimated_seconds": 10 }

GET /api/v1/reports/{id}/status
→ { "status": "done", "file_path": "...", "file_size": 45230 }
```

---

## 四、数据模型

### 4.1 新增表（5张）

#### score_template — 评分权重模板

```sql
CREATE TABLE score_template (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    weights JSONB NOT NULL DEFAULT '{}',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 预置数据
INSERT INTO score_template (name, description, weights, is_default) VALUES
('保守型', '注重风险控制，适合低风险偏好', '{"return":0.20,"risk":0.35,"sharpe":0.30,"liquidity":0.10,"trend":0.05}', FALSE),
('均衡型', '收益与风险平衡，适合中等风险偏好', '{"return":0.30,"risk":0.25,"sharpe":0.25,"liquidity":0.10,"trend":0.10}', TRUE),
('进取型', '追求高收益，适合高风险偏好', '{"return":0.40,"risk":0.15,"sharpe":0.25,"liquidity":0.10,"trend":0.10}', FALSE);
```

#### etf_score — ETF每日评分快照

```sql
CREATE TABLE etf_score (
    id SERIAL PRIMARY KEY,
    etf_code VARCHAR(20) NOT NULL REFERENCES etf_info(code) ON DELETE CASCADE,
    trade_date DATE NOT NULL,
    template_id INT NOT NULL REFERENCES score_template(id),
    composite_score DECIMAL(8,4),
    score_return DECIMAL(8,4),
    score_risk DECIMAL(8,4),
    score_sharpe DECIMAL(8,4),
    score_liquidity DECIMAL(8,4),
    score_trend DECIMAL(8,4),
    rank_overall INT,
    rank_category INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(etf_code, trade_date, template_id)
);

CREATE INDEX idx_etf_score_date ON etf_score(trade_date);
CREATE INDEX idx_etf_score_template ON etf_score(template_id, trade_date);
CREATE INDEX idx_etf_score_rank ON etf_score(template_id, trade_date, rank_overall);
```

#### pool_weight — 池成员权重配置

```sql
CREATE TABLE pool_weight (
    id SERIAL PRIMARY KEY,
    pool_id INT NOT NULL REFERENCES etf_pools(id) ON DELETE CASCADE,
    etf_code VARCHAR(20) NOT NULL REFERENCES etf_info(code) ON DELETE CASCADE,
    target_weight DECIMAL(5,2) NOT NULL DEFAULT 0,  -- 目标权重 %
    suggested_weight DECIMAL(5,2),                  -- 建议权重 %
    weight_source VARCHAR(20) NOT NULL DEFAULT 'manual', -- manual/equal/score/risk_parity
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(pool_id, etf_code)
);
```

#### pool_snapshot — 池定期持仓快照

```sql
CREATE TABLE pool_snapshot (
    id SERIAL PRIMARY KEY,
    pool_id INT NOT NULL REFERENCES etf_pools(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(pool_id, snapshot_date)
);

CREATE INDEX idx_pool_snapshot_pool ON pool_snapshot(pool_id, snapshot_date);
```

#### report_metadata — 报告元数据

```sql
CREATE TABLE report_metadata (
    id SERIAL PRIMARY KEY,
    report_type VARCHAR(20) NOT NULL,  -- daily / weekly / pool / market
    report_date DATE NOT NULL,
    pool_id INT REFERENCES etf_pools(id) ON DELETE SET NULL,
    template_id INT REFERENCES score_template(id),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/running/done/failed
    format VARCHAR(10) NOT NULL DEFAULT 'html',     -- html / markdown / json
    file_path VARCHAR(500),
    file_size INT,
    error_msg TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_report_date ON report_metadata(report_date);
CREATE INDEX idx_report_pool ON report_metadata(pool_id, report_date);
CREATE INDEX idx_report_status ON report_metadata(status);
```

### 4.2 表关系图

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ etf_info     │◄────│ etf_score    │────►│ score_template│
└──────────────┘     └──────────────┘     └──────────────┘
       ▲                                              ▲
       │                                              │
       │     ┌──────────────┐     ┌──────────────┐    │
       └─────│ pool_weight  │     │ report_metadata│───┘
             └──────────────┘     └──────────────┘
                    │                      │
                    │     ┌──────────────┐ │
                    └─────│ etf_pools    │◄┘
                          └──────────────┘
                                 │
                          ┌──────────────┐
                          │ pool_snapshot│
                          └──────────────┘
```

---

## 五、API 设计

### 5.1 评分系统 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/scores` | GET | 评分列表（支持 template_id, limit, market, category） |
| `/api/v1/scores/{code}` | GET | 单只ETF评分详情（含历史趋势） |
| `/api/v1/scores/templates` | GET | 权重模板列表 |
| `/api/v1/scores/templates` | POST | 创建自定义模板 |
| `/api/v1/scores/templates/{id}` | PUT | 修改模板 |
| `/api/v1/scores/templates/{id}` | DELETE | 删除模板（非默认） |
| `/api/v1/scores/batch` | POST | 批量查询评分 |

### 5.2 筛选排名 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/screen` | GET | 多条件筛选（参数见3.2.2） |
| `/api/v1/screen/presets` | GET | 预置筛选条件 |
| `/api/v1/screen/categories` | GET | 分类列表（含ETF计数） |
| `/api/v1/ranking` | GET | 动态排名（sort_by, order, limit） |

### 5.3 池增强 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/pools/{id}/weights` | GET | 获取池成员权重配置 |
| `/api/v1/pools/{id}/weights` | PUT | 更新目标权重 |
| `/api/v1/pools/{id}/weights/suggest` | POST | 生成建议权重（指定算法） |
| `/api/v1/pools/{id}/analytics` | GET | 池内综合分析 |
| `/api/v1/pools/{id}/correlation` | GET | 池内相关性矩阵 |
| `/api/v1/pools/{id}/snapshots` | GET | 快照列表 |
| `/api/v1/pools/{id}/snapshots` | POST | 手动创建快照 |
| `/api/v1/pools/{id}/snapshots/{date}` | GET | 查看指定日期快照 |
| `/api/v1/pools/compare` | GET | 多池对比（pool_ids 参数） |

### 5.4 报告 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/reports` | GET | 报告列表（分页，支持 type/filter） |
| `/api/v1/reports/{id}` | GET | 报告详情 |
| `/api/v1/reports/generate` | POST | 手动触发报告生成 |
| `/api/v1/reports/{id}/status` | GET | 查询生成状态 |
| `/api/v1/reports/{id}/download` | GET | 下载报告文件 |
| `/api/v1/reports/{id}` | DELETE | 删除报告 |

---

## 六、定时任务

### 6.1 新增定时任务

```python
# app/core/scheduler.py

SCHEDULED_JOBS = {
    # 子项目1已有任务
    "a_share_daily_etl": {...},
    "indicator_calculation": {...},

    # 子项目2新增
    "score_calculation": {
        "func": "app.data.indicators.scoring:calculate_daily_scores",
        "trigger": "cron",
        "hour": 8,
        "minute": 30,  # 指标计算完成后
        "kwargs": {},
    },
    "pool_snapshot_daily": {
        "func": "app.services.pool_enhancement_service:create_all_pool_snapshots",
        "trigger": "cron",
        "hour": 20,
        "minute": 0,
    },
    "weekly_pool_report": {
        "func": "app.services.report_service:generate_scheduled_reports",
        "trigger": "cron",
        "day_of_week": "sun",
        "hour": 22,
        "minute": 0,
        "kwargs": {"report_type": "pool_weekly"},
    },
}
```

### 6.2 任务执行顺序

```
15:30  a_share_daily_etl    # A股数据采集
  │
  ▼
08:00  indicator_calculation  # 指标计算
  │
  ▼
08:30  score_calculation      # 评分计算（依赖指标数据）
  │
  ▼
20:00  pool_snapshot_daily    # 池快照
  │
  ▼
22:00  weekly_pool_report     # 周报生成（周日）
```

---

## 七、目录结构

```
app/
├── main.py                          # FastAPI 入口
├── config.py                        # 配置管理
├── core/
│   ├── database.py                  # SQLAlchemy
│   ├── redis_client.py              # Redis
│   ├── scheduler.py                 # APScheduler（新增评分/快照/报告任务）
│   └── exceptions.py                # 异常
├── models/
│   ├── etf.py                       # ETF/DailyBar/Indicator/FXRate
│   ├── pool.py                      # Pools/Member/Weight/Snapshot（扩展）
│   ├── etl.py                       # ETL/Strategy/Backtest/Signal
│   └── scoring.py                   # ScoreTemplate/ETFScore/ReportMeta（新增）
├── schemas/
│   ├── etf.py
│   ├── pool.py                      # 扩展权重/快照schema
│   ├── scoring.py                   # 评分/模板schema（新增）
│   ├── screening.py                 # 筛选条件schema（新增）
│   └── report.py                    # 报告schema（新增）
├── services/
│   ├── etf_service.py
│   ├── pool_service.py
│   ├── market_data_service.py
│   ├── indicator_service.py
│   ├── analysis_service.py
│   ├── scoring_service.py           # 评分计算/模板管理/查询（新增）
│   ├── screening_service.py         # 筛选排名（新增）
│   ├── pool_enhancement_service.py  # 池增强（新增）
│   └── report_service.py            # 报告生成（新增）
├── api/
│   ├── deps.py                      # 扩展依赖注入
│   └── v1/
│       ├── etfs.py
│       ├── pools.py                 # 扩展权重/分析/快照路由
│       ├── market_data.py
│       ├── indicators.py
│       ├── analysis.py
│       ├── scoring.py               # 评分API（新增）
│       ├── screening.py             # 筛选API（新增）
│       ├── reports.py               # 报告API（新增）
│       └── etl.py
├── data/
│   ├── providers/
│   ├── pipelines/
│   ├── transformers/
│   └── indicators/
│       ├── technical.py
│       ├── risk.py
│       ├── calculator.py
│       └── scoring.py               # 评分计算引擎（新增）
├── templates/
│   └── reports/                     # Jinja2报告模板（新增）
│       ├── base.html
│       ├── components/
│       └── pool_weekly.html
├── tests/
│   └── test_data/
│       ├── test_validator.py
│       └── test_scoring.py          # 评分单元测试（新增）
└── scripts/
    └── init_etfs.py
```

---

## 八、依赖关系

### 8.1 模块依赖

```
评分系统 ──► 依赖：etf_indicator（最新指标数据）
           ──► 被依赖：筛选排名（score_min 筛选）、报告引擎

筛选排名 ──► 依赖：etf_indicator、etf_info、etf_score（可选）
           ──► 被依赖：无

池增强   ──► 依赖：pool_member、etf_indicator、etf_score
           ──► 被依赖：报告引擎

报告引擎 ──► 依赖：池成员、指标、评分、快照
           ──► 被依赖：无
```

### 8.2 实现顺序建议

1. **评分系统**（最基础，被其他模块依赖）
   - 数据模型（score_template, etf_score）
   - 评分计算引擎
   - API路由
2. **筛选排名**（依赖评分系统的数据，但自身独立）
   - 筛选服务
   - 排名API
3. **池增强**（依赖评分系统）
   - 权重配置
   - 池内分析
   - 快照
4. **报告引擎**（依赖前三个模块）
   - 模板系统
   - 异步生成
   - 定时任务

---

## 九、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 评分计算性能（1486只×3模板） | 日终任务耗时 | 使用批量INSERT/UPSERT，控制在30秒内 |
| 报告生成内存占用（HTML渲染） | 大池报告OOM | 流式渲染，分页处理 |
| 筛选查询性能（全表扫描） | API响应慢 | 确保 etf_indicator 索引覆盖查询条件 |
| 权重配置数据一致性 | 权重和不为100% | API层校验，前端辅助提示 |
| 报告并发生成 | 资源竞争 | APScheduler JobStore 单实例执行 |

---

## 十、附录

### 10.1 与手工报告的功能对照

| 手工报告模块 | v1实现 | v2扩展 |
|-------------|--------|--------|
| 概览 | ✅ | |
| 实时行情 | ✅ | |
| 收益分析 | ✅ | |
| 风险分析 | ✅ | |
| 夏普比率 | ✅（并入评分） | |
| 综合评分 | ✅ | |
| 相关性矩阵 | ❌ | ✅ |
| 低相关组合推荐 | ❌ | ✅ |
| 配置建议 | ❌ | ✅ |
| 风险提示 | ✅（简化版） | ✅（详细版） |

### 10.2 性能目标

| 操作 | 目标响应时间 |
|------|-------------|
| 评分查询（Top 20） | < 50ms |
| 筛选排名（单条件） | < 200ms |
| 筛选排名（多条件+评分） | < 500ms |
| 池内分析 | < 300ms |
| 相关性矩阵（10只） | < 500ms |
| 报告生成（16只池） | < 10秒（后台异步） |
