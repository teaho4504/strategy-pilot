from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings


TOKEN_API_ID = "au10001"
TOKEN_PATH = "/oauth2/token"


class TokenManagerError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        api_id: str = TOKEN_API_ID,
        http_status: Optional[int] = None,
        return_code: Optional[object] = None,
        return_msg: Optional[object] = None,
    ) -> None:
        super().__init__(message)
        self.api_id = api_id
        self.http_status = http_status
        self.return_code = return_code
        self.return_msg = return_msg


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
        headers = self._token_request_headers()
        self._validate_token_request(settings.token_url, headers)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(settings.token_url, json=payload, headers=headers)
                data: dict[str, Any] = response.json()
                self._raise_for_token_api_error(response.status_code, data)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TokenManagerError("Kiwoom token HTTP error", http_status=exc.response.status_code) from exc
        except httpx.RequestError as exc:
            raise TokenManagerError("Kiwoom token network error") from exc
        except ValueError as exc:
            raise TokenManagerError("Kiwoom token response was not JSON") from exc

        if not isinstance(data, dict):
            raise TokenManagerError("Kiwoom token response was not an object", http_status=response.status_code)

        token = data.get("token") or data.get("access_token")
        if not token:
            raise self._missing_token_error(response.status_code, data)
        self._access_token = str(token)
        self._expires_at = self._parse_expires_at(data)

    @staticmethod
    def _token_request_headers(api_id: str = TOKEN_API_ID) -> dict[str, str]:
        if api_id != TOKEN_API_ID:
            raise TokenManagerError("Kiwoom token request API ID is invalid")
        return {"api-id": TOKEN_API_ID}

    @staticmethod
    def _validate_token_request(token_url: str, headers: dict[str, str]) -> None:
        parsed = urlparse(token_url)
        if parsed.path != TOKEN_PATH:
            raise TokenManagerError("Kiwoom token URL path is invalid")
        if headers.get("api-id") != TOKEN_API_ID:
            raise TokenManagerError("Kiwoom token request API ID is invalid")

    @staticmethod
    def token_request_diagnostics() -> dict[str, object]:
        settings = get_settings()
        headers = TokenManager._token_request_headers()
        parsed = urlparse(settings.token_url)
        return {
            "method": "POST",
            "base_url_present": bool(parsed.scheme and parsed.netloc),
            "path": parsed.path,
            "api_id_present": bool(headers.get("api-id")),
            "api_id_expected_match": headers.get("api-id") == TOKEN_API_ID,
            "appkey_present": bool(settings.kiwoom_app_key),
            "secretkey_present": bool(settings.kiwoom_secret_key),
            "authorization_header_present": False,
        }

    @staticmethod
    def _raise_for_token_api_error(http_status: int, data: object) -> None:
        if not isinstance(data, dict):
            return
        return_code = data.get("return_code")
        if return_code in (None, 0, "0"):
            return
        return_msg = data.get("return_msg") or "unknown Kiwoom token error"
        raise TokenManagerError(
            f"Kiwoom token API error: return_code={return_code} return_msg={return_msg}",
            http_status=http_status,
            return_code=return_code,
            return_msg=return_msg,
        )

    @staticmethod
    def _missing_token_error(http_status: int, data: dict[str, Any]) -> TokenManagerError:
        return_code = data.get("return_code")
        return_msg = data.get("return_msg")
        detail = "Kiwoom token response did not include token"
        if return_code is not None or return_msg is not None:
            detail = f"{detail}: return_code={return_code} return_msg={return_msg}"
        return TokenManagerError(detail, http_status=http_status, return_code=return_code, return_msg=return_msg)

    @staticmethod
    def _parse_expires_at(data: dict[str, Any]) -> datetime:
        expires_dt = data.get("expires_dt")
        if expires_dt:
            for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    parsed = datetime.strptime(str(expires_dt), fmt)
                    return parsed.replace(tzinfo=timezone.utc) - timedelta(seconds=60)
                except ValueError:
                    continue
        try:
            expires_in = int(data.get("expires_in") or 3600)
        except (TypeError, ValueError):
            expires_in = 3600
        return datetime.now(timezone.utc) + timedelta(seconds=max(expires_in - 60, 60))

    def safe_status(self) -> dict[str, object]:
        return {
            "cached": bool(self._access_token),
            "expiresAt": self._expires_at.isoformat() if self._expires_at else None,
        }


token_manager = TokenManager()
