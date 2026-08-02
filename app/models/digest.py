"""每日夜间 AI 综合研报 ORM 模型（2026-08-03，Daily Digest B1）。

``daily_digest`` 表承载每天 06:30 (Asia/Shanghai) 自动生成的全局
综合研报：聚合层（``app.services.digest.collector``）以
[前一日 06:30, 当日 06:30) 为窗口采集 8 个数据包，生成层
（``app.services.digest.generator``）分 6 章节独立调用 LLM 拼装
成 markdown 全文，落库后供 /digest 页面、Dashboard 摘要卡、
邮件 / Telegram 推送共用。

设计决策：
- ``report_date`` 全局唯一（全局一份报告，非按用户）。同日重生成
  走 upsert 覆盖，配合 scheduler 的 redis_lock 防并发双写。
- ``report_metadata_id`` 弱关联既有 ``report_metadata`` 伴随行
  （report_type="daily_digest", pool_id=NULL）——通知通道
  （NotificationService.send_notification(report_id=...)）沿用
  report_id 语义；ondelete SET NULL 兜底伴随行被清理的场景。
- ``sections_json`` 记录 6 章节逐节状态（success/failed/字数），
  ``data_snapshot_json`` 记录聚合层元数据（窗口、各包行数、
  degraded 列表）。两者是排障入口，不承载前端渲染。
- status 取值：pending / running / success / partial / failed。
  ≥2 章节失败或落库校验（总字数 / 章节标题齐全）不通过时记
  partial——报告仍出仍推送，前端用徽章提示。
"""


from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)

from app.core.database import Base


class DailyDigest(Base):
    """每日 AI 综合研报（全局一份，report_date 唯一）。"""

    __tablename__ = "daily_digest"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    report_date = Column(
        Date,
        nullable=False,
        unique=True,
        index=True,
        comment="报告日期（窗口结束日，Asia/Shanghai 当日 06:30 收口）",
    )
    report_metadata_id = Column(
        Integer,
        ForeignKey("report_metadata.id", ondelete="SET NULL"),
        nullable=True,
        comment="伴随的 report_metadata 行 ID（通知通道 report_id 语义）",
    )
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending / running / success / partial / failed",
    )
    title = Column(String(200), comment="报告标题")
    summary_md = Column(Text, comment="AI 摘要（≤200 字，Dashboard 摘要卡 / 推送首条用）")
    content_md = Column(Text, comment="6 章节 markdown 全文")
    sections_json = Column(
        JSON,
        comment="逐章节状态 [{key,title,status,chars}]，failed 节含占位段说明",
    )
    data_snapshot_json = Column(
        JSON,
        comment="聚合层元数据：窗口起止、各数据包行数、degraded 列表",
    )
    llm_model = Column(String(50), comment="生成所用 LLM 模型名（provider.model）")
    error_msg = Column(Text, comment="整体失败时的错误信息")
    started_at = Column(DateTime(timezone=True), comment="生成开始时间")
    finished_at = Column(DateTime(timezone=True), comment="生成完成时间")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="创建时间",
    )

    def __repr__(self) -> str:
        return (
            f"<DailyDigest {self.report_date} status={self.status}>"
        )
