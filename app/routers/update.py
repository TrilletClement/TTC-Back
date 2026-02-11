from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.updateService import UpdateService

router = APIRouter(prefix="/api/update", tags=["update"])


class UpdateRequest(BaseModel):
    hardware: str
    mac: str


@router.post("/versions")
async def get_update_versions(payload: UpdateRequest):
    print(f"[DEBUG] Received OTA request: hardware={payload.hardware}, mac={payload.mac}")
    
    version_info = UpdateService.get_version_info(payload.hardware, payload.mac)
    
    print(f"[DEBUG] Version info found: {version_info}")
    
    if not version_info:
        print("[DEBUG] No version info - returning 404")
        raise HTTPException(status_code=404, detail="No update info found")
    
    filename = version_info.get("package_file")
    package_url = f"https://transport.trillet.be/api/update/package/{filename}"
    
    result = {
        "app_version": version_info.get("app_version"),  # Changed from "version"
        "app_url": package_url
    }
    
    print(f"[DEBUG] Returning: {result}")
    return result


@router.get("/package/{filename}")
def get_package(filename: str):
    return UpdateService.get_package_file(filename)

