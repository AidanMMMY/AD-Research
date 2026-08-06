"""Notification service with webhook, email and telegram support.

Supports WeChat Work, Feishu, DingTalk webhooks, SMTP email, and
Telegram Bot API (B7, 2026-08-03 — Daily Digest 全文推送).
Sensitive credentials stored in config_json are encrypted at rest.

P0-3 (2026-07-16): ``webhook_url`` is now stored in a dedicated
``webhook_url_encrypted`` column on ``NotificationConfig`` instead of
being held in plaintext inside ``config_json``. The encryption uses the
same Fernet instance as ``_protect_config_json`` (NOTIFICATION_ENCRYPTION_KEY
env var, with ``AUTH_SECRET_KEY`` fallback) so rotation of the key
invalidates both stores consistently.
"""

import base64
import ipaddress
import logging
import re
import smtplib
import socket
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Any
from urllib.parse import urlparse

import requests
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.config import auth_settings, get_settings
from app.core.log_sanitize import sanitize
from app.models.notification import NotificationConfig, NotificationLog
from app.models.scoring import ReportMetadata

logger = logging.getLogger(__name__)

# 前端渠道类型别名（2026-08-03）：生产存量配置的 channel_type 是
# wechat_work/feishu/dingtalk，而发送层只认 webhook/email/telegram，
# 导致存量配置推送全部 "Unsupported channel type" 静默失败（digest
# 首跑实测）。映射到 webhook 分发并补齐 platform 字段（企微/飞书/钉钉
# 各自的载荷格式 _send_webhook 本就支持）。
_WEBHOOK_CHANNEL_ALIASES = {
    "wechat_work": "wechat",
    "feishu": "feishu",
    "dingtalk": "dingtalk",
}


def _normalize_channel_type(channel_type: str, exposed_config: dict) -> str:
    """把前端渠道别名归一到发送层分发类型，顺手补 platform 默认值。"""
    platform = _WEBHOOK_CHANNEL_ALIASES.get(channel_type or "")
    if platform:
        exposed_config.setdefault("platform", platform)
        return "webhook"
    return channel_type


# SSRF guard for webhook URLs (2026-08-06 security audit). Webhook URLs are
# user-supplied (``NotificationConfigCreate.config_json``) and are POSTed by
# the server, so an attacker could otherwise point them at internal services
# or cloud metadata (169.254.169.254 / Aliyun 100.100.100.200) and read the
# response. We reject non-http(s) schemes, localhost/.local hosts, and any
# hostname that resolves to a private/reserved address.
_PRIVATE_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT; includes Aliyun metadata 100.100.100.200
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),  # benchmarking range
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
)


def _validate_webhook_url(url: str) -> None:
    """Raise ``ValueError`` when ``url`` may target an internal/metadata host."""
    if not url or len(url) > 2048:
        raise ValueError("Webhook URL 无效")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Webhook URL 仅支持 http/https")
    host = parsed.hostname
    if not host:
        raise ValueError("Webhook URL 缺少主机名")
    lowered = host.lower()
    if lowered == "localhost" or lowered.endswith(".local"):
        raise ValueError("Webhook URL 不能指向本机或内网地址")

    try:
        candidates = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            candidates = [
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(host, None)
            ]
        except OSError as exc:
            raise ValueError("Webhook URL 域名无法解析") from exc

    for ip in candidates:
        if any(ip in net for net in _PRIVATE_NETWORKS):
            raise ValueError("Webhook URL 不能指向内网或保留地址")


# ── B7 (2026-08-03): Daily Digest 推送用的最小 markdown 转换 ──
# 平台没有引入 markdown 库（grep 全仓无 markdown2/mistune），这里手写
# 最小转换集：标题 / 段落 / 无序列表 / **粗体**，其余原样保留并 HTML
# 转义。邮件与 Telegram 各一套输出（Telegram 只支持极小 HTML 子集）。

# Telegram Bot API 单条消息上限 4096 字符；转 HTML 后标签有额外开销，
# 分段按 3800 字符（markdown 源文本）预留余量。
_TELEGRAM_CHUNK_LIMIT = 3800


def _md_inline_html(text: str) -> str:
    """最小内联转换：先 HTML 转义，再把 **粗体** 转成 <b>。"""
    escaped = escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


def md_to_email_html(md: str) -> str:
    """markdown → 简化邮件 HTML（h1/h2/h3、p、ul/li、粗体）。"""
    blocks: list[str] = []
    for block in re.split(r"\n{2,}", md.strip()):
        block = block.strip("\n")
        if not block.strip():
            continue
        lines = block.split("\n")
        first = lines[0]
        heading = re.match(r"^(#{1,3})\s+(.*)$", first)
        if heading and len(lines) == 1:
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_md_inline_html(heading.group(2).strip())}</h{level}>")
        elif all(re.match(r"^\s*[-*]\s+", line) for line in lines if line.strip()):
            item_texts = [
                re.sub(r"^\s*[-*]\s+", "", line).strip()
                for line in lines
                if line.strip()
            ]
            items = "".join(f"<li>{_md_inline_html(text)}</li>" for text in item_texts)
            blocks.append(f"<ul>{items}</ul>")
        else:
            inner = "<br>\n".join(_md_inline_html(line) for line in lines)
            blocks.append(f"<p>{inner}</p>")
    return "\n".join(blocks)


def md_to_telegram_html(md: str) -> str:
    """markdown → Telegram HTML 最小集（parse_mode=HTML 只认 b/i/a/code 等）。

    标题行降级为 <b> 粗体行，无序列表保留 "• " 文本前缀，其余按行
    转义输出，避免 MarkdownV2 的转义地狱。
    """
    out_lines: list[str] = []
    for line in md.split("\n"):
        stripped = line.strip()
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            out_lines.append(f"<b>{_md_inline_html(heading.group(2).strip())}</b>")
        elif re.match(r"^[-*]\s+", stripped):
            body = re.sub(r"^[-*]\s+", "", stripped)
            out_lines.append(f"• {_md_inline_html(body)}")
        else:
            out_lines.append(_md_inline_html(line) if stripped else "")
    return "\n".join(out_lines)


def split_telegram_chunks(text: str, limit: int = _TELEGRAM_CHUNK_LIMIT) -> list[str]:
    """按段落边界（\\n\\n）把长文切成 ≤limit 的段；单段超长再硬切。"""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = para if not current else f"{current}\n\n{para}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        # 单个段落自身超限：硬切，保证每条消息都不越限
        while len(para) > limit:
            chunks.append(para[:limit])
            para = para[limit:]
        current = para
    if current:
        chunks.append(current)
    return chunks


class NotificationService:
    """Service for sending notifications via various channels."""

    # Marker for encrypted values stored in config_json
    _ENCRYPTED_PREFIX = "enc:"

    def __init__(self, db: Session):
        self.db = db
        self._fernet = self._get_fernet()

    def _get_fernet(self) -> Fernet | None:
        """Build a Fernet instance from the configured encryption key."""
        settings = get_settings()
        key = settings.notification_encryption_key or auth_settings.SECRET_KEY
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
        # B7: telegram 的 bot_token 与 smtp_password 同级敏感，照抄 Fernet 惯例
        for key in ("smtp_password", "webhook_secret", "bot_token"):
            if key in protected and protected[key]:
                protected[key] = self._encrypt_value(str(protected[key]))
        return protected

    def _expose_config_json(self, config_json: dict[str, Any]) -> dict[str, Any]:
        """Decrypt sensitive values when returning config_json to callers."""
        exposed = dict(config_json)
        for key in ("smtp_password", "webhook_secret", "bot_token"):
            if key in exposed and exposed[key]:
                exposed[key] = self._decrypt_value(str(exposed[key]))
        return exposed

    def _encrypt_webhook_url(self, webhook_url: str | None) -> str | None:
        """Encrypt ``webhook_url`` for the dedicated ``webhook_url_encrypted`` column.

        Returns ``None`` when the input is falsy. Returns the original
        (already-prefixed) value if Fernet is unavailable — better to
        risk plaintext than to silently drop the URL.
        """
        if not webhook_url:
            return None
        if not self._fernet:
            return webhook_url
        if webhook_url.startswith(self._ENCRYPTED_PREFIX):
            return webhook_url
        return f"{self._ENCRYPTED_PREFIX}{self._fernet.encrypt(webhook_url.encode('utf-8')).decode('utf-8')}"

    def _decrypt_webhook_url(self, encrypted: str | None) -> str | None:
        """Decrypt ``webhook_url_encrypted`` back to plaintext.

        Returns ``None`` when the input is falsy or Fernet is unavailable.
        Returns ``""`` when decryption fails (rotated key, tampered row).
        """
        if not encrypted:
            return None
        if not self._fernet:
            return None
        if not encrypted.startswith(self._ENCRYPTED_PREFIX):
            return encrypted  # legacy plaintext
        try:
            return self._fernet.decrypt(encrypted[len(self._ENCRYPTED_PREFIX):].encode("utf-8")).decode("utf-8")
        except Exception:
            return ""

    def _resolve_webhook_url(self, config: NotificationConfig) -> str | None:
        """Read webhook URL from the encrypted column with config_json fallback.

        Legacy rows (created before the P0-3 migration) still hold the
        URL inside ``config_json`` — readable as plaintext or as an
        ``enc:``-prefixed value if a previous version of the code
        encrypted it in place. Both paths are normalised through
        ``_decrypt_webhook_url``.
        """
        if config.webhook_url_encrypted:
            return self._decrypt_webhook_url(config.webhook_url_encrypted)
        legacy = (config.config_json or {}).get("webhook_url")
        if legacy:
            return self._decrypt_webhook_url(legacy)
        return None

    def get_configs(self, user_id: int | None = None) -> list[dict[str, Any]]:
        """Get all notification configurations."""
        query = self.db.query(NotificationConfig)
        if user_id:
            query = query.filter(NotificationConfig.user_id == user_id)
        configs = query.all()
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

    def create_config(self, name: str, channel_type: str, config_json: dict[str, Any], user_id: int | None = None) -> dict[str, Any]:
        """Create a new notification configuration.

        P0-3: ``webhook_url`` from ``config_json`` is encrypted into the
        dedicated ``webhook_url_encrypted`` column and then stripped from
        ``config_json`` so the plaintext never lands in the JSONB blob.
        """
        protected = self._protect_config_json(config_json)
        webhook_url = protected.pop("webhook_url", None)
        if webhook_url:
            _validate_webhook_url(str(webhook_url))
        encrypted_url = self._encrypt_webhook_url(webhook_url) if webhook_url else None

        config = NotificationConfig(
            user_id=user_id,
            name=name,
            channel_type=channel_type,
            config_json=protected,
            webhook_url_encrypted=encrypted_url,
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

    def update_config(self, config_id: int, user_id: int | None = None, **kwargs) -> dict[str, Any] | None:
        """Update a notification configuration.

        P0-3: when ``config_json`` is being updated and contains a
        ``webhook_url`` key, the plaintext value is encrypted into the
        dedicated column (or re-encrypted if it was already there) and
        stripped from ``config_json``.
        """
        query = self.db.query(NotificationConfig).filter(NotificationConfig.id == config_id)
        if user_id:
            query = query.filter(NotificationConfig.user_id == user_id)
        config = query.first()
        if not config:
            return None
        for key, value in kwargs.items():
            if not hasattr(config, key):
                continue
            if key == "config_json" and isinstance(value, dict):
                protected = self._protect_config_json(value)
                new_webhook_url = protected.pop("webhook_url", None)
                if new_webhook_url is not None:
                    # Skip validation for already-encrypted round-trips.
                    if not str(new_webhook_url).startswith(self._ENCRYPTED_PREFIX):
                        _validate_webhook_url(str(new_webhook_url))
                    config.webhook_url_encrypted = self._encrypt_webhook_url(new_webhook_url)
                setattr(config, key, protected)
            else:
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

    def delete_config(self, config_id: int, user_id: int | None = None) -> bool:
        """Delete a notification configuration."""
        query = self.db.query(NotificationConfig).filter(NotificationConfig.id == config_id)
        if user_id:
            query = query.filter(NotificationConfig.user_id == user_id)
        config = query.first()
        if not config:
            return False
        self.db.delete(config)
        self.db.commit()
        return True

    def send_notification(self, config_id: int, report_id: int | None = None, test: bool = False, user_id: int | None = None) -> dict[str, Any]:
        """Send a notification using the specified configuration."""
        query = self.db.query(NotificationConfig).filter(NotificationConfig.id == config_id)
        if user_id:
            query = query.filter(NotificationConfig.user_id == user_id)
        config = query.first()
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
            # P0-3: merge the decrypted webhook_url into the runtime view.
            webhook_url = self._resolve_webhook_url(config)
            if webhook_url:
                exposed_config["webhook_url"] = webhook_url
            channel_type = _normalize_channel_type(config.channel_type, exposed_config)
            if channel_type == "webhook":
                result = self._send_webhook(exposed_config, report_id, test)
            elif channel_type == "email":
                result = self._send_email(exposed_config, report_id, test)
            elif channel_type == "telegram":
                result = self._send_telegram(exposed_config, report_id, test)
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
        """Send notification via webhook (WeChat Work / Feishu / DingTalk).

        ``config`` is the *decrypted* view of ``config_json`` merged with
        the plaintext ``webhook_url`` read from the dedicated encrypted
        column (see :meth:`send_notification`).
        """
        webhook_url = config.get("webhook_url")
        platform = config.get("platform", "wechat")  # wechat / feishu / dingtalk

        if not webhook_url:
            return {"success": False, "error": "Webhook URL not configured"}
        try:
            _validate_webhook_url(str(webhook_url))
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        # Build message
        if test:
            content = "AlloyResearch - 测试消息\n这是一条测试推送消息，如果您的系统收到此消息，说明推送配置正确。"
        else:
            report = self.db.query(ReportMetadata).filter(ReportMetadata.id == report_id).first() if report_id else None
            if report:
                content = f"AlloyResearch报告通知\n报告类型: {report.report_type}\n报告日期: {report.report_date}\n状态: {report.status}"
            else:
                content = "AlloyResearch - 新报告已生成"

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
            # Redirects could bounce a public URL to an internal host (SSRF
            # bypass). Legitimate webhook endpoints do not redirect.
            allow_redirects=False,
        )

        if response.status_code == 200:
            return {"success": True}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}

    def _send_email(self, config: dict[str, Any], report_id: int | None, test: bool) -> dict[str, Any]:
        """Send notification via SMTP email."""
        settings = get_settings()
        to_emails = config.get("to_emails", "")
        subject_prefix = config.get("subject_prefix", "AlloyResearch")

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
            body_text = "这是一封测试邮件。\n\n如果您的邮箱收到此邮件，说明邮件推送配置正确。\n\n—— AlloyResearch"
            body_html = """
            <html><body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #333;">
            <h2 style="color: #818cf8;">测试邮件</h2>
            <p>这是一封测试邮件。</p>
            <p>如果您的邮箱收到此邮件，说明邮件推送配置正确。</p>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
            <p style="color: #94a3b8; font-size: 12px;">AlloyResearch · 自动发送</p>
            </body></html>
            """
        else:
            report = self.db.query(ReportMetadata).filter(ReportMetadata.id == report_id).first() if report_id else None
            # B7: Daily Digest 走全文邮件（summary + content 全量），
            # 其余 pool 报告维持原有简短通知，行为零变化。
            digest_email = (
                self._build_digest_email(report) if report is not None else None
            )
            if digest_email is not None:
                subject, body_text, body_html = digest_email
            elif report:
                subject = f"[{subject_prefix}] {report.report_type} 报告"
                body_text = f"""AlloyResearch报告通知

报告类型: {report.report_type}
报告日期: {report.report_date}
状态: {report.status}

请登录平台查看详细内容。"""
                body_html = f"""
                <html><body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #333;">
                <h2 style="color: #818cf8;">📊 AlloyResearch报告通知</h2>
                <table style="border-collapse: collapse; margin: 16px 0;">
                <tr><td style="padding: 8px 16px 8px 0; color: #64748b;">报告类型</td><td style="padding: 8px 0; font-weight: 500;">{report.report_type}</td></tr>
                <tr><td style="padding: 8px 16px 8px 0; color: #64748b;">报告日期</td><td style="padding: 8px 0; font-weight: 500;">{report.report_date}</td></tr>
                <tr><td style="padding: 8px 16px 8px 0; color: #64748b;">状态</td><td style="padding: 8px 0; font-weight: 500;">{report.status}</td></tr>
                </table>
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
                <p style="color: #94a3b8; font-size: 12px;">AlloyResearch · 自动发送</p>
                </body></html>
                """
            else:
                subject = f"[{subject_prefix}] 新报告已生成"
                body_text = "AlloyResearch - 新报告已生成\n\n请登录平台查看详细内容。"
                body_html = "<html><body><h2>新报告已生成</h2><p>请登录平台查看详细内容。</p></body></html>"

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = ", ".join(recipients)
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            msg.attach(MIMEText(body_html, "html", "utf-8"))

            # 465 = 隐式 SSL（163/QQ 邮箱默认端口），必须 SMTP_SSL 直连，
            # 先明文再 STARTTLS 会在握手阶段挂起；其余端口走 STARTTLS。
            use_ssl = bool(config.get("use_ssl", smtp_port == 465))
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
            else:
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

    # ── B7 (2026-08-03): Daily Digest 全文邮件 / Telegram 通道 ──

    def _load_digest(self, report: ReportMetadata):
        """按 report_metadata 伴随行反查 DailyDigest（report_metadata_id 优先，
        report_date 兜底——伴随行被清理后仍可取到当日报告）。"""
        from app.models.digest import DailyDigest

        digest = (
            self.db.query(DailyDigest)
            .filter(DailyDigest.report_metadata_id == report.id)
            .first()
        )
        if digest is None:
            digest = (
                self.db.query(DailyDigest)
                .filter(DailyDigest.report_date == report.report_date)
                .first()
            )
        return digest

    def _build_digest_email(self, report: ReportMetadata) -> tuple[str, str, str] | None:
        """构造 Daily Digest 全文邮件（subject, body_text, body_html）。

        仅当 report_type=="daily_digest" 且能取到 digest 行时返回；
        否则返回 None，调用方回退到既有通用通知模板。
        """
        if report.report_type != "daily_digest":
            return None
        digest = self._load_digest(report)
        if digest is None:
            return None

        mmdd = report.report_date.strftime("%m-%d")
        # 标题缺失时退化为 summary 首句，再退化为固定文案
        fallback_title = (digest.summary_md or "").strip().split("\n")[0].strip() or "全球市场一日纵览"
        title = (digest.title or "").strip() or fallback_title
        subject = f"{mmdd} 每日综合研报：{title}"

        summary = (digest.summary_md or "").strip()
        content = (digest.content_md or "").strip()
        full_md = f"{summary}\n\n{content}".strip()

        # 平台暂无前端 base url 配置项，文案用相对路径提示
        link_hint = "请登录平台查看完整排版：/digest"
        body_text = f"{full_md}\n\n——\n{link_hint}\nAlloyResearch · 自动发送"

        body_html = f"""
        <html><body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; color: #333; line-height: 1.7;">
        <h2 style="color: #818cf8;">{escape(title)}</h2>
        <p style="color: #64748b; font-size: 13px;">{mmdd} 每日综合研报 · AI 自动生成</p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 16px 0;">
        {md_to_email_html(full_md)}
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0;">
        <p style="color: #94a3b8; font-size: 12px;">{escape(link_hint)}<br>AlloyResearch · 自动发送</p>
        </body></html>
        """
        return subject, body_text, body_html

    def _send_telegram(self, config: dict[str, Any], report_id: int | None, test: bool) -> dict[str, Any]:
        """通过 Telegram Bot API 推送（parse_mode=HTML）。

        config_json = {"bot_token": ..., "chat_id": ...}；bot_token 在
        落库时已被 _protect_config_json Fernet 加密，此处拿到的是解密值。
        Daily Digest 场景：首条 = 标题 + summary，content 全文按段落
        边界切 ≤3800 字符分段发送，每条间隔 0.5s 防限流。
        """
        bot_token = (config.get("bot_token") or "").strip()
        chat_id = (config.get("chat_id") or "").strip()
        if not bot_token:
            return {"success": False, "error": "Telegram bot_token 未配置"}
        if not chat_id:
            return {"success": False, "error": "Telegram chat_id 未配置"}

        if test:
            messages = [
                "<b>AlloyResearch - 测试消息</b>\n\n"
                "这是一条测试推送消息，如果您收到此消息，说明 Telegram 推送配置正确。"
            ]
        else:
            report = self.db.query(ReportMetadata).filter(ReportMetadata.id == report_id).first() if report_id else None
            digest = self._load_digest(report) if report is not None and report.report_type == "daily_digest" else None
            if digest is not None:
                title = (digest.title or "").strip() or "每日综合研报"
                summary_html = md_to_telegram_html((digest.summary_md or "").strip())
                first = f"<b>{escape(title)}</b>\n\n{summary_html}".strip()
                messages = [first]
                content = (digest.content_md or "").strip()
                if content:
                    for chunk in split_telegram_chunks(content):
                        messages.append(md_to_telegram_html(chunk))
            elif report:
                messages = [
                    f"<b>AlloyResearch报告通知</b>\n"
                    f"报告类型: {escape(str(report.report_type))}\n"
                    f"报告日期: {escape(str(report.report_date))}\n"
                    f"状态: {escape(str(report.status))}"
                ]
            else:
                messages = ["AlloyResearch - 新报告已生成\n\n请登录平台查看详细内容。"]

        api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        for idx, text in enumerate(messages):
            if idx > 0:
                time.sleep(0.5)  # 防 Telegram 限流
            try:
                response = requests.post(
                    api_url,
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                    timeout=30,
                )
            except Exception as e:
                return {"success": False, "error": f"Telegram 发送失败（第{idx + 1}条）: {e}"}
            # Telegram 返回 {"ok": true, ...}；非 JSON 响应按状态码兜底
            ok = False
            try:
                ok = response.status_code == 200 and bool(response.json().get("ok"))
            except Exception:
                ok = response.status_code == 200
            if not ok:
                return {
                    "success": False,
                    "error": f"Telegram 第{idx + 1}条发送失败: HTTP {response.status_code}: {response.text[:200]}",
                }
        return {"success": True}

    # ── P0-6: ETL failure alerting ──
    # Only active admin NotificationConfigs receive the alert. Failures
    # from the alerting path itself are swallowed so an unreachable
    # webhook never crashes the calling scheduler job.

    def _send_etl_alert_to_config(
        self, config: NotificationConfig, job_name: str, error_msg: str
    ) -> bool:
        """Push one ETL-alert payload to a single admin-owned config.

        Builds a synthetic report-shaped payload so the existing
        ``_send_webhook`` / ``_send_email`` paths can be reused without
        refactoring. Returns ``True`` on successful send.
        """
        try:
            exposed_config = self._expose_config_json(config.config_json or {})
            webhook_url = self._resolve_webhook_url(config)
            if webhook_url:
                exposed_config["webhook_url"] = webhook_url

            if _normalize_channel_type(config.channel_type, exposed_config) == "webhook":
                # Webhook path uses platform-specific payload shape;
                # bypass the report-shape branch by calling _send_webhook
                # with a synthetic ``content`` via config_json override.
                if not exposed_config.get("webhook_url"):
                    return False
                platform = exposed_config.get("platform", "wechat")
                content = (
                    f"[AlloyResearch] ETL 任务失败告警\n"
                    f"任务: {job_name}\n"
                    f"错误: {error_msg[:500]}"
                )
                if platform == "feishu":
                    payload = {"msg_type": "text", "content": {"text": content}}
                else:
                    payload = {"msgtype": "text", "text": {"content": content}}

                response = requests.post(
                    exposed_config["webhook_url"],
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=15,
                )
                return response.status_code == 200

            if config.channel_type == "email":
                # Reuse the email path with a synthesised test-like body.
                exposed_config["_etl_alert_subject"] = (
                    f"[AlloyResearch] ETL 失败: {job_name}"
                )
                exposed_config["_etl_alert_body"] = (
                    f"ETL 任务 {job_name} 执行失败。\n\n错误信息:\n{error_msg[:1500]}"
                )
                # Delegate to _send_email by wrapping the error_msg as a
                # fake report_id flow: easier to just call it directly.
                result = self._send_email(exposed_config, None, test=False)
                return bool(result.get("success"))

            return False
        except Exception as exc:  # pragma: no cover — alerting must not crash jobs
            logger.error(
                "[NotificationService] ETL alert dispatch failed: %s",
                sanitize(str(exc)),
            )
            return False

    def _send_etl_message_to_config(
        self, config: NotificationConfig, subject: str, content: str
    ) -> bool:
        """Push a free-form ops message to a single admin-owned config.

        Shares the webhook / email plumbing with the failure-alert path but
        takes an arbitrary subject + body so it can carry *completion*
        notices (ops P1-4) as well as failures.
        """
        try:
            exposed_config = self._expose_config_json(config.config_json or {})
            webhook_url = self._resolve_webhook_url(config)
            if webhook_url:
                exposed_config["webhook_url"] = webhook_url

            if _normalize_channel_type(config.channel_type, exposed_config) == "webhook":
                if not exposed_config.get("webhook_url"):
                    return False
                platform = exposed_config.get("platform", "wechat")
                if platform == "feishu":
                    payload = {"msg_type": "text", "content": {"text": content}}
                else:
                    payload = {"msgtype": "text", "text": {"content": content}}
                response = requests.post(
                    exposed_config["webhook_url"],
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=15,
                )
                return response.status_code == 200

            if config.channel_type == "email":
                exposed_config["_etl_alert_subject"] = subject
                exposed_config["_etl_alert_body"] = content
                result = self._send_email(exposed_config, None, test=False)
                return bool(result.get("success"))

            return False
        except Exception as exc:  # pragma: no cover — alerting must not crash callers
            logger.error(
                "[NotificationService] ETL message dispatch failed: %s",
                sanitize(str(exc)),
            )
            return False

    def send_etl_completion(
        self, job_name: str, status: str = "success", detail: str = ""
    ) -> int:
        """Broadcast an ETL-run completion notice to active-admin channels.

        Mirrors :meth:`send_etl_alert` but for successful / manual re-runs
        (ops P1-4). Returns the number of successful sends; failures are
        logged and swallowed so a re-run never crashes on a dead webhook.
        """
        from app.models.user import User

        admin_ids = {
            row.id
            for row in self.db.query(User.id)
            .filter(User.role == "admin", User.is_active.is_(True))
            .all()
        }
        if not admin_ids:
            return 0

        configs = (
            self.db.query(NotificationConfig)
            .filter(
                NotificationConfig.user_id.in_(admin_ids),
                NotificationConfig.is_active.is_(True),
            )
            .all()
        )
        if not configs:
            return 0

        subject = f"[AlloyResearch] ETL 任务完成: {job_name}"
        content = (
            f"[AlloyResearch] ETL 任务完成通知\n"
            f"任务: {job_name}\n"
            f"状态: {status}\n"
            f"备注: {detail or '—'}"
        )

        sent = 0
        for config in configs:
            try:
                if self._send_etl_message_to_config(config, subject, content):
                    sent += 1
            except Exception:
                continue
        return sent


    def send_etl_alert(self, job_name: str, error_msg: str) -> int:
        """Send an ETL-failure alert to every active admin-owned channel.

        Iterates over NotificationConfigs whose owner is currently an
        active admin and dispatches via each channel's normal pipeline.
        Returns the number of successful sends. Failures are logged and
        swallowed.
        """
        from app.models.user import User

        admin_ids = {
            row.id
            for row in self.db.query(User.id)
            .filter(User.role == "admin", User.is_active.is_(True))
            .all()
        }
        if not admin_ids:
            return 0

        configs = (
            self.db.query(NotificationConfig)
            .filter(
                NotificationConfig.user_id.in_(admin_ids),
                NotificationConfig.is_active.is_(True),
            )
            .all()
        )
        if not configs:
            return 0

        sent = 0
        for config in configs:
            try:
                if self._send_etl_alert_to_config(config, job_name, error_msg):
                    sent += 1
            except Exception:
                continue
        return sent

    def get_logs(
        self,
        page: int = 1,
        page_size: int = 20,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Get notification send logs with pagination.

        Returns:
            Dict with keys: items (list), total, page, page_size.
        Each item contains user_id/channel/target joined from the related
        NotificationConfig when available.
        """
        page = max(1, page)
        page_size = max(1, min(200, page_size))
        offset = (page - 1) * page_size

        query = self.db.query(NotificationLog, NotificationConfig).outerjoin(
            NotificationConfig,
            NotificationLog.config_id == NotificationConfig.id,
        )
        if user_id:
            query = query.filter(NotificationConfig.user_id == user_id)
        query = query.order_by(NotificationLog.created_at.desc())

        total = query.count()
        rows = query.offset(offset).limit(page_size).all()

        items: list[dict[str, Any]] = []
        for log, cfg in rows:
            target: str | None = None
            if cfg is not None and isinstance(cfg.config_json, dict):
                target = (
                    cfg.config_json.get("webhook_url")
                    or cfg.config_json.get("to")
                    or cfg.config_json.get("email")
                )
            items.append(
                {
                    "id": log.id,
                    "config_id": log.config_id,
                    "user_id": cfg.name if cfg is not None else None,
                    "channel": cfg.channel_type if cfg is not None else None,
                    "target": target,
                    "report_id": log.report_id,
                    "status": log.status,
                    "error": log.error_msg,
                    "sent_at": log.sent_at.isoformat() if log.sent_at else None,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
            )

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
