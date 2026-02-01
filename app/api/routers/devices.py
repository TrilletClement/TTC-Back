from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.api.services.deviceService import DeviceService
from app.core.security.jwt import get_current_user
from shared.db import get_db
from shared.models import User
import re

router = APIRouter(prefix="/api", tags=["devices"])

@router.get("/esp-devices")
def get_esp_devices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    devices = DeviceService.get_connected_devices(current_user, db)["esp_devices"]
    return [d.to_dict() for d in devices]

@router.delete("/esp-devices/{esp_id}")
def delete_esp_device(
    esp_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return DeviceService.delete_esp_device(esp_id, current_user, db)

@router.get("/esp/ledstrips")
def get_ledstrip_status(
    mac: str = Query(...),
    db: Session = Depends(get_db)
):
    if re.fullmatch(r"[0-9a-fA-F]{12}", mac):
        mac = ":".join(mac[i:i+2] for i in range(0, 12, 2)).lower()

    return DeviceService.get_ledstrip_status(mac, db)