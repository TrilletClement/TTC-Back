from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FirmwareOut(BaseModel):
    id: int
    filename: str

class HardwareOut(BaseModel):
    id: int
    hardware_type: str

class OrderOut(BaseModel):
    id: int
    status: str
    created_at: Optional[datetime]

class BoardOut(BaseModel):
    id: int
    name: str
    orders: list[OrderOut]

class BoardListOut(BaseModel):
    id: int
    name: str
    owner_email: Optional[str]

class DevicePatch(BaseModel):
    name: Optional[str] = None
    owner_email: Optional[str] = None
    clear_owner: bool = False
    board_id: Optional[int] = None
    unlink_board: bool = False
    target_firmware_id: Optional[int] = None
    clear_target_firmware: bool = False
    hardware_id: Optional[int] = None

class DeviceAdminOut(BaseModel):
    id: int
    mac_address: str
    name: Optional[str]
    owner_email: Optional[str]
    board: Optional[BoardOut]
    hardware: Optional[HardwareOut]
    current_firmware: Optional[FirmwareOut]
    current_firmware_version: Optional[str]
    target_firmware: Optional[FirmwareOut]
    version_updater: Optional[str]
    running_partition: Optional[str]
    boot_partition: Optional[str]
    update_partition: Optional[str]
    ota_state: Optional[str]
    last_connected: Optional[datetime]
    last_ota_check: Optional[datetime]
    registered_at: Optional[datetime]


# ── user-facing ───────────────────────────────────────────────────────────────

class DeviceLink(BaseModel):
    esp_id: int
    board_id: int


class DeviceRename(BaseModel):
    name: str | None = None


class DeviceLuminosity(BaseModel):
    light_intensity_percent: float


class LedStripStatusRow(BaseModel):
    id: int
    h: int = Field(..., description="Row index/order")
    v: list[list[int]] = Field(
        ...,
        description="Per-LED RGB states for this row, e.g. [[0,255,0],[0,0,0],...]",
    )


class LedStripStatusResponse(BaseModel):
    strips: list[LedStripStatusRow]
    settings_updated_at: Optional[str] = None