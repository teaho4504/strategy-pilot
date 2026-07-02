from app.core.config import Settings, get_settings
from app.schemas.portfolio import WatchTicker
from app.services.kiwoom_client import KiwoomClient, kiwoom_client
from app.services.portfolio_mapper import map_watch_ticker
from app.services.runtime_state import mark_success


class MarketService:
    def __init__(self, settings: Settings | None = None, client: KiwoomClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or kiwoom_client

    async def get_watchlist(self) -> list[WatchTicker]:
        tickers: list[WatchTicker] = []
        for code in self.settings.kiwoom_watchlist:
            response = await self.client.request_tr("ka10001", {"stk_cd": code})
            tickers.append(map_watch_ticker(response.body))
        mark_success()
        return tickers


market_service = MarketService()
