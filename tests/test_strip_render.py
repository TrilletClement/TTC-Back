"""Single-strip render (board_svg_service.build_strip_svg) and its service.

Pure in-memory ORM objects — no database needed.
"""
import xml.etree.ElementTree as ET

import pytest

import app.orm_models  # noqa: F401 — registers every mapper (relationship targets)
from app.domain.exceptions import NotFoundError, ValidationError
from app.orm_models.auth import Role, User
from app.orm_models.board import Board, BoardType, Led, LedStrip
from app.orm_models.gtfs import Line, Stop, TripStop
from app.services import board_svg_service as svg_service
from app.services.board_svg_service import build_export_svg, build_strip_svg
from app.services.strip_render_service import StripRenderService

SVG_NS = "{http://www.w3.org/2000/svg}"
STOP_NAMES = ["Sclessin", "Pont d'Avroy", "Place Saint-Lambert", "Opéra", "Guillemins & Gare", "<script>alert(1)</script>"]


def _led(led_id: int, index: int, name: str, type_: str = "") -> Led:
    ts = TripStop(id=led_id * 10, stop=Stop(name=name, stop_id=f"S{led_id}", agency_name="TEC"))
    return Led(id=led_id, ledstrip_index=index, type=type_, led_color="#00FF00", trip_stops=[ts])


def _board(owner_id: int = 1) -> Board:
    # Like real strips: one Led row per physical LED (max_led = 12), only the
    # first ones occupied (with trip stops).
    leds = [_led(i + 1, i + 1, name, "c_left" if i == 2 else "") for i, name in enumerate(STOP_NAMES)]
    leds += [
        Led(id=100 + i, ledstrip_index=i, type="", led_color="#00FF00", trip_stops=[])
        for i in range(len(STOP_NAMES) + 1, 13)
    ]
    strip = LedStrip(
        id=7, order_index=1, line_agency_name="TEC", line_color=None,
        custom_terminus_left_name="Sclessin", custom_terminus_right_name="Coronmeuse",
        line=Line(id=1, short_name="T1", color="#FFCD00", text_color="#000000"),
        leds=leds,
    )
    return Board(
        id=3, owner_id=owner_id, name="Test",
        board_type=BoardType(max_led=12, max_ledstrip=4),
        led_strips=[strip],
    )


def _parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)  # raises on malformed XML


# ── build_strip_svg ───────────────────────────────────────────────────────────

def test_strip_svg_is_well_formed_and_escapes_user_text():
    svg = build_strip_svg(_board(), 7, None, db=None)
    root = _parse(svg)
    assert root.tag == f"{SVG_NS}svg"
    # Stop names are user/feed controlled: never raw markup in the output.
    assert "<script>" not in svg
    assert not root.findall(f".//{SVG_NS}script")


def test_strip_svg_shows_every_stop_and_both_terminus_boxes():
    svg = build_strip_svg(_board(), 7, None, db=None)
    texts = [t.text for t in _parse(svg).iter(f"{SVG_NS}text")]
    assert "Sclessin" in texts and "Coronmeuse" in texts
    assert "T1" in texts
    for name in STOP_NAMES[1:5]:
        assert svg_service._shorten(name) in texts


def test_strip_svg_draws_users_stop_ring_like_the_export():
    svg = build_strip_svg(_board(), 7, None, db=None)
    assert 'stroke="#d84b3a"' in svg  # central (c_left) outer ring


def test_lit_leds_are_filled_with_their_colour():
    board = _board()
    dark = build_strip_svg(board, 7, None, db=None)
    live = build_strip_svg(board, 7, {2: "#FF00AA"}, db=None)
    assert "#FF00AA" not in dark
    assert 'fill="#FF00AA"' in live
    assert 'fill-opacity="0.35"' in live  # halo


def test_physical_export_is_unaffected_by_live_rendering():
    export = build_export_svg(_board(), with_frame=False, db=None)
    assert "fill-opacity" not in export
    _parse(export)


def test_strip_svg_embeds_brand_font():
    svg = build_strip_svg(_board(), 7, None, db=None)
    assert svg_service._BRUSSELINE_B64, "Brusseline font file missing from app/assets/fonts"
    assert "@font-face" in svg and "Brusseline" in svg


def test_unknown_strip_and_missing_board_type():
    board = _board()
    with pytest.raises(LookupError):
        build_strip_svg(board, 999, None, db=None)
    board.board_type = None
    with pytest.raises(ValueError):
        build_strip_svg(board, 7, None, db=None)


# ── StripRenderService (access control, validation) ──────────────────────────

class _FakeBoardService:
    def __init__(self, on_ids: set[int]):
        self.on_ids = on_ids

    def get_board_status(self, board_id, current_user):
        return {"ledStrips": [{"id": 7, "leds": [{"ledId": i, "isOn": i in self.on_ids} for i in range(1, 7)]}]}


def _user(user_id: int, admin: bool = False) -> User:
    return User(id=user_id, roles=[Role(name="admin")] if admin else [])


@pytest.fixture
def service(monkeypatch):
    board = _board(owner_id=1)
    monkeypatch.setattr("app.services.strip_render_service.load_board_for_export", lambda board_id, db: board if board_id == 3 else None)
    return StripRenderService(db=None, board_service=_FakeBoardService(on_ids={4}))


def test_owner_gets_live_render(service):
    svg, leds_on = service.render_svg(3, 7, live=True, current_user=_user(1))
    assert leds_on == 1
    assert 'fill="#00FF00"' in svg


def test_other_users_board_is_not_found(service):
    with pytest.raises(NotFoundError):
        service.render_svg(3, 7, live=False, current_user=_user(2))


def test_admin_can_render_any_board(service):
    service.render_svg(3, 7, live=False, current_user=_user(2, admin=True))


def test_unknown_board_or_strip_is_not_found(service):
    with pytest.raises(NotFoundError):
        service.render_svg(404, 7, live=False, current_user=_user(1))
    with pytest.raises(NotFoundError):
        service.render_svg(3, 999, live=False, current_user=_user(1))


@pytest.mark.parametrize("width", [0, 199, 1601, 100000])
def test_png_width_is_bounded(service, width):
    with pytest.raises(ValidationError):
        service.render_png(3, 7, live=False, width=width, current_user=_user(1))


def test_png_render():
    pytest.importorskip("cairosvg")
    board = _board()
    import app.services.strip_render_service as mod
    svc = StripRenderService(db=None, board_service=_FakeBoardService(on_ids=set()))
    mod_load = mod.load_board_for_export
    mod.load_board_for_export = lambda board_id, db: board
    try:
        png, _ = svc.render_png(3, 7, live=False, width=400, current_user=_user(1))
    finally:
        mod.load_board_for_export = mod_load
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
