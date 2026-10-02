import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload

from app.orm_models.board import Led, LedStrip, trip_stop_led_link
from app.orm_models.departure_alert import DepartureAlert, DepartureAlertSent, PushDevice
from app.orm_models.gtfs import Trip, TripStop
from app.services.departure_alert_rules import Arrival


class DepartureAlertRepository:
    def __init__(self, db: Session):
        self.db = db

    # ── Push devices ─────────────────────────────────────────────────────────

    def get_device_by_token(self, token: str) -> PushDevice | None:
        return self.db.query(PushDevice).filter(PushDevice.token == token).first()

    def devices_for_users(self, user_ids: list[int]) -> list[PushDevice]:
        if not user_ids:
            return []
        return self.db.query(PushDevice).filter(PushDevice.user_id.in_(user_ids)).all()

    def delete_devices_by_token(self, tokens: list[str]) -> None:
        if tokens:
            self.db.query(PushDevice).filter(PushDevice.token.in_(tokens)).delete(synchronize_session=False)
            self.db.commit()

    # ── Alerts ────────────────────────────────────────────────────────────────

    def get_strip(self, strip_id: int) -> LedStrip | None:
        return (
            self.db.query(LedStrip)
            .options(joinedload(LedStrip.board), joinedload(LedStrip.line))
            .filter(LedStrip.id == strip_id)
            .first()
        )

    def get_alert(self, alert_id: int) -> DepartureAlert | None:
        return self.db.query(DepartureAlert).filter(DepartureAlert.id == alert_id).first()

    def alerts_for_user(self, user_id: int) -> list[DepartureAlert]:
        return (
            self.db.query(DepartureAlert)
            .options(joinedload(DepartureAlert.led_strip).joinedload(LedStrip.line))
            .filter(DepartureAlert.user_id == user_id)
            .order_by(DepartureAlert.id)
            .all()
        )

    def count_for_user(self, user_id: int) -> int:
        return self.db.query(DepartureAlert).filter(DepartureAlert.user_id == user_id).count()

    def alerts_for_strip(self, user_id: int, strip_id: int) -> list[DepartureAlert]:
        return (
            self.db.query(DepartureAlert)
            .filter(DepartureAlert.user_id == user_id, DepartureAlert.led_strip_id == strip_id)
            .all()
        )

    def enabled_alerts_with_devices(self) -> list[DepartureAlert]:
        """Enabled alerts of users with at least one phone, strips not archived."""
        has_device = sa.exists().where(PushDevice.user_id == DepartureAlert.user_id)
        return (
            self.db.query(DepartureAlert)
            .options(joinedload(DepartureAlert.led_strip).joinedload(LedStrip.line))
            .filter(DepartureAlert.enabled.is_(True), has_device)
            .all()
        )

    def save(self, obj) -> None:
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)

    def delete(self, obj) -> None:
        self.db.delete(obj)
        self.db.commit()

    def commit(self) -> None:
        self.db.commit()

    # ── Strip stops ───────────────────────────────────────────────────────────

    def strip_leds(self, strip_id: int) -> list[Led]:
        """The strip's LEDs with their stops and trips (for names and directions)."""
        return (
            self.db.query(Led)
            .options(
                joinedload(Led.trip_stops).joinedload(TripStop.stop),
                joinedload(Led.trip_stops).joinedload(TripStop.trip).joinedload(Trip.terminus),
            )
            .filter(Led.ledstrip_id == strip_id)
            .order_by(Led.ledstrip_index)
            .all()
        )

    def alert_trip_stops(self, alert: DepartureAlert) -> list[TripStop]:
        """Trip stops of the strip's own line at the alert's station (and direction)."""
        strip = alert.led_strip
        pairs = [tuple(k) for k in alert.stop_keys or []]
        if not pairs:
            return []
        q = (
            self.db.query(TripStop)
            .options(joinedload(TripStop.trip).joinedload(Trip.terminus))
            .join(trip_stop_led_link, trip_stop_led_link.c.trip_stop_id == TripStop.id)
            .join(Led, Led.id == trip_stop_led_link.c.led_id)
            .join(Trip, Trip.id == TripStop.trip_id)
            .filter(
                Led.ledstrip_id == alert.led_strip_id,
                sa.tuple_(TripStop.stop_stop_id, TripStop.stop_agency_name).in_(pairs),
                Trip.line_id == strip.line_id,
                Trip.line_agency_name == strip.line_agency_name,
            )
        )
        if alert.direction is not None:
            q = q.filter(Trip.direction == alert.direction)
        return q.distinct().all()

    # ── Realtime ──────────────────────────────────────────────────────────────

    def upcoming_arrivals(self, trip_stop_ids: list[int], now: int, horizon: int) -> list[Arrival]:
        """Vehicles reaching these stops between now and now + horizon (same view as the LEDs)."""
        if not trip_stop_ids:
            return []
        rows = self.db.execute(sa.text("""
            SELECT raw_trip_id, service_date, canonical_trip_stop_id,
                   led_on_from, led_on_until, is_realtime
            FROM active_incoming_intervals
            WHERE canonical_trip_stop_id = ANY(:ids)
              AND led_on_until BETWEEN :now AND :until
        """), {"ids": trip_stop_ids, "now": now, "until": now + horizon}).all()
        return [
            Arrival(r.raw_trip_id, r.service_date, r.canonical_trip_stop_id,
                    int(r.led_on_from), int(r.led_on_until), bool(r.is_realtime))
            for r in rows
        ]

    # ── Dedup log ─────────────────────────────────────────────────────────────

    def sent_keys(self, alert_ids: list[int]) -> set[tuple[int, int, str]]:
        if not alert_ids:
            return set()
        rows = (
            self.db.query(DepartureAlertSent.alert_id, DepartureAlertSent.raw_trip_id, DepartureAlertSent.service_date)
            .filter(DepartureAlertSent.alert_id.in_(alert_ids))
            .all()
        )
        return {(r.alert_id, r.raw_trip_id, r.service_date) for r in rows}

    def record_sent(self, alert_id: int, raw_trip_id: int, service_date: str) -> None:
        self.db.execute(
            pg_insert(DepartureAlertSent)
            .values(alert_id=alert_id, raw_trip_id=raw_trip_id, service_date=service_date)
            .on_conflict_do_nothing(constraint="uq_departure_alert_sent_trip")
        )
        self.db.commit()

    def purge_sent_before(self, cutoff: datetime.datetime) -> None:
        self.db.query(DepartureAlertSent).filter(DepartureAlertSent.sent_at < cutoff).delete(synchronize_session=False)
        self.db.commit()
