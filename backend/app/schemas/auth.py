from __future__ import annotations

from typing import Literal
from typing import Optional

from pydantic import BaseModel, Field


class KiwoomLoginRequest(BaseModel):
    mode: Literal["live"]
    accountNo: str = Field(min_length=1, max_length=40)
    appKey: str = Field(min_length=1, max_length=200)
    secretKey: str = Field(min_length=1, max_length=300)
    accessPin: str = Field(min_length=1, max_length=80)


class KiwoomProfileLoginRequest(BaseModel):
    profile: Optional[str] = Field(default=None, max_length=64)
    accessPin: str = Field(min_length=1, max_length=80)


class KiwoomCliProfileSummary(BaseModel):
    profile: str
    mode: Literal["real"]
    current: bool
    accountLabel: str


class KiwoomLoginResponse(BaseModel):
    accessToken: str
    tokenType: str = "Bearer"
    mode: Literal["live"]
    accountLabel: str
    baseUrl: str
    readOnly: bool
    orderEnabled: bool
    expiresAt: str
