"""2026-08-17 安全审计 LOW：通知配置敏感字段掩码协议测试。

覆盖：
  - 读取路径（create/get_configs/update 响应）只回 "****"+末4位 掩码，
    明文绝不下发；过短的 secret 整体遮蔽。
  - 更新路径：掩码回传 / 空值 → 保留库里的加密原值；真实新值 → 重新加密。
  - webhook_url（独立加密列）：读取回掩码；掩码回传保留原值，新值重加密。
  - 发送链路（_expose_config_json）内部仍拿明文，不受掩码影响。
"""

from __future__ import annotations

import pytest

import app.models  # noqa: F401  # 注册全部 ORM 模型（create_all 需要）
from app.config import get_settings
from app.models.notification import NotificationConfig
from app.services import notification_service as ns
from app.services.notification_service import NotificationService

BOT_TOKEN = "123456:ABC-DEF-token"  # 末 4 位 "oken"
WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=abc123XYZ9"


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    """确定的 Fernet key（env → lru_cache 清理）。"""
    monkeypatch.setenv("NOTIFICATION_ENCRYPTION_KEY", "mask-test-encryption-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def no_url_validation(monkeypatch):
    """webhook 用例跳过 SSRF/DNS 校验（离线测试环境）。"""
    monkeypatch.setattr(ns, "_validate_webhook_url", lambda url: None)


def _make_telegram(svc: NotificationService) -> dict:
    return svc.create_config(
        name="tg",
        channel_type="telegram",
        config_json={"bot_token": BOT_TOKEN, "chat_id": "42"},
        user_id=1,
    )


# ── 读取路径掩码 ──


def test_read_paths_return_mask_not_plaintext(db_session):
    svc = NotificationService(db_session)
    created = _make_telegram(svc)

    assert created["config_json"]["bot_token"] == "****oken"
    assert BOT_TOKEN not in str(created)

    listed = svc.get_configs(user_id=1)[0]
    assert listed["config_json"]["bot_token"] == "****oken"
    assert BOT_TOKEN not in str(listed)
    # 非敏感字段不受影响
    assert listed["config_json"]["chat_id"] == "42"


def test_short_secret_fully_masked(db_session):
    """≤4 字符的 secret 不暴露任何字符（掩码即全文的风险）。"""
    svc = NotificationService(db_session)
    created = svc.create_config(
        name="t",
        channel_type="telegram",
        config_json={"bot_token": "abc", "chat_id": "1"},
        user_id=1,
    )
    assert created["config_json"]["bot_token"] == "****"


def test_smtp_password_masked(db_session):
    svc = NotificationService(db_session)
    created = svc.create_config(
        name="mail",
        channel_type="email",
        config_json={"to_emails": "a@example.com", "smtp_password": "s3cret-passw0rd"},
        user_id=1,
    )
    assert created["config_json"]["smtp_password"] == "****w0rd"
    assert "s3cret-passw0rd" not in str(created)


# ── 更新路径：留空/掩码保留原值，新值重加密 ──


@pytest.mark.parametrize("echoed", ["****oken", "", "   "])
def test_update_masked_or_blank_keeps_original(db_session, echoed):
    svc = NotificationService(db_session)
    created = _make_telegram(svc)
    stored_before = db_session.get(NotificationConfig, created["id"]).config_json["bot_token"]
    assert stored_before.startswith("enc:")

    res = svc.update_config(
        created["id"],
        user_id=1,
        config_json={"bot_token": echoed, "chat_id": "42"},
    )

    row = db_session.get(NotificationConfig, created["id"])
    assert row.config_json["bot_token"] == stored_before
    assert svc._decrypt_value(row.config_json["bot_token"]) == BOT_TOKEN
    # 响应同样只回掩码
    assert res["config_json"]["bot_token"] == "****oken"


def test_update_new_secret_reencrypts(db_session):
    svc = NotificationService(db_session)
    created = _make_telegram(svc)
    stored_before = db_session.get(NotificationConfig, created["id"]).config_json["bot_token"]

    res = svc.update_config(
        created["id"],
        user_id=1,
        config_json={"bot_token": "777:BRAND-new1", "chat_id": "42"},
    )

    row = db_session.get(NotificationConfig, created["id"])
    stored = row.config_json["bot_token"]
    assert stored.startswith("enc:") and stored != stored_before
    assert svc._decrypt_value(stored) == "777:BRAND-new1"
    assert res["config_json"]["bot_token"] == "****new1"


# ── webhook_url（独立加密列）掩码协议 ──


def test_webhook_url_masked_on_read(db_session, no_url_validation):
    svc = NotificationService(db_session)
    created = svc.create_config(
        name="wx",
        channel_type="webhook",
        config_json={"platform": "wechat", "webhook_url": WEBHOOK_URL},
        user_id=1,
    )
    assert created["config_json"]["webhook_url"] == "****XYZ9"
    assert WEBHOOK_URL not in str(created)

    listed = svc.get_configs(user_id=1)[0]
    assert listed["config_json"]["webhook_url"] == "****XYZ9"
    assert WEBHOOK_URL not in str(listed)


def test_webhook_url_masked_echo_keeps_column(db_session, no_url_validation):
    svc = NotificationService(db_session)
    created = svc.create_config(
        name="wx",
        channel_type="webhook",
        config_json={"platform": "wechat", "webhook_url": WEBHOOK_URL},
        user_id=1,
    )
    enc_before = db_session.get(NotificationConfig, created["id"]).webhook_url_encrypted

    # 掩码回传 = 不修改
    svc.update_config(
        created["id"],
        user_id=1,
        config_json={"platform": "wechat", "webhook_url": "****XYZ9"},
    )
    row = db_session.get(NotificationConfig, created["id"])
    assert row.webhook_url_encrypted == enc_before
    assert svc._decrypt_webhook_url(row.webhook_url_encrypted) == WEBHOOK_URL

    # 新值 = 重新加密入库
    new_url = "https://example.com/hook?key=NEWKEY99"
    svc.update_config(
        created["id"],
        user_id=1,
        config_json={"platform": "wechat", "webhook_url": new_url},
    )
    row = db_session.get(NotificationConfig, created["id"])
    assert row.webhook_url_encrypted != enc_before
    assert svc._decrypt_webhook_url(row.webhook_url_encrypted) == new_url


# ── 发送链路不受影响（内部仍用明文） ──


def test_send_path_still_uses_plaintext(db_session, monkeypatch):
    svc = NotificationService(db_session)
    created = _make_telegram(svc)

    calls: list[dict] = []

    class _Resp:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"ok": True}

    monkeypatch.setattr(
        ns.requests,
        "post",
        lambda url, json=None, **kw: calls.append({"url": url, "json": json}) or _Resp(),
    )

    result = svc.send_notification(config_id=created["id"], test=True)
    assert result["success"] is True
    assert f"bot{BOT_TOKEN}" in calls[0]["url"]
