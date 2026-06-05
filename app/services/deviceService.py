import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.orm_models.auth import User
from app.orm_models.board import Board
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
        # Import here to avoid circular dependency
        from app.services.boardService import BoardService

        if not mac:
            raise HTTPException(status_code=400, detail="MAC address is required.")

        mac = mac.strip().lower()
        if re.fullmatch(r"[0-9a-f]{12}", mac):
            mac = ":".join(mac[i : i + 2] for i in range(0, 12, 2))

        esp = db.query(ESP32Device).filter(ESP32Device.mac_address == mac).first()
        if not esp or not esp.board:
            raise HTTPException(status_code=401, detail="Invalid or unlinked ESP32 device.")

        board = db.query(Board).filter(Board.id == esp.board_id).first()
        if not board:
            raise HTTPException(status_code=404, detail="Linked board not found")

        # Reuse the canonical LED-state logic — single source of truth for isOn.
        strips_data = BoardService._build_led_strips_data(board, db)

        response_data = []
        for idx, strip in enumerate(strips_data, start=1):
            rgb_array = [
                DeviceService._parse_color_to_rgb(led.get("ledColor")) if led.get("isOn") else [0, 0, 0]
                for led in strip.get("leds", [])
            ]
            response_data.append({
                "id": strip["id"],
                "h":  strip.get("orderIndex") if strip.get("orderIndex") is not None else idx,
                "v":  rgb_array,
            })

        return {"strips": response_data}
