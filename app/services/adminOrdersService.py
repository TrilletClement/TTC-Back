from typing import Optional

from app.core.config import settings
from app.domain.exceptions import NotFoundError, BusinessError, ValidationError
from app.orm_models.order import Order
from app.orm_models.device import ESP32Device
from app.repositories.order_repo import OrderRepository
from app.schemas.order import OrderOut, AddressOut, OrderPatch, AssociateDevicePayload

ORDER_STATUSES = {"pending", "paid", "processing", "shipped", "delivered", "cancelled", "refunded"}


def _stripe_payment_url(payment_intent_id: Optional[str]) -> Optional[str]:
    if not payment_intent_id:
        return None
    mode = "test/" if settings.STRIPE_SECRET_KEY.startswith("sk_test_") else ""
    return f"https://dashboard.stripe.com/{mode}payments/{payment_intent_id}"


def _addr_dict(d) -> Optional[AddressOut]:
    if not d:
        return None
    return AddressOut(
        id=d.id,
        firstName=d.first_name,
        lastName=d.last_name,
        phone=d.phone,
        addressLine1=d.address_line1,
        city=d.city,
        postalCode=d.postal_code,
        country=d.country,
    )


def _build_order_out(o: Order, include_svg: bool = False) -> OrderOut:
    sd = o.shipping_details
    bd = o.billing_details
    same_address = sd and bd and sd.id == bd.id
    dev = o.esp_device
    return OrderOut(
        id=o.id,
        cart_ref=o.cart_ref,
        status=o.status,
        amount_cents=o.amount_cents,
        shipping_cost_cents=o.shipping_cost_cents,
        currency=o.currency,
        tracking_number=o.tracking_number,
        created_at=o.created_at,
        paid_at=o.paid_at,
        stripe_payment_url=_stripe_payment_url(o.payment_intent_id),
        board_id=o.board_id,
        board_name=o.board.name if o.board else None,
        user_id=o.user_id,
        user_email=o.user.email if o.user else None,
        esp_device_id=dev.id if dev else None,
        esp_device_mac=dev.mac_address if dev else None,
        esp_device_name=dev.name or dev.mac_address if dev else None,
        sendcloud_parcel_id=o.sendcloud_parcel_id,
        label_url=o.label_url,
        tracking_url=o.tracking_url,
        shipping_option_code=o.shipping_option_code,
        shipping_details=_addr_dict(sd),
        billing_details=None if same_address else _addr_dict(bd),
        same_address=same_address,
        svg_content=o.svg_content if include_svg else None,
    )


def _unique_device_name(base_name: str, existing_names: set[str]) -> str:
    candidate = base_name
    n = 2
    while candidate in existing_names:
        candidate = f"{base_name} {n}"
        n += 1
    return candidate


class AdminOrdersService:
    def __init__(self, repo: OrderRepository):
        self.repo = repo

    def list_orders(self, status: str | None, search: str | None, sort: str) -> list[OrderOut]:
        orders = self.repo.list_all(status)

        if search:
            s = search.strip().lower()
            orders = [
                o for o in orders
                if s in (o.user.email or "").lower()
                or (o.shipping_details and s in f"{o.shipping_details.first_name} {o.shipping_details.last_name}".lower())
                or (o.board and s in (o.board.name or "").lower())
                or s in str(o.id)
            ]

        reverse = sort in ("date_desc", "amount_desc")
        key = (lambda o: o.amount_cents or 0) if "amount" in sort else (lambda o: o.created_at or "")
        orders = sorted(orders, key=key, reverse=reverse)

        return [_build_order_out(o) for o in orders]

    def get_order(self, order_id: int, include_svg: bool = False) -> OrderOut:
        o = self.repo.get_by_id(order_id)
        if not o:
            raise NotFoundError("Order", order_id)
        return _build_order_out(o, include_svg)

    def list_unowned_devices(self) -> list[dict]:
        return [
            {"id": d.id, "mac_address": d.mac_address, "name": d.name}
            for d in self.repo.list_unowned_devices()
        ]

    def list_all_devices(self) -> list[dict]:
        return [
            {"id": d.id, "mac_address": d.mac_address, "name": d.name, "owner_email": d.owner.email if d.owner else None}
            for d in self.repo.list_all_devices()
        ]

    def patch_order(self, order_id: int, payload: OrderPatch) -> OrderOut:
        o = self.repo.get_by_id(order_id)
        if not o:
            raise NotFoundError("Order", order_id)

        if payload.status is not None:
            if payload.status not in ORDER_STATUSES:
                raise ValidationError(f"Invalid status. Allowed: {ORDER_STATUSES}")
            o.status = payload.status

        if payload.tracking_number is not None:
            o.tracking_number = payload.tracking_number or None

        if payload.shipping_details and o.shipping_details:
            sd = payload.shipping_details
            d  = o.shipping_details
            if sd.firstName    is not None: d.first_name    = sd.firstName
            if sd.lastName     is not None: d.last_name     = sd.lastName
            if sd.phone        is not None: d.phone         = sd.phone or None
            if sd.addressLine1 is not None: d.address_line1 = sd.addressLine1
            if sd.city         is not None: d.city          = sd.city
            if sd.postalCode   is not None: d.postal_code   = sd.postalCode
            if sd.country      is not None: d.country       = sd.country

        if payload.clear_esp_device:
            o.esp_device_id = None
        elif payload.esp_device_id is not None:
            o.esp_device_id = payload.esp_device_id

        self.repo.save(o)
        return _build_order_out(o)

    def associate_device(self, order_id: int, payload: AssociateDevicePayload) -> OrderOut:
        o = self.repo.get_by_id(order_id)
        if not o:
            raise NotFoundError("Order", order_id)
        if o.status != "paid":
            raise BusinessError("Order must be in 'paid' status to associate a device.")

        device = self.repo.get_device_by_id(payload.device_id)
        if not device:
            raise NotFoundError("Device", payload.device_id)
        if device.owner_id is not None:
            raise BusinessError("Device already has an owner.")

        device.owner_id = o.user_id
        device.board_id = o.board_id

        base_name = f"{o.board.name if o.board else 'Display'} Display"
        existing  = self.repo.get_device_names_for_owner(o.user_id, device.id)
        device.name = _unique_device_name(base_name, existing)

        o.status = "processing"
        o.esp_device_id = device.id

        self.repo.save(o)
        return _build_order_out(o)

    def ship_order(self, order_id: int, fallback_option_code: Optional[str] = None) -> OrderOut:
        from app.services import sendcloudService

        o = self.repo.get_by_id(order_id)
        if not o:
            raise NotFoundError("Order", order_id)
        if o.status not in {"paid", "processing"}:
            raise BusinessError(
                f"Cannot ship an order with status '{o.status}'. Must be 'paid' or 'processing'."
            )
        sd = o.shipping_details
        if not sd:
            raise BusinessError("Order has no shipping address.")

        option_code = o.shipping_option_code or fallback_option_code or ""
        if not option_code:
            raise BusinessError(
                "No shipping option configured. Add at least one option in the admin Shipping tab."
            )

        try:
            result = sendcloudService.create_parcel(
                name=f"{sd.first_name} {sd.last_name}".strip(),
                address=sd.address_line1,
                city=sd.city,
                postal_code=sd.postal_code,
                country_iso=sd.country if len(sd.country) == 2 else "BE",
                email=o.user.email if o.user else "",
                telephone=sd.phone or None,
                order_ref=o.cart_ref or str(o.id),
                shipping_option_code=option_code,
            )
        except RuntimeError as exc:
            raise BusinessError(str(exc))

        o.sendcloud_parcel_id = result.parcel_id
        o.label_url           = result.label_url
        o.tracking_url        = result.tracking_url
        if result.tracking_number:
            o.tracking_number = result.tracking_number
        o.status = "shipped"

        self.repo.save(o)
        return _build_order_out(o)

    def get_label_url(self, order_id: int) -> str:
        o = self.repo.get_by_id(order_id)
        if not o:
            raise NotFoundError("Order", order_id)
        if not o.label_url:
            raise BusinessError("No label available for this order.")
        return o.label_url