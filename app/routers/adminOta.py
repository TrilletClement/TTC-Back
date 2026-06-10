from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.domain.exceptions import NotFoundError, BusinessError, ValidationError
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.repositories.firmware_repo import FirmwareRepository
from app.schemas.ota import ArchiveRequest, AssignDeviceFirmwareRequest, DeletePackageRequest, UpsertHardwareRequest
from app.services.adminOtaService import AdminOtaService, FirmwareStorage
from app.core.config import settings

router = APIRouter(prefix="/api/admin/ota", tags=["admin-ota"])


def get_service(db: Session = Depends(get_db)) -> AdminOtaService:
    return AdminOtaService(
        repo=FirmwareRepository(db),
        storage=FirmwareStorage(settings.FIRMWARE_DIR),
    )


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, BusinessError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("/versions")
@require_admin
def get_data(svc: AdminOtaService = Depends(get_service)):
    return svc.get_data()


@router.post("/upload")
@require_admin
async def upload_firmware(
    file: UploadFile = File(...),
    svc: AdminOtaService = Depends(get_service),
):
    try:
        return svc.upload_firmware(file)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.patch("/packages/{package_id}/archive")
@require_admin
def archive_package(
    package_id: int,
    payload: ArchiveRequest,
    svc: AdminOtaService = Depends(get_service),
):
    try:
        return svc.set_archived(package_id, payload.archived)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.delete("/packages")
@require_admin
def delete_package(
    payload: DeletePackageRequest,
    svc: AdminOtaService = Depends(get_service),
):
    try:
        return svc.delete_package(payload.package_id, payload.delete_file, payload.force)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.post("/hardware")
@require_admin
def upsert_hardware(
    payload: UpsertHardwareRequest,
    svc: AdminOtaService = Depends(get_service),
):
    try:
        return svc.upsert_hardware(payload.hardware_type, payload.firmware_package_id)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.delete("/hardware/{hardware_id}")
@require_admin
def delete_hardware(
    hardware_id: int,
    svc: AdminOtaService = Depends(get_service),
):
    try:
        return svc.delete_hardware(hardware_id)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.post("/device-assignments")
@require_admin
def assign_device_firmware(
    payload: AssignDeviceFirmwareRequest,
    svc: AdminOtaService = Depends(get_service),
):
    try:
        return svc.assign_device_firmware(payload.mac_address, payload.firmware_package_id)
    except (NotFoundError, BusinessError, ValidationError) as e:
        raise _handle(e)


@router.get("/files")
@require_admin
def list_firmware_files(svc: AdminOtaService = Depends(get_service)):
    return svc.list_firmware_files()