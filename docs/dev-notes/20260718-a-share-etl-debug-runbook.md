# A 股 ETF 日线/指标补齐 Debug Runbook

> 适用场景：A 股日线（`instrument_daily_bar`）或指标（`etf_indicator`）缺失、重算中断、数据源切换、部署后需要手动回补。
> 记录时间：2026-07-18
> 最后核实更新：2026-07-21
> 相关记忆：[[生产 /data 磁盘满事件]]、[[指标补齐临时切换 celery-worker 为 indicator-only]]、[[A 股 2026-07-15 指标补齐最终复盘报告]]

---

## 1. 数据链路总览

```
ETFInfo (active A-share ETFs)
        │
        ▼
AkshareProvider.fetch_daily_bars(codes, start, end)
        │
        ▼
AShareETLPipeline.extract()  ->  只保留 target_date 的行
        │
        ▼
AShareETLPipeline.load()     ->  ON CONFLICT (etf_code, trade_date) DO UPDATE
        │
        ▼
instrument_daily_bar
        │
        ▼
batch_calculate_indicators(target_date, market_filter='A股')
        │
        ▼
etf_indicator  (ON CONFLICT (etf_code, trade_date) DO UPDATE)
```

关键文件：

- `app/data/pipelines/a_share.py` — 日线 ETL，负责写入 `instrument_daily_bar`。
- `app/data/indicators/calculator.py` — 指标计算，写入 `etf_indicator`。
- `app/tasks/indicator.py` — Celery 任务 `calculate_indicators`。
- `app/core/celery_app.py` — Celery 应用配置。
- `deploy/aliyun-ecs/docker-compose.yml` — `celery-worker-indicator`（`-Q indicator`）与 `celery-worker-cninfo`（`-Q celery,cninfo,industry`）服务定义。

---

## 2. 快速检查清单

### 2.1 检查某日日线是否补齐

```sql
SELECT trade_date, COUNT(*) AS cnt
FROM instrument_daily_bar
WHERE trade_date IN ('2026-07-15', '2026-07-16', '2026-07-17')
GROUP BY trade_date
ORDER BY trade_date;
```

目标值 ≈ 当日有行情的 A 股 ETF 数量（`etf_info` 中 `market='A股' AND status='active'`）。

### 2.2 检查某日指标是否补齐

```sql
SELECT trade_date, COUNT(*) AS cnt
FROM etf_indicator
WHERE trade_date IN ('2026-07-15', '2026-07-16', '2026-07-17')
GROUP BY trade_date
ORDER BY trade_date;
```

指标行数应 ≥ 日线行数（同一 `etf_code + trade_date` 对应一条指标记录）。

### 2.3 检查 active ETF 总数

```sql
SELECT COUNT(*) FROM etf_info
WHERE market = 'A股' AND status = 'active';
```

### 2.4 检查哪些 code 缺失

```sql
WITH active AS (
    SELECT code FROM etf_info WHERE market='A股' AND status='active'
)
SELECT a.code
FROM active a
LEFT JOIN instrument_daily_bar b
    ON a.code = b.etf_code AND b.trade_date = '2026-07-17'
WHERE b.etf_code IS NULL;
```

---

## 3. 常见故障模式与处理

### 3.1 EM 接口连续失败，回落到 Sina 数据源

现象：Celery / backend 日志出现：

```
[INFO] EM 接口连续失败 2 次，后续将直接使用 Sina 接口
```

影响：

- Sina 接口可能缺少 `turnover_rate` 等字段。
- `AShareETLPipeline.load()` 已做幂等保护：NULL 值不会覆盖已有非 NULL 值（`CASE WHEN excluded.col IS NOT NULL THEN excluded.col ELSE existing_col END`）。
- 若某字段为 NULL，可等数据源恢复后重跑该日期，ETL 会自动补全。

处理：

1. 观察 EM 接口是否恢复（网络、akshare 版本、节假日）。
2. 若长期缺失，可手动用 Sina 先补，后续 EM 恢复后再重跑。

### 3.2 指标重算任务被 backend 重启中断

背景：重算任务原本在 `alloyresearch-backend` 容器内通过 `docker exec` 运行，backend 部署/重启会杀死它。

当前状态：指标重算已改造为 Celery 任务，由独立的 `alloyresearch-celery-worker-indicator` 容器消费。backend 重启不会影响已入队任务。

验证 worker 是否在线：

```bash
ssh ad-research
docker top alloyresearch-celery-worker-indicator | grep celery
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app inspect active
```

### 3.3 /data 磁盘满导致 Postgres PANIC

现象：

```
PANIC: could not write to file ... No space left on device
```

处理：

1. 检查磁盘：

   ```bash
   ssh ad-research df -h /data
   ```

2. 若 Aliyun 控制台已扩容到 120 GiB 但系统仍显示 40 GB，执行在线扩容：

   ```bash
   ssh ad-research
   sudo resize2fs /dev/vdb
   ```

3. 清理：删除旧 Docker build cache、过期日志、不必要的备份。

监控阈值：建议 `/data` 使用率 ≥ 80%（约 95 GB）时告警。

### 3.4 `ON CONFLICT` 字段不匹配导致 ETL 报错

现象：ETL 插入时报 `ON CONFLICT DO UPDATE` 列不匹配。

根因：DataFrame 中不同来源的列集不同，SQLAlchemy bulk insert 要求所有 value dict 键一致。

修复：当前 `a_share.py` 的 `load()` 已把所有记录规范化到相同的 `present_cols` 集合；若某来源缺少某列，则该列在该批次记录中全部为 NULL，并在 DO UPDATE SET 中跳过该列。

---

## 4. 指标缺失根因与修复

2026-07-15 前后 A 股指标多次出现大面积缺失，复盘后定位到 5 类根因与对应修复措施。

### 4.1 DECIMAL(8,4) 对极端收益溢出

现象：指标计算写入 `etf_indicator` 时报 `numeric field overflow`，任务失败。

根因：`return_1y`、`change_pct` 等字段使用 `DECIMAL(8,4)`，对类似 `600601.SH` 这种退市整理/极端行情个股，收益值超过 9999.9999 可表示范围，导致 SQL 报错。

修复：

- 相关收益/波动字段扩宽为 `DECIMAL(12,4)` 或 `DECIMAL(18,8)`，保留 4 位小数但扩大整数位。
- 计算层在 `calculator.py` 中增加 `np.clip` 或 `Decimal` 边界兜底，避免写入时二次溢出。

验证：

```sql
SELECT column_name, data_type, numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_name = 'etf_indicator' AND column_name LIKE 'return%';
```

### 4.2 /data 磁盘满导致 Postgres 崩溃

现象：

```
PANIC: could not write to file ... No space left on device
ERROR: could not fsync file ...: No space left on device
```

根因：/data 只显示 40 GB 但实际磁盘已扩容到 120 GB，文件系统未 `resize2fs`；同时 Docker build cache、过期日志占用空间，最终 100% 导致 Postgres 无法写入 WAL/临时文件，部分进程崩溃。

修复：

- 已执行 `sudo resize2fs /dev/vdb`，/data 扩展到约 118 GB。
- 清理 Docker build cache、过期日志和临时备份。
- 在 /health 中增加磁盘使用率检查，≥ 80% 返回 degraded。
- 设置告警阈值：/data 使用率 ≥ 80%（约 95 GB）触发告警。

详见：[[生产 /data 磁盘满事件]]。

### 4.3 Celery Redis visibility_timeout 默认 1h 小于指标任务运行时长

现象：指标重算任务重复执行，同一日期被多个 worker 同时消费，日志出现多次 `calculate_indicators` 入口。

根因：Redis broker 默认 `visibility_timeout=3600`（1 小时），而 A 股全量指标重算在数据量大时可能超过 1 小时。任务未及时确认，被 broker 重新投递。

修复：在 `app/core/celery_app.py` 中显式配置（当前值 12 小时）：

```python
celery_app.conf.update(
    ...
    broker_transport_options={"visibility_timeout": 43200},  # 12h，避免长任务被重复投递
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    ...
)
```

同时指标任务设置 `time_limit` 和 `soft_time_limit`（当前为软 4h / 硬 6h）：

```python
@celery_app.task(bind=True, soft_time_limit=4 * 3600, time_limit=6 * 3600, queue="indicator")
def calculate_indicators(self, target_date=None, market_filter="A股", ...):
    ...
```

### 4.4 单一 worker 同时跑 indicator / cninfo / celery，cninfo_pdf 长时间占满并发

现象：指标任务排队严重，晚上 cninfo 定期报告任务启动后，4 个并发槽被 PDF 下载长时间占满，指标计算延迟数小时。

根因：旧部署中一个 `celery-worker` 容器同时监听 `celery`、`indicator`、`cninfo` 队列，`-c 4` 的并发被 cninfo_pdf 这类 I/O 长任务占满，指标任务无法及时执行。

修复（2026-07-21 核实后的现状）：

- 生产 `deploy/aliyun-ecs/docker-compose.yml` 已拆分为两个独立 worker 服务：
  - `celery-worker-indicator`（容器名 `alloyresearch-celery-worker-indicator`）：仅监听 `indicator` 队列，`-c 4`，保证指标重算不被其他任务挤占。
  - `celery-worker-cninfo`（容器名 `alloyresearch-celery-worker-cninfo`）：监听 `celery,cninfo,industry` 队列，`-c 2`，PDF 下载等长任务在此消费。
- 队列路由在 `app/core/celery_app.py` 的 `task_routes` 中配置（indicator → `indicator`，cninfo/cninfo_pdf → `cninfo`，sw_industry → `industry`）。

### 4.5 调度器使用 target_date=None，两次调度造成 latest-date 漂移和重复跑

现象：夜间调度出现同一日期跑两次，或最新交易日漂移（例如跑到非目标日期）。

根因：定时任务调用 `calculate_indicators.delay()` 时未传 `target_date`，函数内部使用 `date.today()` 或查询最新日期；当调度器在 00:00 前后触发两次时，第二次可能已跨天，导致 latest-date 漂移。此外，未传 market_filter 时可能误触其他市场。

修复：

- 调度器在投递前先把 `target_date` 解析为确定日期（`app/core/scheduler.py` 的 `_resolve_a_share_target_date()`：显式传入优先，否则从 A 股最新 bar 推断），再显式传入 `target_date` 和 `market_filter`：

```python
effective_date = _resolve_a_share_target_date(target_date, db)
calculate_indicators.delay(target_date=effective_date.isoformat(), market_filter="A股")
```

- 幂等保护：`_acquire_indicator_date_lock()` 用 Redis 锁保证同一日期同一时刻只有一个调度在跑；并新增 17:00 的 `a_share_indicator_fallback` 兜底补算任务（幂等 UPSERT，防止 08:00 跑在 ETL 之前导致当日缺行）。
- 注意（2026-07-21 核实）：Celery 任务入口本身**没有**「`target_date` 为空则报错」的防御性检查——`target_date=None` 时任务仍会按全量最新日期执行，防护依赖调度器层始终显式传日期。

### 4.6 完整性巡检

除上述修复外，建立每日巡检机制：

- 运行审计脚本检查指标覆盖率：

  ```bash
  DATABASE_URL=postgresql://... python scripts/audit_indicator_completeness.py
  ```

- 覆盖率低于 95% 触发 WARN，低于 90% 触发 CRITICAL，自动通知运维。
- 巡检纳入 `/health` 接口或独立 cron 任务。

---

## 5. 手动触发与回填

### 5.1 手动触发日线 ETL（单日期）

```bash
ssh ad-research
docker exec -i alloyresearch-backend python - <<'PY'
from datetime import date
from app.core.database import SessionLocal
from app.data.pipelines.a_share import AShareETLPipeline

db = SessionLocal()
try:
    pipe = AShareETLPipeline(db, target_date=date(2026, 7, 17))
    rows = pipe.run()
    print("upserted", rows)
finally:
    db.close()
PY
```

### 5.2 通过 Celery 触发指标重算

```bash
ssh ad-research
docker exec alloyresearch-celery-worker-indicator python -c "
from app.tasks.indicator import calculate_indicators
r = calculate_indicators.delay(target_date='2026-07-17', market_filter='A股')
print(r.id)
"
```

查询任务状态：

```bash
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app inspect active
```

### 5.3 批量回补最近 N 天

```bash
ssh ad-research
docker exec alloyresearch-celery-worker-indicator python -c "
from datetime import date, timedelta
from app.tasks.indicator import calculate_indicators
for i in range(3):
    d = (date.today() - timedelta(days=i+1)).isoformat()
    calculate_indicators.delay(target_date=d, market_filter='A股')
    print('queued', d)
"
```

---

## 6. 验证与收尾

回补后必须执行：

```sql
-- 日线
SELECT trade_date, COUNT(*) FROM instrument_daily_bar
WHERE trade_date >= '2026-07-15' GROUP BY trade_date ORDER BY trade_date;

-- 指标
SELECT trade_date, COUNT(*) FROM etf_indicator
WHERE trade_date >= '2026-07-15' GROUP BY trade_date ORDER BY trade_date;
```

若指标仍少于日线，查看 Celery worker 日志：

```bash
ssh ad-research
docker logs --tail 100 alloyresearch-celery-worker-indicator
```

常见原因：

- `max_bars` 窗口不足 -> 检查 `calculator.py` 中的参数。
- 某代码历史 bar 不足 -> 该 code 指标为 NULL，属正常。
- SQL backend 查询超时 -> 改用 pandas backend 或分片。

---

## 7. 关键设计决策

1. **幂等写入**：日线和指标表都有唯一索引 `(etf_code, trade_date)`，重跑不会重复。
2. **NULL 不覆盖**：日线 ETL 用 `CASE ... ELSE existing_col` 保护，避免 Sina 回落清空 EM 已写字段。
3. **Celery 隔离**：长时重算任务在独立 worker 容器，backend 部署不再中断它们。
4. **并发限制**：worker `-c 4` 同时跑 4 个任务，防止拖垮数据库。

---

## 8. 附录：相关 SQL 与命令速查

### 8.1 常用命令

```bash
# 查看当前活跃 Celery 任务
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app inspect active

# 查看指定队列任务数（scheduled / reserved）
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app inspect scheduled
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app inspect reserved

# 清空某个队列（危险，仅在确认需要时执行）
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app control queue_purge indicator

# 运行指标完整性审计脚本（自动取 A 股最新交易日）
DATABASE_URL=postgresql://user:pass@localhost:5432/ad_research \
  python scripts/audit_indicator_completeness.py

# 审计指定日期
DATABASE_URL=postgresql://user:pass@localhost:5432/ad_research \
  python scripts/audit_indicator_completeness.py --date 2026-07-17
```

### 8.2 常用 SQL

```sql
-- 按来源查看某日写入量
SELECT source, COUNT(*) FROM news_article
WHERE DATE(published_at) = '2026-07-17'
GROUP BY source ORDER BY COUNT(*) DESC;

-- 查看 celery 任务结果（若启用 result backend）
-- redis-cli -n 0 KEYS 'celery-task-meta-*' | head
```

```bash
# 查看 Redis 队列堆积
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app inspect scheduled
docker exec alloyresearch-celery-worker-indicator celery -A app.core.celery_app inspect reserved

# 清空 indicator 队列（危险，仅在需要时）
docker exec alloyresearch-redis redis-cli -n 0 DEL celery:indicator
```
