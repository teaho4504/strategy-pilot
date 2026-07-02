from app.core.config import Settings, get_settings
from app.schemas.account import Account
from app.schemas.portfolio import Portfolio
from app.services.kiwoom_client import KiwoomClient, kiwoom_client
from app.services.performance_service import performance_service
from app.services.portfolio_mapper import map_portfolio, mask_account_no
from app.services.runtime_state import mark_success


class AccountService:
    def __init__(self, settings: Settings | None = None, client: KiwoomClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client or kiwoom_client

    async def get_accounts(self) -> list[Account]:
        response = await self.client.request_tr("ka00001", {})
        account_no = str(response.body.get("acctNo") or self.settings.kiwoom_account_no or "")
        account_id = f"kiwoom-{account_no[-4:]}" if account_no else "kiwoom-account"
        result = [
            Account(
                id=account_id,
                broker="키움증권",
                label="기본계좌" if self.settings.kiwoom_mode == "live" else "데모계좌",
                isDemo=self.settings.kiwoom_mode != "live",
                maskedNumber=mask_account_no(account_no),
            )
        ]
        mark_success()
        return result

    async def get_portfolio(self) -> Portfolio:
        account_eval = await self.client.request_tr_all(
            "kt00004",
            {"qry_tp": "0", "dmst_stex_tp": self.settings.kiwoom_dmst_stex_tp},
        )
        performance = await performance_service.get_performance_raw()
        result = map_portfolio(account_eval.body, performance)
        mark_success()
        return result


account_service = AccountService()
