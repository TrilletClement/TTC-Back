from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.orm_models.device import ESP32Device, FirmwarePackage, Hardware
from app.orm_models.board import Board
from app.orm_models.order import Order

router = APIRouter(prefix="/api/admin/devices", tags=["admin-devices"])


class FirmwareOut(BaseModel):
    id: int
    filename: str


class HardwareOut(BaseModel):
    id: int
    hardware_type: str


class OrderOut(BaseModel):
    id: int
    status: str
    created_at: Optional[datetime]


class BoardOut(BaseModel):
    id: int
    name: str
    orders: list[OrderOut]


class DevicePatch(BaseModel):
    name: Optional[str] = None
    owner_email: Optional[str] = None
    board_id: Optional[int] = None
    unlink_board: bool = False
    target_firmware_id: Optional[int] = None
    clear_target_firmware: bool = False
    hardware_id: Optional[int] = None


class BoardListOut(BaseModel):
    id: int
    name: str
    owner_email: Optional[str]


class DeviceAdminOut(BaseModel):
    id: int
    mac_address: str
    name: Optional[str]
    owner_email: Optional[str]
    board: Optional[BoardOut]
    hardware: Optional[HardwareOut]
    current_firmware: Optional[FirmwareOut]
    current_firmware_version: Optional[str]
    target_firmware: Optional[FirmwareOut]
    version_updater: Optional[str]
    running_partition: Optional[str]
    boot_partition: Optional[str]
    update_partition: Optional[str]
    ota_state: Optional[str]
    last_connected: Optional[datetime]
    last_ota_check: Optional[datetime]
    registered_at: Optional[datetime]


@router.get("", response_model=list[DeviceAdminOut])
@require_admin
def list_all_devices(db: Session = Depends(get_db)):
    devices = db.query(ESP32Device).order_by(ESP32Device.registered_at.desc().nullslast()).all()

    result = []
    for d in devices:
        board_out = None
        if d.board:
            orders = db.query(Order).filter(Order.board_id == d.board_id).order_by(Order.created_at.desc()).all()
            board_out = BoardOut(
                id=d.board.id,
                name=d.board.name,
                orders=[OrderOut(id=o.id, status=o.status, created_at=o.created_at) for o in orders],
            )

        result.append(DeviceAdminOut(
            id=d.id,
            mac_address=d.mac_address,
            name=d.name,
            owner_email=d.owner.email if d.owner else None,
            board=board_out,
            hardware=HardwareOut(
                id=d.hardware.id,
                hardware_type=d.hardware.hardware_type,
            ) if d.hardware else None,
            current_firmware=FirmwareOut(
                id=d.current_firmware.id,
                filename=d.current_firmware.filename,
            ) if d.current_firmware else None,
            current_firmware_version=d.current_firmware_version,
            target_firmware=FirmwareOut(
                id=d.target_firmware.id,
                filename=d.target_firmware.filename,
            ) if d.target_firmware else None,
            version_updater=d.version_updater,
            running_partition=d.running_partition,
            boot_partition=d.boot_partition,
            update_partition=d.update_partition,
            ota_state=d.ota_state,
            last_connected=d.last_connected,
            last_ota_check=d.last_ota_check,
            registered_at=d.registered_at,
        ))

    return result


@router.get("/users", response_model=list[str])
@require_admin
def list_all_user_emails(db: Session = Depends(get_db)):
    from app.orm_models.auth import User as UserModel
    users = db.query(UserModel.email).order_by(UserModel.email).all()
    return [u.email for u in users]


@router.get("/boards", response_model=list[BoardListOut])
@require_admin
def list_boards(owner_email: Optional[str] = None, db: Session = Depends(get_db)):
    from app.orm_models.auth import User as UserModel
    query = db.query(Board)
    if owner_email:
        user = db.query(UserModel).filter(UserModel.email == owner_email).first()
        if user:
            query = query.filter(Board.owner_id == user.id)
        else:
            return []
    boards = query.order_by(Board.name).all()
    return [
        BoardListOut(id=b.id, name=b.name, owner_email=b.owner.email if b.owner else None)
        for b in boards
    ]


@router.patch("/{device_id}", response_model=DeviceAdminOut)
@require_admin
def patch_device(device_id: int, payload: DevicePatch, db: Session = Depends(get_db)):
    device = db.query(ESP32Device).filter(ESP32Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    if payload.name is not None:
        device.name = payload.name.strip() or None

    if payload.owner_email is not None:
        from app.orm_models.auth import User as UserModel
        user = db.query(UserModel).filter(UserModel.email == payload.owner_email).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{payload.owner_email}' not found")
        device.owner_id = user.id

    if payload.unlink_board:
        device.board_id = None
    elif payload.board_id is not None:
        board = db.query(Board).filter(Board.id == payload.board_id).first()
        if not board:
            raise HTTPException(status_code=404, detail="Board not found")
        device.board_id = payload.board_id

    if payload.clear_target_firmware:
        device.target_firmware_id = None
    elif payload.target_firmware_id is not None:
        pkg = db.query(FirmwarePackage).filter(FirmwarePackage.id == payload.target_firmware_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Firmware package not found")
        device.target_firmware_id = payload.target_firmware_id

    if payload.hardware_id is not None:
        hw = db.query(Hardware).filter(Hardware.id == payload.hardware_id).first()
        if not hw:
            raise HTTPException(status_code=404, detail="Hardware type not found")
        device.hardware_id = payload.hardware_id

    db.commit()
    db.refresh(device)

    board_out = None
    if device.board:
        orders = db.query(Order).filter(Order.board_id == device.board_id).order_by(Order.created_at.desc()).all()
        board_out = BoardOut(
            id=device.board.id,
            name=device.board.name,
            orders=[OrderOut(id=o.id, status=o.status, created_at=o.created_at) for o in orders],
        )

    return DeviceAdminOut(
        id=device.id,
        mac_address=device.mac_address,
        name=device.name,
        owner_email=device.owner.email if device.owner else None,
        board=board_out,
        hardware=HardwareOut(
            id=device.hardware.id,
            hardware_type=device.hardware.hardware_type,
        ) if device.hardware else None,
        current_firmware=FirmwareOut(
            id=device.current_firmware.id,
            filename=device.current_firmware.filename,
        ) if device.current_firmware else None,
        current_firmware_version=device.current_firmware_version,
        target_firmware=FirmwareOut(
            id=device.target_firmware.id,
            filename=device.target_firmware.filename,
        ) if device.target_firmware else None,
        version_updater=device.version_updater,
        running_partition=device.running_partition,
        boot_partition=device.boot_partition,
        update_partition=device.update_partition,
        ota_state=device.ota_state,
        last_connected=device.last_connected,
        last_ota_check=device.last_ota_check,
        registered_at=device.registered_at,
    )
