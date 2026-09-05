from __future__ import annotations

import asyncio
import os
from contextlib import suppress

from app.core.time import now_iso
from app.services.us_condition_service import us_condition_service
from app.services.us_order_service import us_order_service


_runner_task: asyncio.Task[None] | None = None
_runner_started_at: str | None = None
_runner_last_tick_at: str | None = None
_runner_last_error: str | None = None
_runner_tick_count = 0
_runner_condition_wake_count = 0
_runner_last_wake_reason = "startup"
_runner_last_observation_action: str | None = None
_runner_last_observation_strategy: str | None = None
_runner_last_observation_symbol: str | None = None
_runner_last_observation_exchange: str | None = None
_runner_last_observation_blocked_reasons: list[str] = []
_runner_last_observation_failed_criteria: list[str] = []
_runner_last_observation_at: str | None = None
_runner_last_observation_signature: tuple[object, ...] | None = None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    try:
        parsed = float(str(value).strip()) if value is not None else default
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def autotrade_runner_configured() -> bool:
    return _env_bool(
        "KIWOOM_US_AUTOTRADE_RUNNER_ENABLED",
        _env_bool("KIWOOM_US_ENABLE_ORDER", False),
    )


def autotrade_runner_mode() -> str:
    if not autotrade_runner_configured():
        return "off"
    if _env_bool("KIWOOM_READ_ONLY", True) or not _env_bool("KIWOOM_US_ENABLE_ORDER", False):
        return "observe"
    return "live"


def autotrade_observation_autostart_configured() -> bool:
    return (
        autotrade_runner_mode() == "observe"
        and _env_bool("KIWOOM_US_AUTOTRADE_OBSERVATION_ENABLED", False)
    )


def autotrade_runner_status() -> dict[str, object]:
    return {
        "runnerEnabled": autotrade_runner_configured(),
        "runnerRunning": _runner_task is not None and not _runner_task.done(),
        "runnerMode": autotrade_runner_mode(),
        "runnerIntervalSeconds": _env_float("KIWOOM_US_AUTOTRADE_RUNNER_INTERVAL_SECONDS", 5.0),
        "runnerStartedAt": _runner_started_at,
        "runnerLastTickAt": _runner_last_tick_at,
        "runnerLastError": _runner_last_error,
        "runnerTickCount": _runner_tick_count,
        "runnerConditionWakeCount": _runner_condition_wake_count,
        "runnerLastWakeReason": _runner_last_wake_reason,
        "runnerLastObservationAction": _runner_last_observation_action,
        "runnerLastObservationStrategy": _runner_last_observation_strategy,
        "runnerLastObservationSymbol": _runner_last_observation_symbol,
        "runnerLastObservationExchange": _runner_last_observation_exchange,
        "runnerLastObservationBlockedReasons": list(_runner_last_observation_blocked_reasons),
        "runnerLastObservationFailedCriteria": list(_runner_last_observation_failed_criteria),
        "runnerLastObservationAt": _runner_last_observation_at,
    }


async def start_autotrade_runner() -> None:
    global _runner_task, _runner_started_at
    if not autotrade_runner_configured():
        return
    if _runner_task is not None and not _runner_task.done():
        return
    if autotrade_observation_autostart_configured():
        await us_order_service.enable_auto_trade_observation()
    _runner_started_at = now_iso()
    _runner_task = asyncio.create_task(_autotrade_runner_loop(), name="strategy-pilot-us-autotrade-runner")


async def stop_autotrade_runner() -> None:
    global _runner_task
    if _runner_task is None:
        return
    _runner_task.cancel()
    with suppress(asyncio.CancelledError):
        await _runner_task
    _runner_task = None


async def _autotrade_runner_loop() -> None:
    global _runner_last_tick_at, _runner_last_error, _runner_tick_count
    global _runner_condition_wake_count, _runner_last_wake_reason
    while True:
        interval = _env_float("KIWOOM_US_AUTOTRADE_RUNNER_INTERVAL_SECONDS", 5.0)
        try:
            mode = autotrade_runner_mode()
            if mode in {"live", "observe"}:
                status = await us_order_service.get_auto_trade_status()
                if getattr(status, "observationEnabled", False) and not status.enabled:
                    observation_ok = await _run_observation_stage()
                    _runner_last_tick_at = now_iso()
                    _runner_tick_count += 1
                    _runner_last_error = None if observation_ok else "STAGE_ERROR"
                elif mode == "observe" or not status.enabled:
                    await asyncio.sleep(interval)
                    continue
                else:
                    exit_ok = await _run_autotrade_stage("auto_exit", us_order_service.run_auto_exit_tick)
                    entry_ok = await _run_autotrade_stage("auto_entry", us_order_service.run_auto_entry_tick)
                    _runner_last_tick_at = now_iso()
                    _runner_tick_count += 1
                    _runner_last_error = None if exit_ok and entry_ok else "STAGE_ERROR"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _runner_last_error = exc.__class__.__name__
            us_order_service.record_runner_error(_runner_last_error, stage="runner")
        condition_wake = await us_condition_service.wait_for_entry_signal(interval)
        if condition_wake:
            _runner_condition_wake_count += 1
            _runner_last_wake_reason = "condition_entry"
        else:
            _runner_last_wake_reason = "interval"


async def _run_autotrade_stage(stage: str, callback) -> bool:
    try:
        await callback()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        us_order_service.record_runner_error(exc.__class__.__name__, stage=stage, detail=str(exc))
        return False
    return True


async def _run_observation_stage() -> bool:
    global _runner_last_observation_action, _runner_last_observation_strategy
    global _runner_last_observation_symbol, _runner_last_observation_exchange
    global _runner_last_observation_blocked_reasons, _runner_last_observation_failed_criteria
    global _runner_last_observation_at, _runner_last_observation_signature
    try:
        result = await us_order_service.run_auto_entry_observation_tick()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        us_order_service.record_runner_error(
            exc.__class__.__name__,
            stage="entry_observation",
            detail=str(exc),
        )
        return False
    signature = (
        result.action,
        result.strategy,
        result.symbol,
        result.exchange,
        tuple(result.blockedReasons),
        tuple(result.failedCriteria),
    )
    if signature != _runner_last_observation_signature:
        us_order_service.record_observation_result(result)
        _runner_last_observation_signature = signature
    _runner_last_observation_action = result.action
    _runner_last_observation_strategy = result.strategy
    _runner_last_observation_symbol = result.symbol
    _runner_last_observation_exchange = result.exchange
    _runner_last_observation_blocked_reasons = list(result.blockedReasons)
    _runner_last_observation_failed_criteria = list(result.failedCriteria)
    _runner_last_observation_at = result.updatedAt
    return True
