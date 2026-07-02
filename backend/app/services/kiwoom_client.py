from dataclasses import dataclass
import logging
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.services.token_manager import token_manager

logger = logging.getLogger(__name__)


class KiwoomClientError(RuntimeError):
    pass


class KiwoomConfigurationError(KiwoomClientError):
    pass


class KiwoomApiError(KiwoomClientError):
    pass


@dataclass(frozen=True)
class KiwoomTrSpec:
    api_id: str
    name: str
    service_uri: str
    default_payload: dict[str, Any]
    list_key: str | None = None
    doc_note: str = ""


@dataclass
class KiwoomResponse:
    api_id: str
    body: dict[str, Any]
    cont_yn: str
    next_key: str


TR_SPECS: dict[str, KiwoomTrSpec] = {
    # Official Kiwoom REST API guide, domestic stock account jobTpCode=08.
    "ka00001": KiwoomTrSpec("ka00001", "계좌번호조회", "/api/dostk/acnt", {}),
    "ka10085": KiwoomTrSpec("ka10085", "계좌수익률요청", "/api/dostk/acnt", {"stex_tp": "0"}, "acnt_prft_rt"),
    "kt00001": KiwoomTrSpec("kt00001", "예수금상세현황요청", "/api/dostk/acnt", {"qry_tp": "3"}),
    "kt00004": KiwoomTrSpec("kt00004", "계좌평가현황요청", "/api/dostk/acnt", {"qry_tp": "0", "dmst_stex_tp": "KRX"}, "stk_acnt_evlt_prst"),
    "kt00005": KiwoomTrSpec("kt00005", "체결잔고요청", "/api/dostk/acnt", {"dmst_stex_tp": "KRX"}, "stk_cntr_remn"),
    # Official Kiwoom REST API guide, domestic stock info jobTpCode=01.
    "ka10001": KiwoomTrSpec("ka10001", "주식기본정보요청", "/api/dostk/stkinfo", {"stk_cd": "005930"}),
}


class KiwoomClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def request_tr(
        self,
        api_id: str,
        payload: dict[str, Any],
        cont_yn: str = "N",
        next_key: str = "",
    ) -> KiwoomResponse:
        spec = self._spec(api_id)
        request_payload = {**spec.default_payload, **payload}

        if self.settings.kiwoom_mode != "live":
            logger.info("Kiwoom mock TR response api_id=%s payload=%s", api_id, self._mask(request_payload))
            return KiwoomResponse(api_id=api_id, body=self._mock_tr_response(api_id, request_payload), cont_yn="N", next_key="")

        if not self.settings.kiwoom_configured:
            missing = ", ".join(self.settings.missing_kiwoom_env)
            raise KiwoomConfigurationError(f"Kiwoom live mode requires backend credentials: {missing}")

        token = await token_manager.get_access_token()
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": api_id,
        }
        url = f"{self.settings.kiwoom_base_url}{spec.service_uri}"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(url, json=request_payload, headers=headers)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            raise KiwoomApiError(f"Kiwoom TR {api_id} HTTP error: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise KiwoomApiError(f"Kiwoom TR {api_id} network error: {exc}") from exc
        except ValueError as exc:
            raise KiwoomApiError(f"Kiwoom TR {api_id} response was not JSON") from exc

        if not isinstance(body, dict):
            raise KiwoomApiError(f"Kiwoom TR {api_id} returned non-object JSON")

        return_code = body.get("return_code")
        if return_code not in (None, 0, "0"):
            message = body.get("return_msg") or "unknown Kiwoom error"
            raise KiwoomApiError(f"Kiwoom TR {api_id} failed: {message}")

        response_cont_yn = response.headers.get("cont-yn", "N") or "N"
        response_next_key = response.headers.get("next-key", "") or ""
        logger.info(
            "Kiwoom TR success api_id=%s cont_yn=%s has_next_key=%s body_keys=%s",
            api_id,
            response_cont_yn,
            bool(response_next_key),
            sorted(body.keys()),
        )
        return KiwoomResponse(api_id=api_id, body=body, cont_yn=response_cont_yn, next_key=response_next_key)

    async def request_tr_all(self, api_id: str, payload: dict[str, Any]) -> KiwoomResponse:
        spec = self._spec(api_id)
        first = await self.request_tr(api_id, payload)
        if not spec.list_key:
            return first

        items = list(first.body.get(spec.list_key) or [])
        current = first
        while current.cont_yn == "Y" and current.next_key:
            current = await self.request_tr(api_id, payload, cont_yn="Y", next_key=current.next_key)
            items.extend(current.body.get(spec.list_key) or [])

        merged = dict(first.body)
        merged[spec.list_key] = items
        return KiwoomResponse(api_id=api_id, body=merged, cont_yn=current.cont_yn, next_key=current.next_key)

    @staticmethod
    def _spec(api_id: str) -> KiwoomTrSpec:
        try:
            return TR_SPECS[api_id]
        except KeyError as exc:
            raise KiwoomConfigurationError(f"Unsupported Kiwoom TR: {api_id}") from exc

    @staticmethod
    def _mask(payload: dict[str, Any]) -> dict[str, Any]:
        masked = dict(payload)
        for key in ("token", "appkey", "secretkey", "authorization", "Authorization"):
            if key in masked:
                masked[key] = "***"
        return masked

    @staticmethod
    def _mock_tr_response(api_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if api_id == "ka00001":
            return {"acctNo": "1234567890", "return_code": 0, "return_msg": "mock"}
        if api_id == "kt00001":
            return {"entr": "00000018420000", "ord_alow_amt": "00000012550000", "pymn_alow_amt": "00000011230000", "return_code": 0, "return_msg": "mock"}
        if api_id == "kt00004":
            return {
                "entr": "00000018420000",
                "aset_evlt_amt": "00000052184300",
                "prsm_dpst_aset_amt": "00000052184300",
                "tdy_lspft": "0000000312500",
                "tdy_lspft_rt": "0.61",
                "lspft": "0000002184300",
                "stk_acnt_evlt_prst": [
                    {"stk_cd": "A005930", "stk_nm": "삼성전자", "rmnd_qty": "000000000020", "avg_prc": "000000071350", "cur_prc": "000000071800", "evlt_amt": "000001436000", "pl_amt": "000000009000", "pl_rt": "0.6307", "pur_amt": "000001427000"},
                    {"stk_cd": "A000660", "stk_nm": "SK하이닉스", "rmnd_qty": "000000000004", "avg_prc": "000000195200", "cur_prc": "000000198500", "evlt_amt": "000000794000", "pl_amt": "000000013200", "pl_rt": "1.6906", "pur_amt": "000000780800"},
                ],
                "return_code": 0,
                "return_msg": "mock",
            }
        if api_id == "kt00005":
            return {
                "entr": "00000018420000",
                "pymn_alow_amt": "00000011230000",
                "ord_alowa": "00000012550000",
                "evlt_amt_tot": "000002230000",
                "tot_pl_tot": "000000022200",
                "tot_pl_rt": "1.0050",
                "stk_cntr_remn": [
                    {"stk_cd": "A005930", "stk_nm": "삼성전자", "cur_qty": "000000000020", "cur_prc": "000000071800", "buy_uv": "000000071350", "pur_amt": "000001427000", "evlt_amt": "000001436000", "evltv_prft": "000000009000", "pl_rt": "0.6307"},
                    {"stk_cd": "A000660", "stk_nm": "SK하이닉스", "cur_qty": "000000000004", "cur_prc": "000000198500", "buy_uv": "000000195200", "pur_amt": "000000780800", "evlt_amt": "000000794000", "evltv_prft": "000000013200", "pl_rt": "1.6906"},
                ],
                "return_code": 0,
                "return_msg": "mock",
            }
        if api_id == "ka10085":
            return {
                "acnt_prft_rt": [
                    {"stk_cd": "005930", "stk_nm": "삼성전자", "cur_prc": "71800", "pur_pric": "71350", "pur_amt": "1427000", "rmnd_qty": "20", "tdy_sel_pl": "0"},
                    {"stk_cd": "000660", "stk_nm": "SK하이닉스", "cur_prc": "198500", "pur_pric": "195200", "pur_amt": "780800", "rmnd_qty": "4", "tdy_sel_pl": "0"},
                ],
                "return_code": 0,
                "return_msg": "mock",
            }
        if api_id == "ka10001":
            samples = {
                "005930": {"stk_nm": "삼성전자", "cur_prc": "71800", "flu_rt": "0.84"},
                "000660": {"stk_nm": "SK하이닉스", "cur_prc": "198500", "flu_rt": "1.92"},
                "035420": {"stk_nm": "NAVER", "cur_prc": "184200", "flu_rt": "-0.65"},
            }
            code = str(payload.get("stk_cd") or "005930")
            sample = samples.get(code, {"stk_nm": code, "cur_prc": "0", "flu_rt": "0"})
            return {"stk_cd": code, **sample, "return_code": 0, "return_msg": "mock"}
        return {"return_code": 0, "return_msg": "mock"}


kiwoom_client = KiwoomClient()
