from fastapi import APIRouter, Request

from app.schemas.portfolio import MarketWatchlistResponse
from app.services.portfolio_mapper import mock_market_watchlist

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/watchlist", response_model=MarketWatchlistResponse)
async def get_watchlist(request: Request) -> MarketWatchlistResponse:
    response = mock_market_watchlist()
    request.app.state.last_success_at = response.updatedAt
    return response
