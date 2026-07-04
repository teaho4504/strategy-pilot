from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.core.config import get_settings


class TokenManagerError(RuntimeError):
    pass


class TokenManager:
    def __init__(self) -> None:
        self._access_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None

    async def get_access_token(self) -> str:
        settings = get_settings()
        if settings.kiwoom_mode != "live":
            return "mock-access-token"
        if not settings.credentials_configured:
            missing = ", ".join(settings.missing_kiwoom_env)
            raise TokenManagerError(f"Kiwoom live mode requires backend credentials: {missing}")
        if self._access_token and self._expires_at and datetime.now(timezone.utc) < self._expires_at:
            return self._access_token
        await self.refresh_access_token()
        if not self._access_token:
            raise TokenManagerError("Kiwoom access token refresh did not return a token")
        return self._access_token

    async def refresh_access_token(self) -> None:
        settings = get_settings()
        payload = {
            "grant_type": "client_credentials",
            "appkey": settings.kiwoom_app_key,
            "secretkey": settings.kiwoom_secret_key,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(settings.token_url, json=payload, headers={"api-id": "au10001"})
                response.raise_for_status()
                data: dict[str, Any] = response.json()
        except httpx.HTTPStatusError as exc:
            raise TokenManagerError(f"Kiwoom token HTTP error: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise TokenManagerError(f"Kiwoom token network error: {exc}") from exc
        except ValueError as exc:
            raise TokenManagerError("Kiwoom token response was not JSON") from exc

        token = data.get("token") or data.get("access_token")
        if not token:
            raise TokenManagerError("Kiwoom token response did not include access token")
        expires_in = int(data.get("expires_in") or 3600)
        self._access_token = str(token)
        self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(expires_in - 60, 60))

    def safe_status(self) -> dict[str, object]:
        return {
            "cached": bool(self._access_token),
            "expiresAt": self._expires_at.isoformat() if self._expires_at else None,
        }


token_manager = TokenManager()
