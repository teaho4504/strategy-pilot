from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError, PyJWKClient, PyJWKClientError

from app.core.config import get_settings
from app.services.kiwoom_session import kiwoom_session_manager, set_active_kiwoom_session


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    email: str
    subject: Optional[str] = None


class SupabaseAuthError(Exception):
    pass


_jwk_clients: dict[str, PyJWKClient] = {}


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not allowed")


def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    client = _jwk_clients.get(jwks_url)
    if client is None:
        client = PyJWKClient(jwks_url, timeout=5)
        _jwk_clients[jwks_url] = client
    return client


def _email_from_claims(claims: dict[str, Any]) -> str:
    email_value = claims.get("email")
    if email_value is None:
        user_metadata = claims.get("user_metadata")
        if isinstance(user_metadata, dict):
            email_value = user_metadata.get("email")

    if not isinstance(email_value, str):
        raise SupabaseAuthError("Supabase JWT did not include a valid email")

    email = email_value.strip().lower()
    if not email:
        raise SupabaseAuthError("Supabase JWT did not include a valid email")
    return email


def _decode_supabase_jwt(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.supabase_jwks_url or not settings.supabase_jwt_issuer or not settings.supabase_jwt_audience:
        raise SupabaseAuthError("Supabase JWT verification is not configured")

    try:
        signing_key = _get_jwk_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.supabase_jwt_audience,
            issuer=settings.supabase_jwt_issuer,
            options={"require": ["exp", "aud", "iss"]},
        )
    except (ExpiredSignatureError, InvalidTokenError, PyJWKClientError) as exc:
        raise SupabaseAuthError("Supabase JWT verification failed") from exc


def verify_supabase_jwt(token: str) -> AuthenticatedUser:
    claims = _decode_supabase_jwt(token)
    return AuthenticatedUser(email=_email_from_claims(claims), subject=claims.get("sub"))


async def require_authenticated_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthorized()

    kiwoom_session = kiwoom_session_manager.get_session(credentials.credentials)
    if kiwoom_session is not None:
        set_active_kiwoom_session(kiwoom_session)
        user = AuthenticatedUser(email=f"kiwoom-{kiwoom_session.mode}@local", subject="kiwoom-session")
        request.state.user = user
        request.state.kiwoom_session = kiwoom_session
        return user

    try:
        user = verify_supabase_jwt(credentials.credentials)
    except SupabaseAuthError:
        raise _unauthorized() from None

    settings = get_settings()
    if not settings.allowed_user_emails or user.email not in settings.allowed_user_emails:
        raise _forbidden()

    request.state.user = user
    return user
