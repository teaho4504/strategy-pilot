from typing import Any

import httpx

from app.core.config import Settings
from app.services.portfolio_mapper import mock_ka10085_pages
from app.services.token_manager import KiwoomApiError, KiwoomConfigError, token_manager


class KiwoomClient:
    """Read-only Kiwoom REST client.

    This client intentionally contains no order submission methods. The first
    live integration target is ka10085 account performance inquiry only.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def get_account_performance_pages(self) -> tuple[list[dict[str, Any]], str]:
        if not self.settings.is_live:
            return mock_ka10085_pages(), "mock"

        if not self.settings.kiwoom_configured:
            raise KiwoomConfigError("KIWOOM_MODE=live requires KIWOOM_ACCOUNT_NO and either KIWOOM_ACCESS_TOKEN or app key/secret")

        token = await token_manager.get_access_token(self.settings)
        pages: list[dict[str, Any]] = []
        next_key: str | None = None
        cont_yn = "N"

        async with httpx.AsyncClient(timeout=15) as client:
            for _ in range(20):
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json;charset=UTF-8",
                    "api-id": "ka10085",
                    "cont-yn": cont_yn,
                }
                if next_key:
                    headers["next-key"] = next_key

                payload = {"acct_no": self.settings.kiwoom_account_no}
                try:
                    response = await client.post(
                        f"{self.settings.kiwoom_api_base_url}/api/dostk/acnt",
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    pages.append(response.json())
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in {401, 403}:
                        raise KiwoomApiError("Kiwoom authentication failed or token expired") from exc
                    raise KiwoomApiError(f"Kiwoom ka10085 request failed: HTTP {exc.response.status_code}") from exc
                except httpx.HTTPError as exc:
                    raise KiwoomApiError("Kiwoom ka10085 request failed due to a network error") from exc
                except ValueError as exc:
                    raise KiwoomApiError("Kiwoom ka10085 response was not valid JSON") from exc

                response_cont = response.headers.get("cont-yn") or response.headers.get("Cont-Yn") or "N"
                response_next_key = response.headers.get("next-key") or response.headers.get("Next-Key")
                if response_cont.upper() != "Y" or not response_next_key:
                    break
                cont_yn = "Y"
                next_key = response_next_key
            else:
                raise KiwoomApiError("Kiwoom ka10085 continuation exceeded the 20 page safety limit")

        return pages, "kiwoom-ka10085"
