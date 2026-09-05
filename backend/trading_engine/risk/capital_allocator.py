from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import floor


@dataclass(frozen=True, slots=True)
class CapitalAllocationPolicy:
    max_symbols: int = 4
    tranches_per_symbol: int = 2
    tranche_fraction: float = 0.5

    def __post_init__(self) -> None:
        if self.max_symbols <= 0:
            raise ValueError("max_symbols must be positive")
        if self.tranches_per_symbol <= 0:
            raise ValueError("tranches_per_symbol must be positive")
        expected_fraction = 1 / self.tranches_per_symbol
        if abs(self.tranche_fraction - expected_fraction) > 1e-9:
            raise ValueError("tranche_fraction must evenly split the symbol budget")


@dataclass(frozen=True, slots=True)
class CapitalAllocationState:
    cycle_capital: float
    orderable_cash: float
    reserved_cash: float = 0.0
    open_symbols: frozenset[str] = field(default_factory=frozenset)
    filled_tranches: dict[str, int] = field(default_factory=dict)
    pending_symbols: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.cycle_capital < 0 or self.orderable_cash < 0 or self.reserved_cash < 0:
            raise ValueError("capital values cannot be negative")

    @property
    def available_cash(self) -> float:
        return max(0.0, self.orderable_cash - self.reserved_cash)


@dataclass(frozen=True, slots=True)
class CapitalAllocationDecision:
    allowed: bool
    symbol: str
    tranche: int | None
    position_slot: int | None
    quantity: int
    symbol_budget: float
    tranche_budget: float
    estimated_notional: float
    available_cash: float
    remaining_cash: float
    pause_new_entries: bool
    blocked_reasons: tuple[str, ...]


def evaluate_capital_allocation(
    *,
    state: CapitalAllocationState,
    symbol: str,
    reference_price: float,
    policy: CapitalAllocationPolicy | None = None,
    max_quantity: int | None = None,
) -> CapitalAllocationDecision:
    active_policy = policy or CapitalAllocationPolicy()
    clean_symbol = _normalize_symbol(symbol)
    available_cash = state.available_cash
    reasons: list[str] = []

    if not clean_symbol:
        reasons.append("SYMBOL_REQUIRED")
    if reference_price <= 0:
        reasons.append("REFERENCE_PRICE_REQUIRED")
    if available_cash <= 0:
        reasons.append("ORDERABLE_CASH_DEPLETED")
    if clean_symbol in state.pending_symbols:
        reasons.append("SYMBOL_ORDER_PENDING")

    completed_tranches = max(0, state.filled_tranches.get(clean_symbol, 0))
    if completed_tranches >= active_policy.tranches_per_symbol:
        reasons.append("SYMBOL_TRANCHE_LIMIT_REACHED")

    is_open_symbol = clean_symbol in state.open_symbols or completed_tranches > 0
    if not is_open_symbol and len(state.open_symbols) >= active_policy.max_symbols:
        reasons.append("MAX_SYMBOLS_REACHED")

    symbol_budget = state.cycle_capital / active_policy.max_symbols
    tranche_budget = symbol_budget * active_policy.tranche_fraction
    spendable = min(tranche_budget, available_cash)
    quantity = floor(spendable / reference_price) if reference_price > 0 else 0
    if max_quantity is not None:
        quantity = min(quantity, max(0, max_quantity))
    if quantity <= 0 and reference_price > 0 and available_cash > 0:
        reasons.append("INSUFFICIENT_CASH_FOR_ONE_SHARE")

    estimated_notional = round(quantity * reference_price, 4)
    remaining_cash = round(max(0.0, available_cash - estimated_notional), 4)
    allowed = not reasons
    position_slot = None
    if allowed:
        position_slot = (
            sorted(state.open_symbols).index(clean_symbol) + 1
            if clean_symbol in state.open_symbols
            else len(state.open_symbols) + 1
        )

    return CapitalAllocationDecision(
        allowed=allowed,
        symbol=clean_symbol,
        tranche=completed_tranches + 1 if allowed else None,
        position_slot=position_slot,
        quantity=quantity if allowed else 0,
        symbol_budget=round(symbol_budget, 4),
        tranche_budget=round(tranche_budget, 4),
        estimated_notional=estimated_notional if allowed else 0.0,
        available_cash=round(available_cash, 4),
        remaining_cash=remaining_cash if allowed else round(available_cash, 4),
        pause_new_entries=available_cash <= 0,
        blocked_reasons=tuple(reasons),
    )


def reserve_allocation(
    state: CapitalAllocationState,
    decision: CapitalAllocationDecision,
) -> CapitalAllocationState:
    if not decision.allowed:
        raise ValueError("cannot reserve a blocked allocation")
    return replace(
        state,
        reserved_cash=round(state.reserved_cash + decision.estimated_notional, 4),
        open_symbols=state.open_symbols | {decision.symbol},
        pending_symbols=state.pending_symbols | {decision.symbol},
    )


def _normalize_symbol(value: str) -> str:
    return "".join(
        character
        for character in str(value).upper().strip()
        if character.isalnum() or character in {".", "-"}
    )[:12]
