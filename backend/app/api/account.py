from fastapi import APIRouter, HTTPException

from app.schemas.account import Account, CashBalance, PerformanceSummary
from app.schemas.portfolio import Holding, Portfolio
from app.services.account_service import MapperValidationError
from app.services.account_service import account_service
from app.services.kiwoom_client import KiwoomClientError
from app.services.runtime_state import mark_error


router = APIRouter()


def raise_backend_error(exc: Exception) -> None:
    mark_error(str(exc))
    status_code = 400 if "requires" in str(exc).lower() or "missing" in str(exc).lower() else 502
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/accounts", response_model=list[Account])
async def get_accounts() -> list[Account]:
    try:
        return await account_service.get_accounts()
    except (KiwoomClientError, MapperValidationError) as exc:
        raise_backend_error(exc)


@router.get("/account/portfolio", response_model=Portfolio)
async def get_portfolio() -> Portfolio:
    try:
        return await account_service.get_portfolio()
    except (KiwoomClientError, MapperValidationError) as exc:
        raise_backend_error(exc)


@router.get("/account/cash", response_model=CashBalance)
async def get_cash() -> CashBalance:
    try:
        return await account_service.get_cash()
    except (KiwoomClientError, MapperValidationError) as exc:
        raise_backend_error(exc)


@router.get("/account/performance", response_model=PerformanceSummary)
async def get_performance() -> PerformanceSummary:
    try:
        return await account_service.get_performance()
    except (KiwoomClientError, MapperValidationError) as exc:
        raise_backend_error(exc)


@router.get("/account/holdings", response_model=list[Holding])
async def get_holdings() -> list[Holding]:
    try:
        return await account_service.get_holdings()
    except (KiwoomClientError, MapperValidationError) as exc:
        raise_backend_error(exc)
