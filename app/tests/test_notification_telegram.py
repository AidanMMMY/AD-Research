"""B7 (2026-08-03): Telegram 通道 + Daily Digest 全文邮件测试。

Coverage:
  - split_telegram_chunks: 分段不切段落、单段超长硬切、全段越限正确累积。
  - md_to_telegram_html / md_to_email_html: HTML 转义、标题/粗体/列表转换。
  - bot_token Fernet 加密往返（create_config 落库 enc: 前缀，get_configs 解密）。
  - _send_telegram: digest 场景首条=标题+summary、content 分段发送、
    段间 sleep；sendMessage 失败 → NotificationLog failed 且不抛异常。
  - digest 邮件分支: report_type=daily_digest 走全文模板（summary+content），
    pool 报告维持既有简短模板（回归零影响）。
"""

from __future__ import annotations

from datetime import date

import pytest

from app.config import get_settings

# 注册全部 ORM 模型（create_all 需要）
import app.models  # noqa: F401
from app.models.digest import DailyDigest
from app.models.notification import NotificationConfig, NotificationLog
from app.models.scoring import ReportMetadata
from app.services import notification_service as ns
from app.services.notification_service import (
    NotificationService,
    md_to_email_html,
    md_to_telegram_html,
    split_telegram_chunks,
)

REPORT_DATE = date(2026, 8, 3)


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    """给 NotificationService 一个确定的 Fernet key（env → lru_cache 清理）。"""
    monkeypatch.setenv("NOTIFICATION_ENCRYPTION_KEY", "b7-test-encryption-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def no_sleep(monkeypatch):
    """段间 0.5s 防限流 sleep 在测试中移除。"""
    monkeypatch.setattr(ns.time, "sleep", lambda *_: None)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"ok": True}
        self.text = text

    def json(self):
        return self._payload


class FakeSMTP:
    """记录 sendmail 调用，替代真实 SMTP。"""

    instances: list["FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.sent: list[tuple[str, list[str], str]] = []
        FakeSMTP.instances.append(self)

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def sendmail(self, from_addr, to_addrs, msg):
        self.sent.append((from_addr, to_addrs, msg))

    def quit(self):
        pass


def _make_digest(db, content_md: str) -> tuple[DailyDigest, ReportMetadata]:
    metadata = ReportMetadata(
        report_type="daily_digest",
        report_date=REPORT_DATE,
        pool_id=None,
        template_id=None,
        status="success",
        format="markdown",
        file_path=None,
    )
    db.add(metadata)
    db.flush()
    digest = DailyDigest(
        report_date=REPORT_DATE,
        report_metadata_id=metadata.id,
        status="success",
        title="8月3日 每日综合研报",
        summary_md="**隔夜** 美股上涨，A股关注量能。",
        content_md=content_md,
    )
    db.add(digest)
    db.commit()
    return digest, metadata


def _make_telegram_config(db, svc: NotificationService) -> dict:
    return svc.create_config(
        name="tg-test",
        channel_type="telegram",
        config_json={"bot_token": "123:ABC-token", "chat_id": "456"},
        user_id=1,
    )


def _make_email_config(db, svc: NotificationService) -> dict:
    return svc.create_config(
        name="email-test",
        channel_type="email",
        config_json={
            "to_emails": "a@example.com",
            "smtp_host": "smtp.example.com",
            "smtp_user": "u@example.com",
            "smtp_password": "pw",
            "use_tls": True,
        },
        user_id=1,
    )


# ── 分段 ──


def test_split_chunks_respects_paragraph_boundaries():
    # 3 段各 2000 字符：limit 3800 → 前两段无法同段共存？2000+2+2000=4002>3800
    paras = ["甲" * 2000, "乙" * 2000, "丙" * 100]
    chunks = split_telegram_chunks("\n\n".join(paras), limit=3800)
    assert len(chunks) == 2
    assert chunks[0] == paras[0]
    assert chunks[1] == f"{paras[1]}\n\n{paras[2]}"
    # 段落原文完整，未被拦腰切断
    assert all(p in "".join(chunks) for p in paras)


def test_split_chunks_hard_cuts_oversized_paragraph():
    para = "长" * 8000
    chunks = split_telegram_chunks(para, limit=3800)
    assert len(chunks) == 3
    assert all(len(c) <= 3800 for c in chunks)
    assert "".join(chunks) == para


def test_split_chunks_short_text_single_chunk():
    assert split_telegram_chunks("短文", limit=3800) == ["短文"]


# ── markdown 转换与转义 ──


def test_telegram_html_escapes_and_converts():
    md = "## 一、要闻 <必读>\n\n**上涨** & 下跌\n- 项目一\n- 项目二"
    html = md_to_telegram_html(md)
    assert "<b>一、要闻 &lt;必读&gt;</b>" in html
    assert "<b>上涨</b> &amp; 下跌" in html
    assert "• 项目一" in html
    # 原始 < > 不得裸露（除转换产物 <b>）
    assert "&lt;必读&gt;" in html


def test_email_html_blocks():
    md = "# 大标题\n\n正文 **加粗** 段落\n\n- 甲\n- 乙"
    html = md_to_email_html(md)
    assert "<h1>大标题</h1>" in html
    assert "<strong>" not in html  # 最小集只用 <b>
    assert "<b>加粗</b>" in html
    assert "<ul><li>甲</li><li>乙</li></ul>" in html


def test_email_html_escapes_raw_html():
    html = md_to_email_html("正文 <script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ── 加密往返 ──


def test_bot_token_encrypted_at_rest(db_session):
    svc = NotificationService(db_session)
    created = _make_telegram_config(db_session, svc)
    row = db_session.query(NotificationConfig).filter_by(id=created["id"]).one()
    stored = row.config_json["bot_token"]
    assert stored.startswith("enc:")
    assert "123:ABC-token" not in stored
    # 对外暴露时解密回明文
    exposed = svc.get_configs(user_id=1)[0]
    assert exposed["config_json"]["bot_token"] == "123:ABC-token"


# ── Telegram 发送 ──


def test_telegram_digest_fulltext_chunked(db_session, monkeypatch, no_sleep):
    svc = NotificationService(db_session)
    content = "## 一、隔夜要闻\n\n" + ("段落甲。" * 100) + "\n\n" + ("段落乙。" * 1500)
    _, metadata = _make_digest(db_session, content)
    cfg = _make_telegram_config(db_session, svc)

    calls: list[dict] = []

    def fake_post(url, json=None, timeout=None, **kwargs):
        calls.append({"url": url, "json": json})
        return FakeResponse()

    monkeypatch.setattr(ns.requests, "post", fake_post)

    result = svc.send_notification(config_id=cfg["id"], report_id=metadata.id)
    assert result["success"] is True

    # URL 带解密后的 token；parse_mode=HTML
    assert all("bot123:ABC-token" in c["url"] for c in calls)
    assert all(c["json"]["parse_mode"] == "HTML" for c in calls)
    assert all(c["json"]["chat_id"] == "456" for c in calls)

    # 首条 = 标题 + summary
    first = calls[0]["json"]["text"]
    assert "<b>8月3日 每日综合研报</b>" in first
    assert "<b>隔夜</b> 美股上涨" in first

    # content 分段发送，段落完整
    bodies = [c["json"]["text"] for c in calls[1:]]
    assert len(bodies) >= 2
    joined = "".join(bodies)
    assert "段落甲。" in joined and "段落乙。" in joined
    assert any("<b>一、隔夜要闻</b>" in b for b in bodies)

    log = db_session.query(NotificationLog).filter_by(config_id=cfg["id"]).one()
    assert log.status == "success"
    assert log.report_id == metadata.id


def test_telegram_failure_logs_notificationlog(db_session, monkeypatch, no_sleep):
    svc = NotificationService(db_session)
    _, metadata = _make_digest(db_session, "正文")
    cfg = _make_telegram_config(db_session, svc)

    def fake_post(url, json=None, timeout=None, **kwargs):
        return FakeResponse(status_code=401, payload={"ok": False, "description": "Unauthorized"}, text="Unauthorized")

    monkeypatch.setattr(ns.requests, "post", fake_post)

    # 单渠道失败：返回 success=False，不抛异常
    result = svc.send_notification(config_id=cfg["id"], report_id=metadata.id)
    assert result["success"] is False
    assert "401" in result["error"]

    log = db_session.query(NotificationLog).filter_by(config_id=cfg["id"]).one()
    assert log.status == "failed"
    assert "401" in log.error_msg


def test_telegram_missing_token(db_session):
    svc = NotificationService(db_session)
    cfg = svc.create_config(
        name="tg-empty",
        channel_type="telegram",
        config_json={"chat_id": "456"},
        user_id=1,
    )
    result = svc.send_notification(config_id=cfg["id"], test=True)
    assert result["success"] is False
    assert "bot_token" in result["error"]


# ── 邮件 digest 分支 + pool 回归 ──


def _send_and_parse_email(db_session, monkeypatch, cfg, report_id):
    """发送并解析 MIME 邮件，返回 (subject, text_body, html_body)。"""
    from email import message_from_string
    from email.header import decode_header, make_header

    FakeSMTP.instances = []
    monkeypatch.setattr(ns.smtplib, "SMTP", FakeSMTP)
    svc = NotificationService(db_session)
    result = svc.send_notification(config_id=cfg["id"], report_id=report_id)
    assert result["success"] is True
    assert FakeSMTP.instances and FakeSMTP.instances[-1].sent

    raw = FakeSMTP.instances[-1].sent[-1][2]
    msg = message_from_string(raw)
    subject = str(make_header(decode_header(msg["Subject"])))
    bodies: dict[str, str] = {}
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype in ("text/plain", "text/html"):
            payload = part.get_payload(decode=True)
            bodies[ctype] = payload.decode(part.get_content_charset() or "utf-8")
    return subject, bodies.get("text/plain", ""), bodies.get("text/html", "")


def test_email_digest_fulltext_branch(db_session, monkeypatch):
    svc = NotificationService(db_session)
    content = "## 一、隔夜要闻\n\n正文 **重点** 内容"
    _, metadata = _make_digest(db_session, content)
    cfg = _make_email_config(db_session, svc)

    subject, text_body, html_body = _send_and_parse_email(
        db_session, monkeypatch, cfg, metadata.id
    )

    # 主题：MM-DD 每日综合研报：标题
    assert subject == "08-03 每日综合研报：8月3日 每日综合研报"
    # 全文进正文：summary + content 均在，且转成 HTML
    assert "美股上涨" in text_body
    assert "隔夜要闻" in html_body
    assert "<b>重点</b>" in html_body
    assert "/digest" in html_body


def test_email_pool_report_unchanged(db_session, monkeypatch):
    """回归：非 daily_digest 的 pool 报告维持既有简短模板。"""
    svc = NotificationService(db_session)
    pool_report = ReportMetadata(
        report_type="weekly",
        report_date=REPORT_DATE,
        pool_id=None,
        template_id=None,
        status="success",
        format="pdf",
        file_path="/tmp/x.pdf",
    )
    db_session.add(pool_report)
    db_session.commit()
    cfg = _make_email_config(db_session, svc)

    subject, text_body, html_body = _send_and_parse_email(
        db_session, monkeypatch, cfg, pool_report.id
    )

    # 旧模板特征：表格化报告通知 + "请登录平台查看详细内容"
    assert "weekly" in subject
    assert "AlloyResearch报告通知" in html_body
    assert "请登录平台查看详细内容" in text_body
    # 不得误入 digest 全文模板
    assert "每日综合研报" not in subject
    assert "/digest" not in html_body


# ── 渠道别名（2026-08-03）：wechat_work/feishu/dingtalk → webhook ──


def test_wechat_work_alias_dispatches_as_wechat(db_session, monkeypatch):
    """存量 channel_type=wechat_work 配置此前全部 Unsupported 静默失败，
    别名映射后应走 wechat 载荷格式（{"msgtype": "text"}）。"""
    svc = NotificationService(db_session)
    _, metadata = _make_digest(db_session, "正文")
    cfg = svc.create_config(
        name="wx",
        channel_type="wechat_work",
        config_json={"webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=k"},
        user_id=1,
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        ns.requests, "post",
        lambda url, json=None, **kw: calls.append({"url": url, "json": json}) or FakeResponse(),
    )

    result = svc.send_notification(config_id=cfg["id"], report_id=metadata.id)
    assert result["success"] is True
    assert len(calls) == 1
    assert calls[0]["json"]["msgtype"] == "text"
    assert "content" in calls[0]["json"]["text"]


def test_feishu_alias_dispatches_as_feishu(db_session, monkeypatch):
    """feishu 别名 → 飞书载荷（{"msg_type": "text"}）。"""
    svc = NotificationService(db_session)
    _, metadata = _make_digest(db_session, "正文")
    cfg = svc.create_config(
        name="fs",
        channel_type="feishu",
        config_json={"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/x"},
        user_id=1,
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        ns.requests, "post",
        lambda url, json=None, **kw: calls.append({"url": url, "json": json}) or FakeResponse(),
    )

    result = svc.send_notification(config_id=cfg["id"], report_id=metadata.id)
    assert result["success"] is True
    assert calls[0]["json"]["msg_type"] == "text"
    assert "text" in calls[0]["json"]["content"]


def test_dingtalk_alias_maps_platform(db_session, monkeypatch):
    """dingtalk 别名 → wechat 同款载荷但 platform=dingtalk（_send_webhook 分支）。"""
    svc = NotificationService(db_session)
    _, metadata = _make_digest(db_session, "正文")
    cfg = svc.create_config(
        name="dt",
        channel_type="dingtalk",
        config_json={"webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=t"},
        user_id=1,
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        ns.requests, "post",
        lambda url, json=None, **kw: calls.append({"url": url, "json": json}) or FakeResponse(),
    )

    result = svc.send_notification(config_id=cfg["id"], report_id=metadata.id)
    assert result["success"] is True
    assert calls[0]["json"]["msgtype"] == "text"
