"""每日 AI 综合研报 Pydantic schemas（2026-08-03，Daily Digest B5）。

字段对齐 B6 前端契约（``web/src/api/digest.ts``）：
- 列表项带 ``content_chars``（前端列表卡显示篇幅，不回传全文）；
- 详情带 ``content_md`` / ``sections_json`` / ``data_snapshot_json`` /
  ``llm_model`` / ``finished_at``；
- Dashboard 轻量摘要只带 5 个字段。
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


# ------------------------------------------------------------------
# 列表
# ------------------------------------------------------------------

class DigestListItem(BaseModel):
    """列表项（不含 content_md 全文）。"""

    id: int
    report_date: date
    status: str
    title: str = ""
    summary_md: str | None = None
    content_chars: int = 0
    created_at: datetime | None = None


class DigestListResponse(BaseModel):
    """分页列表响应（字段命名对齐平台 page/page_size 惯例）。"""

    items: list[DigestListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ------------------------------------------------------------------
# 详情（/latest、/{id}、/by-date/{date} 共用）
# ------------------------------------------------------------------

class DigestDetail(BaseModel):
    """完整报告：含 markdown 全文与排障元数据。"""

    id: int
    report_date: date
    status: str
    title: str = ""
    summary_md: str | None = None
    content_md: str | None = None
    sections_json: list[dict[str, Any]] = []
    data_snapshot_json: dict[str, Any] | None = None
    llm_model: str | None = None
    error_msg: str | None = None
    report_metadata_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


class DigestSummary(BaseModel):
    """Dashboard 摘要卡轻量响应。"""

    id: int
    report_date: date
    status: str
    title: str = ""
    summary_md: str | None = None
    content_chars: int = 0


# ------------------------------------------------------------------
# 手动重生成
# ------------------------------------------------------------------

class DigestRegenerateRequest(BaseModel):
    """可选 body：缺省时重生成今天（Asia/Shanghai）的报告。"""

    target_date: date | None = None


class DigestRegenerateResponse(BaseModel):
    """后台线程已接受任务，立即返回（不等生成完成）。"""

    status: str
    report_date: date
