from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.services.token_manager import TokenManagerError, token_manager


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
    list_key: Optional[str] = None


@dataclass
class KiwoomResponse:
    api_id: str
    body: dict[str, Any]
    cont_yn: str
    next_key: str


TR_SPECS: dict[str, KiwoomTrSpec] = {
    "ka00001": KiwoomTrSpec("ka00001", "계좌번호조회", "/api/dostk/acnt", {}),
    "ka10085": KiwoomTrSpec("ka10085", "계좌수익률요청", "/api/dostk/acnt", {"stex_tp": "0"}, "acnt_prft_rt"),
    "kt00001": KiwoomTrSpec("kt00001", "예수금상세현황요청", "/api/dostk/acnt", {"qry_tp": "2"}),
    "kt00004": KiwoomTrSpec("kt00004", "계좌평가현황요청", "/api/dostk/acnt", {"qry_tp": "1", "dmst_stex_tp": "KRX"}, "stk_acnt_evlt_prst"),
    "kt00005": KiwoomTrSpec("kt00005", "체결잔고요청", "/api/dostk/acnt", {"dmst_stex_tp": "KRX"}, "stk_cntr_remn"),
}


class KiwoomClient:
    async def request_tr(
        self,
        api_id: str,
        payload: Optional[dict[str, Any]] = None,
        cont_yn: str = "N",
        next_key: str = "",
    ) -> KiwoomResponse:
        settings = get_settings()
        spec = self._spec(api_id)
        request_payload = {**spec.default_payload, **(payload or {})}

        if settings.kiwoom_mode != "live":
            return KiwoomResponse(api_id=api_id, body=self._mock_response(api_id), cont_yn="N", next_key="")

        if not settings.credentials_configured:
            missing = ", ".join(settings.missing_kiwoom_env)
            raise KiwoomConfigurationError(f"Kiwoom live mode requires backend credentials: {missing}")
        if not settings.kiwoom_read_only:
            raise KiwoomConfigurationError("Read-only backend requires KIWOOM_READ_ONLY=true")

        try:
            token = await token_manager.get_access_token()
        except TokenManagerError as exc:
            raise KiwoomConfigurationError(str(exc)) from exc

        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": f"Bearer {token}",
            "cont-yn": cont_yn,
            "next-key": next_key,
            "api-id": api_id,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(f"{settings.kiwoom_base_url}{spec.service_uri}", json=request_payload, headers=headers)
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

        return KiwoomResponse(
            api_id=api_id,
            body=body,
            cont_yn=response.headers.get("cont-yn", "N") or "N",
            next_key=response.headers.get("next-key", "") or "",
        )

    async def request_tr_all(self, api_id: str, payload: Optional[dict[str, Any]] = None) -> KiwoomResponse:
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
    def _mock_response(api_id: str) -> dict[str, Any]:
        if api_id == "ka00001":
            return {"acctNo": "MOCK_ACCOUNT", "return_code": 0, "return_msg": "mock"}
        if api_id == "ka10085":
            return {
                "acnt_prft_rt": [
                    {"stk_cd": "000001", "stk_nm": "MOCK HOLDING 1", "rmnd_qty": "10", "pur_pric": "10000", "cur_prc": "10500", "pur_amt": "100000"},
                    {"stk_cd": "000002", "stk_nm": "MOCK HOLDING 2", "rmnd_qty": "5", "pur_pric": "20000", "cur_prc": "19800", "pur_amt": "100000"},
                ],
                "return_code": 0,
                "return_msg": "mock",
            }
        if api_id == "kt00001":
            return {"entr": "18420000", "pymn_alow_amt": "11230000", "ord_alow_amt": "12550000", "return_code": 0, "return_msg": "mock"}
        if api_id == "kt00004":
            return {
                "aset_evlt_amt": "52184300",
                "tdy_lspft_amt": "312500",
                "tdy_lspft_rt": "0.61",
                "lspft_amt": "2184300",
                "stk_acnt_evlt_prst": [],
                "return_code": 0,
                "return_msg": "mock",
            }
        if api_id == "kt00005":
            return {
                "entr": "18420000",
                "pymn_alow_amt": "11230000",
                "ord_alowa": "12550000",
                "stk_cntr_remn": [
                    {"stk_cd": "000001", "stk_nm": "MOCK HOLDING 1", "cur_qty": "10", "buy_uv": "10000", "cur_prc": "10500", "evlt_amt": "105000", "evltv_prft": "5000", "pl_rt": "5.0"}
                ],
                "return_code": 0,
                "return_msg": "mock",
            }
        return {"return_code": 0, "return_msg": "mock"}


kiwoom_client = KiwoomClient()
