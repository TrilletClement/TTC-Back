import os
import re
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.update_repo import UpdateRepository


class UpdateService:
    PACKAGE_BASE_URL = os.environ.get("OTA_PACKAGE_BASE_URL", "https://esp.trillet.be")

    # Packages are named "<firmware_name>-v<version>.bin" (see build_target.sh on the
    # device side). Devices report their running version as the bare semver (e.g.
    # "1.0.8"), so app_version must be extracted, not left as the full filename —
    # otherwise it can never string-equal current_version and the device treats
    # every check as a newer version, including immediately after updating.
    _VERSION_RE = re.compile(r"-v([^-]+)\.bin$")

    @staticmethod
    def normalize_mac(mac: str) -> str:
        value = (mac or "").strip().lower().replace("-", ":")
        if len(value) == 12 and ":" not in value:
            value = ":".join(value[i:i + 2] for i in range(0, 12, 2))
        return value

    @staticmethod
    def _pkg_url(filename: str) -> str:
        return f"{UpdateService.PACKAGE_BASE_URL}/api/update/package/{filename}"

    @staticmethod
    def _serialize(pkg) -> dict:
        match = UpdateService._VERSION_RE.search(pkg.filename)
        version = match.group(1) if match else pkg.filename
        return {
            "package_id":    pkg.id,
            "app_version":   version,
            "app_url":       UpdateService._pkg_url(pkg.filename),
            "package_file":  pkg.filename,
            "firmware_name": pkg.filename,
        }

    @staticmethod
    def get_version_info(
        db: Session,
        hardware: str,
        mac: str,
        hardware_version: Optional[str] = None,
        firmware_name: Optional[str] = None,
        current_version: Optional[str] = None,
        running_partition: Optional[str] = None,
        boot_partition: Optional[str] = None,
        update_partition: Optional[str] = None,
        ota_state: Optional[str] = None,
    ) -> Optional[dict]:
        repo = UpdateRepository(db)
        normalized_mac = UpdateService.normalize_mac(mac)
        hardware_type  = (hardware or "").strip()

        device = repo.get_device_by_mac(normalized_mac) if normalized_mac else None
        hw = repo.get_hardware_by_type(hardware_type)

        if device:
            if hw:
                device.hardware_id = hw.id
            if current_version:
                device.current_firmware_version = current_version
            if running_partition is not None:
                device.running_partition = running_partition
            if boot_partition is not None:
                device.boot_partition = boot_partition
            if update_partition is not None:
                device.update_partition = update_partition
            if ota_state is not None:
                device.ota_state = ota_state
            if firmware_name and current_version:
                expected = f"{firmware_name}-v{current_version}.bin"
                cur_pkg = repo.get_firmware_by_filename(expected)
                if cur_pkg:
                    device.current_firmware_id = cur_pkg.id
            now = datetime.utcnow()
            device.last_ota_check = now
            device.last_connected = now
            repo.commit()

        pkg = None
        if device and device.target_firmware_id:
            pkg = repo.get_active_firmware_by_id(device.target_firmware_id)
        if not pkg and hw and hw.firmware_package_id:
            pkg = repo.get_active_firmware_by_id(hw.firmware_package_id)

        # No firmware assigned anywhere (device override or hardware default) —
        # a real "nothing to report" case, kept distinct from "up to date" below.
        if not pkg:
            return None

        result = UpdateService._serialize(pkg)
        result["hardware_type"]    = hardware_type
        result["hardware_version"] = ""
        return result

    @staticmethod
    def get_package_file(db: Session, filename: str) -> FileResponse:
        repo = UpdateRepository(db)
        if not repo.firmware_exists(filename):
            raise HTTPException(status_code=403, detail="Access forbidden")

        path = os.path.join(settings.FIRMWARE_DIR, filename)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Package not found on disk")

        return FileResponse(path, media_type="application/octet-stream", filename=filename)
