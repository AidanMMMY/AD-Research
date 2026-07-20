"""SQL window-function indicator calculator.

Drop-in replacement for the pandas path in :mod:`app.data.indicators.calculator`
that computes every per-ETF indicator in a single PostgreSQL query.

Why this exists
---------------
The pandas path is dominated by ``pandas.rolling.apply`` with Python
lambdas (``calc_max_drawdown`` / ``calc_sharpe``), which do not vectorise.
A profile of one ETF (512760.SH, 360 bars) showed:

* total per-ETF wall time: ~0.15 s
* of which ``rolling.apply`` lambdas (drawdown + sharpe): ~0.14 s
* the ewm-based RSI / MACD / ATR pieces: ~0.01 s (already fast)

At 7 061 A-share ETFs that adds up to ~18 minutes on the ECS container,
which is why the previous run timed out at the 600 s orchestrator budget.

Pushing the computation to PostgreSQL replaces the per-ETF Python
loop with a single set-based query. Everything that pandas expresses
with ``rolling(N).mean/std/max/cummax`` translates to a ``ROWS BETWEEN
N-1 PRECEDING AND CURRENT ROW`` window frame. Wilder smoothing
(``alpha = 1 / window``) and EMA (``alpha = 2 / (span + 1)``) are
expressed with recursive CTEs that walk each ``etf_code``'s ordered
bars exactly the way the pandas ewm engine does.

Public entrypoints
------------------
* :func:`sql_calculate_latest` — latest indicator row per code (the
  common scheduler path; ~30 s on the full universe).
* :func:`sql_calculate_full_history` — every historical row in the
  window (used by the backfill scripts).
* :func:`build_indicator_payload` — same upsert shape as the pandas
  path so the existing ``batch_calculate_indicators`` writes are
  unchanged.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date
from typing import Iterable

import pandas as pd
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.orm import Session

from app.data.indicators.market_config import get_market_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Defaults (A-share). Actual per-query values come from MarketIndicatorConfig.
# ---------------------------------------------------------------------------

# A-share default config, kept for module-level backward compatibility and
# for the few callers that still import the constants.
_DEFAULT_CONFIG = get_market_config("A股")

MA_WINDOWS: tuple[int, ...] = _DEFAULT_CONFIG.ma_windows
BB_WINDOW = _DEFAULT_CONFIG.bb_window
BB_NUM_STD = 2.0
RSI_WINDOW = _DEFAULT_CONFIG.rsi_window
ATR_WINDOW = _DEFAULT_CONFIG.atr_window

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

VOL_SHORT_WINDOW = 20
VOL_LONG_WINDOW = 60
RISK_LONG_WINDOW = _DEFAULT_CONFIG.risk_long_window
RISK_LONG_MIN_PERIODS = _DEFAULT_CONFIG.risk_long_min_periods

RETURN_WINDOWS: dict[str, int] = _DEFAULT_CONFIG.return_windows

# Clamp bound for period returns. WARNING: PostgreSQL's GREATEST/LEAST
# skip NULL arguments instead of propagating NULL, so this bound must
# never be applied to a potentially-NULL LAG expression inline —
# GREATEST(NULL, -1e9) returns -1e9, silently turning "history shorter
# than the window" into a -1000000000 sentinel row (production incident,
# etf_indicator return_* columns). The generated SQL materializes the
# lagged close in the ``lagged`` CTE and gates the ratio with an
# explicit NULL / non-positive CASE check before clamping.
RETURN_CLAMP: float = 1e9

TRADING_DAYS_PER_YEAR = _DEFAULT_CONFIG.annualization_factor
RISK_FREE_RATE = 0.02

# Query timeout. The SQL backend must stay within the 600 s orchestrator
# budget per chunk, so the default statement timeout is 600 000 ms.
INDICATOR_SQL_STATEMENT_TIMEOUT_MS: int = int(
    os.environ.get("INDICATOR_SQL_STATEMENT_TIMEOUT_MS", "600000")
)


def _get_max_bars_for_prefix(prefix: str | None) -> int:
    """Resolve the per-prefix ``max_bars`` cap for latest-only runs.

    ``full_history`` ignores this value entirely (it scans the whole
    history). The default is read from ``INDICATOR_SQL_MAX_BARS``; a
    prefix can be tuned with ``INDICATOR_SQL_MAX_BARS_PREFIX_<P>``,
    e.g. ``INDICATOR_SQL_MAX_BARS_PREFIX_6=280`` for the dense Shanghai
    A-share shard.
    """
    default = int(os.environ.get("INDICATOR_SQL_MAX_BARS", "300"))
    if not prefix:
        return default
    override = os.environ.get(f"INDICATOR_SQL_MAX_BARS_PREFIX_{prefix}")
    if override:
        return int(override)
    return default

# Columns the calculator writes back to ETFIndicator. Must match
# ``calculator._INDICATOR_COLUMNS`` so the existing upsert works
# without schema changes.
INDICATOR_OUTPUT_COLUMNS: tuple[str, ...] = (
    "ma5",
    "ma10",
    "ma20",
    "ma60",
    "rsi14",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "atr14",
    "bb_upper",
    "bb_lower",
    "volatility_20d",
    "volatility_60d",
    "max_drawdown_1y",
    "sharpe_1y",
    "return_1w",
    "return_1m",
    "return_3m",
    "return_6m",
    "return_1y",
    "amount",
)


# ---------------------------------------------------------------------------
# SQL building blocks
# ---------------------------------------------------------------------------


def _bars_source_cte(
    codes_bind: str,
    target_filter_sql: str,
    *,
    max_bars: int | None = None,
) -> str:
    """Build the ``windowed`` source CTE used by ``bars``.

    Returns the SQL for a CTE named ``windowed`` that selects the
    relevant rows from ``instrument_daily_bar`` for the requested
    codes, optionally limiting each code to its most recent
    ``max_bars`` rows.  The caller must define ``bars`` after this
    CTE.
    """
    if max_bars is not None:
        return f"""
        windowed AS (
            SELECT *
            FROM (
                SELECT
                    b.etf_code,
                    b.trade_date,
                    b.close,
                    b.high,
                    b.low,
                    b.adj_factor,
                    b.amount,
                    b.volume,
                    ROW_NUMBER() OVER (PARTITION BY b.etf_code ORDER BY b.trade_date DESC) AS rn_desc
                FROM instrument_daily_bar b
                WHERE b.etf_code = ANY({codes_bind})
                  AND EXISTS (
                      SELECT 1 FROM instrument_daily_bar ec
                      WHERE ec.etf_code = b.etf_code
                        AND ec.trade_date <= COALESCE(:target_date, CURRENT_DATE)
                  )
                  {target_filter_sql}
            ) ranked
            WHERE rn_desc <= {max_bars}
        )
        """
    return f"""
        windowed AS (
            SELECT
                b.etf_code,
                b.trade_date,
                b.close,
                b.high,
                b.low,
                b.adj_factor,
                b.amount,
                b.volume
            FROM instrument_daily_bar b
            WHERE b.etf_code = ANY({codes_bind})
              AND EXISTS (
                  SELECT 1 FROM instrument_daily_bar ec
                  WHERE ec.etf_code = b.etf_code
                    AND ec.trade_date <= COALESCE(:target_date, CURRENT_DATE)
              )
              {target_filter_sql}
        )
    """


_bars_select_sql = """
    bars AS (
        SELECT
            b.etf_code,
            b.trade_date,
            b.close::numeric                                        AS close,
            b.high::numeric                                         AS high,
            b.low::numeric                                          AS low,
            b.qfq_close,
            b.amount::numeric                                       AS amount,
            b.volume                                                AS volume,
            LAG(b.qfq_close)        OVER w_etf                      AS prev_qfq_close,
            ROW_NUMBER() OVER w_etf                                 AS rn,
            -- Total row count for the partition (NOT a running
            -- count). Drop the ORDER BY so the window is the
            -- whole partition, not "from start to current".
            COUNT(*) OVER (PARTITION BY b.etf_code)                 AS bar_count,
            b.qfq_close / NULLIF(LAG(b.qfq_close) OVER w_etf, 0) - 1 AS daily_return
        FROM (
            SELECT
                b.etf_code,
                b.trade_date,
                b.close,
                b.high,
                b.low,
                b.adj_factor,
                b.amount,
                b.volume,
                -- 前复权 close: 以当前窗口最新 adj_factor 为基准对历史 close
                -- 进行复权，确保技术指标与收益计算在同一可比价格空间。
                (b.close * COALESCE(b.adj_factor, 1.0)
                    / NULLIF(MAX(b.adj_factor) OVER (PARTITION BY b.etf_code), 0)
                )::numeric                                            AS qfq_close
            FROM windowed b
        ) b
        WINDOW w_etf AS (PARTITION BY b.etf_code ORDER BY b.trade_date)
    )
"""


def _ema_chain(span: int) -> str:
    """Recursive CTE for standard EMA. ``alpha = 2 / (span + 1)``.

    Matches pandas ``ewm(span=span, adjust=False)`` exactly.
    """
    return f"""
        ema_chain_{span} AS (
            SELECT b.etf_code, b.trade_date, b.rn,
                   b.qfq_close              AS ema_{span}
            FROM bars b
            WHERE b.rn = 1
            UNION ALL
            SELECT b.etf_code, b.trade_date, b.rn,
                   (2.0 / ({span} + 1.0)) * b.qfq_close
                     + (({span} - 1.0) / ({span} + 1.0)) * e.ema_{span}
            FROM bars b
            JOIN ema_chain_{span} e
              ON b.etf_code = e.etf_code AND b.rn = e.rn + 1
        )
    """


def build_indicator_query_sql(
    *,
    full_history: bool,
    target_filter_sql: str = "",
    max_bars: int | None = None,
    config: object | None = None,
    market: str = "A股",
) -> str:
    """Build the full per-code indicator SELECT statement.

    The returned string is a single ``WITH ... SELECT`` block. The
    caller binds ``:codes`` (an array of strings) and optionally
    ``:target_date``.

    Args:
        full_history: Whether to return every historical row or only the
            latest row per code.
        target_filter_sql: Optional SQL predicate appended to the bar
            source filter (e.g. ``"AND b.trade_date <= :target_date"``).
        max_bars: Optional cap on the number of recent bars per code.
        config: Optional ``MarketIndicatorConfig`` overriding the market
            lookup. If not provided, ``market`` is used.
        market: Market key used to load the correct config when ``config``
            is not provided.
    """
    if config is None:
        config = get_market_config(market)

    # Longest look-back is the long-window risk metric. For ``full_history=False``
    # we only need enough bars to warm up that window plus a safety margin;
    # reading the entire history per code is wasteful and dominates runtime
    # for instruments with many years of daily bars.
    if full_history:
        max_bars = None
    elif max_bars is None:
        max_bars = int(os.environ.get("INDICATOR_SQL_MAX_BARS", "300"))

    min_safe_max_bars = config.risk_long_window
    if max_bars is not None and max_bars < min_safe_max_bars:
        logger.warning(
            "INDICATOR_SQL_MAX_BARS=%d is below the %d-day minimum needed for the "
            "configured long-window risk metrics; 1-year risk indicators may be "
            "computed on a truncated sample.",
            max_bars,
            min_safe_max_bars,
        )
    windowed_cte = _bars_source_cte(":codes", target_filter_sql, max_bars=max_bars)

    rsi_window = config.rsi_window
    atr_window = config.atr_window
    bb_window = config.bb_window
    one_minus_rsi = rsi_window - 1
    one_minus_atr = atr_window - 1

    # Wilder-smoothed ATR. Two layers:
    #   (1) recursive walk for rn >= ATR_WINDOW, matching pandas
    #       ewm(alpha=1/14, adjust=False, min_periods=14)
    #   (2) SMA warmup for rn < ATR_WINDOW (pandas emits SMA for
    #       those rows when ``min_periods`` kicks in).
    # The seed row is the first rn in wilder_input (which is rn=2
    # because the anchor filters out rows without prev_qfq_close).
    wilder_atr_chain = f"""
        wilder_atr_chain AS (
            SELECT d.etf_code, d.trade_date, d.rn,
                   d.tr_value AS wilder_value
            FROM wilder_input d
            WHERE d.rn = (SELECT MIN(rn) FROM wilder_input)
            UNION ALL
            SELECT d.etf_code, d.trade_date, d.rn,
                   (1.0/{atr_window}.0) * d.tr_value
                     + ({one_minus_atr}.0/{atr_window}.0) * wc.wilder_value
            FROM wilder_input d
            JOIN wilder_atr_chain wc
              ON d.etf_code = wc.etf_code AND d.rn = wc.rn + 1
        )
    """

    wilder_gain_chain = f"""
        wilder_gain_chain AS (
            SELECT d.etf_code, d.trade_date, d.rn,
                   d.gain_value AS wilder_value
            FROM wilder_input d
            WHERE d.rn = (SELECT MIN(rn) FROM wilder_input)
            UNION ALL
            SELECT d.etf_code, d.trade_date, d.rn,
                   (1.0/{rsi_window}.0) * d.gain_value
                     + ({one_minus_rsi}.0/{rsi_window}.0) * wc.wilder_value
            FROM wilder_input d
            JOIN wilder_gain_chain wc
              ON d.etf_code = wc.etf_code AND d.rn = wc.rn + 1
        )
    """

    wilder_loss_chain = f"""
        wilder_loss_chain AS (
            SELECT d.etf_code, d.trade_date, d.rn,
                   d.loss_value AS wilder_value
            FROM wilder_input d
            WHERE d.rn = (SELECT MIN(rn) FROM wilder_input)
            UNION ALL
            SELECT d.etf_code, d.trade_date, d.rn,
                   (1.0/{rsi_window}.0) * d.loss_value
                     + ({one_minus_rsi}.0/{rsi_window}.0) * wc.wilder_value
            FROM wilder_input d
            JOIN wilder_loss_chain wc
              ON d.etf_code = wc.etf_code AND d.rn = wc.rn + 1
        )
    """

    # MACD: ema_chain_12 and ema_chain_26 are produced by _ema_chain
    # macros below; their DIF feeds ema_chain_signal (recursive).
    ema_fast = _ema_chain(MACD_FAST)
    ema_slow = _ema_chain(MACD_SLOW)

    macd_dif_cte = f"""
        macd_dif AS (
            SELECT f.etf_code, f.trade_date, f.rn,
                   f.ema_{MACD_FAST} - s.ema_{MACD_SLOW} AS dif
            FROM ema_chain_{MACD_FAST} f
            JOIN ema_chain_{MACD_SLOW} s USING (etf_code, rn, trade_date)
        )
    """

    macd_signal_chain = f"""
        macd_signal_chain AS (
            SELECT d.etf_code, d.trade_date, d.rn,
                   d.dif AS wilder_value
            FROM macd_dif d
            WHERE d.rn = 1
            UNION ALL
            SELECT d.etf_code, d.trade_date, d.rn,
                   (2.0/({MACD_SIGNAL} + 1.0)) * d.dif
                     + (({MACD_SIGNAL} - 1.0)/({MACD_SIGNAL} + 1.0)) * wc.wilder_value
            FROM macd_dif d
            JOIN macd_signal_chain wc
              ON d.etf_code = wc.etf_code AND d.rn = wc.rn + 1
        )
    """

    # SELECT-list fragments. All columns are qualified with ``b.`` so
    # they don't collide with the ``close`` column in wilder_input /
    # ema_chain_* / etc.
    # The output column names (ma5/ma10/ma20/ma60) are fixed by the
    # ETFIndicator schema, but the lookback windows come from the market
    # config so crypto can use 7/14/30/90 calendar-day windows.
    ma_labels = ("ma5", "ma10", "ma20", "ma60")
    ma_frags = ",\n            ".join(
        f"AVG(b.qfq_close) OVER (PARTITION BY b.etf_code ORDER BY b.trade_date "
        f"ROWS BETWEEN {w - 1} PRECEDING AND CURRENT ROW) AS {col}"
        for col, w in zip(ma_labels, config.ma_windows)
    )
    # Period returns on 前复权 close. PostgreSQL's GREATEST/LEAST skip
    # NULL arguments, so clamping ``LAG(...)`` inline would turn a
    # missing lookback (history shorter than the window) into the
    # -1e9 lower bound instead of NULL. The lagged close per window is
    # materialized once in the ``lagged`` CTE below and the ratio is
    # gated with an explicit NULL / non-positive check, matching the
    # pandas path which emits NaN (-> NULL) for the same warmup rows.
    lag_frags = ",\n            ".join(
        f"LAG(b.qfq_close, {n}) OVER w_etf AS prev_qfq_{col.removeprefix('return_')}"
        for col, n in config.return_windows.items()
    )
    return_frags = ",\n            ".join(
        f"CASE WHEN b.prev_qfq_{col.removeprefix('return_')} IS NULL "
        f"OR b.prev_qfq_{col.removeprefix('return_')} <= 0 THEN NULL "
        f"ELSE LEAST(GREATEST(b.qfq_close / b.prev_qfq_{col.removeprefix('return_')} - 1, "
        f"-{RETURN_CLAMP}), {RETURN_CLAMP}) END AS {col}"
        for col in config.return_windows
    )

    # Filter: latest-only vs. full-history
    history_filter = "" if full_history else "WHERE rn = bar_count"

    # Long-window gate: max_drawdown_1y / sharpe_1y are only emitted
    # once the trailing long window has at least ``risk_long_min_periods``
    # non-null observations, matching the pandas
    # rolling(window=long_window, min_periods=risk_long_min_periods) threshold.
    long_window = config.risk_long_window
    long_window_min_rn = config.risk_long_min_periods
    annualization_factor = config.annualization_factor

    sql = f"""
    WITH RECURSIVE
    {windowed_cte},
    {_bars_select_sql},
    lagged AS (
        SELECT
            b.*,
            -- Lagged 前复权 close per return window, materialized here
            -- so the return CASE expressions in per_row can test for
            -- NULL before applying the GREATEST/LEAST clamp.
            {lag_frags}
        FROM bars b
        WINDOW w_etf AS (PARTITION BY b.etf_code ORDER BY b.trade_date)
    ),
    wilder_input AS (
        SELECT
            b.etf_code, b.trade_date, b.rn, b.qfq_close, b.high, b.low,
            b.prev_qfq_close,
            GREATEST(b.high - b.low,
                     ABS(b.high - b.prev_qfq_close),
                     ABS(b.low  - b.prev_qfq_close))    AS tr_value,
            CASE WHEN (b.qfq_close - b.prev_qfq_close) > 0
                 THEN b.qfq_close - b.prev_qfq_close ELSE 0 END AS gain_value,
            CASE WHEN (b.qfq_close - b.prev_qfq_close) < 0
                 THEN -(b.qfq_close - b.prev_qfq_close) ELSE 0 END AS loss_value
        FROM bars b
        WHERE b.prev_qfq_close IS NOT NULL
    ),
    {wilder_atr_chain},
    atr_out AS (
        SELECT
            b.etf_code, b.rn,
            CASE
              WHEN b.rn < {atr_window} THEN
                AVG(w.tr_value) OVER (PARTITION BY b.etf_code ORDER BY b.trade_date
                                      ROWS BETWEEN {atr_window - 1} PRECEDING AND CURRENT ROW)
              ELSE wc.wilder_value
            END AS atr14
        FROM bars b
        JOIN wilder_input w ON b.etf_code = w.etf_code AND b.rn = w.rn
        LEFT JOIN wilder_atr_chain wc
          ON b.etf_code = wc.etf_code AND b.rn = wc.rn
    ),
    {wilder_gain_chain},
    {wilder_loss_chain},
    rsi_out AS (
        SELECT
            g.etf_code, g.trade_date, g.rn,
            -- pandas' calc_rsi uses ``ewm(min_periods=rsi_window)`` so the
            -- first rsi_window-1 rows are NaN. The pandas code then
            -- replaces NaN with 0 / 100 via the avg_gain / avg_loss
            -- guards. Match that behaviour here so the SQL path
            -- produces the same warmup values as the pandas path.
            CASE
                WHEN g.rn < {rsi_window} THEN 0.0
                WHEN l.wilder_value IS NULL OR g.wilder_value IS NULL THEN NULL::numeric
                WHEN l.wilder_value = 0 AND g.wilder_value > 0 THEN 100.0
                WHEN g.wilder_value = 0 AND l.wilder_value > 0 THEN 0.0
                ELSE 100.0 - (100.0 / (1.0 + g.wilder_value / NULLIF(l.wilder_value, 0)))
            END AS rsi14
        FROM wilder_gain_chain g
        JOIN wilder_loss_chain l USING (etf_code, rn, trade_date)
    ),
    {ema_fast},
    {ema_slow},
    {macd_dif_cte},
    {macd_signal_chain},
    macd_out AS (
        SELECT
            d.etf_code, d.trade_date, d.rn,
            d.dif AS macd_dif,
            CASE
              WHEN d.rn < {MACD_SIGNAL} THEN
                AVG(d.dif) OVER (PARTITION BY d.etf_code ORDER BY d.trade_date
                                 ROWS BETWEEN {MACD_SIGNAL - 1} PRECEDING AND CURRENT ROW)
              ELSE ms.wilder_value
            END AS macd_dea
        FROM macd_dif d
        LEFT JOIN macd_signal_chain ms
          ON d.etf_code = ms.etf_code AND d.rn = ms.rn
    ),
    per_row AS (
        SELECT
            b.etf_code,
            b.trade_date,
            b.rn,
            b.bar_count,
            b.qfq_close,
            b.amount,
            b.daily_return,
            -- Moving averages on 前复权 close
            {ma_frags},
            -- Bollinger Bands on 前复权 close
            AVG(b.qfq_close) OVER (PARTITION BY b.etf_code ORDER BY b.trade_date
                                   ROWS BETWEEN {bb_window - 1} PRECEDING AND CURRENT ROW) AS bb_ma,
            STDDEV_SAMP(b.qfq_close) OVER (PARTITION BY b.etf_code ORDER BY b.trade_date
                                           ROWS BETWEEN {bb_window - 1} PRECEDING AND CURRENT ROW) AS bb_std,
            -- Period returns on 前复权 close (matches pandas path)
            {return_frags},
            -- Rolling max 前复权 close over the long risk window (used for max_drawdown).
            -- pandas calc_max_drawdown is computed on qfq_close so
            -- long-window stats stay comparable across dividends / splits.
            MAX(b.qfq_close) OVER (PARTITION BY b.etf_code ORDER BY b.trade_date
                                   ROWS BETWEEN {long_window - 1} PRECEDING AND CURRENT ROW) AS rolling_max_close,
            -- Per-row drawdown on 前复权 close (used for max_drawdown).
            (b.qfq_close / NULLIF(MAX(b.qfq_close) OVER (PARTITION BY b.etf_code ORDER BY b.trade_date
                              ROWS BETWEEN {long_window - 1} PRECEDING AND CURRENT ROW), 0) - 1) AS drawdown_row,
            -- ATR / RSI / MACD joins
            atr.atr14,
            rsi.rsi14,
            macd.macd_dif,
            macd.macd_dea,
            -- Volatility 20d / 60d on 前复权 close returns (matches risk.calculate_risk_indicators)
            CASE
                WHEN COUNT(b.daily_return) OVER (PARTITION BY b.etf_code ORDER BY b.trade_date
                    ROWS BETWEEN {VOL_SHORT_WINDOW - 1} PRECEDING AND CURRENT ROW) >= 5
                THEN STDDEV_SAMP(b.daily_return) OVER (PARTITION BY b.etf_code ORDER BY b.trade_date
                    ROWS BETWEEN {VOL_SHORT_WINDOW - 1} PRECEDING AND CURRENT ROW)
                ELSE NULL
            END * sqrt({annualization_factor}) AS volatility_20d,
            CASE
                WHEN COUNT(b.daily_return) OVER (PARTITION BY b.etf_code ORDER BY b.trade_date
                    ROWS BETWEEN {VOL_LONG_WINDOW - 1} PRECEDING AND CURRENT ROW) >= 10
                THEN STDDEV_SAMP(b.daily_return) OVER (PARTITION BY b.etf_code ORDER BY b.trade_date
                    ROWS BETWEEN {VOL_LONG_WINDOW - 1} PRECEDING AND CURRENT ROW)
                ELSE NULL
            END * sqrt({annualization_factor}) AS volatility_60d,
            -- Sharpe 1y on 前复权 close returns
            (AVG(b.daily_return) OVER (PARTITION BY b.etf_code ORDER BY b.trade_date
                ROWS BETWEEN {long_window - 1} PRECEDING AND CURRENT ROW)
                - {RISK_FREE_RATE} / {annualization_factor})
            / NULLIF(STDDEV_SAMP(b.daily_return) OVER (PARTITION BY b.etf_code ORDER BY b.trade_date
                ROWS BETWEEN {long_window - 1} PRECEDING AND CURRENT ROW), 0)
            * sqrt({annualization_factor}) AS sharpe_1y_raw
        FROM lagged b
        LEFT JOIN wilder_input w ON b.etf_code = w.etf_code AND b.rn = w.rn
        LEFT JOIN atr_out atr ON b.etf_code = atr.etf_code AND b.rn = atr.rn
        LEFT JOIN rsi_out rsi ON b.etf_code = rsi.etf_code AND b.rn = rsi.rn
        LEFT JOIN macd_out macd ON b.etf_code = macd.etf_code AND b.rn = macd.rn
        WINDOW w_etf AS (PARTITION BY b.etf_code ORDER BY b.trade_date)
    ),
    enriched AS (
        SELECT
            pr.*,
            -- Max drawdown_1y: minimum of drawdown_row within the
            -- long-window. Matches pandas calc_max_drawdown
            -- (cummax within window then min of (close/cummax - 1)).
            MIN(pr.drawdown_row) OVER (PARTITION BY pr.etf_code ORDER BY pr.trade_date
                ROWS BETWEEN {long_window - 1} PRECEDING AND CURRENT ROW) AS max_drawdown_1y_pre
        FROM per_row pr
    )
    SELECT
        etf_code,
        trade_date,
        ma5::double precision,
        ma10::double precision,
        ma20::double precision,
        ma60::double precision,
        (bb_ma + {BB_NUM_STD} * bb_std)::double precision        AS bb_upper,
        (bb_ma - {BB_NUM_STD} * bb_std)::double precision        AS bb_lower,
        atr14::double precision,
        -- COALESCE handles the warmup rows where wilder_gain / loss
        -- chains haven't started yet (rn=1 lacks prev_qfq_close). At
        -- those rows emit 0.0 to match pandas' NaN-replacement behaviour.
        COALESCE(rsi14, CASE WHEN rn < {rsi_window} THEN 0.0 ELSE NULL END)::double precision AS rsi14,
        macd_dif::double precision,
        macd_dea::double precision,
        (macd_dif - macd_dea)::double precision                  AS macd_hist,
        volatility_20d::double precision,
        volatility_60d::double precision,
        CASE
            WHEN rn < {long_window_min_rn} THEN NULL
            ELSE max_drawdown_1y_pre
        END::double precision AS max_drawdown_1y,
        CASE
            WHEN rn < {long_window_min_rn} THEN NULL
            ELSE sharpe_1y_raw
        END::double precision AS sharpe_1y,
        return_1w::double precision,
        return_1m::double precision,
        return_3m::double precision,
        return_6m::double precision,
        return_1y::double precision,
        amount::double precision
    FROM enriched
    {history_filter}
    ORDER BY etf_code, trade_date
    """

    return sql


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def _execute_indicator_query(
    db: Session,
    codes: Iterable[str],
    *,
    full_history: bool,
    target_date: date | None = None,
    config: object | None = None,
    market: str = "A股",
) -> list[dict]:
    """Run the indicator query and return rows as list[dict]."""
    codes_list = list(codes)
    if not codes_list:
        return []

    if config is None:
        config = get_market_config(market)

    # Always bind :target_date so the EXISTS pre-filter and the
    # outer ``b.trade_date <= :target_date`` predicate both have a
    # concrete value. When the caller passes ``None`` we default to
    # today's date — that mirrors the pandas path's "no future-dated
    # bars expected" semantics and matches the EXISTS subquery's
    # COALESCE fallback.
    effective_target = target_date if target_date is not None else date.today()
    target_filter_sql = "AND b.trade_date <= :target_date"
    params: dict = {"codes": codes_list, "target_date": effective_target}

    prefix = codes_list[0][0] if codes_list else None
    if full_history:
        max_bars = None
    else:
        max_bars = max(_get_max_bars_for_prefix(prefix), config.risk_long_window)
    sql = build_indicator_query_sql(
        full_history=full_history,
        target_filter_sql=target_filter_sql,
        max_bars=max_bars,
        config=config,
    )

    stmt = text(sql).bindparams(bindparam("codes", type_=ARRAY(TEXT)))
    stmt = stmt.bindparams(target_date=effective_target)

    logger.info(
        "sql_calculator: running indicator query market=%s codes=%d full_history=%s target=%s max_bars=%s",
        market,
        len(codes_list),
        full_history,
        effective_target,
        max_bars,
    )
    start = time.perf_counter()
    rows: list[dict] = []
    # Use a detached AUTOCOMMIT Core connection for each indicator query.
    # Detaching forces SQLAlchemy to close the underlying DBAPI connection
    # when done instead of returning it to the pool.  This avoids the
    # stalls observed on some Mac + Docker Postgres setups where repeated
    # pool checkouts after hundreds of chunks eventually hang with no
    # server-side activity.
    conn = db.bind.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        # The statement timeout enforces the 600 s per-chunk budget.
        conn.execute(text(f"SET statement_timeout = '{INDICATOR_SQL_STATEMENT_TIMEOUT_MS}'"))
        with conn.execute(stmt, params) as result:
            columns = result.keys()
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
    finally:
        elapsed = time.perf_counter() - start
        conn.detach()
        conn.close()
    logger.info(
        "sql_calculator: indicator query finished codes=%d rows=%d elapsed=%.3fs",
        len(codes_list),
        len(rows),
        elapsed,
    )
    return rows


def sql_calculate_latest(
    db: Session,
    codes: Iterable[str],
    *,
    target_date: date | None = None,
    config: object | None = None,
    market: str = "A股",
) -> list[dict]:
    """Compute the latest indicator row per code.

    Equivalent to the pandas ``batch_calculate_indicators`` path when
    called with ``full_history=False``.
    """
    return _execute_indicator_query(
        db, codes, full_history=False, target_date=target_date, config=config, market=market
    )


def sql_calculate_full_history(
    db: Session,
    codes: Iterable[str],
    *,
    target_date: date | None = None,
    config: object | None = None,
    market: str = "A股",
) -> list[dict]:
    """Compute indicator rows for every (code, trade_date) in the window.

    Equivalent to the pandas path with ``full_history=True``.
    """
    return _execute_indicator_query(
        db, codes, full_history=True, target_date=target_date, config=config, market=market
    )


# Return / drawdown columns widened to DECIMAL(18, 6).  Used to clamp
# SQL result values before binding, mirroring the pandas path defence.
_RETURN_DRAWDOWN_COLUMNS: dict[str, tuple[int, int]] = {
    "max_drawdown_1y": (18, 6),
    "return_1w": (18, 6),
    "return_1m": (18, 6),
    "return_3m": (18, 6),
    "return_6m": (18, 6),
    "return_1y": (18, 6),
}


def _clamp_decimal(value: float, precision: int | None, scale: int | None) -> float:
    """把 float 截断到 DECIMAL(precision, scale) 可表达的范围.

    当 precision / scale 为 None 时直接原值返回。最大可表示绝对值为
    ``10^(precision - scale) - 10^(-scale)``；超出时返回边界值，避免
    upsert 阶段触发 numeric field overflow。
    """
    if precision is None or scale is None:
        return value
    max_val = 10 ** (precision - scale) - 10 ** (-scale)
    if value > max_val:
        return max_val
    if value < -max_val:
        return -max_val
    return value


# Data-quality gate for period returns. No legitimate 1w/1m/3m/6m/1y
# return can reach 1e8 (100 亿倍); values at this magnitude are the
# -1e9 sentinel produced by the pre-fix GREATEST/LEAST clamp bug (or
# future dirty rows). ``build_indicator_payload`` coerces them to None
# so they never reach the upsert / aggregation layers again.
_RETURN_ABS_GUARD: float = 1e8


def build_indicator_payload(row: dict) -> dict:
    """Coerce a SQL result row to the ETFIndicator upsert shape.

    NaN/inf become ``None`` so SQLAlchemy binds them as NULL instead
    of failing the numeric column constraint. Return / drawdown
    columns are clamped to DECIMAL(18, 6) to prevent a single extreme
    value (e.g. 600601.SH style returns) from failing the whole chunk.
    ``return_*`` values with absolute magnitude >= 1e8 are treated as
    corrupt sentinels, logged, and coerced to ``None``.
    """
    record: dict = {
        "etf_code": row["etf_code"],
        "trade_date": row["trade_date"],
    }
    for col in INDICATOR_OUTPUT_COLUMNS:
        value = row.get(col)
        if value is None:
            record[col] = None
            continue
        try:
            f = float(value)
        except (TypeError, ValueError):
            record[col] = None
            continue
        if pd.isna(f) or f == float("inf") or f == float("-inf"):
            record[col] = None
        elif col.startswith("return_") and abs(f) >= _RETURN_ABS_GUARD:
            logger.warning(
                "build_indicator_payload: dropping implausible %s=%r for %s on %s "
                "(|return| >= %g sentinel guard)",
                col,
                f,
                row.get("etf_code"),
                row.get("trade_date"),
                _RETURN_ABS_GUARD,
            )
            record[col] = None
        else:
            record[col] = _clamp_decimal(f, *_RETURN_DRAWDOWN_COLUMNS.get(col, (None, None)))
    return record


__all__ = [
    "sql_calculate_latest",
    "sql_calculate_full_history",
    "build_indicator_payload",
    "INDICATOR_OUTPUT_COLUMNS",
    "build_indicator_query_sql",
]
