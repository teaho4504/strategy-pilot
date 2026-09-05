from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import require_authenticated_user
from app.schemas.us_account import UsDailyAccountReturnSummary, UsReadOnlyTrSummary
from app.services.runtime_state import mark_error
from app.services.us_account_service import US_READONLY_SERVICE_ERRORS, us_account_service


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


def raise_us_backend_error(exc: Exception) -> None:
    mark_error(str(exc))
    status_code = 400 if "missing" in str(exc).lower() or "must be" in str(exc).lower() else 502
    raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/us/account/cash", response_model=UsReadOnlyTrSummary)
async def get_us_cash() -> UsReadOnlyTrSummary:
    try:
        return await us_account_service.get_cash()
    except US_READONLY_SERVICE_ERRORS as exc:
        raise_us_backend_error(exc)


@router.get("/us/account/valuation", response_model=UsReadOnlyTrSummary)
async def get_us_valuation() -> UsReadOnlyTrSummary:
    try:
        return await us_account_service.get_valuation()
    except US_READONLY_SERVICE_ERRORS as exc:
        raise_us_backend_error(exc)


@router.get("/us/account/holdings", response_model=UsReadOnlyTrSummary)
async def get_us_holdings(
    exchange: Optional[str] = Query("", max_length=2),
    symbol: Optional[str] = Query("", max_length=12),
) -> UsReadOnlyTrSummary:
    try:
        return await us_account_service.get_holdings(exchange or "", symbol or "")
    except US_READONLY_SERVICE_ERRORS as exc:
        raise_us_backend_error(exc)


@router.get("/us/account/realized-pnl", response_model=UsReadOnlyTrSummary)
async def get_us_realized_pnl(fc_krw_tp: str = Query("1", min_length=1, max_length=2)) -> UsReadOnlyTrSummary:
    try:
        return await us_account_service.get_realized_pnl(fc_krw_tp)
    except US_READONLY_SERVICE_ERRORS as exc:
        raise_us_backend_error(exc)


@router.get("/us/account/period-return", response_model=UsReadOnlyTrSummary)
async def get_us_period_return(
    fromDate: Optional[str] = Query(None, min_length=8, max_length=8),
    toDate: Optional[str] = Query(None, min_length=8, max_length=8),
) -> UsReadOnlyTrSummary:
    try:
        return await us_account_service.get_period_return(fromDate, toDate)
    except US_READONLY_SERVICE_ERRORS as exc:
        raise_us_backend_error(exc)


@router.get("/us/account/daily-returns", response_model=UsDailyAccountReturnSummary)
async def get_us_daily_returns(
    fromDate: Optional[str] = Query(None, min_length=8, max_length=8),
    toDate: Optional[str] = Query(None, min_length=8, max_length=8),
) -> UsDailyAccountReturnSummary:
    try:
        return await us_account_service.get_daily_returns(fromDate, toDate)
    except US_READONLY_SERVICE_ERRORS as exc:
        raise_us_backend_error(exc)


@router.get("/us/account/order-fills", response_model=UsReadOnlyTrSummary)
async def get_us_order_fills(
    symbol: Optional[str] = Query(None, min_length=1, max_length=12),
    exchange: Optional[str] = Query(None, min_length=2, max_length=2),
    side: str = Query("0", min_length=1, max_length=1),
) -> UsReadOnlyTrSummary:
    try:
        return await us_account_service.get_today_order_fills(symbol=symbol, exchange=exchange, side=side)
    except US_READONLY_SERVICE_ERRORS as exc:
        raise_us_backend_error(exc)
