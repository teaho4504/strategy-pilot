from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
import secrets
from typing import Literal, Optional

from app.services.kiwoom_cli_profile import KiwoomCliProfileError, load_kiwoom_cli_credential, safe_kiwoom_cli_account_label
from app.services.token_manager import TokenManager, TokenManagerError


KiwoomLoginMode = Literal["live"]


class KiwoomSessionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        return_code: object | None = None,
        return_msg: object | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.return_code = return_code
        self.return_msg = return_msg


@dataclass(frozen=True)
class KiwoomSession:
    session_token: str
    mode: KiwoomLoginMode
    account_no: str
    base_url: str
    access_token: str
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    @property
    def safe_account_label(self) -> str:
        text = self.account_no.strip()
        # CLI profile sessions already carry a server-sanitized label such as
        # ``****-1574 [위탁종합]``. Masking that label a second time would keep
        # the last four Korean characters instead of the account suffix.
        if text == "configured" or text.startswith("****-"):
            return text
        if len(text) <= 4:
            return "configured"
        digits = "".join(ch for ch in text if ch.isdigit())
        return f"****-{digits[-4:]}" if len(digits) >= 4 else "configured"


_active_kiwoom_session: ContextVar[Optional[KiwoomSession]] = ContextVar("active_kiwoom_session", default=None)


def get_active_kiwoom_session() -> Optional[KiwoomSession]:
    return _active_kiwoom_session.get()


def set_active_kiwoom_session(session: Optional[KiwoomSession]) -> None:
    _active_kiwoom_session.set(session)


class KiwoomSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, KiwoomSession] = {}
        self._latest_session_token: str | None = None

    async def create_session(self, *, mode: KiwoomLoginMode, account_no: str, app_key: str, secret_key: str) -> KiwoomSession:
        clean_account = account_no.strip()
        clean_key = app_key.strip()
        clean_secret = secret_key.strip()
        if mode != "live":
            raise KiwoomSessionError("Only live Kiwoom sessions are supported")
        if not clean_account:
            raise KiwoomSessionError("Account number is required")
        if not clean_key or not clean_secret:
            raise KiwoomSessionError("App key and secret key are required")

        base_url = self._base_url(mode)
        try:
            access_token, expires_at = await TokenManager.issue_access_token(
                token_url=f"{base_url}/oauth2/token",
                app_key=clean_key,
                secret_key=clean_secret,
            )
        except TokenManagerError as exc:
            raise KiwoomSessionError(
                "Kiwoom token issue failed",
                http_status=exc.http_status,
                return_code=exc.return_code,
                return_msg=exc.return_msg,
            ) from exc

        session = KiwoomSession(
            session_token=secrets.token_urlsafe(32),
            mode=mode,
            account_no=clean_account,
            base_url=base_url,
            access_token=access_token,
            expires_at=expires_at,
        )
        self._sessions[session.session_token] = session
        self._latest_session_token = session.session_token
        return session

    async def create_session_from_cli_profile(self, profile: Optional[str] = None) -> KiwoomSession:
        try:
            credential = load_kiwoom_cli_credential(profile)
        except KiwoomCliProfileError as exc:
            raise KiwoomSessionError(str(exc)) from exc

        if credential.mode != "real":
            raise KiwoomSessionError("Only real Kiwoom CLI profiles are supported")
        mode: KiwoomLoginMode = "live"
        base_url = self._base_url(mode)
        try:
            access_token, expires_at = await TokenManager.issue_access_token(
                token_url=f"{base_url}/oauth2/token",
                app_key=credential.app_key,
                secret_key=credential.secret_key,
            )
        except TokenManagerError as exc:
            raise KiwoomSessionError(
                "Kiwoom token issue failed",
                http_status=exc.http_status,
                return_code=exc.return_code,
                return_msg=exc.return_msg,
            ) from exc

        session = KiwoomSession(
            session_token=secrets.token_urlsafe(32),
            mode=mode,
            account_no=safe_kiwoom_cli_account_label(credential.profile),
            base_url=base_url,
            access_token=access_token,
            expires_at=expires_at,
        )
        self._sessions[session.session_token] = session
        self._latest_session_token = session.session_token
        return session

    def get_session(self, session_token: str) -> Optional[KiwoomSession]:
        session = self._sessions.get(session_token)
        if session is None or session.is_expired:
            if session is not None:
                self._sessions.pop(session_token, None)
            if self._latest_session_token == session_token:
                self._latest_session_token = None
            return None
        self._latest_session_token = session.session_token
        return session

    def get_latest_session(self) -> Optional[KiwoomSession]:
        if not self._latest_session_token:
            return None
        return self.get_session(self._latest_session_token)

    def revoke_session(self, session_token: str) -> None:
        self._sessions.pop(session_token, None)
        if self._latest_session_token == session_token:
            self._latest_session_token = None

    @staticmethod
    def _base_url(mode: KiwoomLoginMode) -> str:
        if mode != "live":
            raise KiwoomSessionError("Only the Kiwoom live domain is supported")
        return "https://api.kiwoom.com"


kiwoom_session_manager = KiwoomSessionManager()


def get_active_or_latest_kiwoom_session() -> Optional[KiwoomSession]:
    active = get_active_kiwoom_session()
    if active is not None and not active.is_expired:
        return active
    if active is not None:
        set_active_kiwoom_session(None)
    return kiwoom_session_manager.get_latest_session()
