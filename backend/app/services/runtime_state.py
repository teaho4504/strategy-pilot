from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RuntimeState:
    last_successful_refresh_at: Optional[str] = None
    last_error: Optional[str] = None


runtime_state = RuntimeState()


def mark_success() -> None:
    runtime_state.last_successful_refresh_at = datetime.now(timezone.utc).isoformat()
    runtime_state.last_error = None


def mark_error(message: str) -> None:
    runtime_state.last_error = message
