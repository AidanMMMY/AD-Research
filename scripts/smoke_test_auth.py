"""Smoke test for the 6 routers that just got router-level auth.

Verifies that for each of etfs / pools / signals / backtests / market_data / strategies:
  - request WITHOUT a token         -> 401
  - request with FAKE token         -> 401
  - request with VALID admin token  -> 200 (or 2xx)

Reads BASE_URL, LOGIN_USER, LOGIN_PASSWORD from env.

Usage:
  pip install requests
  BASE_URL=http://localhost:8000/api/v1 \
  LOGIN_USER=admin LOGIN_PASSWORD=changeme \
  python scripts/smoke_test_auth.py

The script is read-only and never writes to disk beyond stdout.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Callable

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000/api/v1").rstrip("/")
LOGIN_USER = os.getenv("LOGIN_USER", "admin")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "")

# GET endpoints that should be cheap & safe. (one per router for breadth)
# Keep these stable; if a router changes paths, update here too.
GET_PROBES: dict[str, str] = {
    "etfs":        "/etfs?page=1&page_size=1",
    "pools":       "/pools",
    "signals":     "/signals?limit=1",
    "backtests":   "/backtests?limit=1",
    "market_data": "/market-data/snapshot?codes=510300",   # any known ETF code
    "strategies":  "/strategies",
}

EXPECT_AUTH = 401
EXPECT_OK_MIN = 200
EXPECT_OK_MAX = 299

FAKE_TOKEN = "this.is.not.a.real.jwt"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def login(username: str, password: str) -> str:
    """POST /auth/login, return the access_token (raise on failure)."""
    url = f"{BASE_URL}/auth/login"
    r = requests.post(url, json={"username": username, "password": password}, timeout=15)
    r.raise_for_status()
    data = r.json()
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"login response missing access_token: {data!r}")
    return token


def hit(method: str, path: str, token: str | None) -> requests.Response:
    url = f"{BASE_URL}{path}"
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, url, headers=headers, timeout=15)


def expect(actual: int, expected: int, label: str) -> bool:
    ok = actual == expected
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}: got {actual}, expected {expected}")
    return ok


def expect_2xx(actual: int, label: str) -> bool:
    ok = EXPECT_OK_MIN <= actual <= EXPECT_OK_MAX
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}: got {actual}, expected 2xx")
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def probe_one(router: str, path: str, token: str | None, label: str) -> bool:
    """One (router, scenario) round-trip. Returns True on expected result."""
    try:
        r = hit("GET", path, token)
        status = r.status_code
    except requests.RequestException as exc:
        print(f"  [FAIL] {label}: request error: {exc}")
        return False
    if label.startswith("no-token"):
        return expect(status, EXPECT_AUTH, label)
    if label.startswith("fake-token"):
        return expect(status, EXPECT_AUTH, label)
    if label.startswith("valid-token"):
        return expect_2xx(status, label)
    return False


def main() -> int:
    print(f"BASE_URL = {BASE_URL}")
    if not LOGIN_PASSWORD:
        print("WARN: LOGIN_PASSWORD not set — valid-token scenario will be skipped.")

    # Acquire a real admin token (optional)
    real_token: str | None = None
    if LOGIN_PASSWORD:
        try:
            t0 = time.time()
            real_token = login(LOGIN_USER, LOGIN_PASSWORD)
            print(f"login OK as {LOGIN_USER} (took {time.time() - t0:.2f}s)")
        except Exception as exc:  # noqa: BLE001
            print(f"login FAILED: {exc}")
            print("  → valid-token scenario will be reported as FAIL")

    total = 0
    passed = 0
    for router, path in GET_PROBES.items():
        print(f"\n== {router} :: GET {path} ==")
        scenarios: list[tuple[str, str | None]] = [
            ("no-token", None),
            ("fake-token", FAKE_TOKEN),
        ]
        if real_token:
            scenarios.append(("valid-token", real_token))
        for label, tok in scenarios:
            total += 1
            if probe_one(router, path, tok, label):
                passed += 1

    print(f"\nSummary: {passed}/{total} probes matched expectation")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
