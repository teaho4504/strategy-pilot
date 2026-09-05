from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from app.core.config import get_settings


TOKEN_PATH = "/oauth2/token"
TOKEN_REQUEST_BODY_KEYS = ("grant_type", "appkey", "secretkey")
TOKEN_REQUEST_TIMEOUT_SECONDS = 5


class TokenManagerError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        api_id: str = "au10001",
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
        token, expires_at = await self.issue_access_token(
            token_url=settings.token_url,
            app_key=settings.kiwoom_app_key,
            secret_key=settings.kiwoom_secret_key,
        )
        self._access_token = token
        self._expires_at = expires_at

    @classmethod
    async def issue_access_token(cls, *, token_url: str, app_key: str, secret_key: str) -> tuple[str, datetime]:
        request = cls._build_token_request(token_url, app_key, secret_key)
        try:
            async with httpx.AsyncClient(timeout=TOKEN_REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(request["url"], json=request["json"], headers=request["headers"])
                cls._raise_for_token_redirect(response.status_code)
                data: dict[str, Any] = response.json()
                cls._raise_for_token_api_error(response.status_code, data)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TokenManagerError("Kiwoom token HTTP error", http_status=exc.response.status_code) from exc
        except httpx.TimeoutException as exc:
            raise TokenManagerError(
                "Kiwoom token request timed out",
                return_code="TIMEOUT",
                return_msg="token request timed out",
            ) from exc
        except httpx.RequestError as exc:
            raise TokenManagerError(
                "Kiwoom token network error",
                return_code="NETWORK_ERROR",
                return_msg=exc.__class__.__name__,
            ) from exc
        except ValueError as exc:
            raise TokenManagerError("Kiwoom token response was not JSON") from exc

        if not isinstance(data, dict):
            raise TokenManagerError("Kiwoom token response was not an object", http_status=response.status_code)

        token = data.get("token") or data.get("access_token")
        if not token:
            raise cls._missing_token_error(response.status_code, data)
        return str(token), cls._parse_expires_at(data)

    @staticmethod
    def _build_token_request(token_url: str, app_key: str, secret_key: str) -> dict[str, object]:
        headers = TokenManager._token_request_headers()
        payload = {
            "grant_type": "client_credentials",
            "appkey": app_key,
            "secretkey": secret_key,
        }
        TokenManager._validate_token_request(token_url, headers, payload)
        return {"url": token_url, "headers": headers, "json": payload}

    @staticmethod
    def _token_request_headers() -> dict[str, str]:
        return {"Content-Type": "application/json;charset=UTF-8"}

    @staticmethod
    def _validate_token_request(token_url: str, headers: dict[str, str], payload: Optional[dict[str, object]] = None) -> None:
        parsed = urlparse(token_url)
        if parsed.path != TOKEN_PATH:
            raise TokenManagerError("Kiwoom token URL path is invalid")
        header_names = {str(key).lower() for key in headers.keys()}
        if "api-id" in header_names:
            raise TokenManagerError("Kiwoom token request must not include api-id header")
        if "authorization" in header_names:
            raise TokenManagerError("Kiwoom token request must not include authorization header")
        if payload is not None and tuple(payload.keys()) != TOKEN_REQUEST_BODY_KEYS:
            raise TokenManagerError("Kiwoom token request body keys are invalid")

    @staticmethod
    def token_request_diagnostics() -> dict[str, object]:
        settings = get_settings()
        request = TokenManager._build_token_request(settings.token_url, settings.kiwoom_app_key, settings.kiwoom_secret_key)
        headers = request["headers"]
        payload = request["json"]
        parsed = urlparse(str(request["url"]))
        return {
            "method": "POST",
            "base_url_present": bool(parsed.scheme and parsed.netloc),
            "url_expected_match": str(request["url"]) == "https://api.kiwoom.com/oauth2/token",
            "path": parsed.path,
            "api_id_header_present": "api-id" in {str(key).lower() for key in headers.keys()},
            "header_names": sorted(str(key).lower() for key in headers.keys()),
            "content_type_expected_match": headers.get("Content-Type") == "application/json;charset=UTF-8",
            "request_body_keys": list(payload.keys()),
            "appkey_present": bool(settings.kiwoom_app_key),
            "secretkey_present": bool(settings.kiwoom_secret_key),
            "authorization_header_present": "authorization" in {str(key).lower() for key in headers.keys()},
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
    def _raise_for_token_redirect(http_status: int) -> None:
        if 300 <= http_status < 400:
            raise TokenManagerError(
                "Kiwoom token endpoint redirected unexpectedly",
                http_status=http_status,
                return_code="TOKEN_ENDPOINT_REDIRECT",
                return_msg="Secure token issuance is temporarily unavailable",
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
                    return (
                        parsed.replace(tzinfo=ZoneInfo("Asia/Seoul"))
                        .astimezone(timezone.utc)
                        - timedelta(seconds=60)
                    )
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
