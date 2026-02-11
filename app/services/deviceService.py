from sqlalchemy.orm import subqueryload, Session
from fastapi import HTTPException, status
from app.orm_models.auth import User
from app.orm_models.board import Board, Led, LedStrip
from app.orm_models.device import ESP32Device
import re

class DeviceService:

    @staticmethod
    def get_connected_devices(current_user: User, db: Session):
        esp = db.query(ESP32Device).filter_by(owner_id=current_user.id).all()
        boards = db.query(Board).filter_by(owner_id=current_user.id).all()
        return {
            'esp_devices': esp,
            'boards': boards
        }

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
        if not re.fullmatch(r'[0-9a-f]{12}', mac_address):
            raise HTTPException(status_code=400, detail="Invalid MAC address. Must be 12 hex characters (0-9, a-e).")

        formatted_mac = ':'.join(mac_address[i:i+2] for i in range(0, 12, 2))

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

        esp = db.query(ESP32Device).filter(ESP32Device.mac_address == mac).first()
        if not esp or not esp.board:
            raise HTTPException(status_code=401, detail="Invalid or unlinked ESP32 device.")

        led_options = [subqueryload(getattr(LedStrip, f"led{i}_obj")).subqueryload(Led.trip_stops) for i in range(1, 13)]
        board = db.query(Board).options(subqueryload(Board.led_strips).options(*led_options)).filter(Board.id == esp.board_id).first()

        if not board:
            raise HTTPException(status_code=404, detail="Linked board not found")

        strips_sorted = sorted(board.led_strips, key=lambda s: ((s.order_index or 0), s.id or 0))
        response_data = []

        for idx, strip in enumerate(strips_sorted, start=1):
            bool_array = []
            for i in range(1, 13):
                led_obj = getattr(strip, f"led{i}_obj")
                if not led_obj:
                    bool_array.append(0)
                    continue
                vehicle_incoming = any(ts.vehicle_incoming for ts in led_obj.trip_stops)
                bool_array.append(1 if vehicle_incoming else 0)
            response_data.append({
                'id': strip.id,
                'h': strip.order_index if strip.order_index is not None else idx,
                'v': bool_array
            })

        return {'strips': response_data}
