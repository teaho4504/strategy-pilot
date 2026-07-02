from app.core.config import Settings, get_settings
from app.schemas.account import PerformanceSummary
from app.services.kiwoom_client import KiwoomClient, kiwoom_client
from app.services.portfolio_mapper import map_performance
from app.services.runtime_state import mark_success


class PerformanceService:
    def __init__(self, settings: Settings | None = None, client: KiwoomClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or kiwoom_client

    async def get_performance(self) -> PerformanceSummary:
        response = await self.client.request_tr_all("ka10085", {"stex_tp": self.settings.kiwoom_stex_tp})
        result = map_performance(response.body)
        mark_success()
        return result

    async def get_performance_raw(self) -> dict:
        response = await self.client.request_tr_all("ka10085", {"stex_tp": self.settings.kiwoom_stex_tp})
        mark_success()
        return response.body


performance_service = PerformanceService()
