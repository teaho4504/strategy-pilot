from functools import lru_cache
import os
from typing import Literal

KiwoomMode = Literal["mock", "live"]


class Settings:
    def __init__(self) -> None:
        self.kiwoom_mode: KiwoomMode = self._mode(os.getenv("KIWOOM_MODE", "mock"))
        self.kiwoom_app_key = os.getenv("KIWOOM_APP_KEY", "")
        self.kiwoom_secret_key = os.getenv("KIWOOM_SECRET_KEY") or os.getenv("KIWOOM_APP_SECRET", "")
        self.kiwoom_account_no = os.getenv("KIWOOM_ACCOUNT_NO", "")
        self.kiwoom_real_api_base_url = os.getenv("KIWOOM_REAL_API_BASE_URL", "https://api.kiwoom.com").rstrip("/")
        self.kiwoom_mock_api_base_url = os.getenv("KIWOOM_MOCK_API_BASE_URL", "https://mockapi.kiwoom.com").rstrip("/")
        self.kiwoom_dev_api_base_url = os.getenv("KIWOOM_DEV_API_BASE_URL", "https://apidev.kiwoom.com").rstrip("/")
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
    def kiwoom_configured(self) -> bool:
        return bool(self.kiwoom_app_key and self.kiwoom_secret_key)

    @property
    def missing_kiwoom_env(self) -> list[str]:
        missing: list[str] = []
        if not self.kiwoom_app_key:
            missing.append("KIWOOM_APP_KEY")
        if not self.kiwoom_secret_key:
            missing.append("KIWOOM_SECRET_KEY")
        return missing

    @property
    def kiwoom_base_url(self) -> str:
        if self.kiwoom_mode == "live":
            return self.kiwoom_real_api_base_url
        return self.kiwoom_mock_api_base_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
