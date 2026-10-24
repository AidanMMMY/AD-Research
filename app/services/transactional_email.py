"""Thin transactional email wrapper (self-registration, 2026-10-25).

Semantics aligned with ``NotificationService._send_email``: port 465 =
implicit SSL (``SMTP_SSL`` direct connect — 163/QQ default; STARTTLS on
an implicit-SSL port hangs the handshake), every other port connects in
the clear then upgrades via STARTTLS when configured. The global SMTP_*
settings are the single source of configuration.

Safety contract:
  * never raises — the register endpoint must still return 201 so the
    frontend's resend flow stays available when the SMTP leg fails;
  * never logs the message body (the verification email carries the
    plaintext code) — failures log only the exception type + sanitized
    message;
  * one synchronous retry on failure (registration volume is tiny; no
    queue complexity per design §3.3).
"""

from __future__ import annotations

import contextlib
import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings
from app.core.log_sanitize import sanitize

logger = logging.getLogger(__name__)

_RETRY_DELAY_SECONDS = 1.0
_SMTP_TIMEOUT_SECONDS = 30


def _build_message(
    settings, to: str, subject: str, html_body: str, text_body: str
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _send_via_smtp(settings, msg: MIMEMultipart, to: str) -> None:
    """One SMTP attempt. Port 465 → SMTP_SSL; otherwise STARTTLS path."""
    from_addr = msg["From"]
    if settings.smtp_port == 465:
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=_SMTP_TIMEOUT_SECONDS
        )
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=_SMTP_TIMEOUT_SECONDS)
    try:
        if settings.smtp_port != 465 and settings.smtp_use_tls:
            server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(from_addr, [to], msg.as_string())
    finally:
        with contextlib.suppress(Exception):
            server.quit()


def send_email(to: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send one transactional email; retry once; never raise.

    Returns ``True`` on successful dispatch. SMTP unconfigured → log a
    warning (no code, no body) and return ``False``.
    """
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_user or not settings.smtp_password:
        logger.warning("transactional email skipped: SMTP not configured (subject=%r)", subject)
        return False

    msg = _build_message(settings, to, subject, html_body, text_body)
    for attempt in (1, 2):
        try:
            _send_via_smtp(settings, msg, to)
            return True
        except Exception as exc:
            # Exception text can carry server replies only — never the
            # message body — but sanitize defensively anyway.
            logger.warning(
                "transactional email attempt %d failed: %s: %s (subject=%r)",
                attempt,
                type(exc).__name__,
                sanitize(str(exc)),
                subject,
            )
            if attempt == 1:
                time.sleep(_RETRY_DELAY_SECONDS)
    return False
