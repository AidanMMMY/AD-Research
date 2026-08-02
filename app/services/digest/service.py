"""Daily Digest 门面服务（2026-08-03，B3）。

``DailyDigestService.generate()`` 串起全链路：

    聚合（DigestDataCollector）→ 生成（DigestGenerator）→
    upsert daily_digest（report_date unique，同日重生成覆盖）→
    report_metadata 伴随行（report_type="daily_digest", pool_id=NULL,
    format="markdown", file_path=NULL）→ 通知 hook

通知说明：``notify()`` 是 B7 的接线点——遍历所有 is_active 的
NotificationConfig，复用 NotificationService.send_notification
（config_id, report_id=伴随行 id）。这里只 import 不修改
NotificationService；邮件全文/Telegram 通道由 B7 在
NotificationService 内部按 report_type=="daily_digest" 分流。
通知失败只记日志，绝不影响出报主链路。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.digest import DailyDigest
from app.models.notification import NotificationConfig
from app.models.scoring import ReportMetadata
from app.services.digest.collector import DigestDataCollector
from app.services.digest.context import DigestContext
from app.services.digest.generator import DigestGenerator, DigestResult

logger = logging.getLogger(__name__)

REPORT_TYPE = "daily_digest"


class DailyDigestService:
    """聚合→生成→落库→伴随行→通知 的门面。"""

    def __init__(
        self,
        db: Session,
        collector: DigestDataCollector | None = None,
        generator: DigestGenerator | None = None,
    ) -> None:
        self.db = db
        self.collector = collector
        self.generator = generator

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def generate(self, target_date: date | None = None) -> DailyDigest:
        """生成指定日期（窗口结束日）的日报；同日重生成走 upsert 覆盖。

        整体异常（聚合/生成之外的 DB 错误等）→ status=failed 落库后
        re-raise，让调度层 ETLLog 记录失败。
        """
        collector = self.collector or DigestDataCollector(self.db)
        generator = self.generator or DigestGenerator()

        if target_date is None:
            from app.services.digest.collector import SHANGHAI

            target_date = datetime.now(SHANGHAI).date()

        digest = self._get_or_create(target_date)
        now = datetime.now(timezone.utc)
        digest.status = "running"
        digest.started_at = now
        digest.error_msg = None
        self.db.commit()

        try:
            ctx = collector.collect(target_date)
            result = generator.generate(ctx)
            self._apply_result(digest, ctx, result)

            metadata = self._upsert_report_metadata(digest)
            digest.report_metadata_id = metadata.id
            self.db.commit()
            self.db.refresh(digest)
        except Exception as exc:
            digest.status = "failed"
            digest.error_msg = str(exc)
            digest.finished_at = datetime.now(timezone.utc)
            self.db.commit()
            raise

        # 通知是旁路：失败不影响已落库的报告
        try:
            self.notify(digest, metadata.id)
        except Exception as exc:  # noqa: BLE001 - 通知绝不阻塞主链路
            logger.warning("digest notify failed: %s", exc)

        return digest

    # ------------------------------------------------------------------
    # 通知 hook（B7 接线点）
    # ------------------------------------------------------------------

    def notify(self, digest: DailyDigest, report_metadata_id: int) -> list[dict[str, Any]]:
        """遍历 is_active 通知配置逐渠道推送。

        复用 ``NotificationService.send_notification(config_id,
        report_id=...)``；report_id 传 report_metadata 伴随行 id，
        B7 在 NotificationService 内部按 report_type=="daily_digest"
        分流到邮件全文 / Telegram 通道。failed 状态不推送。
        """
        if digest.status not in ("success", "partial"):
            logger.info("digest %s status=%s, skip notify", digest.report_date, digest.status)
            return []

        from app.services.notification_service import NotificationService

        configs = (
            self.db.execute(
                select(NotificationConfig).where(
                    NotificationConfig.is_active.is_(True),
                    # system_alert 是 watchdog 内部 sink（auto_created），
                    # 不是真实外发渠道，推送只会记一条 failed 噪音日志。
                    NotificationConfig.channel_type != "system_alert",
                )
            )
            .scalars()
            .all()
        )
        results: list[dict[str, Any]] = []
        svc = NotificationService(self.db)
        for cfg in configs:
            try:
                res = svc.send_notification(
                    config_id=cfg.id, report_id=report_metadata_id
                )
            except Exception as exc:  # noqa: BLE001 - 单渠道失败不影响其他渠道
                logger.warning("digest notify config %s failed: %s", cfg.id, exc)
                res = {"success": False, "error": str(exc)}
            results.append({"config_id": cfg.id, **res})
        return results

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _get_or_create(self, report_date: date) -> DailyDigest:
        digest = (
            self.db.execute(
                select(DailyDigest).where(DailyDigest.report_date == report_date)
            )
            .scalars()
            .first()
        )
        if digest is None:
            digest = DailyDigest(report_date=report_date, status="pending")
            self.db.add(digest)
            self.db.flush()
        return digest

    def _apply_result(
        self, digest: DailyDigest, ctx: DigestContext, result: DigestResult
    ) -> None:
        digest.title = result.title
        digest.summary_md = result.summary_md
        digest.content_md = result.content_md
        digest.sections_json = result.sections
        digest.data_snapshot_json = ctx.snapshot_meta()
        digest.llm_model = result.llm_model
        digest.status = result.status
        digest.error_msg = None
        digest.finished_at = datetime.now(timezone.utc)

    def _upsert_report_metadata(self, digest: DailyDigest) -> ReportMetadata:
        """report_metadata 伴随行：通知通道沿用 report_id 语义。

        同日重生成复用已有伴随行（report_type+report_date+pool_id NULL
        定位），避免通知日志关联到已废弃的旧行。
        """
        metadata = (
            self.db.execute(
                select(ReportMetadata).where(
                    ReportMetadata.report_type == REPORT_TYPE,
                    ReportMetadata.report_date == digest.report_date,
                    ReportMetadata.pool_id.is_(None),
                )
            )
            .scalars()
            .first()
        )
        if metadata is None:
            metadata = ReportMetadata(
                report_type=REPORT_TYPE,
                report_date=digest.report_date,
                pool_id=None,
                template_id=None,
                status="running",  # NOT NULL 占位，下方随即覆盖为终态
                format="markdown",
                file_path=None,
            )
            self.db.add(metadata)

        metadata.status = (
            "success" if digest.status in ("success", "partial") else "failed"
        )
        metadata.started_at = digest.started_at
        metadata.finished_at = digest.finished_at
        metadata.error_msg = digest.error_msg
        self.db.flush()
        return metadata
