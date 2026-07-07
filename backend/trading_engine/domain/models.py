from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from trading_engine.domain.enums import FillSide, SignalType, WatchSource, WatchStatus
from trading_engine.domain.events import utc_now


@dataclass
class WatchItem:
    symbol: str
    symbol_name: str
    status: WatchStatus
    source: WatchSource
    condition_id: str | None = None
    condition_name: str | None = None
    first_seen_at: datetime = field(default_factory=utc_now)
    last_event_at: datetime = field(default_factory=utc_now)
    enter_count: int = 1


@dataclass
class MarketSnapshot:
    symbol: str
    last_price: int
    change_rate: float
    trade_volume: int
    cumulative_volume: int
    bid: int
    ask: int
    updated_at: datetime
    ticks: list[dict[str, object]] = field(default_factory=list)
    seconds_since_condition_entered: float | None = None


@dataclass(frozen=True)
class AccountState:
    cash: int = 10_000_000
    realized_pnl: int = 0
    unrealized_pnl: int = 0
    open_positions: int = 0
    daily_entry_count: int = 0
    daily_loss: int = 0


@dataclass(frozen=True)
class StrategySignal:
    signal_type: SignalType
    symbol: str
    strategy_name: str
    reason: str
    score: int = 0
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class Position:
    symbol: str
    symbol_name: str
    quantity: int
    average_price: int
    strategy_name: str
    condition_name: str
    opened_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class PaperFill:
    symbol: str
    symbol_name: str
    side: FillSide
    quantity: int
    price: int
    fee: int
    slippage: int
    realized_pnl: int
    reason: str
    strategy_name: str
    condition_name: str
    filled_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class DailyJournal:
    trade_date: str
    entries: int
    exits: int
    total_pnl: int
    win_rate: float
    average_pnl: float
    max_loss: int
    max_open_positions: int
    risk_blocks: int
    strategy_breakdown: dict[str, dict[str, float | int]]
