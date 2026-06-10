from typing import Optional
from pydantic import BaseModel


class PriceEntryIn(BaseModel):
    board_type_id:       int
    base_price_cents:    int
    reduced_price_cents: int


class ShippingRateIn(BaseModel):
    country_code:      str
    country_name:      str
    cost_cents:        int
    delivery_days_min: int
    delivery_days_max: int


class PriceVersionCreate(BaseModel):
    label:    Optional[str] = None
    prices:   list[PriceEntryIn]
    shipping: list[ShippingRateIn] = []