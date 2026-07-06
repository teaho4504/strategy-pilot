from fastapi import APIRouter

from app.schemas.market import WatchTicker
from app.services.market_service import market_service


router = APIRouter()


@router.get("/market/watchlist", response_model=list[WatchTicker])
async def get_watchlist() -> list[WatchTicker]:
    return await market_service.get_watchlist()
