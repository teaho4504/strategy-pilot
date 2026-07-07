from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trading_engine.config import EngineSettings
from trading_engine.domain.enums import SignalType
from trading_engine.domain.models import AccountState, RiskDecision, StrategySignal


class RiskManager:
    def __init__(self, settings: EngineSettings) -> None:
        self.settings = settings
        self.last_entry_at: dict[str, datetime] = {}
        self.block_count = 0

    def check_entry(self, signal: StrategySignal, account_state: AccountState, entry_amount: int) -> RiskDecision:
        if signal.signal_type != SignalType.PAPER_BUY_CANDIDATE:
            return RiskDecision(True, "not an entry signal")
        if self.settings.kill_switch:
            return self._block("kill switch enabled")
        if self.settings.strategy_paused:
            return self._block("strategy paused")
        if account_state.daily_loss >= self.settings.daily_max_loss:
            return self._block("daily max loss reached")
        if entry_amount > self.settings.per_symbol_max_entry_amount:
            return self._block("per-symbol amount limit exceeded")
        if account_state.open_positions >= self.settings.max_open_positions:
            return self._block("max open positions reached")
        if account_state.daily_entry_count >= self.settings.max_daily_entries:
            return self._block("daily entry limit reached")
        last_entry = self.last_entry_at.get(signal.symbol)
        if last_entry and datetime.now(timezone.utc) - last_entry < timedelta(seconds=self.settings.reentry_cooldown_seconds):
            return self._block("re-entry cooldown active")
        return RiskDecision(True, "allowed")

    def mark_entry(self, symbol: str) -> None:
        self.last_entry_at[symbol] = datetime.now(timezone.utc)

    def _block(self, reason: str) -> RiskDecision:
        self.block_count += 1
        return RiskDecision(False, reason)
