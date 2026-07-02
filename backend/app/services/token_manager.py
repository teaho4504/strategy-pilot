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
        self._issued_at: datetime | None = None
        self._last_error: str | None = None

    async def get_access_token(self) -> str:
        if self.settings.kiwoom_mode != "live":
            raise KiwoomAuthError("KIWOOM_MODE is not live; token issuance is disabled in mock mode.")
        if not self.settings.kiwoom_configured:
            missing = ", ".join(self.settings.missing_kiwoom_env)
            raise KiwoomAuthError(f"Missing Kiwoom credentials: {missing}")
        if self._has_valid_token():
            return self._token or ""

        payload = {
            "grant_type": "client_credentials",
            "appkey": self.settings.kiwoom_app_key,
            "secretkey": self.settings.kiwoom_secret_key,
        }
        url = self.settings.token_url

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(url, json=payload, headers={"Content-Type": "application/json;charset=UTF-8"})
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            self._last_error = f"Kiwoom token request failed: HTTP {exc.response.status_code}"
            raise KiwoomAuthError(self._last_error) from exc
        except httpx.HTTPError as exc:
            self._last_error = "Kiwoom token request failed due to a network error"
            raise KiwoomAuthError(self._last_error) from exc
        except ValueError as exc:
            self._last_error = "Kiwoom token response was not JSON"
            raise KiwoomAuthError(self._last_error) from exc

        token = str(data.get("token") or data.get("access_token") or "")
        if not token:
            self._last_error = f"Kiwoom token missing in response: {self._mask(data)}"
            raise KiwoomAuthError(self._last_error)

        self._token = token
        self._issued_at = datetime.now(timezone.utc)
        self._expires_at = self._parse_expires_at(data.get("expires_dt") or data.get("expires_at"), data.get("expires_in"))
        self._last_error = None
        logger.info("Kiwoom access token issued; expires_at=%s", self._expires_at.isoformat())
        return token

    def status(self) -> dict[str, str | bool | None]:
        now = datetime.now(timezone.utc)
        has_token = bool(self._token)
        expired = bool(self._expires_at and self._expires_at <= now)
        expires_in_seconds = int((self._expires_at - now).total_seconds()) if self._expires_at else None
        return {
            "mode": self.settings.kiwoom_mode,
            "hasToken": has_token,
            "valid": bool(has_token and not expired and self._has_valid_token()),
            "expiresAt": self._expires_at.isoformat() if self._expires_at else None,
            "issuedAt": self._issued_at.isoformat() if self._issued_at else None,
            "expiresInSeconds": expires_in_seconds,
            "lastError": self._last_error,
        }

    def _has_valid_token(self) -> bool:
        return bool(self._token and self._expires_at and self._expires_at > datetime.now(timezone.utc) + timedelta(minutes=1))

    @staticmethod
    def _parse_expires_at(value: Any, expires_in: Any = None) -> datetime:
        if isinstance(value, str) and value:
            for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.strptime(value[:19], fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
        try:
            seconds = int(expires_in)
            if seconds > 0:
                return datetime.now(timezone.utc) + timedelta(seconds=seconds)
        except (TypeError, ValueError):
            pass
        return datetime.now(timezone.utc) + timedelta(hours=1)

    @staticmethod
    def _mask(data: dict[str, Any]) -> dict[str, Any]:
        masked = dict(data)
        for key in ("token", "access_token", "appkey", "secretkey", "authorization", "Authorization"):
            if key in masked:
                masked[key] = "***"
        return masked


token_manager = TokenManager()
