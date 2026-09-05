from __future__ import annotations

import pytest

from trading_engine.risk.capital_allocator import (
    CapitalAllocationPolicy,
    CapitalAllocationState,
    evaluate_capital_allocation,
    reserve_allocation,
)


def test_allocates_one_eighth_of_cycle_capital_per_tranche() -> None:
    state = CapitalAllocationState(cycle_capital=4_000, orderable_cash=4_000)

    decision = evaluate_capital_allocation(
        state=state,
        symbol="NVDA",
        reference_price=100,
    )

    assert decision.allowed is True
    assert decision.position_slot == 1
    assert decision.tranche == 1
    assert decision.symbol_budget == 1_000
    assert decision.tranche_budget == 500
    assert decision.quantity == 5
    assert decision.estimated_notional == 500


def test_reservation_prevents_duplicate_pending_order() -> None:
    state = CapitalAllocationState(cycle_capital=4_000, orderable_cash=4_000)
    first = evaluate_capital_allocation(state=state, symbol="NVDA", reference_price=100)
    reserved = reserve_allocation(state, first)

    duplicate = evaluate_capital_allocation(
        state=reserved,
        symbol="NVDA",
        reference_price=100,
    )

    assert duplicate.allowed is False
    assert "SYMBOL_ORDER_PENDING" in duplicate.blocked_reasons
    assert reserved.reserved_cash == 500


def test_second_tranche_requires_first_fill_and_no_pending_order() -> None:
    state = CapitalAllocationState(
        cycle_capital=4_000,
        orderable_cash=3_500,
        open_symbols=frozenset({"NVDA"}),
        filled_tranches={"NVDA": 1},
    )

    decision = evaluate_capital_allocation(
        state=state,
        symbol="NVDA",
        reference_price=100,
    )

    assert decision.allowed is True
    assert decision.tranche == 2
    assert decision.quantity == 5


def test_blocks_third_tranche() -> None:
    state = CapitalAllocationState(
        cycle_capital=4_000,
        orderable_cash=3_000,
        open_symbols=frozenset({"NVDA"}),
        filled_tranches={"NVDA": 2},
    )

    decision = evaluate_capital_allocation(
        state=state,
        symbol="NVDA",
        reference_price=100,
    )

    assert decision.allowed is False
    assert decision.blocked_reasons == ("SYMBOL_TRANCHE_LIMIT_REACHED",)


def test_blocks_fifth_distinct_symbol() -> None:
    state = CapitalAllocationState(
        cycle_capital=4_000,
        orderable_cash=2_000,
        open_symbols=frozenset({"AAPL", "MSFT", "NVDA", "TSLA"}),
    )

    decision = evaluate_capital_allocation(
        state=state,
        symbol="AMD",
        reference_price=100,
    )

    assert decision.allowed is False
    assert "MAX_SYMBOLS_REACHED" in decision.blocked_reasons


def test_zero_orderable_cash_pauses_new_entries() -> None:
    state = CapitalAllocationState(cycle_capital=4_000, orderable_cash=0)

    decision = evaluate_capital_allocation(
        state=state,
        symbol="NVDA",
        reference_price=100,
    )

    assert decision.allowed is False
    assert decision.pause_new_entries is True
    assert "ORDERABLE_CASH_DEPLETED" in decision.blocked_reasons


def test_sequential_reservations_use_remaining_cash() -> None:
    state = CapitalAllocationState(cycle_capital=4_000, orderable_cash=700)
    first = evaluate_capital_allocation(state=state, symbol="AAA", reference_price=100)
    state = reserve_allocation(state, first)
    second = evaluate_capital_allocation(state=state, symbol="BBB", reference_price=100)

    assert first.quantity == 5
    assert second.quantity == 2
    assert second.estimated_notional == 200
    assert second.remaining_cash == 0


def test_rejects_inconsistent_tranche_policy() -> None:
    with pytest.raises(ValueError, match="evenly split"):
        CapitalAllocationPolicy(tranches_per_symbol=2, tranche_fraction=0.4)
