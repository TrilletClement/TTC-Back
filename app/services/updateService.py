import os
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.orm_models.device import ESP32Device, FirmwarePackage, Hardware


class UpdateService:
    PACKAGE_BASE_URL = os.environ.get("OTA_PACKAGE_BASE_URL", "https://transport.trillet.be")

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
    def _serialize(pkg: FirmwarePackage) -> dict:
        return {
            "package_id":    pkg.id,
            "app_version":   pkg.filename,
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
        normalized_mac = UpdateService.normalize_mac(mac)
        hardware_type  = (hardware or "").strip()

        device = None
        if normalized_mac:
            device = db.query(ESP32Device).filter(ESP32Device.mac_address == normalized_mac).first()

        hw = db.query(Hardware).filter(Hardware.hardware_type == hardware_type).first()

        if device:
            if hw:
                device.hardware_id = hw.id
            # Always store the raw version string and partition state the device reported.
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
            # Try to match the version to a FirmwarePackage row.
            # Build script produces filenames like "{firmware_name}-v{version}.bin".
            if firmware_name and current_version:
                expected = f"{firmware_name}-v{current_version}.bin"
                cur_pkg = db.query(FirmwarePackage).filter(FirmwarePackage.filename == expected).first()
                if cur_pkg:
                    device.current_firmware_id = cur_pkg.id
            now = datetime.utcnow()
            device.last_ota_check = now
            device.last_connected = now
            db.commit()

        # Resolve target firmware: device override > hardware default
        pkg = None

        if device and device.target_firmware_id:
            candidate = db.query(FirmwarePackage).filter(
                FirmwarePackage.id == device.target_firmware_id,
                FirmwarePackage.archived == False,
            ).first()
            if candidate:
                pkg = candidate

        if not pkg and hw and hw.firmware_package_id:
            candidate = db.query(FirmwarePackage).filter(
                FirmwarePackage.id == hw.firmware_package_id,
                FirmwarePackage.archived == False,
            ).first()
            if candidate:
                pkg = candidate

        if not pkg:
            return None

        # Already up to date
        if device and device.current_firmware_id == pkg.id:
            return None

        result = UpdateService._serialize(pkg)
        result["hardware_type"]    = hardware_type
        result["hardware_version"] = ""
        return result

    @staticmethod
    def get_package_file(db: Session, filename: str) -> FileResponse:
        allowed = db.query(FirmwarePackage.id).filter(FirmwarePackage.filename == filename).first()
        if not allowed:
            raise HTTPException(status_code=403, detail="Access forbidden")

        path = os.path.join(settings.FIRMWARE_DIR, filename)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Package not found on disk")

        return FileResponse(path, media_type="application/octet-stream", filename=filename)
