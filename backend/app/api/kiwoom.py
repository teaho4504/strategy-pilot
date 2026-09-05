from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.services.token_manager import token_manager


router = APIRouter()


@router.get("/kiwoom/status")
async def get_kiwoom_status() -> dict[str, object]:
    settings = get_settings()
    token_status = token_manager.safe_status()
    return {
        "mode": settings.kiwoom_mode,
        "readOnly": settings.kiwoom_read_only,
        "orderEnabled": settings.order_enabled,
        "configured": settings.credentials_configured and settings.account_configured,
        "tokenCached": token_status["cached"],
        "tokenExpiresAt": token_status["expiresAt"],
        "missing": settings.missing_kiwoom_env if settings.kiwoom_mode == "live" else [],
    }
