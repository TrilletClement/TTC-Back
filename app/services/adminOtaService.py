import os
import shutil
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.orm_models.device import ESP32Device
from app.orm_models.device import ESP32Device, FirmwarePackage, Hardware
from app.services.updateService import UpdateService


class AdminOtaService:
    _FASTAPI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    PACKAGES_DIR = os.path.join(_FASTAPI_ROOT, "static", "packages")
    ALLOWED_SUFFIXES = (".bin", ".tar", ".tar.gz", ".zip")

    @staticmethod
    def _normalize_scope_value(value: Optional[str]) -> str:
        return (value or "").strip()

    @staticmethod
    def _serialize_package(package: FirmwarePackage) -> dict:
        return {
            "id": package.id,
            "app_name": package.app_name,
            "app_version": package.app_version,
            "package_file": package.package_file,
            "uploaded_by_user_id": package.uploaded_by_user_id,
            "created_at": package.created_at.isoformat() if package.created_at else None,
        }

    @staticmethod
    def _serialize_hardware(hardware: Hardware) -> dict:
        return {
            "id": hardware.id,
            "hardware_type": hardware.hardware_type,
            "hardware_version": hardware.hardware_version,
            "default_firmware_package_id": hardware.default_firmware_package_id,
            "created_at": hardware.created_at.isoformat() if hardware.created_at else None,
            "default_firmware": AdminOtaService._serialize_package(hardware.default_firmware) if hardware.default_firmware else None,
        }

    @staticmethod
    def _serialize_legacy_entry(package: FirmwarePackage) -> dict:
        return {
            "package_id": package.id,
            "firmware_name": package.app_name,
            "app_name": package.app_name,
            "app_version": package.app_version,
            "package_file": package.package_file,
        }

    @staticmethod
    def get_versions(db: Session) -> dict:
        hardware_rows = db.query(Hardware).order_by(Hardware.hardware_type.asc(), Hardware.hardware_version.asc()).all()
        overrides = (
            db.query(ESP32Device)
            .join(FirmwarePackage, FirmwarePackage.id == ESP32Device.target_firmware_id)
            .filter(ESP32Device.target_firmware_id.isnot(None))
            .order_by(ESP32Device.mac_address.asc())
            .all()
        )
        packages = db.query(FirmwarePackage).order_by(FirmwarePackage.created_at.desc(), FirmwarePackage.id.desc()).all()

        default_entries = {}
        for hardware in hardware_rows:
            if not hardware.default_firmware:
                continue
            key = hardware.hardware_type
            if hardware.hardware_version:
                key = f"{hardware.hardware_type}@{hardware.hardware_version}"
            default_entries[key] = AdminOtaService._serialize_legacy_entry(hardware.default_firmware)

        exception_entries = {
            device.mac_address: AdminOtaService._serialize_legacy_entry(device.target_firmware)
            for device in overrides
            if device.target_firmware
        }

        return {
            "default": default_entries,
            "exceptions": exception_entries,
            "packages": [AdminOtaService._serialize_package(package) for package in packages],
            "hardware": [AdminOtaService._serialize_hardware(hardware) for hardware in hardware_rows],
            "device_overrides": [
                {
                    "device_id": device.id,
                    "mac_address": device.mac_address,
                    "hardware_id": device.hardware_id,
                    "target_package": AdminOtaService._serialize_package(device.target_firmware),
                }
                for device in overrides
                if device.target_firmware
            ],
        }

    @staticmethod
    def list_packages(db: Session) -> dict:
        packages = db.query(FirmwarePackage).order_by(FirmwarePackage.created_at.desc(), FirmwarePackage.id.desc()).all()
        return {"packages": [AdminOtaService._serialize_package(package) for package in packages]}

    @staticmethod
    def list_hardware(db: Session) -> dict:
        hardware_rows = db.query(Hardware).order_by(Hardware.hardware_type.asc(), Hardware.hardware_version.asc()).all()
        return {"hardware": [AdminOtaService._serialize_hardware(hardware) for hardware in hardware_rows]}

    @staticmethod
    def _ensure_allowed_filename(filename: str):
        lowered = filename.lower()
        if not any(lowered.endswith(suffix) for suffix in AdminOtaService.ALLOWED_SUFFIXES):
            raise HTTPException(status_code=400, detail="Unsupported firmware package type")

    @staticmethod
    def _save_upload(file: UploadFile) -> str:
        AdminOtaService._ensure_allowed_filename(file.filename)
        os.makedirs(AdminOtaService.PACKAGES_DIR, exist_ok=True)
        dest_path = os.path.join(AdminOtaService.PACKAGES_DIR, file.filename)
        with open(dest_path, "wb") as out:
            shutil.copyfileobj(file.file, out)
        return dest_path

    @staticmethod
    def upload_firmware(
        db: Session,
        file: UploadFile,
        app_version: str,
        app_name: Optional[str] = None,
        uploaded_by_user_id: Optional[int] = None,
    ) -> dict:
        normalized_app_name = AdminOtaService._normalize_scope_value(app_name)
        if not normalized_app_name:
            raise HTTPException(status_code=400, detail="app_name is required")
        if not app_version or not app_version.strip():
            raise HTTPException(status_code=400, detail="app_version is required")

        AdminOtaService._save_upload(file)

        existing = db.query(FirmwarePackage).filter(FirmwarePackage.package_file == file.filename).first()
        if existing:
            existing.app_name = normalized_app_name
            existing.app_version = app_version.strip()
            existing.uploaded_by_user_id = uploaded_by_user_id
            package = existing
        else:
            package = FirmwarePackage(
                app_name=normalized_app_name,
                app_version=app_version.strip(),
                package_file=file.filename,
                uploaded_by_user_id=uploaded_by_user_id,
                created_at=datetime.utcnow(),
            )
            db.add(package)
            db.flush()

        db.commit()
        db.refresh(package)

        return {
            "message": "Firmware uploaded successfully",
            "package": AdminOtaService._serialize_package(package),
        }

    @staticmethod
    def upsert_hardware(
        db: Session,
        hardware_type: str,
        hardware_version: Optional[str] = None,
        default_firmware_package_id: Optional[int] = None,
    ) -> dict:
        normalized_type = AdminOtaService._normalize_scope_value(hardware_type)
        normalized_version = AdminOtaService._normalize_scope_value(hardware_version)
        if not normalized_type:
            raise HTTPException(status_code=400, detail="hardware_type is required")

        package = None
        if default_firmware_package_id is not None:
            package = db.query(FirmwarePackage).filter(FirmwarePackage.id == default_firmware_package_id).first()
            if not package:
                raise HTTPException(status_code=404, detail="Firmware package not found")

        hardware = (
            db.query(Hardware)
            .filter(Hardware.hardware_type == normalized_type, Hardware.hardware_version == normalized_version)
            .first()
        )
        if hardware:
            hardware.default_firmware_package_id = package.id if package else None
        else:
            hardware = Hardware(
                hardware_type=normalized_type,
                hardware_version=normalized_version,
                default_firmware_package_id=package.id if package else None,
                created_at=datetime.utcnow(),
            )
            db.add(hardware)
            db.flush()

        db.commit()
        db.refresh(hardware)
        return {
            "message": "Hardware configuration saved",
            "hardware": AdminOtaService._serialize_hardware(hardware),
        }

    @staticmethod
    def assign_device_firmware(db: Session, mac_address: str, firmware_package_id: Optional[int]) -> dict:
        normalized_mac = UpdateService.normalize_mac(mac_address)
        device = db.query(ESP32Device).filter(ESP32Device.mac_address == normalized_mac).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        if firmware_package_id is None:
            device.target_firmware_id = None
            db.commit()
            return {"message": "Device override cleared", "mac_address": normalized_mac}

        package = db.query(FirmwarePackage).filter(FirmwarePackage.id == firmware_package_id).first()
        if not package:
            raise HTTPException(status_code=404, detail="Firmware package not found")

        device.target_firmware_id = package.id
        db.commit()
        db.refresh(device)
        return {
            "message": "Device firmware override saved",
            "device": {
                "id": device.id,
                "mac_address": device.mac_address,
                "target_package": AdminOtaService._serialize_package(package),
            },
        }

    @staticmethod
    def delete_version(
        db: Session,
        hardware: Optional[str],
        mac_exception: Optional[str],
        delete_file: bool,
        package_id: Optional[int] = None,
        hardware_version: Optional[str] = None,
    ) -> dict:
        normalized_hardware = AdminOtaService._normalize_scope_value(hardware)
        normalized_hardware_version = AdminOtaService._normalize_scope_value(hardware_version)
        normalized_mac = UpdateService.normalize_mac(mac_exception) if mac_exception else ""

        if package_id is not None:
            package = db.query(FirmwarePackage).filter(FirmwarePackage.id == package_id).first()
            if not package:
                raise HTTPException(status_code=404, detail="Firmware package not found")

            hardware_ref = db.query(Hardware.id).filter(Hardware.default_firmware_package_id == package.id).first()
            device_ref = db.query(ESP32Device.id).filter(ESP32Device.target_firmware_id == package.id).first()
            if hardware_ref or device_ref:
                raise HTTPException(status_code=409, detail="Firmware package is still assigned")

            db.delete(package)
            db.commit()

            if delete_file:
                pkg_path = os.path.join(AdminOtaService.PACKAGES_DIR, package.package_file)
                if os.path.exists(pkg_path):
                    os.remove(pkg_path)

            return {"message": "Firmware package deleted", "package_file": package.package_file}

        if normalized_mac:
            device = db.query(ESP32Device).filter(ESP32Device.mac_address == normalized_mac).first()
            if not device or not device.target_firmware_id:
                raise HTTPException(status_code=404, detail="Device override not found")
            deleted_package = device.target_firmware
            device.target_firmware_id = None
            db.commit()
            return {
                "message": "Device override deleted",
                "entry": AdminOtaService._serialize_package(deleted_package) if deleted_package else None,
            }

        if normalized_hardware:
            hardware_row = (
                db.query(Hardware)
                .filter(Hardware.hardware_type == normalized_hardware, Hardware.hardware_version == normalized_hardware_version)
                .first()
            )
            if not hardware_row:
                raise HTTPException(status_code=404, detail="Hardware configuration not found")
            deleted_package = hardware_row.default_firmware
            hardware_row.default_firmware_package_id = None
            db.commit()
            return {
                "message": "Hardware default firmware cleared",
                "entry": AdminOtaService._serialize_package(deleted_package) if deleted_package else None,
            }

        raise HTTPException(status_code=400, detail="Provide hardware, mac_exception, or package_id")

    @staticmethod
    def list_firmware_files(db: Session) -> dict:
        os.makedirs(AdminOtaService.PACKAGES_DIR, exist_ok=True)
        db_files = {
            package.package_file: package
            for package in db.query(FirmwarePackage).order_by(FirmwarePackage.created_at.desc(), FirmwarePackage.id.desc()).all()
        }
        files = []
        for filename in sorted(os.listdir(AdminOtaService.PACKAGES_DIR)):
            path = os.path.join(AdminOtaService.PACKAGES_DIR, filename)
            if not os.path.isfile(path):
                continue
            package = db_files.get(filename)
            files.append(
                {
                    "filename": filename,
                    "size_kb": round(os.path.getsize(path) / 1024, 1),
                    "package_id": package.id if package else None,
                    "app_name": package.app_name if package else None,
                    "app_version": package.app_version if package else None,
                }
            )
        return {"files": files}
