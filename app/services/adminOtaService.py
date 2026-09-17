import os
import shutil
from datetime import datetime
from typing import Optional

from fastapi import UploadFile

from app.core.config import settings
from app.domain.exceptions import NotFoundError, BusinessError, ValidationError
from app.orm_models.device import ESP32Device, FirmwarePackage, Hardware
from app.repositories.firmware_repo import FirmwareRepository


def _normalize_mac(mac: str) -> str:
    value = (mac or "").strip().lower().replace("-", ":")
    if len(value) == 12 and ":" not in value:
        value = ":".join(value[i:i + 2] for i in range(0, 12, 2))
    return value


class FirmwareStorage:
    ALLOWED_SUFFIXES = (".bin", ".tar", ".tar.gz", ".zip")

    def __init__(self, firmware_dir: str):
        self.firmware_dir = firmware_dir

    def _path(self, filename: str) -> str:
        os.makedirs(self.firmware_dir, exist_ok=True)
        return os.path.join(self.firmware_dir, filename)

    def _safe_filename(self, original: str) -> str:
        # The client-supplied filename flows straight into os.path.join()
        # via _path() — without this, a name like "../../etc/cron.d/x" (or
        # the backslash equivalent, which plain os.path.basename() would NOT
        # catch on a Linux host) would write outside firmware_dir. Kept
        # human-readable (packages are looked up/displayed by filename, and
        # a re-upload of the same name is meant to replace the existing
        # package) — just strips path separators and traversal segments
        # instead of randomizing the name away like the blog uploads do.
        name = os.path.basename((original or "").replace("\\", "/")).lstrip(".")
        if not name:
            raise ValidationError("Invalid filename")
        return name

    def exists(self, filename: str) -> bool:
        return bool(filename) and os.path.isfile(self._path(filename))

    def save(self, file: UploadFile, filename: str) -> str:
        safe_name = self._safe_filename(filename)
        with open(self._path(safe_name), "wb") as out:
            shutil.copyfileobj(file.file, out)
        return safe_name

    def delete(self, filename: str) -> None:
        path = self._path(filename)
        if os.path.exists(path):
            os.remove(path)

    def list_files(self) -> dict[str, int]:
        dir_path = self.firmware_dir
        os.makedirs(dir_path, exist_ok=True)
        return {
            f: os.path.getsize(os.path.join(dir_path, f))
            for f in sorted(os.listdir(dir_path))
            if os.path.isfile(os.path.join(dir_path, f))
        }

    def validate_suffix(self, filename: str) -> None:
        if not any(filename.lower().endswith(s) for s in self.ALLOWED_SUFFIXES):
            raise ValidationError("Unsupported file type")


class AdminOtaService:
    def __init__(self, repo: FirmwareRepository, storage: FirmwareStorage):
        self.repo = repo
        self.storage = storage

    # ── serializers ───────────────────────────────────────────────────────────

    def _pkg(self, p: FirmwarePackage) -> dict:
        return {
            "id":          p.id,
            "filename":    p.filename,
            "archived":    p.archived,
            "file_exists": self.storage.exists(p.filename),
            "created_at":  p.created_at.isoformat() if p.created_at else None,
        }

    @staticmethod
    def _hw(h: Hardware) -> dict:
        return {
            "id":                  h.id,
            "hardware_type":       h.hardware_type,
            "firmware_package_id": h.firmware_package_id,
            "created_at":          h.created_at.isoformat() if h.created_at else None,
        }

    def _users_of_package(self, package_id: int) -> dict:
        return {
            "hardware_types": [h.hardware_type for h in self.repo.get_hardware_by_package(package_id)],
            "device_macs":    [d.mac_address    for d in self.repo.get_devices_by_target(package_id)],
        }

    # ── public API ────────────────────────────────────────────────────────────

    def get_data(self) -> dict:
        packages  = self.repo.list_all()
        hardware  = self.repo.list_hardware()
        overrides = self.repo.get_devices_with_overrides()

        pkg_users  = {p.id: self._users_of_package(p.id) for p in packages}
        hw_devices = {
            hw.id: [d.mac_address for d in self.repo.get_devices_by_hardware(hw.id)]
            for hw in hardware
        }

        return {
            "packages": [{**self._pkg(p), **pkg_users[p.id]} for p in packages],
            "hardware": [
                {**self._hw(h), "firmware": self._pkg(h.firmware) if h.firmware else None, "device_macs": hw_devices[h.id]}
                for h in hardware
            ],
            "device_overrides": [
                {
                    "device_id":      d.id,
                    "mac_address":    d.mac_address,
                    "hardware_type":  d.hardware.hardware_type if d.hardware else None,
                    "target_package": self._pkg(d.target_firmware),
                }
                for d in overrides if d.target_firmware
            ],
        }

    def upload_firmware(self, file: UploadFile) -> dict:
        filename = file.filename or ""
        self.storage.validate_suffix(filename)
        filename = self.storage.save(file, filename)

        pkg = self.repo.get_by_filename(filename)
        if pkg:
            pkg.archived   = False
            pkg.created_at = datetime.utcnow()
        else:
            pkg = FirmwarePackage(filename=filename, archived=False, created_at=datetime.utcnow())

        self.repo.save(pkg)
        return {"message": "Firmware uploaded", "package": self._pkg(pkg)}

    def set_archived(self, package_id: int, archived: bool) -> dict:
        pkg = self.repo.get_by_id(package_id)
        if not pkg:
            raise NotFoundError("Package", package_id)

        if archived:
            users = self._users_of_package(package_id)
            if users["hardware_types"] or users["device_macs"]:
                raise BusinessError(
                    f"Still used by hardware: {users['hardware_types']} / devices: {users['device_macs']}"
                )

        pkg.archived = archived
        self.repo.save(pkg)
        return {"message": "Package updated", "package": self._pkg(pkg)}

    def delete_package(self, package_id: int, delete_file: bool = False, force: bool = False) -> dict:
        pkg = self.repo.get_by_id(package_id)
        if not pkg:
            raise NotFoundError("Package", package_id)

        users = self._users_of_package(package_id)
        if (users["hardware_types"] or users["device_macs"]) and not force:
            raise BusinessError(
                f"Still used by hardware: {users['hardware_types']} / devices: {users['device_macs']}"
            )

        if force:
            self.repo.detach_package_from_hardware(package_id)
            self.repo.detach_package_from_devices(package_id)
            self.repo.flush()

        filename = pkg.filename
        self.repo.delete(pkg)

        if delete_file:
            self.storage.delete(filename)

        return {"message": "Package deleted", "filename": filename}

    def upsert_hardware(self, hardware_type: str, firmware_package_id: Optional[int]) -> dict:
        hardware_type = hardware_type.strip()
        if not hardware_type:
            raise ValidationError("hardware_type is required")

        if firmware_package_id is not None:
            if not self.repo.get_by_id(firmware_package_id):
                raise NotFoundError("Firmware package", firmware_package_id)

        hw = self.repo.get_hardware_by_type(hardware_type)
        if hw:
            hw.firmware_package_id = firmware_package_id
        else:
            hw = Hardware(
                hardware_type=hardware_type,
                firmware_package_id=firmware_package_id,
                created_at=datetime.utcnow(),
            )

        self.repo.save(hw)
        return {"message": "Hardware saved", "hardware": self._hw(hw)}

    def delete_hardware(self, hardware_id: int) -> dict:
        hw = self.repo.get_hardware_by_id(hardware_id)
        if not hw:
            raise NotFoundError("Hardware", hardware_id)

        linked = self.repo.get_devices_by_hardware(hardware_id)
        for device in linked:
            device.hardware_id = None

        self.repo.delete(hw)
        return {"message": "Hardware deleted", "devices_unlinked": len(linked)}

    def assign_device_firmware(self, mac_address: str, firmware_package_id: Optional[int]) -> dict:
        mac    = _normalize_mac(mac_address)
        device = self.repo.get_device_by_mac(mac)
        if not device:
            raise NotFoundError("Device", mac_address)

        if firmware_package_id is not None:
            if not self.repo.get_by_id(firmware_package_id):
                raise NotFoundError("Package", firmware_package_id)

        device.target_firmware_id = firmware_package_id
        self.repo.commit()
        return {"message": "Device override updated"}

    def list_firmware_files(self) -> dict:
        disk_files = self.storage.list_files()
        db_pkgs    = {p.filename: p for p in self.repo.list_all()}

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