from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.api.services.updateService import UpdateService

router = APIRouter(prefix="/api/update", tags=["update"])


class UpdateRequest(BaseModel):
    hardware: str
    mac: str


@router.post("/versions")
def get_update_versions(payload: UpdateRequest):
    version_info = UpdateService.get_version_info(payload.hardware, payload.mac)

    if not version_info:
        raise HTTPException(
            status_code=404,
            detail="No update info found for this hardware/mac"
        )

    package_url = f"https://transport.trillet.be/api/update/package/{version_info['package_file']}"

    return {
        "app_version": version_info["app_version"],
        "app_url": package_url
    }


@router.get("/package/{filename}")
def get_package(filename: str):
    return UpdateService.get_package_file(filename)
