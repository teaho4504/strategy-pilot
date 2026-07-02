from app.core.config import Settings, get_settings
from app.schemas.account import CashBalance
from app.schemas.holding import Holding
from app.services.kiwoom_client import KiwoomClient, kiwoom_client
from app.services.portfolio_mapper import map_cash, map_holdings
from app.services.runtime_state import mark_success


class BalanceService:
    def __init__(self, settings: Settings | None = None, client: KiwoomClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or kiwoom_client

    async def get_cash(self) -> CashBalance:
        response = await self.client.request_tr("kt00001", {"qry_tp": self.settings.kiwoom_qry_tp})
        result = map_cash(response.body)
        mark_success()
        return result

    async def get_holdings(self) -> list[Holding]:
        balance = await self.client.request_tr_all("kt00005", {"dmst_stex_tp": self.settings.kiwoom_dmst_stex_tp})
        performance = await self.client.request_tr_all("ka10085", {"stex_tp": self.settings.kiwoom_stex_tp})
        result = map_holdings(balance.body, performance.body)
        mark_success()
        return result

    async def get_balance_raw(self) -> dict:
        response = await self.client.request_tr_all("kt00005", {"dmst_stex_tp": self.settings.kiwoom_dmst_stex_tp})
        mark_success()
        return response.body


balance_service = BalanceService()
