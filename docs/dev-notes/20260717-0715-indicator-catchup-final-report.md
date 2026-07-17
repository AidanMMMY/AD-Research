# 2026-07-17 11:00 A 股 2026-07-15 指标补齐复盘报告

> 报告生成时间：2026-07-17 11:37 CST（最终检查时间，因 SSH 等待连接 reset 略有延迟）  
> 报告人：Claude Code（总管子 agent 调度）  
> 关联文档：[[20260717-deploy-health-celery-followup]]、[[20260712-celery-worker-runbook]]、[[20260717-indicator-catchup-temp-worker]]

---

## 1. 最终结果

| 指标 | 数值 | 状态 |
|---|---|---|
| A 股 2026-07-15 有 bars 的代码数 | **7,066** | ✅ 基准 |
| `etf_indicator` 2026-07-15 行数 | **7,066** | ✅ **100% 补齐** |
| 与目标差值 | 0 | ✅ |
| `indicator` 队列长度 | 0 | ✅ 已清空 |
| `cninfo` 队列长度 | 14 | ⏳ 正常消费中 |
| `celery` 队列长度 | 0 | ✅ |
| celery-worker 监听队列 | `celery,indicator,cninfo` | ✅ 已恢复三队列 |
| celery-worker 并发数 | 3 | ✅ |
| 当前活跃任务 | 3 个 `download_cninfo_pdfs` | ⏳ 预计持续数小时 |

**结论**：A 股 2026-07-15 指标补齐目标达成，`indicator` 队列清空，worker 已恢复为常驻三队列模式，`cninfo` PDF 回填任务在三队列 worker 下正常运行。

---

## 2. 关键修复与优化

### 2.1 性能调优

- `app/data/indicators/sql_calculator.py`：将递归 CTE 的 `max_bars` 从硬编码 **500 下调至 300**（通过环境变量 `INDICATOR_SQL_MAX_BARS` 默认），减少单 chunk 行数、提升 throughput。
- `deploy/aliyun-ecs/docker-compose.yml`：`celery-worker` 并发从 **2 提升到 3**，命令恢复为 `-Q celery,indicator,cninfo`。

### 2.2 数据精度修复

- 错误：`600653.SH` 的 `volatility_20d` 计算结果约 **36,629.75**，远超原 `numeric(8,4)` 上限 **9,999.9999**，导致整个 SQL chunk 失败并回退到 pandas 单 code，严重拖慢 prefix 6。
- 修复：在 ECS 上执行 `ALTER TABLE etf_indicator ALTER COLUMN volatility_20d/volatility_60d/sharpe_1y TYPE numeric(12,4)`。
- 代码同步：
  - `app/models/etf.py` 中三列从 `DECIMAL(8, 4)` 改为 `DECIMAL(12, 4)`。
  - 新增 alembic 迁移：`alembic/versions/2026_07_17_widen_etf_indicator_volatility_sharpe.py`，保证后续新环境 schema 一致。

### 2.3 队列异常处理

- 现象：worker 重启后 `indicator` 队列只有 2 个任务被消费，大量消息滞留在 Redis `unacked` hash。
- 修复：使用临时脚本读取 Redis `unacked`，将非运行中的任务 `LPUSH` 回 `indicator` 队列并清理 `unacked_index`。
- 清理：补齐完成后，已清空 `indicator` 队列中残留的冗余 prefix 6 任务，避免 worker 空闲后重复执行。

### 2.4 最后 3 条缺失记录

- 缺失代码：`600601.SH`、`600651.SH`、`600653.SH`。
- 原因：prefix 6 SQL batch 因历史数据窗口大、递归 CTE 过慢，600s 未返回。
- 处理：使用 pandas backend 直接对 3 个代码逐条计算并 upsert，2 分钟内完成。

---

## 3. 文件变更清单

| 文件 | 变更内容 | 状态 |
|---|---|---|
| `app/data/indicators/sql_calculator.py` | `max_bars` 改为从 `INDICATOR_SQL_MAX_BARS` 读取，默认 300 | 已应用 |
| `app/models/etf.py` | `volatility_20d/volatility_60d/sharpe_1y` 改为 `DECIMAL(12, 4)` | 已修改 |
| `alembic/versions/2026_07_17_widen_etf_indicator_volatility_sharpe.py` | 新增迁移，扩宽三列 | 已创建 |
| `deploy/aliyun-ecs/docker-compose.yml` | worker 并发 3，恢复 `-Q celery,indicator,cninfo` | 已应用 |
| `/tmp/trigger_0715.py`、`/tmp/requeue_unacked.py`、`/tmp/test_single_indicator*.py` | 本地临时脚本 | 已删除 |
| ECS `/tmp` 临时脚本/日志 | 生产临时文件 | 已清理 |

---

## 4. 当前生产状态

```text
=== time ===
Fri Jul 17 11:37:41 AM CST 2026
=== indicator count ===
7066
=== target bars count ===
7066
=== queues ===
indicator=0
cninfo=14
celery=0
=== worker active_queues ===
celery, indicator, cninfo
```

- `alloyresearch-backend` / `alloyresearch-celery-worker` / `nginx` / `postgres` / `redis` 全部运行中。
- `https://www.alloyresearch.net/health` 返回 `status=ok`。

---

## 5. 仍存在的问题与下一步

| 优先级 | 事项 | 说明 |
|---|---|---|
| P1 | 真 secret rotate | DeepSeek/雪球/Tushare 真 key 已识别，仓库历史 `.env` 未抹，需下一轮 sprint 执行（见 [[20260704-secret-rotate-runbook]]、[[20260705-secret-rotate-3-providers]]） |
| P1 | UI Sprint 遗留 4 项 | 见 [[20260701-p0-and-ui-sprint-results]] |
| P2 | `cninfo_pdf` 任务持续时间长 | 当前 3 个并发任务预计数小时完成，需持续观察是否出现 idle-in-transaction 或 worker 内存问题 |
| P2 | `INDICATOR_SQL_CHUNK_SIZE` 与 `INDICATOR_SQL_MAX_BARS` 调优 | prefix 6 在大窗口下仍可能超时，建议根据运行日志进一步调优 |
| P2 | scheduler 长会话优化 | 多个 scheduler 函数持有 `SessionLocal()` 到 pipeline 结束 |
| P3 | `cninfo_pdf.py` 冗余 `db.close()` | `try` 与 `finally` 各一次，可清理 |

---

## 6. 操作命令速查

```bash
# 查看 2026-07-15 指标行数
docker exec -i -e PGPASSWORD=$POSTGRES_PASSWORD alloyresearch-postgres \
  psql -U etf -d ad_research -c "SELECT COUNT(*) FROM etf_indicator WHERE trade_date = '2026-07-15'"

# 查看队列长度
for q in indicator cninfo celery; do
  docker exec alloyresearch-backend python -c \
    "import redis; print('$q', redis.from_url('redis://redis:6379/0').llen('$q'))"
done

# 查看 worker 监听队列
docker exec alloyresearch-celery-worker celery -A app.core.celery_app inspect active_queues

# 手动触发指标重算（按需）
docker exec -i alloyresearch-backend python -c \
  "from app.tasks.indicator import calculate_indicators; \
   calculate_indicators.delay(target_date='2026-07-15', market_filter='A股', code_prefix='6')"
```

---

## 7. 决策与回滚

- **决策**：本次跨文件修改（部署配置、SQL calculator、模型、迁移、队列运维）已同步更新代码、迁移文件与决策日志。未执行 `git push`，等待用户明确指令。
- **回滚方式**：若新迁移/模型改动导致问题，可执行 `alembic downgrade 2026_07_17_add_instrument_daily_bar_trade_date_index`；部署相关回滚使用 `bash scripts/rollback.sh <COMMIT_SHA>`。
