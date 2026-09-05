from __future__ import annotations

import asyncio
import os
import time

from typing import Any

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.schemas.market import (
    MarketRankItem,
    MarketRankingResponse,
    UsChartCandle,
    UsChartResponse,
    UsAutoTradeCriterion,
    UsAutoTradeOrderTicket,
    UsAutoTradePlanListResponse,
    UsAutoTradeProcessStep,
    UsAutoTradePlanResponse,
    UsConditionSearchMatch,
    UsConditionSearchResponse,
)
from app.core.time import now_iso
from app.services.realtime_quote_service import RealtimeWindowSummary, kiwoom_quote_monitor, realtime_window_store
from app.services.kiwoom_session import get_active_or_latest_kiwoom_session
from app.services.us_condition_service import us_condition_service
from app.services.us_account_service import US_READONLY_SERVICE_ERRORS, us_account_service
from app.services.us_order_service import us_order_service
from app.services.kiwoom_condition_strategy_service import kiwoom_condition_strategy_service
from trading_engine.providers.kiwoom_us.schemas import UsReadOnlyTrResponse


class MarketRankingError(RuntimeError):
    pass


US_RANKING_CONFIG: dict[str, tuple[str, str, str]] = {
    "realtime": ("usa01980", "미국주식 실시간 종목 조회 순위", "실시간 관심 순위"),
    "change-rate": ("usa20910", "미국주식 전일대비 등락률 상위", "전일대비 상승률"),
    "volume": ("usa20530", "미국주식 당일 거래량 상위", "거래량 상위"),
    "price-spike": ("usa20930", "미국주식 가격 급등락", "가격 급등락"),
}

US_CHART_CONFIG: dict[str, tuple[str, str]] = {
    "minute": ("usa06011", "미국주식 분 차트"),
    "day": ("usa06012", "미국주식 일 차트"),
    "week": ("usa06013", "미국주식 주 차트"),
    "month": ("usa06014", "미국주식 월 차트"),
}

US_PREMARKET_VOLUME_THRESHOLD = 100_000
US_PREMARKET_MAX_SPREAD_PCT = 0.15
US_PREMARKET_MAX_QUOTE_AGE_SECONDS = 10
US_PULLBACK_VOLUME_THRESHOLD = 300_000
US_PULLBACK_DEFAULT_MIN_PASSED_CRITERIA = 4
US_AI_RECOMMENDED_CRITICAL_CRITERIA = {
    "ai_price_range",
    "ai_change_range",
    "ai_volume_1m",
    "ai_trade_value_20m",
    "ai_close_above_vwap",
    "ai_ema_stack",
    "ai_spread",
}

EMPTY_KIWOOM_CONDITION_STRATEGY: dict[str, object] = {
    "strategy": "kiwoom-condition-unconfigured",
    "name": "키움 조건검색식",
    "condition_seq": "",
    "condition_name": "",
    "tick_scope": "0",
    "bearish_count": 0,
    "entry_rule": "condition_direct",
    "target_profit_pct": 2.0,
    "stop_loss_pct": 2.0,
    "required_criteria": ("strategy_session", "condition_search_match", "quote_price"),
    "condition_direct_entry": True,
}


def _all_pullback_strategies(conditions) -> tuple[dict[str, object], ...]:
    return kiwoom_condition_strategy_service.runtime_configs(conditions)


class MarketRankingService:
    def __init__(self) -> None:
        self._pullback_plan_cache: UsAutoTradePlanListResponse | None = None
        self._pullback_plan_cached_at = 0.0
        self._pullback_plan_lock = asyncio.Lock()

    def clear_pullback_plan_cache(self) -> None:
        self._pullback_plan_cache = None
        self._pullback_plan_cached_at = 0.0

    async def get_us_ranking(self, ranking_type: str) -> MarketRankingResponse:
        try:
            tr_id, title, reason = US_RANKING_CONFIG[ranking_type]
        except KeyError as exc:
            raise MarketRankingError("Unsupported US ranking type") from exc

        try:
            response = await self._execute_us_ranking(tr_id)
        except US_READONLY_SERVICE_ERRORS as exc:
            raise MarketRankingError(str(exc)) from exc

        rows = response.data.get("result_list") or []
        if not isinstance(rows, list):
            rows = []
        items = [
            _map_us_item(row, index, reason)
            for index, row in enumerate(rows, start=1)
            if isinstance(row, dict)
        ]
        items = _sort_us_ranking_items(tr_id, items)
        return MarketRankingResponse(
            trId=tr_id,
            title=title,
            market="US",
            source=f"kiwoom-us-{tr_id}",
            updatedAt=now_iso(),
            items=items,
        )

    async def _execute_us_ranking(self, tr_id: str) -> UsReadOnlyTrResponse:
        return await us_account_service._execute(tr_id, _us_ranking_payload(tr_id))

    async def get_us_chart(
        self,
        *,
        timeframe: str,
        symbol: str,
        exchange: str = "ND",
        start_date: str | None = None,
        tick_scope: str = "1",
        all_pages: bool = False,
        continuation_pages: int = 20,
        continuation_delay_seconds: float = 0.0,
        require_complete: bool = True,
    ) -> UsChartResponse:
        try:
            tr_id, _ = US_CHART_CONFIG[timeframe]
        except KeyError as exc:
            raise MarketRankingError("Unsupported US chart timeframe") from exc

        clean_symbol = _safe_symbol(symbol)
        clean_exchange = exchange if exchange in {"NA", "ND", "NY"} else "ND"
        clean_start = _safe_yyyymmdd(start_date) if start_date else _default_chart_start(timeframe)
        payload: dict[str, object] = {
            "stex_tp": clean_exchange,
            "stk_cd": clean_symbol,
            "strt_dt": clean_start,
            "upd_stkpc_tp": "0" if timeframe == "minute" else "1",
            "exrt_appl_tp": "1" if timeframe == "minute" else "0",
        }
        if timeframe == "minute":
            payload["tic_scope"] = tick_scope

        response = await (
            us_account_service._execute_all(
                tr_id,
                payload,
                max_pages=continuation_pages,
                page_delay_seconds=continuation_delay_seconds,
                require_complete=require_complete,
            )
            if all_pages
            else us_account_service._execute(tr_id, payload)
        )
        rows = response.data.get("result_list") or []
        if not isinstance(rows, list):
            rows = []
        candles = _normalize_us_chart_candles(rows)
        return UsChartResponse(
            trId=tr_id,
            code=clean_symbol,
            exchange=clean_exchange,
            timeframe=timeframe,
            source=f"kiwoom-us-{tr_id}",
            updatedAt=now_iso(),
            candles=candles,
            continuationComplete=str(getattr(response, "cont_yn", "N")).strip().upper() != "Y",
            continuationPages=int(getattr(response, "page_count", 1) or 1),
        )

    async def get_us_order_candidates(self, *, max_notional: float = 500.0, limit: int = 8) -> MarketRankingResponse:
        max_items = max(1, min(limit, 20))
        max_price = max(0.01, max_notional)
        merged: dict[str, MarketRankItem] = {}
        sources: list[str] = []
        total_seen = 0
        valid_price_count = 0
        affordable_count = 0
        non_common_excluded_count = 0

        for ranking_type in ("realtime", "change-rate", "price-spike", "volume"):
            try:
                ranking = await self.get_us_ranking(ranking_type)
            except MarketRankingError:
                continue
            sources.append(ranking.trId)
            for item in ranking.items:
                total_seen += 1
                if not item.code or item.price <= 0:
                    continue
                valid_price_count += 1
                if _official_ranking_name_indicates_non_common_stock(item.name):
                    non_common_excluded_count += 1
                    continue
                if item.code not in merged:
                    is_affordable = item.price <= max_price
                    if is_affordable:
                        affordable_count += 1
                    volume_tag = "프리마켓 거래량 10만+" if (item.volume or 0) >= US_PREMARKET_VOLUME_THRESHOLD else "거래량 관찰"
                    merged[item.code] = MarketRankItem(
                        rank=len(merged) + 1,
                        code=item.code,
                        name=item.name,
                        price=item.price,
                        changeRate=item.changeRate,
                        volume=item.volume,
                        tradingValue=item.tradingValue,
                        exchange=item.exchange,
                        reason=f"{'1주 후보' if is_affordable else '한도초과 관찰'} · {volume_tag} · {ranking.trId} · {item.reason}",
                    )
                if len(merged) >= max_items:
                    break
                if len(merged) >= max_items:
                    break

        notes = [
            f"maxNotional={max_price:.2f}",
            f"sources={','.join(sources) if sources else 'none'}",
            f"seen={total_seen}",
            f"validPrice={valid_price_count}",
            f"affordable={affordable_count}",
            f"nonCommonExcluded={non_common_excluded_count}",
            f"premarketVolumeThreshold={US_PREMARKET_VOLUME_THRESHOLD}",
            f"volume100k={sum(1 for item in merged.values() if (item.volume or 0) >= US_PREMARKET_VOLUME_THRESHOLD)}",
        ]
        if not sources:
            notes.append("ranking source unavailable")
        elif total_seen == 0:
            notes.append("ranking source returned no rows")
        elif valid_price_count == 0:
            notes.append("ranking rows had no usable price")
        elif affordable_count == 0:
            notes.append("no ranking item was within current notional limit")

        items = sorted(
            merged.values(),
            key=lambda row: (
                row.price <= max_price,
                (row.volume or 0) >= US_PREMARKET_VOLUME_THRESHOLD,
                row.changeRate,
                row.volume or 0,
                -row.price,
            ),
            reverse=True,
        )
        return MarketRankingResponse(
            trId="+".join(sources) if sources else "us-order-candidates",
            title="미국주식 1주 테스트 후보",
            market="US",
            source="kiwoom-us-order-candidate-mvp",
            updatedAt=now_iso(),
            items=[item.model_copy(update={"rank": index}) for index, item in enumerate(items[:max_items], start=1)],
            notes=notes,
        )

    async def get_us_pullback_auto_trade_plans(self) -> UsAutoTradePlanListResponse:
        if self._pullback_plan_cache_is_current():
            return self._pullback_plan_cache.model_copy(deep=True)

        async with self._pullback_plan_lock:
            if self._pullback_plan_cache_is_current():
                return self._pullback_plan_cache.model_copy(deep=True)
            response = await self._load_us_pullback_auto_trade_plans()
            self._pullback_plan_cache = response
            self._pullback_plan_cached_at = time.monotonic()
            return response.model_copy(deep=True)

    def _pullback_plan_cache_is_current(self) -> bool:
        return (
            self._pullback_plan_cache is not None
            and time.monotonic() - self._pullback_plan_cached_at < 2.0
        )

    async def _load_us_pullback_auto_trade_plans(self) -> UsAutoTradePlanListResponse:
        try:
            catalog = await us_condition_service.get_condition_list()
            conditions = catalog.conditions
            kiwoom_condition_strategy_service.sync(conditions)
        except Exception:
            conditions = kiwoom_condition_strategy_service.stored_conditions()
        configs = _all_pullback_strategies(conditions)
        if any(not bool(config.get("condition_direct_entry")) for config in configs):
            ranking = await self._get_pullback_candidate_ranking()
        else:
            ranking = MarketRankingResponse(
                trId="",
                title="키움 조건검색 직접 진입",
                market="US",
                source="kiwoom-us-condition-only",
                updatedAt=now_iso(),
                items=[],
                notes=["programRankingDisabled=true"],
            )
        default_condition_seq = None
        condition_sequences = {
            str(config.get("condition_seq") or "").strip() or default_condition_seq
            for config in configs
            if us_order_service.is_strategy_enabled(str(config["strategy"]))
        }
        condition_responses: dict[str | None, UsConditionSearchResponse | BaseException] = {}
        condition_results = await asyncio.gather(
            *(us_condition_service.get_condition_search(seq) for seq in condition_sequences),
            return_exceptions=True,
        )
        for seq, result in zip(condition_sequences, condition_results):
            condition_responses[seq] = result

        realtime_exchanges: dict[str, str] = {
            item.code: item.exchange
            for item in ranking.items[:10]
            if item.code and item.exchange in {"ND", "NY", "NA"}
        }
        all_condition_codes: set[str] = set()
        for result in condition_responses.values():
            if isinstance(result, BaseException):
                continue
            all_condition_codes.update(item.code for item in result.matches if item.code)
            realtime_exchanges.update({
                item.code: item.exchange
                for item in result.matches
                if item.code and item.exchange in {"ND", "NY", "NA"}
            })

        realtime_symbols = [item.code for item in ranking.items[:10] if item.code]
        realtime_symbols.extend(sorted(all_condition_codes))
        session = get_active_or_latest_kiwoom_session()
        if session is not None and realtime_symbols:
            await kiwoom_quote_monitor.ensure_union(
                session,
                realtime_symbols,
                realtime_exchanges,
                prefer_existing=True,
            )
        candidate_plans: list[UsAutoTradePlanResponse] = []
        plans: list[UsAutoTradePlanResponse] = []
        for config in configs:
            condition_seq = str(config.get("condition_seq") or "").strip() or default_condition_seq
            condition_result = condition_responses.get(condition_seq)
            condition_codes: set[str] | None = None
            condition_matches: list[UsConditionSearchMatch] | None = None
            condition_name = str(config.get("condition_name") or "").strip() or None
            if condition_result is not None and not isinstance(condition_result, BaseException):
                if condition_result.selectedSeq is not None:
                    condition_seq = condition_result.selectedSeq
                    condition_matches = list(condition_result.matches)
                    condition_codes = {item.code for item in condition_result.matches if item.code}
                    condition_name = condition_result.selectedName or condition_name or condition_result.selectedSeq
            evaluation_config = {
                **config,
                "condition_seq": condition_seq or "",
                "condition_name": condition_name or "",
            }
            strategy_candidates = await self._build_pullback_strategy_candidates(
                ranking,
                evaluation_config,
                condition_codes=condition_codes,
                condition_matches=condition_matches,
                condition_name=condition_name,
            )
            candidate_plans.extend(strategy_candidates)
            selected_for_strategy = _select_pullback_plan(strategy_candidates)
            if selected_for_strategy is not None:
                plans.append(selected_for_strategy)
            elif strategy_candidates:
                plans.append(strategy_candidates[0])
        selected = _select_pullback_plan(plans)
        return UsAutoTradePlanListResponse(
            source="kiwoom-us-auto-trade-plan-mvp",
            updatedAt=now_iso(),
            selectedStrategy=selected.strategy if selected else None,
            plans=plans,
            candidatePlans=candidate_plans,
        )

    async def _get_pullback_candidate_ranking(self) -> MarketRankingResponse:
        try:
            change_rate = await self.get_us_ranking("change-rate")
        except MarketRankingError:
            change_rate = MarketRankingResponse(
                trId="usa20910",
                title="미국주식 전일대비 등락률 상위",
                market="US",
                source="kiwoom-us-usa20910-unavailable",
                updatedAt=now_iso(),
                items=[],
                notes=["rankingUnavailable=true"],
            )
        if change_rate.items or not _is_us_premarket():
            return change_rate

        merged: dict[str, MarketRankItem] = {}
        sources: list[str] = []
        for ranking_type in ("realtime", "volume"):
            try:
                ranking = await self.get_us_ranking(ranking_type)
            except MarketRankingError:
                continue
            sources.append(ranking.trId)
            for item in ranking.items:
                if item.code and item.code not in merged and not _official_ranking_name_indicates_non_common_stock(item.name):
                    merged[item.code] = item

        items = sorted(
            merged.values(),
            key=lambda item: (item.changeRate, item.volume or 0),
            reverse=True,
        )[:10]
        if not items:
            return change_rate
        return MarketRankingResponse(
            trId="+".join(sources),
            title="미국주식 프리마켓 후보",
            market="US",
            source="kiwoom-us-premarket-candidates",
            updatedAt=now_iso(),
            items=[item.model_copy(update={"rank": index}) for index, item in enumerate(items, start=1)],
            notes=[
                "premarket=true",
                f"premarketEntryEnabled={str(_premarket_entry_enabled()).lower()}",
                "premarketOrderType=00",
            ],
        )

    async def get_us_pullback_auto_trade_plan(self) -> UsAutoTradePlanResponse:
        plans = await self.get_us_pullback_auto_trade_plans()
        selected = _select_pullback_plan(plans.plans)
        if selected is not None:
            return selected
        return _empty_pullback_plan(
            EMPTY_KIWOOM_CONDITION_STRATEGY,
            "HTS 키움 조건검색식 동기화 대기",
            "usa20280",
        )

    async def _build_pullback_strategy_plan(
        self,
        ranking: MarketRankingResponse,
        config: dict[str, object],
    ) -> UsAutoTradePlanResponse:
        evaluated = await self._build_pullback_strategy_candidates(
            ranking,
            config,
            condition_codes=None,
            condition_matches=None,
            condition_name=None,
        )
        return _select_pullback_plan(evaluated) or evaluated[0]

    async def _build_pullback_strategy_candidates(
        self,
        ranking: MarketRankingResponse,
        config: dict[str, object],
        *,
        condition_codes: set[str] | None,
        condition_matches: list[UsConditionSearchMatch] | None,
        condition_name: str | None,
    ) -> list[UsAutoTradePlanResponse]:
        strategy = str(config["strategy"])
        tick_scope = str(config["tick_scope"])
        target_profit_pct = float(config["target_profit_pct"])
        if not us_order_service.is_strategy_enabled(strategy):
            return [_empty_pullback_plan(config, "전략 OFF")]
        if condition_codes is None:
            return [_empty_pullback_plan(config, "usa20280→usa20281→usa20290 조건검색 결과 필요")]
        direct_condition_entry = bool(config.get("condition_direct_entry"))
        if direct_condition_entry:
            candidates = [
                _condition_match_to_market_item(match, index)
                for index, match in enumerate(condition_matches or [], start=1)
                if match.code
            ]
        else:
            candidates = [
                item
                for item in ranking.items[:10]
                if item.code
                and item.code in condition_codes
                and not _official_ranking_name_indicates_non_common_stock(item.name)
            ]
        if not candidates:
            if direct_condition_entry:
                return [_empty_pullback_plan(config, "키움 조건검색 편입 종목 대기", "usa20290")]
            source_label = "프리마켓 후보" if _ranking_is_premarket(ranking.trId) else "usa20910 TOP10"
            return [_empty_pullback_plan(config, f"키움 조건검색 편입 종목과 {source_label} 교집합 대기", ranking.trId)]

        evaluated: list[UsAutoTradePlanResponse] = []
        for target_rank, target in enumerate(candidates, start=1):
            exchange = target.exchange if target.exchange in {"NA", "ND", "NY"} else "ND"
            if direct_condition_entry:
                chart = UsChartResponse(
                    trId="",
                    code=target.code,
                    exchange=exchange,
                    timeframe="minute",
                    source="condition-direct-entry-no-chart",
                    updatedAt=now_iso(),
                    candles=[],
                )
            else:
                try:
                    chart = await self.get_us_chart(
                        timeframe="minute",
                        symbol=target.code,
                        exchange=exchange,
                        tick_scope=tick_scope,
                    )
                except Exception:
                    chart = UsChartResponse(
                        trId="usa06011",
                        code=target.code,
                        exchange=exchange,
                        timeframe="minute",
                        source="kiwoom-us-usa06011-unavailable",
                        updatedAt=now_iso(),
                        candles=[],
                    )
            evaluated.append(
                await self._compose_pullback_plan(
                    config=config,
                    target=target,
                    target_rank=target_rank,
                    chart=chart,
                    exchange=exchange,
                    target_profit_pct=target_profit_pct,
                    condition_codes=condition_codes,
                    condition_name=condition_name,
                    ranking_tr_id="usa20290" if direct_condition_entry else ranking.trId,
                )
            )

        return evaluated

    async def _compose_pullback_plan(
        self,
        *,
        config: dict[str, object],
        target: MarketRankItem,
        target_rank: int,
        chart: UsChartResponse,
        exchange: str,
        target_profit_pct: float,
        condition_codes: set[str],
        condition_name: str | None,
        ranking_tr_id: str,
    ) -> UsAutoTradePlanResponse:
        strategy = str(config["strategy"])
        strategy_name = str(config["name"])
        strategy_enabled = us_order_service.is_strategy_enabled(strategy)
        tick_scope = str(config["tick_scope"])
        stop_loss_pct = float(config.get("stop_loss_pct", 2.0))
        realtime = realtime_window_store.summary(target.code)
        direct_condition_entry = bool(config.get("condition_direct_entry"))
        if direct_condition_entry:
            criteria = _evaluate_condition_direct_criteria(
                target,
                condition_codes=condition_codes,
                condition_name=condition_name,
                realtime=realtime,
            )
            min_passed = len(criteria)
        else:
            criteria = _evaluate_pullback_strategy_criteria(
                target,
                chart,
                config,
                target_rank,
                condition_codes=condition_codes,
                condition_name=condition_name,
                ranking_tr_id=ranking_tr_id,
                realtime=realtime,
            )
            min_passed = _pullback_min_passed_criteria()
        available = [item for item in criteria if item.status != "unavailable"]
        passed = [item for item in available if item.status == "pass"]
        critical_keys = set(config.get("required_criteria", ()))
        # HTS condition inclusion is the sole strategy signal. Session and
        # quote checks remain execution prerequisites, not program searches.
        critical_keys.add("condition_search_match")
        premarket_entry = _is_us_premarket()
        if premarket_entry:
            critical_keys.add("premarket_orderbook")
        if bool(config.get("ai_recommended")):
            critical_keys.update(US_AI_RECOMMENDED_CRITICAL_CRITERIA)
        critical_failed = [
            item for item in criteria
            if item.key in critical_keys and item.status != "pass"
        ]
        ready = strategy_enabled and len(passed) >= min_passed and not critical_failed
        reference_price = target.price if target.price > 0 else (chart.candles[-1].close if chart.candles else 0)
        trade_type = "03"
        if premarket_entry:
            trade_type = "00"
            reference_price = _premarket_buy_limit_price(realtime) or 0
        ticket = None
        if reference_price > 0:
            ticket = UsAutoTradeOrderTicket(
                side="buy",
                exchange=exchange,
                symbol=target.code,
                quantity=1,
                tradeType=trade_type,
                referencePrice=reference_price,
                targetProfitPct=target_profit_pct,
                takeProfitPrice=round(reference_price * (1 + target_profit_pct / 100), 4),
                submitEndpoint="/api/us/orders",
                submitBlocked=True,
                submitBlockReason="live_order_waits_for_policy_and_entry_conditions",
            )
        take_profit_ticket = None
        if ticket is not None:
            take_profit_ticket = UsAutoTradeOrderTicket(
                side="sell",
                exchange=exchange,
                symbol=target.code,
                quantity=1,
                tradeType="30",
                referencePrice=ticket.takeProfitPrice,
                targetProfitPct=target_profit_pct,
                takeProfitPrice=ticket.takeProfitPrice,
                submitEndpoint="/api/us/orders",
                submitBlocked=True,
                submitBlockReason="live_order_waits_for_auto_exit_monitor",
            )
        execution_state = "entry_ready" if ready else "waiting_conditions"
        live_blockers: list[str] = []
        if not strategy_enabled:
            live_blockers.append("STRATEGY_DISABLED")
        if critical_failed:
            live_blockers.append("ENTRY_CRITICAL_CONDITIONS_FAILED")
        if not ready:
            live_blockers.append("ENTRY_CONDITIONS_NOT_READY")
        if ticket is None:
            live_blockers.append("BUY_TICKET_UNAVAILABLE")
        if take_profit_ticket is None:
            live_blockers.append("TAKE_PROFIT_TICKET_UNAVAILABLE")
        process_ready = ready and ticket is not None and take_profit_ticket is not None
        live_auto_submit_ready = process_ready and not live_blockers
        if ticket is not None:
            ticket = ticket.model_copy(update={
                "submitBlocked": not live_auto_submit_ready,
                "submitBlockReason": None if live_auto_submit_ready else "live_auto_order_blocked_by_policy_or_conditions",
            })
        if take_profit_ticket is not None:
            take_profit_ticket = take_profit_ticket.model_copy(update={
                "submitBlocked": not live_auto_submit_ready,
                "submitBlockReason": None if live_auto_submit_ready else "live_auto_exit_waits_for_buy_fill_and_target",
            })
        process_steps = _one_share_process_steps(
            ready=ready,
            buy_ticket=ticket,
            sell_ticket=take_profit_ticket,
            blockers=live_blockers,
            strategy_name=strategy_name,
            tick_scope=tick_scope,
            target_profit_pct=target_profit_pct,
            ranking_tr_id=ranking_tr_id,
        )
        return UsAutoTradePlanResponse(
            source="kiwoom-us-auto-trade-plan-mvp",
            strategy=strategy,
            strategyName=strategy_name,
            conditionSeq=str(config.get("condition_seq") or "") or None,
            conditionName=condition_name or str(config.get("condition_name") or "") or None,
            enabled=strategy_enabled,
            timeframe="minute",
            tickScope=tick_scope,
            rankingTrId=ranking_tr_id,
            chartTrId="" if direct_condition_entry else "usa06011",
            orderPrecheckTrId="ust31490",
            updatedAt=now_iso(),
            targetRank=target_rank,
            target=target.model_copy(update={"rank": target_rank}),
            criteria=criteria,
            minPassedCriteria=min_passed,
            passedCriteriaCount=len(passed),
            criticalFailedCriteria=[item.key for item in critical_failed],
            readyForEntry=ready,
            stopLossPct=stop_loss_pct,
            orderTicket=ticket,
            takeProfitOrderTicket=take_profit_ticket,
            oneShareProcessReady=process_ready,
            liveOrderBlockedReasons=_dedupe(live_blockers),
            processSteps=process_steps,
            executionState=execution_state,
            nextAction=_live_next_action(execution_state, target_profit_pct),
        )

def _us_ranking_payload(tr_id: str) -> dict[str, object]:
    if tr_id == "usa01980":
        return {"svc_type": "B281"}
    if tr_id == "usa20910":
        return {
            "stex_tp": "0",
            "inds_cd": "",
            "inds_cls_tp": "0",
            "sort_tp": "1",
            "stk_tp": "1",
            "stk_cnd": "0",
            "pric_cnd": "0",
            "trde_prica_cnd": "0",
            "trde_qty_tp": "",
        }
    if tr_id == "usa20530":
        return {
            "stex_tp": "0",
            "inds_cd": "",
            "stk_tp": "1",
            "trde_qty_tp": "0",
            "qry_tp": "0",
            "stk_cnd": "0",
            "pric_cnd": "0",
            "trde_prica_cnd": "0",
        }
    if tr_id == "usa20930":
        return {
            "stex_tp": "0",
            "stk_tp": "1",
            "inds_cd": "",
            "stk_cnd": "0",
            "flu_tp": "1",
            "tm_tp": "1",
            "tm": "0",
            "pric_cnd": "0",
            "trde_qty_tp": "0",
            "trde_prica_cnd": "0",
        }
    return {}


def _empty_pullback_plan(
    config: dict[str, object],
    reason: str,
    ranking_tr_id: str = "usa20910",
) -> UsAutoTradePlanResponse:
    direct_condition_entry = bool(config.get("condition_direct_entry"))
    empty_criterion = (
        _auto_criterion(
            "condition_search_match",
            "키움 조건검색 편입",
            "unavailable",
            None,
            reason,
        )
        if direct_condition_entry
        else _auto_criterion(
            "top10_change_rate",
            "전일대비 등락률 상위 10개",
            "unavailable",
            None,
            reason,
        )
    )
    return UsAutoTradePlanResponse(
        source="kiwoom-us-auto-trade-plan-mvp",
        strategy=str(config["strategy"]),
        strategyName=str(config["name"]),
        conditionSeq=str(config.get("condition_seq") or "") or None,
        conditionName=str(config.get("condition_name") or "") or None,
        enabled=us_order_service.is_strategy_enabled(str(config["strategy"])),
        timeframe="minute",
        tickScope=str(config["tick_scope"]),
        rankingTrId=ranking_tr_id,
        chartTrId="" if direct_condition_entry else "usa06011",
        orderPrecheckTrId="ust31490",
        updatedAt=now_iso(),
        targetRank=0,
        target=None,
        criteria=[empty_criterion],
        minPassedCriteria=3 if direct_condition_entry else _pullback_min_passed_criteria(),
        criticalFailedCriteria=["condition_search_match"] if direct_condition_entry else [],
        readyForEntry=False,
        orderTicket=None,
        executionState="waiting_for_condition_entry" if direct_condition_entry else "waiting_for_rank_data",
        nextAction="키움 조건검색 실시간 편입 대기" if direct_condition_entry else "전일대비 등락률 상위 목록 수신 대기",
    )


def _select_pullback_plan(plans: list[UsAutoTradePlanResponse]) -> UsAutoTradePlanResponse | None:
    if not plans:
        return None
    ready = [plan for plan in plans if plan.readyForEntry and plan.orderTicket is not None]
    if ready:
        return sorted(ready, key=lambda plan: (plan.passedCriteriaCount, -(plan.targetRank or 99)), reverse=True)[0]
    return sorted(plans, key=lambda plan: (plan.passedCriteriaCount, -(plan.targetRank or 99)), reverse=True)[0]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def _live_next_action(state: str, target_profit_pct: float = 2.0) -> str:
    if state == "waiting_price":
        return "실시간 진입 기준가 수신 대기"
    if state == "entry_ready":
        return f"주문 정책 확인 후 진입 · +{target_profit_pct:.0f}% 목표 감시"
    return "눌림 조건 추가 충족 대기"


def _one_share_process_steps(
    *,
    ready: bool,
    buy_ticket: UsAutoTradeOrderTicket | None,
    sell_ticket: UsAutoTradeOrderTicket | None,
    blockers: list[str],
    strategy_name: str = "등락률 눌림매매",
    tick_scope: str = "1",
    target_profit_pct: float = 2.0,
    ranking_tr_id: str = "usa20910",
) -> list[UsAutoTradeProcessStep]:
    entry_status = "ready" if ready and buy_ticket is not None else "waiting"
    order_status = "blocked" if blockers else "ready"
    sell_status = "ready" if sell_ticket is not None else "waiting"
    return [
        UsAutoTradeProcessStep(
            step="entry_signal",
            label="조건 충족 확인",
            status=entry_status,
            trId=f"{ranking_tr_id}+usa06011",
            detail=f"{strategy_name}: {ranking_tr_id} 후보, 거래량 30만주, {tick_scope}분봉 눌림 조건이 충족되면 1주 매수 후보가 됩니다.",
        ),
        UsAutoTradeProcessStep(
            step="buy_order_ticket",
            label="1주 매수 주문표",
            status="ready" if buy_ticket is not None else "waiting",
            trId="ust20000",
            detail="자동매매 ON, 주문 정책, 조건식을 모두 통과하면 백엔드 runner가 미국주식 매수 TR을 전송합니다.",
        ),
        UsAutoTradeProcessStep(
            step="live_order_policy",
            label="실주문 안전장치",
            status=order_status,
            trId=None,
            detail="; ".join(blockers[:6]) if blockers else "주문 정책상 차단 사유가 없습니다. 다음 runner tick에서 자동 주문 전송 대상입니다.",
        ),
        UsAutoTradeProcessStep(
            step="take_profit_sell_ticket",
            label=f"+{target_profit_pct:.0f}% 매도 주문표",
            status=sell_status,
            trId="ust20001",
            detail=f"매수 체결 후 기준가 대비 +{target_profit_pct:.0f}%부터 익절 감시에 들어가고, -2% 손절 또는 강한 음봉 반전 시 매도 요청으로 이어집니다.",
        ),
    ]


def _evaluate_pullback_strategy_criteria(
    item: MarketRankItem,
    chart: UsChartResponse,
    config: dict[str, object],
    target_rank: int,
    *,
    condition_codes: set[str] | None = None,
    condition_name: str | None = None,
    ranking_tr_id: str = "usa20910",
    realtime: RealtimeWindowSummary | None = None,
) -> list[UsAutoTradeCriterion]:
    tick_scope = str(config["tick_scope"])
    all_candles = _completed_strategy_candles(chart.candles, tick_scope)
    candles = all_candles[-12:]
    latest = candles[-1] if candles else None
    recent_high = max((row.high for row in candles), default=0)
    pullback_pct = ((recent_high - latest.close) / recent_high * 100) if latest and recent_high > 0 else None
    bearish_count = int(config["bearish_count"])
    entry_rule = str(config["entry_rule"])
    pattern = (
        _ai_pullback_pattern_status(all_candles)
        if entry_rule == "ai_pullback_reversal"
        else _pullback_pattern_status(candles, bearish_count, entry_rule)
    )
    session_open, session_label = _strategy_session_status(tick_scope)
    premarket = _is_us_premarket()
    ranking_label = "프리마켓 후보 상위 10개" if _ranking_is_premarket(ranking_tr_id) else "전일대비 등락률 상위 10개"
    criteria = [
        _auto_criterion(
            "strategy_session",
            "전략 진입 시간",
            "pass" if session_open else "fail",
            session_label,
            "프리마켓 지정가 진입 허용 시간" if session_open and premarket else (
                "전략 진입 허용 시간" if session_open else "현재 세션은 신규 진입 허용 시간이 아님"
            ),
        ),
        _auto_criterion(
            "condition_search_match",
            "키움 조건검색 편입",
            "unavailable" if condition_codes is None else ("pass" if item.code in condition_codes else "fail"),
            condition_name if condition_codes is not None and item.code in condition_codes else None,
            "usa20280→usa20281→usa20290 조건검색 결과에 포함" if condition_codes is not None and item.code in condition_codes else "키움 조건검색 편입 결과 필요",
        ),
        _auto_criterion(
            "top10_change_rate",
            ranking_label,
            "pass" if 1 <= target_rank <= 10 else "fail",
            f"TOP{target_rank}" if target_rank else None,
            f"{ranking_tr_id} 상위 10개 종목" if 1 <= target_rank <= 10 else f"{ranking_tr_id} 상위 10개 밖",
        ),
        _auto_criterion(
            "common_stock_only",
            "일반주식 조건",
            "pass" if not _official_ranking_name_indicates_non_common_stock(item.name) else "fail",
            "stk_tp=1",
            f"{ranking_tr_id} 일반주식 후보 기준" if not _official_ranking_name_indicates_non_common_stock(item.name) else "ETF/권리/레버리지성 이름 제외",
        ),
        _auto_criterion(
            "positive_change",
            "전일대비 상승",
            "pass" if item.changeRate > 0 else "fail",
            f"{item.changeRate:+.2f}%",
            "전일대비 상승 종목" if item.changeRate > 0 else "전일대비 상승 아님",
        ),
        _auto_criterion(
            "volume_300k",
            "거래량 30만주 이상",
            "unavailable" if item.volume is None else ("pass" if item.volume >= US_PULLBACK_VOLUME_THRESHOLD else "fail"),
            None if item.volume is None else str(item.volume),
            "누적 거래량 300,000주 이상" if item.volume is not None and item.volume >= US_PULLBACK_VOLUME_THRESHOLD else "누적 거래량 300,000주 미만 또는 미수신",
        ),
        _auto_criterion(
            "pullback_depth",
            "고점 대비 눌림",
            "unavailable" if pullback_pct is None else ("pass" if 0.1 <= pullback_pct <= 6.0 else "fail"),
            None if pullback_pct is None else f"{pullback_pct:.2f}%",
            "최근 고점 대비 눌림 구간" if pullback_pct is not None and 0.1 <= pullback_pct <= 6.0 else "눌림 폭 데이터 부족 또는 과도",
        ),
        _auto_criterion(
            "pullback_entry_pattern",
            str(pattern["label"]),
            str(pattern["status"]),
            str(pattern["value"]) if pattern["value"] is not None else None,
            str(pattern["reason"]),
        ),
    ]
    if premarket:
        limit_price = _premarket_buy_limit_price(realtime)
        criteria.append(
            _auto_criterion(
                "premarket_orderbook",
                "프리마켓 실시간 호가",
                "pass" if limit_price is not None else "fail",
                None if limit_price is None else f"${limit_price:.4f}",
                "FT 최우선 매도호가·10초 이내 수신·스프레드 0.15% 이하"
                if limit_price is not None
                else "프리마켓 지정가 주문에 필요한 최신 FT 호가 또는 스프레드 조건 미충족",
            )
        )
    if bool(config.get("ai_recommended")):
        criteria.extend(_ai_recommended_5m_criteria(item, all_candles, realtime))
    return criteria


def _evaluate_condition_direct_criteria(
    item: MarketRankItem,
    *,
    condition_codes: set[str],
    condition_name: str | None,
    realtime: RealtimeWindowSummary | None,
) -> list[UsAutoTradeCriterion]:
    session_open, session_label = _condition_direct_session_status()
    criteria = [
        _auto_criterion(
            "strategy_session",
            "주문 가능 시간",
            "pass" if session_open else "fail",
            session_label,
            "키움 조건 편입 직접 진입 허용 시간" if session_open else "현재는 신규 진입 허용 시간이 아님",
        ),
        _auto_criterion(
            "condition_search_match",
            "키움 조건검색 편입",
            "pass" if item.code in condition_codes else "fail",
            condition_name if item.code in condition_codes else None,
            "usa20280→usa20281→usa20290 실시간 조건검색 편입"
            if item.code in condition_codes else "키움 조건검색 편입 결과 필요",
        ),
        _auto_criterion(
            "quote_price",
            "주문 기준가격",
            "pass" if item.price > 0 else "fail",
            f"${item.price:.4f}" if item.price > 0 else None,
            "조건검색 또는 FE 실시간 현재가 수신" if item.price > 0 else "주문에 필요한 현재가 미수신",
        ),
    ]
    if _is_us_premarket():
        limit_price = _premarket_buy_limit_price(realtime)
        criteria.append(
            _auto_criterion(
                "premarket_orderbook",
                "프리마켓 실시간 호가",
                "pass" if limit_price is not None else "fail",
                None if limit_price is None else f"${limit_price:.4f}",
                "FT 최우선 매도호가·10초 이내 수신·스프레드 0.15% 이하"
                if limit_price is not None else "프리마켓 지정가 주문에 필요한 최신 FT 호가 미수신",
            )
        )
    return criteria


def _ai_recommended_5m_criteria(
    item: MarketRankItem,
    candles: list[UsChartCandle],
    realtime: RealtimeWindowSummary | None,
) -> list[UsAutoTradeCriterion]:
    closes = [row.close for row in candles]
    ema9 = _latest_ema(closes, 9)
    ema20 = _latest_ema(closes, 20)
    ema50 = _latest_ema(closes, 50)
    current_vwap = _chart_vwap(candles)
    latest = candles[-1] if candles else None
    spread = realtime.spreadPct if realtime else None
    ema_values_available = ema9 is not None and ema20 is not None and ema50 is not None
    return [
        _auto_criterion("ai_price_range", "가격 $5~300", "pass" if 5 <= item.price <= 300 else "fail", f"${item.price:.4f}", "AI 추천 종목 가격 범위"),
        _auto_criterion("ai_change_range", "등락률 +1.5~40%", "pass" if 1.5 <= item.changeRate <= 40 else "fail", f"{item.changeRate:+.2f}%", "과열 추격 상한을 포함한 상승 종목 범위"),
        _auto_criterion("ai_volume_1m", "거래량 100만주", "unavailable" if item.volume is None else ("pass" if item.volume >= 1_000_000 else "fail"), None if item.volume is None else str(item.volume), "누적 거래량 1,000,000주 이상"),
        _auto_criterion("ai_trade_value_20m", "거래대금 $20M", "unavailable" if item.tradingValue is None else ("pass" if item.tradingValue >= 20_000_000 else "fail"), None if item.tradingValue is None else f"${item.tradingValue:,.0f}", "누적 거래대금 2,000만 달러 이상"),
        _auto_criterion("ai_close_above_vwap", "종가 > VWAP", "unavailable" if latest is None or current_vwap is None else ("pass" if latest.close > current_vwap else "fail"), None if current_vwap is None else f"{current_vwap:.4f}", "5분봉 종가가 당일 VWAP 위"),
        _auto_criterion("ai_ema_stack", "EMA9 > EMA20 > EMA50", "unavailable" if not ema_values_available else ("pass" if ema9 > ema20 > ema50 else "fail"), None if not ema_values_available else f"{ema9:.4f}/{ema20:.4f}/{ema50:.4f}", "5분봉 상승 추세 정렬"),
        _auto_criterion("ai_rvol", "동시간 RVOL 1.5", "unavailable", None, "과거 동일 시간대 누적 거래량 기준선 저장이 필요"),
        _auto_criterion("ai_spread", "스프레드 0.15% 이하", "unavailable" if spread is None else ("pass" if spread <= 0.15 else "fail"), None if spread is None else f"{spread:.3f}%", "FT 실시간 1호가 스프레드"),
    ]


def _latest_ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    value = sum(values[:period]) / period
    multiplier = 2 / (period + 1)
    for current in values[period:]:
        value = current * multiplier + value * (1 - multiplier)
    return value


def _chart_vwap(candles: list[UsChartCandle]) -> float | None:
    total_volume = sum(max(0, row.volume) for row in candles)
    if total_volume <= 0:
        return None
    return sum(((row.high + row.low + row.close) / 3) * max(0, row.volume) for row in candles) / total_volume


def _ai_pullback_pattern_status(candles: list[UsChartCandle]) -> dict[str, object]:
    if len(candles) < 27:
        return {
            "label": "상승파동 후 2~4봉 눌림 반전",
            "status": "unavailable",
            "value": None,
            "reason": "완료된 5분봉 27개 이상 필요",
        }
    latest = candles[-1]
    for pullback_size in range(4, 1, -1):
        pullback = candles[-(pullback_size + 1):-1]
        for wave_size in range(6, 2, -1):
            wave_end = len(candles) - (pullback_size + 1)
            wave_start = wave_end - wave_size
            if wave_start < 20:
                continue
            wave = candles[wave_start:wave_end]
            baseline = [row.volume for row in candles[wave_start - 20:wave_start]]
            median_volume = sorted(baseline)[len(baseline) // 2] if baseline else 0
            wave_low = min(row.low for row in wave)
            wave_high = max(row.high for row in wave)
            wave_range = wave_high - wave_low
            wave_gain = (wave_high - wave[0].open) / wave[0].open * 100 if wave[0].open > 0 else 0
            wave_avg_volume = sum(row.volume for row in wave) / len(wave)
            pullback_low = min(row.low for row in pullback)
            retrace = (wave_high - pullback_low) / wave_range * 100 if wave_range > 0 else 0
            pullback_avg_volume = sum(row.volume for row in pullback) / len(pullback)
            ready = (
                wave_gain >= 1.2
                and median_volume > 0
                and wave_avg_volume >= median_volume * 1.5
                and 30 <= retrace <= 60
                and pullback_avg_volume <= wave_avg_volume * 0.7
                and latest.close > latest.open
                and latest.close > pullback[-1].high
                and latest.volume > pullback_avg_volume * 1.2
            )
            if ready:
                return {
                    "label": "상승파동 후 2~4봉 눌림 반전",
                    "status": "pass",
                    "value": f"{pullback_size}봉 · {retrace:.1f}%",
                    "reason": "거래량 감소 눌림 후 반전봉 직전 고가 돌파",
                }
    return {
        "label": "상승파동 후 2~4봉 눌림 반전",
        "status": "fail",
        "value": None,
        "reason": "상승파동·30~60% 되돌림·거래량 감소·반전 돌파 조합 대기",
    }


def _pullback_pattern_status(
    candles: list[UsChartCandle],
    bearish_count: int,
    entry_rule: str,
) -> dict[str, object]:
    if len(candles) < bearish_count + 1:
        return {
            "label": f"{bearish_count}연속 음봉 후 진입 캔들",
            "status": "unavailable",
            "value": None,
            "reason": f"분봉 {bearish_count + 1}개 이상 필요",
        }
    previous = candles[-(bearish_count + 1):-1]
    latest = candles[-1]
    bearish_ok = all(row.close < row.open for row in previous)
    if entry_rule == "bullish_reversal":
        bullish = latest.close > latest.open
        return {
            "label": f"5분봉 {bearish_count}음봉 후 양봉 전환",
            "status": "pass" if bearish_ok and bullish else "fail",
            "value": f"{sum(1 for row in previous if row.close < row.open)}/{bearish_count}",
            "reason": (
                f"{bearish_count}번 음봉 후 다음 양봉 출현"
                if bearish_ok and bullish
                else f"{bearish_count}음봉 후 양봉 전환 미확인"
            ),
        }
    prior_close = previous[-1].close if previous else 0
    drop_pct = ((prior_close - latest.close) / prior_close * 100) if prior_close > 0 else None
    shallow_drop = drop_pct is not None and 0 < drop_pct <= 1.0
    return {
        "label": "1분봉 2음봉 후 1% 이하 추가 눌림",
        "status": "pass" if bearish_ok and shallow_drop else "fail",
        "value": None if drop_pct is None else f"{drop_pct:.2f}%",
        "reason": "2번 음봉 후 다음 캔들 1% 이하 추가 눌림" if bearish_ok and shallow_drop else "2음봉 후 1% 이하 추가 눌림 미확인",
    }


def _map_us_item(row: dict[str, Any], index: int, reason: str) -> MarketRankItem:
    return MarketRankItem(
        rank=_safe_int(row.get("rank") or row.get("kw_high_rank"), index),
        code=str(row.get("stk_cd") or ""),
        name=str(row.get("stk_nm") or row.get("stk_enm") or row.get("stk_cd") or ""),
        price=float(_safe_price(row.get("cur_prc") or row.get("curr_pric"))),
        changeRate=float(_safe_number(row.get("flu_rt") or row.get("diff_rate_for_gjga"))),
        volume=_optional_int(row.get("acc_trde_qty") or row.get("trde_qty")),
        tradingValue=_optional_float(row.get("trde_prica")),
        exchange=str(row.get("stex_tp") or "") or None,
        reason=reason,
    )


def _condition_match_to_market_item(match: UsConditionSearchMatch, index: int) -> MarketRankItem:
    realtime = realtime_window_store.summary(match.code)
    realtime_price = realtime.latestPrice if realtime is not None else None
    realtime_volume = realtime.latestVolume if realtime is not None else None
    return MarketRankItem(
        rank=index,
        code=match.code,
        name=match.name or match.code,
        price=float(match.price or realtime_price or 0),
        changeRate=float(match.changeRate or 0),
        volume=match.volume if match.volume is not None else realtime_volume,
        tradingValue=None,
        exchange=match.exchange,
        reason="키움 조건검색 실시간 편입",
    )


def _sort_us_ranking_items(tr_id: str, items: list[MarketRankItem]) -> list[MarketRankItem]:
    if tr_id == "usa20910":
        ordered = sorted(items, key=lambda item: (item.changeRate, item.volume or 0), reverse=True)
    elif tr_id == "usa20530":
        ordered = sorted(items, key=lambda item: (item.volume or 0, item.changeRate), reverse=True)
    else:
        ordered = items
    return [item.model_copy(update={"rank": index}) for index, item in enumerate(ordered, start=1)]


def _official_ranking_name_indicates_non_common_stock(value: str | None) -> bool:
    text = (value or "").upper()
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


def _default_chart_start(timeframe: str) -> str:
    days = {
        "minute": 7,
        "day": 180,
        "week": 730,
        "month": 1825,
    }.get(timeframe, 180)
    return (date.today() - timedelta(days=days)).strftime("%Y%m%d")


def _map_us_chart_candle(row: dict[str, Any]) -> UsChartCandle:
    return UsChartCandle(
        close=_safe_price(row.get("cur_prc")),
        volume=_safe_int(row.get("trde_qty") or row.get("acc_trde_qty")),
        open=_safe_price(row.get("open_pric")),
        high=_safe_price(row.get("high_pric")),
        low=_safe_price(row.get("low_pric")),
        executedAt=str(row.get("cntr_tm") or row.get("dt") or "") or None,
        businessDate=str(row.get("bus_dt") or row.get("dt") or "") or None,
    )


def _normalize_us_chart_candles(rows: list[object]) -> list[UsChartCandle]:
    indexed: dict[str, UsChartCandle] = {}
    without_timestamp: list[UsChartCandle] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        candle = _map_us_chart_candle(row)
        key = candle.executedAt or ""
        if not key:
            without_timestamp.append(candle)
            continue
        existing = indexed.get(key)
        if existing is None:
            indexed[key] = candle
            continue
        indexed[key] = UsChartCandle(
            open=existing.open,
            high=max(existing.high, candle.high),
            low=min(existing.low, candle.low),
            close=candle.close,
            volume=max(existing.volume, candle.volume),
            executedAt=key,
            businessDate=candle.businessDate or existing.businessDate,
        )
    return [indexed[key] for key in sorted(indexed)] + without_timestamp


def _completed_strategy_candles(candles: list[UsChartCandle], tick_scope: str) -> list[UsChartCandle]:
    if not candles:
        return []
    latest_at = parse_kiwoom_us_candle_time(candles[-1].executedAt)
    if latest_at is None:
        return candles
    try:
        interval_minutes = max(1, int(tick_scope))
    except ValueError:
        interval_minutes = 1
    if datetime.now(ZoneInfo("America/New_York")) < latest_at + timedelta(minutes=interval_minutes):
        return candles[:-1]
    return candles


def parse_kiwoom_us_candle_time(value: str | None) -> datetime | None:
    """Parse observed Kiwoom US business-date + extended KST hour timestamps."""
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if len(digits) < 14:
        return None
    try:
        base = datetime.strptime(digits[:8], "%Y%m%d").replace(tzinfo=ZoneInfo("Asia/Seoul"))
        hour, minute, second = int(digits[8:10]), int(digits[10:12]), int(digits[12:14])
        if hour > 47 or minute > 59 or second > 59:
            return None
        return base + timedelta(hours=hour, minutes=minute, seconds=second)
    except (TypeError, ValueError):
        return None


def _auto_criterion(key: str, label: str, status: str, value: str | None, reason: str) -> UsAutoTradeCriterion:
    return UsAutoTradeCriterion(key=key, label=label, status=status, value=value, reason=reason)


def _pullback_min_passed_criteria() -> int:
    raw = os.getenv("KIWOOM_US_PULLBACK_MIN_PASSED_CRITERIA", str(US_PULLBACK_DEFAULT_MIN_PASSED_CRITERIA))
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = US_PULLBACK_DEFAULT_MIN_PASSED_CRITERIA
    return max(1, min(parsed, 6))


def _is_us_premarket(now: datetime | None = None) -> bool:
    current = now.astimezone(ZoneInfo("America/New_York")) if now is not None else datetime.now(ZoneInfo("America/New_York"))
    minutes = current.hour * 60 + current.minute
    return current.weekday() < 5 and 4 * 60 <= minutes < 9 * 60 + 30


def _premarket_entry_enabled() -> bool:
    return os.getenv("KIWOOM_US_PREMARKET_ENTRY_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _premarket_buy_limit_price(realtime: RealtimeWindowSummary | None) -> float | None:
    if realtime is None or realtime.bid is None or realtime.ask is None:
        return None
    if realtime.bid <= 0 or realtime.ask <= 0 or realtime.ask < realtime.bid:
        return None
    if realtime.spreadPct is None or realtime.spreadPct > US_PREMARKET_MAX_SPREAD_PCT:
        return None
    if not _iso_timestamp_is_fresh(realtime.lastEventAt, US_PREMARKET_MAX_QUOTE_AGE_SECONDS):
        return None
    return round(realtime.ask, 4)


def _iso_timestamp_is_fresh(value: str | None, max_age_seconds: int) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        return False
    age_seconds = (datetime.now(parsed.tzinfo) - parsed).total_seconds()
    return 0 <= age_seconds <= max_age_seconds


def _ranking_is_premarket(tr_id: str) -> bool:
    sources = set(str(tr_id).split("+"))
    return bool(sources & {"usa01980", "usa20530"}) and "usa20910" not in sources


def _condition_direct_session_status(now: datetime | None = None) -> tuple[bool, str]:
    current = now.astimezone(ZoneInfo("America/New_York")) if now is not None else datetime.now(ZoneInfo("America/New_York"))
    minutes = current.hour * 60 + current.minute
    if current.weekday() >= 5:
        return False, "미국장 휴장일"
    if 4 * 60 <= minutes < 9 * 60 + 30:
        return _premarket_entry_enabled(), "04:00~09:29 ET · 지정가(00)"
    return 9 * 60 + 30 <= minutes < 15 * 60 + 50, "09:30~15:49 ET · 시장가(03)"


def _strategy_session_status(tick_scope: str, now: datetime | None = None) -> tuple[bool, str]:
    current = now.astimezone(ZoneInfo("America/New_York")) if now is not None else datetime.now(ZoneInfo("America/New_York"))
    minutes = current.hour * 60 + current.minute
    if current.weekday() < 5 and 4 * 60 <= minutes < 9 * 60 + 30:
        return _premarket_entry_enabled(), "04:00~09:29 ET · 지정가(00)"
    if tick_scope == "5":
        start, end, label = 9 * 60 + 45, 14 * 60 + 30, "09:45~14:30 ET"
    else:
        start, end, label = 9 * 60 + 35, 11 * 60 + 30, "09:35~11:30 ET"
    return current.weekday() < 5 and start <= minutes <= end, label


def _safe_symbol(value: str) -> str:
    symbol = "".join(ch for ch in str(value).upper().strip() if ch.isalnum() or ch in {".", "-"})
    if not symbol:
        raise MarketRankingError("US symbol is required")
    return symbol[:16]


def _safe_yyyymmdd(value: str) -> str:
    cleaned = str(value).strip()
    if len(cleaned) != 8 or not cleaned.isdigit():
        raise MarketRankingError("startDate must be YYYYMMDD")
    return cleaned


def _safe_number(value: object) -> float:
    try:
        return float(str(value).replace(",", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _safe_price(value: object) -> float:
    return abs(_safe_number(value))


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "").replace("+", "").strip()))
    except (TypeError, ValueError):
        return default


def _optional_int(value: object) -> int | None:
    parsed = _safe_int(value, 0)
    return parsed if value not in (None, "") else None


def _optional_float(value: object) -> float | None:
    parsed = _safe_number(value)
    return parsed if value not in (None, "") else None


market_ranking_service = MarketRankingService()
