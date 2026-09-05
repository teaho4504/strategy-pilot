from __future__ import annotations

from pathlib import Path
import sqlite3

from app.core.time import now_iso
from app.schemas.market import UsConditionItem
from trading_engine.config import get_engine_settings


KIWOOM_CONDITION_STRATEGY_PREFIX = "kiwoom-condition-"


class KiwoomConditionStrategyService:
    """Persist the ON/OFF state for conditions authored in Kiwoom HTS."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path

    def sync(self, conditions: list[UsConditionItem]) -> None:
        timestamp = now_iso()
        with self._connect() as connection:
            for condition in conditions:
                connection.execute(
                    """
                    INSERT INTO us_kiwoom_condition_strategies(
                      condition_seq, condition_name, enabled, created_at, updated_at
                    ) VALUES (?, ?, 0, ?, ?)
                    ON CONFLICT(condition_seq) DO UPDATE SET
                      condition_name = excluded.condition_name,
                      updated_at = excluded.updated_at
                    """,
                    (condition.seq, condition.name, timestamp, timestamp),
                )
            connection.commit()

    def set_enabled(self, seq: str, enabled: bool) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE us_kiwoom_condition_strategies
                SET enabled = ?, updated_at = ?
                WHERE condition_seq = ?
                """,
                (int(enabled), now_iso(), seq),
            )
            connection.commit()
            return cursor.rowcount > 0

    def is_enabled(self, seq: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT enabled FROM us_kiwoom_condition_strategies WHERE condition_seq = ?",
                (seq,),
            ).fetchone()
        return bool(row and row["enabled"])

    def enabled_sequences(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT condition_seq FROM us_kiwoom_condition_strategies WHERE enabled = 1"
            ).fetchall()
        return {str(row["condition_seq"]) for row in rows}

    def stored_conditions(self) -> list[UsConditionItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT condition_seq, condition_name
                FROM us_kiwoom_condition_strategies
                ORDER BY condition_seq
                """
            ).fetchall()
        return [
            UsConditionItem(seq=str(row["condition_seq"]), name=str(row["condition_name"]))
            for row in rows
        ]

    def runtime_configs(self, conditions: list[UsConditionItem]) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "strategy": self.strategy_id(condition.seq),
                "name": condition.name,
                "condition_seq": condition.seq,
                "condition_name": condition.name,
                "tick_scope": "0",
                "bearish_count": 0,
                "entry_rule": "condition_direct",
                "target_profit_pct": 2.0,
                "stop_loss_pct": 2.0,
                "required_criteria": (
                    "strategy_session",
                    "condition_search_match",
                    "quote_price",
                ),
                "condition_direct_entry": True,
                "kiwoom_condition_strategy": True,
            }
            for condition in conditions
        )

    @staticmethod
    def strategy_id(seq: str) -> str:
        return f"{KIWOOM_CONDITION_STRATEGY_PREFIX}{seq}"

    @staticmethod
    def sequence_from_strategy(strategy: str) -> str | None:
        if not strategy.startswith(KIWOOM_CONDITION_STRATEGY_PREFIX):
            return None
        seq = strategy[len(KIWOOM_CONDITION_STRATEGY_PREFIX):].strip()
        return seq or None

    def _connect(self) -> sqlite3.Connection:
        path = self.db_path or get_engine_settings().db_path
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS us_kiwoom_condition_strategies (
              condition_seq TEXT PRIMARY KEY,
              condition_name TEXT NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
        return connection


kiwoom_condition_strategy_service = KiwoomConditionStrategyService()
