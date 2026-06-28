#!/usr/bin/env python3
"""Comprehensive database consistency check for AD-Research."""

import sys

sys.path.insert(0, "/Users/aidanliu/Documents/vibe-trading/etf-research-platform")

from sqlalchemy import func, text

from app.core.database import SessionLocal, engine
from app.models.etf import ETFDailyBar, ETFIndicator, ETFInfo
from app.models.etl import BacktestResult, Signal, StrategyConfig
from app.models.pool import ETFPools, PoolMember, PoolSnapshot, PoolWeight
from app.models.scoring import ETFScore, ReportMetadata, ScoreTemplate


def check_1_orphaned_scores(db):
    """ETF in etf_score that doesn't exist in etf_info."""
    print("=" * 70)
    print("CHECK 1: Orphaned ETF scores (etf_score -> etf_info)")
    print("-" * 70)
    result = db.query(ETFScore.etf_code).outerjoin(
        ETFInfo, ETFScore.etf_code == ETFInfo.code
    ).filter(ETFInfo.code.is_(None)).distinct().all()
    if result:
        codes = [r[0] for r in result]
        print(f"  FAIL: {len(codes)} orphaned etf_score records")
        print(f"  Orphaned ETF codes: {codes}")
        count = db.query(func.count(ETFScore.id)).filter(ETFScore.etf_code.in_(codes)).scalar()
        print(f"  Total orphaned score rows: {count}")
    else:
        print("  PASS: All etf_score records reference valid etf_info")
    return len(result)


def check_2_orphaned_indicators(db):
    """ETF in etf_indicator that doesn't exist in etf_info."""
    print("\n" + "=" * 70)
    print("CHECK 2: Orphaned ETF indicators (etf_indicator -> etf_info)")
    print("-" * 70)
    result = db.query(ETFIndicator.etf_code).outerjoin(
        ETFInfo, ETFIndicator.etf_code == ETFInfo.code
    ).filter(ETFInfo.code.is_(None)).distinct().all()
    if result:
        codes = [r[0] for r in result]
        print(f"  FAIL: {len(codes)} orphaned etf_indicator records")
        print(f"  Orphaned ETF codes: {codes}")
        count = db.query(func.count(ETFIndicator.id)).filter(ETFIndicator.etf_code.in_(codes)).scalar()
        print(f"  Total orphaned indicator rows: {count}")
    else:
        print("  PASS: All etf_indicator records reference valid etf_info")
    return len(result)


def check_3_orphaned_pool_members(db):
    """PoolMember referencing non-existent etf_code."""
    print("\n" + "=" * 70)
    print("CHECK 3: Orphaned pool members (pool_member -> etf_info)")
    print("-" * 70)
    result = db.query(PoolMember.etf_code).outerjoin(
        ETFInfo, PoolMember.etf_code == ETFInfo.code
    ).filter(ETFInfo.code.is_(None)).distinct().all()
    if result:
        codes = [r[0] for r in result]
        print(f"  FAIL: {len(codes)} orphaned pool_member records")
        print(f"  Orphaned ETF codes: {codes}")
        count = db.query(func.count(PoolMember.id)).filter(PoolMember.etf_code.in_(codes)).scalar()
        print(f"  Total orphaned pool_member rows: {count}")
    else:
        print("  PASS: All pool_member records reference valid etf_info")
    return len(result)


def check_4_orphaned_backtests(db):
    """BacktestResult referencing non-existent strategy_id."""
    print("\n" + "=" * 70)
    print("CHECK 4: Orphaned backtest results (backtest_result -> strategy_config)")
    print("-" * 70)
    result = db.query(BacktestResult.strategy_id).outerjoin(
        StrategyConfig, BacktestResult.strategy_id == StrategyConfig.id
    ).filter(StrategyConfig.id.is_(None)).distinct().all()
    if result:
        ids = [r[0] for r in result]
        print(f"  FAIL: {len(ids)} orphaned backtest_result records")
        print(f"  Orphaned strategy IDs: {ids}")
        count = db.query(func.count(BacktestResult.id)).filter(BacktestResult.strategy_id.in_(ids)).scalar()
        print(f"  Total orphaned backtest rows: {count}")
    else:
        print("  PASS: All backtest_result records reference valid strategy_config")
    return len(result)


def check_5_orphaned_signals(db):
    """Signal referencing non-existent strategy_id or etf_code."""
    print("\n" + "=" * 70)
    print("CHECK 5: Orphaned signals (signal -> strategy_config + etf_info)")
    print("-" * 70)

    # Check strategy_id
    bad_strategy = db.query(Signal.strategy_id).outerjoin(
        StrategyConfig, Signal.strategy_id == StrategyConfig.id
    ).filter(StrategyConfig.id.is_(None)).distinct().all()

    # Check etf_code
    bad_etf = db.query(Signal.etf_code).outerjoin(
        ETFInfo, Signal.etf_code == ETFInfo.code
    ).filter(ETFInfo.code.is_(None)).distinct().all()

    issues = 0
    if bad_strategy:
        ids = [r[0] for r in bad_strategy]
        print(f"  FAIL: {len(ids)} signals with invalid strategy_id")
        print(f"  Invalid strategy IDs: {ids}")
        count = db.query(func.count(Signal.id)).filter(Signal.strategy_id.in_(ids)).scalar()
        print(f"  Total affected signal rows: {count}")
        issues += len(ids)
    else:
        print("  PASS: All signals reference valid strategy_config")

    if bad_etf:
        codes = [r[0] for r in bad_etf]
        print(f"  FAIL: {len(codes)} signals with invalid etf_code")
        print(f"  Invalid ETF codes: {codes}")
        count = db.query(func.count(Signal.id)).filter(Signal.etf_code.in_(codes)).scalar()
        print(f"  Total affected signal rows: {count}")
        issues += len(codes)
    else:
        print("  PASS: All signals reference valid etf_info")

    return issues


def check_6_active_vs_daily_bars(db):
    """Count active etf_info vs those with daily bars."""
    print("\n" + "=" * 70)
    print("CHECK 6: Active ETFs vs ETFs with daily bars")
    print("-" * 70)

    total_etfs = db.query(func.count(ETFInfo.code)).scalar()
    active_etfs = db.query(func.count(ETFInfo.code)).filter(ETFInfo.status == "active").scalar()
    inactive_etfs = db.query(func.count(ETFInfo.code)).filter(ETFInfo.status != "active").filter(ETFInfo.status.isnot(None)).scalar()
    null_status = db.query(func.count(ETFInfo.code)).filter(ETFInfo.status.is_(None)).scalar()

    etfs_with_bars = db.query(ETFDailyBar.etf_code).distinct().count()
    active_with_bars = db.query(ETFDailyBar.etf_code).filter(
        ETFDailyBar.etf_code.in_(
            db.query(ETFInfo.code).filter(ETFInfo.status == "active")
        )
    ).distinct().count()

    active_without_bars = active_etfs - active_with_bars

    print(f"  Total ETFs in etf_info:     {total_etfs}")
    print(f"  Active ETFs:                {active_etfs}")
    print(f"  Inactive ETFs:              {inactive_etfs}")
    print(f"  NULL status ETFs:           {null_status}")
    print(f"  ETFs with daily bars:       {etfs_with_bars}")
    print(f"  Active ETFs with bars:      {active_with_bars}")
    print(f"  Active ETFs WITHOUT bars:   {active_without_bars}")

    if active_without_bars > 0:
        print(f"\n  WARNING: {active_without_bars} active ETFs have no daily bar data")
        missing = db.query(ETFInfo.code, ETFInfo.name).filter(
            ETFInfo.status == "active"
        ).filter(
            ~ETFInfo.code.in_(db.query(ETFDailyBar.etf_code).distinct())
        ).limit(20).all()
        for code, name in missing:
            print(f"    - {code}: {name}")
    else:
        print("  PASS: All active ETFs have daily bar data")

    return active_without_bars


def check_7_latest_dates(db):
    """Check latest dates across all tables for consistency."""
    print("\n" + "=" * 70)
    print("CHECK 7: Latest dates across all tables")
    print("-" * 70)

    tables_with_dates = [
        ("etf_daily_bar", "trade_date"),
        ("etf_indicator", "trade_date"),
        ("etf_score", "trade_date"),
        ("etf_scan_log", "scan_date"),
        ("backtest_result", "end_date"),
        ("signal", "trade_date"),
        ("pool_snapshot", "snapshot_date"),
        ("report_metadata", "report_date"),
    ]

    results = {}
    for table, col in tables_with_dates:
        try:
            result = db.execute(text(f"SELECT MAX({col}) FROM {table}")).scalar()
            results[table] = result
            print(f"  {table:.<30} {col:.<15} {result}")
        except Exception as e:
            print(f"  {table:.<30} {col:.<15} ERROR: {e}")
            results[table] = None

    # Check for date gaps
    dates = {k: v for k, v in results.items() if v is not None}
    if dates:
        max_date = max(dates.values())
        min_date = min(dates.values())
        print(f"\n  Latest date overall:  {max_date}")
        print(f"  Earliest max date:    {min_date}")
        if max_date != min_date:
            print("  WARNING: Date inconsistency detected across tables")
            for table, date in sorted(dates.items(), key=lambda x: x[1], reverse=True):
                gap = (max_date - date).days if hasattr(max_date, 'days') or hasattr(date, '__sub__') else "N/A"
                print(f"    {table}: {date} (gap: {gap} days)")
        else:
            print("  PASS: All tables have consistent latest dates")

    return results


def check_8_null_critical_columns(db):
    """Check for NULL values in critical columns."""
    print("\n" + "=" * 70)
    print("CHECK 8: NULL values in critical columns")
    print("-" * 70)

    checks = [
        ("etf_info", "code", "PRIMARY KEY"),
        ("etf_info", "name", "NOT NULL"),
        ("etf_info", "status", "has default"),
        ("etf_daily_bar", "etf_code", "PRIMARY KEY"),
        ("etf_daily_bar", "trade_date", "PRIMARY KEY"),
        ("etf_daily_bar", "close", "price data"),
        ("etf_indicator", "etf_code", "NOT NULL FK"),
        ("etf_indicator", "trade_date", "NOT NULL"),
        ("etf_score", "etf_code", "NOT NULL FK"),
        ("etf_score", "trade_date", "NOT NULL"),
        ("etf_score", "template_id", "NOT NULL FK"),
        ("pool_member", "pool_id", "NOT NULL FK"),
        ("pool_member", "etf_code", "NOT NULL FK"),
        ("pool_weight", "pool_id", "NOT NULL FK"),
        ("pool_weight", "etf_code", "NOT NULL FK"),
        ("pool_weight", "weight_source", "NOT NULL"),
        ("backtest_result", "strategy_id", "NOT NULL FK"),
        ("signal", "strategy_id", "NOT NULL FK"),
        ("signal", "etf_code", "NOT NULL FK"),
        ("signal", "trade_date", "NOT NULL"),
        ("signal", "signal_type", "NOT NULL"),
        ("strategy_config", "name", "NOT NULL"),
        ("score_template", "name", "NOT NULL"),
        ("score_template", "weights", "NOT NULL"),
        ("etf_pools", "name", "NOT NULL"),
        ("report_metadata", "report_type", "NOT NULL"),
        ("report_metadata", "report_date", "NOT NULL"),
        ("report_metadata", "status", "NOT NULL"),
    ]

    total_issues = 0
    for table, column, constraint in checks:
        try:
            result = db.execute(text(
                f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL"
            )).scalar()
            if result and result > 0:
                print(f"  FAIL: {table}.{column} has {result} NULL values ({constraint})")
                total_issues += result
            else:
                print(f"  PASS: {table}.{column} - no NULLs ({constraint})")
        except Exception as e:
            print(f"  SKIP: {table}.{column} - {e}")

    return total_issues


def check_extra(db):
    """Additional consistency checks."""
    print("\n" + "=" * 70)
    print("EXTRA CHECKS")
    print("-" * 70)

    # Pool weights referencing non-existent ETFs
    print("\n  Pool weights -> ETFInfo:")
    bad = db.query(PoolWeight.etf_code).outerjoin(
        ETFInfo, PoolWeight.etf_code == ETFInfo.code
    ).filter(ETFInfo.code.is_(None)).distinct().all()
    if bad:
        print(f"    FAIL: {len(bad)} pool_weight records with invalid etf_code: {[r[0] for r in bad]}")
    else:
        print("    PASS: All pool_weight records reference valid etf_info")

    # Report metadata referencing non-existent pools
    print("\n  Report metadata -> ETF Pools:")
    bad = db.query(ReportMetadata.pool_id).outerjoin(
        ETFPools, ReportMetadata.pool_id == ETFPools.id
    ).filter(ETFPools.id.is_(None)).filter(ReportMetadata.pool_id.isnot(None)).distinct().all()
    if bad:
        print(f"    FAIL: {len(bad)} report_metadata records with invalid pool_id: {[r[0] for r in bad]}")
    else:
        print("    PASS: All report_metadata records reference valid etf_pools (or NULL)")

    # Score template references
    print("\n  ETF Score -> Score Template:")
    bad = db.query(ETFScore.template_id).outerjoin(
        ScoreTemplate, ETFScore.template_id == ScoreTemplate.id
    ).filter(ScoreTemplate.id.is_(None)).distinct().all()
    if bad:
        print(f"    FAIL: {len(bad)} etf_score records with invalid template_id: {[r[0] for r in bad]}")
    else:
        print("    PASS: All etf_score records reference valid score_template")

    # Pool snapshot -> pool
    print("\n  Pool Snapshot -> ETF Pools:")
    bad = db.query(PoolSnapshot.pool_id).outerjoin(
        ETFPools, PoolSnapshot.pool_id == ETFPools.id
    ).filter(ETFPools.id.is_(None)).distinct().all()
    if bad:
        print(f"    FAIL: {len(bad)} pool_snapshot records with invalid pool_id: {[r[0] for r in bad]}")
    else:
        print("    PASS: All pool_snapshot records reference valid etf_pools")

    # Duplicate ETF codes in etf_info
    print("\n  Duplicate ETF codes in etf_info:")
    dupes = db.query(ETFInfo.code, func.count(ETFInfo.code)).group_by(ETFInfo.code).having(func.count(ETFInfo.code) > 1).all()
    if dupes:
        print(f"    FAIL: {len(dupes)} duplicate ETF codes found: {dupes}")
    else:
        print("    PASS: No duplicate ETF codes in etf_info")

    # Row counts per table
    print("\n  Row counts per table:")
    tables = [
        "etf_info", "etf_daily_bar", "etf_indicator", "etf_score",
        "score_template", "etf_pools", "pool_member", "pool_weight",
        "pool_snapshot", "strategy_config", "backtest_result", "signal",
        "etf_scan_log", "etl_log", "report_metadata", "data_source_config",
        "notification_config", "notification_log", "fx_rate"
    ]
    for t in tables:
        try:
            count = db.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"    {t:.<35} {count:>10,}")
        except Exception as e:
            print(f"    {t:.<35} ERROR: {e}")


def main():
    print("=" * 70)
    print("AD-RESEARCH - DATABASE CONSISTENCY CHECK")
    print(f"Database: {engine.url}")
    print("=" * 70)

    db = SessionLocal()
    try:
        issues = []
        issues.append(("Orphaned ETF scores", check_1_orphaned_scores(db)))
        issues.append(("Orphaned ETF indicators", check_2_orphaned_indicators(db)))
        issues.append(("Orphaned pool members", check_3_orphaned_pool_members(db)))
        issues.append(("Orphaned backtest results", check_4_orphaned_backtests(db)))
        issues.append(("Orphaned signals", check_5_orphaned_signals(db)))
        issues.append(("Active ETFs without daily bars", check_6_active_vs_daily_bars(db)))
        check_7_latest_dates(db)
        issues.append(("NULL critical columns", check_8_null_critical_columns(db)))
        check_extra(db)

        print("\n" + "=" * 70)
        print("SUMMARY")
        print("-" * 70)
        total_issues = 0
        for name, count in issues:
            status = "PASS" if count == 0 else f"FAIL ({count})"
            print(f"  {name:.<50} {status}")
            total_issues += count
        print("-" * 70)
        if total_issues == 0:
            print("  ALL CHECKS PASSED - Database is consistent")
        else:
            print(f"  TOTAL ISSUES FOUND: {total_issues}")
        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    main()
