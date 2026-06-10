from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.orm_models.db import get_db
from app.domain.exceptions import NotFoundError
from app.schemas.device import DeviceAdminOut, DevicePatch, BoardListOut
from app.repositories.device_repo import DeviceRepository
from app.services.adminDevicesService import AdminDevicesService

router = APIRouter(prefix="/api/admin/devices", tags=["admin-devices"])


def get_service(db: Session = Depends(get_db)) -> AdminDevicesService:
    return AdminDevicesService(DeviceRepository(db))


@router.get("", response_model=list[DeviceAdminOut])
@require_admin
def list_all_devices(svc: AdminDevicesService = Depends(get_service)):
    return svc.list_devices()


@router.get("/users", response_model=list[str])
@require_admin
def list_all_user_emails(svc: AdminDevicesService = Depends(get_service)):
    return svc.list_user_emails()


@router.get("/boards", response_model=list[BoardListOut])
@require_admin
def list_boards(owner_email: Optional[str] = None, svc: AdminDevicesService = Depends(get_service)):
    return svc.list_boards(owner_email)


@router.patch("/{device_id}", response_model=DeviceAdminOut)
@require_admin
def patch_device(device_id: int, payload: DevicePatch, svc: AdminDevicesService = Depends(get_service)):
    try:
        return svc.patch_device(device_id, payload)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))