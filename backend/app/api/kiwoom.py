from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.kiwoom import KiwoomStatus, KiwoomTokenStatus
from app.services.token_manager import token_manager

router = APIRouter()


@router.get("/kiwoom/status", response_model=KiwoomStatus)
async def kiwoom_status() -> KiwoomStatus:
    settings = get_settings()
    token_status = token_manager.status()
    return KiwoomStatus(
        mode=settings.kiwoom_mode,
        baseUrl=settings.kiwoom_base_url,
        tokenUrlConfigured=bool(settings.kiwoom_token_url),
        token=KiwoomTokenStatus(**token_status),
        credentialsConfigured=settings.kiwoom_credentials_configured,
        accountConfigured=settings.kiwoom_account_configured,
        readOnly=settings.kiwoom_read_only,
        orderEnabled=settings.order_enabled,
        missing=settings.missing_kiwoom_account_env if settings.kiwoom_mode == "live" else [],
    )
