"""SSRF guard tests for notification webhooks (audit 2026-08-06)."""

import pytest

from app.services.notification_service import _validate_webhook_url


def test_accepts_public_https_webhook():
    _validate_webhook_url("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc")


def test_accepts_public_http_webhook():
    _validate_webhook_url("http://example.com/hook")


def test_rejects_non_http_scheme():
    with pytest.raises(ValueError):
        _validate_webhook_url("file:///etc/passwd")
    with pytest.raises(ValueError):
        _validate_webhook_url("ftp://example.com/hook")


def test_rejects_localhost():
    with pytest.raises(ValueError):
        _validate_webhook_url("http://localhost:8000/hook")
    with pytest.raises(ValueError):
        _validate_webhook_url("http://127.0.0.1/hook")


def test_rejects_private_ipv4():
    for url in (
        "http://10.0.0.5/hook",
        "http://172.16.0.1/hook",
        "http://192.168.1.1/hook",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.100.100.200/latest/meta-data/",
    ):
        with pytest.raises(ValueError):
            _validate_webhook_url(url)


def test_rejects_private_ipv6():
    with pytest.raises(ValueError):
        _validate_webhook_url("http://[::1]/hook")
    with pytest.raises(ValueError):
        _validate_webhook_url("http://[fc00::1]/hook")


def test_rejects_dotlocal_hostname():
    with pytest.raises(ValueError):
        _validate_webhook_url("http://myhost.local/hook")
