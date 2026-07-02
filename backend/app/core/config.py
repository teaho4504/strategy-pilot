from functools import lru_cache
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")
load_dotenv()

KiwoomMode = Literal["mock", "live"]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def mask_secret(value: str, visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}...{value[-visible:]}"


class Settings:
    def __init__(self) -> None:
        self.kiwoom_mode: KiwoomMode = self._mode(os.getenv("KIWOOM_MODE", "mock"))
        self.kiwoom_app_key = os.getenv("KIWOOM_APP_KEY", "")
        self.kiwoom_secret_key = os.getenv("KIWOOM_SECRET_KEY") or os.getenv("KIWOOM_APP_SECRET", "")
        self.kiwoom_account_no = os.getenv("KIWOOM_ACCOUNT_NO", "")
        self.kiwoom_read_only = _env_bool("KIWOOM_READ_ONLY", True)
        self.kiwoom_enable_order = _env_bool("KIWOOM_ENABLE_ORDER", False)
        configured_base_url = os.getenv("KIWOOM_BASE_URL", "").rstrip("/")
        self.kiwoom_real_api_base_url = (configured_base_url or os.getenv("KIWOOM_REAL_API_BASE_URL", "https://api.kiwoom.com")).rstrip("/")
        self.kiwoom_mock_api_base_url = os.getenv("KIWOOM_MOCK_API_BASE_URL", "https://mockapi.kiwoom.com").rstrip("/")
        self.kiwoom_dev_api_base_url = os.getenv("KIWOOM_DEV_API_BASE_URL", "https://apidev.kiwoom.com").rstrip("/")
        self.kiwoom_token_url = os.getenv("KIWOOM_TOKEN_URL", "").rstrip("/")
        self.kiwoom_stex_tp = os.getenv("KIWOOM_STEX_TP", "0")
        self.kiwoom_qry_tp = os.getenv("KIWOOM_QRY_TP", "3")
        self.kiwoom_dmst_stex_tp = os.getenv("KIWOOM_DMST_STEX_TP", "KRX")
        self.kiwoom_watchlist = [
            code.strip()
            for code in os.getenv("KIWOOM_WATCHLIST", "005930,000660,035420").split(",")
            if code.strip()
        ]
        self.backend_cors_origins = [
            origin.strip()
            for origin in os.getenv("BACKEND_CORS_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080").split(",")
            if origin.strip()
        ]

    @staticmethod
    def _mode(value: str) -> KiwoomMode:
        normalized = value.strip().lower()
        if normalized == "live":
            return "live"
        return "mock"

    @property
    def kiwoom_credentials_configured(self) -> bool:
        return bool(self.kiwoom_app_key and self.kiwoom_secret_key)

    @property
    def kiwoom_account_configured(self) -> bool:
        return bool(self.kiwoom_account_no)

    @property
    def kiwoom_configured(self) -> bool:
        return self.kiwoom_credentials_configured

    @property
    def missing_kiwoom_env(self) -> list[str]:
        missing: list[str] = []
        if not self.kiwoom_app_key:
            missing.append("KIWOOM_APP_KEY")
        if not self.kiwoom_secret_key:
            missing.append("KIWOOM_SECRET_KEY")
        return missing

    @property
    def missing_kiwoom_account_env(self) -> list[str]:
        missing = list(self.missing_kiwoom_env)
        if not self.kiwoom_account_no:
            missing.append("KIWOOM_ACCOUNT_NO")
        return missing

    @property
    def kiwoom_base_url(self) -> str:
        if self.kiwoom_mode == "live":
            return self.kiwoom_real_api_base_url
        return self.kiwoom_mock_api_base_url

    @property
    def token_url(self) -> str:
        if self.kiwoom_token_url:
            return self.kiwoom_token_url
        return f"{self.kiwoom_base_url}/oauth2/token"

    @property
    def order_enabled(self) -> bool:
        return bool(self.kiwoom_enable_order and not self.kiwoom_read_only)

    def safe_summary(self) -> dict[str, str | bool | list[str]]:
        return {
            "mode": self.kiwoom_mode,
            "baseUrl": self.kiwoom_base_url,
            "tokenUrlConfigured": bool(self.kiwoom_token_url),
            "credentialsConfigured": self.kiwoom_credentials_configured,
            "accountConfigured": self.kiwoom_account_configured,
            "readOnly": self.kiwoom_read_only,
            "orderEnabled": self.order_enabled,
            "missing": self.missing_kiwoom_account_env if self.kiwoom_mode == "live" else [],
            "appKey": mask_secret(self.kiwoom_app_key),
            "accountNo": mask_secret(self.kiwoom_account_no, visible=2),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
