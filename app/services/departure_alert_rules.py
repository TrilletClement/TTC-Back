"""Pure rules of the "time to leave" notifications — no DB, no Firebase.

Kept apart from DepartureAlertService so they are unit-tested directly.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.exceptions import ValidationError

TRIGGERS = ("minutes", "led")
MIN_MINUTES, MAX_MINUTES = 1, 60
MAX_WINDOWS = 7
# The scan only looks this far ahead (mview rows with led_on_until <= now + horizon).
HORIZON_SECONDS = MAX_MINUTES * 60

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ── Windows ────────────────────────────────────────────────────────────────────

def validate_windows(windows) -> list[dict]:
    """Normalised copy of user-supplied windows, or ValidationError."""
    if not isinstance(windows, list) or len(windows) > MAX_WINDOWS:
        raise ValidationError(f"windows must be a list of at most {MAX_WINDOWS} entries")
    clean = []
    for w in windows:
        if not isinstance(w, dict):
            raise ValidationError("each window must be an object")
        days = w.get("days")
        if (not isinstance(days, list) or not days
                or any(not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6 for d in days)):
            raise ValidationError("window days must be a non-empty list of 0..6 (Monday = 0)")
        start, end = w.get("start"), w.get("end")
        if not isinstance(start, str) or not isinstance(end, str) or not _HHMM.match(start) or not _HHMM.match(end):
            raise ValidationError("window start/end must be HH:MM")
        clean.append({"days": sorted(set(days)), "start": start, "end": end})
    return clean


def _minutes(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def in_windows(windows: list[dict], local: datetime) -> bool:
    """True if the Brussels-local `local` falls in one of the windows ([] = always).

    start == end means the whole day; end < start spans midnight and belongs
    to the day it starts on (Friday 23:00–01:00 includes Saturday 00:30).
    """
    if not windows:
        return True
    day, now = local.weekday(), local.hour * 60 + local.minute
    for w in windows:
        start, end, days = _minutes(w["start"]), _minutes(w["end"]), w["days"]
        if start == end:
            if day in days:
                return True
        elif start < end:
            if day in days and start <= now < end:
                return True
        else:
            if (day in days and now >= start) or ((day - 1) % 7 in days and now < end):
                return True
    return False


# ── Which vehicle fires ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Arrival:
    """A row of active_incoming_intervals: one vehicle heading to one stop."""
    raw_trip_id: int
    service_date: str
    trip_stop_id: int
    led_on_from: int    # epoch: left the previous stop
    led_on_until: int   # epoch: arrives at this stop
    is_realtime: bool


def fires(trigger: str, minutes_before: int, arrival: Arrival, now: int, realtime_only: bool = False) -> bool:
    if realtime_only and not arrival.is_realtime:
        return False
    if arrival.led_on_until < now:
        return False
    if trigger == "led":
        return arrival.led_on_from <= now
    return arrival.led_on_until - now <= minutes_before * 60


def due_arrivals(trigger: str, minutes_before: int, arrivals: list[Arrival], now: int,
                 already_sent: set[tuple[int, str]], realtime_only: bool = False) -> list[Arrival]:
    """Arrivals that should notify now, soonest first, one per vehicle, never twice."""
    seen: set[tuple[int, str]] = set()
    due = []
    for a in sorted(arrivals, key=lambda a: a.led_on_until):
        key = (a.raw_trip_id, a.service_date)
        if key in seen or key in already_sent:
            continue
        if fires(trigger, minutes_before, a, now, realtime_only):
            seen.add(key)
            due.append(a)
    return due


# ── Text ────────────────────────────────────────────────────────────────────────

_TEXT = {
    "fr": {
        "minutes": "À {stop} dans {n} min. C'est le moment de partir !",
        "now": "Arrive à {stop} maintenant.",
        "led": "Vient de quitter l'arrêt précédent : à {stop} dans {n} min.",
        "scheduled": " (horaire théorique)",
        "test_title": "Notifications activées",
        "test_body": "Vous serez prévenu quand il est temps de partir.",
    },
    "en": {
        "minutes": "At {stop} in {n} min. Time to leave!",
        "now": "Arriving at {stop} now.",
        "led": "Just left the previous stop: at {stop} in {n} min.",
        "scheduled": " (scheduled)",
        "test_title": "Notifications are on",
        "test_body": "You'll be told when it's time to leave.",
    },
}


def text(lang: str) -> dict:
    return _TEXT.get(lang, _TEXT["fr"])


def message(lang: str, trigger: str, line: str, terminus: str | None, stop: str,
            arrival: Arrival, now: int) -> tuple[str, str]:
    """(title, body) of a notification, e.g. ("T1 → Standard", "À Pont Atlas dans 6 min…")."""
    t = text(lang)
    n = max(0, round((arrival.led_on_until - now) / 60))
    title = f"{line} → {terminus}" if terminus else line
    if n == 0:
        body = t["now"].format(stop=stop)
    elif trigger == "led":
        body = t["led"].format(stop=stop, n=n)
    else:
        body = t["minutes"].format(stop=stop, n=n)
    if not arrival.is_realtime:
        body += t["scheduled"]
    return title, body


def sent_retention_cutoff(now: datetime) -> datetime:
    """Dedup rows older than this can go: no service day lasts two days."""
    return now - timedelta(days=2)
