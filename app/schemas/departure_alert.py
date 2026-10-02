from typing import Literal, Optional

from pydantic import BaseModel, Field


class PushDeviceIn(BaseModel):
    token: str = Field(..., min_length=1, max_length=512)
    platform: Literal["android"] = "android"
    lang: str = Field("fr", max_length=5)


class PushDeviceTokenIn(BaseModel):
    token: str = Field(..., min_length=1, max_length=512)


class AlertWindow(BaseModel):
    days: list[int]
    start: str
    end: str


class DepartureAlertIn(BaseModel):
    strip_id: int
    stop_keys: list[list[str]]
    direction: Optional[int] = None
    trigger: Literal["minutes", "led"] = "minutes"
    minutes_before: int = 5
    windows: list[AlertWindow] = []
    enabled: bool = True


class DepartureAlertPatch(BaseModel):
    stop_keys: Optional[list[list[str]]] = None
    direction: Optional[int] = None
    trigger: Optional[Literal["minutes", "led"]] = None
    minutes_before: Optional[int] = None
    windows: Optional[list[AlertWindow]] = None
    enabled: Optional[bool] = None


class StripAlertsEnabledIn(BaseModel):
    enabled: bool
