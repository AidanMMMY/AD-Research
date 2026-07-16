"""Strategy parameter optimization engine.

Provides a brute-force ``itertools.product`` grid-search over the cartesian
product of param-value lists and surfaces the Pareto-optimal set sorted
by Sharpe ratio.

Public API:

- :func:`grid_search` — Run the full sweep and return one dict per
  candidate.
- :func:`pareto_top_n` — Reduce the sweep to the top-N (default 10)
  candidates sorted by Sharpe, with total_return as the tie-breaker.

The optimization engine is intentionally narrow. It exists to fill the
"parameter sweep" gap left by the existing ``run_walk_forward`` path
(which already does an internal grid search per fold but does not expose
the candidates). Adding a focused entry point makes it possible to
admin/research notebooks to ask "what were the best param combinations
for this strategy on this window?" without redeploying the engine.
"""

from __future__ import annotations

from datetime import date
from itertools import product
from typing import Any

from app.services.backtest_engine import run_backtest


def grid_search(
    strategy_type: str,
    base_params: dict[str, Any],
    grid: dict[str, list[Any]],
    start_date: date,
    end_date: date,
    *,
    etf_code: str | None = None,
    etf_codes: list[str] | None = None,
    initial_capital: float = 100000.0,
    commission_rate: float = 0.001,
    slippage_rate: float = 0.001,
    position_size: float = 1.0,
    risk_free_rate: float = 0.02,
    db: Any | None = None,
    execution_price_model: str = "open",
    market: str = "cn_a",
    apply_friction: bool = True,
) -> list[dict[str, Any]]:
    """Run a cartesian-product grid search across ``grid`` for ``strategy_type``.

    Each combination is a separate ``run_backtest`` invocation; failed
    candidates are captured as ``{"error": str(exc)}`` entries and
    skipped. The result list is sorted by Sharpe descending, with
    ``total_return`` used as a tie-breaker (matching the walk-forward
    selection rule).

    Args:
        strategy_type: Strategy identifier (must exist in
            ``StrategyRegistry``).
        base_params: Base parameter dict; per-candidate grid values are
            merged on top.
        grid: Mapping of ``param_name -> [v1, v2, ...]``. Any param not
            in ``grid`` inherits from ``base_params``.
        start_date: Inclusive backtest start.
        end_date: Inclusive backtest end.
        etf_code: Single-instrument backtest (default).
        etf_codes: Multi-instrument backtest. When provided, takes
            precedence over ``etf_code``.
        initial_capital: Starting capital, default ``100000``.
        commission_rate: Per-side commission rate.
        slippage_rate: Per-side slippage rate.
        position_size: Position-size ratio in [0, 1].
        risk_free_rate: Annualised risk-free rate for Sharpe.
        db: Optional SQLAlchemy session forwarded to ``run_backtest``.
        execution_price_model: Forwarded to ``run_backtest``.
        market: Forwarded to ``run_backtest``.
        apply_friction: Forwarded to ``run_backtest``.

    Returns:
        List of ``{"params": {...}, "metrics": {...}}`` dicts, one per
        successful candidate. Empty list on input failure.
    """
    if not grid:
        # Degenerate case — no grid means we just run the base params once.
        keys: list[str] = []
        value_lists: list[list[Any]] = []
    else:
        keys = list(grid.keys())
        value_lists = [list(v) for v in (grid[k] for k in keys)]

    # Materialize the cartesian product once so we can pre-size the list.
    combinations = list(product(*value_lists))

    results: list[dict[str, Any]] = []
    for combo in combinations:
        merged = dict(base_params)
        for k, v in zip(keys, combo):
            merged[k] = v

        try:
            outcome = run_backtest(
                strategy_type=strategy_type,
                params=merged,
                start_date=start_date,
                end_date=end_date,
                etf_code=etf_code or "",
                etf_codes=etf_codes,
                initial_capital=initial_capital,
                commission_rate=commission_rate,
                slippage_rate=slippage_rate,
                position_size=position_size,
                risk_free_rate=risk_free_rate,
                db=db,
                execution_price_model=execution_price_model,
                market=market,
                apply_friction=apply_friction,
            )
        except Exception as exc:  # noqa: BLE001 — grid must keep going
            results.append({"params": merged, "error": str(exc)})
            continue

        # ``run_backtest`` returns ``metrics`` either populated with the
        # run, or ``{"error": "no_data"}`` when no bars could be loaded.
        # Both paths should be surface-able to the caller.
        results.append({
            "params": merged,
            "metrics": outcome.metrics or {},
            "trade_count": len(outcome.trades or []),
        })

    results = _sort_by_sharpe(results)
    return results


def pareto_top_n(
    results: list[dict[str, Any]],
    n: int = 10,
    *,
    sort_key: str = "sharpe_ratio",
) -> list[dict[str, Any]]:
    """Reduce a grid-search result list to the top-N Pareto-optimal set.

    "Pareto-optimal" here is the simpler single-objective variant: we
    rank by ``sort_key`` (default ``sharpe_ratio``) descending, with
    ``total_return`` as the tie-breaker. Failure entries
    (``"error" in row``) are dropped.

    Args:
        results: Output of :func:`grid_search`.
        n: Top-N slice. Defaults to 10.
        sort_key: Metric to rank by. Must be a numeric key in
            ``metrics`` (default ``sharpe_ratio``).

    Returns:
        A list of up to ``n`` rows.
    """
    if n <= 0:
        return []

    successful = [r for r in results if "error" not in r and r.get("metrics")]
    if not successful:
        return []

    def _score(row: dict[str, Any]) -> tuple[float, float]:
        metrics = row.get("metrics") or {}
        primary = float(metrics.get(sort_key) or 0.0)
        tiebreak = float(metrics.get("total_return") or 0.0)
        return (primary, tiebreak)

    sorted_rows = sorted(successful, key=_score, reverse=True)
    return sorted_rows[:n]


def _sort_by_sharpe(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable sort by sharpe_ratio desc, total_return desc.

    Failure rows are pushed to the end but kept so the caller can still
    see them in the full sweep.
    """
    def _key(row: dict[str, Any]) -> tuple[int, float, float]:
        if "error" in row:
            # (bucket=1, sharpe=0, total_return=0) so failures sort last
            return (1, 0.0, 0.0)
        metrics = row.get("metrics") or {}
        sharpe = float(metrics.get("sharpe_ratio") or 0.0)
        total_return = float(metrics.get("total_return") or 0.0)
        return (0, sharpe, total_return)

    return sorted(results, key=_key, reverse=True)
