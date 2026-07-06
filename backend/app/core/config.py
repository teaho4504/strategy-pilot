from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")
load_dotenv()

KiwoomMode = Literal["mock", "live"]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.kiwoom_mode: KiwoomMode = self._mode(os.getenv("KIWOOM_MODE", "mock"))
        self.kiwoom_app_key = os.getenv("KIWOOM_APP_KEY", "")
        self.kiwoom_secret_key = os.getenv("KIWOOM_SECRET_KEY", "") or os.getenv("KIWOOM_APP_SECRET", "")
        self.kiwoom_account_no = os.getenv("KIWOOM_ACCOUNT_NO", "")
        self.kiwoom_base_url = os.getenv("KIWOOM_BASE_URL", "https://api.kiwoom.com").strip().rstrip("/")
        self.kiwoom_token_url = os.getenv("KIWOOM_TOKEN_URL", "").strip().rstrip("/")
        self.kiwoom_read_only = env_bool("KIWOOM_READ_ONLY", True)
        self.kiwoom_enable_order = env_bool("KIWOOM_ENABLE_ORDER", False)
        self.kiwoom_stex_tp = os.getenv("KIWOOM_STEX_TP", "0")
        self.kiwoom_cash_qry_tp = os.getenv("KIWOOM_CASH_QRY_TP", "2")
        self.kiwoom_portfolio_qry_tp = os.getenv("KIWOOM_PORTFOLIO_QRY_TP", "1")
        self.kiwoom_dmst_stex_tp = os.getenv("KIWOOM_DMST_STEX_TP", "KRX")
        self.backend_cors_origins = [
            origin.strip()
            for origin in os.getenv(
                "BACKEND_CORS_ORIGINS",
                "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        ]
        self.supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self.supabase_jwt_issuer = os.getenv("SUPABASE_JWT_ISSUER", "").strip()
        self.supabase_jwt_audience = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated").strip() or "authenticated"
        self.allowed_user_emails = {
            email.strip().lower()
            for email in os.getenv("ALLOWED_USER_EMAILS", "").split(",")
            if email.strip()
        }

    @staticmethod
    def _mode(value: str) -> KiwoomMode:
        return "live" if value.strip().lower() == "live" else "mock"

    @property
    def token_url(self) -> str:
        if self.kiwoom_token_url:
            return self.kiwoom_token_url
        return f"{self.kiwoom_base_url}/oauth2/token"

    @property
    def credentials_configured(self) -> bool:
        return bool(self.kiwoom_app_key and self.kiwoom_secret_key)

    @property
    def account_configured(self) -> bool:
        return bool(self.kiwoom_account_no)

    @property
    def order_enabled(self) -> bool:
        return bool(self.kiwoom_enable_order and not self.kiwoom_read_only)

    @property
    def missing_kiwoom_env(self) -> list[str]:
        missing: list[str] = []
        if not self.kiwoom_app_key:
            missing.append("KIWOOM_APP_KEY")
        if not self.kiwoom_secret_key:
            missing.append("KIWOOM_SECRET_KEY")
        if not self.kiwoom_account_no:
            missing.append("KIWOOM_ACCOUNT_NO")
        return missing

    def safe_summary(self) -> dict[str, object]:
        return {
            "mode": self.kiwoom_mode,
            "baseUrlConfigured": bool(self.kiwoom_base_url),
            "tokenUrlConfigured": bool(self.kiwoom_token_url),
            "credentialsConfigured": self.credentials_configured,
            "accountConfigured": self.account_configured,
            "readOnly": self.kiwoom_read_only,
            "orderEnabled": self.order_enabled,
            "missing": self.missing_kiwoom_env if self.kiwoom_mode == "live" else [],
        }

    @property
    def supabase_jwks_url(self) -> str:
        if not self.supabase_url:
            return ""
        return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
