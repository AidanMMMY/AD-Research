"""Notification service with webhook support.

Supports WeChat Work, Feishu, and DingTalk webhooks.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from app.models.notification import NotificationConfig, NotificationLog
from app.models.scoring import ReportMetadata


class NotificationService:
    """Service for sending notifications via various channels."""

    def __init__(self, db: Session):
        self.db = db

    def get_configs(self) -> List[Dict[str, Any]]:
        """Get all notification configurations."""
        configs = self.db.query(NotificationConfig).all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "channel_type": c.channel_type,
                "config_json": c.config_json,
                "is_active": c.is_active,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in configs
        ]

    def create_config(self, name: str, channel_type: str, config_json: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new notification configuration."""
        config = NotificationConfig(
            name=name,
            channel_type=channel_type,
            config_json=config_json,
            is_active=True,
        )
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return {
            "id": config.id,
            "name": config.name,
            "channel_type": config.channel_type,
            "config_json": config.config_json,
            "is_active": config.is_active,
        }

    def update_config(self, config_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        """Update a notification configuration."""
        config = self.db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
        if not config:
            return None
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        self.db.commit()
        self.db.refresh(config)
        return {
            "id": config.id,
            "name": config.name,
            "channel_type": config.channel_type,
            "config_json": config.config_json,
            "is_active": config.is_active,
        }

    def delete_config(self, config_id: int) -> bool:
        """Delete a notification configuration."""
        config = self.db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
        if not config:
            return False
        self.db.delete(config)
        self.db.commit()
        return True

    def send_notification(self, config_id: int, report_id: Optional[int] = None, test: bool = False) -> Dict[str, Any]:
        """Send a notification using the specified configuration."""
        config = self.db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
        if not config:
            return {"success": False, "error": "Config not found"}

        if not config.is_active:
            return {"success": False, "error": "Config is inactive"}

        # Create log entry
        log = NotificationLog(
            config_id=config_id,
            report_id=report_id,
            status="pending",
        )
        self.db.add(log)
        self.db.commit()

        try:
            if config.channel_type == "webhook":
                result = self._send_webhook(config.config_json, report_id, test)
            else:
                result = {"success": False, "error": f"Unsupported channel type: {config.channel_type}"}

            log.status = "success" if result.get("success") else "failed"
            log.error_msg = result.get("error")
            log.sent_at = datetime.utcnow()
            self.db.commit()

            return result
        except Exception as e:
            log.status = "failed"
            log.error_msg = str(e)
            log.sent_at = datetime.utcnow()
            self.db.commit()
            return {"success": False, "error": str(e)}

    def _send_webhook(self, config: Dict[str, Any], report_id: Optional[int], test: bool) -> Dict[str, Any]:
        """Send notification via webhook (WeChat Work / Feishu / DingTalk)."""
        webhook_url = config.get("webhook_url")
        platform = config.get("platform", "wechat")  # wechat / feishu / dingtalk

        if not webhook_url:
            return {"success": False, "error": "Webhook URL not configured"}

        # Build message
        if test:
            content = "ETF投研平台 - 测试消息\n这是一条测试推送消息，如果您的系统收到此消息，说明推送配置正确。"
        else:
            report = self.db.query(ReportMetadata).filter(ReportMetadata.id == report_id).first() if report_id else None
            if report:
                content = f"ETF投研平台报告通知\n报告类型: {report.report_type}\n报告日期: {report.report_date}\n状态: {report.status}"
            else:
                content = "ETF投研平台 - 新报告已生成"

        # Platform-specific payload
        if platform == "wechat":
            payload = {
                "msgtype": "text",
                "text": {"content": content},
            }
        elif platform == "feishu":
            payload = {
                "msg_type": "text",
                "content": {"text": content},
            }
        elif platform == "dingtalk":
            payload = {
                "msgtype": "text",
                "text": {"content": content},
            }
        else:
            payload = {"text": content}

        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        if response.status_code == 200:
            return {"success": True}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}

    def get_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get notification send logs."""
        logs = (
            self.db.query(NotificationLog)
            .order_by(NotificationLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": log.id,
                "config_id": log.config_id,
                "report_id": log.report_id,
                "status": log.status,
                "error_msg": log.error_msg,
                "sent_at": log.sent_at.isoformat() if log.sent_at else None,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
