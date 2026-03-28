from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security.jwt import get_current_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.services.adminOtaService import AdminOtaService

router = APIRouter(prefix="/api/admin/ota", tags=["admin-ota"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if "admin" not in [role.name for role in current_user.roles]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@router.get("/versions")
def get_versions(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return AdminOtaService.get_versions(db)


@router.get("/packages")
def list_packages(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return AdminOtaService.list_packages(db)


@router.get("/hardware")
def list_hardware(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return AdminOtaService.list_hardware(db)


@router.post("/upload")
async def upload_firmware(
    file: UploadFile = File(...),
    app_version: str = Form(...),
    app_name: Optional[str] = Form(None),
    firmware_name: Optional[str] = Form(None),
    hardware: Optional[str] = Form(None),
    current_user: User = Depends(require_admin),
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
    mac_exception: Optional[str] = None
    package_id: Optional[int] = None
    delete_file: bool = False


@router.delete("/versions")
def delete_version(
    payload: DeleteVersionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return AdminOtaService.delete_version(
        db,
        payload.hardware,
        payload.mac_exception,
        payload.delete_file,
        payload.package_id,
        payload.hardware_version,
    )


class UpsertHardwareRequest(BaseModel):
    hardware_type: str
    hardware_version: Optional[str] = None
    default_firmware_package_id: Optional[int] = None


@router.post("/hardware")
def upsert_hardware(
    payload: UpsertHardwareRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return AdminOtaService.upsert_hardware(
        db,
        payload.hardware_type,
        payload.hardware_version,
        payload.default_firmware_package_id,
    )


class AssignDeviceFirmwareRequest(BaseModel):
    mac_address: str
    firmware_package_id: Optional[int] = None


@router.post("/device-assignments")
def assign_device_firmware(
    payload: AssignDeviceFirmwareRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return AdminOtaService.assign_device_firmware(db, payload.mac_address, payload.firmware_package_id)


@router.get("/files")
def list_firmware_files(current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return AdminOtaService.list_firmware_files(db)
