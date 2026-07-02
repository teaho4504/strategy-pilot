from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import httpx

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class KiwoomAuthError(RuntimeError):
    pass


class TokenManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._token: str | None = None
        self._expires_at: datetime | None = None

    async def get_access_token(self) -> str:
        if self.settings.kiwoom_mode != "live":
            raise KiwoomAuthError("KIWOOM_MODE is not live; token issuance is disabled in mock mode.")
        if not self.settings.kiwoom_configured:
            missing = ", ".join(self.settings.missing_kiwoom_env)
            raise KiwoomAuthError(f"Missing Kiwoom credentials: {missing}")
        if self._token and self._expires_at and self._expires_at > datetime.now(timezone.utc) + timedelta(minutes=1):
            return self._token

        payload = {
            "grant_type": "client_credentials",
            "appkey": self.settings.kiwoom_app_key,
            "secretkey": self.settings.kiwoom_secret_key,
        }
        url = f"{self.settings.kiwoom_base_url}/oauth2/token"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(url, json=payload, headers={"Content-Type": "application/json;charset=UTF-8"})
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise KiwoomAuthError(f"Kiwoom token request failed: {exc}") from exc
        except ValueError as exc:
            raise KiwoomAuthError("Kiwoom token response was not JSON") from exc

        token = str(data.get("token") or "")
        if not token:
            raise KiwoomAuthError(f"Kiwoom token missing in response: {self._mask(data)}")

        self._token = token
        self._expires_at = self._parse_expires_at(data.get("expires_dt"))
        logger.info("Kiwoom access token issued; expires_at=%s", self._expires_at.isoformat())
        return token

    @staticmethod
    def _parse_expires_at(value: Any) -> datetime:
        if isinstance(value, str) and value:
            for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(value[:19], fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
        return datetime.now(timezone.utc) + timedelta(hours=1)

    @staticmethod
    def _mask(data: dict[str, Any]) -> dict[str, Any]:
        masked = dict(data)
        if "token" in masked:
            masked["token"] = "***"
        return masked


token_manager = TokenManager()
