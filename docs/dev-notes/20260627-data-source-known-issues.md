# 数据源已知问题备忘

> **注**：本文为 2026-06-27 的时点记录，部分内容可能已过时（如 akshare 接口行为、`560000.SH` 在 `etf_info` 中的状态需以数据库现状为准）。

> 记录 A 股 ETF 数据采集中遇到的已知数据源问题及处理决策。
> 最后更新：2026-06-27

---

## 560000.SH 智能电车ETF浦银

### 问题现象

在 2026-06-27 的 A 股 ETF 日线补数据过程中，`AShareETLPipeline` 报告：

```text
Missing expected ETF codes: ['560000.SH']
```

即该 ETF 在目标交易日（2026-06-26）没有获取到日线数据。

### 根因分析

1. **ETF 仍存在且交易正常**
   - `akshare.fund_etf_spot_em()` 实时行情接口可查到该 ETF
   - 最新价 0.939，涨跌幅 0.0%

2. **新浪历史数据断层**
   - `akshare.fund_etf_hist_sina(symbol='sh560000')` 返回的历史数据仅到 **2026-04-30**
   - 2026-05-01 至 2026-06-26 期间无任何日线数据

3. **东方财富接口存在 2026 年份解析 bug**
   - `akshare.fund_etf_hist_em(symbol='560000', start_date='20250620', end_date='20250626')`
   - 实际返回的是 **2025-06-20 至 2025-06-26** 的数据
   - 使用 `20260620` 作为参数时返回空
   - 该 bug 影响东方财富接口对 2026 年日期的解析

### 处理决策

已于 2026-06-27 将该 ETF 在 `etf_info` 表中的状态从 `active` 更新为 `inactive`：

```sql
UPDATE etf_info
SET status = 'inactive', updated_at = NOW()
WHERE code = '560000.SH';
```

后续 `AShareETLPipeline` 和定时任务不会再尝试获取该 ETF 的数据，pipeline 警告也会随之消除。

### 恢复条件

当满足以下任一条件时，可重新将其置为 `active`：

1. `akshare.fund_etf_hist_sina('sh560000')` 能正常返回 2026-04-30 之后的数据
2. `akshare.fund_etf_hist_em()` 修复了 2026 年份解析 bug
3. 切换到其他能覆盖该 ETF 的数据源

恢复命令：

```sql
UPDATE etf_info
SET status = 'active', updated_at = NOW()
WHERE code = '560000.SH';
```

---

## 相关命令

### 检查某只 ETF 的数据源状态

```bash
ssh alloy-research
docker exec -i -w /app alloyresearch-backend python3 - <<'PY'
import akshare as ak
import pandas as pd
from datetime import date

code = '560000.SH'
pure = code.split('.')[0]
exchange = 'sh' if code.endswith('.SH') else 'sz'

# 新浪接口
df = ak.fund_etf_hist_sina(symbol=f'{exchange}{pure}')
df['date'] = pd.to_datetime(df['date']).dt.date
recent = df[(df['date'] >= date(2026, 6, 20)) & (df['date'] <= date(2026, 6, 26))]
print(f'新浪 {code}: 最近 7 天记录数 {len(recent)}')

# 东方财富接口
df2 = ak.fund_etf_hist_em(symbol=pure, period='daily', start_date='20260101', end_date='20260626', adjust='qfq')
print(f'东方财富 {code}: 2026 年记录数 {len(df2)}')
PY
```

### 查看当前 inactive ETF 列表

```sql
SELECT code, name, updated_at
FROM etf_info
WHERE status = 'inactive'
ORDER BY updated_at DESC;
```

---

*文档生成时间：2026-06-27*
