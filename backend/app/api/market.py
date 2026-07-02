from fastapi import APIRouter, HTTPException

from app.schemas.portfolio import WatchTicker
from app.services.kiwoom_client import KiwoomClientError
from app.services.market_service import market_service
from app.services.runtime_state import mark_error

router = APIRouter()


@router.get("/market/watchlist", response_model=list[WatchTicker])
async def get_watchlist() -> list[WatchTicker]:
    try:
        return await market_service.get_watchlist()
    except KiwoomClientError as exc:
        mark_error(str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
