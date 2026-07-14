# A 股指标每日完整性 Runbook

## 1. 问题

`etf_indicator` 表同一日期的记录数差异巨大：有时 1500 条（全 ETF），有时 5500 条（全 STOCK），看上去「完整」但其实各缺一半。

## 2. 根因

**不是 indicator 计算任务有 bug，是上游日 K ETL 跑得不全。**

| 文件 | cron | 过滤 | 数据源 |
|---|---|---|---|
| `app/data/pipelines/a_share.py` | 15:30 | `market='A股' AND instrument_type='ETF'` | akshare |
| `app/data/pipelines/a_share_stock_daily.py` | 16:00 | `instrument_type='STOCK'` | Tushare |

两条 ETL 各自跑、各自可能失败。`instrument_daily_bar` 当日缺哪类 → indicator 计算 08:00 时只能找到有的那类，写出对应记录。

数据库验证：

```
SELECT trade_date,
       count(*) FILTER (WHERE etf_code LIKE '5%' OR etf_code LIKE '1%') AS etf_like,
       count(*) FILTER (WHERE etf_code ~ '^(000|001|002|003|300|301|600|601|603|605|688)') AS stock_like
FROM etf_indicator GROUP BY trade_date ORDER BY trade_date DESC LIMIT 5;

 2026-07-13 | 3 (ETF) | 447 (STOCK)  ← 修复前：600601.SH overflow 卡死只残留早期任务写入
 2026-07-10 | 0        | 5186         ← ETF ETL 失败，仅 STOCK
 2026-07-09 | 0        | 122          ← ETF ETL 失败，仅 STOCK
 2026-07-08 | 1514     | 0            ← STOCK ETL 失败，仅 ETF
```

## 3. 修复

### 3.1 新增 17:00 兜底 cron（核心）

`app/core/scheduler.py` 新增函数与 cron：

```python
def run_a_share_indicator_fallback(target_date=None):
    with redis_lock(_LOCK_DAILY_PIPELINE, expire_seconds=3600, wait_timeout=1800):
        calculate_indicators.delay(
            target_date=target_date.isoformat() if target_date else None,
            full_history=False,
            market_filter="A股",
        )

# init_scheduler() 中注册
scheduler.add_job(
    run_a_share_indicator_fallback,
    trigger=CronTrigger(hour=17, minute=0, timezone="Asia/Shanghai"),
    id="a_share_indicator_fallback",
    name="A股指标17点兜底补算",
    replace_existing=True,
    max_instances=1,
)
```

**为什么 17:00**：
- 15:30 ETF ETL（自带 `run_with_retry`）
- 16:00 STOCK ETL
- 16:30 STOCK 估值 ETL
- 17:00 时所有上游 ETL 都 retry 完；此时跑 indicator 计算，`instrument_daily_bar` 当日数据齐整（ETF + STOCK 都有）

### 3.2 `--instrument-type` 兼容选项

`scripts/trigger_indicator_calc.py` 增加：

```bash
# 默认 = 跑全部 A 股（推荐）
python scripts/trigger_indicator_calc.py --target-date 2026-07-13 --market A股

# 运维想强制只跑某类型时
python scripts/trigger_indicator_calc.py --instrument-type ETF
python scripts/trigger_indicator_calc.py --instrument-type STOCK
```

`app/data/indicators/calculator.py` `batch_calculate_indicators` 和 `app/tasks/indicator.py` `calculate_indicators` Celery 任务同步增加可选 kwarg `instrument_type_filter`，默认 `None` 不影响旧调用。

## 4. 验证

```bash
# 修复后某天的健康分布（应 ETF + STOCK 混合 ~7000 条）
docker exec alloyresearch-postgres psql -U etf -d ad_research -c "
SELECT substring(etf_code FROM 1 for 3) AS prefix, count(*)
FROM etf_indicator WHERE trade_date='2026-07-14' GROUP BY 1 ORDER BY 2 DESC LIMIT 20;"
# 期望：159/510/511/.../600/688/000/300 等前缀都出现，总数 ≥ 5500
```

## 5. 建议的后续防御（下一轮 sprint）

1. **bar 数据齐整性告警**：在 `run_a_share_indicator_fallback` 加前置检查，比较 `instrument_daily_bar` 当日条数 vs `etf_info where market='A股' and status='active'` 条数，差距 >5% 时发 Slack/钉钉告警
2. **pipeline extract 层字段容错**：`a_share_daily_etl` 失败原因多为 `change_pct` / `turnover_rate` 字段缺失（provider 返回 None），需在 extract 层做字段容错避免整条失败
3. **monitor 看板**：在 `/admin/etl-health` 显示每日 bar / indicator 覆盖率

## 6. 已知陷阱

- 修改 `batch_calculate_indicators` 时永远加 `if instrument_type_filter is not None` 守卫，避免影响老调用
- 17:00 cron 部署后**第一次**需要 backend 容器重启才能让 `init_scheduler()` 注册（scheduler 进程内单例）