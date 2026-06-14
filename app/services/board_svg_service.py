"""
Physical SVG export for boards.

All coordinates are in millimetres (SVG viewBox units = mm, 1 unit = 1 mm).
No nested SVG elements — every element is placed at absolute canvas positions.
"""
import base64
from pathlib import Path
from xml.sax.saxutils import escape as _esc

from sqlalchemy.orm import Session, joinedload

# Brusseline Bold font embedded as base64 so the SVG is self-contained.
_FONT_PATH = Path(__file__).parent.parent.parent.parent / "doc" / "brusseline-bold-webfont.woff2"
try:
    _BRUSSELINE_B64: str | None = base64.b64encode(_FONT_PATH.read_bytes()).decode()
except Exception:
    _BRUSSELINE_B64 = None

from app.orm_models.board import Board, Led, LedStrip
from app.orm_models.gtfs import Line, Stop, Trip, TripStop

# ── Hardware / layout constants ───────────────────────────────────────────────
LED_PITCH_MM = 1000.0 / 60.0   # ~16.667 mm — 60-LED/m strip pitch (hardware constant)
STRIP_H_MM   = 50.0             # mm between consecutive rail centres (PCB property)
MARGIN_MM    = 15.0             # canvas margin for cut marks and frame overlap

# Circle diameter 6.91 mm (as measured on hardware).
R        = 3.455  # LED circle radius mm  (6.91 / 2)
R_OUTER  = 5.5    # central LED outer-ring radius mm  (R × 16/10 web ratio)
R_SW     = 0.8    # station circle stroke-width mm
RAIL_W   = 1.8    # rail line stroke-width mm (STIB)
RAIL_W_T = 1.2    # rail line stroke-width mm (TEC)

# Terminus indicators: [RouteNum square][TerminusName rect]  (no gap, only outer edges rounded)
TB_H     = 10.0   # mm — height of both boxes
ROUTE_SZ = 10.0   # mm — route-number square (width = height)
TB_RX    =  1.5   # mm — outer corner radius
# Width of the name box is auto-computed from text length (see _est_name_w).
# Char width estimate for Brusseline Bold at 5 mm: ~2.8 mm/char
_CHAR_W  =  2.8   # mm per character (empirical for Brusseline Bold)
_NAME_PAD=  4.0   # mm — total horizontal padding inside name box
TB_TOP   = 13.0   # mm from strip top edge to top of terminus boxes
            #       (= strip_top + 3 mm base + 10 mm "lower" shift)

_DEFAULTS = dict(
    max_width_mm=302.0, max_height_mm=212.0,
    delta_x_mm=16.0,   delta_y_mm=12.0,
    frame_inner_x_mm=287.0, frame_inner_y_mm=197.0,
    frame_outer_x_mm=317.0, frame_outer_y_mm=227.0,
    frame_overlap_x_mm=7.5, frame_overlap_y_mm=7.5,
)


# ── Smart title-case for ALL-CAPS DB stop / terminus names ───────────────────
# Words that stay lowercase in the middle of a name (French + Dutch function words).
_SMART_LOWER: frozenset[str] = frozenset({
    # French articles
    "le", "la", "les", "un", "une",
    # French prepositions
    "de", "du", "des", "à", "au", "aux", "en", "par", "pour",
    "sur", "sous", "dans", "avec", "vers", "entre", "chez",
    # French conjunctions / misc
    "et", "ou", "mais", "ni", "car", "que", "qui", "dont", "où",
    # Dutch articles
    "het", "een",
    # Dutch prepositions
    "van", "voor", "op", "in", "aan", "bij", "met", "te", "naar",
    "tot", "over", "onder", "om", "per",
    # Dutch conjunctions
    "of", "maar",
    # Genitive / archaic forms
    "den", "der", "ter",
    # Shared FR/NL
    "en",
})


def _tec_stop_name(raw: str) -> str:
    """
    Strip the city-name prefix from a TEC stop name, then apply smart title case.

    TEC GTFS names have the municipality as a leading prefix, e.g.
      • mixed-case DB: "NAMUR Place de l'Armée"   → "Place de l'Armée"
      • all-caps DB:   "NAMUR PLACE DE L ARMEE"    → "Place de l Armee"

    Detection: if the raw string has any lowercase letter (accented included),
    strip leading ALL-CAPS words; otherwise assume all-caps DB and strip only
    the first word.
    """
    words = raw.split()
    if len(words) <= 1:
        return _smart_title(raw)

    if raw != raw.upper():                    # mixed-case DB
        i = 0
        while i < len(words) - 1:
            w = words[i].replace("-", "").replace("'", "")
            if w and w == w.upper():
                i += 1
            else:
                break
        return _smart_title(" ".join(words[i:])) if i > 0 else _smart_title(raw)
    else:                                     # all-caps DB — strip first word
        return _smart_title(" ".join(words[1:]))


def _smart_title(s: str) -> str:
    """
    Convert an ALL-CAPS DB stop/terminus name to smart title case.

    - First word always capitalised.
    - After a hyphen always capitalised (compound proper names).
    - Apostrophe prefix (l', d') lowercased; suffix always capitalised.
    - Known FR/NL articles/prepositions/conjunctions → lowercase in mid-name.
    - Everything else → capitalised (assumed proper noun/place).
    """
    if not s:
        return s
    result: list[str] = []
    for i, word in enumerate(s.split()):
        if "-" in word:
            result.append("-".join(seg.lower().capitalize() for seg in word.split("-")))
        elif "'" in word:
            idx    = word.index("'")
            prefix = word[:idx].lower()
            suffix = word[idx + 1:].lower().capitalize()
            p      = prefix.capitalize() if i == 0 else prefix
            result.append(p + "'" + suffix)
        else:
            low = word.lower()
            result.append(low if (i > 0 and low in _SMART_LOWER) else low.capitalize())
    return " ".join(result)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _p(n: float) -> str:
    return f"{n:.3f}"


def _c(s: str | None, fallback: str = "#000000") -> str:
    if not s:
        return fallback
    return s if s.startswith("#") else f"#{s}"


def _dims(bt) -> dict:
    return {k: (getattr(bt, k) or _DEFAULTS[k]) for k in _DEFAULTS}


# ── DB query ──────────────────────────────────────────────────────────────────
def load_board_for_export(board_id: int, db: Session) -> Board | None:
    return (
        db.query(Board)
        .options(
            joinedload(Board.board_type),
            joinedload(Board.led_strips)
                .joinedload(LedStrip.line)
                .joinedload(Line.best_trip_b)
                .joinedload(Trip.terminus),
            joinedload(Board.led_strips)
                .joinedload(LedStrip.line)
                .joinedload(Line.best_trip_f)
                .joinedload(Trip.terminus),
            joinedload(Board.led_strips)
                .joinedload(LedStrip.leds)
                .joinedload(Led.trip_stops)
                .joinedload(TripStop.stop),
        )
        .filter_by(id=board_id)
        .first()
    )


# ── Terminus name resolution ──────────────────────────────────────────────────
def _resolve_terminus(trip, db: Session) -> str:
    if not trip:
        return ""
    if trip.terminus and trip.terminus.name:
        return trip.terminus.name
    if trip.terminus_stop_id and trip.terminus_agency_name:
        stop = db.query(Stop).filter_by(
            stop_id=trip.terminus_stop_id,
            agency_name=trip.terminus_agency_name,
        ).first()
        return stop.name if stop else ""
    return ""


def _strip_terminus(leds: list, line, side: str) -> str:
    has_cl = any(l.type == "c_left"  for l in leds)
    has_cr = any(l.type == "c_right" for l in leds)
    if not line:
        return ""
    t0 = getattr(line, "_t0", "") or ""
    t1 = getattr(line, "_t1", "") or ""
    if has_cl and not has_cr:
        return t1 if side == "left" else t0
    if has_cr and not has_cl:
        return t0 if side == "left" else t1
    return t0 if side == "right" else t1


# ── Arrow helpers (same position logic as the web visualisation) ──────────────
def _need_arrow(i: int, max_led: int, has_cl: bool, has_cr: bool) -> bool:
    if has_cl and has_cr:
        la = max_led // 2 - 3
        ra = la + 4
        return i in (la, ra) or (max_led >= 16 and i in (1, max_led - 2))
    if has_cl or has_cr:
        b = max_led // 2 - 4
        return i in (b, b + 3, b + 6) or (max_led >= 16 and i in (1, max_led - 3))
    return False


def _arrow_dir(i: int, leds: list) -> str:
    icl = next((j for j, l in enumerate(leds) if l.type == "c_left"),  -1)
    icr = next((j for j, l in enumerate(leds) if l.type == "c_right"), -1)
    if icl != -1 and icr != -1:
        return "right" if i <= icl else "left"
    return "left" if icr != -1 else "right"


# ── SVG path helpers for one-sided rounded rects ─────────────────────────────
def _path_round_left(x: float, y: float, w: float, h: float, r: float) -> str:
    """Rect with rounded corners on the LEFT side only."""
    return (
        f"M {_p(x+r)},{_p(y)} H {_p(x+w)} V {_p(y+h)} H {_p(x+r)} "
        f"A {_p(r)},{_p(r)} 0 0 1 {_p(x)},{_p(y+h-r)} "
        f"V {_p(y+r)} A {_p(r)},{_p(r)} 0 0 1 {_p(x+r)},{_p(y)} Z"
    )

def _path_round_right(x: float, y: float, w: float, h: float, r: float) -> str:
    """Rect with rounded corners on the RIGHT side only."""
    return (
        f"M {_p(x)},{_p(y)} H {_p(x+w-r)} "
        f"A {_p(r)},{_p(r)} 0 0 1 {_p(x+w)},{_p(y+r)} "
        f"V {_p(y+h-r)} A {_p(r)},{_p(r)} 0 0 1 {_p(x+w-r)},{_p(y+h)} "
        f"H {_p(x)} V {_p(y)} Z"
    )


def _est_name_w(text: str) -> float:
    """Estimate name-box width (mm) for a given terminus string."""
    return max(15.0, len(text) * _CHAR_W + _NAME_PAD)


# ── Terminus indicator (at top of strip area) ─────────────────────────────────
def _terminus_box(
    left_led_x: float, right_led_x: float, rail_y: float,
    terminus: str, route: str,
    tb_fill: str, lc: str, tc: str, side: str,
    name_w: float,
) -> str:
    """
    STIB-style terminus indicator: [RouteNum square][TerminusName rect].

    Route number is always on the LEFT, terminus name always on the RIGHT.
    Left  terminus: anchored to left_led_x,  extends right.
    Right terminus: anchored to right_led_x, extends left — same visual order.

    name_w is pre-computed (uniform across all strips on the board).
    Only the outermost corners are rounded (TB_RX), inner join is straight.
    """
    strip_top = rail_y - STRIP_H_MM
    box_top   = strip_top + TB_TOP
    mid_y     = box_top + TB_H / 2

    if side == "left":
        rx = left_led_x               # route square: starts at leftmost LED
        nx = rx + ROUTE_SZ            # name rect: immediately to the right
    else:
        # Route on LEFT, name on RIGHT — block ends at rightmost LED
        nx = right_led_x - name_w    # name rect right edge = right_led_x
        rx = nx - ROUTE_SZ            # route square to the left of name rect

    parts: list[str] = []

    # Route square — rounded LEFT corners only
    parts.append(
        f'<path d="{_path_round_left(rx, box_top, ROUTE_SZ, TB_H, TB_RX)}" fill="{lc}"/>'
    )
    # Name rect — rounded RIGHT corners only
    parts.append(
        f'<path d="{_path_round_right(nx, box_top, name_w, TB_H, TB_RX)}" fill="{tb_fill}"/>'
    )
    # Route number text (centred in square)
    if route:
        parts.append(
            f'<text x="{_p(rx + ROUTE_SZ/2)}" y="{_p(mid_y)}" '
            f'text-anchor="middle" dominant-baseline="middle" '
            f'font-family="Inter,Arial,sans-serif" font-size="{_p(min(ROUTE_SZ*0.65, 6.5))}" '
            f'font-weight="700" fill="{tc}">{_esc(route[:5])}</text>'
        )
    # Terminus name text — left-aligned inside name rect
    if terminus:
        parts.append(
            f'<text x="{_p(nx + 2)}" y="{_p(mid_y)}" '
            f'dominant-baseline="middle" '
            f'font-family="Brusseline,Arial Narrow,Arial,sans-serif" '
            f'font-size="{_p(TB_H * 0.52)}" font-weight="700" fill="white">'
            f'{_esc(terminus)}</text>'
        )

    return "\n".join(parts)


# ── Per-strip SVG elements (in global canvas mm) ──────────────────────────────
def _build_strip(
    strip: LedStrip, rail_y: float, bgx: float, dims: dict,
    max_led: int, db: Session, name_w: float,
) -> str:
    leds = sorted(strip.leds, key=lambda l: (l.ledstrip_index or 0))
    if not leds:
        return ""

    is_stib = (strip.line_agency_name or "").lower() != "tec"
    line    = strip.line

    lc       = _c(line.color if line else None, "#d84b3a") if is_stib else "#FFD34E"
    tc       = _c(line.text_color if line else None, "#ffffff") if is_stib else "#1a1a1a"
    s_stroke = "#1f3c88"                      # same blue for both STIB and TEC
    tb_fill  = "#1f3c88" if is_stib else lc
    l_color  = "#1f3c88" if is_stib else "#555555"
    lw       = str(RAIL_W) if is_stib else str(RAIL_W_T)

    has_cl = any(l.type == "c_left"  for l in leds)
    has_cr = any(l.type == "c_right" for l in leds)

    first_led_x = bgx + dims["delta_x_mm"]

    def led_x(idx1: int) -> float:          # ledstrip_index is 1-based
        return first_led_x + (idx1 - 1) * LED_PITCH_MM

    AH   = 3.0   # arrow half-height mm
    AW   = 3.5   # arrow half-width mm (tip-to-tail distance = AW, centred at mid)
    HALF = AW / 2  # distance from mid to tip / to tail

    parts: list[str] = []

    # ── Rail segments: drawn first, circles cover the ends — no gap needed ────
    for i in range(len(leds) - 1):
        x1 = led_x(leds[i].ledstrip_index     or (i + 1))
        x2 = led_x(leds[i + 1].ledstrip_index or (i + 2))

        if _need_arrow(i, max_led, has_cl, has_cr):
            mid  = (x1 + x2) / 2
            d    = _arrow_dir(i, leds)
            # Centre the chevron at mid: tip at mid±HALF, tail at mid∓HALF.
            seg  = HALF + 1.5   # clear space from mid to where rail resumes

            parts.append(
                f'<line x1="{_p(x1 - 0.5)}" y1="{_p(rail_y)}" '
                f'x2="{_p(mid - seg)}" y2="{_p(rail_y)}" '
                f'stroke="{lc}" stroke-width="{lw}" stroke-linecap="round"/>'
            )
            if d == "right":
                parts.append(
                    f'<path d="M {_p(mid - HALF)} {_p(rail_y - AH)} '
                    f'L {_p(mid + HALF)} {_p(rail_y)} '
                    f'L {_p(mid - HALF)} {_p(rail_y + AH)}" '
                    f'fill="none" stroke="{lc}" stroke-width="1.2" '
                    f'stroke-linecap="round" stroke-linejoin="round"/>'
                )
            else:
                parts.append(
                    f'<path d="M {_p(mid + HALF)} {_p(rail_y - AH)} '
                    f'L {_p(mid - HALF)} {_p(rail_y)} '
                    f'L {_p(mid + HALF)} {_p(rail_y + AH)}" '
                    f'fill="none" stroke="{lc}" stroke-width="1.2" '
                    f'stroke-linecap="round" stroke-linejoin="round"/>'
                )
            parts.append(
                f'<line x1="{_p(mid + seg)}" y1="{_p(rail_y)}" '
                f'x2="{_p(x2 + 0.5)}" y2="{_p(rail_y)}" '
                f'stroke="{lc}" stroke-width="{lw}" stroke-linecap="round"/>'
            )
        else:
            # Extend 0.5 mm beyond each circle centre so the cap is hidden under it.
            parts.append(
                f'<line x1="{_p(x1 - 0.5)}" y1="{_p(rail_y)}" '
                f'x2="{_p(x2 + 0.5)}" y2="{_p(rail_y)}" '
                f'stroke="{lc}" stroke-width="{lw}" stroke-linecap="round"/>'
            )

    # ── LED circles (drawn after rails so circles cover line ends) ────────────
    for led in leds:
        x       = led_x(led.ledstrip_index or 1)
        central = led.type in ("c_left", "c_right")
        if central:
            parts.append(
                f'<circle cx="{_p(x)}" cy="{_p(rail_y)}" r="{_p(R_OUTER)}" '
                f'fill="white" stroke="#d84b3a" stroke-width="{_p(R_SW)}"/>'
            )
        parts.append(
            f'<circle cx="{_p(x)}" cy="{_p(rail_y)}" r="{_p(R)}" '
            f'fill="white" stroke="{s_stroke}" stroke-width="{_p(R_SW)}"/>'
        )

    # ── Station labels (rotated -60° above each circle) ───────────────────────
    label_y = rail_y - (R + 1.5)
    for led in leds:
        x       = led_x(led.ledstrip_index or 1)
        central = led.type in ("c_left", "c_right")
        raw = ""
        if led.trip_stops:
            ts  = led.trip_stops[0]
            raw = (ts.stop.name if ts.stop else None) or ""
        if not raw:
            raw = led.custom_name or ""
        cased  = _tec_stop_name(raw) if not is_stib else _smart_title(raw)
        name   = (cased[:17] + ".") if len(cased) > 17 else cased
        weight = "900" if central else "700"
        parts.append(
            f'<text x="{_p(x)}" y="{_p(label_y)}" '
            f'transform="rotate(-60,{_p(x)},{_p(label_y)})" '
            f'font-family="Arial Narrow,Arial,sans-serif" font-size="3.2" '
            f'font-weight="{weight}" text-transform="uppercase" fill="{l_color}">'
            f'{_esc(name)}</text>'
        )

    # ── Pre-stop minute badges ─────────────────────────────────────────────────
    for led in leds:
        if led.pre_travel_minutes:
            x  = led_x(led.ledstrip_index or 1)
            by = rail_y - R - 7
            parts.append(
                f'<rect x="{_p(x - 3.5)}" y="{_p(by - 3.5)}" width="7" height="4" '
                f'rx="2" fill="#FFA500" opacity="0.92"/>'
                f'<text x="{_p(x)}" y="{_p(by - 0.5)}" text-anchor="middle" '
                f'font-size="2.5" font-weight="bold" fill="white">'
                f"{led.pre_travel_minutes}'"
                f'</text>'
            )

    # ── Terminus boxes at top of strip area ───────────────────────────────────
    route_label = (line.short_name if line and line.short_name else "") or ""
    if not route_label and strip.line_id is not None:
        route_label = str(strip.line_id)

    left_t  = _strip_terminus(leds, line, "left")
    right_t = _strip_terminus(leds, line, "right")

    left_x  = led_x(leds[0].ledstrip_index  or 1)
    right_x = led_x(leds[-1].ledstrip_index or max_led)

    # Truncate terminus names: same 17-char limit as stop labels, period suffix
    left_t  = (left_t[:17]  + ".") if len(left_t)  > 17 else left_t
    right_t = (right_t[:17] + ".") if len(right_t) > 17 else right_t

    parts.append(_terminus_box(left_x, right_x, rail_y, left_t,  route_label, tb_fill, lc, tc, "left",  name_w))
    parts.append(_terminus_box(left_x, right_x, rail_y, right_t, route_label, tb_fill, lc, tc, "right", name_w))

    return "\n".join(parts)


# ── Cut marks ─────────────────────────────────────────────────────────────────
def _cut_marks(bgx: float, bgy: float, w: float, h: float) -> str:
    ln, off, sw = 5.0, 2.0, 0.3
    corners = [
        (bgx,     bgy,     -1, -1),
        (bgx + w, bgy,      1, -1),
        (bgx,     bgy + h, -1,  1),
        (bgx + w, bgy + h,  1,  1),
    ]
    lines = []
    for cx, cy, sx, sy in corners:
        lines.append(
            f'<line x1="{_p(cx + sx * off)}" y1="{_p(cy)}" '
            f'x2="{_p(cx + sx * (off + ln))}" y2="{_p(cy)}" '
            f'stroke="black" stroke-width="{sw}"/>'
        )
        lines.append(
            f'<line x1="{_p(cx)}" y1="{_p(cy + sy * off)}" '
            f'x2="{_p(cx)}" y2="{_p(cy + sy * (off + ln))}" '
            f'stroke="black" stroke-width="{sw}"/>'
        )
    return "\n".join(lines)


# ── Frame overlay ─────────────────────────────────────────────────────────────
def _frame(bgx: float, bgy: float, dims: dict) -> str:
    fox = dims["frame_overlap_x_mm"]
    foy = dims["frame_overlap_y_mm"]
    foL = bgx - fox;  foT = bgy - foy
    foR = foL + dims["frame_outer_x_mm"]
    foB = foT + dims["frame_outer_y_mm"]
    fiL = bgx + fox;  fiT = bgy + foy
    fiR = fiL + dims["frame_inner_x_mm"]
    fiB = fiT + dims["frame_inner_y_mm"]
    return (
        f'<path fill="black" fill-rule="evenodd" '
        f'd="M {_p(foL)} {_p(foT)} H {_p(foR)} V {_p(foB)} H {_p(foL)} Z '
        f'M {_p(fiL)} {_p(fiT)} H {_p(fiR)} V {_p(fiB)} H {_p(fiL)} Z"/>'
    )


# ── Public entry point ────────────────────────────────────────────────────────
def build_export_svg(board: Board, with_frame: bool, db: Session) -> str:
    bt = board.board_type
    if not bt:
        raise ValueError("Board has no board type")

    dims       = _dims(bt)
    max_led    = bt.max_led or 12
    max_strips = bt.max_ledstrip or len(board.led_strips)

    canvas_w = dims["max_width_mm"]  + 2 * MARGIN_MM
    canvas_h = dims["max_height_mm"] + 2 * MARGIN_MM
    bgx = bgy = MARGIN_MM

    bottom_rail_y = bgy + dims["max_height_mm"] - dims["delta_y_mm"]

    # Pre-resolve terminus names with TEC city-prefix stripping
    for strip in board.led_strips:
        line = strip.line
        if line:
            is_tec = (strip.line_agency_name or "").lower() == "tec"
            _process = _tec_stop_name if is_tec else _smart_title
            line._t0 = _process(_resolve_terminus(line.best_trip_b, db))
            line._t1 = _process(_resolve_terminus(line.best_trip_f, db))

    # Fixed terminus name-box width — sized for exactly 17 chars (matches stop label limit).
    # Clamped to half the available strip width so left/right boxes never overlap.
    _est_strip_w  = (max_led - 1) * LED_PITCH_MM
    _half_avail   = max(10.0, (_est_strip_w - 2 * ROUTE_SZ) / 2)
    _name_w       = min(17 * _CHAR_W + _NAME_PAD, _half_avail)

    strips_by_slot: dict[int, LedStrip] = {}
    for s in board.led_strips:
        strips_by_slot[s.order_index or 1] = s

    font_defs = ""
    if _BRUSSELINE_B64:
        font_defs = (
            f'<defs><style>'
            f'@font-face{{font-family:"Brusseline";font-weight:700;'
            f'src:url("data:font/woff2;base64,{_BRUSSELINE_B64}") format("woff2");}}'
            f'</style></defs>'
        )

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{canvas_w}mm" height="{canvas_h}mm" '
        f'viewBox="0 0 {canvas_w} {canvas_h}">',
        font_defs,
        f'<rect width="{_p(canvas_w)}" height="{_p(canvas_h)}" fill="white"/>',
        f'<rect x="{_p(bgx)}" y="{_p(bgy)}" '
        f'width="{_p(dims["max_width_mm"])}" height="{_p(dims["max_height_mm"])}" '
        f'fill="white"/>',
    ]

    for slot in range(1, max_strips + 1):
        rail_y = bottom_rail_y - (max_strips - slot) * STRIP_H_MM
        strip  = strips_by_slot.get(slot)
        if strip and strip.leds:
            out.append(_build_strip(strip, rail_y, bgx, dims, max_led, db, _name_w))

    out.append(_cut_marks(bgx, bgy, dims["max_width_mm"], dims["max_height_mm"]))

    if with_frame:
        out.append(_frame(bgx, bgy, dims))

    out.append("</svg>")
    return "\n".join(out)
