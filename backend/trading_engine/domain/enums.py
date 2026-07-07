from __future__ import annotations

from enum import Enum


class EngineMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class ConditionEventType(str, Enum):
    ENTERED = "condition_entered"
    EXITED = "condition_exited"
    SNAPSHOT = "condition_snapshot"


class WatchStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    EXITED = "exited"
    COOLDOWN = "cooldown"
    BLOCKED = "blocked"


class WatchSource(str, Enum):
    MANUAL = "manual"
    CONDITION = "condition"


class SignalType(str, Enum):
    NO_ACTION = "no_action"
    PAPER_BUY_CANDIDATE = "paper_buy_candidate"
    PAPER_SELL_CANDIDATE = "paper_sell_candidate"
    BLOCK = "block"
    OBSERVE = "observe"


class FillSide(str, Enum):
    BUY = "buy"
    SELL = "sell"
