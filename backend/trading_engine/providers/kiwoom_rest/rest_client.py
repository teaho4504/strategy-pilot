from __future__ import annotations

from collections.abc import Callable
from typing import Any

from trading_engine.providers.kiwoom_rest.credentials import CredentialProvider, SkeletonCredentialProvider
from trading_engine.providers.kiwoom_rest.safety import KiwoomProviderSafety, sanitize_mapping
from trading_engine.providers.kiwoom_rest.schemas import KiwoomRequestSpec, KiwoomTokenStatus
from trading_engine.providers.kiwoom_rest.tr_codes import DomesticReadOnlyTR


Transport = Callable[[KiwoomRequestSpec, dict[str, str]], dict[str, Any]]


class KiwoomRestClientSkeleton:
    """Read-only Kiwoom REST client skeleton.

    It mirrors the official sample's separation between OAuth and TR requests:
    regular TR calls carry ``api-id`` and ``authorization`` headers, while token
    issuance is intentionally outside this trading-engine provider skeleton.
    """

    def __init__(
        self,
        *,
        safety: KiwoomProviderSafety | None = None,
        credentials: CredentialProvider | None = None,
        transport: Transport | None = None,
    ) -> None:
        self.safety = safety or KiwoomProviderSafety()
        self.credentials = credentials or SkeletonCredentialProvider()
        self.transport = transport

    def token_status(self) -> KiwoomTokenStatus:
        status = self.credentials.status()
        return KiwoomTokenStatus(configured=status.configured, cached=status.token_cached)

    def stock_info(self, symbol: str) -> dict[str, Any]:
        return self._read_only_request(
            KiwoomRequestSpec(
                api_id=DomesticReadOnlyTR.STOCK_INFO.code,
                path=DomesticReadOnlyTR.STOCK_INFO.path,
                body={"stk_cd": symbol},
            )
        )

    def balance(self) -> dict[str, Any]:
        return self._read_only_request(
            KiwoomRequestSpec(
                api_id=DomesticReadOnlyTR.ACCOUNT_VALUATION.code,
                path=DomesticReadOnlyTR.ACCOUNT_VALUATION.path,
                body={"qry_tp": "1", "dmst_stex_tp": "KRX"},
            )
        )

    def cash(self) -> dict[str, Any]:
        return self._read_only_request(
            KiwoomRequestSpec(
                api_id=DomesticReadOnlyTR.CASH.code,
                path=DomesticReadOnlyTR.CASH.path,
                body={"qry_tp": "2"},
            )
        )

    def place_order(self, *_: object, **__: object) -> None:
        self.safety.assert_order_blocked()

    def _read_only_request(self, spec: KiwoomRequestSpec) -> dict[str, Any]:
        self.safety.assert_no_order(spec.api_id)
        self.safety.assert_live_allowed()
        if self.transport is None:
            raise RuntimeError("Kiwoom REST transport is not configured")
        headers = self._headers(spec)
        return sanitize_mapping(self.transport(spec, headers))

    def _headers(self, spec: KiwoomRequestSpec) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "api-id": spec.api_id,
            "authorization": self.credentials.authorization_header(),
        }
        if spec.cont_yn:
            headers["cont-yn"] = spec.cont_yn
        if spec.next_key:
            headers["next-key"] = spec.next_key
        return headers
