from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class EngineSettings:
    mode: str = "paper"
    order_enabled: bool = False
    live_provider_enabled: bool = False
    db_path: Path = Path("backend/data/trading_engine.sqlite3")
    tick_window: int = 20
    daily_max_loss: int = 300_000
    per_symbol_max_entry_amount: int = 1_000_000
    max_open_positions: int = 3
    reentry_cooldown_seconds: int = 300
    max_daily_entries: int = 10
    kill_switch: bool = False
    strategy_paused: bool = False


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_engine_settings() -> EngineSettings:
    return EngineSettings(
        mode=os.getenv("TRADING_ENGINE_MODE", "paper").strip().lower() or "paper",
        order_enabled=env_bool("TRADING_ENGINE_ORDER_ENABLED", False),
        live_provider_enabled=env_bool("TRADING_ENGINE_LIVE_PROVIDER_ENABLED", False),
        db_path=Path(os.getenv("TRADING_ENGINE_DB_PATH", "backend/data/trading_engine.sqlite3")),
        kill_switch=env_bool("TRADING_ENGINE_KILL_SWITCH", False),
        strategy_paused=env_bool("TRADING_ENGINE_STRATEGY_PAUSED", False),
    )
