from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel

from app.core.security.jwt import get_current_user
from app.orm_models.auth import User
from app.services.adminOtaService import AdminOtaService

router = APIRouter(prefix="/api/admin/ota", tags=["admin-ota"])


# ── Admin guard ───────────────────────────────────────────────────────────────

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if "admin" not in [role.name for role in current_user.roles]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/versions")
def get_versions(current_user: User = Depends(require_admin)):
    return AdminOtaService.get_versions()


@router.post("/upload")
async def upload_firmware(
    file: UploadFile = File(...),
    hardware: str = Form(...),
    app_version: str = Form(...),
    mac_exception: Optional[str] = Form(None),
    current_user: User = Depends(require_admin),
):
    return await AdminOtaService.upload_firmware(file, hardware, app_version, mac_exception)


class DeleteVersionRequest(BaseModel):
    hardware: Optional[str] = None
    mac_exception: Optional[str] = None
    delete_file: bool = False


@router.delete("/versions")
def delete_version(
    payload: DeleteVersionRequest,
    current_user: User = Depends(require_admin),
):
    return AdminOtaService.delete_version(payload.hardware, payload.mac_exception, payload.delete_file)


@router.get("/files")
def list_firmware_files(current_user: User = Depends(require_admin)):
    return AdminOtaService.list_firmware_files()