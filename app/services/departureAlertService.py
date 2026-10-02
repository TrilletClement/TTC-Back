"""'Time to leave' notifications: phones, alerts, and the 20 s evaluation.

An alert = one station of one of the user's strips (+ direction), a trigger
("minutes" before arrival, or when the station's LED turns on), time windows
and an on/off switch (also toggled from the Android widget). The scheduler
calls evaluate(): it reads active_incoming_intervals — the very view that
lights the LEDs — so a notification always matches what the board shows.
"""
import datetime
import logging
from zoneinfo import ZoneInfo

from app.domain.exceptions import NotFoundError, ValidationError
from app.orm_models.auth import User
from app.orm_models.board import LedStrip
from app.orm_models.departure_alert import DepartureAlert, PushDevice
from app.repositories.departure_alert_repo import DepartureAlertRepository
from app.services import departure_alert_rules as rules
from app.services.push_sender import Push, PushSender, push_sender

logger = logging.getLogger(__name__)

BRUSSELS = ZoneInfo("Europe/Brussels")
MAX_ALERTS_PER_USER = 20
LANGS = ("fr", "en")


class DepartureAlertService:
    def __init__(self, repo: DepartureAlertRepository, sender: PushSender = push_sender):
        self.repo = repo
        self.sender = sender

    # ── Phones ────────────────────────────────────────────────────────────────

    def register_device(self, user: User, token: str, platform: str, lang: str) -> None:
        """Upsert: a token moves to whoever is signed in on that phone now."""
        token = (token or "").strip()
        if not token or len(token) > 512:
            raise ValidationError("invalid token")
        device = self.repo.get_device_by_token(token) or PushDevice(token=token)
        device.user_id = user.id
        device.platform = platform if platform in ("android",) else "android"
        device.lang = lang if lang in LANGS else "fr"
        device.last_seen_at = datetime.datetime.now(datetime.timezone.utc)
        self.repo.save(device)

    def unregister_device(self, user: User, token: str) -> None:
        device = self.repo.get_device_by_token((token or "").strip())
        if device and device.user_id == user.id:
            self.repo.delete(device)

    def send_test(self, user: User) -> int:
        devices = self.repo.devices_for_users([user.id])
        pushes = [
            Push(d.token, rules.text(d.lang)["test_title"], rules.text(d.lang)["test_body"], {"type": "test"})
            for d in devices
        ]
        self.repo.delete_devices_by_token(self.sender.send(pushes))
        return len(pushes)

    # ── Strip stations ────────────────────────────────────────────────────────

    def _owned_strip(self, user: User, strip_id: int) -> LedStrip:
        strip = self.repo.get_strip(strip_id)
        if not strip or not strip.board or strip.board.owner_id != user.id or strip.board.archived:
            raise NotFoundError("LED strip", strip_id)
        return strip

    def _stations(self, strip: LedStrip) -> list[dict]:
        """One entry per LED of the strip, in board order, for its own line."""
        stations, seen = [], set()
        for led in self.repo.strip_leds(strip.id):
            keys, directions, name = set(), {}, led.custom_name
            for ts in led.trip_stops:
                trip = ts.trip
                if not trip or trip.line_id != strip.line_id or trip.line_agency_name != strip.line_agency_name:
                    continue  # cross-line trunk sharing: another line's stop on this LED
                keys.add((ts.stop_stop_id, ts.stop_agency_name))
                if trip.direction not in directions:
                    directions[trip.direction] = trip.terminus.name if trip.terminus else None
                if not name and ts.stop:
                    name = ts.stop.name
            frozen = frozenset(keys)
            if not keys or frozen in seen:
                continue
            seen.add(frozen)
            stations.append({
                "stop_keys": sorted([list(k) for k in keys]),
                "name": name or "?",
                "central": led.type == "central",
                "directions": [{"direction": d, "terminus": t} for d, t in sorted(directions.items())],
            })
        return stations

    def strip_stations(self, user: User, strip_id: int) -> dict:
        strip = self._owned_strip(user, strip_id)
        return {
            "strip_id": strip.id,
            "board_id": strip.board_id,
            "line_short_name": strip.line.short_name if strip.line else None,
            "line_color": strip.line_color or (strip.line.color if strip.line else None),
            "line_text_color": strip.line.text_color if strip.line else None,
            "stations": self._stations(strip),
        }

    # ── Alerts ────────────────────────────────────────────────────────────────

    def _to_dict(self, alert: DepartureAlert, stations: list[dict]) -> dict:
        strip = alert.led_strip
        keys = sorted([list(k) for k in alert.stop_keys or []])
        station = self._station_of(alert, stations)
        terminus = None
        if station and alert.direction is not None:
            terminus = next((d["terminus"] for d in station["directions"] if d["direction"] == alert.direction), None)
        return {
            "id": alert.id,
            "board_id": strip.board_id,
            "strip_id": strip.id,
            "line_short_name": strip.line.short_name if strip.line else None,
            "line_color": strip.line_color or (strip.line.color if strip.line else None),
            "stop_keys": keys,
            "stop_name": station["name"] if station else alert.stop_name,
            "stop_on_board": station is not None,
            "direction": alert.direction,
            "terminus": terminus,
            "trigger": alert.trigger,
            "minutes_before": alert.minutes_before,
            "windows": alert.windows or [],
            "enabled": alert.enabled,
        }

    def list_alerts(self, user: User) -> list[dict]:
        alerts = self.repo.alerts_for_user(user.id)
        stations_by_strip: dict[int, list[dict]] = {}
        out = []
        for alert in alerts:
            if alert.led_strip_id not in stations_by_strip:
                stations_by_strip[alert.led_strip_id] = self._stations(alert.led_strip)
            out.append(self._to_dict(alert, stations_by_strip[alert.led_strip_id]))
        return out

    @staticmethod
    def _station_of(alert: DepartureAlert, stations: list[dict]) -> dict | None:
        keys = sorted([list(k) for k in alert.stop_keys or []])
        return next((s for s in stations if s["stop_keys"] == keys), None)

    def _apply(self, alert: DepartureAlert, stations: list[dict], data: dict) -> None:
        """Validates and copies the editable fields present in `data`."""
        if "stop_keys" in data:
            alert.stop_keys = sorted([list(k) for k in data["stop_keys"] or []])
            station = self._station_of(alert, stations)
            if not station:
                raise ValidationError("this stop is not on the strip")
            alert.stop_name = station["name"][:100]
        station = self._station_of(alert, stations)
        if "direction" in data:
            alert.direction = data["direction"]
        if alert.direction is not None:
            known = [d["direction"] for d in station["directions"]] if station else [0, 1]
            if alert.direction not in known:
                raise ValidationError("invalid direction for this stop")
        if "trigger" in data:
            if data["trigger"] not in rules.TRIGGERS:
                raise ValidationError("trigger must be 'minutes' or 'led'")
            alert.trigger = data["trigger"]
        if "minutes_before" in data:
            m = data["minutes_before"]
            if not isinstance(m, int) or not rules.MIN_MINUTES <= m <= rules.MAX_MINUTES:
                raise ValidationError(f"minutes_before must be {rules.MIN_MINUTES}–{rules.MAX_MINUTES}")
            alert.minutes_before = m
        if "windows" in data:
            alert.windows = rules.validate_windows(data["windows"])
        if "enabled" in data:
            alert.enabled = bool(data["enabled"])

    def create_alert(self, user: User, data: dict) -> dict:
        strip = self._owned_strip(user, data.get("strip_id"))
        if self.repo.count_for_user(user.id) >= MAX_ALERTS_PER_USER:
            raise ValidationError(f"at most {MAX_ALERTS_PER_USER} alerts")
        if "stop_keys" not in data:
            raise ValidationError("stop_keys is required")
        stations = self._stations(strip)
        alert = DepartureAlert(user_id=user.id, led_strip_id=strip.id, direction=None,
                               trigger="minutes", minutes_before=5, windows=[], enabled=True)
        alert.led_strip = strip
        self._apply(alert, stations, data)
        self.repo.save(alert)
        return self._to_dict(alert, stations)

    def _owned_alert(self, user: User, alert_id: int) -> DepartureAlert:
        alert = self.repo.get_alert(alert_id)
        if not alert or alert.user_id != user.id:
            raise NotFoundError("Alert", alert_id)
        return alert

    def update_alert(self, user: User, alert_id: int, data: dict) -> dict:
        alert = self._owned_alert(user, alert_id)
        stations = self._stations(alert.led_strip)
        self._apply(alert, stations, data)
        self.repo.save(alert)
        return self._to_dict(alert, stations)

    def delete_alert(self, user: User, alert_id: int) -> None:
        self.repo.delete(self._owned_alert(user, alert_id))

    def set_strip_enabled(self, user: User, strip_id: int, enabled: bool) -> dict:
        """The widget's bell: every alert of the user on that strip at once."""
        self._owned_strip(user, strip_id)
        alerts = self.repo.alerts_for_strip(user.id, strip_id)
        for alert in alerts:
            alert.enabled = enabled
        self.repo.commit()
        return {"strip_id": strip_id, "enabled": enabled, "count": len(alerts)}

    # ── Evaluation (scheduler, every 20 s) ───────────────────────────────────

    def evaluate(self, now: int | None = None) -> int:
        """Sends the notifications due now; returns how many were sent."""
        now = now if now is not None else int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        local = datetime.datetime.fromtimestamp(now, BRUSSELS)

        alerts = [
            a for a in self.repo.enabled_alerts_with_devices()
            if a.led_strip and a.led_strip.board and not a.led_strip.board.archived
            and rules.in_windows(a.windows or [], local)
        ]
        if not alerts:
            return 0

        sent_keys = self.repo.sent_keys([a.id for a in alerts])
        devices_by_user: dict[int, list[PushDevice]] = {}
        for d in self.repo.devices_for_users(list({a.user_id for a in alerts})):
            devices_by_user.setdefault(d.user_id, []).append(d)

        pushes: list[Push] = []
        to_record: list[tuple[int, int, str]] = []
        for alert in alerts:
            trip_stops = {ts.id: ts for ts in self.repo.alert_trip_stops(alert)}
            arrivals = self.repo.upcoming_arrivals(list(trip_stops), now, rules.HORIZON_SECONDS)
            already = {(t, d) for (a_id, t, d) in sent_keys if a_id == alert.id}
            strip = alert.led_strip
            for arrival in rules.due_arrivals(alert.trigger, alert.minutes_before, arrivals, now,
                                              already, realtime_only=bool(strip.rt_only)):
                trip = trip_stops[arrival.trip_stop_id].trip
                terminus = trip.terminus.name if trip and trip.terminus else None
                line = strip.line.short_name if strip.line else ""
                for device in devices_by_user.get(alert.user_id, []):
                    title, body = rules.message(device.lang, alert.trigger, line, terminus,
                                                alert.stop_name, arrival, now)
                    pushes.append(Push(device.token, title, body, {
                        "type": "departure",
                        "alert_id": str(alert.id),
                        "board_id": str(strip.board_id),
                        "strip_id": str(strip.id),
                    }))
                to_record.append((alert.id, arrival.raw_trip_id, arrival.service_date))

        # Recorded before sending: a crash mid-send must not spam on the next run.
        for key in to_record:
            self.repo.record_sent(*key)
        self.repo.delete_devices_by_token(self.sender.send(pushes))
        self.repo.purge_sent_before(rules.sent_retention_cutoff(datetime.datetime.now(datetime.timezone.utc)))
        return len(pushes)
