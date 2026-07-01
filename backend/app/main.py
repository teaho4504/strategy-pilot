from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.account import router as account_router
from app.api.health import router as health_router
from app.api.market import router as market_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="Strategy Pilot Backend", version="0.1.0")
app.state.last_success_at = None
app.state.last_error = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(account_router)
app.include_router(market_router)
