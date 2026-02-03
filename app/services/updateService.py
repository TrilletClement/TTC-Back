import os
import json
from fastapi import HTTPException
from fastapi.responses import FileResponse


class UpdateService:
    # Paths moved to fastapi-server/static/*
    _FASTAPI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    PACKAGE_DIR = os.path.join(_FASTAPI_ROOT, "static", "packages")
    PACKAGE_VERSION_FILE = os.path.join(_FASTAPI_ROOT, "static", "package-version.json")

    @staticmethod
    def get_version_info(hardware: str, mac: str):
        try:
            with open(UpdateService.PACKAGE_VERSION_FILE) as f:
                data = json.load(f)
        except Exception:
            return None

        mac = mac.upper()

        if mac in data.get("exceptions", {}):
            return data["exceptions"][mac]

        return data.get("default", {}).get(hardware)

    @staticmethod
    def get_package_file(filename: str):
        try:
            with open(UpdateService.PACKAGE_VERSION_FILE) as f:
                packages = json.load(f)
        except Exception:
            raise HTTPException(status_code=500, detail="Version file not readable")

        allowed_files = set()

        for hw in packages.get("default", {}).values():
            if hw.get("package_file"):
                allowed_files.add(hw["package_file"])

        for exc in packages.get("exceptions", {}).values():
            if exc.get("package_file"):
                allowed_files.add(exc["package_file"])

        if filename not in allowed_files:
            raise HTTPException(status_code=403, detail="Access forbidden")

        path = os.path.join(UpdateService.PACKAGE_DIR, filename)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Package not found")

        return FileResponse(
            path,
            media_type="application/octet-stream",
            filename=filename
        )
