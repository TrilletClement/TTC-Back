import json
import os
import shutil
from fastapi import HTTPException, UploadFile
from typing import Optional

VERSIONS_FILE = os.environ.get("VERSIONS_FILE", "versions.json")
PACKAGES_DIR = os.environ.get("PACKAGES_DIR", "packages")


class AdminOtaService:

    @staticmethod
    def load_versions() -> dict:
        if not os.path.exists(VERSIONS_FILE):
            return {"default": {}, "exceptions": {}}
        with open(VERSIONS_FILE, "r") as f:
            return json.load(f)

    @staticmethod
    def save_versions(data: dict):
        with open(VERSIONS_FILE, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def get_versions() -> dict:
        return AdminOtaService.load_versions()

    @staticmethod
    async def upload_firmware(
        file: UploadFile,
        hardware: str,
        app_version: str,
        mac_exception: Optional[str] = None,
    ) -> dict:
        if not file.filename.endswith(".bin"):
            raise HTTPException(status_code=400, detail="Only .bin files are accepted")

        os.makedirs(PACKAGES_DIR, exist_ok=True)
        dest_path = os.path.join(PACKAGES_DIR, file.filename)

        with open(dest_path, "wb") as out:
            shutil.copyfileobj(file.file, out)

        versions = AdminOtaService.load_versions()
        entry = {"app_version": app_version, "package_file": file.filename}

        if mac_exception:
            versions.setdefault("exceptions", {})[mac_exception] = entry
        else:
            versions.setdefault("default", {})[hardware] = entry

        AdminOtaService.save_versions(versions)

        return {
            "message": "Firmware uploaded and registered successfully",
            "filename": file.filename,
            "hardware": hardware,
            "app_version": app_version,
            "mac_exception": mac_exception,
        }

    @staticmethod
    def delete_version(
        hardware: Optional[str],
        mac_exception: Optional[str],
        delete_file: bool,
    ) -> dict:
        versions = AdminOtaService.load_versions()
        deleted_entry = None

        if mac_exception:
            deleted_entry = versions.get("exceptions", {}).pop(mac_exception, None)
        elif hardware:
            deleted_entry = versions.get("default", {}).pop(hardware, None)
        else:
            raise HTTPException(status_code=400, detail="Provide hardware or mac_exception")

        if not deleted_entry:
            raise HTTPException(status_code=404, detail="Version entry not found")

        AdminOtaService.save_versions(versions)

        if delete_file:
            pkg_path = os.path.join(PACKAGES_DIR, deleted_entry["package_file"])
            if os.path.exists(pkg_path):
                os.remove(pkg_path)

        return {"message": "Version entry deleted", "entry": deleted_entry}

    @staticmethod
    def list_firmware_files() -> dict:
        os.makedirs(PACKAGES_DIR, exist_ok=True)
        files = [
            {
                "filename": f,
                "size_kb": round(os.path.getsize(os.path.join(PACKAGES_DIR, f)) / 1024, 1)
            }
            for f in os.listdir(PACKAGES_DIR)
            if f.endswith(".bin")
        ]
        return {"files": files}