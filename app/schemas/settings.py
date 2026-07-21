from typing import Any
from pydantic import BaseModel, Field

class SchemaPayload(BaseModel):
    json_schema: dict = Field(alias="schema")
    # BLE provisioning identity for this hardware type (see device_label_service.py) —
    # optional so the settings-schema editor can keep posting without them; when present
    # they're merged into the same json_settings blob alongside "sections".
    ble_prov_prefix: str | None = None
    ble_prov_pop_salt: str | None = None

class OverridesPayload(BaseModel):
    overrides: dict[str, Any]

class DeviceSettingsOut(BaseModel):
    device_id:       int
    json_schema:     dict
    overrides:       dict
    effective:       dict
    last_updated_at: str | None 