from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.services.adminOtaService import AdminOtaService

router = APIRouter(prefix="/api/admin/ota", tags=["admin-ota"])


@router.get("/versions")
@require_admin
def get_versions(db: Session = Depends(get_db)):
    return AdminOtaService.get_versions(db)


@router.get("/packages")
@require_admin
def list_packages(db: Session = Depends(get_db)):
    return AdminOtaService.list_packages(db)


@router.get("/hardware")
@require_admin
def list_hardware(db: Session = Depends(get_db)):
    return AdminOtaService.list_hardware(db)


@router.post("/upload")
@require_admin
async def upload_firmware(
    file: UploadFile = File(...),
    app_version: str = Form(...),
    app_name: Optional[str] = Form(None),
    firmware_name: Optional[str] = Form(None),
    hardware: Optional[str] = Form(None),
    current_user: User = None,
    db: Session = Depends(get_db),
):
    resolved_app_name = app_name or firmware_name or hardware
    return AdminOtaService.upload_firmware(
        db=db,
        file=file,
        app_version=app_version,
        app_name=resolved_app_name,
        uploaded_by_user_id=current_user.id,
    )


class DeleteVersionRequest(BaseModel):
    hardware: Optional[str] = None
    hardware_version: Optional[str] = None
    firmware_name: Optional[str] = None
    mac_exception: Optional[str] = None
    package_id: Optional[int] = None
    delete_file: bool = False


@router.delete("/versions")
@require_admin
def delete_version(payload: DeleteVersionRequest, db: Session = Depends(get_db)):
    return AdminOtaService.delete_version(
        db,
        payload.hardware,
        payload.mac_exception,
        payload.delete_file,
        payload.package_id,
        payload.hardware_version,
        payload.firmware_name,
    )


class UpsertHardwareRequest(BaseModel):
    hardware_type: str
    hardware_version: Optional[str] = None
    default_firmware_package_id: Optional[int] = None


@router.post("/hardware")
@require_admin
def upsert_hardware(payload: UpsertHardwareRequest, db: Session = Depends(get_db)):
    return AdminOtaService.upsert_hardware(
        db,
        payload.hardware_type,
        payload.hardware_version,
        payload.default_firmware_package_id,
    )


class UpsertHardwareFirmwareRequest(BaseModel):
    hardware_type: str
    hardware_version: Optional[str] = None
    firmware_name: str
    firmware_package_id: int


@router.post("/hardware-firmware")
@require_admin
def upsert_hardware_firmware(payload: UpsertHardwareFirmwareRequest, db: Session = Depends(get_db)):
    return AdminOtaService.upsert_hardware_firmware(
        db,
        payload.hardware_type,
        payload.firmware_name,
        payload.firmware_package_id,
        payload.hardware_version,
    )


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
