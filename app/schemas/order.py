from typing import Optional
from pydantic import BaseModel
from datetime import datetime


class AddressOut(BaseModel):
    id:           int
    firstName:    Optional[str]
    lastName:     Optional[str]
    phone:        Optional[str]
    addressLine1: Optional[str]
    city:         Optional[str]
    postalCode:   Optional[str]
    country:      Optional[str]


class OrderItemOut(BaseModel):
    id:              int
    board_id:        Optional[int]
    board_name:      Optional[str]
    svg_content:     Optional[str]
    amount_cents:    int
    esp_device_id:   Optional[int]
    esp_device_mac:  Optional[str]
    esp_device_name: Optional[str]


class OrderOut(BaseModel):
    id:                  int
    cart_ref:            Optional[str]
    status:              str
    amount_cents:        Optional[int]
    shipping_cost_cents: Optional[int]
    currency:            Optional[str]
    tracking_number:     Optional[str]
    created_at:          Optional[datetime]
    paid_at:             Optional[datetime]
    stripe_payment_url:  Optional[str]
    user_id:             Optional[int]
    user_email:          Optional[str]
    sendcloud_parcel_id:  Optional[str] = None
    label_url:            Optional[str] = None
    tracking_url:         Optional[str] = None
    shipping_option_code: Optional[str] = None
    shipping_details:    Optional[AddressOut]
    billing_details:     Optional[AddressOut]
    same_address:        Optional[bool]
    items:               list[OrderItemOut] = []


class AddressPatch(BaseModel):
    firstName:    Optional[str] = None
    lastName:     Optional[str] = None
    phone:        Optional[str] = None
    addressLine1: Optional[str] = None
    city:         Optional[str] = None
    postalCode:   Optional[str] = None
    country:      Optional[str] = None


class OrderPatch(BaseModel):
    status:           Optional[str] = None
    tracking_number:  Optional[str] = None
    shipping_details: Optional[AddressPatch] = None


class AssociateDevicePayload(BaseModel):
    device_id: int
