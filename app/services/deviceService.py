import re

from fastapi import HTTPException
from sqlalchemy.orm import Session, subqueryload

from app.orm_models.auth import User
from app.orm_models.board import Board, Led, LedStrip
from app.orm_models.device import ESP32Device


class DeviceService:
    @staticmethod
    def _parse_color_to_rgb(color: str | None) -> list[int]:
        if not color:
            return [0, 255, 0]

        value = color.strip().lower()
        if value.startswith("#") and len(value) == 7:
            try:
                return [int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)]
            except ValueError:
                return [0, 255, 0]

        return [0, 255, 0]

    @staticmethod
    def get_connected_devices(current_user: User, db: Session):
        esp = db.query(ESP32Device).filter_by(owner_id=current_user.id).all()
        boards = db.query(Board).filter_by(owner_id=current_user.id).all()
        return {"esp_devices": esp, "boards": boards}

    @staticmethod
    def delete_esp_device(esp_id: int, current_user: User, db: Session):
        device = db.query(ESP32Device).filter_by(id=esp_id, owner_id=current_user.id).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found or not owned by the user.")
        db.delete(device)
        db.commit()
        return {"message": "Device deleted successfully."}

    @staticmethod
    def register_device_by_account(mac_address: str, name: str, current_user: User, db: Session):
        if not mac_address:
            raise HTTPException(status_code=400, detail="MAC address is required.")

        mac_address = mac_address.lower().strip()
        if not re.fullmatch(r"[0-9a-f]{12}", mac_address):
            raise HTTPException(status_code=400, detail="Invalid MAC address. Must be 12 hex characters (0-9, a-e).")

        formatted_mac = ":".join(mac_address[i : i + 2] for i in range(0, 12, 2))

        if name:
            name = name.strip()
            if len(name) > 100:
                raise HTTPException(status_code=400, detail="Device name too long (max 100 characters).")

        existing = db.query(ESP32Device).filter_by(mac_address=formatted_mac).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"MAC address already registered. Device ID: {existing.id}")

        if name:
            same_name = db.query(ESP32Device).filter_by(owner_id=current_user.id, name=name).first()
            if same_name:
                raise HTTPException(status_code=409, detail=f'You already have a device named "{name}".')

        new_device = ESP32Device(mac_address=formatted_mac, name=name, owner_id=current_user.id)
        db.add(new_device)
        db.commit()
        db.refresh(new_device)
        return {"message": "Device registered successfully.", "id": new_device.id}

    @staticmethod
    def link_device_to_board(esp_id: int, board_id: int, current_user: User, db: Session):
        if not esp_id or not board_id:
            raise HTTPException(status_code=400, detail="Both ESP ID and board ID are required.")

        esp = db.query(ESP32Device).filter_by(id=esp_id, owner_id=current_user.id).first()
        board = db.query(Board).filter_by(id=board_id, owner_id=current_user.id).first()
        if not esp or not board:
            raise HTTPException(status_code=404, detail="Invalid ESP32 device or board.")

        esp.board_id = board.id
        db.commit()
        return {"message": "ESP32 device linked to board successfully."}

    @staticmethod
    def unlink_device_from_board(esp_id: int, current_user: User, db: Session):
        if not esp_id:
            raise HTTPException(status_code=400, detail="ESP ID is required.")

        esp = db.query(ESP32Device).filter_by(id=esp_id, owner_id=current_user.id).first()
        if not esp:
            raise HTTPException(status_code=404, detail="Invalid ESP32 device.")

        esp.board_id = None
        db.commit()
        return {"message": "ESP32 device unlinked from board successfully."}

    @staticmethod
    def get_ledstrip_status(mac: str, db: Session):
        if not mac:
            raise HTTPException(status_code=400, detail="MAC address is required.")

        mac = mac.strip().lower()
        if re.fullmatch(r"[0-9a-f]{12}", mac):
            mac = ":".join(mac[i : i + 2] for i in range(0, 12, 2))

        esp = db.query(ESP32Device).filter(ESP32Device.mac_address == mac).first()
        if not esp or not esp.board:
            raise HTTPException(status_code=401, detail="Invalid or unlinked ESP32 device.")

        board = (
            db.query(Board)
            .options(
                subqueryload(Board.led_strips)
                .subqueryload(LedStrip.leds)
                .subqueryload(Led.trip_stops)
            )
            .filter(Board.id == esp.board_id)
            .first()
        )

        if not board:
            raise HTTPException(status_code=404, detail="Linked board not found")

        strips_sorted = sorted(board.led_strips, key=lambda s: ((s.order_index or 0), s.id or 0))
        response_data = []

        for idx, strip in enumerate(strips_sorted, start=1):
            leds_sorted = sorted(strip.leds, key=lambda led: (led.ledstrip_index or 0, led.id or 0))
            rgb_array = []
            for led in leds_sorted:
                vehicle_incoming = any(ts.vehicle_incoming for ts in led.trip_stops)
                rgb_array.append(DeviceService._parse_color_to_rgb(led.led_color) if vehicle_incoming else [0, 0, 0])

            response_data.append(
                {
                    "id": strip.id,
                    "h": strip.order_index if strip.order_index is not None else idx,
                    "v": rgb_array,
                }
            )

        return {"strips": response_data}
