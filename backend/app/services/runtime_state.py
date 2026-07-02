from datetime import datetime, timezone

_last_success_at: datetime | None = None
_last_error: str | None = None


def mark_success() -> None:
    global _last_success_at, _last_error
    _last_success_at = datetime.now(timezone.utc)
    _last_error = None


def mark_error(message: str) -> None:
    global _last_error
    _last_error = message


def last_success_at() -> str | None:
    return _last_success_at.isoformat() if _last_success_at else None


def last_error() -> str | None:
    return _last_error
