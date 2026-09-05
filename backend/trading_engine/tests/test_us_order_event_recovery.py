from __future__ import annotations

import sqlite3

from trading_engine.risk.allocation_store import CapitalAllocationStore
from trading_engine.risk.capital_allocator import (
    CapitalAllocationState,
    evaluate_capital_allocation,
)
from trading_engine.risk.order_recovery import replay_us_order_event_payloads


def _submitted_reservation(
    tmp_path,
    *,
    symbol: str = "NVDA",
    quantity: int = 2,
    order_no: str = "original-order",
):
    db_path = tmp_path / "allocation.sqlite3"
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-30",
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(
            cycle_capital=4_000,
            orderable_cash=4_000,
        ),
        symbol=symbol,
        reference_price=100,
        max_quantity=quantity,
    )
    reservation = store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )
    store.mark_submitted(reservation.id, order_no)
    return db_path, cycle, reservation


def _f5_payload(
    *,
    order_no: str = "original-order",
    symbol: str = "NVDA",
    status: str = "부분체결",
    fill_no: str = "fill-1",
    fill_quantity: str = "1",
    unfilled_quantity: str = "1",
    side: str = "02",
    account_marker: str = "ACCOUNT-MUST-NOT-PERSIST",
):
    return {
        "trnm": "REAL",
        "data": [
            {
                "type": "F5",
                "item": symbol,
                "values": {
                    "9201": account_marker,
                    "9203": order_no,
                    "9001": symbol,
                    "907": side,
                    "908": "101501",
                    "913": status,
                    "900": "2",
                    "902": unfilled_quantity,
                    "909": fill_no,
                    "910": "100.25",
                    "911": fill_quantity,
                    "8043": "USD",
                },
            }
        ],
    }


def _f4_payload(
    *,
    order_no: str,
    original_order_no: str,
    symbol: str = "NVDA",
    status: str,
):
    return {
        "trnm": "REAL",
        "data": [
            {
                "type": "F4",
                "item": symbol,
                "values": {
                    "9201": "ACCOUNT-MUST-NOT-PERSIST",
                    "9203": order_no,
                    "9001": symbol,
                    "904": original_order_no,
                    "905": "12",
                    "907": "02",
                    "908": "101502",
                    "913": status,
                    "900": "2",
                    "8043": "USD",
                },
            }
        ],
    }


def test_partial_fill_survives_restart_and_duplicate_replay(tmp_path):
    db_path, cycle, _ = _submitted_reservation(tmp_path)
    payload = _f5_payload()

    first = replay_us_order_event_payloads(
        store=CapitalAllocationStore(db_path),
        cycle=cycle,
        payloads=[payload],
    )
    restarted = CapitalAllocationStore(db_path)
    restored = restarted.list_reservations(cycle.id)[0]
    duplicate = replay_us_order_event_payloads(
        store=restarted,
        cycle=cycle,
        payloads=[payload],
    )
    state = restarted.load_state(cycle=cycle, orderable_cash=3_900)

    assert first.updated_count == 1
    assert restored.status == "submitted"
    assert restored.filled_quantity == 1
    assert restored.last_broker_status == "부분체결"
    assert duplicate.duplicate_count == 1
    assert restarted.list_reservations(cycle.id)[0].filled_quantity == 1
    assert state.pending_symbols == frozenset({"NVDA"})


def test_partial_fill_then_confirmed_cancel_closes_pending_reservation(tmp_path):
    db_path, cycle, _ = _submitted_reservation(tmp_path)
    store = CapitalAllocationStore(db_path)

    summary = replay_us_order_event_payloads(
        store=store,
        cycle=cycle,
        payloads=[
            _f5_payload(),
            _f4_payload(
                order_no="cancel-order",
                original_order_no="original-order",
                status="취소완료",
            ),
        ],
    )
    reservation = CapitalAllocationStore(db_path).list_reservations(cycle.id)[0]
    state = CapitalAllocationStore(db_path).load_state(
        cycle=cycle,
        orderable_cash=3_900,
    )

    assert summary.updated_count == 2
    assert reservation.status == "filled"
    assert reservation.filled_quantity == 1
    assert reservation.last_broker_status == "취소완료"
    assert state.pending_symbols == frozenset()
    assert state.filled_tranches == {"NVDA": 1}


def test_full_fill_after_restart_marks_tranche_filled(tmp_path):
    db_path, cycle, _ = _submitted_reservation(tmp_path)
    payload = _f5_payload(
        status="체결완료",
        fill_quantity="2",
        unfilled_quantity="0",
    )

    summary = replay_us_order_event_payloads(
        store=CapitalAllocationStore(db_path),
        cycle=cycle,
        payloads=[payload],
    )
    duplicate = replay_us_order_event_payloads(
        store=CapitalAllocationStore(db_path),
        cycle=cycle,
        payloads=[payload],
    )
    reservation = CapitalAllocationStore(db_path).list_reservations(cycle.id)[0]

    assert summary.updated_count == 1
    assert duplicate.duplicate_count == 1
    assert reservation.status == "filled"
    assert reservation.filled_quantity == 2


def test_rejected_order_releases_unfilled_reservation(tmp_path):
    db_path, cycle, _ = _submitted_reservation(tmp_path)

    summary = replay_us_order_event_payloads(
        store=CapitalAllocationStore(db_path),
        cycle=cycle,
        payloads=[
            _f4_payload(
                order_no="original-order",
                original_order_no="000000000",
                status="무효주문",
            )
        ],
    )
    store = CapitalAllocationStore(db_path)
    reservation = store.list_reservations(cycle.id)[0]
    state = store.load_state(cycle=cycle, orderable_cash=4_000)

    assert summary.updated_count == 1
    assert reservation.status == "released"
    assert reservation.filled_quantity == 0
    assert state.open_symbols == frozenset()
    assert state.reserved_cash == 0


def test_unmatched_or_sell_event_does_not_change_buy_reservation(tmp_path):
    db_path, cycle, _ = _submitted_reservation(tmp_path)

    summary = replay_us_order_event_payloads(
        store=CapitalAllocationStore(db_path),
        cycle=cycle,
        payloads=[
            _f5_payload(order_no="different-order"),
            _f5_payload(side="01"),
        ],
    )
    reservation = CapitalAllocationStore(db_path).list_reservations(cycle.id)[0]

    assert summary.unmatched_count == 1
    assert summary.ignored_count == 1
    assert reservation.status == "submitted"
    assert reservation.filled_quantity == 0


def test_recovery_storage_excludes_account_and_raw_payload_values(tmp_path):
    marker = "ACCOUNT-MUST-NOT-PERSIST"
    db_path, cycle, _ = _submitted_reservation(tmp_path)
    replay_us_order_event_payloads(
        store=CapitalAllocationStore(db_path),
        cycle=cycle,
        payloads=[_f5_payload(account_marker=marker)],
    )

    connection = sqlite3.connect(db_path)
    try:
        event_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(us_capital_allocation_events)"
            ).fetchall()
        }
        persisted_values = [
            value
            for row in connection.execute(
                """
                SELECT event_key, tr_id, order_no, symbol, status
                FROM us_capital_allocation_events
                """
            ).fetchall()
            for value in row
        ]
    finally:
        connection.close()

    assert "account_no" not in event_columns
    assert "raw_payload" not in event_columns
    assert marker not in {str(value) for value in persisted_values}
