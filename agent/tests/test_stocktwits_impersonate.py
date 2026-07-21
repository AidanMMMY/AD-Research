#!/usr/bin/env python3
"""Tests for stocktwits._curl_cffi_get impersonate-profile fallback.

Cloudflare rotates which TLS fingerprints it challenges (chrome124 was
blocked 2026-07-22), so the worker must walk IMPERSONATE_PROFILES on 403
instead of hardcoding a single profile. These tests mock curl_cffi so
they run without network or the curl_cffi package installed.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workers"))

import stocktwits  # noqa: E402


class _FakeResp:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text

    def json(self):
        return {}


class _FakeCreq:
    """Records requested profiles; serves per-profile status codes."""

    def __init__(self, status_by_profile: dict[str, int] | None = None, exc_profiles=()):
        self.status_by_profile = status_by_profile or {}
        self.exc_profiles = set(exc_profiles)
        self.calls: list[str] = []

    def get(self, url, impersonate=None, timeout=None):
        self.calls.append(impersonate)
        if impersonate in self.exc_profiles:
            raise ConnectionError("Recv failure: Connection reset by peer")
        return _FakeResp(self.status_by_profile.get(impersonate, 200))


@pytest.fixture()
def fake_creq(monkeypatch):
    def _install(fake: _FakeCreq) -> _FakeCreq:
        monkeypatch.setattr(stocktwits, "_HAS_CURL_CFFI", True)
        monkeypatch.setattr(stocktwits, "creq", fake)
        # No real sleeping on the exception-retry path.
        monkeypatch.setattr(stocktwits.time, "sleep", lambda *_a, **_k: None)
        return fake

    return _install


LOG = logging.getLogger("test.stocktwits")


def test_falls_back_to_next_profile_on_403(fake_creq):
    first, second = stocktwits.IMPERSONATE_PROFILES[:2]
    fake = fake_creq(_FakeCreq({first: 403}))
    resp = stocktwits._curl_cffi_get("https://example.com/x", LOG)
    assert resp is not None
    assert resp.status_code == 200
    # 403 on the first profile must advance to the second, not retry it.
    assert fake.calls == [first, second]


def test_returns_none_when_every_profile_403(fake_creq):
    fake = fake_creq(_FakeCreq({p: 403 for p in stocktwits.IMPERSONATE_PROFILES}))
    resp = stocktwits._curl_cffi_get("https://example.com/x", LOG)
    assert resp is None
    assert fake.calls == stocktwits.IMPERSONATE_PROFILES


def test_connection_error_retries_then_next_profile(fake_creq):
    first, second = stocktwits.IMPERSONATE_PROFILES[:2]
    fake = fake_creq(_FakeCreq(exc_profiles={first}))
    resp = stocktwits._curl_cffi_get("https://example.com/x", LOG, retries=1)
    assert resp is not None
    assert resp.status_code == 200
    # First profile retried once (2 calls), then second profile succeeds.
    assert fake.calls == [first, first, second]


def test_returns_none_without_curl_cffi(monkeypatch):
    monkeypatch.setattr(stocktwits, "_HAS_CURL_CFFI", False)
    assert stocktwits._curl_cffi_get("https://example.com/x", LOG) is None
