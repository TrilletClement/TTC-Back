import json
from datetime import datetime
from typing import Any

from app.domain.exceptions import NotFoundError
from app.orm_models.device import ESP32Device, Hardware
from app.repositories.settings_repo import SettingsRepository


def _extract_defaults(schema: dict) -> dict[str, Any]:
    return {
        s["key"]: s["default"]
        for section in schema.get("sections", [])
        for s in section.get("settings", [])
        if "key" in s and "default" in s
    }


def _extract_keys(schema: dict) -> set[str]:
    return {
        s["key"]
        for section in schema.get("sections", [])
        for s in section.get("settings", [])
        if "key" in s
    }


def _parse_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}


class adminSettingsService:
    def __init__(self, repo: SettingsRepository):
        self.repo = repo

    @staticmethod
    def get_hardware_schema(hardware: Hardware) -> dict:
        data = _parse_json(hardware.json_settings if hardware else None)
        return data if "sections" in data else {"sections": []}

    @staticmethod
    def get_device_overrides(device: ESP32Device) -> dict[str, Any]:
        return _parse_json(device.json_settings_override)

    @staticmethod
    def get_effective_settings(device: ESP32Device) -> dict[str, Any]:
        schema     = adminSettingsService.get_hardware_schema(device.hardware) if device.hardware else {"sections": []}
        defaults   = _extract_defaults(schema)
        valid_keys = _extract_keys(schema)
        overrides  = adminSettingsService.get_device_overrides(device)
        return {**defaults, **{k: v for k, v in overrides.items() if k in valid_keys}}

    def get_hardware_settings(self, hardware_id: int) -> dict:
        hw = self.repo.get_hardware_by_id(hardware_id)
        if not hw:
            raise NotFoundError("Hardware", hardware_id)
        return {"hardware_id": hardware_id, "schema": self.get_hardware_schema(hw)}

    def update_hardware_schema(self, hardware_id: int, schema: dict) -> dict:
        hw = self.repo.get_hardware_by_id(hardware_id)
        if not hw:
            raise NotFoundError("Hardware", hardware_id)

        old_keys     = _extract_keys(self.get_hardware_schema(hw))
        removed_keys = old_keys - _extract_keys(schema)
        hw.json_settings = json.dumps(schema)

        if removed_keys:
            for device in self.repo.get_devices_by_hardware(hardware_id):
                overrides = self.get_device_overrides(device)
                pruned    = {k: v for k, v in overrides.items() if k not in removed_keys}
                device.json_settings_override    = json.dumps(pruned) if pruned else None
                device.last_settings_updated_at  = datetime.utcnow()

        self.repo.commit()
        self.repo.refresh(hw)
        return {"hardware_id": hardware_id, "schema": self.get_hardware_schema(hw)}

    def get_device_settings(self, device_id: int) -> dict:
        device = self.repo.get_device_by_id(device_id)
        if not device:
            raise NotFoundError("Device", device_id)
        return self._build_device_out(device)

    def update_device_overrides(self, device_id: int, overrides: dict[str, Any]) -> dict:
        device = self.repo.get_device_by_id(device_id)
        if not device:
            raise NotFoundError("Device", device_id)

        if device.hardware:
            valid_keys = _extract_keys(self.get_hardware_schema(device.hardware))
            filtered   = {k: v for k, v in overrides.items() if k in valid_keys}
        else:
            filtered = {}

        device.json_settings_override   = json.dumps(filtered) if filtered else None
        device.last_settings_updated_at = datetime.utcnow()
        self.repo.commit()
        self.repo.refresh(device)
        return self._build_device_out(device)

    def _build_device_out(self, device: ESP32Device) -> dict:
        schema    = self.get_hardware_schema(device.hardware) if device.hardware else {"sections": []}
        overrides = self.get_device_overrides(device)
        effective = self.get_effective_settings(device)
        return {
            "device_id":       device.id,
            "schema":          schema,
            "overrides":       overrides,
            "effective":       effective,
            "last_updated_at": device.last_settings_updated_at.isoformat() if device.last_settings_updated_at else None,
        }