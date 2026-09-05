from __future__ import annotations

from pathlib import Path
import json
import sqlite3

from trading_engine.domain.events import ConditionEvent, MarketDataEvent
from trading_engine.domain.models import StrategySignal
from trading_engine.services.market_time import market_time_context
from trading_engine.storage.migrations import SCHEMA
from trading_engine.strategies.us_day_trading import StrategyDecision


class SQLiteStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def record_condition_event(self, event: ConditionEvent) -> None:
        self.connection.execute(
            """
            INSERT INTO condition_events(event_type, condition_id, condition_name, symbol, symbol_name, occurred_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event.event_type.value, event.condition_id, event.condition_name, event.symbol, event.symbol_name, event.occurred_at.isoformat(), event.source),
        )
        self.connection.commit()

    def record_market_event(self, event: MarketDataEvent) -> None:
        self.connection.execute(
            """
            INSERT INTO market_events(symbol, last_price, change_rate, trade_volume, cumulative_volume, bid, ask, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event.symbol, event.last_price, event.change_rate, event.trade_volume, event.cumulative_volume, event.bid, event.ask, event.timestamp.isoformat()),
        )
        self.connection.commit()

    def record_signal(self, signal: StrategySignal) -> None:
        self.connection.execute(
            """
            INSERT INTO strategy_signals(signal_type, symbol, strategy_name, reason, score, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (signal.signal_type.value, signal.symbol, signal.strategy_name, signal.reason, signal.score, signal.created_at.isoformat()),
        )
        self.connection.commit()

    def record_risk_block(self, symbol: str, reason: str, created_at: str) -> None:
        self.connection.execute("INSERT INTO risk_blocks(symbol, reason, created_at) VALUES (?, ?, ?)", (symbol, reason, created_at))
        self.connection.commit()

    def record_us_strategy_decision(self, decision: StrategyDecision) -> None:
        time_context = market_time_context()
        self.connection.execute(
            """
            INSERT INTO us_strategy_decisions(
              strategy_id, symbol, exchange, ready, entry_price, stop_price,
              quantity, blocked_reasons, criteria_json, decided_at,
              decided_at_et, us_market_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.strategy_id,
                decision.symbol,
                decision.exchange,
                1 if decision.ready else 0,
                decision.entry_price,
                decision.stop_price,
                decision.quantity,
                ",".join(decision.blocked_reasons),
                json.dumps(
                    [
                        {"key": item.key, "passed": item.passed, "value": item.value, "reason": item.reason}
                        for item in decision.criteria
                    ],
                    ensure_ascii=False,
                ),
                time_context.utc.isoformat(),
                time_context.us_eastern.isoformat(),
                time_context.us_market_date,
            ),
        )
        self.connection.commit()

    def count_rows(self, table: str) -> int:
        row = self.connection.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
        return int(row["c"])
