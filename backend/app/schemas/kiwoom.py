from typing import Literal

from pydantic import BaseModel


class KiwoomTokenStatus(BaseModel):
    mode: Literal["mock", "live"]
    hasToken: bool
    valid: bool
    expiresAt: str | None
    issuedAt: str | None
    expiresInSeconds: int | None
    lastError: str | None


class KiwoomStatus(BaseModel):
    mode: Literal["mock", "live"]
    baseUrl: str
    tokenUrlConfigured: bool
    token: KiwoomTokenStatus
    credentialsConfigured: bool
    accountConfigured: bool
    readOnly: bool
    orderEnabled: bool
    missing: list[str]
