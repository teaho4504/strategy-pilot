from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.schemas.portfolio import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        mode=settings.kiwoom_mode,
        kiwoom=settings.safe_status(),
        lastSuccessAt=getattr(request.app.state, "last_success_at", None),
        error=getattr(request.app.state, "last_error", None),
    )
