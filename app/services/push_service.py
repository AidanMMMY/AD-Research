"""APNs (Apple Push Notification service) integration.

Requires:
  - httpx with HTTP/2 support (already in pyproject.toml extras)
  - APNs Auth Key (.p8 file) from Apple Developer Console
  - Team ID + Key ID from Apple Developer Console

Configuration (environment variables):
  APNS_KEY_PATH      - Path to .p8 private key file
  APNS_KEY_ID        - Key ID from Apple Developer
  APNS_TEAM_ID       - Apple Developer Team ID
  APNS_TOPIC         - App Bundle ID (e.g. com.adresearch.ios)
  APNS_USE_SANDBOX   - "true" for development, "false" for production
"""

import datetime
import json
import logging
import time
from pathlib import Path
from typing import Optional

import httpx
from jose import jwt

from app.config import push_settings

logger = logging.getLogger(__name__)

# ── Constants ──
APNS_DEVELOPMENT_URL = "https://api.sandbox.push.apple.com/3/device"
APNS_PRODUCTION_URL = "https://api.push.apple.com/3/device"
JWT_ALGORITHM = "ES256"
JWT_EXPIRATION_SECONDS = 3600  # 1 hour
MAX_CONCURRENT_PUSHES = 10


class PushService:
    """Send push notifications via APNs HTTP/2 API."""

    def __init__(self):
        self.key_path = push_settings.apns_key_path or None
        self.key_id = push_settings.apns_key_id or None
        self.team_id = push_settings.apns_team_id or None
        self.topic = push_settings.apns_topic or None
        self.use_sandbox = push_settings.apns_use_sandbox

        self._key_data: Optional[str] = None
        self._jwt: Optional[str] = None
        self._jwt_expires_at: float = 0.0

        self.base_url = APNS_DEVELOPMENT_URL if self.use_sandbox else APNS_PRODUCTION_URL

    @property
    def configured(self) -> bool:
        """Return True if all required APNs config is present."""
        return all([self.key_path, self.key_id, self.team_id, self.topic])

    # ── Private helpers ──

    def _load_key(self) -> str:
        """Load the .p8 private key from disk (cached)."""
        if self._key_data is not None:
            return self._key_data

        if not self.key_path:
            raise RuntimeError("APNS_KEY_PATH is not configured")

        key_file = Path(self.key_path)
        if not key_file.exists():
            raise FileNotFoundError(f"APNs key file not found: {self.key_path}")

        self._key_data = key_file.read_text()
        return self._key_data

    def _generate_jwt(self) -> str:
        """Generate a JWT for APNs authentication (cached for 1 hour)."""
        now = time.time()
        if self._jwt and now < self._jwt_expires_at - 60:
            return self._jwt

        if not all([self.key_id, self.team_id]):
            raise RuntimeError("APNS_KEY_ID and APNS_TEAM_ID must be configured")

        key_data = self._load_key()
        headers = {"kid": self.key_id}
        payload = {
            "iss": self.team_id,
            "iat": int(now),
            "exp": int(now + JWT_EXPIRATION_SECONDS),
        }

        self._jwt = jwt.encode(payload, key_data, algorithm=JWT_ALGORITHM, headers=headers)
        self._jwt_expires_at = now + JWT_EXPIRATION_SECONDS
        return self._jwt

    # ── Public API ──

    async def send_push(
        self,
        device_token: str,
        title: str,
        body: str,
        badge: Optional[int] = None,
        sound: str = "default",
        category: Optional[str] = None,
        custom_payload: Optional[dict] = None,
    ) -> bool:
        """Send a push notification to a single device.

        Args:
            device_token: APNs device token (hex string)
            title: Notification title
            body: Notification body
            badge: Optional badge number
            sound: Notification sound ("default" or None for silent)
            category: Optional notification category (for action buttons)
            custom_payload: Optional custom data to include

        Returns:
            True if the push was sent successfully.
        """
        if not self.configured:
            logger.warning("APNs not configured, skipping push")
            return False

        jwt_token = self._generate_jwt()
        url = f"{self.base_url}/{device_token}"

        aps: dict = {
            "alert": {
                "title": title,
                "body": body,
            },
        }
        if badge is not None:
            aps["badge"] = badge
        if sound:
            aps["sound"] = sound
        if category:
            aps["category"] = category

        payload = {"aps": aps}
        if custom_payload:
            payload.update(custom_payload)

        headers = {
            "authorization": f"bearer {jwt_token}",
            "apns-topic": self.topic,
            "apns-push-type": "alert",
            "apns-expiration": "0",
            "apns-priority": "10",
        }

        try:
            async with httpx.AsyncClient(http2=True, timeout=10) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 200:
                    logger.info(f"Push sent to {device_token[:8]}...: {title}")
                    return True
                else:
                    logger.error(
                        f"APNs error ({response.status_code}): {response.text} "
                        f"for device {device_token[:8]}..."
                    )
                    return False
        except Exception as e:
            logger.error(f"APNs request failed: {e}")
            return False

    async def send_price_alert(
        self,
        device_token: str,
        code: str,
        name: str,
        price: float,
        change_pct: float,
    ) -> bool:
        """Send a price alert push notification."""
        direction = "📈" if change_pct >= 0 else "📉"
        title = f"{direction} {code} {name}"
        body = f"当前价格 ¥{price:.3f} · {'+' if change_pct >= 0 else ''}{change_pct:.2f}%"
        custom = {
            "type": "price_alert",
            "code": code,
            "price": price,
            "change_pct": change_pct,
        }
        return await self.send_push(
            device_token=device_token,
            title=title,
            body=body,
            custom_payload=custom,
        )

    async def send_signal_alert(
        self,
        device_token: str,
        code: str,
        name: str,
        signal_type: str,
    ) -> bool:
        """Send a trading signal alert push notification."""
        signal_emoji = {"BUY": "🔴", "SELL": "🟢", "HOLD": "⚪️"}.get(signal_type, "📊")
        signal_label = {"BUY": "买入信号", "SELL": "卖出信号", "HOLD": "持有信号"}.get(signal_type, signal_type)
        title = f"{signal_emoji} {signal_label}"
        body = f"{code} {name}"
        custom = {"type": "signal", "code": code, "signal_type": signal_type}
        return await self.send_push(
            device_token=device_token,
            title=title,
            body=body,
            custom_payload=custom,
        )

    async def send_report_ready(
        self,
        device_token: str,
        report_type: str,
        report_date: str,
    ) -> bool:
        """Notify user that a report has been generated."""
        return await self.send_push(
            device_token=device_token,
            title="📄 报告已生成",
            body=f"{report_type} ({report_date}) 已准备就绪",
            custom_payload={"type": "report_ready", "report_type": report_type, "report_date": report_date},
        )


# ── Singleton ──

_push_service: Optional[PushService] = None


def get_push_service() -> PushService:
    """Return a singleton PushService instance."""
    global _push_service
    if _push_service is None:
        _push_service = PushService()
    return _push_service
