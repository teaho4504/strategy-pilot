from __future__ import annotations

from trading_engine.domain.enums import SignalType, WatchStatus
from trading_engine.domain.models import AccountState, MarketSnapshot, StrategySignal, WatchItem


class SimpleConditionStrategy:
    def __init__(self, name: str = "조건검색 거래대금 Paper 전략") -> None:
        self.name = name

    def evaluate(self, watch_item: WatchItem, market_snapshot: MarketSnapshot, account_state: AccountState) -> StrategySignal:
        spread = market_snapshot.ask - market_snapshot.bid
        spread_pct = spread / market_snapshot.last_price * 100 if market_snapshot.last_price else 999
        if watch_item.status not in {WatchStatus.CANDIDATE, WatchStatus.ACTIVE}:
            return StrategySignal(SignalType.OBSERVE, watch_item.symbol, self.name, "watch item is not active")
        if account_state.open_positions > 0:
            return StrategySignal(SignalType.NO_ACTION, watch_item.symbol, self.name, "position already open")
        if market_snapshot.trade_volume >= 50_000 and 0.5 <= market_snapshot.change_rate <= 8.0 and spread_pct <= 0.3:
            return StrategySignal(
                SignalType.PAPER_BUY_CANDIDATE,
                watch_item.symbol,
                self.name,
                "condition entered, volume and spread checks passed",
                score=72,
            )
        return StrategySignal(SignalType.OBSERVE, watch_item.symbol, self.name, "waiting for volume/change/spread criteria")
