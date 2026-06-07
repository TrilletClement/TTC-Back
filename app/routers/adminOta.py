from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.services.adminOtaService import AdminOtaService

router = APIRouter(prefix="/api/admin/ota", tags=["admin-ota"])


@router.get("/versions")
@require_admin
def get_data(db: Session = Depends(get_db)):
    return AdminOtaService.get_data(db)


@router.post("/upload")
@require_admin
async def upload_firmware(
    file: UploadFile = File(...),
    current_user: User = None,
    db: Session = Depends(get_db),
):
    return AdminOtaService.upload_firmware(db=db, file=file)


class ArchiveRequest(BaseModel):
    archived: bool


@router.patch("/packages/{package_id}/archive")
@require_admin
def archive_package(package_id: int, payload: ArchiveRequest, db: Session = Depends(get_db)):
    return AdminOtaService.set_archived(db, package_id, payload.archived)


class DeletePackageRequest(BaseModel):
    package_id: int
    delete_file: bool = False
    force: bool = False


@router.delete("/packages")
@require_admin
def delete_package(payload: DeletePackageRequest, db: Session = Depends(get_db)):
    return AdminOtaService.delete_package(db, payload.package_id, payload.delete_file, payload.force)


class UpsertHardwareRequest(BaseModel):
    hardware_type: str
    firmware_package_id: Optional[int] = None


@router.post("/hardware")
@require_admin
def upsert_hardware(payload: UpsertHardwareRequest, db: Session = Depends(get_db)):
    return AdminOtaService.upsert_hardware(db, payload.hardware_type, payload.firmware_package_id)


@router.delete("/hardware/{hardware_id}")
@require_admin
def delete_hardware(hardware_id: int, db: Session = Depends(get_db)):
    return AdminOtaService.delete_hardware(db, hardware_id)


class AssignDeviceFirmwareRequest(BaseModel):
    mac_address: str
    firmware_package_id: Optional[int] = None


@router.post("/device-assignments")
@require_admin
def assign_device_firmware(payload: AssignDeviceFirmwareRequest, db: Session = Depends(get_db)):
    return AdminOtaService.assign_device_firmware(db, payload.mac_address, payload.firmware_package_id)


@router.get("/files")
@require_admin
def list_firmware_files(db: Session = Depends(get_db)):
    return AdminOtaService.list_firmware_files(db)
