from fastapi import APIRouter, HTTPException, Request

from app.core.config import get_settings
from app.schemas.account import Account, AccountPerformance, Holding
from app.schemas.portfolio import PortfolioSnapshot
from app.services.kiwoom_client import KiwoomClient
from app.services.portfolio_mapper import map_ka10085_to_performance, mock_accounts, portfolio_from_performance
from app.services.token_manager import KiwoomApiError, KiwoomConfigError

router = APIRouter(prefix="/api", tags=["account"])


async def _performance(request: Request) -> AccountPerformance:
    settings = get_settings()
    client = KiwoomClient(settings)
    try:
        pages, source = await client.get_account_performance_pages()
        performance = map_ka10085_to_performance(pages, source=source)
        request.app.state.last_success_at = performance.updatedAt
        request.app.state.last_error = None
        return performance
    except KiwoomConfigError as exc:
        request.app.state.last_error = str(exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except KiwoomApiError as exc:
        request.app.state.last_error = str(exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/accounts", response_model=list[Account])
async def get_accounts() -> list[Account]:
    settings = get_settings()
    if not settings.is_live:
        return mock_accounts()
    if not settings.kiwoom_account_no:
        raise HTTPException(status_code=503, detail="KIWOOM_ACCOUNT_NO is required when KIWOOM_MODE=live")
    from app.services.portfolio_mapper import mask_account

    return [Account(id="kiwoom-primary", broker="키움증권", label="실계좌 조회", isDemo=False, maskedNumber=mask_account(settings.kiwoom_account_no))]


@router.get("/account/performance", response_model=AccountPerformance)
async def get_account_performance(request: Request) -> AccountPerformance:
    return await _performance(request)


@router.get("/account/portfolio", response_model=PortfolioSnapshot)
async def get_account_portfolio(request: Request) -> PortfolioSnapshot:
    performance = await _performance(request)
    return portfolio_from_performance(performance)


@router.get("/account/holdings", response_model=list[Holding])
async def get_account_holdings(request: Request) -> list[Holding]:
    performance = await _performance(request)
    return performance.holdings
