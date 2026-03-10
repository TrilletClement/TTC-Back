from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from app.services.deviceService import DeviceService
from app.core.security.jwt import get_current_user
from app.orm_models.db import get_db
from app.orm_models.auth import User
import re

router = APIRouter(prefix="/api", tags=["devices"])

class DeviceRegister(BaseModel):
    mac_address: str
    name: str | None = None

class DeviceLink(BaseModel):
    esp_id: int
    board_id: int


class LedStripStatusRow(BaseModel):
    id: int
    h: int = Field(..., description="Row index/order")
    v: list[list[int]] = Field(
        ...,
        description="Per-LED RGB states for this row, e.g. [[0,255,0],[0,0,0],...]",
    )


class LedStripStatusResponse(BaseModel):
    strips: list[LedStripStatusRow]


def _normalize_mac(mac: str) -> str:
    mac = (mac or "").strip()
    if re.fullmatch(r"[0-9a-fA-F]{12}", mac):
        return ":".join(mac[i : i + 2] for i in range(0, 12, 2)).lower()
    if re.fullmatch(r"[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}", mac):
        return mac.lower()
    raise HTTPException(status_code=400, detail="Invalid MAC format")

@router.post("/register_device_mac")
def register_device_by_mac(
    device_data: DeviceRegister,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return DeviceService.register_device_by_account(
        device_data.mac_address,
        device_data.name,
        current_user,
        db
    )

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

@router.post("/link-device-board")
def link_device_to_board(
    link_data: DeviceLink,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return DeviceService.link_device_to_board(
        link_data.esp_id,
        link_data.board_id,
        current_user,
        db
    )

@router.post("/unlink-device-board/{esp_id}")
def unlink_device_from_board(
    esp_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return DeviceService.unlink_device_from_board(esp_id, current_user, db)

@router.get(
    "/esp/ledstrips",
    response_model=LedStripStatusResponse,
    summary="Get LED strips state for ESP (RGB per LED)",
)
def get_ledstrip_status(
    mac: str = Query(..., description="ESP MAC address, 12-hex or colon-separated"),
    db: Session = Depends(get_db)
):
    normalized_mac = _normalize_mac(mac)
    return DeviceService.get_ledstrip_status(normalized_mac, db)
