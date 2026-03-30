import os
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.orm_models.device import ESP32Device, FirmwarePackage, Hardware, HardwareFirmwareAssignment


class UpdateService:
    _FASTAPI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    PACKAGE_DIR = os.path.join(_FASTAPI_ROOT, "static", "packages")
    PACKAGE_BASE_URL = os.environ.get("OTA_PACKAGE_BASE_URL", "https://transport.trillet.be")

    @staticmethod
    def normalize_mac(mac: str) -> str:
        value = (mac or "").strip().lower().replace("-", ":")
        if len(value) == 12 and ":" not in value:
            value = ":".join(value[i : i + 2] for i in range(0, 12, 2))
        return value

    @staticmethod
    def _normalize_scope_value(value: Optional[str]) -> str:
        return (value or "").strip()

    @staticmethod
    def _serialize_package(package: FirmwarePackage) -> dict:
        package_url = f"{UpdateService.PACKAGE_BASE_URL}/api/update/package/{package.package_file}"
        return {
            "package_id": package.id,
            "app_name": package.app_name,
            "app_version": package.app_version,
            "package_file": package.package_file,
            "app_url": package_url,
        }

    @staticmethod
    def _resolve_hardware(db: Session, hardware_type: str, hardware_version: str) -> Optional[Hardware]:
        exact = (
            db.query(Hardware)
            .filter(Hardware.hardware_type == hardware_type, Hardware.hardware_version == hardware_version)
            .first()
        )
        if exact:
            return exact

        if hardware_version:
            return (
                db.query(Hardware)
                .filter(Hardware.hardware_type == hardware_type, Hardware.hardware_version == "")
                .first()
            )

        return None

    @staticmethod
    def _package_matches_requested_firmware(package: Optional[FirmwarePackage], firmware_name: str) -> bool:
        if not package:
            return False
        if not firmware_name:
            return True
        return package.app_name == firmware_name

    @staticmethod
    def _resolve_hardware_assignment(
        db: Session,
        hardware: Optional[Hardware],
        firmware_name: str,
    ) -> Optional[FirmwarePackage]:
        if not hardware or not firmware_name:
            return None

        assignment = (
            db.query(HardwareFirmwareAssignment)
            .filter(
                HardwareFirmwareAssignment.hardware_id == hardware.id,
                HardwareFirmwareAssignment.firmware_name == firmware_name,
            )
            .first()
        )
        if assignment and assignment.firmware_package:
            return assignment.firmware_package
        return None

    @staticmethod
    def get_version_info(
        db: Session,
        hardware: str,
        mac: str,
        hardware_version: Optional[str] = None,
        firmware_name: Optional[str] = None,
        current_version: Optional[str] = None,
    ):
        normalized_mac = UpdateService.normalize_mac(mac)
        normalized_hardware = UpdateService._normalize_scope_value(hardware)
        normalized_hardware_version = UpdateService._normalize_scope_value(hardware_version)
        normalized_firmware_name = UpdateService._normalize_scope_value(firmware_name)
        normalized_current_version = UpdateService._normalize_scope_value(current_version)

        resolved_hardware = UpdateService._resolve_hardware(db, normalized_hardware, normalized_hardware_version)
        current_package = None
        if normalized_firmware_name and normalized_current_version:
            current_package = db.query(FirmwarePackage).filter(
                FirmwarePackage.app_name == normalized_firmware_name,
                FirmwarePackage.app_version == normalized_current_version,
            ).first()

        device = None
        if normalized_mac:
            device = db.query(ESP32Device).filter(ESP32Device.mac_address == normalized_mac).first()

        if device:
            if resolved_hardware:
                device.hardware_id = resolved_hardware.id
            if current_package:
                device.current_firmware_id = current_package.id
            now = datetime.utcnow()
            device.last_ota_check = now
            device.last_connected = now
            db.commit()
            db.refresh(device)

        package = None
        if device and device.target_firmware_id:
            candidate = db.query(FirmwarePackage).filter(FirmwarePackage.id == device.target_firmware_id).first()
            if UpdateService._package_matches_requested_firmware(candidate, normalized_firmware_name):
                package = candidate

        if not package:
            package = UpdateService._resolve_hardware_assignment(db, resolved_hardware, normalized_firmware_name)

        if not package and resolved_hardware and resolved_hardware.default_firmware_package_id:
            candidate = db.query(FirmwarePackage).filter(
                FirmwarePackage.id == resolved_hardware.default_firmware_package_id
            ).first()
            if UpdateService._package_matches_requested_firmware(candidate, normalized_firmware_name):
                package = candidate

        if package:
            result = UpdateService._serialize_package(package)
            result["hardware_type"] = normalized_hardware
            result["hardware_version"] = normalized_hardware_version
            result["firmware_name"] = package.app_name
            return result

        return None

    @staticmethod
    def get_package_file(db: Session, filename: str):
        allowed = db.query(FirmwarePackage.id).filter(FirmwarePackage.package_file == filename).first()
        if not allowed:
            raise HTTPException(status_code=403, detail="Access forbidden")

        path = os.path.join(UpdateService.PACKAGE_DIR, filename)
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="Package not found")

        return FileResponse(path, media_type="application/octet-stream", filename=filename)
