from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import AuthenticatedUser, bearer_scheme, require_authenticated_user
from app.core.config import get_settings
from app.schemas.auth import KiwoomCliProfileSummary, KiwoomLoginRequest, KiwoomLoginResponse, KiwoomProfileLoginRequest
from app.services.kiwoom_cli_profile import KiwoomCliProfileError, safe_kiwoom_cli_profiles
from app.services.kiwoom_session import (
    KiwoomSessionError,
    kiwoom_session_manager,
    set_active_kiwoom_session,
)


router = APIRouter()


def _assert_dashboard_access_pin(pin: str | None) -> None:
    settings = get_settings()
    if not settings.dashboard_access_pin:
        raise HTTPException(
            status_code=503,
            detail={"message": "Dashboard access PIN is not configured"},
        )
    if not pin or not hmac.compare_digest(pin.strip(), settings.dashboard_access_pin):
        raise HTTPException(
            status_code=403,
            detail={"message": "Dashboard access PIN is invalid"},
        )


def _login_response(session) -> KiwoomLoginResponse:
    settings = get_settings()
    return KiwoomLoginResponse(
        accessToken=session.session_token,
        mode=session.mode,
        accountLabel=session.safe_account_label,
        baseUrl=session.base_url,
        readOnly=settings.kiwoom_read_only,
        orderEnabled=settings.order_enabled,
        expiresAt=session.expires_at.isoformat(),
    )


async def _resume_order_state_monitor() -> None:
    try:
        from app.services.us_order_service import us_order_service

        await us_order_service.ensure_order_state_monitor()
    except Exception:
        # Login remains available when the optional observation monitor is
        # disabled, has no submitted orders, or cannot recover its local state.
        return


@router.get("/auth/kiwoom/profiles", response_model=list[KiwoomCliProfileSummary])
async def get_kiwoom_profiles(x_dashboard_pin: str | None = Header(default=None)) -> list[KiwoomCliProfileSummary]:
    _assert_dashboard_access_pin(x_dashboard_pin)
    try:
        return [
            KiwoomCliProfileSummary(**profile)
            for profile in safe_kiwoom_cli_profiles()
            if profile.get("mode") == "real"
        ]
    except KiwoomCliProfileError:
        return []


@router.post("/auth/kiwoom/login", response_model=KiwoomLoginResponse)
async def login_kiwoom(payload: KiwoomLoginRequest) -> KiwoomLoginResponse:
    _assert_dashboard_access_pin(payload.accessPin)
    try:
        session = await kiwoom_session_manager.create_session(
            mode=payload.mode,
            account_no=payload.accountNo,
            app_key=payload.appKey,
            secret_key=payload.secretKey,
        )
    except KiwoomSessionError as exc:
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Kiwoom credential verification failed",
                "httpStatus": exc.http_status,
                "returnCode": exc.return_code,
                "returnMessage": exc.return_msg,
            },
        ) from exc

    await _resume_order_state_monitor()
    return _login_response(session)


@router.post("/auth/kiwoom/profile-login", response_model=KiwoomLoginResponse)
async def login_kiwoom_profile(payload: KiwoomProfileLoginRequest) -> KiwoomLoginResponse:
    _assert_dashboard_access_pin(payload.accessPin)
    try:
        session = await kiwoom_session_manager.create_session_from_cli_profile(payload.profile)
    except KiwoomSessionError as exc:
        raise HTTPException(
            status_code=401,
            detail={
                "message": "Kiwoom CLI profile verification failed",
                "httpStatus": exc.http_status,
                "returnCode": exc.return_code,
                "returnMessage": exc.return_msg,
            },
        ) from exc

    await _resume_order_state_monitor()
    return _login_response(session)


@router.post("/auth/kiwoom/logout", status_code=204)
async def logout_kiwoom(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    _user: AuthenticatedUser = Depends(require_authenticated_user),
) -> Response:
    if credentials is not None and credentials.credentials:
        kiwoom_session_manager.revoke_session(credentials.credentials)
    set_active_kiwoom_session(None)

    from app.services.us_order_state_monitor import kiwoom_order_state_monitor

    await kiwoom_order_state_monitor.stop()
    return Response(status_code=204)
