from typing import Optional
from pydantic import BaseModel


class ArchiveRequest(BaseModel):
    archived: bool


class DeletePackageRequest(BaseModel):
    package_id: int
    delete_file: bool = False
    force: bool = False


class UpsertHardwareRequest(BaseModel):
    hardware_type: str
    firmware_package_id: Optional[int] = None


class AssignDeviceFirmwareRequest(BaseModel):
    mac_address: str
    firmware_package_id: Optional[int] = None