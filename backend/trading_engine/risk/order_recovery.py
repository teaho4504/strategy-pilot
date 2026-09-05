from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Iterable

from trading_engine.providers.kiwoom_us.order_event_mapper import (
    UsBrokerOrderEvent,
    map_us_order_realtime_payload,
)
from trading_engine.risk.allocation_store import (
    AllocationBrokerEvent,
    AllocationCycle,
    CapitalAllocationStore,
)


@dataclass(frozen=True, slots=True)
class OrderRecoverySummary:
    payload_count: int
    event_count: int
    updated_count: int
    duplicate_count: int
    unmatched_count: int
    ignored_count: int


def replay_us_order_event_payloads(
    *,
    store: CapitalAllocationStore,
    cycle: AllocationCycle,
    payloads: Iterable[dict[str, Any]],
) -> OrderRecoverySummary:
    payload_count = 0
    event_count = 0
    outcomes: list[str] = []
    for payload in payloads:
        payload_count += 1
        events = map_us_order_realtime_payload(payload)
        event_count += len(events)
        outcomes.extend(
            _apply_us_order_events(
                store=store,
                cycle=cycle,
                events=events,
            )
        )

    return _summary(
        payload_count=payload_count,
        event_count=event_count,
        outcomes=outcomes,
    )


def apply_us_order_events(
    *,
    store: CapitalAllocationStore,
    cycle: AllocationCycle,
    events: Iterable[UsBrokerOrderEvent],
) -> OrderRecoverySummary:
    event_list = tuple(events)
    return _summary(
        payload_count=0,
        event_count=len(event_list),
        outcomes=_apply_us_order_events(
            store=store,
            cycle=cycle,
            events=event_list,
        ),
    )


def _apply_us_order_events(
    *,
    store: CapitalAllocationStore,
    cycle: AllocationCycle,
    events: Iterable[UsBrokerOrderEvent],
) -> list[str]:
    outcomes: list[str] = []
    for event in events:
        result = store.apply_broker_event(
            cycle=cycle,
            event=_to_allocation_event(event),
        )
        outcomes.append(result.outcome)
    return outcomes


def _summary(
    *,
    payload_count: int,
    event_count: int,
    outcomes: list[str],
) -> OrderRecoverySummary:
    return OrderRecoverySummary(
        payload_count=payload_count,
        event_count=event_count,
        updated_count=outcomes.count("updated"),
        duplicate_count=outcomes.count("duplicate"),
        unmatched_count=outcomes.count("unmatched"),
        ignored_count=len(outcomes)
        - outcomes.count("updated")
        - outcomes.count("duplicate")
        - outcomes.count("unmatched"),
    )


def _to_allocation_event(event: UsBrokerOrderEvent) -> AllocationBrokerEvent:
    return AllocationBrokerEvent(
        event_key=_event_key(event),
        tr_id=event.tr_id,
        order_no=event.order_no,
        original_order_no=event.original_order_no,
        symbol=event.symbol,
        side=event.side,
        status=event.status,
        fill_quantity=event.fill_quantity or 0,
        unfilled_quantity=event.unfilled_quantity,
    )


def _event_key(event: UsBrokerOrderEvent) -> str:
    material = "|".join(
        (
            event.tr_id,
            event.order_no,
            event.original_order_no or "",
            event.symbol,
            event.status,
            event.event_time or "",
            event.fill_no or "",
            str(event.fill_quantity or 0),
            str(event.fill_price or ""),
            str(event.unfilled_quantity if event.unfilled_quantity is not None else ""),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
