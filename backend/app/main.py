from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import account, auth, health, kiwoom, market, realtime, us_account, us_order
from app.core.config import get_settings
from app.core.security import security_middleware
from app.services.autotrade_runner import start_autotrade_runner, stop_autotrade_runner
from app.services.realtime_quote_service import kiwoom_quote_monitor
from app.services.us_condition_service import us_condition_service
from app.services.us_order_state_monitor import kiwoom_order_state_monitor


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_autotrade_runner()
    try:
        yield
    finally:
        await us_condition_service.stop_realtime_monitor()
        await kiwoom_quote_monitor.stop()
        await kiwoom_order_state_monitor.stop()
        await stop_autotrade_runner()


app = FastAPI(
    title="Strategy Pilot Backend",
    version="0.1.0",
    description="Live Kiwoom account and market-data backend with financial mutations blocked.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.middleware("http")(security_middleware)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(kiwoom.router, prefix="/api", tags=["kiwoom"])
app.include_router(account.router, prefix="/api", tags=["account"])
app.include_router(market.router, prefix="/api", tags=["market"])
app.include_router(us_account.router, prefix="/api", tags=["us-account"])
app.include_router(us_order.router, prefix="/api", tags=["us-order"])
app.include_router(realtime.router, prefix="/api", tags=["realtime"])


@app.get("/")
async def root() -> dict[str, object]:
    return {
        "service": "strategy-pilot-backend",
        "mode": settings.kiwoom_mode,
        "readOnly": settings.kiwoom_read_only,
        "orderEnabled": settings.order_enabled,
    }
