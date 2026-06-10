import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security.device_auth import get_device_from_mac
from app.core.user_access import require_user
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.orm_models.device import ESP32Device
from app.repositories.device_repo import DeviceRepository
from app.schemas.device import DeviceLink, DeviceRename, DeviceLuminosity, LedStripStatusResponse
from app.services.deviceService import DeviceService


router = APIRouter(prefix="/api", tags=["devices"])


def get_service(db: Session = Depends(get_db)) -> DeviceService:
    return DeviceService(DeviceRepository(db))


@router.get("/esp-devices")
@require_user
def get_esp_devices(current_user: User, svc: DeviceService = Depends(get_service)):
    devices = svc.get_connected_devices(current_user)["esp_devices"]
    return [d.to_dict() for d in devices]


@router.patch("/esp-devices/{esp_id}/name")
@require_user
def rename_esp_device(esp_id: int, body: DeviceRename, current_user: User, svc: DeviceService = Depends(get_service)):
    return svc.rename_device(esp_id, body.name, current_user)


@router.post("/link-device-board")
@require_user
def link_device_to_board(payload: DeviceLink, current_user: User, svc: DeviceService = Depends(get_service)):
    return svc.link_device_to_board(payload.esp_id, payload.board_id, current_user)


@router.post("/unlink-device-board/{esp_id}")
@require_user
def unlink_device_from_board(esp_id: int, current_user: User, svc: DeviceService = Depends(get_service)):
    return svc.unlink_device_from_board(esp_id, current_user)


@router.get("/esp-devices/{esp_id}/settings")
@require_user
def get_device_luminosity(esp_id: int, current_user: User, svc: DeviceService = Depends(get_service)):
    return svc.get_luminosity(esp_id, current_user)


@router.patch("/esp-devices/{esp_id}/settings")
@require_user
def patch_device_luminosity(esp_id: int, body: DeviceLuminosity, current_user: User, svc: DeviceService = Depends(get_service)):
    return svc.patch_luminosity(esp_id, body.light_intensity_percent, current_user)


@router.get("/esp/ledstrips", response_model=LedStripStatusResponse)
def get_ledstrip_status(
    db: Session = Depends(get_db),
    device: ESP32Device = Depends(get_device_from_mac),
):
    svc = DeviceService(DeviceRepository(db))
    device.last_connected = datetime.datetime.utcnow()
    db.commit()
    return svc.get_ledstrip_status(device.mac_address)


@router.get("/esp/settings")
def get_esp_settings(
    db: Session = Depends(get_db),
    device: ESP32Device = Depends(get_device_from_mac),
):
    from app.services.adminSettingsService import adminSettingsService
    return adminSettingsService.get_effective_settings(device)