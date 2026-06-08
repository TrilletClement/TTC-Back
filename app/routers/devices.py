import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import re

from app.core.security.device_auth import get_device_from_mac
from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.orm_models.device import ESP32Device
from app.services.deviceService import DeviceService

router = APIRouter(prefix="/api", tags=["devices"])


class DeviceLink(BaseModel):
    esp_id: int
    board_id: int


class DeviceRename(BaseModel):
    name: str | None = None


class DeviceLuminosity(BaseModel):
    light_intensity_percent: float


class LedStripStatusRow(BaseModel):
    id: int
    h: int = Field(..., description="Row index/order")
    v: list[list[int]] = Field(
        ...,
        description="Per-LED RGB states for this row, e.g. [[0,255,0],[0,0,0],...]",
    )


class LedStripStatusResponse(BaseModel):
    strips: list[LedStripStatusRow]
    settings_updated_at: Optional[str] = None


def _normalize_mac(mac: str) -> str:
    mac = (mac or "").strip()
    if re.fullmatch(r"[0-9a-fA-F]{12}", mac):
        return ":".join(mac[i : i + 2] for i in range(0, 12, 2)).lower()
    if re.fullmatch(r"[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}", mac):
        return mac.lower()
    raise HTTPException(status_code=400, detail="Invalid MAC format")


@router.get("/esp-devices")
@require_user
def get_esp_devices(current_user: User, db: Session = Depends(get_db)):
    devices = DeviceService.get_connected_devices(current_user, db)["esp_devices"]
    return [d.to_dict() for d in devices]


@router.patch("/esp-devices/{esp_id}/name")
@require_user
def rename_esp_device(esp_id: int, body: DeviceRename, current_user: User, db: Session = Depends(get_db)):
    device = db.query(ESP32Device).filter_by(id=esp_id, owner_id=current_user.id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")
    device.name = body.name.strip() if body.name else None
    db.commit()
    return {"id": device.id, "name": device.name}


@router.post("/link-device-board")
@require_user
def link_device_to_board(
    link_data: DeviceLink,
    current_user: User,
    db: Session = Depends(get_db),
):
    return DeviceService.link_device_to_board(
        link_data.esp_id,
        link_data.board_id,
        current_user,
        db,
    )


@router.get("/esp-devices/{esp_id}/settings")
@require_user
def get_device_luminosity(esp_id: int, current_user: User, db: Session = Depends(get_db)):
    device = db.query(ESP32Device).filter_by(id=esp_id, owner_id=current_user.id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")
    from app.services.settingsService import SettingsService
    effective = SettingsService.get_effective_settings(device)
    return {"light_intensity_percent": effective.get("light_intensity_percent", 100.0)}


@router.patch("/esp-devices/{esp_id}/settings")
@require_user
def patch_device_luminosity(esp_id: int, body: DeviceLuminosity, current_user: User, db: Session = Depends(get_db)):
    device = db.query(ESP32Device).filter_by(id=esp_id, owner_id=current_user.id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")
    import json as _json
    overrides = _json.loads(device.json_settings_override or '{}')
    overrides['light_intensity_percent'] = max(0.0, min(100.0, body.light_intensity_percent))
    device.json_settings_override = _json.dumps(overrides)
    device.last_settings_updated_at = datetime.datetime.utcnow()
    db.commit()
    return {"light_intensity_percent": overrides['light_intensity_percent']}


@router.post("/unlink-device-board/{esp_id}")
@require_user
def unlink_device_from_board(esp_id: int, current_user: User, db: Session = Depends(get_db)):
    return DeviceService.unlink_device_from_board(esp_id, current_user, db)


@router.get(
    "/esp/ledstrips",
    response_model=LedStripStatusResponse,
    summary="Get LED strips state for ESP (RGB per LED)",
)
def get_ledstrip_status(
    db: Session = Depends(get_db),
    device: ESP32Device = Depends(get_device_from_mac),
):
    """LED strip state polled by ESP32 hardware — requires a device cert (Apache gate) and X-Device-Mac header."""
    device.last_connected = datetime.datetime.utcnow()
    db.commit()
    return DeviceService.get_ledstrip_status(device.mac_address, db)


@router.get("/esp/settings", summary="Get effective device settings")
def get_esp_settings(
    db: Session = Depends(get_db),
    device: ESP32Device = Depends(get_device_from_mac),
):
    """Device settings merged from hardware defaults + device overrides."""
    from app.services.settingsService import SettingsService
    return SettingsService.get_effective_settings(device)
