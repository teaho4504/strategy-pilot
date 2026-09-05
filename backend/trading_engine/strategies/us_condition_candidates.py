from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from trading_engine.domain.events import utc_now


US_COMMON_LIQUID_LONG = "US_COMMON_LIQUID_LONG"


class ConditionRegistrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class UsConditionDefinition:
    seq: str
    name: str
    tr_id: str = "usa20280"


@dataclass
class UsConditionCandidate:
    symbol: str
    exchange: str
    condition_seq: str
    condition_name: str
    entered_at: datetime = field(default_factory=utc_now)
    last_seen_at: datetime = field(default_factory=utc_now)
    enter_count: int = 1
    active: bool = True


class UsConditionCandidateManager:
    """Tracks Kiwoom condition-search candidates without performing API calls."""

    def __init__(self, required_condition_name: str = US_COMMON_LIQUID_LONG) -> None:
        self.required_condition_name = required_condition_name
        self.conditions: dict[str, UsConditionDefinition] = {}
        self.realtime_registered: set[str] = set()
        self.candidates: dict[tuple[str, str], UsConditionCandidate] = {}

    def load_condition_list(self, conditions: list[UsConditionDefinition]) -> None:
        self.conditions = {condition.seq: condition for condition in conditions}

    def selected_common_condition(self) -> UsConditionDefinition:
        for condition in self.conditions.values():
            if condition.name == self.required_condition_name:
                return condition
        raise ConditionRegistrationError(f"required condition is not available: {self.required_condition_name}")

    def register_realtime(self, seq: str) -> None:
        if not self.conditions:
            raise ConditionRegistrationError("usa20280 condition list must be loaded before usa20290 realtime registration")
        if seq not in self.conditions:
            raise ConditionRegistrationError(f"unknown condition sequence: {seq}")
        self.realtime_registered.add(seq)

    def clear_realtime(self, seq: str) -> None:
        self.realtime_registered.discard(seq)

    def handle_enter(self, *, seq: str, symbol: str, exchange: str, occurred_at: datetime | None = None) -> UsConditionCandidate:
        if seq not in self.realtime_registered:
            raise ConditionRegistrationError("condition realtime registration is required before accepting candidates")
        condition = self.conditions[seq]
        key = (exchange, symbol.upper())
        now = occurred_at or utc_now()
        existing = self.candidates.get(key)
        if existing is not None:
            existing.active = True
            existing.last_seen_at = now
            existing.enter_count += 1
            return existing
        candidate = UsConditionCandidate(
            symbol=symbol.upper(),
            exchange=exchange,
            condition_seq=seq,
            condition_name=condition.name,
            entered_at=now,
            last_seen_at=now,
        )
        self.candidates[key] = candidate
        return candidate

    def handle_exit(self, *, seq: str, symbol: str, exchange: str, occurred_at: datetime | None = None) -> UsConditionCandidate | None:
        key = (exchange, symbol.upper())
        candidate = self.candidates.get(key)
        if candidate is None:
            return None
        candidate.active = False
        candidate.last_seen_at = occurred_at or utc_now()
        return candidate

    def active_candidates(self) -> list[UsConditionCandidate]:
        return sorted(
            [candidate for candidate in self.candidates.values() if candidate.active],
            key=lambda item: item.last_seen_at,
            reverse=True,
        )
