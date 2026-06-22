"""Notification service with webhook and email support.

Supports WeChat Work, Feishu, DingTalk webhooks, and SMTP email.
Sensitive credentials stored in config_json are encrypted at rest.
"""

import base64
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import requests
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.config import auth_settings, get_settings
from app.models.notification import NotificationConfig, NotificationLog
from app.models.scoring import ReportMetadata


class NotificationService:
    """Service for sending notifications via various channels."""

    # Marker for encrypted values stored in config_json
    _ENCRYPTED_PREFIX = "enc:"

    def __init__(self, db: Session):
        self.db = db
        self._fernet = self._get_fernet()

    def _get_fernet(self) -> Fernet | None:
        """Build a Fernet instance from the configured encryption key."""
        key = auth_settings.NOTIFICATION_ENCRYPTION_KEY or auth_settings.SECRET_KEY
        if not key:
            return None
        # Derive a URL-safe base64-encoded 32-byte key
        import hashlib

        digest = hashlib.sha256(key.encode("utf-8")).digest()
        encoded = base64.urlsafe_b64encode(digest)
        return Fernet(encoded)

    def _encrypt_value(self, value: str) -> str:
        """Encrypt a sensitive string for storage in config_json."""
        if not self._fernet:
            return value
        if value.startswith(self._ENCRYPTED_PREFIX):
            return value
        encrypted = self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        return f"{self._ENCRYPTED_PREFIX}{encrypted}"

    def _decrypt_value(self, value: str) -> str:
        """Decrypt a sensitive string from config_json."""
        if not self._fernet or not value.startswith(self._ENCRYPTED_PREFIX):
            return value
        encrypted = value[len(self._ENCRYPTED_PREFIX) :]
        try:
            return self._fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
        except Exception:
            return ""

    def _protect_config_json(self, config_json: dict[str, Any]) -> dict[str, Any]:
        """Encrypt sensitive values before persisting config_json."""
        protected = dict(config_json)
        for key in ("smtp_password", "webhook_secret"):
            if key in protected and protected[key]:
                protected[key] = self._encrypt_value(str(protected[key]))
        return protected

    def _expose_config_json(self, config_json: dict[str, Any]) -> dict[str, Any]:
        """Decrypt sensitive values when returning config_json to callers."""
        exposed = dict(config_json)
        for key in ("smtp_password", "webhook_secret"):
            if key in exposed and exposed[key]:
                exposed[key] = self._decrypt_value(str(exposed[key]))
        return exposed

    def get_configs(self) -> list[dict[str, Any]]:
        """Get all notification configurations."""
        configs = self.db.query(NotificationConfig).all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "channel_type": c.channel_type,
                "config_json": self._expose_config_json(c.config_json or {}),
                "is_active": c.is_active,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in configs
        ]

    def create_config(self, name: str, channel_type: str, config_json: dict[str, Any]) -> dict[str, Any]:
        """Create a new notification configuration."""
        config = NotificationConfig(
            name=name,
            channel_type=channel_type,
            config_json=self._protect_config_json(config_json),
            is_active=True,
        )
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return {
            "id": config.id,
            "name": config.name,
            "channel_type": config.channel_type,
            "config_json": self._expose_config_json(config.config_json or {}),
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    def update_config(self, config_id: int, **kwargs) -> dict[str, Any] | None:
        """Update a notification configuration."""
        config = self.db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
        if not config:
            return None
        for key, value in kwargs.items():
            if hasattr(config, key):
                if key == "config_json" and isinstance(value, dict):
                    value = self._protect_config_json(value)
                setattr(config, key, value)
        self.db.commit()
        self.db.refresh(config)
        return {
            "id": config.id,
            "name": config.name,
            "channel_type": config.channel_type,
            "config_json": self._expose_config_json(config.config_json or {}),
            "is_active": config.is_active,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    def delete_config(self, config_id: int) -> bool:
        """Delete a notification configuration."""
        config = self.db.query(NotificationConfig).filter(NotificationConfig.id == config_id).first()
        if not config:
            return False
        self.db.delete(config)
        self.db.commit()
        return True

    def send_notification(self, config_id: int, report_id: int | None = None, test: bool = False) -> dict[str, Any]:
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
            exposed_config = self._expose_config_json(config.config_json or {})
            if config.channel_type == "webhook":
                result = self._send_webhook(exposed_config, report_id, test)
            elif config.channel_type == "email":
                result = self._send_email(exposed_config, report_id, test)
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

    def _send_webhook(self, config: dict[str, Any], report_id: int | None, test: bool) -> dict[str, Any]:
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

    def _send_email(self, config: dict[str, Any], report_id: int | None, test: bool) -> dict[str, Any]:
        """Send notification via SMTP email."""
        settings = get_settings()
        to_emails = config.get("to_emails", "")
        subject_prefix = config.get("subject_prefix", "ETF投研平台")

        if not to_emails:
            return {"success": False, "error": "收件人邮箱未配置"}

        # Split comma-separated emails
        recipients = [e.strip() for e in str(to_emails).split(",") if e.strip()]
        if not recipients:
            return {"success": False, "error": "收件人邮箱格式错误"}

        # Get SMTP settings from global config first, then per-config
        smtp_host = settings.smtp_host or config.get("smtp_host", "")
        smtp_port = int(config.get("smtp_port", settings.smtp_port) or 587)
        smtp_user = settings.smtp_user or config.get("smtp_user", "")
        smtp_password = settings.smtp_password or config.get("smtp_password", "")
        smtp_from = settings.smtp_from or config.get("smtp_from", "") or smtp_user
        use_tls = config.get("use_tls", settings.smtp_use_tls)

        if not smtp_host:
            return {"success": False, "error": "SMTP服务器未配置。请在环境变量(SMTP_HOST)或配置中设置SMTP服务器地址。"}
        if not smtp_user:
            return {"success": False, "error": "SMTP用户名未配置。请在环境变量(SMTP_USER)或配置中设置。"}
        if not smtp_password:
            return {"success": False, "error": "SMTP密码未配置。请在环境变量(SMTP_PASSWORD)或配置中设置。"}

        # Build message content
        if test:
            subject = f"[{subject_prefix}] 测试邮件"
            body_text = "这是一封测试邮件。\n\n如果您的邮箱收到此邮件，说明邮件推送配置正确。\n\n—— ETF投研平台"
            body_html = """
            <html><body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #333;">
            <h2 style="color: #818cf8;">测试邮件</h2>
            <p>这是一封测试邮件。</p>
            <p>如果您的邮箱收到此邮件，说明邮件推送配置正确。</p>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
            <p style="color: #94a3b8; font-size: 12px;">ETF投研平台 · 自动发送</p>
            </body></html>
            """
        else:
            report = self.db.query(ReportMetadata).filter(ReportMetadata.id == report_id).first() if report_id else None
            if report:
                subject = f"[{subject_prefix}] {report.report_type} 报告"
                body_text = f"""ETF投研平台报告通知

报告类型: {report.report_type}
报告日期: {report.report_date}
状态: {report.status}

请登录平台查看详细内容。"""
                body_html = f"""
                <html><body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #333;">
                <h2 style="color: #818cf8;">📊 ETF投研平台报告通知</h2>
                <table style="border-collapse: collapse; margin: 16px 0;">
                <tr><td style="padding: 8px 16px 8px 0; color: #64748b;">报告类型</td><td style="padding: 8px 0; font-weight: 500;">{report.report_type}</td></tr>
                <tr><td style="padding: 8px 16px 8px 0; color: #64748b;">报告日期</td><td style="padding: 8px 0; font-weight: 500;">{report.report_date}</td></tr>
                <tr><td style="padding: 8px 16px 8px 0; color: #64748b;">状态</td><td style="padding: 8px 0; font-weight: 500;">{report.status}</td></tr>
                </table>
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
                <p style="color: #94a3b8; font-size: 12px;">ETF投研平台 · 自动发送</p>
                </body></html>
                """
            else:
                subject = f"[{subject_prefix}] 新报告已生成"
                body_text = "ETF投研平台 - 新报告已生成\n\n请登录平台查看详细内容。"
                body_html = "<html><body><h2>新报告已生成</h2><p>请登录平台查看详细内容。</p></body></html>"

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = ", ".join(recipients)
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))

            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            if use_tls:
                server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, recipients, msg.as_string())
            server.quit()

            return {"success": True}
        except smtplib.SMTPAuthenticationError as e:
            return {"success": False, "error": f"SMTP认证失败: {e}"}
        except smtplib.SMTPConnectError as e:
            return {"success": False, "error": f"SMTP连接失败: {e}"}
        except Exception as e:
            return {"success": False, "error": f"邮件发送失败: {e}"}

    def get_logs(self, limit: int = 50) -> list[dict[str, Any]]:
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
