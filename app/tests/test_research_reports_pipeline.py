"""Tests for the ResearchReportsPipeline and the fetch/upsert split in
:class:`ResearchReportService`.

Regression context: the daily ``research_reports_daily`` job used to fail
every run with ``'int' object is not iterable`` because
``ResearchReportsPipeline.extract()`` called
``ResearchReportService.fetch_recent_reports()`` — a method that upserts
internally and returns a row *count* (int) — and then ``transform()``
called ``list()`` on that int.  The service now exposes a fetch-only
``fetch_recent_report_rows()`` used by the pipeline, while
``fetch_recent_reports()`` keeps its fetch+upsert contract.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from app.data.pipelines.research_reports import ResearchReportsPipeline
from app.models.etf import ETFInfo
from app.models.research_report import ResearchReport
from app.services.research_report_service import ResearchReportService

SAMPLE_ROWS = [
    {
        "ts_code": "600519.SH",
        "name": "贵州茅台",
        "title": "贵州茅台：季报点评",
        "org_name": "中信证券",
        "industry": "食品饮料",
        "publish_date": date(2026, 7, 15),
        "rating": "买入",
        "pdf_url": "https://example.com/a.pdf",
        "raw": {"source": "mock"},
    },
    {
        "ts_code": "000001.SZ",
        "name": "平安银行",
        "title": "平安银行：深度报告",
        "org_name": "国泰君安",
        "industry": "银行",
        "publish_date": date(2026, 7, 16),
        "rating": "增持",
        "pdf_url": "https://example.com/b.pdf",
        "raw": {"source": "mock"},
    },
]


def _seed_active_ashare_stocks(db_session, codes=("600519.SH", "000001.SZ")):
    for code in codes:
        db_session.add(
            ETFInfo(
                code=code,
                name=f"Stock {code}",
                market="A股",
                instrument_type="STOCK",
                status="active",
            )
        )
    db_session.commit()


def _make_pipeline(db_session, provider_rows):
    """Build a pipeline whose EastMoney provider returns ``provider_rows``."""
    provider = MagicMock()
    provider.name = "eastmoney_research"
    provider.fetch_for_codes.return_value = provider_rows
    with patch(
        "app.data.pipelines.research_reports.EastMoneyResearchProvider",
        return_value=provider,
    ):
        pipeline = ResearchReportsPipeline(db_session)
    return pipeline, provider


def test_pipeline_run_upserts_records(db_session):
    """Full extract -> transform -> load run succeeds and writes rows.

    This is the exact path that used to crash with
    ``'int' object is not iterable`` in production.
    """
    _seed_active_ashare_stocks(db_session)
    pipeline, provider = _make_pipeline(db_session, SAMPLE_ROWS)

    result = pipeline.run()

    assert result.success is True
    assert result.error is None
    assert result.records == 2
    provider.fetch_for_codes.assert_called_once()
    rows = db_session.query(ResearchReport).all()
    assert {r.ts_code for r in rows} == {"600519.SH", "000001.SZ"}
    assert all(r.source == "eastmoney" for r in rows)


def test_extract_returns_list_and_does_not_persist(db_session):
    """``extract()`` must return a list of row dicts (never an int) and
    must not write to the DB — persistence belongs to ``load()``."""
    _seed_active_ashare_stocks(db_session)
    pipeline, _ = _make_pipeline(db_session, SAMPLE_ROWS)

    records = pipeline.extract()

    assert isinstance(records, list)
    assert records == SAMPLE_ROWS
    assert db_session.query(ResearchReport).count() == 0


def test_pipeline_run_handles_empty_provider_rows(db_session):
    """No upstream rows -> success with 0 records (keeps scheduler green)."""
    _seed_active_ashare_stocks(db_session)
    pipeline, _ = _make_pipeline(db_session, [])

    result = pipeline.run()

    assert result.success is True
    assert result.records == 0
    assert db_session.query(ResearchReport).count() == 0


def test_pipeline_run_is_idempotent(db_session):
    """Re-running the same batch updates in place instead of duplicating."""
    _seed_active_ashare_stocks(db_session)
    pipeline, _ = _make_pipeline(db_session, SAMPLE_ROWS)
    assert pipeline.run().success is True

    pipeline2, _ = _make_pipeline(db_session, SAMPLE_ROWS)
    result = pipeline2.run()

    assert result.success is True
    assert db_session.query(ResearchReport).count() == 2


def test_fetch_recent_reports_still_upserts_and_returns_count(db_session):
    """The legacy fetch+upsert entry point keeps its int-return contract."""
    _seed_active_ashare_stocks(db_session)
    provider = MagicMock()
    provider.fetch_for_codes.return_value = SAMPLE_ROWS
    service = ResearchReportService(db_session, provider=provider)

    written = service.fetch_recent_reports(limit=200)

    assert written == 2
    assert db_session.query(ResearchReport).count() == 2


def test_fetch_recent_report_rows_empty_universe(db_session):
    """No active A-share stocks -> empty list, provider never called."""
    provider = MagicMock()
    service = ResearchReportService(db_session, provider=provider)

    assert service.fetch_recent_report_rows(limit=200) == []
    provider.fetch_for_codes.assert_not_called()
