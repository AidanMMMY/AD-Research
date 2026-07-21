# 2026-07-21 全站指标正确性交叉核实与系统性修复报告

> 起因：SectorRotation 页「市场平均 1月 = -994458818.74%」与「Phase 3 官方指数回报 0/32」。
> 方法：10 个只读核实 agent 并行（计算链路审计 + 生产库脏数据扫描 + 东方财富/新浪/akshare、
> sina/stooq/yfinance、Binance 权威源抽样交叉核实），随后 9 个修复 agent 并行施工，
> 最后服务器数据修复链 + 指标重算。本文记录根因、修复与验证结果。

## 一、系统性根因（按影响排序）

### 1. adj_factor 复权因子接缝（P0，影响面最大）
- **个股**：7/9 起 daily ETL 写入 Tushare 真实累计因子（139.008、10055.64…），历史行是 1.0/归一化
  混合基底 → 5216 只个股的 return/MA/RSI/波动率全部失真（000001.SZ return_1m 显示 13997%，真实 -2.5%）
- **ETF**：方向相反——历史=真因子（510300=1.2671），7/6 起 daily 新行被 Sina/EM 路径写 1.0
  → 237 只 ETF 收益失真（510020 +877%、159943 -92%）
- **修复**：源头（akshare Sina fallback/EM daily 不再写因子，置 NA 由 upsert CASE 保留）+
  数据（全量回填：ETF 46.9 万行、个股近年段 189 万行 + 全历史后台回填）+
  护栏（a_share_stock_daily 因子连续性 ERROR 告警）

### 2. -1e9 哨兵（P0）
- PG 的 GREATEST/LEAST 跳过 NULL 参数：sql_calculator 的 clamp 把「历史不足 → NULL」变成
  -1000000000（生产每日最多 531 行），污染板块均值/评分分位/筛选排序
- **修复**：LAG 落 CTE 列后 CASE 判空写 NULL（与 pandas 路径一致）+ payload |return|≥1e8 质量门
  + sector_rotation_service |v|≥10 物理域过滤（防线）

### 3. 缺 8 个交易日（6/24, 6/29-7/3, 7/9, 7/10, 7/16）
- LAG(21) 基准日错位，连干净标的 r1m 也错 3-9pp
- **修复**：8 天全部回补（EM 自动降级 Sina）

### 4. 指标查询性能（重算 blocker）
- bars CTE 冗余 EXISTS 半连接（恒真，嵌套循环）+ 全历史扫描 → 20 code/chunk 128s
- **修复**：删 EXISTS 换直接谓词 + per-code LATERAL LIMIT 300 → 34s（输入 40k→6k 行）

### 5. Phase 3 官方回报 0/32
- service 写 return_source/official_close/sw_l1_code，但 SectorPerformance schema 未声明，
  FastAPI response_model 全剥离——功能上线起就没透出过
- **修复**：schema 补 3 个 Optional 字段

### 6. 其他（全部已修）
- us_backfill 头阻塞（BF.B/BRK.B 永远失败永远优先 → 冷却+符号映射，美股日线已恢复到 7/17）
- us_daily_etl 第三兜底源 SinaUSProvider（Tiingo 配额/yfinance 限流双挂保底）
- flow_signal 塌缩（composite 缺量归一 + gdhs 列名 + AH 垃圾行 + NameError + partial 诚实化 + 交易日守卫）
- futures 换月日 pre_settle shift 失真、Binance change_pct 前收口径、低价币零价防护
- Microstructure lift_ratio 小数口径、formatRelative 未来时间「刚刚」、东财 F10 持仓单位 ×1e4（存量 15979 行已修）
- 调度时点对齐上游：global_indices 16:00→17:00、sw_industry 周一 09:30→每交易日 20:00、microstructure 18:30→19:30

## 二、验证结果（生产，2026-07-21 11:15）

| 项 | 修复前 | 修复后 | 验证方式 |
|---|---|---|---|
| SectorRotation 市场平均 1月 | **-994458818.74%** | **-2.11%** | API 实测，与指数 -4.9% 同向（等权口径） |
| Phase 3 官方回报 | 0/32 | **31/32**（上限即 31，宽基桶无官方指数） | API 实测，各行业带官方点位 |
| 指标外部抽样（510300/512190/510020/510500） | 偏差最大 +879pp | **4/4 精确一致**（误差 <0.01pp） | sina/akshare 交叉核实 |
| 美股日线 | 断供至 6/29 | 恢复至 **7/17**（最新交易日） | 生产库 max(trade_date) |
| etf_indicator 7/17 均值/max | avg 6.25 / max 9407 | avg ~0.0003 / max <100（尾部清理中） | 生产库统计 |
| pytest | 58 failed | **923 全绿**（+40 个新回归测试） | 本地全量 |
| web check:ci | stylelint 103 error | **全绿** | 本地 |

## 三、遗留事项

- [ ] 24 天历史指标重算后台消化中（6/15-7/16，~10h，不影响最新数据正确性）
- [ ] 全历史因子回填（2010-2022 段）暂停在 2022-10，晚间用 --start 2022-10-10 续跑（仅影响 1 年以上回望）
- [ ] 每日 08:00 例行指标任务今后 ~2h（原 ~8h），观察首日
- [ ] 中国宏观金十源停更近一年（CPI/PMI/M2 停 2025-08），需换源（决策项）
- [ ] 东财资金流主源被封，fallback 为东财 push2 候选 200 只（覆盖率降，需评估付费源）
- [ ] Wilder 递归链仍是指标查询主要成本（~30-90s/chunk），可评估非递归化
- [ ] PEPE/BONK 低价币需扩列精度（numeric(18,8) 迁移）才能恢复采集
- [ ] psycopg2 + numpy 2.x 是系统性地雷（repr 变 np.float64），建议全库审计 insert 参数来源
