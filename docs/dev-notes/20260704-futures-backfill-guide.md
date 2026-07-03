# 商品期货数据补跑指南（2026-07-04）

## 背景

`futures_contracts` 和 `futures_daily_bars` 表在 2026-07-04 之前为空。根因是
`FuturesContractDiscoveryPipeline` 与 `FuturesDailyPipeline` 继承了基类
`ETLPipeline.run()`，而基类使用 ETF OHLCV 专属的四层校验器，导致：
- 合约发现产出的元数据（`code/name/exchange/product`）被拒绝。
- 日 K 提取的列名 `code` 被基类 normalizer 映射为 `etf_code`，导致 `load()` 读不到列；ETF 专属业务校验（`high < low`、OHLC 容差）进一步把正常/可修复的行判定为非法，整批失败。

## 修复（已合并）

`app/data/pipelines/futures.py`：
- `FuturesContractDiscoveryPipeline.run()` 覆盖基类，跳过 ETF OHLCV 校验。
- `FuturesDailyPipeline.run()` 覆盖基类，仅保留轻量 L1 列存在性检查。
- 日 K extract 内部符号列改回 `etf_code`，与 `load()` 对齐。
- 丢弃 `high < low` 等明显脏行而非 abort。

`app/tests/test_futures_pipeline.py`：新增 3 个回归测试。

## 一键补跑脚本

`scripts/backfill_futures_history.py`

常用命令：

```bash
# 默认：10000 天历史 + 自动发现合约
python3 scripts/backfill_futures_history.py

# 指定历史窗口
python3 scripts/backfill_futures_history.py --history-days 5000

# 指定目标日期（默认昨日）
python3 scripts/backfill_futures_history.py --target-date 2026-07-03

# 跳过合约发现，只补日 K
python3 scripts/backfill_futures_history.py --skip-discovery

# 单合约手动重试次数（默认 3）
python3 scripts/backfill_futures_history.py --max-attempts 5
```

## 历史补跑结果（2026-07-04）

| 交易所 | 合约数 | 日线数        | 区间                          |
|--------|--------|---------------|-------------------------------|
| CFFEX  | 6      | 12,040        | 2017-01-17 ~ 2026-07-03       |
| CZCE   | 25     | 59,931        | 2005-01-04 ~ 2026-07-03       |
| DCE    | 22     | 68,605        | 2005-01-04 ~ 2026-07-03       |
| GFEX   | 5      | 2,221         | 2022-12-22 ~ 2026-07-03       |
| INE    | 5      | 7,194         | 2018-03-26 ~ 2026-07-03       |
| SHFE   | 19     | 58,365        | 2005-01-04 ~ 2026-07-03       |

合计：82 个主力连续合约 / 208,356 条日线 / 时间跨度 2005-01-04 至 2026-07-03。
期间 1 条 `high < low` 脏数据被丢弃。

## 后续调度

调度器中的 `run_futures_daily`、`run_futures_contract_refresh` 现在可以正常工作，
日常跑批会自动保留最近 30 天数据。如需重新补更久远的历史，按上面命令调
`--history-days` 即可。
