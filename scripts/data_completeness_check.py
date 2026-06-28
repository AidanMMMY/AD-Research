#!/usr/bin/env python3
"""Comprehensive data completeness check for AD-Research."""

import sys
from collections import Counter
from datetime import date

sys.path.insert(0, "/Users/aidanliu/Documents/vibe-trading/etf-research-platform")

from sqlalchemy import func, text

from app.core.calendar import get_trading_dates
from app.core.database import SessionLocal
from app.models.etf import ETFDailyBar, ETFIndicator, ETFInfo
from app.models.etf_scan_log import ETFScanLog
from app.models.etl import BacktestResult, ETLLog, Signal, StrategyConfig
from app.models.notification import NotificationConfig, NotificationLog
from app.models.pool import ETFPools, PoolMember, PoolSnapshot, PoolWeight
from app.models.scoring import ETFScore, ReportMetadata, ScoreTemplate


def section(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("-" * 70)


def check_basic_counts(db):
    section("一、基础数据量统计")
    counts = {
        "ETF 总数": db.query(func.count(ETFInfo.code)).scalar(),
        "活跃 ETF": db.query(func.count(ETFInfo.code)).filter(ETFInfo.status == "active").scalar(),
        "退市/暂停 ETF": db.query(func.count(ETFInfo.code)).filter(ETFInfo.status != "active").scalar(),
        "日线总条数": db.execute(text("SELECT COUNT(*) FROM etf_daily_bar")).scalar(),
        "指标总条数": db.query(func.count(ETFIndicator.id)).scalar(),
        "评分总条数": db.query(func.count(ETFScore.id)).scalar(),
        "评分模板数": db.query(func.count(ScoreTemplate.id)).scalar(),
        "标的池数": db.query(func.count(ETFPools.id)).scalar(),
        "池成员数": db.query(func.count(PoolMember.id)).scalar(),
        "池权重数": db.query(func.count(PoolWeight.id)).scalar(),
        "池快照数": db.query(func.count(PoolSnapshot.id)).scalar(),
        "策略配置数": db.query(func.count(StrategyConfig.id)).scalar(),
        "回测结果数": db.query(func.count(BacktestResult.id)).scalar(),
        "信号数": db.query(func.count(Signal.id)).scalar(),
        "扫描日志数": db.query(func.count(ETFScanLog.id)).scalar(),
        "ETL 日志数": db.query(func.count(ETLLog.id)).scalar(),
        "报告元数据数": db.query(func.count(ReportMetadata.id)).scalar(),
        "通知配置数": db.query(func.count(NotificationConfig.id)).scalar(),
        "通知日志数": db.query(func.count(NotificationLog.id)).scalar(),
    }
    for k, v in counts.items():
        print(f"  {k:.<30} {v:>10,}")
    return counts


def check_etf_info_completeness(db):
    section("二、ETF 基础信息字段完整性")
    total = db.query(func.count(ETFInfo.code)).scalar()
    fields = ["name", "market", "category", "exchange", "currency", "fund_size"]
    issues = []
    for field in fields:
        null_count = db.query(func.count(ETFInfo.code)).filter(
            getattr(ETFInfo, field).is_(None)
        ).scalar()
        pct = null_count / total * 100 if total else 0
        status = "PASS" if null_count == 0 else "WARN"
        print(f"  {status}: {field:.<20} 缺失 {null_count:>6,} / {total:>6,} ({pct:5.2f}%)")
        if null_count:
            issues.append((field, null_count))
    return issues


def check_latest_data_coverage(db):
    section("三、最新交易日数据覆盖")
    today = date.today()
    print(f"  今天日期: {today} ({['周一','周二','周三','周四','周五','周六','周日'][today.weekday()]})")

    latest_bar = db.query(func.max(ETFDailyBar.trade_date)).scalar()
    latest_ind = db.query(func.max(ETFIndicator.trade_date)).scalar()
    latest_score = db.query(func.max(ETFScore.trade_date)).scalar()
    latest_signal = db.query(func.max(Signal.trade_date)).scalar()

    print(f"  最新日线日期: {latest_bar}")
    print(f"  最新指标日期: {latest_ind}")
    print(f"  最新评分日期: {latest_score}")
    print(f"  最新信号日期: {latest_signal}")

    # Expected latest trading day is the latest date actually present in daily bars
    expected = latest_bar
    print(f"  数据库最新交易日: {expected}")

    gaps = []
    for name, actual in [("日线", latest_bar), ("指标", latest_ind), ("评分", latest_score), ("信号", latest_signal)]:
        if actual is None:
            gaps.append((name, "无数据"))
            print(f"  WARN: {name} 无数据")
        elif actual < expected:
            gap_days = (expected - actual).days
            gaps.append((name, gap_days))
            print(f"  WARN: {name} 数据落后 {gap_days} 个交易日 ({actual} < {expected})")
        else:
            print(f"  PASS: {name} 数据已更新到 {actual}")

    # Count ETFs with latest date data
    if latest_bar:
        bar_count = db.execute(text(f"SELECT COUNT(*) FROM etf_daily_bar WHERE trade_date = '{latest_bar}'")).scalar()
        print(f"\n  {latest_bar} 日线覆盖 ETF 数: {bar_count:,} / {db.query(func.count(ETFInfo.code)).scalar():,}")
    if latest_ind:
        ind_count = db.query(func.count(ETFIndicator.id)).filter(ETFIndicator.trade_date == latest_ind).scalar()
        print(f"  {latest_ind} 指标覆盖 ETF 数: {ind_count:,} / {db.query(func.count(ETFInfo.code)).scalar():,}")
    if latest_score:
        score_count = db.query(func.count(ETFScore.id)).filter(ETFScore.trade_date == latest_score).scalar()
        print(f"  {latest_score} 评分覆盖 ETF 数: {score_count:,} / {db.query(func.count(ETFInfo.code)).scalar():,}")

    return gaps


def check_historical_coverage(db):
    section("四、历史数据覆盖均匀性")
    db.query(func.count(ETFInfo.code)).scalar()

    # Daily bars per ETF stats
    result = db.query(ETFDailyBar.etf_code, func.count('*')).group_by(ETFDailyBar.etf_code).all()
    bar_counts = [r[1] for r in result]
    if bar_counts:
        avg = sum(bar_counts) / len(bar_counts)
        min_c = min(bar_counts)
        max_c = max(bar_counts)
        print(f"  日线: ETF 数 {len(bar_counts):,}, 平均 {avg:.1f} 条/只, 最少 {min_c}, 最多 {max_c}")
        if min_c < avg * 0.5:
            print("  WARN: 部分 ETF 日线数量明显偏少")
            low = [(code, c) for code, c in result if c < avg * 0.5][:10]
            for code, c in low:
                print(f"    - {code}: {c} 条")

    # Date range
    bar_min = db.query(func.min(ETFDailyBar.trade_date)).scalar()
    bar_max = db.query(func.max(ETFDailyBar.trade_date)).scalar()
    if bar_min and bar_max:
        trading_days_expected = len(get_trading_dates(bar_min, bar_max))
        all_dates = set(db.query(ETFDailyBar.trade_date).distinct().all())
        print(f"  日线时间范围: {bar_min} ~ {bar_max}")
        print(f"  日线不同交易日数: {len(all_dates):,} (预期交易日约 {trading_days_expected:,})")

    # Indicators date range
    ind_min = db.query(func.min(ETFIndicator.trade_date)).scalar()
    ind_max = db.query(func.max(ETFIndicator.trade_date)).scalar()
    if ind_min and ind_max:
        ind_dates = set(db.query(ETFIndicator.trade_date).distinct().all())
        print(f"  指标时间范围: {ind_min} ~ {ind_max}")
        print(f"  指标不同交易日数: {len(ind_dates):,}")

    # Scores date range
    score_min = db.query(func.min(ETFScore.trade_date)).scalar()
    score_max = db.query(func.max(ETFScore.trade_date)).scalar()
    if score_min and score_max:
        score_dates = set(db.query(ETFScore.trade_date).distinct().all())
        print(f"  评分时间范围: {score_min} ~ {score_max}")
        print(f"  评分不同交易日数: {len(score_dates):,}")


def check_pools(db):
    section("五、标的池数据检查")
    pools = db.query(ETFPools).all()
    print(f"  标的池数量: {len(pools)}")
    issues = []
    for pool in pools:
        members = db.query(PoolMember).filter(PoolMember.pool_id == pool.id).count()
        weights = db.query(PoolWeight).filter(PoolWeight.pool_id == pool.id).count()
        snapshots = db.query(PoolSnapshot).filter(PoolSnapshot.pool_id == pool.id).count()
        print(f"  - {pool.name} (id={pool.id}): 成员 {members}, 权重 {weights}, 快照 {snapshots}")
        if members == 0:
            issues.append((pool.name, "空池"))
        if weights != members and weights != 0:
            issues.append((pool.name, f"权重数({weights})与成员数({members})不一致"))
        if snapshots == 0:
            issues.append((pool.name, "无快照"))
    return issues


def check_reports(db):
    section("六、报告数据检查")
    reports = db.query(ReportMetadata).order_by(ReportMetadata.report_date.desc()).all()
    print(f"  报告总数: {len(reports)}")
    by_type = Counter(r.report_type for r in reports)
    for t, c in by_type.items():
        print(f"    - {t}: {c}")
    if reports:
        latest = reports[0]
        print(f"  最新报告: {latest.report_type} @ {latest.report_date}, 状态={latest.status}")
    return reports


def check_etl_status(db):
    section("七、ETL 执行状态")
    logs = db.query(ETLLog).order_by(ETLLog.created_at.desc()).limit(10).all()
    print("  最近 10 条 ETL 日志:")
    issues = []
    for log in logs:
        status_flag = "✓" if log.status == "success" else "✗"
        print(f"    {status_flag} {log.job_name} | {log.status} | {log.created_at} | {log.error_msg or ''}")
        if log.status != "success":
            issues.append((log.job_name, log.status, log.error_msg))

    # Last success per task
    print("\n  各任务最近成功时间:")
    tasks = db.query(ETLLog.job_name).distinct().all()
    for (job_name,) in tasks:
        last_success = db.query(func.max(ETLLog.created_at)).filter(
            ETLLog.job_name == job_name, ETLLog.status == "success"
        ).scalar()
        print(f"    {job_name}: {last_success or '从未成功'}")
    return issues


def check_scan_logs(db):
    section("八、ETF 扫描日志")
    latest = db.query(func.max(ETFScanLog.scan_date)).scalar()
    print(f"  最新扫描日期: {latest}")
    if latest:
        log = db.query(ETFScanLog).filter(ETFScanLog.scan_date == latest).first()
        if log:
            print(f"  扫描结果: 新增 {log.new_count}, 退市 {log.delisted_count}, 变更 {log.changed_count}, 状态={log.status}")
    return latest


def check_fx_rate(db):
    section("九、汇率数据 (fx_rate)")
    count = db.execute(text("SELECT COUNT(*) FROM fx_rate")).scalar()
    if count == 0:
        print("  WARN: fx_rate 表为空，跨境 ETF 分析可能受影响")
        return [("fx_rate", "空表")]
    else:
        print(f"  PASS: fx_rate 表有 {count:,} 条记录")
        return []


def check_price_quality(db):
    section("十、价格数据质量")
    # Check for zero/negative prices
    zero_close = db.execute(text("SELECT COUNT(*) FROM etf_daily_bar WHERE close <= 0")).scalar()
    null_volume = db.execute(text("SELECT COUNT(*) FROM etf_daily_bar WHERE volume IS NULL")).scalar()
    print(f"  收盘价 <= 0 的记录: {zero_close:,}")
    print(f"  成交量为 NULL 的记录: {null_volume:,}")
    issues = []
    if zero_close:
        issues.append(("收盘价异常", zero_close))
    # NULL volume is acceptable (illiquid days); just report it
    if null_volume:
        print(f"  INFO: {null_volume} 条记录成交量为 NULL（已清理或为停牌/无成交日）")
    return issues


def check_redis():
    section("十一、Redis 缓存")
    try:
        from app.core.redis_client import get_redis_client
        r = get_redis_client()
        key_count = r.dbsize()
        print("  Redis 连接: OK")
        print(f"  Redis keys 数量: {key_count:,}")
        if key_count == 0:
            print("  WARN: Redis 中没有任何缓存 key")
            return [("redis", "empty")]
        else:
            print("  PASS: Redis 缓存已启用")
            return []
    except Exception as e:
        print(f"  FAIL: 无法连接 Redis: {e}")
        return [("redis", "connection failed")]


def main():
    print("=" * 70)
    print("AD-RESEARCH - DATA COMPLETENESS CHECK")
    print(f"检查时间: {date.today()}")
    print("=" * 70)

    db = SessionLocal()
    try:
        all_issues = []

        check_basic_counts(db)
        all_issues.extend(("ETF字段", f) for f in check_etf_info_completeness(db))
        all_issues.extend(("最新数据", g) for g in check_latest_data_coverage(db))
        check_historical_coverage(db)
        all_issues.extend(("标的池", p) for p in check_pools(db))
        check_reports(db)
        all_issues.extend(("ETL", e) for e in check_etl_status(db))
        check_scan_logs(db)
        all_issues.extend(("汇率", f) for f in check_fx_rate(db))
        all_issues.extend(("价格质量", q) for q in check_price_quality(db))
        all_issues.extend(("Redis", r) for r in check_redis())

        section("汇总")
        if all_issues:
            print(f"  共发现 {len(all_issues)} 项需关注的问题:")
            for category, issue in all_issues:
                print(f"    [{category}] {issue}")
        else:
            print("  未发现明显数据完整性问题")

    finally:
        db.close()


if __name__ == "__main__":
    main()
