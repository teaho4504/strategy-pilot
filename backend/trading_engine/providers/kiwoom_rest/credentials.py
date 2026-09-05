from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from trading_engine.providers.kiwoom_rest.safety import mask_secret


@dataclass(frozen=True)
class KiwoomCredentialStatus:
    source: str
    configured: bool
    token_cached: bool = False


@dataclass(frozen=True)
class KiwoomCredentialRef:
    """Reference to credentials held outside the repository.

    The official Kiwoom REST API GitHub sample recommends CLI/keyring based
    credential storage first and treats ``.env`` as a fallback. This skeleton
    follows that boundary by carrying only metadata and never storing raw
    app keys, secrets, tokens, or account numbers.
    """

    source: str = "external-secret-store"
    profile: str | None = None
    account_alias: str | None = None

    def status(self) -> KiwoomCredentialStatus:
        return KiwoomCredentialStatus(source=self.source, configured=False, token_cached=False)

    def describe_safe(self) -> str:
        profile = self.profile or "default"
        return f"KiwoomCredentialRef(source={self.source}, profile={mask_secret(profile)})"


class CredentialProvider(Protocol):
    def status(self) -> KiwoomCredentialStatus:
        ...

    def authorization_header(self) -> str:
        ...


class SkeletonCredentialProvider:
    """Credential provider placeholder.

    Any attempt to obtain an authorization header fails until a real server-side
    credential provider is explicitly implemented and reviewed.
    """

    def __init__(self, ref: KiwoomCredentialRef | None = None) -> None:
        self.ref = ref or KiwoomCredentialRef()

    def status(self) -> KiwoomCredentialStatus:
        return self.ref.status()

    def authorization_header(self) -> str:
        raise RuntimeError("Kiwoom credentials are not loaded in provider skeleton")
