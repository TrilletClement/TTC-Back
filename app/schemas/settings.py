from typing import Any
from pydantic import BaseModel

class SchemaPayload(BaseModel):
    json_schema: dict

class OverridesPayload(BaseModel):
    overrides: dict[str, Any]

class DeviceSettingsOut(BaseModel):
    device_id:       int
    json_schema:     dict
    overrides:       dict
    effective:       dict
    last_updated_at: str | None 