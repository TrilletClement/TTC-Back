from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.orm_models.db import get_db
from app.services.updateService import UpdateService

router = APIRouter(prefix="/api/update", tags=["update"])


class UpdateRequest(BaseModel):
    hardware: str
    mac: str
    hardware_version: Optional[str] = None
    firmware_name: Optional[str] = None
    current_version: Optional[str] = None


@router.post("/versions")
async def get_update_versions(payload: UpdateRequest, db: Session = Depends(get_db)):
    version_info = UpdateService.get_version_info(
        db=db,
        hardware=payload.hardware,
        mac=payload.mac,
        hardware_version=payload.hardware_version,
        firmware_name=payload.firmware_name,
        current_version=payload.current_version,
    )

    if not version_info:
        raise HTTPException(status_code=404, detail="No update info found")

    return {
        "app_version": version_info.get("app_version"),
        "app_url": version_info.get("app_url"),
        "firmware_name": version_info.get("firmware_name"),
        "hardware": version_info.get("hardware_type"),
        "hardware_version": version_info.get("hardware_version"),
    }


@router.get("/package/{filename}")
def get_package(filename: str, db: Session = Depends(get_db)):
    return UpdateService.get_package_file(db, filename)
