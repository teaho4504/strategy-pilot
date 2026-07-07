from __future__ import annotations

from trading_engine.domain.enums import FillSide
from trading_engine.domain.models import AccountState, PaperFill, Position, StrategySignal, WatchItem


class PaperBroker:
    def __init__(self, starting_cash: int = 10_000_000, fee_rate: float = 0.00015, slippage_bps: int = 2) -> None:
        self.cash = starting_cash
        self.fee_rate = fee_rate
        self.slippage_bps = slippage_bps
        self.positions: dict[str, Position] = {}
        self.fills: list[PaperFill] = []
        self.realized_pnl = 0
        self.order_api_call_count = 0

    def account_state(self) -> AccountState:
        return AccountState(
            cash=self.cash,
            realized_pnl=self.realized_pnl,
            open_positions=len(self.positions),
            daily_entry_count=sum(1 for fill in self.fills if fill.side == FillSide.BUY),
            daily_loss=max(0, -self.realized_pnl),
        )

    def paper_buy(self, watch_item: WatchItem, signal: StrategySignal, price: int, amount: int) -> PaperFill:
        execution_price = self._buy_price(price)
        quantity = max(1, amount // execution_price)
        gross = execution_price * quantity
        fee = int(gross * self.fee_rate)
        self.cash -= gross + fee
        self.positions[watch_item.symbol] = Position(
            symbol=watch_item.symbol,
            symbol_name=watch_item.symbol_name,
            quantity=quantity,
            average_price=execution_price,
            strategy_name=signal.strategy_name,
            condition_name=watch_item.condition_name or "unknown",
        )
        fill = PaperFill(
            symbol=watch_item.symbol,
            symbol_name=watch_item.symbol_name,
            side=FillSide.BUY,
            quantity=quantity,
            price=execution_price,
            fee=fee,
            slippage=execution_price - price,
            realized_pnl=0,
            reason=signal.reason,
            strategy_name=signal.strategy_name,
            condition_name=watch_item.condition_name or "unknown",
        )
        self.fills.append(fill)
        return fill

    def paper_sell(self, symbol: str, price: int, reason: str) -> PaperFill | None:
        position = self.positions.pop(symbol, None)
        if position is None:
            return None
        execution_price = self._sell_price(price)
        gross = execution_price * position.quantity
        fee = int(gross * self.fee_rate)
        pnl = (execution_price - position.average_price) * position.quantity - fee
        self.cash += gross - fee
        self.realized_pnl += pnl
        fill = PaperFill(
            symbol=position.symbol,
            symbol_name=position.symbol_name,
            side=FillSide.SELL,
            quantity=position.quantity,
            price=execution_price,
            fee=fee,
            slippage=price - execution_price,
            realized_pnl=pnl,
            reason=reason,
            strategy_name=position.strategy_name,
            condition_name=position.condition_name,
        )
        self.fills.append(fill)
        return fill

    def _buy_price(self, price: int) -> int:
        return int(price * (1 + self.slippage_bps / 10_000))

    def _sell_price(self, price: int) -> int:
        return int(price * (1 - self.slippage_bps / 10_000))
