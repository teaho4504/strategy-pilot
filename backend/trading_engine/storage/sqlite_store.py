from __future__ import annotations

from pathlib import Path
import sqlite3

from trading_engine.domain.events import ConditionEvent, MarketDataEvent
from trading_engine.domain.models import DailyJournal, PaperFill, StrategySignal
from trading_engine.storage.migrations import SCHEMA


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

    def record_fill(self, fill: PaperFill) -> None:
        self.connection.execute(
            """
            INSERT INTO paper_fills(symbol, symbol_name, side, quantity, price, fee, slippage, realized_pnl, reason, strategy_name, condition_name, filled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fill.symbol,
                fill.symbol_name,
                fill.side.value,
                fill.quantity,
                fill.price,
                fill.fee,
                fill.slippage,
                fill.realized_pnl,
                fill.reason,
                fill.strategy_name,
                fill.condition_name,
                fill.filled_at.isoformat(),
            ),
        )
        self.connection.commit()

    def count_rows(self, table: str) -> int:
        row = self.connection.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
        return int(row["c"])

    def daily_journal(self, trade_date: str) -> DailyJournal:
        fills = self.connection.execute("SELECT * FROM paper_fills WHERE substr(filled_at, 1, 10) = ?", (trade_date,)).fetchall()
        risk_blocks = self.connection.execute("SELECT COUNT(*) AS c FROM risk_blocks WHERE substr(created_at, 1, 10) = ?", (trade_date,)).fetchone()
        entries = [row for row in fills if row["side"] == "buy"]
        exits = [row for row in fills if row["side"] == "sell"]
        pnls = [int(row["realized_pnl"]) for row in exits]
        wins = [pnl for pnl in pnls if pnl > 0]
        strategy_breakdown: dict[str, dict[str, float | int]] = {}
        for row in fills:
            item = strategy_breakdown.setdefault(row["strategy_name"], {"entries": 0, "exits": 0, "pnl": 0})
            if row["side"] == "buy":
                item["entries"] = int(item["entries"]) + 1
            if row["side"] == "sell":
                item["exits"] = int(item["exits"]) + 1
                item["pnl"] = int(item["pnl"]) + int(row["realized_pnl"])
        return DailyJournal(
            trade_date=trade_date,
            entries=len(entries),
            exits=len(exits),
            total_pnl=sum(pnls),
            win_rate=(len(wins) / len(pnls)) if pnls else 0.0,
            average_pnl=(sum(pnls) / len(pnls)) if pnls else 0.0,
            max_loss=min(pnls) if pnls else 0,
            max_open_positions=len(entries),
            risk_blocks=int(risk_blocks["c"]),
            strategy_breakdown=strategy_breakdown,
        )
