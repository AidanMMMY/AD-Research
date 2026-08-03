"""cninfo PDF→Markdown 提取管线（B2，2026-08-03）测试.

Coverage:
- extract_markdown 主路径 + 回退（pymupdf4llm 抛错 → pdfplumber 级联被调）；
- HTML 标签剥离（<mark>/<u>/<br>）；
- extract_text_for_report fmt="md"：写库 + 写盘（tmp_path）+ md_path 落库；
- extract_text_for_report fmt="text"：保持旧行为；
- 删除脚本：find_candidates 过滤 + dry-run 不动文件 + execute 真删并置 NULL。
"""

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.cninfo_report_service as svc_module
from app.core.database import Base
from app.models.cninfo_report import CninfoReport
from app.services.cninfo_report_service import CninfoReportService

# scripts/ 不是 package，按路径加载删除脚本。
_script_path = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "delete_extracted_cninfo_pdfs.py"
)
_spec = importlib.util.spec_from_file_location("delete_cninfo_pdfs", _script_path)
delete_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(delete_script)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session():
    """内存 SQLite session（与 test_cninfo_api.py 同款样板）。"""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, checkfirst=True)
    Session_ = sessionmaker(bind=engine)
    session = Session_()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine, checkfirst=True)
        engine.dispose()


def _seed_report(db, **overrides):
    defaults = {
        "ts_code": "600519.SH",
        "stock_code": "600519",
        "org_id": "gssh0600519",
        "sec_code": "600519",
        "announcement_id": "1234567890",
        "announcement_title": "贵州茅台2025年年度报告",
        "adjunct_url": "/finalpage/2026-03-15/1234567890.PDF",
        "announcement_time": datetime(2026, 3, 15, 9, 0, 0),
        "adjunct_type": "annual",
        "is_periodic": True,
        "extraction_status": "downloaded",
        "source": "cninfo",
    }
    defaults.update(overrides)
    row = CninfoReport(**defaults)
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def fake_pdf(tmp_path):
    """造一个占位 PDF 文件，返回其路径。"""
    pdf = tmp_path / "1234567890.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    return pdf


# ---------------------------------------------------------------------------
# extract_markdown
# ---------------------------------------------------------------------------


def test_extract_markdown_primary_path(monkeypatch, fake_pdf):
    """pymupdf4llm 正常时走主路径，且剥离偶发 HTML 标签。"""
    import types

    fake = types.SimpleNamespace(
        to_markdown=lambda p: "# 标题\n<mark>高亮</mark> <u>下划线</u><br>换行"
    )
    monkeypatch.setitem(sys.modules, "pymupdf4llm", fake)

    out = svc_module.extract_markdown(fake_pdf)
    assert out == "# 标题\n高亮 下划线\n换行"


def test_extract_markdown_fallback_on_error(monkeypatch, fake_pdf):
    """pymupdf4llm 抛错 → 回退纯文本级联（extract_text 被调用）。"""
    import types

    def _boom(path):
        raise RuntimeError("pymupdf cannot open")

    fake = types.SimpleNamespace(to_markdown=_boom)
    monkeypatch.setitem(sys.modules, "pymupdf4llm", fake)

    calls = []

    def _fake_extract_text(path):
        calls.append(path)
        return "纯文本内容"

    monkeypatch.setattr(svc_module, "extract_text", _fake_extract_text)

    out = svc_module.extract_markdown(fake_pdf)
    assert out == "纯文本内容"
    assert calls == [fake_pdf]


def test_extract_markdown_fallback_on_import_error(monkeypatch, fake_pdf):
    """pymupdf4llm 未安装（ImportError）也回退纯文本级联。"""
    import builtins

    real_import = builtins.__import__

    def _guarded_import(name, *args, **kwargs):
        if name == "pymupdf4llm":
            raise ImportError("no module named pymupdf4llm")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _guarded_import)
    monkeypatch.setattr(
        svc_module, "extract_text", lambda path: "fallback text"
    )

    assert svc_module.extract_markdown(fake_pdf) == "fallback text"


def test_strip_html_tags():
    assert svc_module._strip_html_tags("<mark>a</mark> <u>b</u><br/>c") == "a b\nc"
    assert svc_module._strip_html_tags("no tags") == "no tags"


# ---------------------------------------------------------------------------
# extract_text_for_report fmt="md" / fmt="text"
# ---------------------------------------------------------------------------


def test_extract_for_report_md_writes_db_and_disk(
    db_session, tmp_path, fake_pdf, monkeypatch
):
    """fmt="md"：extracted_text/format/md_path 落库，md 文件写盘。"""
    md_dir = tmp_path / "md"
    monkeypatch.setattr(svc_module, "_DEFAULT_MD_DIR", md_dir)
    monkeypatch.setattr(
        svc_module, "extract_markdown", lambda path: "# 年报 markdown"
    )

    row = _seed_report(db_session, file_path=str(fake_pdf), file_size=13)
    service = CninfoReportService(db_session)

    assert service.extract_text_for_report(row.id, fmt="md") is True

    db_session.refresh(row)
    assert row.extracted_text == "# 年报 markdown"
    assert row.extracted_format == "md"
    assert row.extraction_status == "extracted"
    assert row.md_path == "600519/1234567890.md"
    assert (md_dir / "600519" / "1234567890.md").read_text(
        encoding="utf-8"
    ) == "# 年报 markdown"


def test_extract_for_report_md_disk_failure_still_succeeds(
    db_session, tmp_path, fake_pdf, monkeypatch
):
    """写盘失败只记 warning 不判失败——DB 仍是主存储。"""
    # 指向一个无法创建的路径（父路径是普通文件 → mkdir 必败）。
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    monkeypatch.setattr(svc_module, "_DEFAULT_MD_DIR", blocker / "md")
    monkeypatch.setattr(svc_module, "extract_markdown", lambda path: "md 内容")

    row = _seed_report(db_session, file_path=str(fake_pdf))
    service = CninfoReportService(db_session)

    assert service.extract_text_for_report(row.id, fmt="md") is True
    db_session.refresh(row)
    assert row.extracted_text == "md 内容"
    assert row.extracted_format == "md"
    assert row.md_path is None  # 写盘失败，md_path 不落库


def test_extract_for_report_text_unchanged(db_session, fake_pdf, monkeypatch):
    """fmt="text" 保持旧行为：纯文本级联、不写盘、截断 _MAX_TEXT_LEN。"""
    monkeypatch.setattr(
        svc_module, "extract_text", lambda path: "plain text"
    )
    # 主路径不应被调用。
    monkeypatch.setattr(
        svc_module,
        "extract_markdown",
        lambda path: (_ for _ in ()).throw(AssertionError("should not call")),
    )

    row = _seed_report(db_session, file_path=str(fake_pdf))
    service = CninfoReportService(db_session)

    assert service.extract_text_for_report(row.id, fmt="text") is True
    db_session.refresh(row)
    assert row.extracted_text == "plain text"
    assert row.extracted_format == "text"
    assert row.md_path is None


# ---------------------------------------------------------------------------
# 删除脚本
# ---------------------------------------------------------------------------


def _seed_md_report(db, tmp_path, name="a.pdf"):
    """造一行满足删除条件的记录 + 一个真实 PDF 文件。"""
    pdf = tmp_path / name
    pdf.write_bytes(b"x" * 100)
    return _seed_report(
        db,
        announcement_id=name.split(".")[0],
        file_path=str(pdf),
        file_size=100,
        extraction_status="extracted",
        extracted_format="md",
        md_path=f"600519/{name.split('.')[0]}.md",
    )


def test_delete_script_find_candidates(db_session, tmp_path):
    """只有 extracted + md + md_path + file_path 全满足的行入选。"""
    eligible = _seed_md_report(db_session, tmp_path, "111.pdf")
    # 旧 text 格式：不入选。
    _seed_report(
        db_session,
        announcement_id="222",
        file_path=str(tmp_path / "222.pdf"),
        extraction_status="extracted",
        extracted_format="text",
    )
    # md 但 file_path 已空：不入选。
    _seed_report(
        db_session,
        announcement_id="333",
        extraction_status="extracted",
        extracted_format="md",
        md_path="600519/333.md",
    )

    rows = delete_script.find_candidates(db_session)
    assert [r.id for r in rows] == [eligible.id]


def test_delete_script_dry_run_leaves_files(db_session, tmp_path):
    row = _seed_md_report(db_session, tmp_path, "dry.pdf")
    rows = delete_script.find_candidates(db_session)

    counters = delete_script.purge(db_session, rows, execute=False)

    assert counters["candidates"] == 1
    assert counters["bytes_freed"] == 100
    assert Path(row.file_path).exists()  # dry-run 不动文件
    db_session.refresh(row)
    assert row.file_path is not None


def test_delete_script_execute_removes_and_nulls(db_session, tmp_path):
    row = _seed_md_report(db_session, tmp_path, "exec.pdf")
    pdf_path = Path(row.file_path)
    rows = delete_script.find_candidates(db_session)

    counters = delete_script.purge(db_session, rows, execute=True)

    assert counters["deleted"] == 1
    assert counters["bytes_freed"] == 100
    assert not pdf_path.exists()
    db_session.refresh(row)
    assert row.file_path is None
    assert row.file_size is None
    # adjunct_url 保留，可随时重新下载。
    assert row.adjunct_url
