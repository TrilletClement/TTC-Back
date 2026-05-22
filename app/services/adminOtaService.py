import os
import shutil
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.orm_models.device import ESP32Device, FirmwarePackage, Hardware


class AdminOtaService:
    ALLOWED_SUFFIXES = (".bin", ".tar", ".tar.gz", ".zip")

    # ── filesystem helpers ────────────────────────────────────────────────────

    @classmethod
    def _packages_dir(cls) -> str:
        os.makedirs(settings.FIRMWARE_DIR, exist_ok=True)
        return settings.FIRMWARE_DIR

    @classmethod
    def _file_path(cls, filename: str) -> str:
        return os.path.join(cls._packages_dir(), filename)

    @classmethod
    def _file_exists(cls, filename: str) -> bool:
        return bool(filename) and os.path.isfile(cls._file_path(filename))

    @classmethod
    def _delete_file(cls, filename: str) -> None:
        path = cls._file_path(filename)
        if os.path.exists(path):
            os.remove(path)

    # ── serializers ───────────────────────────────────────────────────────────

    @classmethod
    def _pkg(cls, p: FirmwarePackage) -> dict:
        return {
            "id":          p.id,
            "filename":    p.filename,
            "archived":    p.archived,
            "file_exists": cls._file_exists(p.filename),
            "created_at":  p.created_at.isoformat() if p.created_at else None,
        }

    @staticmethod
    def _hw(h: Hardware) -> dict:
        return {
            "id":                  h.id,
            "hardware_type":       h.hardware_type,
            "firmware_package_id": h.firmware_package_id,
            "firmware":            AdminOtaService._pkg(h.firmware) if h.firmware else None,
            "created_at":          h.created_at.isoformat() if h.created_at else None,
        }

    # ── queries ───────────────────────────────────────────────────────────────

    @staticmethod
    def _users_of_package(db: Session, package_id: int) -> dict:
        """Return hardware types and device MACs that actively point to this package."""
        hardware = db.query(Hardware).filter(Hardware.firmware_package_id == package_id).all()
        devices  = db.query(ESP32Device).filter(ESP32Device.target_firmware_id == package_id).all()
        return {
            "hardware_types": [h.hardware_type for h in hardware],
            "device_macs":    [d.mac_address    for d in devices],
        }

    # ── public API ────────────────────────────────────────────────────────────

    @classmethod
    def get_data(cls, db: Session) -> dict:
        packages  = db.query(FirmwarePackage).order_by(FirmwarePackage.created_at.desc()).all()
        hardware  = db.query(Hardware).order_by(Hardware.hardware_type).all()
        overrides = (
            db.query(ESP32Device)
            .filter(ESP32Device.target_firmware_id.isnot(None))
            .order_by(ESP32Device.mac_address)
            .all()
        )

        pkg_users = {p.id: cls._users_of_package(db, p.id) for p in packages}

        return {
            "packages": [{**cls._pkg(p), **pkg_users[p.id]} for p in packages],
            "hardware": [cls._hw(h) for h in hardware],
            "device_overrides": [
                {
                    "device_id":      d.id,
                    "mac_address":    d.mac_address,
                    "hardware_type":  d.hardware.hardware_type if d.hardware else None,
                    "target_package": cls._pkg(d.target_firmware),
                }
                for d in overrides if d.target_firmware
            ],
        }

    @classmethod
    def upload_firmware(cls, db: Session, file: UploadFile) -> dict:
        filename = file.filename or ""
        lowered  = filename.lower()
        if not any(lowered.endswith(s) for s in cls.ALLOWED_SUFFIXES):
            raise HTTPException(status_code=400, detail="Unsupported file type")

        dest = cls._file_path(filename)
        with open(dest, "wb") as out:
            shutil.copyfileobj(file.file, out)

        existing = db.query(FirmwarePackage).filter(FirmwarePackage.filename == filename).first()
        if existing:
            existing.archived   = False
            existing.created_at = datetime.utcnow()
            pkg = existing
        else:
            pkg = FirmwarePackage(filename=filename, archived=False, created_at=datetime.utcnow())
            db.add(pkg)

        db.commit()
        db.refresh(pkg)
        return {"message": "Firmware uploaded", "package": cls._pkg(pkg)}

    @classmethod
    def set_archived(cls, db: Session, package_id: int, archived: bool) -> dict:
        pkg = db.query(FirmwarePackage).filter(FirmwarePackage.id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")

        if archived:
            users = cls._users_of_package(db, package_id)
            if users["hardware_types"] or users["device_macs"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Still used by hardware: {users['hardware_types']} / devices: {users['device_macs']}"
                )

        pkg.archived = archived
        db.commit()
        db.refresh(pkg)
        return {"message": "Package updated", "package": cls._pkg(pkg)}

    @classmethod
    def delete_package(cls, db: Session, package_id: int, delete_file: bool = False) -> dict:
        pkg = db.query(FirmwarePackage).filter(FirmwarePackage.id == package_id).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")

        users = cls._users_of_package(db, package_id)
        if users["hardware_types"] or users["device_macs"]:
            raise HTTPException(
                status_code=409,
                detail=f"Still used by hardware: {users['hardware_types']} / devices: {users['device_macs']}"
            )

        filename = pkg.filename
        db.delete(pkg)
        db.commit()

        if delete_file:
            cls._delete_file(filename)

        return {"message": "Package deleted", "filename": filename}

    @staticmethod
    def upsert_hardware(db: Session, hardware_type: str, firmware_package_id: Optional[int]) -> dict:
        hardware_type = hardware_type.strip()
        if not hardware_type:
            raise HTTPException(status_code=400, detail="hardware_type is required")

        if firmware_package_id is not None:
            pkg = db.query(FirmwarePackage).filter(FirmwarePackage.id == firmware_package_id).first()
            if not pkg:
                raise HTTPException(status_code=404, detail="Firmware package not found")

        hw = db.query(Hardware).filter(Hardware.hardware_type == hardware_type).first()
        if hw:
            hw.firmware_package_id = firmware_package_id
        else:
            hw = Hardware(
                hardware_type=hardware_type,
                firmware_package_id=firmware_package_id,
                created_at=datetime.utcnow(),
            )
            db.add(hw)

        db.commit()
        db.refresh(hw)
        return {"message": "Hardware saved", "hardware": AdminOtaService._hw(hw)}

    @staticmethod
    def delete_hardware(db: Session, hardware_id: int) -> dict:
        hw = db.query(Hardware).filter(Hardware.id == hardware_id).first()
        if not hw:
            raise HTTPException(status_code=404, detail="Hardware not found")
        db.delete(hw)
        db.commit()
        return {"message": "Hardware deleted"}

    @staticmethod
    def assign_device_firmware(db: Session, mac_address: str, firmware_package_id: Optional[int]) -> dict:
        from app.services.updateService import UpdateService
        mac = UpdateService.normalize_mac(mac_address)
        device = db.query(ESP32Device).filter(ESP32Device.mac_address == mac).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        if firmware_package_id is not None:
            pkg = db.query(FirmwarePackage).filter(FirmwarePackage.id == firmware_package_id).first()
            if not pkg:
                raise HTTPException(status_code=404, detail="Package not found")

        device.target_firmware_id = firmware_package_id
        db.commit()
        return {"message": "Device override updated"}

    @classmethod
    def list_firmware_files(cls, db: Session) -> dict:
        packages_dir = cls._packages_dir()
        disk_files = {
            f: os.path.getsize(os.path.join(packages_dir, f))
            for f in sorted(os.listdir(packages_dir))
            if os.path.isfile(os.path.join(packages_dir, f))
        }
        db_pkgs = {p.filename: p for p in db.query(FirmwarePackage).all()}

        files = []
        for filename, size in disk_files.items():
            pkg = db_pkgs.get(filename)
            files.append({
                "filename":   filename,
                "size_kb":    round(size / 1024, 1),
                "on_disk":    True,
                "in_db":      pkg is not None,
                "package_id": pkg.id if pkg else None,
                "archived":   pkg.archived if pkg else False,
            })

        for filename, pkg in db_pkgs.items():
            if filename not in disk_files:
                files.append({
                    "filename":   filename,
                    "size_kb":    None,
                    "on_disk":    False,
                    "in_db":      True,
                    "package_id": pkg.id,
                    "archived":   pkg.archived,
                })

        return {"files": files}
