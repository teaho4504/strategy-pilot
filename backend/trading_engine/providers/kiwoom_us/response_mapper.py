from __future__ import annotations

from typing import Any

from trading_engine.providers.kiwoom_us.schemas import (
    UsAccountBalance,
    UsConditionSearchResult,
    UsDailyAccountReturn,
    UsDailyAccountReturnRow,
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


def map_daily_account_return_response(raw: dict[str, Any]) -> UsDailyAccountReturn:
    _required_text(raw, "return_code")
    _required_text(raw, "return_msg")
    result_list = raw.get("result_lsit")
    if result_list is None:
        result_list = raw.get("result_list")
    if result_list is None:
        result_list = []
    if not isinstance(result_list, list):
        raise UsMappingError("field must be a list: result_lsit/result_list")
    rows = []
    known_row_fields = {
        "wo_base_dt",
        "wo_stk_evlta",
        "wo_pl_amt",
        "wo_dvid_amt",
        "wo_cmsn_tax",
        "wo_acum_pl_amt",
        "wo_pymn_amt",
        "wo_dast",
        "wo_dly_amt",
        "wo_sell_amt",
        "wo_buy_amt",
        "wo_prft_rt",
        "wo_frgn_stk_outq_amt",
        "wo_frgn_stk_inq_amt",
        "wo_ina_amt",
        "wo_exrt",
        "wo_total_cnt",
        "wo_rnum",
        "base_dt",
        "stk_evlta",
        "pl_amt",
        "dvid_amt",
        "cmsn_tax",
        "acum_pl_amt",
        "pymn_amt",
        "dast",
        "dly_amt",
        "sell_amt",
        "buy_amt",
        "prft_rt",
        "frgn_stk_outq_amt",
        "frgn_stk_inq_amt",
        "ina_amt",
        "exrt",
    }
    for item in result_list:
        if not isinstance(item, dict):
            raise UsMappingError("result_list item must be an object")
        rows.append(
            UsDailyAccountReturnRow(
                base_dt=_optional_first_text(item, "wo_base_dt", "base_dt"),
                stk_evlta=_optional_first_text(item, "wo_stk_evlta", "stk_evlta"),
                pl_amt=_optional_first_text(item, "wo_pl_amt", "pl_amt"),
                dvid_amt=_optional_first_text(item, "wo_dvid_amt", "dvid_amt"),
                cmsn_tax=_optional_first_text(item, "wo_cmsn_tax", "cmsn_tax"),
                acum_pl_amt=_optional_first_text(item, "wo_acum_pl_amt", "acum_pl_amt"),
                pymn_amt=_optional_first_text(item, "wo_pymn_amt", "pymn_amt"),
                dast=_optional_first_text(item, "wo_dast", "dast"),
                dly_amt=_optional_first_text(item, "wo_dly_amt", "dly_amt"),
                sell_amt=_optional_first_text(item, "wo_sell_amt", "sell_amt"),
                buy_amt=_optional_first_text(item, "wo_buy_amt", "buy_amt"),
                prft_rt=_optional_first_text(item, "wo_prft_rt", "prft_rt"),
                frgn_stk_outq_amt=_optional_first_text(item, "wo_frgn_stk_outq_amt", "frgn_stk_outq_amt"),
                frgn_stk_inq_amt=_optional_first_text(item, "wo_frgn_stk_inq_amt", "frgn_stk_inq_amt"),
                ina_amt=_optional_first_text(item, "wo_ina_amt", "ina_amt"),
                exrt=_optional_first_text(item, "wo_exrt", "exrt"),
                unknown_fields=_unknown(item, known_row_fields),
            )
        )
    return UsDailyAccountReturn(
        tr_id="usa21670",
        rows=rows,
        unknown_fields=_unknown(raw, {"return_code", "return_msg", "result_lsit", "result_list"}),
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


def _optional_text(raw: dict[str, Any], key: str) -> str | None:
    value = raw.get(key)
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def _optional_first_text(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _optional_text(raw, key)
        if value is not None:
            return value
    return None


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
