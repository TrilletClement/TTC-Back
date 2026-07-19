from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.domain.exceptions import NotFoundError
from app.orm_models.db import get_db
from app.repositories.settings_repo import SettingsRepository
from app.schemas.settings import OverridesPayload, SchemaPayload
from app.services.adminSettingsService import adminSettingsService

router = APIRouter(prefix="/api/admin/settings", tags=["admin-settings"])


def get_service(db: Session = Depends(get_db)) -> adminSettingsService:
    return adminSettingsService(SettingsRepository(db))


@router.get("/hardware/{hardware_id}")
@require_admin
def get_hardware_settings(hardware_id: int, svc: adminSettingsService = Depends(get_service)):
    try:
        return svc.get_hardware_settings(hardware_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/hardware/{hardware_id}")
@require_admin
def update_hardware_settings(hardware_id: int, payload: SchemaPayload, svc: adminSettingsService = Depends(get_service)):
    try:
        return svc.update_hardware_schema(hardware_id, payload.json_schema)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/device/{device_id}")
@require_admin
def get_device_settings(device_id: int, svc: adminSettingsService = Depends(get_service)):
    try:
        return svc.get_device_settings(device_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/device/{device_id}")
@require_admin
def update_device_settings(device_id: int, payload: OverridesPayload, svc: adminSettingsService = Depends(get_service)):
    try:
        return svc.update_device_overrides(device_id, payload.overrides)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))