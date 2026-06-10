from app.repositories.price_repo import PriceRepository
from app.schemas.price import PriceVersionCreate


class AdminPricesService:
    def __init__(self, repo: PriceRepository):
        self.repo = repo

    def list_versions(self) -> list[dict]:
        versions    = self.repo.list_versions()
        board_types = self.repo.get_board_types()
        latest_id   = versions[0].id if versions else None

        return [
            {
                "id":        v.id,
                "label":     v.label,
                "createdAt": v.created_at.isoformat(),
                "isCurrent": v.id == latest_id,
                "prices": [
                    {
                        "boardTypeId":       p.board_type_id,
                        "boardTypeName":     board_types.get(p.board_type_id, f"Type {p.board_type_id}"),
                        "basePriceCents":    p.base_price_cents,
                        "reducedPriceCents": p.reduced_price_cents,
                    }
                    for p in sorted(v.prices, key=lambda p: p.board_type_id)
                ],
                "shippingRates": [
                    {
                        "countryCode":     r.country_code,
                        "countryName":     r.country_name,
                        "costCents":       r.cost_cents,
                        "deliveryDaysMin": r.delivery_days_min,
                        "deliveryDaysMax": r.delivery_days_max,
                    }
                    for r in v.shipping_rates
                ],
            }
            for v in versions
        ]

    def create_version(self, payload: PriceVersionCreate) -> dict:
        version = self.repo.create_version(payload.label or None)

        for entry in payload.prices:
            self.repo.add_price_entry(
                version.id,
                entry.board_type_id,
                entry.base_price_cents,
                entry.reduced_price_cents,
            )

        for rate in payload.shipping:
            self.repo.add_shipping_rate(
                version.id,
                rate.country_code,
                rate.country_name,
                rate.cost_cents,
                rate.delivery_days_min,
                rate.delivery_days_max,
            )

        self.repo.commit_and_refresh(version)
        return {"id": version.id, "label": version.label, "createdAt": version.created_at.isoformat()}