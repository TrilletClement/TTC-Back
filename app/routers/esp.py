from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import subqueryload
from shared.db import get_db
from shared.models import Board, LedStrip, Led, ESP32Device  # Added ESP32Device
from .schemas import LedStripStatusResponse, LedStripCompact

router = APIRouter(prefix="/esp", tags=["esp"])

@router.get("/ledstrips", response_model=LedStripStatusResponse)
def get_ledstrip_status(mac: str = Query(..., description="MAC address of the ESP32 device")):
    with get_db() as db:
        # Find ESP32Device by MAC
        esp = db.query(ESP32Device).filter(ESP32Device.mac_address == mac).first()
        if not esp or not esp.board:
            raise HTTPException(status_code=401, detail="Invalid or unlinked ESP32 device")

        # Fetch the Board with all its led_strips and related LEDs + trip stops
        led_options = [
            subqueryload(getattr(LedStrip, f"led{i}_obj")).subqueryload(Led.trip_stops)
            for i in range(1, 13)
        ]
        board = db.query(Board).options(
            subqueryload(Board.led_strips).options(*led_options)
        ).filter(Board.id == esp.board_id).first()

        if not board:
            raise HTTPException(status_code=404, detail="Linked board not found")

        response_data = []
        for strip in board.led_strips:
            bool_array = []
            for i in range(1, 13):
                led_obj = getattr(strip, f"led{i}_obj")
                if not led_obj:
                    bool_array.append(0)
                    continue
                vehicle_incoming = any(ts.vehicle_incoming for ts in led_obj.trip_stops)
                bool_array.append(1 if vehicle_incoming else 0)
            response_data.append(LedStripCompact(id=strip.id, v=bool_array))

        return LedStripStatusResponse(strips=response_data)
