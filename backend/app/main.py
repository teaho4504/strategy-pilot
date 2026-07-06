from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import account, health, kiwoom, market
from app.core.config import get_settings


settings = get_settings()

app = FastAPI(
    title="Strategy Pilot Backend",
    version="0.1.0",
    description="Read-only account backend for the Strategy Pilot dashboard.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(kiwoom.router, prefix="/api", tags=["kiwoom"])
app.include_router(account.router, prefix="/api", tags=["account"])
app.include_router(market.router, prefix="/api", tags=["market"])


@app.get("/")
async def root() -> dict[str, object]:
    return {
        "service": "strategy-pilot-backend",
        "mode": settings.kiwoom_mode,
        "readOnly": settings.kiwoom_read_only,
        "orderEnabled": settings.order_enabled,
    }
