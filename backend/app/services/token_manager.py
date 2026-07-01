import time
from dataclasses import dataclass

import httpx

from app.core.config import Settings


class KiwoomConfigError(RuntimeError):
    pass


class KiwoomApiError(RuntimeError):
    pass


@dataclass
class CachedToken:
    access_token: str
    expires_at: float


class TokenManager:
    def __init__(self) -> None:
        self._cached: CachedToken | None = None

    async def get_access_token(self, settings: Settings) -> str:
        if not settings.is_live:
            return "mock-token"

        if settings.kiwoom_access_token:
            return settings.kiwoom_access_token

        if not settings.kiwoom_app_key or not settings.kiwoom_app_secret:
            raise KiwoomConfigError("KIWOOM_APP_KEY and KIWOOM_APP_SECRET are required when KIWOOM_MODE=live")

        if self._cached and self._cached.expires_at > time.time() + 60:
            return self._cached.access_token

        token = await self._issue_token(settings)
        self._cached = token
        return token.access_token

    async def _issue_token(self, settings: Settings) -> CachedToken:
        url = f"{settings.kiwoom_api_base_url}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "appkey": settings.kiwoom_app_key,
            "secretkey": settings.kiwoom_app_secret,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            raise KiwoomApiError(f"Kiwoom token request failed: HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise KiwoomApiError("Kiwoom token request failed due to a network error") from exc
        except ValueError as exc:
            raise KiwoomApiError("Kiwoom token response was not valid JSON") from exc

        access_token = body.get("access_token") or body.get("token")
        if not access_token:
            raise KiwoomApiError("Kiwoom token response did not include access_token")

        expires_in = int(body.get("expires_in") or 3600)
        return CachedToken(access_token=access_token, expires_at=time.time() + expires_in)


token_manager = TokenManager()
