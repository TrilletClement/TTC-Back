import re

from fastapi import HTTPException

from app.orm_models.auth import User
from app.repositories.device_repo import DeviceRepository


class DeviceService:
    def __init__(self, repo: DeviceRepository):
        self.repo = repo

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_color_to_rgb(color: str | None) -> list[int]:
        if not color:
            return [0, 255, 0]
        value = color.strip().lower()
        if value.startswith("#") and len(value) == 7:
            try:
                return [int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)]
            except ValueError:
                return [0, 255, 0]
        return [0, 255, 0]

    # ── user-facing ───────────────────────────────────────────────────────────

    def get_connected_devices(self, current_user: User):
        esp = self.repo.get_devices_for_owner(current_user.id)
        return {"esp_devices": esp}

    def rename_device(self, esp_id: int, name: str | None, current_user: User):
        device = self.repo.get_device_by_id(esp_id, current_user.id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found.")
        device.name = name.strip() if name else None
        self.repo.commit()
        return {"id": device.id, "name": device.name}

    def link_device_to_board(self, esp_id: int, board_id: int, current_user: User):
        if not esp_id or not board_id:
            raise HTTPException(status_code=400, detail="Both ESP ID and board ID are required.")
        esp = self.repo.get_device_by_id(esp_id, current_user.id)
        board = self.repo.get_board_by_id(board_id, current_user.id)
        if not esp or not board:
            raise HTTPException(status_code=404, detail="Invalid ESP32 device or board.")
        esp.board_id = board.id
        self.repo.commit()
        return {"message": "ESP32 device linked to board successfully."}

    def unlink_device_from_board(self, esp_id: int, current_user: User):
        if not esp_id:
            raise HTTPException(status_code=400, detail="ESP ID is required.")
        esp = self.repo.get_device_by_id(esp_id, current_user.id)
        if not esp:
            raise HTTPException(status_code=404, detail="Invalid ESP32 device.")
        esp.board_id = None
        self.repo.commit()
        return {"message": "ESP32 device unlinked from board successfully."}

    def get_luminosity(self, esp_id: int, current_user: User):
        device = self.repo.get_device_by_id(esp_id, current_user.id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found.")
        from app.services.adminSettingsService import adminSettingsService
        effective = adminSettingsService.get_effective_settings(device)
        return {"light_intensity_percent": effective.get("light_intensity_percent", 100.0)}

    def patch_luminosity(self, esp_id: int, value: float, current_user: User):
        device = self.repo.get_device_by_id(esp_id, current_user.id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found.")
        result = self.repo.update_luminosity(device, value)
        return {"light_intensity_percent": result}

    # ── ESP hardware-facing ───────────────────────────────────────────────────

    def get_ledstrip_status(self, mac: str):
        from app.services.boardService import BoardService

        if not mac:
            raise HTTPException(status_code=400, detail="MAC address is required.")

        mac = mac.strip().lower()
        if re.fullmatch(r"[0-9a-f]{12}", mac):
            mac = ":".join(mac[i: i + 2] for i in range(0, 12, 2))

        esp = self.repo.get_device_by_mac(mac)
        if not esp:
            raise HTTPException(status_code=401, detail="Unknown ESP32 device.")

        settings_ts = esp.last_settings_updated_at.isoformat() if esp.last_settings_updated_at else None

        if not esp.board_id:
            return {"strips": [], "settings_updated_at": settings_ts}

        board = self.repo.get_board_by_id_only(esp.board_id)
        if not board:
            return {"strips": [], "settings_updated_at": settings_ts}

        bt = board.board_type
        max_strips = bt.max_ledstrip
        max_leds = bt.max_led

        strips_data = BoardService._build_led_strips_data(board, self.repo.db)

        configured: dict[int, list[list[int]]] = {}
        for idx, strip in enumerate(strips_data, start=1):
            h = strip.get("orderIndex") if strip.get("orderIndex") is not None else idx
            rgb_array = [
                self._parse_color_to_rgb(led.get("ledColor")) if led.get("isOn") else [0, 0, 0]
                for led in strip.get("leds", [])
            ]
            if len(rgb_array) < max_leds:
                rgb_array += [[0, 0, 0]] * (max_leds - len(rgb_array))
            else:
                rgb_array = rgb_array[:max_leds]
            configured[h] = rgb_array

        empty_strip = [[0, 0, 0]] * max_leds
        return {
            "strips": [
                {"id": h, "h": h, "v": configured.get(h, empty_strip)}
                for h in range(1, max_strips + 1)
            ],
            "settings_updated_at": settings_ts,
        }