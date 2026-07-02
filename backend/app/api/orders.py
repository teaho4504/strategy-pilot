from fastapi import APIRouter, HTTPException, status

from app.core.config import get_settings

router = APIRouter()


def _orders_disabled() -> None:
    settings = get_settings()
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "message": "Order APIs are disabled in this phase.",
            "readOnly": settings.kiwoom_read_only,
            "orderEnabled": settings.order_enabled,
        },
    )


@router.post("/orders")
async def create_order() -> None:
    _orders_disabled()


@router.post("/orders/cancel")
async def cancel_order() -> None:
    _orders_disabled()


@router.post("/orders/amend")
async def amend_order() -> None:
    _orders_disabled()
