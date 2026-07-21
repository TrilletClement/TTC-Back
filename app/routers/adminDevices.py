from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.orm_models.db import get_db
from app.domain.exceptions import BusinessError, NotFoundError, ValidationError
from app.schemas.device import DeviceAdminOut, DevicePatch, BoardListOut, DeviceLabelsRequest
from app.repositories.device_repo import DeviceRepository
from app.services.adminDevicesService import AdminDevicesService
from app.services.device_label_service import DeviceLabelService

router = APIRouter(prefix="/api/admin/devices", tags=["admin-devices"])


def get_service(db: Session = Depends(get_db)) -> AdminDevicesService:
    return AdminDevicesService(DeviceRepository(db))


def get_label_service(db: Session = Depends(get_db)) -> DeviceLabelService:
    return DeviceLabelService(DeviceRepository(db))


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


@router.post("/labels")
@require_admin
def get_device_labels(payload: DeviceLabelsRequest, svc: DeviceLabelService = Depends(get_label_service)):
    try:
        pdf_bytes = svc.generate_labels_pdf(payload.device_ids)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (BusinessError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    filename = f"labels-{len(payload.device_ids)}-devices.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})