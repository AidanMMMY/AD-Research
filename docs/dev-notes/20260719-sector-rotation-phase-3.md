# Sector Rotation Phase 3 — 申万一级行业指数官方回报

**日期**：2026-07-19
**触发**：解决 `app/services/sector_rotation_service.py:808` 的 Phase 3 TODO
**作者**：总管 Agent（用户授权 A 股/AKShare 路径）

## 背景

`sector_rotation_service.analyze_sectors(classification="SW")` 之前
的板块回报是"等权平均所有 ETF + STOCK 的 `return_1w/1m/...`"。这只
是方便近似，不是官方行业指数回报。

Phase 3 目标：用 申万2021 一级行业指数 自身的 1w/1m/3m/6m/1y 回报
替代等权平均，UI 可对照显示两条曲线。

## 决策

| 维度 | 选择 | 原因 |
|---|---|---|
| 分类版本 | 申万2021 (31 个 L1) | 与 `etf_info.sw_l1` 现存映射一致；业务主流 |
| 数据源 | AKShare `index_hist_sw` | 免费；Tushare `index_classify(L1, src="SW")` 实测返 0 行（套餐权限不够） |
| 调度 | 每周一 09:30 (盘前) Asia/Shanghai | 数据变化慢；避免与周日其他重活冲突 |
| 队列 | `industry`（挂在 cninfo worker `-Q celery,cninfo,industry`） | 任务轻量（5min），不抢 indicator worker 资源 |
| Fallback | SW 表缺数据时回退到 constituents_equal_weight | 首次跑 / 行业代码错位时 UI 不空 |
| 字段命名 | `return_*` 优先用官方指数；`constituent_return_*` 保留等权 | Backward-compatible + UI 对照 |
| 标记字段 | `return_source: "official_index" \| "constituents_equal_weight"` | 监控 + UI 显示 |

## 实施

### 1. 数据层
- 新增 `app/models/sw_industry_index.py` — `SWIndustryIndexReturn`
  (pk=`sw_l1_code+trade_date`)，列：close, return_1w/1m/3m/6m/1y,
  source, fetched_at
- 新增 alembic 迁移 `p1r4s0t7u8v9_add_sw_industry_index_return.py` —
  创表 + 2 个 index
- 新增 provider 方法
  `app/data/providers/akshare_provider.py::fetch_sw_industry_index_daily`
  + `fetch_sw_industry_index_info`

### 2. Pipeline
- `app/data/pipelines/sw_industry_index.py` — 拉 31 个指数全历史
  → 算滚动回报 → UPSERT
- `_rolling_returns` 用与 ETFIndicator 一致的 5/21/63/126/252 窗口
- 数据来源：从 `etf_info.sw_l1_code` 取 distinct（无需硬编码 31 个）
- 输出 psycopg2-safe python float（避免 `np.float64` schema 报错）

### 3. Service
- `app/services/sector_rotation_service.py::analyze_sectors` 在
  `classification="SW"` 时：
  - 预查 `(sw_l1_code, trade_date <= X)` 的官方指数回报
    （容忍 1 天错位 — 指数比指标通常落后 0~1 个交易日）
  - 覆盖 `return_*` 与 `relative_strength_*`
  - 新增字段 `sw_l1_code`, `official_close`, `return_source`,
    `constituent_return_*`

### 4. Celery + Scheduler
- `app/tasks/sw_industry.py::refresh_sw_industry_returns` —
  `queue="industry"`, soft=10min / hard=15min
- `app/core/celery_app.py` — include `app.tasks.sw_industry`,
  route `industry` 队列
- `app/core/scheduler.py` — 新 cron 周一 09:30 Asia/Shanghai
- `deploy/aliyun-ecs/docker-compose.yml` — cninfo worker
  `-Q celery,cninfo,industry`

## 验证（2026-07-19 17:36 实测）

- 迁移：`c38dfe612183 → p1r4s0t7u8v9` ✓
- 拉数：31 个 code × 400 天 = **12,400 行** UPSERT 成功，0 错误 ✓
- 范围：trade_date 2024-11-21 → 2026-07-16 ✓
- Service：SW 模式 32 个 sector，**19 个 official_index / 13 个 fallback**：
  - 农林牧渔：官方 +3.08% vs 等权 +10.84%（官方跑输成分股）
  - 综合：官方 -0.20% vs 等权 -4.65%（官方跑赢）

## 已知 issue / 后续

1. **13 个 sector 走 fallback**：sector=医药生物 / 机械设备 / 非银金融
   等的 `sw_l1_code` 为 NULL — `backfill_a_share_sw` 没覆盖到这些
   标的（与 Phase 3 无关，是上一步 backfill 覆盖不全）。
   后续：跑 `python -m app.scripts.backfill_a_share_sw --from-tushare`
   （或重写 CSRC→SW 静态映射）后这些 sector 也会走官方指数。

2. **第一次部署必须 alembic upgrade head** + Celery worker 镜像重建
   （镜像不重建则 `include` 不带新 task，dispatch 会报
   "unregistered task"，跟 deploy-tripwire runbook 描述的
   "image not rebuilt" 同因）。

## 风险

- AKShare 单次取全历史（~6k 行/指数），但本地 tail(400)；
  31 个指数顺序拉，无并发——可接受（3min 总时长）。
- `result.metadata["codes_count"]` 当前未写入 etl_log；
  监控可走 etf_info.sw_l1_code 覆盖率。

## 运维命令

```bash
# 手动触发
docker exec alloyresearch-celery-worker-cninfo celery -A app.core.celery_app call \
    app.tasks.sw_industry.refresh_sw_industry_returns

# 看最新数据
docker exec alloyresearch-postgres psql -U etf -d ad_research -c \
    "SELECT count(*), min(trade_date), max(trade_date), max(fetched_at) FROM sw_industry_index_return"

# 看 SW 模式 sector 分布
docker exec alloyresearch-backend python3 -c "
import os; os.environ.setdefault('PYTHONPATH', '/app')
from app.core.database import SessionLocal
from app.services.sector_rotation_service import SectorRotationService
from collections import Counter
db=SessionLocal()
res=SectorRotationService(db).analyze_sectors(classification='SW')
print(Counter(s['return_source'] for s in res['sectors']))
"
```

## 关联

- TODO 位置：`app/services/sector_rotation_service.py:808`（已注释
  关闭）
- etf_info.sw_l1 写入：`app/scripts/backfill_a_share_sw.py`
- AKShare provider：`app/data/providers/akshare_provider.py`
- 部署注意事项：`docs/dev-notes/20260719-deploy-tripwires.md` 第 4 类
  tripwire（image rebuild required after alembic 迁移）