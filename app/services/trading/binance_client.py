"""Binance signed REST client for live trading (Phase 3).

Supports both testnet (https://testnet.binance.vision) and production
(https://api.binance.com) endpoints.  All account/trade endpoints require
HMAC-SHA256 signed requests.

Security:
  - API credentials are passed at construction time, never logged.
  - ``_sign()`` uses HMAC-SHA256 per Binance spec.
  - Rate limiting: respects Binance weight system by sleeping between calls.

Usage::

    client = BinanceClient(api_key="...", api_secret="...", testnet=True)
    account = client.get_account_info()
    order = client.place_order("BTCUSDT", "BUY", "0.001", order_type="LIMIT", price=50000)
"""

import hashlib
import hmac
import json
import time
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import requests


class BinanceClientError(Exception):
    """Raised when a Binance API call fails."""


_BASE_URL_PROD = "https://api.binance.com"
_BASE_URL_TESTNET = "https://testnet.binance.vision"


class BinanceClient:
    """Signed Binance REST client.

    Public endpoints (kline, ticker, exchangeInfo) are served by
    ``BinanceProvider``.  This client handles **authenticated** endpoints
    (account, order, trade history).

    Parameters:
        api_key: Binance API key.
        api_secret: Binance API secret.
        testnet: If True, use testnet.binance.vision.
        recv_window: Millisecond receive window (default 5000).
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        recv_window: int = 5000,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = _BASE_URL_TESTNET if testnet else _BASE_URL_PROD
        self.recv_window = recv_window
        self._last_request_time = 0.0

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        """Ensure at least 0.1 s between signed requests (1200 weight/min)."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < 0.1:
            time.sleep(0.1 - elapsed)
        self._last_request_time = time.monotonic()

    # ------------------------------------------------------------------
    # HMAC-SHA256 signing
    # ------------------------------------------------------------------

    def _sign(self, params: dict[str, Any]) -> str:
        """Return HMAC-SHA256 signature for the given params dict."""
        query_string = urlencode(params)
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _build_params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build a signed parameter dict with timestamp and recvWindow."""
        params: dict[str, Any] = {
            "timestamp": int(time.time() * 1000),
            "recvWindow": self.recv_window,
        }
        if extra:
            params.update(extra)
        params["signature"] = self._sign(params)
        return params

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict:
        """Send a signed GET request."""
        self._throttle()
        signed_params = self._build_params(params)
        url = f"{self.base_url}{endpoint}"
        headers = {"X-MBX-APIKEY": self.api_key}
        try:
            resp = requests.get(url, params=signed_params, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise BinanceClientError(f"GET {endpoint} failed: {exc}") from exc

    def _post(self, endpoint: str, params: dict[str, Any] | None = None) -> dict:
        """Send a signed POST request."""
        self._throttle()
        signed_params = self._build_params(params)
        url = f"{self.base_url}{endpoint}"
        headers = {"X-MBX-APIKEY": self.api_key}
        try:
            resp = requests.post(url, params=signed_params, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise BinanceClientError(f"POST {endpoint} failed: {exc}") from exc

    def _delete(self, endpoint: str, params: dict[str, Any] | None = None) -> dict:
        """Send a signed DELETE request."""
        self._throttle()
        signed_params = self._build_params(params)
        url = f"{self.base_url}{endpoint}"
        headers = {"X-MBX-APIKEY": self.api_key}
        try:
            resp = requests.delete(url, params=signed_params, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise BinanceClientError(f"DELETE {endpoint} failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Symbol helpers (shared convention with BinanceProvider)
    # ------------------------------------------------------------------

    @staticmethod
    def to_binance_symbol(code: str) -> str:
        """Convert internal code to Binance trading pair.

        >>> BinanceClient.to_binance_symbol("BTC.US")
        'BTCUSDT'
        """
        if code.endswith(".US"):
            return code[:-3] + "USDT"
        return code + "USDT"

    @staticmethod
    def from_binance_symbol(symbol: str) -> str:
        """Convert Binance trading pair to internal code.

        >>> BinanceClient.from_binance_symbol("BTCUSDT")
        'BTC.US'
        """
        if symbol.endswith("USDT"):
            return symbol[:-4] + ".US"
        return symbol + ".US"

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Check connectivity (public endpoint, no auth required)."""
        try:
            resp = requests.get(f"{self.base_url}/api/v3/ping", timeout=10)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    # ------------------------------------------------------------------
    # Low-risk: read-only account endpoints
    # ------------------------------------------------------------------

    def get_account_info(self) -> dict:
        """GET /api/v3/account — return full account information."""
        return self._get("/api/v3/account")

    def get_balances(self) -> dict[str, dict]:
        """Return non-zero balances keyed by asset.

        Each value is a dict with ``free``, ``locked``, ``total`` as Decimals.
        """
        account = self.get_account_info()
        balances: dict[str, dict] = {}
        for b in account.get("balances", []):
            free = Decimal(b.get("free", "0"))
            locked = Decimal(b.get("locked", "0"))
            total = free + locked
            if total > 0:
                balances[b["asset"]] = {
                    "free": free,
                    "locked": locked,
                    "total": total,
                }
        return balances

    def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        """GET /api/v3/openOrders — return all open orders.

        Args:
            symbol: Optional Binance symbol filter (e.g. "BTCUSDT").
        """
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        return self._get("/api/v3/openOrders", params)

    def get_order_history(
        self, symbol: str | None = None, limit: int = 50
    ) -> list[dict]:
        """GET /api/v3/allOrders — return order history."""
        params: dict[str, Any] = {"limit": min(limit, 1000)}
        if symbol:
            params["symbol"] = symbol
        return self._get("/api/v3/allOrders", params)

    def get_trades(
        self, symbol: str | None = None, limit: int = 50
    ) -> list[dict]:
        """GET /api/v3/myTrades — return trade history."""
        params: dict[str, Any] = {"limit": min(limit, 1000)}
        if symbol:
            params["symbol"] = symbol
        return self._get("/api/v3/myTrades", params)

    def get_exchange_info(self) -> dict:
        """GET /api/v3/exchangeInfo — return exchange trading rules."""
        try:
            resp = requests.get(
                f"{self.base_url}/api/v3/exchangeInfo", timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise BinanceClientError(f"exchangeInfo failed: {exc}") from exc

    def get_ticker_price(self, symbol: str) -> Decimal | None:
        """GET /api/v3/ticker/price — return last price for a symbol."""
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        try:
            resp = requests.get(
                f"{self.base_url}/api/v3/ticker/price",
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return Decimal(str(data.get("price", 0)))
            return Decimal(str(data[0].get("price", 0))) if data else None
        except requests.RequestException as exc:
            raise BinanceClientError(f"ticker/price failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Medium-risk: write endpoints (order placement / cancellation)
    # ------------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        order_type: str = "LIMIT",
        price: Decimal | None = None,
        time_in_force: str = "GTC",
    ) -> dict:
        """POST /api/v3/order — place a new order.

        Args:
            symbol: Binance trading pair (e.g. "BTCUSDT").
            side: "BUY" or "SELL".
            quantity: Base asset quantity as Decimal.
            order_type: "LIMIT" or "MARKET".
            price: Limit price (required for LIMIT orders).
            time_in_force: "GTC", "IOC", or "FOK" (limit orders only).

        Returns:
            The full Binance order response dict.
        """
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(quantity),
        }

        if order_type.upper() == "LIMIT":
            if price is None:
                raise BinanceClientError("price is required for LIMIT orders")
            params["price"] = str(price)
            params["timeInForce"] = time_in_force

        return self._post("/api/v3/order", params)

    def cancel_order(self, symbol: str, order_id: int | str) -> dict:
        """DELETE /api/v3/order — cancel an open order.

        Args:
            symbol: Binance trading pair (e.g. "BTCUSDT").
            order_id: Binance order ID to cancel.

        Returns:
            The cancelled order response dict.
        """
        return self._delete(
            "/api/v3/order",
            {"symbol": symbol.upper(), "orderId": str(order_id)},
        )

    def get_order(self, symbol: str, order_id: int | str) -> dict:
        """GET /api/v3/order — check an order's status."""
        return self._get(
            "/api/v3/order",
            {"symbol": symbol.upper(), "orderId": str(order_id)},
        )
