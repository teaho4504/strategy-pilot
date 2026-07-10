from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UsKiwoomRequest:
    tr_id: str
    endpoint: str
    method: str
    body: dict[str, Any] = field(default_factory=dict)
    stream: bool = False
    read_only: bool = True


@dataclass(frozen=True)
class UsReadOnlyTrRequest:
    tr_id: str
    endpoint: str
    method: str
    headers: dict[str, str]
    body: dict[str, Any] = field(default_factory=dict)
    read_only: bool = True


@dataclass(frozen=True)
class UsReadOnlyTrResponse:
    tr_id: str
    return_code: str
    return_msg: str
    data: dict[str, Any] = field(default_factory=dict)
    unknown_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UsConditionSearchRequest:
    seq: str
    realtime: bool = False
    cont_yn: str | None = None
    next_key: str | None = None


@dataclass(frozen=True)
class UsConditionSearchResult:
    condition_id: str
    condition_name: str
    symbols: list[str] = field(default_factory=list)
    unknown_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UsAccountBalance:
    tr_id: str
    currency: str | None = None
    cash: str | None = None
    orderable_cash: str | None = None
    valuation_amount: str | None = None
    unknown_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UsProfitLoss:
    tr_id: str
    realized_profit_loss: str | None = None
    profit_loss_rate: str | None = None
    unknown_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UsRealtimeSymbol:
    symbol: str
    exchange: str
    country: str = "US"

    def to_item(self) -> dict[str, str]:
        return {"jmcode": self.symbol, "stex_tp": self.exchange}


@dataclass(frozen=True)
class UsRealtimeRegistration:
    tr_id: str
    symbols: list[UsRealtimeSymbol]
    group_no: str = "1"
    refresh: str = "1"

    def to_packet(self) -> dict[str, Any]:
        return {
            "trnm": "REG",
            "grp_no": self.group_no,
            "refresh": self.refresh,
            "data": [{"item": [symbol.to_item() for symbol in self.symbols], "type": [self.tr_id]}],
        }
