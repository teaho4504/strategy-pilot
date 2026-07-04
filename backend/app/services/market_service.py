from app.schemas.market import WatchTicker
from app.services.mock_data import mock_watchlist


class MarketService:
    async def get_watchlist(self) -> list[WatchTicker]:
        return mock_watchlist()


market_service = MarketService()
