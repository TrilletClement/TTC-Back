import json
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.orm_models.device import ESP32Device, Hardware


def _extract_defaults(schema: dict) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for section in schema.get("sections", []):
        for s in section.get("settings", []):
            key = s.get("key")
            if key and "default" in s:
                result[key] = s["default"]
    return result


def _extract_keys(schema: dict) -> set[str]:
    keys: set[str] = set()
    for section in schema.get("sections", []):
        for s in section.get("settings", []):
            key = s.get("key")
            if key:
                keys.add(key)
    return keys


class SettingsService:

    @staticmethod
    def get_hardware_schema(hardware: Hardware) -> dict:
        if not hardware or not hardware.json_settings:
            return {"sections": []}
        try:
            data = json.loads(hardware.json_settings)
            return data if "sections" in data else {"sections": []}
        except (json.JSONDecodeError, TypeError):
            return {"sections": []}

    @staticmethod
    def get_device_overrides(device: ESP32Device) -> dict[str, Any]:
        if not device.json_settings_override:
            return {}
        try:
            return json.loads(device.json_settings_override)
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def get_effective_settings(device: ESP32Device) -> dict[str, Any]:
        schema = SettingsService.get_hardware_schema(device.hardware) if device.hardware else {"sections": []}
        defaults = _extract_defaults(schema)
        valid_keys = _extract_keys(schema)
        overrides = SettingsService.get_device_overrides(device)
        return {**defaults, **{k: v for k, v in overrides.items() if k in valid_keys}}

    @staticmethod
    def update_hardware_schema(db: Session, hardware_id: int, schema: dict) -> Hardware:
        hw = db.query(Hardware).filter(Hardware.id == hardware_id).first()
        if not hw:
            raise HTTPException(status_code=404, detail="Hardware not found")

        old_schema = SettingsService.get_hardware_schema(hw)
        removed_keys = _extract_keys(old_schema) - _extract_keys(schema)

        hw.json_settings = json.dumps(schema)

        if removed_keys:
            devices = db.query(ESP32Device).filter(ESP32Device.hardware_id == hardware_id).all()
            for device in devices:
                overrides = SettingsService.get_device_overrides(device)
                pruned = {k: v for k, v in overrides.items() if k not in removed_keys}
                device.json_settings_override = json.dumps(pruned) if pruned else None
                device.last_settings_updated_at = datetime.utcnow()

        db.commit()
        db.refresh(hw)
        return hw

    @staticmethod
    def update_device_overrides(db: Session, device_id: int, overrides: dict[str, Any]) -> ESP32Device:
        device = db.query(ESP32Device).filter(ESP32Device.id == device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")

        if device.hardware:
            schema = SettingsService.get_hardware_schema(device.hardware)
            valid_keys = _extract_keys(schema)
            filtered = {k: v for k, v in overrides.items() if k in valid_keys}
        else:
            filtered = {}

        device.json_settings_override = json.dumps(filtered) if filtered else None
        device.last_settings_updated_at = datetime.utcnow()
        db.commit()
        db.refresh(device)
        return device
