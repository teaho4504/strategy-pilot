from __future__ import annotations

import os
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3

from app.core.config import get_settings
from app.schemas.us_order import (
    UsAutoEntryTickResponse,
    UsAutoTradeDiagnosticsResponse,
    UsAutoTradeEventItem,
    UsAutoTradePipelineSnapshot,
    UsLiquidationExecuteResponse,
    UsLiquidationHoldingItem,
    UsLiquidationPlanResponse,
    UsOrderHistoryItem,
    UsObservationCriterionCount,
    UsObservationStatsResponse,
    UsObservationStrategyStats,
    UsOrderPrecheckResponse,
    UsOrderPrecheckTrStep,
    UsOrderRequest,
    UsOrderResponse,
    UsOrderRuntimeLockResponse,
    UsOrderStateMonitorPreflight,
    UsOrderStateMonitorStatus,
    UsOrderStatus,
    UsAutoExitTickResponse,
    UsAutoTradeRuntimeStatus,
    UsAutoTradeStrategyStatusItem,
    UsAutoTradeStrategyStatusResponse,
    UsStrategyPnlSnapshot,
    UsStrategyPnlSummary,
    UsTakeProfitMonitorResponse,
    UsTakeProfitPlanResponse,
)
from app.schemas.market import UsAutoTradePlanResponse
from app.services.kiwoom_session import get_active_or_latest_kiwoom_session as get_active_kiwoom_session
from app.core.time import now_iso
from app.services.realtime_quote_service import realtime_summary_is_fresh, realtime_window_store
from app.services.us_account_service import US_READONLY_SERVICE_ERRORS, us_account_service
from app.services.us_condition_service import UsConditionSearchError, us_condition_service
from app.services.us_order_state_monitor import (
    ORDER_STATE_CHANNELS,
    kiwoom_order_state_monitor,
    order_state_monitor_configured,
)
from app.services.kiwoom_condition_strategy_service import kiwoom_condition_strategy_service
from trading_engine.config import get_engine_settings
from trading_engine.risk.allocation_store import CapitalAllocationStore
from trading_engine.risk.capital_allocator import evaluate_capital_allocation
from trading_engine.services.market_time import market_time_context
from trading_engine.providers.kiwoom_us.tr_codes import US_REST_BASE_URL


US_ORDER_CONFIRM = "I_UNDERSTAND_LIVE_US_ORDER"
US_ORDER_UNLOCK = "I_ACCEPT_REAL_US_ORDER_RISK"
US_ORDER_RUNTIME_LOCK_REASON = "RUNTIME_ORDER_LOCKED"
US_LIVE_ORDER_BLOCK_REASON = "LIVE_ORDER_EXECUTION_NOT_IMPLEMENTED"
_auto_trade_runtime_enabled = False
_auto_trade_observation_enabled = False
_auto_trade_started_at: str | None = None
_auto_trade_stopped_at: str | None = None
_auto_trade_strategy_condition_errors: dict[str, str] = {}


class UsOrderServiceError(RuntimeError):
    pass


class UsOrderBlocked(UsOrderServiceError):
    pass


class UsOrderTransportError(UsOrderServiceError):
    pass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    try:
        parsed = int(str(value).strip()) if value is not None else default
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    try:
        parsed = float(str(value).strip()) if value is not None else default
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _env_optional_float(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        return None
    try:
        parsed = float(str(value).strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _safe_diagnostic_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    redacted_terms = ("token", "secret", "appkey", "authorization", "account")
    lowered = text.lower()
    if any(term in lowered for term in redacted_terms):
        return exc.__class__.__name__
    return text[:160]


def _optional_safe_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if any(
        term in lowered
        for term in ("token", "secret", "appkey", "authorization", "account")
    ):
        return "REDACTED"
    return text[:80]


def _safe_nonnegative_int(value: object) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _optional_nonnegative_int(value: object) -> int | None:
    if value is None:
        return None
    return _safe_nonnegative_int(value)


def _allocation_account_scope(mode: str, safe_account_label: str) -> str:
    material = f"{str(mode).strip().lower()}:{str(safe_account_label).strip()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]


class UsOrderService:
    async def get_order_state_monitor_preflight(
        self,
    ) -> UsOrderStateMonitorPreflight:
        session = get_active_kiwoom_session()
        monitor_configured = order_state_monitor_configured()
        runtime_locked = _runtime_order_locked()
        session_valid = bool(
            session is not None
            and session.mode == "live"
            and not session.is_expired
        )
        blockers: list[str] = []
        if not monitor_configured:
            blockers.append("ORDER_STATE_MONITOR_DISABLED")
        if session is None:
            blockers.append("KIWOOM_SESSION_REQUIRED")
        elif session.mode != "live":
            blockers.append("LIVE_SESSION_REQUIRED")
        elif session.is_expired:
            blockers.append("KIWOOM_SESSION_EXPIRED")
        if not runtime_locked:
            blockers.append("RUNTIME_ORDER_LOCK_REQUIRED")

        submitted_count = 0
        eligible_symbol_count = 0
        allocation_state_available = True
        if session_valid and session is not None:
            try:
                store = CapitalAllocationStore(get_engine_settings().db_path)
                cycle = store.find_cycle(
                    account_scope=_allocation_account_scope(
                        session.mode,
                        session.safe_account_label,
                    ),
                    market_date=market_time_context().us_market_date,
                )
                if cycle is not None:
                    submitted = [
                        reservation
                        for reservation in store.list_reservations(cycle.id)
                        if reservation.status == "submitted"
                        and reservation.order_no
                    ]
                    submitted_count = len(submitted)
                    eligible_symbol_count = len(
                        {reservation.symbol for reservation in submitted}
                    )
            except (OSError, sqlite3.Error, ValueError):
                allocation_state_available = False
                blockers.append("ALLOCATION_STATE_UNAVAILABLE")
        if submitted_count == 0:
            blockers.append("NO_SUBMITTED_ORDERS")

        if not session_valid:
            observation_state = "blocked"
            required_action = "RESTORE_SESSION"
        elif not allocation_state_available:
            observation_state = "blocked"
            required_action = "CHECK_ALLOCATION_STATE"
        elif submitted_count == 0:
            observation_state = "no_target"
            required_action = "WAIT_FOR_SUBMITTED_ORDER"
        elif not runtime_locked:
            observation_state = "blocked"
            required_action = "LOCK_RUNTIME_ORDERS"
        elif not monitor_configured:
            observation_state = "blocked"
            required_action = "ENABLE_READONLY_MONITOR"
        else:
            observation_state = "ready"
            required_action = "START_OBSERVATION"

        return UsOrderStateMonitorPreflight(
            readyForObservation=observation_state == "ready",
            observationState=observation_state,
            requiredActionCode=required_action,
            monitorConfigured=monitor_configured,
            sessionPresent=session is not None,
            sessionValid=session_valid,
            runtimeOrderLocked=runtime_locked,
            submittedReservationCount=submitted_count,
            eligibleSymbolCount=eligible_symbol_count,
            channels=list(ORDER_STATE_CHANNELS),
            blockerReasons=blockers,
            source="kiwoom-f4-f5-order-state-preflight",
            updatedAt=now_iso(),
        )

    async def get_order_state_monitor_status(
        self,
    ) -> UsOrderStateMonitorStatus:
        status = kiwoom_order_state_monitor.status()
        symbols = status.get("symbols")
        channels = status.get("channels")
        return UsOrderStateMonitorStatus(
            enabled=bool(status.get("enabled")),
            running=bool(status.get("running")),
            connected=bool(status.get("connected")),
            monitoredSymbolCount=len(symbols) if isinstance(symbols, list) else 0,
            channels=[
                str(channel)
                for channel in channels
                if isinstance(channel, str)
            ]
            if isinstance(channels, list)
            else [],
            lastEventAt=_optional_safe_text(status.get("lastEventAt")),
            lastConnectedAt=_optional_safe_text(
                status.get("lastConnectedAt")
            ),
            lastHeartbeatAt=_optional_safe_text(
                status.get("lastHeartbeatAt")
            ),
            lastError=_optional_safe_text(status.get("lastError")),
            lastReconcileError=_optional_safe_text(
                status.get("lastReconcileError")
            ),
            reconnectCount=_safe_nonnegative_int(
                status.get("reconnectCount")
            ),
            nextRetrySeconds=_optional_nonnegative_int(
                status.get("nextRetrySeconds")
            ),
            updatedCount=_safe_nonnegative_int(status.get("updatedCount")),
            duplicateCount=_safe_nonnegative_int(
                status.get("duplicateCount")
            ),
            source="kiwoom-f4-f5-order-state-monitor",
            updatedAt=now_iso(),
        )

    async def get_auto_trade_strategy_status(
        self,
        *,
        refresh_catalog: bool = False,
    ) -> UsAutoTradeStrategyStatusResponse:
        try:
            catalog = (
                await us_condition_service.get_condition_list(force_refresh=True)
                if refresh_catalog
                else await us_condition_service.get_condition_list()
            )
            if catalog.conditions:
                conditions = catalog.conditions
                kiwoom_condition_strategy_service.sync(conditions)
            else:
                conditions = kiwoom_condition_strategy_service.stored_conditions()
        except UsConditionSearchError:
            conditions = kiwoom_condition_strategy_service.stored_conditions()

        enabled_conditions = [
            condition
            for condition in conditions
            if kiwoom_condition_strategy_service.is_enabled(condition.seq)
            and not bool(us_condition_service.monitor_status(condition.seq)["active"])
        ]
        for condition in enabled_conditions:
            try:
                await us_condition_service.get_condition_search(condition.seq)
                _auto_trade_strategy_condition_errors.pop(
                    kiwoom_condition_strategy_service.strategy_id(condition.seq),
                    None,
                )
            except UsConditionSearchError as exc:
                _auto_trade_strategy_condition_errors[
                    kiwoom_condition_strategy_service.strategy_id(condition.seq)
                ] = _safe_diagnostic_error(exc)

        return UsAutoTradeStrategyStatusResponse(
            strategies=[
                self._condition_strategy_status_item(condition.seq, condition.name)
                for condition in conditions
            ],
            source="kiwoom-us-condition-strategy-status",
            updatedAt=now_iso(),
        )

    async def set_auto_trade_strategy_enabled(self, strategy: str, enabled: bool) -> UsAutoTradeStrategyStatusResponse:
        try:
            catalog = await us_condition_service.get_condition_list()
            if catalog.conditions:
                kiwoom_condition_strategy_service.sync(catalog.conditions)
        except UsConditionSearchError:
            pass
        condition_seq = kiwoom_condition_strategy_service.sequence_from_strategy(strategy)
        if condition_seq is None or not kiwoom_condition_strategy_service.set_enabled(condition_seq, enabled):
            raise UsOrderBlocked("Unsupported auto-trade strategy")
        if enabled:
            try:
                await us_condition_service.get_condition_search(condition_seq)
                _auto_trade_strategy_condition_errors.pop(strategy, None)
            except UsConditionSearchError as exc:
                _auto_trade_strategy_condition_errors[strategy] = _safe_diagnostic_error(exc)
        else:
            _auto_trade_strategy_condition_errors.pop(strategy, None)
            await us_condition_service.stop_condition_monitor(condition_seq)
        _record_auto_trade_event(
            action="strategy_toggle",
            status="enabled" if enabled else "disabled",
            strategy=strategy,
        )
        from app.services.market_ranking_service import market_ranking_service

        market_ranking_service.clear_pullback_plan_cache()
        return await self.get_auto_trade_strategy_status()

    def _condition_strategy_status_item(
        self,
        condition_seq: str,
        condition_name: str,
    ) -> UsAutoTradeStrategyStatusItem:
        strategy = kiwoom_condition_strategy_service.strategy_id(condition_seq)
        enabled = kiwoom_condition_strategy_service.is_enabled(condition_seq)
        monitor = us_condition_service.monitor_status(condition_seq)
        condition_error = None
        if enabled and not monitor["active"]:
            condition_error = _auto_trade_strategy_condition_errors.get(strategy) or (
                str(monitor["error"]) if monitor["error"] else None
            )
        return UsAutoTradeStrategyStatusItem(
            strategy=strategy,
            strategyName=condition_name,
            enabled=enabled,
            conditionSeq=str(monitor["selectedSeq"] or condition_seq),
            conditionName=str(monitor["selectedName"] or condition_name),
            conditionConnected=bool(monitor["active"]),
            conditionMatchCount=int(monitor["matchCount"]),
            conditionMatches=us_condition_service.monitor_matches(condition_seq) if enabled else [],
            conditionError=condition_error,
        )

    @staticmethod
    def _strategy_condition_selection(strategy: str) -> tuple[str | None, str | None]:
        condition_seq = kiwoom_condition_strategy_service.sequence_from_strategy(strategy)
        if condition_seq is None:
            return None, None
        name = next(
            (
                condition.name
                for condition in kiwoom_condition_strategy_service.stored_conditions()
                if condition.seq == condition_seq
            ),
            None,
        )
        return condition_seq, name

    def _enabled_condition_sequences(self) -> set[str | None]:
        return set(kiwoom_condition_strategy_service.enabled_sequences())

    def is_strategy_enabled(self, strategy: str) -> bool:
        condition_seq = kiwoom_condition_strategy_service.sequence_from_strategy(strategy)
        return bool(condition_seq and kiwoom_condition_strategy_service.is_enabled(condition_seq))

    async def get_auto_trade_status(self) -> UsAutoTradeRuntimeStatus:
        from app.services.autotrade_runner import autotrade_runner_status

        status = await self.get_status()
        blockers = [
            reason
            for reason in status.blockedReasons
            if reason != US_LIVE_ORDER_BLOCK_REASON
        ]
        if status.maxOrderQuantity > 1:
            blockers.append("AUTO_TRADE_MAX_QUANTITY_NOT_SAFE")
        runner = autotrade_runner_status()
        return UsAutoTradeRuntimeStatus(
            enabled=_auto_trade_runtime_enabled,
            observationEnabled=_auto_trade_observation_enabled,
            mode=(
                "live"
                if _auto_trade_runtime_enabled
                else "observe"
                if _auto_trade_observation_enabled
                else "off"
            ),
            entryConfirmBypassEnabled=_auto_trade_runtime_enabled,
            autoExitEnabled=_auto_trade_runtime_enabled and _env_bool("KIWOOM_US_AUTO_EXIT_ENABLED", False),
            **runner,
            startedAt=_auto_trade_started_at,
            stoppedAt=_auto_trade_stopped_at,
            maxOrderQuantity=status.maxOrderQuantity,
            maxOrderNotional=status.maxOrderNotional,
            capitalUsagePct=status.capitalUsagePct,
            blockedReasons=blockers,
            source="kiwoom-us-autotrade-runtime",
            updatedAt=now_iso(),
        )

    async def list_auto_trade_events(self, limit: int = 30) -> list[UsAutoTradeEventItem]:
        safe_limit = max(1, min(int(limit), 100))
        connection = _connect_order_db()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM us_auto_trade_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
            return [_event_row_to_item(row) for row in rows]
        finally:
            connection.close()

    async def get_observation_stats(self, limit: int = 500) -> UsObservationStatsResponse:
        safe_limit = max(1, min(int(limit), 1_000))
        connection = _connect_order_db()
        try:
            rows = connection.execute(
                """
                SELECT strategy, symbol, status, blocked_reasons, created_at
                FROM us_auto_trade_events
                WHERE action = 'entry_observation'
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        finally:
            connection.close()

        buckets: dict[str, dict[str, object]] = {}
        for row in rows:
            strategy = str(row["strategy"] or "unknown")
            bucket = buckets.setdefault(
                strategy,
                {
                    "state_changes": 0,
                    "ready_changes": 0,
                    "waiting_changes": 0,
                    "symbols": set(),
                    "criteria": {},
                    "last_changed_at": None,
                },
            )
            bucket["state_changes"] = int(bucket["state_changes"]) + 1
            status = str(row["status"] or "")
            if status == "ready":
                bucket["ready_changes"] = int(bucket["ready_changes"]) + 1
            elif status == "waiting":
                bucket["waiting_changes"] = int(bucket["waiting_changes"]) + 1
            symbol = str(row["symbol"] or "").strip().upper()
            if symbol:
                symbols = bucket["symbols"]
                assert isinstance(symbols, set)
                symbols.add(symbol)
            criteria = bucket["criteria"]
            assert isinstance(criteria, dict)
            for reason in str(row["blocked_reasons"] or "").split(","):
                if reason.startswith("CRITERION_"):
                    criterion = reason.removeprefix("CRITERION_").lower()
                    criteria[criterion] = int(criteria.get(criterion, 0)) + 1
            if bucket["last_changed_at"] is None:
                bucket["last_changed_at"] = str(row["created_at"])

        strategies = []
        for strategy, bucket in buckets.items():
            criteria = bucket["criteria"]
            symbols = bucket["symbols"]
            assert isinstance(criteria, dict)
            assert isinstance(symbols, set)
            top_criteria = sorted(criteria.items(), key=lambda item: (-int(item[1]), str(item[0])))[:3]
            strategies.append(
                UsObservationStrategyStats(
                    strategy=strategy,
                    stateChanges=int(bucket["state_changes"]),
                    readyChanges=int(bucket["ready_changes"]),
                    waitingChanges=int(bucket["waiting_changes"]),
                    uniqueCandidateCount=len(symbols),
                    topFailedCriteria=[
                        UsObservationCriterionCount(criterion=str(name), count=int(count))
                        for name, count in top_criteria
                    ],
                    lastChangedAt=str(bucket["last_changed_at"]) if bucket["last_changed_at"] else None,
                )
            )
        strategies.sort(key=lambda item: (-item.stateChanges, item.strategy))
        return UsObservationStatsResponse(
            strategies=strategies,
            totalStateChanges=sum(item.stateChanges for item in strategies),
            source="kiwoom-us-observation-events",
            updatedAt=now_iso(),
        )

    async def get_auto_trade_diagnostics(self) -> UsAutoTradeDiagnosticsResponse:
        status = await self.get_auto_trade_status()
        latest_events = await self.list_auto_trade_events(limit=1)
        latest_event = latest_events[0] if latest_events else None
        pipeline = _pipeline_snapshot(status)
        plan = None
        plan_error = None

        try:
            from app.services.market_ranking_service import market_ranking_service

            plan = await market_ranking_service.get_us_pullback_auto_trade_plan()
        except Exception as exc:  # noqa: BLE001 - diagnostics must not hide runtime state.
            plan_error = _safe_diagnostic_error(exc)

        blocker_reasons: list[str] = []
        blocking_stage: str | None = None
        decision = "waiting"
        required_action = "전략 조건을 감시 중입니다."
        can_attempt_entry = False
        can_attempt_exit = _latest_armed_buy_row() is not None

        if not status.enabled and not status.observationEnabled:
            blocker_reasons.append("AUTO_TRADE_DISABLED")
            blocking_stage = "runtime"
            decision = "disabled"
            required_action = "홈 또는 전략 탭에서 전체 자동매매를 ON으로 전환하세요."
        elif status.enabled and status.blockedReasons:
            blocker_reasons.extend(status.blockedReasons)
            blocking_stage = "order_policy"
            decision = "blocked"
            required_action = "주문 정책 차단 사유를 먼저 해소하세요."
        elif plan_error:
            blocker_reasons.append("AUTO_TRADE_PLAN_UNAVAILABLE")
            blocking_stage = "plan"
            decision = "blocked"
            required_action = "랭킹/차트/조건검색 TR 응답 상태를 확인하세요."
        elif plan is None:
            blocker_reasons.append("AUTO_TRADE_PLAN_EMPTY")
            blocking_stage = "plan"
            decision = "blocked"
            required_action = "자동매매 계획 응답을 확인하세요."
        else:
            blocker_reasons.extend(plan.liveOrderBlockedReasons)
            if not plan.readyForEntry:
                blocker_reasons.append("ENTRY_CONDITIONS_NOT_READY")
            if plan.orderTicket is None:
                blocker_reasons.append("BUY_TICKET_UNAVAILABLE")

            blocker_reasons = _dedupe_reasons(blocker_reasons)
            if blocker_reasons:
                blocking_stage = "entry_conditions"
                decision = "observing" if status.observationEnabled else "blocked"
                required_action = (
                    "실주문 잠금을 유지한 채 조건검색·랭킹·차트 후보를 감시 중입니다."
                    if status.observationEnabled
                    else "조건검색/랭킹/차트/주문가능수량 중 차단 사유를 확인하세요."
                )
            else:
                decision = "observation_ready" if status.observationEnabled else "entry_ready"
                can_attempt_entry = not status.observationEnabled
                required_action = (
                    "진입 가능 후보를 확인했습니다. 관찰 모드이므로 주문은 전송하지 않습니다."
                    if status.observationEnabled
                    else (
                        "기존 포지션 매도를 감시하면서 다음 자동매매 tick에서 "
                        "배분 가능한 후보의 매수 precheck를 진행합니다."
                        if can_attempt_exit
                        else "다음 자동매매 tick에서 매수 precheck 후 주문 전송을 시도합니다."
                    )
                )

        blocker_reasons = _dedupe_reasons(blocker_reasons)
        return UsAutoTradeDiagnosticsResponse(
            decision=decision,
            canAttemptEntry=can_attempt_entry,
            canAttemptExit=can_attempt_exit,
            blockingStage=blocking_stage,
            blockerReasons=blocker_reasons,
            requiredAction=required_action,
            status=status,
            pipeline=pipeline,
            plan=plan,
            latestEvent=latest_event,
            planError=plan_error,
            source="kiwoom-us-autotrade-diagnostics",
            updatedAt=now_iso(),
        )

    async def enable_auto_trade(self) -> UsAutoTradeRuntimeStatus:
        global _auto_trade_runtime_enabled, _auto_trade_observation_enabled
        global _auto_trade_started_at, _auto_trade_stopped_at
        status = await self.get_status()
        blockers = [
            reason
            for reason in status.blockedReasons
            if reason not in {
                US_ORDER_RUNTIME_LOCK_REASON,
                US_LIVE_ORDER_BLOCK_REASON,
            }
        ]
        if status.maxOrderQuantity > 1:
            blockers.append("AUTO_TRADE_MAX_QUANTITY_NOT_SAFE")
        if blockers:
            _record_auto_trade_event(
                action="runtime_enable",
                status="blocked",
                blocked_reasons=blockers,
            )
            from app.services.autotrade_runner import autotrade_runner_status

            runner = autotrade_runner_status()
            return UsAutoTradeRuntimeStatus(
                enabled=False,
                observationEnabled=_auto_trade_observation_enabled,
                mode="blocked",
                entryConfirmBypassEnabled=False,
                autoExitEnabled=False,
                **runner,
                startedAt=_auto_trade_started_at,
                stoppedAt=_auto_trade_stopped_at,
                maxOrderQuantity=status.maxOrderQuantity,
                maxOrderNotional=status.maxOrderNotional,
                capitalUsagePct=status.capitalUsagePct,
                blockedReasons=blockers,
                source="kiwoom-us-autotrade-runtime",
                updatedAt=now_iso(),
            )
        _clear_runtime_order_lock()
        _auto_trade_observation_enabled = False
        _auto_trade_runtime_enabled = True
        _auto_trade_started_at = now_iso()
        _auto_trade_stopped_at = None
        _record_auto_trade_event(action="runtime_enable", status="enabled")
        return await self.get_auto_trade_status()

    async def disable_auto_trade(self) -> UsAutoTradeRuntimeStatus:
        global _auto_trade_runtime_enabled, _auto_trade_observation_enabled, _auto_trade_stopped_at
        _auto_trade_runtime_enabled = False
        _auto_trade_observation_enabled = False
        _auto_trade_stopped_at = now_iso()
        await kiwoom_order_state_monitor.stop()
        await self.lock_runtime_orders()
        _record_auto_trade_event(action="runtime_disable", status="disabled")
        return await self.get_auto_trade_status()

    async def enable_auto_trade_observation(self) -> UsAutoTradeRuntimeStatus:
        global _auto_trade_runtime_enabled, _auto_trade_observation_enabled
        global _auto_trade_started_at, _auto_trade_stopped_at
        _auto_trade_runtime_enabled = False
        _auto_trade_observation_enabled = True
        _auto_trade_started_at = now_iso()
        _auto_trade_stopped_at = None
        await kiwoom_order_state_monitor.stop()
        await self.lock_runtime_orders()
        _record_auto_trade_event(action="runtime_observe", status="enabled")
        return await self.get_auto_trade_status()

    async def disable_auto_trade_observation(self) -> UsAutoTradeRuntimeStatus:
        global _auto_trade_observation_enabled, _auto_trade_stopped_at
        _auto_trade_observation_enabled = False
        _auto_trade_stopped_at = now_iso()
        await self.lock_runtime_orders()
        _record_auto_trade_event(action="runtime_observe", status="disabled")
        return await self.get_auto_trade_status()

    async def ensure_order_state_monitor(self) -> dict[str, object]:
        session = get_active_kiwoom_session()
        if session is None:
            await kiwoom_order_state_monitor.stop()
            return kiwoom_order_state_monitor.status()

        store = CapitalAllocationStore(get_engine_settings().db_path)
        cycle = store.find_cycle(
            account_scope=_allocation_account_scope(
                session.mode,
                session.safe_account_label,
            ),
            market_date=market_time_context().us_market_date,
        )
        if cycle is None:
            await kiwoom_order_state_monitor.stop()
            return kiwoom_order_state_monitor.status()

        submitted = [
            reservation
            for reservation in store.list_reservations(cycle.id)
            if reservation.status == "submitted" and reservation.order_no
        ]
        if not submitted:
            await kiwoom_order_state_monitor.stop()
            return kiwoom_order_state_monitor.status()

        async def reconcile_rest_state() -> None:
            await _reconcile_submitted_allocation_reservations(
                session_mode=session.mode,
                safe_account_label=session.safe_account_label,
                force=True,
            )

        await kiwoom_order_state_monitor.ensure(
            session=session,
            cycle=cycle,
            store=store,
            symbols=[reservation.symbol for reservation in submitted],
            exchanges={
                reservation.symbol: reservation.exchange
                for reservation in submitted
            },
            reconcile=reconcile_rest_state,
        )
        return kiwoom_order_state_monitor.status()

    def record_runner_error(self, error_type: str, *, stage: str = "runner", detail: str | None = None) -> None:
        stage_code = _safe_stage_code(stage)
        reasons = [f"STAGE_{stage_code.upper()}", _safe_reason_code(error_type)]
        if detail:
            detail_code = _safe_reason_code(detail)
            if detail_code not in reasons:
                reasons.append(detail_code)
        action = "runner_tick" if stage_code == "runner" else f"runner_{stage_code}"
        _record_auto_trade_event(
            action=action,
            status="failed",
            blocked_reasons=reasons,
        )

    def record_observation_result(self, result: UsAutoEntryTickResponse) -> None:
        criteria = [
            f"CRITERION_{_safe_reason_code(criterion)}"
            for criterion in result.failedCriteria
        ]
        _record_auto_trade_event(
            action="entry_observation",
            status="ready" if result.action == "ready" else "waiting",
            strategy=result.strategy,
            symbol=result.symbol,
            exchange=result.exchange,
            blocked_reasons=[*result.blockedReasons, *criteria],
        )

    async def get_status(self) -> UsOrderStatus:
        session = get_active_kiwoom_session()
        order_enabled = _env_bool("KIWOOM_US_ENABLE_ORDER", False)
        read_only = _env_bool("KIWOOM_READ_ONLY", True)
        runtime_locked = _runtime_order_locked()
        confirm_configured = os.getenv("KIWOOM_US_ORDER_CONFIRM") == US_ORDER_CONFIRM
        live_order_unlock_configured = os.getenv("KIWOOM_US_LIVE_ORDER_UNLOCK") == US_ORDER_UNLOCK
        allowed_symbols = _allowed_symbols()
        allow_all_common_stocks = _allow_all_common_stocks()
        policy_symbols = ["COMMON_STOCK_ONLY"] if allow_all_common_stocks else allowed_symbols
        max_order_quantity = _max_order_quantity()
        max_order_notional = _max_order_notional()
        capital_usage_pct = _capital_usage_pct()
        reasons = _order_policy_blockers()
        return UsOrderStatus(
            orderEnabled=order_enabled,
            readOnly=read_only,
            runtimeOrderLocked=runtime_locked,
            sessionPresent=session is not None,
            sessionMode=session.mode if session else None,
            accountLabel=session.safe_account_label if session else None,
            liveOrderConfirmConfigured=confirm_configured,
            liveOrderUnlockConfigured=live_order_unlock_configured,
            requiredConfirmText=US_ORDER_CONFIRM,
            requiredUnlockText=US_ORDER_UNLOCK,
            allowedExchanges=["ND", "NY", "NA"],
            allowedTradeTypes=["03", "00", "26", "27", "30", "36", "37"],
            allowedSymbols=policy_symbols,
            maxOrderQuantity=max_order_quantity,
            maxOrderNotional=max_order_notional,
            capitalUsagePct=capital_usage_pct,
            blockedReasons=reasons,
            readinessChecklist=_readiness_checklist(),
            source="kiwoom-us-order-policy",
            updatedAt=now_iso(),
        )

    async def lock_runtime_orders(self) -> UsOrderRuntimeLockResponse:
        path = _runtime_lock_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"locked_at={now_iso()}\n", encoding="utf-8")
        return UsOrderRuntimeLockResponse(
            runtimeOrderLocked=True,
            source="kiwoom-us-order-runtime-lock",
            updatedAt=now_iso(),
        )

    async def precheck_order(self, payload: UsOrderRequest) -> UsOrderPrecheckResponse:
        status = await self.get_status()
        reasons: list[str] = []
        orderable_quantity: int | None = None
        orderable_amount: float | None = None
        managed_orderable_amount: float | None = None
        cash_reserve_amount: float | None = None
        currency: str | None = None
        margin_rate: str | None = None
        tr_steps: list[UsOrderPrecheckTrStep] = []
        allowed_symbols = _allowed_symbols()
        allow_all_common_stocks = _allow_all_common_stocks()
        reference_price = _order_reference_price(payload)

        if not allowed_symbols and not allow_all_common_stocks:
            reasons.append("SYMBOL_ALLOWLIST_EMPTY")
        elif not allow_all_common_stocks and allowed_symbols and payload.symbol not in allowed_symbols:
            reasons.append("SYMBOL_NOT_ALLOWED")
        if allow_all_common_stocks:
            try:
                stock_info = await us_account_service._execute(
                    "usa10100",
                    {
                        "stk_cd": payload.symbol,
                    },
                )
                is_etf = _safe_text(stock_info.data.get("isEtf"))
                stock_name = _safe_text(stock_info.data.get("stk_nm"))
                stock_english_name = _safe_text(stock_info.data.get("stk_enm"))
                derivative_like = _official_name_indicates_non_common_stock(stock_name, stock_english_name)
                if is_etf != "N":
                    reasons.append("COMMON_STOCK_ONLY")
                if derivative_like:
                    reasons.append("NON_COMMON_STOCK_NAME")
                tr_steps.append(UsOrderPrecheckTrStep(
                    trId="usa10100",
                    label="미국주식 종목 조회",
                    status="pass" if is_etf == "N" and not derivative_like else "block",
                    detail="isEtf=N, 명칭상 일반주식 확인" if is_etf == "N" and not derivative_like else "ETF/ETN/워런트 등 일반주식 제외 대상",
                ))
            except US_READONLY_SERVICE_ERRORS:
                reasons.append("COMMON_STOCK_LOOKUP_FAILED")
                tr_steps.append(UsOrderPrecheckTrStep(
                    trId="usa10100",
                    label="미국주식 종목 조회",
                    status="error",
                    detail="종목정보 TR 조회 실패",
                ))
        if payload.quantity > status.maxOrderQuantity:
            reasons.append("MAX_ORDER_QUANTITY_EXCEEDED")
        if reference_price is None:
            reasons.append("REFERENCE_PRICE_REQUIRED")
        elif payload.quantity * reference_price > status.maxOrderNotional:
            reasons.append("MAX_ORDER_NOTIONAL_EXCEEDED")
        if payload.tradeType in {"00", "30"} and not payload.orderPrice:
            reasons.append("ORDER_PRICE_REQUIRED")
        if payload.confirmText != US_ORDER_CONFIRM and not _auto_trade_runtime_enabled:
            reasons.append("CONFIRM_TEXT_REQUIRED")

        if reference_price is not None and payload.side == "buy":
            try:
                summary = await us_account_service._execute(
                    "ust31490",
                    {
                        "stex_tp": payload.exchange,
                        "stk_cd": payload.symbol,
                        "uv": _format_numeric_text(reference_price),
                    },
                )
                orderable_quantity = _safe_int(summary.data.get("min_ord_alowq"))
                orderable_amount = _safe_float(summary.data.get("min_ord_alowa"))
                if orderable_amount is not None:
                    managed_orderable_amount = round(orderable_amount * _capital_usage_pct() / 100, 4)
                    cash_reserve_amount = round(max(0.0, orderable_amount - managed_orderable_amount), 4)
                currency = (_safe_text(summary.data.get("crnc_code")) or "").upper() or None
                margin_rate = _safe_text(summary.data.get("aplc_rt") or summary.data.get("profa_rt"))
                orderability_reasons: list[str] = []
                if orderable_quantity is None:
                    orderability_reasons.append("ORDERABLE_QUANTITY_UNAVAILABLE")
                elif payload.quantity > orderable_quantity:
                    reasons.append("ORDERABLE_QUANTITY_EXCEEDED")
                    orderability_reasons.append("ORDERABLE_QUANTITY_EXCEEDED")
                if orderable_amount is None:
                    orderability_reasons.append("ORDERABLE_AMOUNT_UNAVAILABLE")
                elif payload.quantity * reference_price > orderable_amount:
                    orderability_reasons.append("ORDERABLE_AMOUNT_EXCEEDED")
                if (
                    managed_orderable_amount is not None
                    and payload.quantity * reference_price > managed_orderable_amount
                ):
                    orderability_reasons.append("CAPITAL_USAGE_LIMIT_EXCEEDED")
                if currency != "USD":
                    orderability_reasons.append("ORDERABLE_CURRENCY_UNSUPPORTED")
                reasons.extend(
                    reason
                    for reason in orderability_reasons
                    if reason not in reasons
                )
                tr_steps.append(UsOrderPrecheckTrStep(
                    trId="ust31490",
                    label="미국주식 주문가능수량",
                    status="pass" if not orderability_reasons else "block",
                    detail=(
                        f"미수불가 가능수량={orderable_quantity if orderable_quantity is not None else '-'} "
                        f"가능금액={orderable_amount if orderable_amount is not None else '-'} "
                        f"통화={currency or '-'}"
                    ),
                ))
            except US_READONLY_SERVICE_ERRORS:
                reasons.append("ORDERABLE_QUANTITY_LOOKUP_FAILED")
                tr_steps.append(UsOrderPrecheckTrStep(
                    trId="ust31490",
                    label="미국주식 주문가능수량",
                    status="error",
                    detail="주문가능수량 TR 조회 실패",
                ))
        if payload.side == "sell":
            sellable_quantity: int | None = None
            sellable_verified = False
            try:
                sellable_quantity = await _sellable_holding_quantity(payload.symbol, payload.exchange)
                sellable_verified = sellable_quantity >= payload.quantity
                tr_steps.append(UsOrderPrecheckTrStep(
                    trId="ust21070",
                    label="미국주식 잔고",
                    status="pass" if sellable_verified else "block",
                    detail=f"매도가능수량={sellable_quantity}주",
                ))
            except US_READONLY_SERVICE_ERRORS:
                sellable_quantity = None
                tr_steps.append(UsOrderPrecheckTrStep(
                    trId="ust21070",
                    label="미국주식 잔고",
                    status="error",
                    detail="매도 전 잔고 확인 실패",
                ))
            if not sellable_verified:
                fallback_reason = "잔고조회 실패 fallback" if sellable_quantity is None else "잔고 미반영 fallback"
                try:
                    net_quantity = await _today_net_filled_quantity(payload.symbol, payload.exchange)
                    if net_quantity >= payload.quantity:
                        sellable_verified = True
                    else:
                        reasons.append("SELL_HOLDINGS_NOT_VERIFIED")
                    tr_steps.append(UsOrderPrecheckTrStep(
                        trId="ust21510",
                        label="미국주식 당일 주문체결",
                        status="pass" if net_quantity >= payload.quantity else "block",
                        detail=f"{fallback_reason} · 당일 순체결수량={net_quantity}주",
                    ))
                except US_READONLY_SERVICE_ERRORS:
                    reasons.append("SELL_HOLDINGS_LOOKUP_FAILED" if sellable_quantity is None else "SELL_HOLDINGS_NOT_VERIFIED")
                    tr_steps.append(UsOrderPrecheckTrStep(
                        trId="ust21510",
                        label="미국주식 당일 주문체결",
                        status="error",
                        detail="매도 전 체결수량 확인 실패",
                    ))
        tr_steps.append(UsOrderPrecheckTrStep(
            trId="ust20000" if payload.side == "buy" else "ust20001",
            label="최종 주문 전송",
            status="ready" if not reasons else "blocked",
            detail="모든 프리체크 통과 후에만 전송" if not reasons else "차단 사유 해소 전 전송 금지",
        ))

        return UsOrderPrecheckResponse(
            canSubmit=not reasons,
            blockedReasons=reasons,
            requestSummary={
                "side": payload.side,
                "exchange": payload.exchange,
                "symbol": payload.symbol,
                "quantity": payload.quantity,
                "tradeType": payload.tradeType,
            },
            trSteps=tr_steps,
            orderableQuantity=orderable_quantity,
            orderableAmount=orderable_amount,
            capitalUsagePct=_capital_usage_pct(),
            managedOrderableAmount=managed_orderable_amount,
            cashReserveAmount=cash_reserve_amount,
            currency=currency,
            marginRate=margin_rate,
            source="kiwoom-us-order-precheck",
            updatedAt=now_iso(),
        )

    async def list_orders(self, limit: int = 30) -> list[UsOrderHistoryItem]:
        connection = _connect_order_db()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM us_order_attempts
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
        finally:
            connection.close()
        return [
            UsOrderHistoryItem(
                id=int(row["id"]),
                trId=str(row["tr_id"]),
                side=str(row["side"]),
                code=str(row["symbol"]),
                exchange=str(row["exchange"]),
                quantity=int(row["quantity"]),
                orderPrice=str(row["order_price"]),
                referencePrice=str(row["reference_price"]) if "reference_price" in row.keys() and row["reference_price"] else None,
                tradeType=str(row["trade_type"]),
                strategy=str(row["strategy"]) if "strategy" in row.keys() and row["strategy"] else None,
                reason=str(row["reason"]) if "reason" in row.keys() and row["reason"] else None,
                returnCode=str(row["return_code"]),
                returnMessage=str(row["return_msg"]),
                orderNo=str(row["order_no"]) if row["order_no"] else None,
                createdAt=str(row["created_at"]),
            )
            for row in rows
        ]

    async def get_strategy_pnl_summary(self) -> UsStrategyPnlSummary:
        refreshed = False
        warning: str | None = None
        try:
            fill_summary = await us_account_service.get_today_order_fills(side="0")
            rows = _strategy_pnl_from_fills(fill_summary.data)
            _persist_strategy_pnl(rows)
            refreshed = True
        except US_READONLY_SERVICE_ERRORS:
            warning = "ORDER_FILLS_REFRESH_FAILED"
        return UsStrategyPnlSummary(
            rows=_list_strategy_pnl_snapshots(),
            trId="ust21510",
            refreshed=refreshed,
            warning=warning,
            source="kiwoom-us-strategy-pnl-store",
            updatedAt=now_iso(),
        )

    async def get_take_profit_plan(
        self,
        target_profit_pct: float = 2.0,
        *,
        source_order_id: int | None = None,
    ) -> UsTakeProfitPlanResponse:
        target_pct = min(max(float(target_profit_pct), 0.1), 20.0)
        row = _successful_buy_row(source_order_id)

        if row is None:
            return UsTakeProfitPlanResponse(
                hasOpenBuy=False,
                targetProfitPct=target_pct,
                sellTradeType="30",
                submitEndpoint="/api/us/orders",
                blockedReasons=["NO_SUCCESSFUL_BUY_REFERENCE"],
                source="kiwoom-us-take-profit-plan",
                updatedAt=now_iso(),
            )

        entry_reference = _safe_float(row["reference_price"])
        if entry_reference is None or entry_reference <= 0:
            return UsTakeProfitPlanResponse(
                hasOpenBuy=False,
                sourceOrderId=int(row["id"]),
                targetProfitPct=target_pct,
                sellTradeType="30",
                submitEndpoint="/api/us/orders",
                blockedReasons=["BUY_REFERENCE_PRICE_MISSING"],
                source="kiwoom-us-take-profit-plan",
                updatedAt=now_iso(),
            )

        fill_row = await _latest_today_fill_for_order(row)
        fill_price = _safe_float(fill_row.get("cntr_uv")) if fill_row else None
        filled_quantity = _safe_int(fill_row.get("cntr_qty")) if fill_row else None
        fill_status = _safe_text(fill_row.get("ord_stat") or fill_row.get("ord_stat_nm")) if fill_row else None
        effective_entry = fill_price if fill_price and fill_price > 0 else entry_reference
        target_price = round(effective_entry * (1 + target_pct / 100), 4)
        exit_quantity = filled_quantity if filled_quantity and filled_quantity > 0 else int(row["quantity"])
        payload = UsOrderRequest(
            side="sell",
            exchange=str(row["exchange"]),
            symbol=str(row["symbol"]),
            quantity=exit_quantity,
            orderPrice=_format_numeric_text(target_price),
            referencePrice=_format_numeric_text(target_price),
            tradeType="30",
            confirmText="",
            reason=f"+{target_pct:.2f}% 목표 매도 프리체크",
        )
        precheck = await self.precheck_order(payload)
        return UsTakeProfitPlanResponse(
            hasOpenBuy=True,
            sourceOrderId=int(row["id"]),
            symbol=str(row["symbol"]),
            exchange=str(row["exchange"]),
            quantity=exit_quantity,
            entryReferencePrice=entry_reference,
            actualFillPrice=fill_price,
            filledQuantity=filled_quantity,
            fillStatus=fill_status,
            fillTrId="ust21510",
            targetProfitPct=target_pct,
            targetPrice=target_price,
            sellTradeType="30",
            submitEndpoint="/api/us/orders",
            precheck=precheck,
            blockedReasons=precheck.blockedReasons,
            source="kiwoom-us-take-profit-plan",
            updatedAt=now_iso(),
        )

    async def get_take_profit_monitor(
        self,
        target_profit_pct: float = 2.0,
        stop_loss_pct: float = 2.0,
        *,
        source_order_id: int | None = None,
    ) -> UsTakeProfitMonitorResponse:
        target_pct = min(max(float(target_profit_pct), 0.1), 20.0)
        stop_pct = min(max(float(stop_loss_pct), 0.1), 20.0)
        plan = await self.get_take_profit_plan(
            target_pct,
            source_order_id=source_order_id,
        )
        if not plan.hasOpenBuy or not plan.symbol or not plan.exchange or plan.targetPrice is None:
            return UsTakeProfitMonitorResponse(
                hasOpenBuy=plan.hasOpenBuy,
                sourceOrderId=plan.sourceOrderId,
                symbol=plan.symbol,
                exchange=plan.exchange,
                quantity=plan.quantity,
                targetProfitPct=target_pct,
                stopLossPct=stop_pct,
                entryReferencePrice=plan.entryReferencePrice,
                actualFillPrice=plan.actualFillPrice,
                targetPrice=plan.targetPrice,
                targetReached=False,
                stopLossTriggered=False,
                sellTicketReady=False,
                blockedReasons=plan.blockedReasons,
                source="kiwoom-us-take-profit-monitor",
                updatedAt=now_iso(),
            )

        latest_price, quote_source = await _latest_quote_price(plan.symbol, plan.exchange)
        effective_entry = plan.actualFillPrice if plan.actualFillPrice and plan.actualFillPrice > 0 else plan.entryReferencePrice
        stop_loss_price = round(effective_entry * (1 - stop_pct / 100), 4) if effective_entry and effective_entry > 0 else None
        blocked_reasons = list(plan.blockedReasons)
        target_reached = bool(latest_price is not None and latest_price >= plan.targetPrice)
        stop_loss_triggered = bool(latest_price is not None and stop_loss_price is not None and latest_price <= stop_loss_price)
        if latest_price is None:
            blocked_reasons.append("QUOTE_PRICE_UNAVAILABLE")
        elif not target_reached and not stop_loss_triggered:
            blocked_reasons.append("TARGET_PRICE_NOT_REACHED")
        spread_to_target = None
        if latest_price is not None and plan.targetPrice and plan.targetPrice > 0:
            spread_to_target = round(((plan.targetPrice - latest_price) / plan.targetPrice) * 100, 4)
        spread_to_stop_loss = None
        if latest_price is not None and stop_loss_price and stop_loss_price > 0:
            spread_to_stop_loss = round(((latest_price - stop_loss_price) / stop_loss_price) * 100, 4)
        exit_reason = "take_profit" if target_reached else "stop_loss" if stop_loss_triggered else None

        return UsTakeProfitMonitorResponse(
            hasOpenBuy=True,
            sourceOrderId=plan.sourceOrderId,
            symbol=plan.symbol,
            exchange=plan.exchange,
            quantity=plan.quantity,
            targetProfitPct=target_pct,
            stopLossPct=stop_pct,
            entryReferencePrice=plan.entryReferencePrice,
            actualFillPrice=plan.actualFillPrice,
            targetPrice=plan.targetPrice,
            stopLossPrice=stop_loss_price,
            latestPrice=latest_price,
            targetReached=target_reached,
            stopLossTriggered=stop_loss_triggered,
            spreadToTargetPct=spread_to_target,
            spreadToStopLossPct=spread_to_stop_loss,
            exitReason=exit_reason,
            quoteTrId=quote_source,
            sellTicketReady=(target_reached or stop_loss_triggered) and plan.precheck is not None and plan.precheck.canSubmit,
            blockedReasons=blocked_reasons,
            source="kiwoom-us-take-profit-monitor",
            updatedAt=now_iso(),
        )

    async def run_auto_exit_tick(self) -> UsAutoExitTickResponse:
        if not _env_bool("KIWOOM_US_AUTO_EXIT_ENABLED", False):
            return UsAutoExitTickResponse(
                enabled=False,
                action="disabled",
                blockedReasons=["AUTO_EXIT_DISABLED"],
                source="kiwoom-us-auto-exit-tick",
                updatedAt=now_iso(),
            )
        if not _auto_trade_runtime_enabled:
            return UsAutoExitTickResponse(
                enabled=False,
                action="disabled",
                blockedReasons=["AUTO_TRADE_DISABLED"],
                source="kiwoom-us-auto-exit-tick",
                updatedAt=now_iso(),
            )
        await _reconcile_stale_armed_buy_rows()
        rows = _armed_buy_rows()
        if not rows:
            if _auto_trade_runtime_enabled:
                candidate = _latest_successful_buy_row()
                if candidate is not None and int(candidate["auto_exit_completed"] or 0) == 0:
                    _mark_auto_exit_armed(int(candidate["id"]))
                    _record_auto_trade_event(
                        action="auto_exit",
                        status="armed",
                        symbol=str(candidate["symbol"]),
                        exchange=str(candidate["exchange"]),
                        side="sell",
                        source_order_id=int(candidate["id"]),
                    )
                    rows = _armed_buy_rows()
        if not rows:
            return UsAutoExitTickResponse(
                enabled=True,
                action="idle",
                blockedReasons=["NO_ARMED_BUY_ORDER"],
                source="kiwoom-us-auto-exit-tick",
                updatedAt=now_iso(),
            )

        monitored: list[tuple[sqlite3.Row, UsTakeProfitMonitorResponse]] = []
        pending_exit_rows: list[sqlite3.Row] = []
        for row in reversed(rows):
            pending_exit_order_no = _safe_text(row["auto_exit_order_no"])
            if pending_exit_order_no:
                fill = await _latest_today_auto_exit_fill(row)
                filled_quantity = _safe_int(fill.get("cntr_qty")) if fill else None
                if filled_quantity is not None and filled_quantity >= int(row["quantity"]):
                    if not _close_auto_exit_allocation(row):
                        _record_auto_trade_event(
                            action="auto_exit",
                            status="blocked",
                            symbol=str(row["symbol"]),
                            exchange=str(row["exchange"]),
                            side="sell",
                            tr_id="ust21510",
                            source_order_id=int(row["id"]),
                            blocked_reasons=["ALLOCATION_CLOSE_PENDING"],
                        )
                        pending_exit_rows.append(row)
                        continue
                    _mark_auto_exit_completed(
                        int(row["id"]),
                        str(row["auto_exit_reason"] or "filled"),
                        pending_exit_order_no,
                    )
                    _record_auto_trade_event(
                        action="auto_exit",
                        status="filled",
                        symbol=str(row["symbol"]),
                        exchange=str(row["exchange"]),
                        side="sell",
                        tr_id="ust21510",
                        source_order_id=int(row["id"]),
                    )
                    continue
                pending_exit_rows.append(row)
                continue

            exit_profile = _auto_exit_profile_for_order(row)
            monitor = await self.get_take_profit_monitor(
                target_profit_pct=exit_profile["targetProfitPct"],
                stop_loss_pct=exit_profile["stopLossPct"],
                source_order_id=int(row["id"]),
            )
            if monitor.sourceOrderId != int(row["id"]):
                blocked_reasons = ["POSITION_MONITOR_MISMATCH"]
                _record_auto_trade_event(
                    action="auto_exit",
                    status="blocked",
                    symbol=str(row["symbol"]),
                    exchange=str(row["exchange"]),
                    side="sell",
                    tr_id="ust20001",
                    source_order_id=int(row["id"]),
                    blocked_reasons=blocked_reasons,
                )
                return UsAutoExitTickResponse(
                    enabled=True,
                    action="blocked",
                    monitoredPositionCount=len(rows),
                    sourceOrderId=int(row["id"]),
                    symbol=str(row["symbol"]),
                    exchange=str(row["exchange"]),
                    quantity=int(row["quantity"]),
                    blockedReasons=blocked_reasons,
                    source="kiwoom-us-auto-exit-tick",
                    updatedAt=now_iso(),
                )
            if monitor.exitReason:
                return await self._execute_auto_exit_for_row(
                    row,
                    monitor,
                    monitored_position_count=len(rows),
                )
            monitored.append((row, monitor))

        if pending_exit_rows:
            row = pending_exit_rows[0]
            return UsAutoExitTickResponse(
                enabled=True,
                action="pending_fill",
                monitoredPositionCount=len(rows),
                sourceOrderId=int(row["id"]),
                exitOrderNo=_safe_text(row["auto_exit_order_no"]),
                exitReason=_safe_text(row["auto_exit_reason"]),
                trId="ust21510",
                symbol=str(row["symbol"]),
                exchange=str(row["exchange"]),
                quantity=int(row["quantity"]),
                warning="EXIT_ORDER_AWAITING_FILL",
                blockedReasons=["EXIT_ORDER_PENDING_FILL"],
                source="kiwoom-us-auto-exit-tick",
                updatedAt=now_iso(),
            )
        if not monitored:
            return UsAutoExitTickResponse(
                enabled=True,
                action="idle",
                monitoredPositionCount=len(rows),
                blockedReasons=["NO_ARMED_BUY_ORDER"],
                source="kiwoom-us-auto-exit-tick",
                updatedAt=now_iso(),
            )

        row, monitor = monitored[0]
        return UsAutoExitTickResponse(
            enabled=True,
            action="monitoring",
            monitoredPositionCount=len(monitored),
            sourceOrderId=int(row["id"]),
            symbol=str(row["symbol"]),
            exchange=str(row["exchange"]),
            quantity=monitor.quantity or int(row["quantity"]),
            latestPrice=monitor.latestPrice,
            targetPrice=monitor.targetPrice,
            stopLossPrice=monitor.stopLossPrice,
            blockedReasons=monitor.blockedReasons,
            source="kiwoom-us-auto-exit-tick",
            updatedAt=now_iso(),
        )

    async def _execute_auto_exit_for_row(
        self,
        row: sqlite3.Row,
        monitor: UsTakeProfitMonitorResponse,
        *,
        monitored_position_count: int,
    ) -> UsAutoExitTickResponse:
        quantity = monitor.quantity or int(row["quantity"])
        if not monitor.sellTicketReady:
            _record_auto_trade_event(
                action="auto_exit",
                status="blocked",
                symbol=str(row["symbol"]),
                exchange=str(row["exchange"]),
                side="sell",
                tr_id="ust20001",
                source_order_id=int(row["id"]),
                blocked_reasons=monitor.blockedReasons,
            )
            return UsAutoExitTickResponse(
                enabled=True,
                action="blocked",
                monitoredPositionCount=monitored_position_count,
                sourceOrderId=int(row["id"]),
                exitReason=monitor.exitReason,
                symbol=str(row["symbol"]),
                exchange=str(row["exchange"]),
                quantity=quantity,
                latestPrice=monitor.latestPrice,
                targetPrice=monitor.targetPrice,
                stopLossPrice=monitor.stopLossPrice,
                blockedReasons=monitor.blockedReasons,
                source="kiwoom-us-auto-exit-tick",
                updatedAt=now_iso(),
            )

        exit_price = monitor.latestPrice or monitor.targetPrice or monitor.stopLossPrice
        if exit_price is None:
            _record_auto_trade_event(
                action="auto_exit",
                status="blocked",
                symbol=str(row["symbol"]),
                exchange=str(row["exchange"]),
                side="sell",
                tr_id="ust20001",
                source_order_id=int(row["id"]),
                blocked_reasons=["EXIT_PRICE_UNAVAILABLE"],
            )
            return UsAutoExitTickResponse(
                enabled=True,
                action="blocked",
                monitoredPositionCount=monitored_position_count,
                sourceOrderId=int(row["id"]),
                exitReason=monitor.exitReason,
                symbol=str(row["symbol"]),
                exchange=str(row["exchange"]),
                quantity=quantity,
                blockedReasons=["EXIT_PRICE_UNAVAILABLE"],
                source="kiwoom-us-auto-exit-tick",
                updatedAt=now_iso(),
            )

        sell_payload = UsOrderRequest(
            side="sell",
            exchange=str(row["exchange"]),
            symbol=str(row["symbol"]),
            quantity=quantity,
            orderPrice="" if monitor.exitReason == "stop_loss" else _format_numeric_text(monitor.targetPrice or exit_price),
            referencePrice=_format_numeric_text(exit_price),
            tradeType="03" if monitor.exitReason == "stop_loss" else "30",
            confirmText=US_ORDER_CONFIRM,
            reason=f"auto_exit_{monitor.exitReason}",
        )
        try:
            result = await self.place_order(sell_payload)
        except US_ORDER_SERVICE_ERRORS as exc:
            blocked_reasons = [str(exc)] if str(exc) else ["AUTO_EXIT_SELL_FAILED"]
            _record_auto_trade_event(
                action="auto_exit",
                status="blocked",
                symbol=str(row["symbol"]),
                exchange=str(row["exchange"]),
                side="sell",
                tr_id="ust20001",
                source_order_id=int(row["id"]),
                blocked_reasons=blocked_reasons,
            )
            return UsAutoExitTickResponse(
                enabled=True,
                action="retry_pending",
                monitoredPositionCount=monitored_position_count,
                sourceOrderId=int(row["id"]),
                exitReason=monitor.exitReason,
                trId="ust20001",
                symbol=str(row["symbol"]),
                exchange=str(row["exchange"]),
                quantity=quantity,
                latestPrice=monitor.latestPrice,
                targetPrice=monitor.targetPrice,
                stopLossPrice=monitor.stopLossPrice,
                retryPlanned=True,
                retryCount=1,
                warning="AUTO_EXIT_SELL_FAILED_RETRY_NEXT_TICK",
                blockedReasons=blocked_reasons,
                source="kiwoom-us-auto-exit-tick",
                updatedAt=now_iso(),
            )
        _mark_auto_exit_submitted(int(row["id"]), monitor.exitReason, result.orderNo)
        _record_auto_trade_event(
            action="auto_exit",
            status="submitted",
            symbol=result.code,
            exchange=result.exchange,
            side="sell",
            tr_id=result.trId,
            source_order_id=int(row["id"]),
        )
        return UsAutoExitTickResponse(
            enabled=True,
            action="submitted",
            monitoredPositionCount=monitored_position_count,
            sourceOrderId=int(row["id"]),
            exitOrderNo=result.orderNo,
            exitReason=monitor.exitReason,
            trId=result.trId,
            symbol=result.code,
            exchange=result.exchange,
            quantity=quantity,
            latestPrice=monitor.latestPrice,
            targetPrice=monitor.targetPrice,
            stopLossPrice=monitor.stopLossPrice,
            blockedReasons=[],
            source="kiwoom-us-auto-exit-tick",
            updatedAt=result.updatedAt,
        )

    async def arm_latest_buy_for_auto_exit(self) -> UsAutoExitTickResponse:
        if not _env_bool("KIWOOM_US_AUTO_EXIT_ENABLED", False):
            return UsAutoExitTickResponse(
                enabled=False,
                action="disabled",
                blockedReasons=["AUTO_EXIT_DISABLED"],
                source="kiwoom-us-auto-exit-arm",
                updatedAt=now_iso(),
            )
        row = _latest_successful_buy_row()
        if row is None:
            return UsAutoExitTickResponse(
                enabled=True,
                action="blocked",
                blockedReasons=["NO_SUCCESSFUL_BUY_REFERENCE"],
                source="kiwoom-us-auto-exit-arm",
                updatedAt=now_iso(),
            )
        if int(row["auto_exit_completed"] or 0) == 1:
            return UsAutoExitTickResponse(
                enabled=True,
                action="blocked",
                sourceOrderId=int(row["id"]),
                symbol=str(row["symbol"]),
                exchange=str(row["exchange"]),
                quantity=int(row["quantity"]),
                blockedReasons=["AUTO_EXIT_ALREADY_COMPLETED"],
                source="kiwoom-us-auto-exit-arm",
                updatedAt=now_iso(),
            )
        _mark_auto_exit_armed(int(row["id"]))
        _record_auto_trade_event(
            action="auto_exit",
            status="armed",
            symbol=str(row["symbol"]),
            exchange=str(row["exchange"]),
            side="sell",
            source_order_id=int(row["id"]),
        )
        return UsAutoExitTickResponse(
            enabled=True,
            action="armed",
            sourceOrderId=int(row["id"]),
            symbol=str(row["symbol"]),
            exchange=str(row["exchange"]),
            quantity=int(row["quantity"]),
            blockedReasons=[],
            source="kiwoom-us-auto-exit-arm",
            updatedAt=now_iso(),
        )

    async def get_liquidation_plan(self) -> UsLiquidationPlanResponse:
        holdings_for_order = await us_account_service.get_holdings_for_order(max_quantity=_max_order_quantity())
        holdings = [
            UsLiquidationHoldingItem(
                symbol=item.symbol,
                exchange=item.exchange,
                quantity=item.sellableQuantity,
                price=item.price,
                rawQuantityField=item.rawQuantityField,
                rawExchangeField=item.rawExchangeField,
                rawExchangeValue=item.rawExchangeValue,
                blockedReasons=item.blockedReasons,
            )
            for item in holdings_for_order
        ]
        executable_count = sum(1 for item in holdings if not item.blockedReasons)
        blockers: list[str] = []
        if not holdings:
            blockers.append("NO_HOLDINGS_ROWS_FOUND")
        if executable_count == 0 and holdings:
            blockers.append("NO_EXECUTABLE_HOLDINGS")
        return UsLiquidationPlanResponse(
            enabled=_env_bool("KIWOOM_US_ENABLE_ORDER", False) and not _env_bool("KIWOOM_READ_ONLY", True),
            action="plan",
            holdings=holdings,
            executableCount=executable_count,
            totalCount=len(holdings),
            blockedReasons=blockers,
            source="kiwoom-us-liquidation-plan",
            updatedAt=now_iso(),
        )

    async def execute_liquidation(self) -> UsLiquidationExecuteResponse:
        plan = await self.get_liquidation_plan()
        if not _auto_trade_runtime_enabled:
            return UsLiquidationExecuteResponse(
                enabled=False,
                action="blocked",
                submitted=[],
                skipped=plan.holdings,
                blockedReasons=["AUTO_TRADE_DISABLED"],
                source="kiwoom-us-liquidation-execute",
                updatedAt=now_iso(),
            )
        if plan.blockedReasons:
            return UsLiquidationExecuteResponse(
                enabled=True,
                action="blocked",
                submitted=[],
                skipped=plan.holdings,
                blockedReasons=plan.blockedReasons,
                source="kiwoom-us-liquidation-execute",
                updatedAt=now_iso(),
            )

        submitted: list[UsOrderResponse] = []
        skipped: list[UsLiquidationHoldingItem] = []
        for holding in plan.holdings:
            if holding.blockedReasons or not holding.exchange:
                skipped.append(holding)
                continue
            payload = UsOrderRequest(
                side="sell",
                exchange=holding.exchange,
                symbol=holding.symbol,
                quantity=holding.quantity,
                orderPrice="",
                referencePrice=_format_numeric_text(holding.price or 0),
                tradeType="03",
                confirmText="",
                reason="end_of_day_liquidation_switch",
            )
            try:
                result = await self.place_order(payload)
            except US_ORDER_SERVICE_ERRORS:
                skipped.append(holding.model_copy(update={"blockedReasons": ["SELL_ORDER_FAILED"]}))
                _record_auto_trade_event(
                    action="liquidation",
                    status="blocked",
                    symbol=holding.symbol,
                    exchange=holding.exchange,
                    side="sell",
                    tr_id="ust20001",
                    blocked_reasons=["SELL_ORDER_FAILED"],
                )
                continue
            submitted.append(result)
            _record_auto_trade_event(
                action="liquidation",
                status="submitted",
                symbol=result.code,
                exchange=result.exchange,
                side="sell",
                tr_id=result.trId,
            )

        return UsLiquidationExecuteResponse(
            enabled=True,
            action="submitted" if submitted else "blocked",
            submitted=submitted,
            skipped=skipped,
            blockedReasons=[] if submitted else ["NO_SELL_ORDER_SUBMITTED"],
            source="kiwoom-us-liquidation-execute",
            updatedAt=now_iso(),
        )

    async def run_auto_entry_tick(self) -> UsAutoEntryTickResponse:
        strategy = "kiwoom-condition"
        if not _auto_trade_runtime_enabled:
            return UsAutoEntryTickResponse(
                enabled=False,
                action="disabled",
                strategy=strategy,
                blockedReasons=["AUTO_TRADE_DISABLED"],
                source="kiwoom-us-auto-entry-tick",
                updatedAt=now_iso(),
            )
        session = get_active_kiwoom_session()
        order_state_monitor_status: dict[str, object] = {}
        if session is not None:
            await _reconcile_submitted_allocation_reservations(
                session_mode=session.mode,
                safe_account_label=session.safe_account_label,
            )
            order_state_monitor_status = (
                await self.ensure_order_state_monitor()
            )
        order_state_blocker = None
        if (
            order_state_monitor_status.get("enabled") is True
            and bool(order_state_monitor_status.get("symbols"))
        ):
            if order_state_monitor_status.get("connected") is not True:
                order_state_blocker = "ORDER_STATE_MONITOR_UNAVAILABLE"
            elif order_state_monitor_status.get("lastReconcileError"):
                order_state_blocker = "ORDER_STATE_RECONCILIATION_FAILED"
        if order_state_blocker:
            return UsAutoEntryTickResponse(
                enabled=True,
                action="waiting",
                strategy=strategy,
                blockedReasons=[order_state_blocker],
                source="kiwoom-us-auto-entry-tick",
                updatedAt=now_iso(),
            )
        pending_order_blocker = _submitted_order_state_blocker(
            session_mode=session.mode if session else "",
            safe_account_label=session.safe_account_label if session else "",
        )
        if pending_order_blocker:
            return UsAutoEntryTickResponse(
                enabled=True,
                action="waiting",
                strategy=strategy,
                blockedReasons=[pending_order_blocker],
                source="kiwoom-us-auto-entry-tick",
                updatedAt=now_iso(),
            )
        await _reconcile_stale_armed_buy_rows()

        from app.services.market_ranking_service import market_ranking_service

        plans = await _auto_entry_candidate_plans(market_ranking_service)
        blocked_attempts: list[tuple[UsAutoTradePlanResponse, list[str]]] = []

        for plan in plans:
            strategy = plan.strategy
            blockers = _auto_entry_plan_blockers(plan)
            if blockers:
                blocked_attempts.append((plan, blockers))
                continue

            ticket = plan.orderTicket
            if ticket is None:
                blocked_attempts.append((plan, ["BUY_TICKET_UNAVAILABLE"]))
                continue

            payload = UsOrderRequest(
                side="buy",
                exchange=ticket.exchange,
                symbol=ticket.symbol,
                quantity=ticket.quantity,
                orderPrice="" if ticket.tradeType == "03" else _format_numeric_text(ticket.referencePrice),
                referencePrice=_format_numeric_text(ticket.referencePrice),
                tradeType=ticket.tradeType,
                confirmText="",
                reason=f"auto_entry_{strategy}",
            )
            precheck = await self.precheck_order(payload)
            if not precheck.canSubmit:
                blocked_attempts.append((plan, precheck.blockedReasons))
                continue

            orderable_cash = precheck.managedOrderableAmount
            if orderable_cash is None and precheck.orderableAmount is not None:
                orderable_cash = round(precheck.orderableAmount * _capital_usage_pct() / 100, 4)
            if orderable_cash is None or orderable_cash <= 0:
                blocked_attempts.append((plan, ["ORDERABLE_CASH_UNAVAILABLE"]))
                continue
            if session is None:
                blocked_attempts.append((plan, ["KIWOOM_SESSION_REQUIRED"]))
                continue
            allocation_store = CapitalAllocationStore(get_engine_settings().db_path)
            allocation_cycle = allocation_store.ensure_cycle(
                account_scope=_allocation_account_scope(session.mode, session.safe_account_label),
                market_date=market_time_context().us_market_date,
                orderable_cash=orderable_cash,
                currency=precheck.currency or "USD",
            )
            allocation_state = allocation_store.load_state(
                cycle=allocation_cycle,
                orderable_cash=orderable_cash,
            )
            allocation = evaluate_capital_allocation(
                state=allocation_state,
                symbol=ticket.symbol,
                reference_price=ticket.referencePrice,
                max_quantity=ticket.quantity,
            )
            if not allocation.allowed:
                blocked_attempts.append((plan, list(allocation.blocked_reasons)))
                continue
            payload = payload.model_copy(update={"quantity": allocation.quantity})
            if allocation.quantity != ticket.quantity:
                resized_precheck = await self.precheck_order(payload)
                if not resized_precheck.canSubmit:
                    blocked_attempts.append((plan, resized_precheck.blockedReasons))
                    continue
            reservation = allocation_store.reserve(
                cycle=allocation_cycle,
                decision=allocation,
                strategy=strategy,
                exchange=ticket.exchange,
                reference_price=ticket.referencePrice,
            )
            try:
                result = await self.place_order(payload)
            except Exception:
                allocation_store.release(reservation.id)
                raise
            allocation_store.mark_submitted(reservation.id, result.orderNo)
            _link_order_attempt_allocation(
                order_no=result.orderNo,
                symbol=result.code,
                exchange=result.exchange,
                reservation_id=reservation.id,
            )
            await self.ensure_order_state_monitor()
            _record_auto_trade_event(
                action="auto_entry",
                status="submitted",
                symbol=result.code,
                exchange=result.exchange,
                side="buy",
                tr_id=result.trId,
                strategy=strategy,
            )
            return UsAutoEntryTickResponse(
                enabled=True,
                action="submitted",
                strategy=strategy,
                allocationCycleId=allocation_cycle.id,
                allocationReservationId=reservation.id,
                positionSlot=allocation.position_slot,
                tranche=allocation.tranche,
                reservedNotional=allocation.estimated_notional,
                remainingCash=allocation.remaining_cash,
                symbol=result.code,
                exchange=result.exchange,
                quantity=allocation.quantity,
                referencePrice=ticket.referencePrice,
                trId=result.trId,
                entryOrderNo=result.orderNo,
                targetProfitPct=ticket.targetProfitPct,
                takeProfitPrice=ticket.takeProfitPrice,
                blockedReasons=[],
                source="kiwoom-us-auto-entry-tick",
                updatedAt=result.updatedAt,
            )

        if blocked_attempts:
            plan, blockers = _best_blocked_auto_entry_attempt(blocked_attempts)
            strategy = plan.strategy
            return UsAutoEntryTickResponse(
                enabled=True,
                action="waiting",
                strategy=strategy,
                symbol=plan.target.code if plan.target else None,
                exchange=plan.target.exchange if plan.target else None,
                blockedReasons=_dedupe_reasons(blockers),
                source="kiwoom-us-auto-entry-tick",
                updatedAt=now_iso(),
            )

        return UsAutoEntryTickResponse(
            enabled=True,
            action="waiting",
            strategy=strategy,
            blockedReasons=["AUTO_TRADE_PLAN_EMPTY"],
            source="kiwoom-us-auto-entry-tick",
            updatedAt=now_iso(),
        )

    async def run_auto_entry_observation_tick(self) -> UsAutoEntryTickResponse:
        strategy = "strategy-observation"
        if not _auto_trade_observation_enabled:
            return UsAutoEntryTickResponse(
                enabled=False,
                action="disabled",
                strategy=strategy,
                blockedReasons=["AUTO_TRADE_OBSERVATION_DISABLED"],
                source="kiwoom-us-auto-entry-observation",
                updatedAt=now_iso(),
            )
        if not _runtime_order_locked():
            await self.lock_runtime_orders()

        from app.services.market_ranking_service import market_ranking_service

        plans = await _auto_entry_candidate_plans(market_ranking_service)
        attempts = [
            (
                plan,
                [] if plan.readyForEntry else ["ENTRY_CONDITIONS_NOT_READY"],
            )
            for plan in plans
        ]
        ready = next((plan for plan, blockers in attempts if not blockers), None)
        if ready is not None:
            ticket = ready.orderTicket
            return UsAutoEntryTickResponse(
                enabled=True,
                action="ready",
                strategy=ready.strategy,
                symbol=ready.target.code if ready.target else None,
                exchange=ready.target.exchange if ready.target else None,
                quantity=ticket.quantity if ticket else None,
                referencePrice=ticket.referencePrice if ticket else None,
                targetProfitPct=ticket.targetProfitPct if ticket else None,
                takeProfitPrice=ticket.takeProfitPrice if ticket else None,
                failedCriteria=[],
                blockedReasons=[],
                source="kiwoom-us-auto-entry-observation",
                updatedAt=now_iso(),
            )
        if attempts:
            plan, blockers = _best_blocked_auto_entry_attempt(attempts)
            return UsAutoEntryTickResponse(
                enabled=True,
                action="waiting",
                strategy=plan.strategy,
                symbol=plan.target.code if plan.target else None,
                exchange=plan.target.exchange if plan.target else None,
                failedCriteria=[
                    criterion.key
                    for criterion in plan.criteria
                    if criterion.status == "fail"
                ],
                blockedReasons=_dedupe_reasons(blockers),
                source="kiwoom-us-auto-entry-observation",
                updatedAt=now_iso(),
            )
        return UsAutoEntryTickResponse(
            enabled=True,
            action="waiting",
            strategy=strategy,
            blockedReasons=["AUTO_TRADE_PLAN_EMPTY"],
            source="kiwoom-us-auto-entry-observation",
            updatedAt=now_iso(),
        )

    async def place_order(self, payload: UsOrderRequest) -> UsOrderResponse:
        # Keep all live financial mutations unavailable in this baseline.
        # This is the single submission boundary: no ust20000/ust20001 request
        # may reach the network regardless of upstream status or configuration.
        raise UsOrderBlocked(US_LIVE_ORDER_BLOCK_REASON)

us_order_service = UsOrderService()


US_ORDER_SERVICE_ERRORS = (UsOrderBlocked, UsOrderTransportError)


def _order_policy_blockers() -> list[str]:
    return [US_LIVE_ORDER_BLOCK_REASON]


def _dedupe_reasons(reasons: list[str]) -> list[str]:
    result: list[str] = []
    for reason in reasons:
        if reason and reason not in result:
            result.append(reason)
    return result


async def _auto_entry_candidate_plans(market_ranking_service) -> list[UsAutoTradePlanResponse]:
    try:
        plans_response = await market_ranking_service.get_us_pullback_auto_trade_plans()
        plans = [
            plan for plan in (plans_response.candidatePlans or plans_response.plans)
            if plan is not None and us_order_service.is_strategy_enabled(plan.strategy)
        ]
        if plans:
            return plans
    except Exception:
        pass
    plan = await market_ranking_service.get_us_pullback_auto_trade_plan()
    return [plan]


def _auto_entry_plan_blockers(plan: UsAutoTradePlanResponse) -> list[str]:
    blockers = list(plan.liveOrderBlockedReasons)
    if not plan.readyForEntry:
        blockers.append("ENTRY_CONDITIONS_NOT_READY")
    if plan.orderTicket is None:
        blockers.append("BUY_TICKET_UNAVAILABLE")
    return _dedupe_reasons(blockers)


def _best_blocked_auto_entry_attempt(
    attempts: list[tuple[UsAutoTradePlanResponse, list[str]]],
) -> tuple[UsAutoTradePlanResponse, list[str]]:
    return sorted(
        attempts,
        key=lambda item: (
            item[0].readyForEntry,
            item[0].passedCriteriaCount,
            -(item[0].targetRank or 99),
        ),
        reverse=True,
    )[0]


def _safe_reason_code(value: str) -> str:
    lowered = str(value).lower()
    if any(term in lowered for term in ("token", "secret", "appkey", "authorization", "account")):
        return "RUNNER_ERROR"
    cleaned = "".join(ch for ch in str(value).strip().upper() if ch.isalnum() or ch == "_")
    return cleaned[:80] or "UNKNOWN_ERROR"


def _safe_stage_code(value: str) -> str:
    cleaned = "".join(ch for ch in str(value).strip().lower() if ch.isalnum() or ch == "_")
    return cleaned[:40] or "runner"


def _pipeline_snapshot(status: UsAutoTradeRuntimeStatus) -> UsAutoTradePipelineSnapshot:
    today = now_iso()[:10]
    orders_today = 0
    events_today = 0
    realtime_events_today = 0
    latest_order_at: str | None = None
    latest_event_at: str | None = None
    latest_realtime_at: str | None = None
    latest_event_action: str | None = None
    latest_event_status: str | None = None

    connection = _connect_order_db()
    try:
        order_row = connection.execute(
            """
            SELECT COUNT(*) AS count, MAX(created_at) AS latest
            FROM us_order_attempts
            WHERE created_at >= ?
            """,
            (f"{today}T00:00:00",),
        ).fetchone()
        orders_today = int(order_row["count"] or 0)
        latest_order_at = order_row["latest"]

        event_row = connection.execute(
            """
            SELECT COUNT(*) AS count, MAX(created_at) AS latest
            FROM us_auto_trade_events
            WHERE created_at >= ?
            """,
            (f"{today}T00:00:00",),
        ).fetchone()
        events_today = int(event_row["count"] or 0)
        latest_event_at = event_row["latest"]

        latest_event = connection.execute(
            """
            SELECT action, status
            FROM us_auto_trade_events
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        if latest_event is not None:
            latest_event_action = latest_event["action"]
            latest_event_status = latest_event["status"]

        try:
            realtime_row = connection.execute(
                """
                SELECT COUNT(*) AS count, MAX(created_at) AS latest
                FROM realtime_quote_events
                WHERE created_at >= ?
                """,
                (f"{today}T00:00:00",),
            ).fetchone()
            realtime_events_today = int(realtime_row["count"] or 0)
            latest_realtime_at = realtime_row["latest"]
        except sqlite3.Error:
            realtime_events_today = 0
            latest_realtime_at = None
    finally:
        connection.close()

    data_flow_ok = realtime_events_today > 0
    order_flow_ok = orders_today > 0
    runner_healthy = status.runnerRunning and not status.runnerLastError
    warning = None
    if status.enabled and status.runnerEnabled and not status.runnerRunning:
        warning = "RUNNER_NOT_RUNNING"
    elif status.enabled and status.runnerLastError:
        warning = "RUNNER_LAST_ERROR"
    elif status.enabled and not data_flow_ok:
        warning = "NO_REALTIME_EVENTS_TODAY"
    elif status.enabled and not order_flow_ok:
        warning = "NO_ORDER_ATTEMPTS_TODAY"

    return UsAutoTradePipelineSnapshot(
        todayDate=today,
        ordersToday=orders_today,
        eventsToday=events_today,
        realtimeEventsToday=realtime_events_today,
        latestOrderAt=latest_order_at,
        latestEventAt=latest_event_at,
        latestRealtimeAt=latest_realtime_at,
        latestEventAction=latest_event_action,
        latestEventStatus=latest_event_status,
        dataFlowOk=data_flow_ok,
        orderFlowOk=order_flow_ok,
        runnerHealthy=runner_healthy,
        warning=warning,
    )


def _readiness_checklist() -> list[dict[str, str | bool]]:
    return [
        {
            "key": "final_order_boundary",
            "label": "최종 주문 전송 경계",
            "passed": False,
            "detail": "실주문 네트워크 전송 미구현",
        },
    ]


def _allowed_symbols() -> list[str]:
    raw = os.getenv("KIWOOM_US_ALLOWED_SYMBOLS", "")
    symbols: list[str] = []
    for item in raw.split(","):
        symbol = "".join(ch for ch in item.upper().strip() if ch.isalnum() or ch in {".", "-"})
        if symbol and symbol not in symbols:
            symbols.append(symbol[:12])
    return symbols


def _runtime_lock_file() -> Path:
    configured = os.getenv("KIWOOM_US_ORDER_RUNTIME_LOCK_FILE")
    if configured and configured.strip():
        return Path(configured).expanduser()
    return Path("/tmp/strategy-pilot-us-order.lock")


def _runtime_order_locked() -> bool:
    return _runtime_lock_file().exists()


def _clear_runtime_order_lock() -> None:
    _runtime_lock_file().unlink(missing_ok=True)


def _max_order_quantity() -> int:
    return _env_int("KIWOOM_US_MAX_ORDER_QUANTITY", 100)


def _capital_usage_pct() -> float:
    return min(100.0, max(1.0, _env_float("KIWOOM_US_CAPITAL_USAGE_PCT", 100.0)))


def _max_order_notional() -> float:
    krw_limit = _env_optional_float("KIWOOM_US_MAX_ORDER_KRW")
    if krw_limit is not None:
        usd_krw_rate = _env_float("KIWOOM_US_ORDER_USD_KRW_RATE", 1400.0)
        return max(round(krw_limit / usd_krw_rate, 2), 0.01)
    return _env_float("KIWOOM_US_MAX_ORDER_NOTIONAL", 10_000.0)


def _allow_all_common_stocks() -> bool:
    return _env_bool("KIWOOM_US_ALLOW_ALL_COMMON_STOCKS", False) and _env_bool("KIWOOM_US_COMMON_STOCK_ONLY", True)


def _order_reference_price(payload: UsOrderRequest) -> float | None:
    value = payload.referencePrice or payload.orderPrice
    try:
        parsed = float(str(value).strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _format_numeric_text(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _safe_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_float(value: object) -> float | None:
    try:
        parsed = float(str(value).replace(",", "").replace("+", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _safe_int(value: object) -> int | None:
    try:
        parsed = int(float(str(value).replace(",", "").replace("+", "").strip()))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


async def _latest_today_fill_for_order(row: sqlite3.Row) -> dict[str, object] | None:
    try:
        summary = await us_account_service.get_today_order_fills(
            symbol=str(row["symbol"]),
            exchange=str(row["exchange"]),
            side="2" if str(row["side"]) == "buy" else "1",
        )
    except US_READONLY_SERVICE_ERRORS:
        return None
    rows = summary.data.get("result_list") or summary.data.get("result_lsit") or []
    if not isinstance(rows, list):
        return None
    order_no = str(row["order_no"] or "").strip()
    matched: list[dict[str, object]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        if order_no and str(item.get("ord_no") or "").strip() != order_no:
            continue
        symbol = str(item.get("stk_code") or item.get("stk_cd") or "").strip().upper()
        if symbol and symbol != str(row["symbol"]).strip().upper():
            continue
        filled_quantity = _safe_int(item.get("cntr_qty"))
        fill_price = _safe_float(item.get("cntr_uv"))
        if filled_quantity and filled_quantity > 0 and fill_price and fill_price > 0:
            matched.append(item)
    if not matched:
        return None

    order_quantity = max(int(row["quantity"] or 0), 1)
    total_quantity = sum(_safe_int(item.get("cntr_qty")) or 0 for item in matched)
    total_value = sum(
        (_safe_int(item.get("cntr_qty")) or 0)
        * (_safe_float(item.get("cntr_uv")) or 0.0)
        for item in matched
    )
    filled_quantity = min(total_quantity, order_quantity)
    if filled_quantity <= 0 or total_value <= 0:
        return None

    aggregate = dict(matched[-1])
    aggregate["cntr_qty"] = str(filled_quantity)
    aggregate["cntr_uv"] = _format_numeric_text(total_value / total_quantity)
    aggregate["ord_stat"] = (
        "체결완료"
        if filled_quantity >= order_quantity
        else _safe_text(aggregate.get("ord_stat") or aggregate.get("ord_stat_nm")) or "부분체결"
    )
    return aggregate


async def _reconcile_submitted_allocation_reservations(
    *,
    session_mode: str,
    safe_account_label: str,
    force: bool = False,
) -> int:
    account_scope = _allocation_account_scope(
        session_mode,
        safe_account_label,
    )
    store = CapitalAllocationStore(get_engine_settings().db_path)
    cycle = store.find_cycle(
        account_scope=account_scope,
        market_date=market_time_context().us_market_date,
    )
    if cycle is None:
        return 0

    submitted = [
        reservation
        for reservation in store.list_reservations(cycle.id)
        if reservation.status == "submitted" and reservation.order_no
    ]
    if not submitted:
        return 0

    reconciled = 0
    for reservation in submitted:
        if (
            not force
            and _seconds_since(reservation.last_reconciled_at)
            < _order_reconcile_interval_seconds()
        ):
            continue
        try:
            summary = await us_account_service.get_today_order_fills(
                symbol=reservation.symbol,
                exchange=reservation.exchange,
                side="2",
            )
        except US_READONLY_SERVICE_ERRORS:
            _record_reconciliation_result(
                store,
                reservation.id,
                "fill_query_error",
            )
            continue
        rows = summary.data.get("result_list") or summary.data.get("result_lsit") or []
        if not isinstance(rows, list):
            _record_reconciliation_result(
                store,
                reservation.id,
                "fill_query_error",
            )
            continue

        filled_quantity = 0
        for item in rows:
            if not isinstance(item, dict):
                continue
            if str(item.get("ord_no") or "").strip() != reservation.order_no:
                continue
            symbol = str(item.get("stk_code") or item.get("stk_cd") or "").strip().upper()
            if symbol and symbol != reservation.symbol.strip().upper():
                continue
            filled_quantity += _safe_int(item.get("cntr_qty")) or 0

        if filled_quantity >= reservation.quantity:
            if _resolve_reconciled_reservation(
                store,
                reservation.id,
                result="filled_confirmed",
                terminal_status="filled",
                filled_quantity=reservation.quantity,
                broker_status="filled_confirmed",
            ):
                reconciled += 1
            continue

        try:
            open_order_summary = await us_account_service.get_open_orders(
                symbol=reservation.symbol,
                side="2",
            )
        except US_READONLY_SERVICE_ERRORS:
            _record_reconciliation_result(
                store,
                reservation.id,
                "open_query_error",
            )
            continue
        open_order_rows = (
            open_order_summary.data.get("result_list")
            or open_order_summary.data.get("result_lsit")
            or []
        )
        if not isinstance(open_order_rows, list):
            _record_reconciliation_result(
                store,
                reservation.id,
                "open_query_error",
            )
            continue
        matching_rows = [
            item
            for item in open_order_rows
            if isinstance(item, dict)
            and reservation.order_no
            in {
                str(item.get("ord_no") or "").strip(),
                str(item.get("orig_ord_no") or "").strip(),
            }
            and (
                not str(item.get("stk_code") or item.get("stk_cd") or "").strip()
                or str(item.get("stk_code") or item.get("stk_cd") or "").strip().upper()
                == reservation.symbol.strip().upper()
            )
        ]
        if not matching_rows:
            _record_reconciliation_result(
                store,
                reservation.id,
                "unresolved",
            )
            continue

        filled_quantity = max(
            filled_quantity,
            max((_safe_int(item.get("cntr_qty")) or 0 for item in matching_rows), default=0),
        )
        canceled_quantity = max(
            (_safe_int(item.get("cncl_qty")) or 0 for item in matching_rows),
            default=0,
        )
        status_text = " ".join(
            str(item.get("ord_stat") or "").strip()
            for item in matching_rows
        )
        reported_remaining_quantities = [
            quantity
            for quantity in (
                _safe_int(item.get("ord_remnq"))
                for item in matching_rows
            )
            if quantity is not None
        ]
        remaining_quantity = max(reservation.quantity - filled_quantity, 0)
        terminal_cancel_status = "취소" in status_text and not any(
            marker in status_text
            for marker in ("전송", "접수", "요청")
        )
        canceled = remaining_quantity > 0 and (
            canceled_quantity >= remaining_quantity
            or (
                terminal_cancel_status
                and reported_remaining_quantities
                and min(reported_remaining_quantities) == 0
            )
        )
        rejected = filled_quantity == 0 and any(
            marker in status_text
            for marker in ("거부", "실패")
        )
        if not canceled and not rejected:
            _record_reconciliation_result(
                store,
                reservation.id,
                "partial_fill" if filled_quantity > 0 else "open_pending",
            )
            continue

        terminal_status = "filled" if filled_quantity > 0 else "released"
        if _resolve_reconciled_reservation(
            store,
            reservation.id,
            result=(
                "rejected_confirmed"
                if rejected
                else "canceled_confirmed"
            ),
            terminal_status=terminal_status,
            filled_quantity=filled_quantity,
            broker_status=status_text,
        ):
            reconciled += 1
    return reconciled


def _submitted_order_state_blocker(
    *,
    session_mode: str,
    safe_account_label: str,
) -> str | None:
    if not session_mode or not safe_account_label:
        return None
    account_scope = _allocation_account_scope(
        session_mode,
        safe_account_label,
    )
    store = CapitalAllocationStore(get_engine_settings().db_path)
    cycle = store.find_cycle(
        account_scope=account_scope,
        market_date=market_time_context().us_market_date,
    )
    if cycle is None:
        return None
    submitted = [
        reservation
        for reservation in store.list_reservations(cycle.id)
        if reservation.status == "submitted" and reservation.order_no
    ]
    if not submitted:
        return None
    oldest_submitted_at = min(
        (
            parsed
            for parsed in (
                _parse_iso_datetime(reservation.submitted_at)
                for reservation in submitted
            )
            if parsed is not None
        ),
        default=None,
    )
    if (
        oldest_submitted_at is not None
        and (_utc_now() - oldest_submitted_at).total_seconds()
        >= _order_reconcile_timeout_seconds()
    ):
        return "ORDER_STATE_CONFIRMATION_TIMEOUT"
    return "ORDER_STATE_PENDING_CONFIRMATION"


def _record_reconciliation_result(
    store: CapitalAllocationStore,
    reservation_id: int,
    result: str,
) -> None:
    try:
        store.record_reconciliation_result(reservation_id, result)
    except (sqlite3.Error, ValueError):
        return


def _resolve_reconciled_reservation(
    store: CapitalAllocationStore,
    reservation_id: int,
    *,
    result: str,
    terminal_status: str,
    filled_quantity: int,
    broker_status: str,
) -> bool:
    try:
        store.resolve_submitted_reconciliation(
            reservation_id,
            result=result,
            terminal_status=terminal_status,
            filled_quantity=filled_quantity,
            broker_status=broker_status,
        )
    except (sqlite3.Error, ValueError):
        return False
    return True


def _seconds_since(value: str | None) -> float:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return float("inf")
    return max((_utc_now() - parsed).total_seconds(), 0.0)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _order_reconcile_interval_seconds() -> float:
    return _bounded_env_float(
        "KIWOOM_US_ORDER_RECONCILE_INTERVAL_SECONDS",
        default=5.0,
        minimum=1.0,
        maximum=60.0,
    )


def _order_reconcile_timeout_seconds() -> float:
    return _bounded_env_float(
        "KIWOOM_US_ORDER_CONFIRMATION_TIMEOUT_SECONDS",
        default=30.0,
        minimum=5.0,
        maximum=600.0,
    )


def _bounded_env_float(
    name: str,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(value, maximum))


async def _latest_today_auto_exit_fill(row: sqlite3.Row) -> dict[str, object] | None:
    order_no = _safe_text(row["auto_exit_order_no"])
    if not order_no:
        return None
    try:
        summary = await us_account_service.get_today_order_fills(
            symbol=str(row["symbol"]),
            exchange=str(row["exchange"]),
            side="1",
        )
    except US_READONLY_SERVICE_ERRORS:
        return None
    rows = summary.data.get("result_list") or summary.data.get("result_lsit") or []
    if not isinstance(rows, list):
        return None

    matched: list[dict[str, object]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        if str(item.get("ord_no") or "").strip() != order_no:
            continue
        symbol = str(item.get("stk_code") or item.get("stk_cd") or "").strip().upper()
        if symbol and symbol != str(row["symbol"]).strip().upper():
            continue
        quantity = _safe_int(item.get("cntr_qty"))
        price = _safe_float(item.get("cntr_uv"))
        if quantity and quantity > 0 and price and price > 0:
            matched.append(item)
    if not matched:
        return None

    expected_quantity = max(int(row["quantity"] or 0), 1)
    total_quantity = sum(_safe_int(item.get("cntr_qty")) or 0 for item in matched)
    aggregate = dict(matched[-1])
    aggregate["cntr_qty"] = str(min(total_quantity, expected_quantity))
    return aggregate


async def _today_net_filled_quantity(symbol: str, exchange: str) -> int:
    summary = await us_account_service.get_today_order_fills(symbol=symbol, exchange=exchange, side="0")
    rows = summary.data.get("result_list") or summary.data.get("result_lsit") or []
    if not isinstance(rows, list):
        return 0
    total = 0
    target_symbol = str(symbol).strip().upper()
    for item in rows:
        if not isinstance(item, dict):
            continue
        row_symbol = str(item.get("stk_code") or item.get("stk_cd") or "").strip().upper()
        if row_symbol and row_symbol != target_symbol:
            continue
        filled_quantity = _safe_int(item.get("cntr_qty")) or 0
        side_code = str(item.get("slby_tp") or "").strip()
        side_name = str(item.get("slby_tp_nm") or "").strip()
        if side_code == "2" or side_name == "매수":
            total += filled_quantity
        elif side_code == "1" or side_name == "매도":
            total -= filled_quantity
    return max(total, 0)


async def _sellable_holding_quantity(symbol: str, exchange: str) -> int:
    holdings = await us_account_service.get_holdings_for_order()
    target_symbol = str(symbol).strip().upper()
    target_exchange = str(exchange).strip().upper()
    best_quantity = 0
    for item in holdings:
        if str(item.symbol).strip().upper() != target_symbol:
            continue
        if str(item.exchange or "").strip().upper() != target_exchange:
            continue
        if item.blockedReasons:
            continue
        best_quantity = max(best_quantity, int(item.sellableQuantity or 0))
    return best_quantity


async def _holding_reference_price(symbol: str, exchange: str) -> float | None:
    try:
        holdings = await us_account_service.get_holdings_for_order()
    except US_READONLY_SERVICE_ERRORS:
        return None
    target_symbol = str(symbol).strip().upper()
    target_exchange = str(exchange).strip().upper()
    for item in holdings:
        if str(item.symbol).strip().upper() != target_symbol:
            continue
        if str(item.exchange or "").strip().upper() != target_exchange:
            continue
        if item.price is not None and item.price > 0:
            return item.price
    return None


async def _latest_quote_price(symbol: str, exchange: str) -> tuple[float | None, str]:
    realtime_summary = realtime_window_store.summary(symbol)
    if (
        realtime_summary.latestPrice is not None
        and realtime_summary_is_fresh(realtime_summary)
    ):
        return realtime_summary.latestPrice, "realtime-window"
    try:
        response = await us_account_service._execute(
            "usa10100",
            {
                "stex_tp": exchange if exchange in {"NA", "ND", "NY"} else "ND",
                "stk_cd": symbol,
            },
        )
    except US_READONLY_SERVICE_ERRORS:
        holding_price = await _holding_reference_price(symbol, exchange)
        if holding_price is not None:
            return holding_price, "ust21070"
        return None, "usa10100"
    data = response.data
    price = (
        _safe_float(data.get("cur_prc"))
        or _safe_float(data.get("curr_pric"))
        or _safe_float(data.get("last_prc"))
        or _safe_float(data.get("close_pric"))
    )
    if price is not None:
        _record_rest_poll_tick(symbol, price, data)
        return price, "usa10100"
    holding_price = await _holding_reference_price(symbol, exchange)
    if holding_price is not None:
        return holding_price, "ust21070"
    return None, "usa10100"


def _record_rest_poll_tick(symbol: str, price: float, data: dict[str, object]) -> None:
    event_time = now_iso()
    realtime_window_store.record({
        "type": "TICK",
        "symbol": symbol,
        "name": str(data.get("stk_nm") or data.get("stk_enm") or symbol),
        "price": price,
        "changeRate": _safe_float(data.get("flu_rt") or data.get("diff_rate_for_gjga")),
        "volume": _safe_int(data.get("acc_trde_qty") or data.get("trde_qty")),
        "tradeStrength": _safe_float(data.get("cntr_str") or data.get("tradeStrength")),
        "provider": "kiwoom-rest-poll",
        "timestamp": event_time,
        "receivedAt": event_time,
    })


def _official_name_indicates_non_common_stock(*values: str | None) -> bool:
    text = " ".join(value for value in values if value).upper()
    blocked_terms = (
        "워런트",
        "WARRANT",
        "WARRANTS",
        " C/W",
        " C/WTS",
        "RIGHT",
        "RIGHTS",
        "ETF",
        "ETN",
        "인버스",
        "레버리지",
    )
    return any(term in text for term in blocked_terms)


def _connect_order_db() -> sqlite3.Connection:
    path = Path(get_engine_settings().db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS us_order_attempts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tr_id TEXT NOT NULL,
          side TEXT NOT NULL,
          symbol TEXT NOT NULL,
          exchange TEXT NOT NULL,
          quantity INTEGER NOT NULL,
          order_price TEXT NOT NULL,
          reference_price TEXT NOT NULL DEFAULT '',
          trade_type TEXT NOT NULL,
          strategy TEXT,
          reason TEXT,
          return_code TEXT NOT NULL,
          return_msg TEXT NOT NULL,
          order_no TEXT,
          auto_exit_armed INTEGER NOT NULL DEFAULT 0,
          auto_exit_completed INTEGER NOT NULL DEFAULT 0,
          auto_exit_reason TEXT,
          auto_exit_order_no TEXT,
          allocation_reservation_id INTEGER,
          created_at TEXT NOT NULL
        )
        """
    )
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(us_order_attempts)").fetchall()}
    if "reference_price" not in columns:
        connection.execute("ALTER TABLE us_order_attempts ADD COLUMN reference_price TEXT NOT NULL DEFAULT ''")
    if "auto_exit_armed" not in columns:
        connection.execute("ALTER TABLE us_order_attempts ADD COLUMN auto_exit_armed INTEGER NOT NULL DEFAULT 0")
    if "auto_exit_completed" not in columns:
        connection.execute("ALTER TABLE us_order_attempts ADD COLUMN auto_exit_completed INTEGER NOT NULL DEFAULT 0")
    if "auto_exit_reason" not in columns:
        connection.execute("ALTER TABLE us_order_attempts ADD COLUMN auto_exit_reason TEXT")
    if "auto_exit_order_no" not in columns:
        connection.execute("ALTER TABLE us_order_attempts ADD COLUMN auto_exit_order_no TEXT")
    if "strategy" not in columns:
        connection.execute("ALTER TABLE us_order_attempts ADD COLUMN strategy TEXT")
    if "reason" not in columns:
        connection.execute("ALTER TABLE us_order_attempts ADD COLUMN reason TEXT")
    if "allocation_reservation_id" not in columns:
        connection.execute(
            """
            ALTER TABLE us_order_attempts
            ADD COLUMN allocation_reservation_id INTEGER
            """
        )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS us_auto_trade_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          action TEXT NOT NULL,
          status TEXT NOT NULL,
          strategy TEXT,
          symbol TEXT,
          exchange TEXT,
          side TEXT,
          tr_id TEXT,
          source_order_id INTEGER,
          blocked_reasons TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL
        )
        """
    )
    event_columns = {row["name"] for row in connection.execute("PRAGMA table_info(us_auto_trade_events)").fetchall()}
    if "strategy" not in event_columns:
        connection.execute("ALTER TABLE us_auto_trade_events ADD COLUMN strategy TEXT")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS us_strategy_pnl_snapshots (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          strategy TEXT NOT NULL,
          symbol TEXT NOT NULL,
          trade_date TEXT NOT NULL,
          actual_pnl REAL NOT NULL,
          fill_count INTEGER NOT NULL,
          realized_quantity INTEGER NOT NULL,
          buy_quantity INTEGER NOT NULL,
          sell_quantity INTEGER NOT NULL,
          source TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(strategy, symbol, trade_date)
        )
        """
    )
    connection.commit()
    return connection


def _record_auto_trade_event(
    *,
    action: str,
    status: str,
    strategy: str | None = None,
    symbol: str | None = None,
    exchange: str | None = None,
    side: str | None = None,
    tr_id: str | None = None,
    source_order_id: int | None = None,
    blocked_reasons: list[str] | None = None,
) -> None:
    safe_reasons = _dedupe_reasons(blocked_reasons or [])
    connection = _connect_order_db()
    try:
        connection.execute(
            """
            INSERT INTO us_auto_trade_events(
              action, status, strategy, symbol, exchange, side, tr_id, source_order_id, blocked_reasons, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action,
                status,
                _safe_reason(strategy) if strategy else None,
                symbol,
                exchange,
                side,
                tr_id,
                source_order_id,
                ",".join(safe_reasons),
                now_iso(),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _event_row_to_item(row: sqlite3.Row) -> UsAutoTradeEventItem:
    reasons = [part for part in str(row["blocked_reasons"] or "").split(",") if part]
    action = str(row["action"])
    status = str(row["status"])
    tr_id = row["tr_id"]
    legacy_wait_reasons = {"ENTRY_CONDITIONS_NOT_READY", "BUY_TICKET_UNAVAILABLE", "AUTO_TRADE_PLAN_EMPTY"}
    if (
        action == "auto_entry"
        and status == "blocked"
        and not row["symbol"]
        and row["source_order_id"] is None
        and reasons
        and set(reasons).issubset(legacy_wait_reasons)
    ):
        action = "auto_entry_tick"
        status = "skipped"
        tr_id = None
    return UsAutoTradeEventItem(
        id=int(row["id"]),
        action=action,
        status=status,
        strategy=str(row["strategy"]) if "strategy" in row.keys() and row["strategy"] else None,
        symbol=row["symbol"],
        exchange=row["exchange"],
        side=row["side"],
        trId=tr_id,
        sourceOrderId=row["source_order_id"],
        blockedReasons=reasons,
        createdAt=str(row["created_at"]),
    )


def _strategy_pnl_from_fills(fill_data: dict[str, object]) -> list[UsStrategyPnlSnapshot]:
    fills = _order_fill_rows(fill_data)
    order_lookup = _order_lookup_for_strategy()
    buckets: dict[tuple[str, str], dict[str, float | int]] = {}
    for fill in fills:
        symbol = str(fill.get("symbol") or "").strip().upper()
        side = fill.get("side")
        quantity = int(fill.get("quantity") or 0)
        price = float(fill.get("price") or 0)
        if not symbol or side not in {"buy", "sell"} or quantity <= 0 or price <= 0:
            continue
        order = _match_order_for_fill(fill, order_lookup)
        strategy = _strategy_for_order_row(order)
        key = (strategy, symbol)
        bucket = buckets.setdefault(key, {
            "buy_qty": 0,
            "buy_value": 0.0,
            "sell_qty": 0,
            "sell_value": 0.0,
            "fill_count": 0,
        })
        if side == "buy":
            bucket["buy_qty"] = int(bucket["buy_qty"]) + quantity
            bucket["buy_value"] = float(bucket["buy_value"]) + quantity * price
        else:
            bucket["sell_qty"] = int(bucket["sell_qty"]) + quantity
            bucket["sell_value"] = float(bucket["sell_value"]) + quantity * price
        bucket["fill_count"] = int(bucket["fill_count"]) + 1

    trade_date = now_iso()[:10]
    updated_at = now_iso()
    snapshots: list[UsStrategyPnlSnapshot] = []
    for (strategy, symbol), bucket in buckets.items():
        buy_qty = int(bucket["buy_qty"])
        sell_qty = int(bucket["sell_qty"])
        realized_quantity = min(buy_qty, sell_qty)
        avg_buy = float(bucket["buy_value"]) / buy_qty if buy_qty else 0.0
        avg_sell = float(bucket["sell_value"]) / sell_qty if sell_qty else 0.0
        actual_pnl = round((avg_sell - avg_buy) * realized_quantity, 4) if realized_quantity else 0.0
        snapshots.append(UsStrategyPnlSnapshot(
            strategy=strategy,
            symbol=symbol,
            tradeDate=trade_date,
            actualPnl=actual_pnl,
            fillCount=int(bucket["fill_count"]),
            realizedQuantity=realized_quantity,
            buyQuantity=buy_qty,
            sellQuantity=sell_qty,
            source="ust21510-order-fill-match",
            updatedAt=updated_at,
        ))
    return snapshots


def _order_fill_rows(fill_data: dict[str, object]) -> list[dict[str, object]]:
    raw_rows = fill_data.get("result_list") or fill_data.get("result_lsit") or []
    if not isinstance(raw_rows, list):
        return []
    rows: list[dict[str, object]] = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        side = _fill_side(item)
        rows.append({
            "order_no": _safe_text(item.get("ord_no") or item.get("odno") or item.get("order_no")),
            "symbol": _safe_text(item.get("stk_code") or item.get("stk_cd") or item.get("symbol") or item.get("code")),
            "side": side,
            "quantity": _safe_int(item.get("cntr_qty") or item.get("exec_qty") or item.get("filled_qty") or item.get("ord_qty")) or 0,
            "price": _safe_float(item.get("cntr_uv") or item.get("exec_price") or item.get("filled_price") or item.get("ord_uv")) or 0.0,
        })
    return rows


def _fill_side(row: dict[str, object]) -> str | None:
    code = str(row.get("slby_tp") or row.get("side") or "").strip()
    label = str(row.get("slby_tp_nm") or row.get("frgn_trde_nm") or row.get("sideName") or "").strip().lower()
    if code == "2" or "매수" in label or "buy" in label:
        return "buy"
    if code == "1" or "매도" in label or "sell" in label:
        return "sell"
    return None


def _order_lookup_for_strategy() -> dict[str, dict[str, sqlite3.Row | list[sqlite3.Row]]]:
    connection = _connect_order_db()
    try:
        rows = connection.execute(
            """
            SELECT *
            FROM us_order_attempts
            WHERE return_code = '0'
            ORDER BY id DESC
            LIMIT 500
            """
        ).fetchall()
    finally:
        connection.close()
    by_order_no: dict[str, sqlite3.Row] = {}
    by_symbol_side: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        order_no = str(row["order_no"] or "").strip()
        if order_no:
            by_order_no[order_no] = row
        key = f"{str(row['symbol']).strip().upper()}::{str(row['side']).strip()}"
        by_symbol_side.setdefault(key, []).append(row)
    return {"by_order_no": by_order_no, "by_symbol_side": by_symbol_side}


def _match_order_for_fill(fill: dict[str, object], lookup: dict[str, dict[str, sqlite3.Row | list[sqlite3.Row]]]) -> sqlite3.Row | None:
    order_no = str(fill.get("order_no") or "").strip()
    by_order_no = lookup["by_order_no"]
    if order_no and order_no in by_order_no:
        value = by_order_no[order_no]
        return value if isinstance(value, sqlite3.Row) else None
    symbol = str(fill.get("symbol") or "").strip().upper()
    side = str(fill.get("side") or "").strip()
    candidates = lookup["by_symbol_side"].get(f"{symbol}::{side}")
    if isinstance(candidates, list) and candidates:
        return candidates[0]
    return None


def _strategy_for_order_row(row: sqlite3.Row | None) -> str:
    if row is None:
        return "unmatched-fill"
    strategy = str(row["strategy"] or "").strip() if "strategy" in row.keys() else ""
    if strategy:
        return strategy[:120]
    reason = str(row["reason"] or "").strip() if "reason" in row.keys() else ""
    return _strategy_from_reason(reason) or "manual-mvp"


def _persist_strategy_pnl(rows: list[UsStrategyPnlSnapshot]) -> None:
    if not rows:
        return
    connection = _connect_order_db()
    try:
        connection.executemany(
            """
            INSERT INTO us_strategy_pnl_snapshots(
              strategy, symbol, trade_date, actual_pnl, fill_count, realized_quantity,
              buy_quantity, sell_quantity, source, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(strategy, symbol, trade_date) DO UPDATE SET
              actual_pnl=excluded.actual_pnl,
              fill_count=excluded.fill_count,
              realized_quantity=excluded.realized_quantity,
              buy_quantity=excluded.buy_quantity,
              sell_quantity=excluded.sell_quantity,
              source=excluded.source,
              updated_at=excluded.updated_at
            """,
            [
                (
                    row.strategy,
                    row.symbol,
                    row.tradeDate,
                    row.actualPnl,
                    row.fillCount,
                    row.realizedQuantity,
                    row.buyQuantity,
                    row.sellQuantity,
                    row.source,
                    row.updatedAt,
                )
                for row in rows
            ],
        )
        connection.commit()
    finally:
        connection.close()


def _list_strategy_pnl_snapshots(limit: int = 100) -> list[UsStrategyPnlSnapshot]:
    connection = _connect_order_db()
    try:
        rows = connection.execute(
            """
            SELECT *
            FROM us_strategy_pnl_snapshots
            ORDER BY trade_date DESC, updated_at DESC, id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        ).fetchall()
    finally:
        connection.close()
    return [
        UsStrategyPnlSnapshot(
            strategy=str(row["strategy"]),
            symbol=str(row["symbol"]),
            tradeDate=str(row["trade_date"]),
            actualPnl=float(row["actual_pnl"]),
            fillCount=int(row["fill_count"]),
            realizedQuantity=int(row["realized_quantity"]),
            buyQuantity=int(row["buy_quantity"]),
            sellQuantity=int(row["sell_quantity"]),
            source=str(row["source"]),
            updatedAt=str(row["updated_at"]),
        )
        for row in rows
    ]


def _record_order_attempt(payload: UsOrderRequest, result: UsOrderResponse) -> None:
    connection = _connect_order_db()
    try:
        connection.execute(
            """
            INSERT INTO us_order_attempts(
              tr_id, side, symbol, exchange, quantity, order_price, reference_price, trade_type,
              strategy, reason, return_code, return_msg, order_no, auto_exit_armed, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.trId,
                payload.side,
                payload.symbol,
                payload.exchange,
                payload.quantity,
                payload.orderPrice,
                payload.referencePrice,
                payload.tradeType,
                _strategy_from_reason(payload.reason),
                _safe_reason(payload.reason),
                result.returnCode,
                result.returnMessage,
                result.orderNo,
                1 if _should_arm_auto_exit(payload, result) else 0,
                result.updatedAt,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _link_order_attempt_allocation(
    *,
    order_no: str | None,
    symbol: str,
    exchange: str,
    reservation_id: int,
) -> bool:
    clean_order_no = _safe_text(order_no)
    if not clean_order_no:
        return False
    connection = _connect_order_db()
    try:
        cursor = connection.execute(
            """
            UPDATE us_order_attempts
            SET allocation_reservation_id = ?
            WHERE id = (
              SELECT id
              FROM us_order_attempts
              WHERE side = 'buy'
                AND return_code = '0'
                AND order_no = ?
                AND UPPER(symbol) = UPPER(?)
                AND UPPER(exchange) = UPPER(?)
              ORDER BY id DESC
              LIMIT 1
            )
            """,
            (
                reservation_id,
                clean_order_no,
                str(symbol).strip(),
                str(exchange).strip(),
            ),
        )
        connection.commit()
        return cursor.rowcount == 1
    finally:
        connection.close()


def _close_auto_exit_allocation(row: sqlite3.Row) -> bool:
    store = CapitalAllocationStore(get_engine_settings().db_path)
    reservation_id = (
        _safe_int(row["allocation_reservation_id"])
        if "allocation_reservation_id" in row.keys()
        else None
    )
    try:
        if reservation_id is not None and reservation_id > 0:
            return store.close_filled(reservation_id)

        order_no = _safe_text(row["order_no"])
        if not order_no:
            return True
        reservation = store.find_by_order_no(
            order_no=order_no,
            symbol=str(row["symbol"]),
            exchange=str(row["exchange"]),
        )
        if reservation is None:
            return True
        return store.close_filled(reservation.id)
    except (OSError, sqlite3.Error, ValueError):
        return False


def _safe_reason(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).strip().split())
    return cleaned[:200] or None


def _strategy_from_reason(value: str | None) -> str | None:
    reason = _safe_reason(value)
    if not reason:
        return None
    prefixes = ("auto_entry_", "auto_exit_")
    for prefix in prefixes:
        if reason.startswith(prefix):
            return reason[len(prefix):][:120] or None
    if reason == "end_of_day_liquidation_switch":
        return "end-of-day-liquidation"
    if reason.startswith("MVP"):
        return "manual-mvp"
    return reason[:120]


def _auto_exit_profile_for_order(row: sqlite3.Row) -> dict[str, float]:
    return {"targetProfitPct": 2.0, "stopLossPct": 2.0}


def _should_arm_auto_exit(payload: UsOrderRequest, result: UsOrderResponse) -> bool:
    return (
        payload.side == "buy"
        and result.returnCode == "0"
        and (payload.confirmText == US_ORDER_CONFIRM or _auto_trade_runtime_enabled)
        and _env_bool("KIWOOM_US_AUTO_EXIT_ENABLED", False)
    )


def _latest_armed_buy_row() -> sqlite3.Row | None:
    connection = _connect_order_db()
    try:
        return connection.execute(
            """
            SELECT *
            FROM us_order_attempts
            WHERE side = 'buy'
              AND return_code = '0'
              AND auto_exit_armed = 1
              AND auto_exit_completed = 0
              AND COALESCE(reference_price, '') != ''
            ORDER BY id DESC
            LIMIT 1
            """,
        ).fetchone()
    finally:
        connection.close()


def _armed_buy_rows() -> list[sqlite3.Row]:
    connection = _connect_order_db()
    try:
        return connection.execute(
            """
            SELECT *
            FROM us_order_attempts
            WHERE side = 'buy'
              AND return_code = '0'
              AND auto_exit_armed = 1
              AND auto_exit_completed = 0
              AND COALESCE(reference_price, '') != ''
            ORDER BY id DESC
            """,
        ).fetchall()
    finally:
        connection.close()


def _latest_successful_buy_row() -> sqlite3.Row | None:
    return _successful_buy_row()


def _successful_buy_row(source_order_id: int | None = None) -> sqlite3.Row | None:
    connection = _connect_order_db()
    try:
        if source_order_id is not None:
            return connection.execute(
                """
                SELECT *
                FROM us_order_attempts
                WHERE id = ?
                  AND side = 'buy'
                  AND return_code = '0'
                  AND COALESCE(reference_price, '') != ''
                LIMIT 1
                """,
                (source_order_id,),
            ).fetchone()
        return connection.execute(
            """
            SELECT *
            FROM us_order_attempts
            WHERE side = 'buy'
              AND return_code = '0'
              AND COALESCE(reference_price, '') != ''
            ORDER BY id DESC
            LIMIT 1
            """,
        ).fetchone()
    finally:
        connection.close()


async def _reconcile_stale_armed_buy_rows(*, grace_seconds: int = 600) -> int:
    if get_settings().kiwoom_mode != "live":
        return 0
    rows = _armed_buy_rows()
    if not rows or not any(_armed_row_is_stale(row, grace_seconds) for row in rows):
        return 0
    try:
        holdings = await us_account_service.get_holdings_for_order()
    except US_READONLY_SERVICE_ERRORS:
        return 0

    remaining_by_symbol: dict[str, int] = {}
    for item in holdings:
        symbol = str(item.symbol).strip().upper()
        if symbol:
            remaining_by_symbol[symbol] = remaining_by_symbol.get(symbol, 0) + max(int(item.sellableQuantity or 0), 0)

    reconciled = 0
    for row in rows:
        symbol = str(row["symbol"]).strip().upper()
        quantity = max(int(row["quantity"] or 0), 1)
        available = remaining_by_symbol.get(symbol, 0)
        if available >= quantity:
            remaining_by_symbol[symbol] = available - quantity
            continue
        if not _armed_row_is_stale(row, grace_seconds):
            continue

        reason = "holding_not_found_reconciled" if available <= 0 else "holding_quantity_reconciled"
        blocked_reason = "HOLDING_NOT_FOUND" if available <= 0 else "HOLDING_QUANTITY_MISMATCH"
        _mark_auto_exit_completed(int(row["id"]), reason, None)
        _record_auto_trade_event(
            action="auto_exit",
            status="reconciled",
            symbol=symbol,
            exchange=str(row["exchange"]),
            side="sell",
            source_order_id=int(row["id"]),
            blocked_reasons=[blocked_reason],
        )
        reconciled += 1
    return reconciled


def _armed_row_is_stale(row: sqlite3.Row, grace_seconds: int) -> bool:
    try:
        created_at = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)).total_seconds()
    return age_seconds >= grace_seconds


def _mark_auto_exit_armed(source_order_id: int) -> None:
    connection = _connect_order_db()
    try:
        connection.execute(
            """
            UPDATE us_order_attempts
            SET auto_exit_armed = 1,
                auto_exit_completed = 0,
                auto_exit_reason = NULL,
                auto_exit_order_no = NULL
            WHERE id = ?
            """,
            (source_order_id,),
        )
        connection.commit()
    finally:
        connection.close()


def _mark_auto_exit_completed(source_order_id: int, reason: str | None, order_no: str | None) -> None:
    connection = _connect_order_db()
    try:
        connection.execute(
            """
            UPDATE us_order_attempts
            SET auto_exit_completed = 1,
                auto_exit_reason = ?,
                auto_exit_order_no = ?
            WHERE id = ?
            """,
            (reason, order_no, source_order_id),
        )
        connection.commit()
    finally:
        connection.close()


def _mark_auto_exit_submitted(source_order_id: int, reason: str | None, order_no: str | None) -> None:
    connection = _connect_order_db()
    try:
        connection.execute(
            """
            UPDATE us_order_attempts
            SET auto_exit_armed = 1,
                auto_exit_completed = 0,
                auto_exit_reason = ?,
                auto_exit_order_no = ?
            WHERE id = ?
            """,
            (reason, order_no, source_order_id),
        )
        connection.commit()
    finally:
        connection.close()
