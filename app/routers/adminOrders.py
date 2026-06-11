from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import requests as http_requests

from app.core.config import settings
from app.core.user_access import require_admin
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.domain.exceptions import NotFoundError, BusinessError, ValidationError
from app.repositories.order_repo import OrderRepository
from app.services.adminOrdersService import AdminOrdersService
from app.schemas.order import OrderOut, OrderPatch, AssociateDevicePayload

router = APIRouter(prefix="/api/admin/orders", tags=["admin-orders"])


def get_service(db: Session = Depends(get_db)) -> AdminOrdersService:
    return AdminOrdersService(OrderRepository(db))


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (BusinessError, ValidationError)):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("")
@require_admin
def list_orders(
    current_user: User,
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: str = Query("date_desc"),
    svc: AdminOrdersService = Depends(get_service),
):
    return svc.list_orders(status, search, sort)


@router.get("/unowned-devices")
@require_admin
def list_unowned_devices(current_user: User, svc: AdminOrdersService = Depends(get_service)):
    return svc.list_unowned_devices()


@router.get("/devices")
@require_admin
def list_all_devices_for_select(current_user: User, svc: AdminOrdersService = Depends(get_service)):
    return svc.list_all_devices()


@router.get("/{order_id}")
@require_admin
def get_order(order_id: int, current_user: User, svc: AdminOrdersService = Depends(get_service)):
    try:
        return svc.get_order(order_id, include_svg=True)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.patch("/{order_id}")
@require_admin
def patch_order(order_id: int, payload: OrderPatch, current_user: User, svc: AdminOrdersService = Depends(get_service)):
    try:
        return svc.patch_order(order_id, payload)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.post("/{order_id}/associate-device")
@require_admin
def associate_device(order_id: int, payload: AssociateDevicePayload, current_user: User, svc: AdminOrdersService = Depends(get_service)):
    try:
        return svc.associate_device(order_id, payload)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.post("/{order_id}/ship")
@require_admin
def ship_order(
    order_id: int,
    current_user: User,
    db: Session = Depends(get_db),
    svc: AdminOrdersService = Depends(get_service),
):
    from app.services import adminShippingService
    fallback_code = adminShippingService.get_first_enabled(db)
    try:
        return svc.ship_order(order_id, fallback_option_code=fallback_code)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.get("/{order_id}/label")
@require_admin
def download_label(order_id: int, current_user: User, svc: AdminOrdersService = Depends(get_service)):
    """Proxy the SendCloud label PDF so the browser doesn't need SendCloud credentials."""
    try:
        label_url = svc.get_label_url(order_id)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)

    try:
        resp = http_requests.get(
            label_url,
            auth=(settings.SENDCLOUD_API_KEY, settings.SENDCLOUD_API_SECRET),
            timeout=15,
            stream=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch label: {exc}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"SendCloud returned {resp.status_code}")

    return StreamingResponse(
        resp.iter_content(chunk_size=8192),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="label-order-{order_id}.pdf"'},
    )
