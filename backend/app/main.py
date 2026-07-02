from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import account, health, kiwoom, market, orders
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Strategy Pilot Backend",
    version="0.1.0",
    description="Read-only Kiwoom account query backend. Order APIs are intentionally disabled.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(kiwoom.router, prefix="/api", tags=["kiwoom"])
app.include_router(account.router, prefix="/api", tags=["account"])
app.include_router(market.router, prefix="/api", tags=["market"])
app.include_router(orders.router, prefix="/api", tags=["orders-disabled"])


@app.get("/")
async def root() -> dict[str, str | bool]:
    return {
        "service": "strategy-pilot-backend",
        "mode": settings.kiwoom_mode,
        "readOnly": settings.kiwoom_read_only,
        "orderEnabled": settings.order_enabled,
    }
