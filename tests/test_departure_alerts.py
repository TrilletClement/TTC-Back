"""Departure alerts: pure rules + DepartureAlertService.evaluate with fakes."""
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import app.orm_models  # noqa: F401 — registers every mapper
from app.domain.exceptions import ValidationError
from app.services import departure_alert_rules as rules
from app.services.departure_alert_rules import Arrival
from app.services.departureAlertService import DepartureAlertService

BXL = ZoneInfo("Europe/Brussels")


def _local(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=BXL)


# ── Windows ──────────────────────────────────────────────────────────────────

WAKE_UP = {"days": [0, 1, 2, 3, 4], "start": "06:30", "end": "08:30"}


def test_no_window_means_always():
    assert rules.in_windows([], _local(2026, 10, 4, 3, 0))


def test_weekday_morning_window():
    assert rules.in_windows([WAKE_UP], _local(2026, 10, 5, 7, 0))       # Monday 07:00
    assert not rules.in_windows([WAKE_UP], _local(2026, 10, 5, 8, 30))  # end excluded
    assert not rules.in_windows([WAKE_UP], _local(2026, 10, 4, 7, 0))   # Sunday


def test_window_across_midnight_belongs_to_its_start_day():
    night = [{"days": [4], "start": "23:00", "end": "01:00"}]           # Friday night
    assert rules.in_windows(night, _local(2026, 10, 9, 23, 30))        # Friday 23:30
    assert rules.in_windows(night, _local(2026, 10, 10, 0, 30))        # Saturday 00:30
    assert not rules.in_windows(night, _local(2026, 10, 9, 0, 30))     # Friday 00:30


def test_same_start_and_end_is_the_whole_day():
    assert rules.in_windows([{"days": [6], "start": "00:00", "end": "00:00"}], _local(2026, 10, 4, 15, 0))


def test_validate_windows():
    assert rules.validate_windows([{"days": [4, 0, 0], "start": "06:30", "end": "08:00"}]) == [
        {"days": [0, 4], "start": "06:30", "end": "08:00"}
    ]
    for bad in ([{"days": [7], "start": "06:30", "end": "08:00"}],
                [{"days": [], "start": "06:30", "end": "08:00"}],
                [{"days": [1], "start": "6:30", "end": "08:00"}],
                [{"days": [True], "start": "06:30", "end": "08:00"}],
                [WAKE_UP] * 8, "always"):
        with pytest.raises(ValidationError):
            rules.validate_windows(bad)


# ── Firing ───────────────────────────────────────────────────────────────────

NOW = 1_800_000_000


def _arr(trip, arrives_in, left_ago=60, rt=True, ts=10):
    return Arrival(trip, "20261005", ts, NOW - left_ago, NOW + arrives_in, rt)


def test_minutes_trigger():
    assert rules.fires("minutes", 5, _arr(1, 299), NOW)
    assert rules.fires("minutes", 5, _arr(1, 300), NOW)
    assert not rules.fires("minutes", 5, _arr(1, 301), NOW)
    assert not rules.fires("minutes", 5, _arr(1, -1), NOW)      # already gone


def test_led_trigger_is_the_led_window():
    assert rules.fires("led", 5, _arr(1, 600, left_ago=10), NOW)
    assert not rules.fires("led", 5, _arr(1, 600, left_ago=-10), NOW)   # not left the previous stop yet


def test_realtime_only_strips_ignore_scheduled_vehicles():
    assert not rules.fires("minutes", 5, _arr(1, 60, rt=False), NOW, realtime_only=True)


def test_due_arrivals_once_per_vehicle_soonest_first():
    arrivals = [_arr(2, 200, ts=11), _arr(1, 100, ts=10), _arr(1, 120, ts=12), _arr(3, 1000)]
    due = rules.due_arrivals("minutes", 5, arrivals, NOW, already_sent=set())
    assert [(a.raw_trip_id, a.trip_stop_id) for a in due] == [(1, 10), (2, 11)]
    assert rules.due_arrivals("minutes", 5, arrivals, NOW, already_sent={(1, "20261005")})[0].raw_trip_id == 2


def test_message():
    assert rules.message("fr", "minutes", "T1", "Standard", "Pont Atlas", _arr(1, 360), NOW) == (
        "T1 → Standard", "À Pont Atlas dans 6 min. C'est le moment de partir !")
    assert rules.message("en", "led", "71", None, "Flagey", _arr(1, 120, rt=False), NOW) == (
        "71", "Just left the previous stop: at Flagey in 2 min. (scheduled)")
    assert rules.message("de", "minutes", "7", "X", "Y", _arr(1, 10), NOW)[1] == "Arrive à Y maintenant."


# ── evaluate() ───────────────────────────────────────────────────────────────

class _FakeSender:
    def __init__(self, dead=()):
        self.sent, self.dead = [], list(dead)

    def send(self, pushes):
        self.sent.extend(pushes)
        return self.dead


class _FakeRepo:
    def __init__(self, alerts, devices, arrivals, trip_stops):
        self.alerts, self.devices, self.arrivals, self.trip_stops = alerts, devices, arrivals, trip_stops
        self.recorded, self.deleted_tokens = [], []

    def enabled_alerts_with_devices(self):
        return [a for a in self.alerts if a.enabled]

    def sent_keys(self, alert_ids):
        return {k for k in self.recorded if k[0] in alert_ids}

    def devices_for_users(self, user_ids):
        return [d for d in self.devices if d.user_id in user_ids]

    def alert_trip_stops(self, alert):
        return self.trip_stops

    def upcoming_arrivals(self, ids, now, horizon):
        return [a for a in self.arrivals if a.trip_stop_id in ids]

    def record_sent(self, alert_id, raw_trip_id, service_date):
        self.recorded.append((alert_id, raw_trip_id, service_date))

    def delete_devices_by_token(self, tokens):
        self.deleted_tokens.extend(tokens)

    def purge_sent_before(self, cutoff):
        pass


def _alert(**kw):
    strip = SimpleNamespace(id=5, board_id=2, rt_only=False, line=SimpleNamespace(short_name="T1"),
                            board=SimpleNamespace(archived=False))
    base = dict(id=1, user_id=7, enabled=True, trigger="minutes", minutes_before=5, windows=[],
                stop_name="Pont Atlas", led_strip=strip)
    base.update(kw)
    return SimpleNamespace(**base)


def _setup(alert, arrivals, dead=()):
    trip = SimpleNamespace(terminus=SimpleNamespace(name="Standard"))
    repo = _FakeRepo([alert], [SimpleNamespace(user_id=7, token="tok", lang="fr")], arrivals,
                     [SimpleNamespace(id=10, trip=trip)])
    sender = _FakeSender(dead)
    return repo, sender, DepartureAlertService(repo, sender)


def test_evaluate_sends_once_per_vehicle():
    repo, sender, svc = _setup(_alert(), [_arr(1, 240)])
    assert svc.evaluate(NOW) == 1
    assert (sender.sent[0].title, sender.sent[0].body) == ("T1 → Standard", "À Pont Atlas dans 4 min. C'est le moment de partir !")
    assert sender.sent[0].data == {"type": "departure", "alert_id": "1", "board_id": "2", "strip_id": "5"}
    assert repo.recorded == [(1, 1, "20261005")]
    assert svc.evaluate(NOW + 20) == 0          # same vehicle, next run


def test_evaluate_respects_windows_and_switch():
    # 1_800_000_000 is Friday 15 Jan 2027, 09:00 in Brussels: after the 06:30–08:30 window.
    _, sender, svc = _setup(_alert(windows=[WAKE_UP]), [_arr(1, 60)])
    assert svc.evaluate(NOW) == 0
    _, sender, svc = _setup(_alert(enabled=False), [_arr(1, 60)])
    assert svc.evaluate(NOW) == 0


def test_evaluate_drops_dead_tokens():
    repo, _, svc = _setup(_alert(), [_arr(1, 60)], dead=["tok"])
    svc.evaluate(NOW)
    assert repo.deleted_tokens == ["tok"]
