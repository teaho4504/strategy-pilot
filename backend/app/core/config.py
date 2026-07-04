from dataclasses import dataclass
from functools import lru_cache
import os
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _split_origins(value: str) -> List[str]:
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def mask_secret(value: str | None, visible: int = 4) -> str | None:
    if not value:
        return None
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}...{value[-visible:]}"


@dataclass(frozen=True)
class Settings:
    kiwoom_mode: str = os.getenv("KIWOOM_MODE", "mock").lower()
    kiwoom_api_base_url: str = os.getenv("KIWOOM_API_BASE_URL", "https://api.kiwoom.com").rstrip("/")
    kiwoom_app_key: str | None = os.getenv("KIWOOM_APP_KEY") or None
    kiwoom_app_secret: str | None = os.getenv("KIWOOM_APP_SECRET") or None
    kiwoom_access_token: str | None = os.getenv("KIWOOM_ACCESS_TOKEN") or None
    kiwoom_account_no: str | None = os.getenv("KIWOOM_ACCOUNT_NO") or None
    cors_origins: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.cors_origins is None:
            object.__setattr__(
                self,
                "cors_origins",
                _split_origins(
                    os.getenv(
                        "CORS_ORIGINS",
                        "http://localhost:8080,http://localhost:5173,http://localhost:3000",
                    )
                ),
            )

    @property
    def is_live(self) -> bool:
        return self.kiwoom_mode == "live"

    @property
    def kiwoom_configured(self) -> bool:
        if not self.is_live:
            return True
        has_token_or_keys = bool(self.kiwoom_access_token) or bool(self.kiwoom_app_key and self.kiwoom_app_secret)
        return bool(has_token_or_keys and self.kiwoom_account_no)

    def safe_status(self) -> dict[str, str | bool | None]:
        return {
            "mode": self.kiwoom_mode,
            "apiBaseUrl": self.kiwoom_api_base_url,
            "configured": self.kiwoom_configured,
            "appKey": mask_secret(self.kiwoom_app_key),
            "accountNo": mask_secret(self.kiwoom_account_no, visible=2),
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
