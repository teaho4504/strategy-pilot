from __future__ import annotations

from typing import Any

from trading_engine.providers.kiwoom_us.schemas import (
    UsAccountBalance,
    UsConditionSearchResult,
    UsProfitLoss,
    UsReadOnlyTrResponse,
)


class UsMappingError(ValueError):
    pass


_MISSING = object()


def map_readonly_response(tr_id: str, raw: dict[str, Any]) -> UsReadOnlyTrResponse:
    return_code = _required_text(raw, "return_code")
    return_msg = _required_text(raw, "return_msg")
    known = {"return_code", "return_msg"}
    return UsReadOnlyTrResponse(
        tr_id=tr_id,
        return_code=return_code,
        return_msg=return_msg,
        data={key: value for key, value in raw.items() if key not in known},
        unknown_fields={key: value for key, value in raw.items() if key not in known},
    )


def map_condition_search_response(raw: dict[str, Any]) -> UsConditionSearchResult:
    condition_id = _first_text(raw, "seq", "condition_id")
    condition_name = _first_text(raw, "name", "condition_name", default="US condition")
    symbols = _symbol_list(raw)
    return UsConditionSearchResult(
        condition_id=condition_id,
        condition_name=condition_name,
        symbols=symbols,
        unknown_fields=_unknown(raw, {"seq", "condition_id", "name", "condition_name", "items", "list", "symbols"}),
    )


def map_account_balance_response(tr_id: str, raw: dict[str, Any]) -> UsAccountBalance:
    _required_text(raw, "return_code")
    _required_text(raw, "return_msg")
    return UsAccountBalance(
        tr_id=tr_id,
        currency=_first_text(raw, "crnc_cd", "currency", default=None),
        cash=_first_text(raw, "frcr_dncl_amt_1", "krw_entra", "cash", default=None),
        orderable_cash=_first_text(raw, "ord_alow_amt", "ord_psbl_amt", "orderable_cash", default=None),
        valuation_amount=_first_text(raw, "evlt_amt", "tot_evlt_amt", "valuation_amount", default=None),
        unknown_fields=_unknown(raw, {"return_code", "return_msg", "crnc_cd", "currency", "frcr_dncl_amt_1", "krw_entra", "cash", "ord_alow_amt", "ord_psbl_amt", "orderable_cash", "evlt_amt", "tot_evlt_amt", "valuation_amount"}),
    )


def map_profit_loss_response(tr_id: str, raw: dict[str, Any]) -> UsProfitLoss:
    _required_text(raw, "return_code")
    _required_text(raw, "return_msg")
    return UsProfitLoss(
        tr_id=tr_id,
        realized_profit_loss=_first_text(raw, "rlzt_pl", "tdy_rlzt_pl", "realized_profit_loss", default=None),
        profit_loss_rate=_first_text(raw, "pl_rt", "prft_rt", "profit_loss_rate", default=None),
        unknown_fields=_unknown(raw, {"return_code", "return_msg", "rlzt_pl", "tdy_rlzt_pl", "realized_profit_loss", "pl_rt", "prft_rt", "profit_loss_rate"}),
    )


def _required_text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if value is None or not str(value).strip():
        raise UsMappingError(f"missing required field: {key}")
    return str(value).strip()


def _first_text(raw: dict[str, Any], *keys: str, default: str | None | object = _MISSING) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    if default is not _MISSING:
        return default
    raise UsMappingError(f"missing required field: one of {keys}")


def _symbol_list(raw: dict[str, Any]) -> list[str]:
    source = raw.get("symbols")
    if source is None:
        source = raw.get("items")
    if source is None:
        source = raw.get("list")
    if source is None:
        return []
    if not isinstance(source, list):
        raise UsMappingError("field must be a list: symbols/items/list")
    symbols: list[str] = []
    for item in source:
        if isinstance(item, str) and item.strip():
            symbols.append(item.strip())
        elif isinstance(item, dict):
            symbol = item.get("jmcode") or item.get("stk_cd") or item.get("symbol")
            if symbol is not None and str(symbol).strip():
                symbols.append(str(symbol).strip())
    return symbols


def _unknown(raw: dict[str, Any], known: set[str]) -> dict[str, Any]:
    return {key: value for key, value in raw.items() if key not in known}
