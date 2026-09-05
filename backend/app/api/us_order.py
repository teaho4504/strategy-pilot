from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_authenticated_user
from app.schemas.us_order import (
    UsAutoEntryTickResponse,
    UsAutoTradeDiagnosticsResponse,
    UsAutoExitTickResponse,
    UsAutoTradeEventItem,
    UsAutoTradeRuntimeStatus,
    UsAutoTradeStrategyStatusResponse,
    UsAutoTradeStrategyToggleRequest,
    UsLiquidationExecuteResponse,
    UsLiquidationPlanResponse,
    UsOrderHistoryItem,
    UsObservationStatsResponse,
    UsOrderPrecheckResponse,
    UsOrderRequest,
    UsOrderResponse,
    UsOrderRuntimeLockResponse,
    UsOrderStateMonitorPreflight,
    UsOrderStateMonitorStatus,
    UsOrderStatus,
    UsStrategyPnlSummary,
    UsTakeProfitMonitorResponse,
    UsTakeProfitPlanResponse,
)
from app.services.us_order_service import US_ORDER_SERVICE_ERRORS, UsOrderBlocked, us_order_service


router = APIRouter(dependencies=[Depends(require_authenticated_user)])


@router.get("/us/orders", response_model=list[UsOrderHistoryItem])
async def list_us_orders() -> list[UsOrderHistoryItem]:
    return await us_order_service.list_orders()


@router.get("/us/analytics/strategy-pnl", response_model=UsStrategyPnlSummary)
async def get_us_strategy_pnl_summary() -> UsStrategyPnlSummary:
    return await us_order_service.get_strategy_pnl_summary()


@router.get("/us/orders/status", response_model=UsOrderStatus)
async def get_us_order_status() -> UsOrderStatus:
    return await us_order_service.get_status()


@router.get(
    "/us/orders/state-monitor",
    response_model=UsOrderStateMonitorStatus,
)
async def get_us_order_state_monitor_status() -> UsOrderStateMonitorStatus:
    return await us_order_service.get_order_state_monitor_status()


@router.get(
    "/us/orders/state-monitor/preflight",
    response_model=UsOrderStateMonitorPreflight,
)
async def get_us_order_state_monitor_preflight(
) -> UsOrderStateMonitorPreflight:
    return await us_order_service.get_order_state_monitor_preflight()


@router.get("/us/autotrade/status", response_model=UsAutoTradeRuntimeStatus)
async def get_us_auto_trade_status() -> UsAutoTradeRuntimeStatus:
    return await us_order_service.get_auto_trade_status()


@router.get("/us/autotrade/strategies", response_model=UsAutoTradeStrategyStatusResponse)
async def get_us_auto_trade_strategy_status(refresh: bool = False) -> UsAutoTradeStrategyStatusResponse:
    return await us_order_service.get_auto_trade_strategy_status(refresh_catalog=refresh)


@router.post("/us/autotrade/strategies/{strategy}/toggle", response_model=UsAutoTradeStrategyStatusResponse)
async def toggle_us_auto_trade_strategy(strategy: str, payload: UsAutoTradeStrategyToggleRequest) -> UsAutoTradeStrategyStatusResponse:
    try:
        return await us_order_service.set_auto_trade_strategy_enabled(strategy, payload.enabled)
    except UsOrderBlocked as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/us/autotrade/events", response_model=list[UsAutoTradeEventItem])
async def list_us_auto_trade_events(limit: int = 30) -> list[UsAutoTradeEventItem]:
    return await us_order_service.list_auto_trade_events(limit)


@router.get("/us/autotrade/observation-stats", response_model=UsObservationStatsResponse)
async def get_us_auto_trade_observation_stats(limit: int = 500) -> UsObservationStatsResponse:
    return await us_order_service.get_observation_stats(limit)


@router.get("/us/autotrade/diagnostics", response_model=UsAutoTradeDiagnosticsResponse)
async def get_us_auto_trade_diagnostics() -> UsAutoTradeDiagnosticsResponse:
    return await us_order_service.get_auto_trade_diagnostics()


@router.get("/us/orders/liquidation-plan", response_model=UsLiquidationPlanResponse)
async def get_us_liquidation_plan() -> UsLiquidationPlanResponse:
    return await us_order_service.get_liquidation_plan()


@router.post("/us/orders/liquidate", response_model=UsLiquidationExecuteResponse)
async def execute_us_liquidation() -> UsLiquidationExecuteResponse:
    try:
        return await us_order_service.execute_liquidation()
    except US_ORDER_SERVICE_ERRORS as exc:
        status_code = 403 if isinstance(exc, UsOrderBlocked) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/us/autotrade/enable", response_model=UsAutoTradeRuntimeStatus)
async def enable_us_auto_trade() -> UsAutoTradeRuntimeStatus:
    return await us_order_service.enable_auto_trade()


@router.post("/us/autotrade/disable", response_model=UsAutoTradeRuntimeStatus)
async def disable_us_auto_trade() -> UsAutoTradeRuntimeStatus:
    return await us_order_service.disable_auto_trade()


@router.post("/us/autotrade/observe/enable", response_model=UsAutoTradeRuntimeStatus)
async def enable_us_auto_trade_observation() -> UsAutoTradeRuntimeStatus:
    return await us_order_service.enable_auto_trade_observation()


@router.post("/us/autotrade/observe/disable", response_model=UsAutoTradeRuntimeStatus)
async def disable_us_auto_trade_observation() -> UsAutoTradeRuntimeStatus:
    return await us_order_service.disable_auto_trade_observation()


@router.get("/us/orders/take-profit-plan", response_model=UsTakeProfitPlanResponse)
async def get_us_take_profit_plan() -> UsTakeProfitPlanResponse:
    return await us_order_service.get_take_profit_plan()


@router.get("/us/orders/take-profit-monitor", response_model=UsTakeProfitMonitorResponse)
async def get_us_take_profit_monitor() -> UsTakeProfitMonitorResponse:
    return await us_order_service.get_take_profit_monitor()


@router.post("/us/orders/auto-exit-tick", response_model=UsAutoExitTickResponse)
async def run_us_auto_exit_tick() -> UsAutoExitTickResponse:
    try:
        return await us_order_service.run_auto_exit_tick()
    except US_ORDER_SERVICE_ERRORS as exc:
        status_code = 403 if isinstance(exc, UsOrderBlocked) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/us/orders/auto-exit-arm-latest", response_model=UsAutoExitTickResponse)
async def arm_latest_us_buy_for_auto_exit() -> UsAutoExitTickResponse:
    try:
        return await us_order_service.arm_latest_buy_for_auto_exit()
    except US_ORDER_SERVICE_ERRORS as exc:
        status_code = 403 if isinstance(exc, UsOrderBlocked) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/us/orders/auto-entry-tick", response_model=UsAutoEntryTickResponse)
async def run_us_auto_entry_tick() -> UsAutoEntryTickResponse:
    try:
        return await us_order_service.run_auto_entry_tick()
    except US_ORDER_SERVICE_ERRORS as exc:
        status_code = 403 if isinstance(exc, UsOrderBlocked) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/us/orders/runtime-lock", response_model=UsOrderRuntimeLockResponse)
async def lock_us_order_runtime() -> UsOrderRuntimeLockResponse:
    return await us_order_service.lock_runtime_orders()


@router.post("/us/orders/precheck", response_model=UsOrderPrecheckResponse)
async def precheck_us_order(payload: UsOrderRequest) -> UsOrderPrecheckResponse:
    return await us_order_service.precheck_order(payload)


@router.post("/us/orders", response_model=UsOrderResponse)
async def place_us_order(payload: UsOrderRequest) -> UsOrderResponse:
    try:
        return await us_order_service.place_order(payload)
    except US_ORDER_SERVICE_ERRORS as exc:
        status_code = 403 if isinstance(exc, UsOrderBlocked) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
