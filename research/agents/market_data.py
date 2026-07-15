"""Market data collector.

Uses akshare for A-share market/regime snapshots.
"""

import logging
from pathlib import Path

import akshare as ak

from research.agents.base import save_raw, save_note

logger = logging.getLogger("research.agents.market_data")


def _safe_ak(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("akshare call failed: %s", exc)
        return None


def _try_index_spot():
    """akshare has several index-spot function names across versions."""
    for name in ("index_zh_a_spot", "stock_zh_index_spot_em", "stock_zh_index_spot"):
        fn = getattr(ak, name, None)
        if fn:
            df = _safe_ak(fn)
            if df is not None:
                return df
    return None


def run_market_data_agent(data_dir: str, agent_name: str = "market_data") -> None:
    logging.basicConfig(level=logging.INFO)
    root = Path(data_dir)
    logger.info("Starting %s agent", agent_name)

    snapshots = {}

    df = _try_index_spot()
    if df is not None:
        snapshots["a_share_indices"] = df.head(20).to_dict(orient="records")

    df = _safe_ak(ak.stock_sector_fund_flow_rank, sector_type="行业资金流", indicator="今日")
    if df is not None:
        snapshots["sector_fund_flow"] = df.head(20).to_dict(orient="records")

    df = _safe_ak(ak.stock_market_fund_flow)
    if df is not None:
        snapshots["market_fund_flow"] = df.to_dict(orient="records")

    df = _safe_ak(ak.stock_individual_fund_flow_rank, indicator="今日")
    if df is not None:
        snapshots["individual_fund_flow_top20"] = df.head(20).to_dict(orient="records")

    save_raw(root, agent_name, "market_snapshots", snapshots)

    notes = []
    if "a_share_indices" in snapshots:
        notes.append("## A股主要指数\n" + "\n".join(
            f"- {it.get('名称', it.get('code', '?'))}: {it.get('最新价', it.get('close', 'N/A'))}"
            for it in snapshots["a_share_indices"][:10]
        ))
    if "sector_fund_flow" in snapshots:
        notes.append("## 行业资金流 Top10\n" + "\n".join(
            f"- {it.get('名称', '?')}: 主力净流入 {it.get('主力净流入-净额', 'N/A')}"
            for it in snapshots["sector_fund_flow"][:10]
        ))
    if notes:
        save_note(root, agent_name, "A股市场快照", "\n\n".join(notes))

    logger.info("%s agent finished", agent_name)
