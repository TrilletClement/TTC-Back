from typing import Optional
from pydantic import BaseModel


class PriceEntryIn(BaseModel):
    board_type_id:       int
    base_price_cents:    int
    reduced_price_cents: int


class PriceVersionCreate(BaseModel):
    label:  Optional[str] = None
    prices: list[PriceEntryIn]
