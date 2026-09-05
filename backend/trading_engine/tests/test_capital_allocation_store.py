from __future__ import annotations

import sqlite3

import pytest

from trading_engine.risk.allocation_store import CapitalAllocationStore
from trading_engine.risk.capital_allocator import (
    CapitalAllocationState,
    evaluate_capital_allocation,
)


def test_allocation_cycle_and_reservation_survive_restart(tmp_path) -> None:
    db_path = tmp_path / "allocation.sqlite3"
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-30",
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(cycle_capital=4_000, orderable_cash=4_000),
        symbol="NVDA",
        reference_price=100,
    )
    reservation = store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )
    store.mark_submitted(reservation.id, "safe-order-id")

    restarted = CapitalAllocationStore(db_path)
    restored_cycle = restarted.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-30",
        orderable_cash=3_500,
    )
    state = restarted.load_state(cycle=restored_cycle, orderable_cash=3_500)

    assert restored_cycle.id == cycle.id
    assert restored_cycle.cycle_capital == 4_000
    assert state.reserved_cash == 500
    assert state.open_symbols == frozenset({"NVDA"})
    assert state.pending_symbols == frozenset({"NVDA"})


def test_find_cycle_returns_only_matching_active_cycle(tmp_path) -> None:
    store = CapitalAllocationStore(tmp_path / "allocation.sqlite3")
    cycle = store.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-30",
        orderable_cash=4_000,
    )

    assert store.find_cycle(account_scope="profile-a", market_date="2026-07-30") == cycle
    assert store.find_cycle(account_scope="profile-b", market_date="2026-07-30") is None


def test_filled_reservation_counts_tranche_and_releases_reserved_cash(tmp_path) -> None:
    store = CapitalAllocationStore(tmp_path / "allocation.sqlite3")
    cycle = store.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-30",
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(cycle_capital=4_000, orderable_cash=4_000),
        symbol="NVDA",
        reference_price=100,
    )
    reservation = store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )
    store.mark_submitted(reservation.id, "safe-order-id")
    assert store.close_filled(reservation.id) is False
    store.mark_filled(reservation.id)

    state = store.load_state(cycle=cycle, orderable_cash=3_500)

    assert state.reserved_cash == 0
    assert state.filled_tranches == {"NVDA": 1}
    assert state.pending_symbols == frozenset()


def test_released_reservation_no_longer_uses_position_slot(tmp_path) -> None:
    store = CapitalAllocationStore(tmp_path / "allocation.sqlite3")
    cycle = store.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-30",
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(cycle_capital=4_000, orderable_cash=4_000),
        symbol="NVDA",
        reference_price=100,
    )
    reservation = store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )
    store.release(reservation.id)

    state = store.load_state(cycle=cycle, orderable_cash=4_000)

    assert state.open_symbols == frozenset()
    assert state.pending_symbols == frozenset()
    assert state.reserved_cash == 0


def test_duplicate_symbol_tranche_reservation_is_rejected(tmp_path) -> None:
    store = CapitalAllocationStore(tmp_path / "allocation.sqlite3")
    cycle = store.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-30",
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(cycle_capital=4_000, orderable_cash=4_000),
        symbol="NVDA",
        reference_price=100,
    )
    store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )

    with pytest.raises(ValueError, match="already reserved"):
        store.reserve(
            cycle=cycle,
            decision=decision,
            strategy="strategy-a",
            exchange="ND",
            reference_price=100,
        )


def test_new_market_date_closes_previous_cycle(tmp_path) -> None:
    store = CapitalAllocationStore(tmp_path / "allocation.sqlite3")
    first = store.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-30",
        orderable_cash=4_000,
    )
    second = store.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-31",
        orderable_cash=3_000,
    )

    assert second.id != first.id
    assert second.cycle_capital == 3_000


def test_existing_allocation_database_gets_recovery_columns(tmp_path) -> None:
    db_path = tmp_path / "legacy-allocation.sqlite3"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE us_capital_allocation_cycles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              account_scope TEXT NOT NULL,
              market_date TEXT NOT NULL,
              cycle_capital REAL NOT NULL,
              currency TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE us_capital_allocation_reservations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              cycle_id INTEGER NOT NULL,
              strategy TEXT NOT NULL,
              symbol TEXT NOT NULL,
              exchange TEXT NOT NULL,
              tranche INTEGER NOT NULL,
              quantity INTEGER NOT NULL,
              reference_price REAL NOT NULL,
              reserved_notional REAL NOT NULL,
              status TEXT NOT NULL,
              order_no TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            INSERT INTO us_capital_allocation_cycles
              VALUES (1, 'profile-a', '2026-07-30', 4000, 'USD', 'active', 'now', 'now');
            INSERT INTO us_capital_allocation_reservations
              VALUES (1, 1, 'strategy-a', 'NVDA', 'ND', 1, 2, 100, 200, 'submitted', 'order-a', 'now', 'now');
            """
        )
        connection.commit()
    finally:
        connection.close()

    reservation = CapitalAllocationStore(db_path).list_reservations(1)[0]

    assert reservation.filled_quantity == 0
    assert reservation.last_broker_status is None
    assert reservation.submitted_at == "now"
    assert reservation.last_reconciled_at is None
    assert reservation.reconcile_result is None
    assert reservation.reconcile_attempts == 0
    assert reservation.closed_at is None


def test_reconciliation_state_survives_restart(tmp_path) -> None:
    db_path = tmp_path / "allocation.sqlite3"
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-30",
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(cycle_capital=4_000, orderable_cash=4_000),
        symbol="NVDA",
        reference_price=100,
    )
    reservation = store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )
    store.mark_submitted(reservation.id, "safe-order-id")
    store.record_reconciliation_result(reservation.id, "unresolved")

    restored_store = CapitalAllocationStore(db_path)
    restored = restored_store.list_reservations(cycle.id)[0]

    assert restored.submitted_at is not None
    assert restored.last_reconciled_at is not None
    assert restored.reconcile_result == "unresolved"
    assert restored.reconcile_attempts == 1

    restored_store.record_reconciliation_result(
        reservation.id,
        "open_pending",
    )
    updated = CapitalAllocationStore(db_path).list_reservations(cycle.id)[0]
    assert updated.reconcile_result == "open_pending"
    assert updated.reconcile_attempts == 2

    with pytest.raises(ValueError, match="unsupported"):
        restored_store.record_reconciliation_result(
            reservation.id,
            "raw-broker-payload",
        )


def test_terminal_partial_fill_reconciliation_is_atomic_and_survives_restart(
    tmp_path,
) -> None:
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
        symbol="NVDA",
        reference_price=100,
        max_quantity=2,
    )
    reservation = store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )
    store.mark_submitted(reservation.id, "safe-order-id")

    store.resolve_submitted_reconciliation(
        reservation.id,
        result="canceled_confirmed",
        terminal_status="filled",
        filled_quantity=1,
        broker_status="부분체결 취소완료",
    )

    restarted = CapitalAllocationStore(db_path)
    restored = restarted.list_reservations(cycle.id)[0]
    state = restarted.load_state(cycle=cycle, orderable_cash=3_900)

    assert restored.status == "filled"
    assert restored.filled_quantity == 1
    assert restored.last_broker_status == "부분체결 취소완료"
    assert restored.reconcile_result == "canceled_confirmed"
    assert restored.reconcile_attempts == 1
    assert state.pending_symbols == frozenset()
    assert state.filled_tranches == {"NVDA": 1}


def test_closed_filled_reservation_releases_position_slot_after_restart(
    tmp_path,
) -> None:
    db_path = tmp_path / "allocation.sqlite3"
    store = CapitalAllocationStore(db_path)
    cycle = store.ensure_cycle(
        account_scope="profile-a",
        market_date="2026-07-31",
        orderable_cash=4_000,
    )
    decision = evaluate_capital_allocation(
        state=CapitalAllocationState(
            cycle_capital=4_000,
            orderable_cash=4_000,
        ),
        symbol="NVDA",
        reference_price=100,
        max_quantity=1,
    )
    reservation = store.reserve(
        cycle=cycle,
        decision=decision,
        strategy="strategy-a",
        exchange="ND",
        reference_price=100,
    )
    store.mark_submitted(reservation.id, "safe-order-id")
    store.mark_filled(reservation.id)

    assert store.close_filled(reservation.id) is True
    assert store.close_filled(reservation.id) is True

    restarted = CapitalAllocationStore(db_path)
    restored = restarted.list_reservations(cycle.id)[0]
    state = restarted.load_state(cycle=cycle, orderable_cash=4_000)

    assert restored.status == "closed"
    assert restored.closed_at is not None
    assert state.open_symbols == frozenset()
    assert state.filled_tranches == {}
    assert state.reserved_cash == 0
