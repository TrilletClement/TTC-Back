from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import joinedload, subqueryload
from shared.db import get_db
from shared.models import Device, LedStrip, Led
from .schemas import LedStripStatusResponse, LedStripCompact  # Update this schema accordingly if needed

router = APIRouter(prefix="/esp", tags=["esp"])

@router.get("/ledstrips", response_model=LedStripStatusResponse)
def get_ledstrip_status(token: str = Query(..., description="Permanent token for device auth")):
    with get_db() as db:
        # Dynamically joinload led1_obj to led12_obj with trip_stops
        led_options = [
            subqueryload(getattr(LedStrip, f"led{i}_obj")).subqueryload(Led.trip_stops)
            for i in range(1, 13)
        ]
        #print(f"LED options: {led_options}")
        device = db.query(Device).options(
            subqueryload(Device.led_strips).options(*led_options)
        ).filter(Device.permanent_token == token).first()

        if not device:
            raise HTTPException(status_code=401, detail="Invalid or unknown device token")

        response_data = []
        for strip in device.led_strips:
            #print(f"Processing strip ID: {strip.id}")
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
