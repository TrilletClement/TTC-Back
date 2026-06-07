from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.orm_models.db import get_db
from app.orm_models.device import ESP32Device, Hardware
from app.services.settingsService import SettingsService

router = APIRouter(prefix="/api/admin/settings", tags=["admin-settings"])


class SchemaPayload(BaseModel):
    schema: dict  # {sections: [{key, label, settings: [{key, label, type, default, ...}]}]}


class OverridesPayload(BaseModel):
    overrides: dict[str, Any]


@router.get("/hardware/{hardware_id}")
@require_admin
def get_hardware_settings(hardware_id: int, db: Session = Depends(get_db)):
    hw = db.query(Hardware).filter(Hardware.id == hardware_id).first()
    if not hw:
        raise HTTPException(status_code=404, detail="Hardware not found")
    return {"hardware_id": hardware_id, "schema": SettingsService.get_hardware_schema(hw)}


@router.put("/hardware/{hardware_id}")
@require_admin
def update_hardware_settings(hardware_id: int, payload: SchemaPayload, db: Session = Depends(get_db)):
    hw = SettingsService.update_hardware_schema(db, hardware_id, payload.schema)
    return {"hardware_id": hardware_id, "schema": SettingsService.get_hardware_schema(hw)}


@router.get("/device/{device_id}")
@require_admin
def get_device_settings(device_id: int, db: Session = Depends(get_db)):
    device = db.query(ESP32Device).filter(ESP32Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    schema = SettingsService.get_hardware_schema(device.hardware) if device.hardware else {"sections": []}
    overrides = SettingsService.get_device_overrides(device)
    effective = SettingsService.get_effective_settings(device)
    return {
        "device_id": device_id,
        "schema": schema,
        "overrides": overrides,
        "effective": effective,
        "last_updated_at": device.last_settings_updated_at.isoformat() if device.last_settings_updated_at else None,
    }


@router.put("/device/{device_id}")
@require_admin
def update_device_settings(device_id: int, payload: OverridesPayload, db: Session = Depends(get_db)):
    device = SettingsService.update_device_overrides(db, device_id, payload.overrides)
    schema = SettingsService.get_hardware_schema(device.hardware) if device.hardware else {"sections": []}
    overrides = SettingsService.get_device_overrides(device)
    effective = SettingsService.get_effective_settings(device)
    return {
        "device_id": device_id,
        "schema": schema,
        "overrides": overrides,
        "effective": effective,
        "last_updated_at": device.last_settings_updated_at.isoformat() if device.last_settings_updated_at else None,
    }
