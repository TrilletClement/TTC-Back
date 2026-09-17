from app.domain.exceptions import NotFoundError
from app.orm_models.device import ESP32Device
from app.repositories.device_repo import DeviceRepository
from app.schemas.device import DeviceAdminOut, BoardOut, BoardListOut, OrderOut, HardwareOut, FirmwareOut


class AdminDevicesService:
    def __init__(self, repo: DeviceRepository):
        self.repo = repo

    def _build_device_out(self, d: ESP32Device, orders_by_device: dict[int, list] | None = None) -> DeviceAdminOut:
        board_out = None
        if d.board:
            orders = (
                orders_by_device.get(d.id, []) if orders_by_device is not None
                else self.repo.get_orders_for_device(d.id)
            )
            board_out = BoardOut(
                id=d.board.id,
                name=d.board.name,
                orders=[OrderOut(id=o.id, status=o.status, created_at=o.created_at) for o in orders],
            )

        return DeviceAdminOut(
            id=d.id,
            mac_address=d.mac_address,
            name=d.name,
            owner_email=d.owner.email if d.owner else None,
            board=board_out,
            hardware=HardwareOut(id=d.hardware.id, hardware_type=d.hardware.hardware_type) if d.hardware else None,
            current_firmware=FirmwareOut(id=d.current_firmware.id, filename=d.current_firmware.filename) if d.current_firmware else None,
            current_firmware_version=d.current_firmware_version,
            target_firmware=FirmwareOut(id=d.target_firmware.id, filename=d.target_firmware.filename) if d.target_firmware else None,
            version_updater=d.version_updater,
            running_partition=d.running_partition,
            boot_partition=d.boot_partition,
            update_partition=d.update_partition,
            ota_state=d.ota_state,
            last_connected=d.last_connected,
            last_ota_check=d.last_ota_check,
            registered_at=d.registered_at,
        )

    def list_devices(self) -> list[DeviceAdminOut]:
        devices = self.repo.list_all()
        orders_by_device = self.repo.get_orders_for_devices([d.id for d in devices if d.board])
        return [self._build_device_out(d, orders_by_device) for d in devices]

    def list_user_emails(self) -> list[str]:
        return self.repo.list_user_emails()

    def list_boards(self, owner_email: str | None) -> list[BoardListOut]:
        owner_id = None
        if owner_email:
            user = self.repo.get_user_by_email(owner_email)
            if not user:
                return []
            owner_id = user.id
        boards = self.repo.list_boards(owner_id)
        return [
            BoardListOut(id=b.id, name=b.name, owner_email=b.owner.email if b.owner else None)
            for b in boards
        ]

    def patch_device(self, device_id: int, payload) -> DeviceAdminOut:
        device = self.repo.get_by_id(device_id)
        if not device:
            raise NotFoundError("Device", device_id)

        if payload.name is not None:
            device.name = payload.name.strip() or None

        if payload.clear_owner:
            device.owner_id = None
        elif payload.owner_email is not None:
            user = self.repo.get_user_by_email(payload.owner_email)
            if not user:
                raise NotFoundError("User", payload.owner_email)
            device.owner_id = user.id

        if payload.unlink_board:
            device.board_id = None
        elif payload.board_id is not None:
            if not self.repo.get_board_by_id(payload.board_id):
                raise NotFoundError("Board", payload.board_id)
            device.board_id = payload.board_id

        if payload.clear_target_firmware:
            device.target_firmware_id = None
        elif payload.target_firmware_id is not None:
            if not self.repo.get_firmware_by_id(payload.target_firmware_id):
                raise NotFoundError("Firmware package", payload.target_firmware_id)
            device.target_firmware_id = payload.target_firmware_id

        if payload.hardware_id is not None:
            if not self.repo.get_hardware_by_id(payload.hardware_id):
                raise NotFoundError("Hardware type", payload.hardware_id)
            device.hardware_id = payload.hardware_id

        device = self.repo.save(device)
        return self._build_device_out(device)