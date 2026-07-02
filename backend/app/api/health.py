from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.account import ConnectionStatus, HealthStatus
from app.services.runtime_state import last_error, last_success_at

router = APIRouter()


@router.get("/health", response_model=HealthStatus)
async def health() -> HealthStatus:
    settings = get_settings()
    success_at = last_success_at()
    error = last_error()
    api_state = "connected" if success_at and not error else "error" if error else "disconnected"
    return HealthStatus(
        ok=error is None,
        mode=settings.kiwoom_mode,
        kiwoomConfigured=settings.kiwoom_configured,
        kiwoomMissing=settings.missing_kiwoom_env,
        lastUpdatedAt=success_at,
        lastError=error,
        connection=ConnectionStatus(
            api=api_state,
            websocket="disconnected",
            mode=settings.kiwoom_mode,
            lastUpdatedAt=success_at,
        ),
    )
