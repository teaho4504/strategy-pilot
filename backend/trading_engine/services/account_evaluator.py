from __future__ import annotations

from trading_engine.services.paper_broker import PaperBroker


class AccountEvaluator:
    def __init__(self, broker: PaperBroker) -> None:
        self.broker = broker

    def total_equity(self, last_prices: dict[str, int]) -> int:
        position_value = sum(position.quantity * last_prices.get(symbol, position.average_price) for symbol, position in self.broker.positions.items())
        return self.broker.cash + position_value
