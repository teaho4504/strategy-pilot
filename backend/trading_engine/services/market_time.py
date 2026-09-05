from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
US_EASTERN = ZoneInfo("America/New_York")


class UsMarketSession(str, Enum):
    PREMARKET = "premarket"
    REGULAR = "regular"
    AFTERHOURS = "afterhours"
    CLOSED = "closed"


@dataclass(frozen=True)
class MarketTimeContext:
    utc: datetime
    kst: datetime
    us_eastern: datetime
    us_market_date: str
    us_session: UsMarketSession


def market_time_context(now: datetime | None = None) -> MarketTimeContext:
    utc_now = (now or datetime.now(ZoneInfo("UTC"))).astimezone(ZoneInfo("UTC"))
    kst_now = utc_now.astimezone(KST)
    eastern_now = utc_now.astimezone(US_EASTERN)
    return MarketTimeContext(
        utc=utc_now,
        kst=kst_now,
        us_eastern=eastern_now,
        us_market_date=eastern_now.date().isoformat(),
        us_session=classify_us_session(eastern_now),
    )


def classify_us_session(eastern_dt: datetime) -> UsMarketSession:
    if eastern_dt.weekday() >= 5:
        return UsMarketSession.CLOSED
    current = eastern_dt.time()
    if time(4, 0) <= current < time(9, 30):
        return UsMarketSession.PREMARKET
    if time(9, 30) <= current < time(16, 0):
        return UsMarketSession.REGULAR
    if time(16, 0) <= current < time(20, 0):
        return UsMarketSession.AFTERHOURS
    return UsMarketSession.CLOSED
