from fastapi import APIRouter, HTTPException

from app.schemas.account import Account, CashBalance, PerformanceSummary
from app.schemas.holding import Holding
from app.schemas.portfolio import Portfolio
from app.services.account_service import account_service
from app.services.balance_service import balance_service
from app.services.kiwoom_client import KiwoomClientError
from app.services.performance_service import performance_service
from app.services.runtime_state import mark_error

router = APIRouter()


def _raise_api_error(exc: Exception) -> None:
    mark_error(str(exc))
    raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/accounts", response_model=list[Account])
async def get_accounts() -> list[Account]:
    try:
        return await account_service.get_accounts()
    except KiwoomClientError as exc:
        _raise_api_error(exc)


@router.get("/account/portfolio", response_model=Portfolio)
async def get_portfolio() -> Portfolio:
    try:
        return await account_service.get_portfolio()
    except KiwoomClientError as exc:
        _raise_api_error(exc)


@router.get("/account/performance", response_model=PerformanceSummary)
async def get_performance() -> PerformanceSummary:
    try:
        return await performance_service.get_performance()
    except KiwoomClientError as exc:
        _raise_api_error(exc)


@router.get("/account/cash", response_model=CashBalance)
async def get_cash() -> CashBalance:
    try:
        return await balance_service.get_cash()
    except KiwoomClientError as exc:
        _raise_api_error(exc)


@router.get("/account/holdings", response_model=list[Holding])
async def get_holdings() -> list[Holding]:
    try:
        return await balance_service.get_holdings()
    except KiwoomClientError as exc:
        _raise_api_error(exc)
