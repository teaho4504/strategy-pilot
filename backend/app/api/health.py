from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings
from app.services.runtime_state import runtime_state


router = APIRouter()


@router.get("/health")
async def get_health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "mode": settings.kiwoom_mode,
        "kiwoom": settings.safe_summary(),
        "lastSuccessfulRefreshAt": runtime_state.last_successful_refresh_at,
        "error": runtime_state.last_error,
        "serverTime": datetime.now(timezone.utc).isoformat(),
    }
