"""SMTP SSL/STARTTLS 分支测试（2026-08-03 163 邮箱接入）。

465 = 隐式 SSL（163/QQ 默认），必须 SMTP_SSL 直连；其余端口走 STARTTLS。
config_json 的 ``use_ssl`` 可显式覆盖端口推断。
"""

from __future__ import annotations

import app.services.notification_service as ns
from app.services.notification_service import NotificationService


class _FakeSMTPBase:
    instances: list[_FakeSMTPBase] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.tls_started = False
        self.logged_in = False
        self.sent = []
        type(self).instances.append(self)

    def starttls(self):
        self.tls_started = True

    def login(self, user, password):
        self.logged_in = True

    def sendmail(self, from_addr, to_addrs, msg):
        self.sent.append((from_addr, to_addrs, msg))

    def quit(self):
        pass


class FakeSMTPPlain(_FakeSMTPBase):
    instances: list[_FakeSMTPBase] = []


class FakeSMTPSSL(_FakeSMTPBase):
    instances: list[_FakeSMTPBase] = []


def _patch_smtp(monkeypatch):
    FakeSMTPPlain.instances = []
    FakeSMTPSSL.instances = []
    monkeypatch.setattr(ns.smtplib, "SMTP", FakeSMTPPlain)
    monkeypatch.setattr(ns.smtplib, "SMTP_SSL", FakeSMTPSSL)


def _config(**overrides):
    base = {
        "to_emails": "a@example.com",
        "smtp_host": "smtp.163.com",
        "smtp_user": "bot@163.com",
        "smtp_password": "secret",
    }
    base.update(overrides)
    return base


def test_port_465_uses_implicit_ssl(db_session, monkeypatch):
    """465 端口 → SMTP_SSL 直连，不走 STARTTLS。"""
    _patch_smtp(monkeypatch)
    service = NotificationService(db_session)
    result = service._send_email(_config(smtp_port=465), report_id=None, test=True)
    assert result["success"] is True
    assert len(FakeSMTPSSL.instances) == 1
    assert FakeSMTPSSL.instances[0].port == 465
    assert FakeSMTPSSL.instances[0].tls_started is False
    assert FakeSMTPSSL.instances[0].logged_in is True
    assert len(FakeSMTPPlain.instances) == 0


def test_port_587_uses_starttls(db_session, monkeypatch):
    """587 端口 → 明文连接 + STARTTLS。"""
    _patch_smtp(monkeypatch)
    service = NotificationService(db_session)
    result = service._send_email(_config(smtp_port=587), report_id=None, test=True)
    assert result["success"] is True
    assert len(FakeSMTPPlain.instances) == 1
    assert FakeSMTPPlain.instances[0].tls_started is True
    assert len(FakeSMTPSSL.instances) == 0


def test_use_ssl_explicit_override(db_session, monkeypatch):
    """config_json use_ssl=true 可覆盖端口推断（如 994 这类非标 SSL 端口）。"""
    _patch_smtp(monkeypatch)
    service = NotificationService(db_session)
    result = service._send_email(
        _config(smtp_port=994, use_ssl=True), report_id=None, test=True
    )
    assert result["success"] is True
    assert len(FakeSMTPSSL.instances) == 1
    assert FakeSMTPSSL.instances[0].port == 994
    assert len(FakeSMTPPlain.instances) == 0
