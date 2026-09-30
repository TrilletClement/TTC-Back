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
# Lives inside the API package so it ships in the Docker image (the repo-root
# doc/ folder is outside the build context). The .ttf twin, family renamed
# "Brusseline"/Bold, is installed system-wide by the Dockerfile for the PNG
# rasterizer, which ignores @font-face.
_FONT_PATH = Path(__file__).parent.parent / "assets" / "fonts" / "brusseline-bold.woff2"
try:
    _BRUSSELINE_B64: str | None = base64.b64encode(_FONT_PATH.read_bytes()).decode()
except Exception:
    _BRUSSELINE_B64 = None

from app.orm_models.board import Board, Led, LedStrip
from app.orm_models.gtfs import Line, TripStop

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

# Terminus indicators: [RouteNum square] [gap] [TerminusName rect]
TB_H     = 10.0   # mm — height of both boxes
ROUTE_SZ = 10.0   # mm — route-number square (width = height)
TB_GAP   =  1.5   # mm — white gap between route square and name rect
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




# ── Helpers ───────────────────────────────────────────────────────────────────
def _p(n: float) -> str:
    return f"{n:.3f}"


def _c(s: str | None, fallback: str = "#000000") -> str:
    if not s:
        return fallback
    return s if s.startswith("#") else f"#{s}"


def _relative_luminance(r: int, g: int, b: int) -> float:
    def _linear(c: float) -> float:
        cs = c / 255
        return cs / 12.92 if cs <= 0.03928 else ((cs + 0.055) / 1.055) ** 2.4
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def _is_light_color(hex_color: str) -> bool:
    """True only for a genuinely white/near-white line color (e.g. De Lijn
    425 is literally #ffffff in GTFS) — deliberately tight so a merely vivid
    color like TEC's #ffcd00 (contrast-with-white ~= 1.52, well outside this
    cutoff) never gets the black-outline/dark-text treatment meant for
    colors that actually vanish against the board's white background."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return False
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return False
    luminance = _relative_luminance(r, g, b)
    contrast_with_white = 1.05 / (luminance + 0.05)
    return contrast_with_white < 1.2


def _dims(bt) -> dict:
    return {k: (getattr(bt, k) or _DEFAULTS[k]) for k in _DEFAULTS}


# ── DB query ──────────────────────────────────────────────────────────────────
def load_board_for_export(board_id: int, db: Session) -> Board | None:
    return (
        db.query(Board)
        .options(
            joinedload(Board.board_type),
            joinedload(Board.led_strips).joinedload(LedStrip.line),
            joinedload(Board.led_strips)
                .joinedload(LedStrip.leds)
                .joinedload(Led.trip_stops)
                .joinedload(TripStop.stop),
        )
        .filter_by(id=board_id)
        .first()
    )


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


def _shorten(text: str) -> str:
    """Keep the first 17 chars + '...' if text is longer than 19 chars; else unchanged."""
    return (text[:17] + "...") if len(text) > 19 else text


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
        nx = rx + ROUTE_SZ + TB_GAP  # name rect: gap after route square
    else:
        # Route on LEFT, name on RIGHT — block ends at rightmost LED
        nx = right_led_x - name_w    # name rect right edge = right_led_x
        rx = nx - ROUTE_SZ - TB_GAP  # route square: gap before name rect

    parts: list[str] = []

    # A white/near-white line color makes the square vanish against the
    # board's own white background, and a light default text color would
    # then also be invisible on it — outline the square in black and force
    # dark text instead of relying on a grey backing plate (too little
    # contrast against both the board and light line colors).
    is_light  = _is_light_color(lc)
    route_stroke = ' stroke="#000000" stroke-width="0.5"' if is_light else ""
    route_tc  = "#1a1a1a" if is_light else tc

    # Route square — all corners rounded (standalone element with gap)
    parts.append(
        f'<rect x="{_p(rx)}" y="{_p(box_top)}" width="{_p(ROUTE_SZ)}" height="{_p(TB_H)}" '
        f'rx="{_p(TB_RX)}" fill="{lc}"{route_stroke}/>'
    )
    # Name rect — all corners rounded (standalone element with gap)
    parts.append(
        f'<rect x="{_p(nx)}" y="{_p(box_top)}" width="{_p(name_w)}" height="{_p(TB_H)}" rx="{_p(TB_RX)}" fill="{tb_fill}"/>'
    )
    # Route number text (centred in square)
    if route:
        parts.append(
            f'<text x="{_p(rx + ROUTE_SZ/2)}" y="{_p(mid_y)}" '
            f'text-anchor="middle" dominant-baseline="central" '
            f'font-family="Brusseline,Arial Narrow,Arial,sans-serif" font-size="{_p(min(ROUTE_SZ*0.65, 6.5))}" '
            f'font-weight="700" fill="{route_tc}">{_esc(route[:5])}</text>'
        )
    # Terminus name text — left-aligned inside name rect
    if terminus:
        parts.append(
            f'<text x="{_p(nx + 2)}" y="{_p(mid_y)}" '
            f'dominant-baseline="central" '
            f'font-family="Brusseline,Arial Narrow,Arial,sans-serif" '
            f'font-size="{_p(TB_H * 0.52)}" font-weight="700" fill="white">'
            f'{_esc(terminus)}</text>'
        )

    return "\n".join(parts)


# ── Per-strip SVG elements (in global canvas mm) ──────────────────────────────
def _build_strip(
    strip: LedStrip, rail_y: float, bgx: float, dims: dict,
    max_led: int, db: Session, name_w: float,
    lit: dict[int, str] | None = None,
) -> str:
    """`lit` (led id → colour) draws those LEDs switched on, for the live
    renders; None (the physical export) keeps every station white."""
    leds = sorted(strip.leds, key=lambda l: (l.ledstrip_index or 0))
    if not leds:
        return ""

    is_tec   = (strip.line_agency_name or "").lower() == "tec"
    line     = strip.line

    # Same resolution as everywhere else in the app (BoardService._resolve_line_color,
    # led-visualization.ts pickLineColor): per-strip override wins, then the line's
    # official GTFS color, then an agency-appropriate default — never force TEC to
    # yellow when the strip has its own configured color.
    default_lc = "#FFD34E" if is_tec else "#d84b3a"
    lc       = _c(strip.line_color or (line.color if line else None), default_lc)
    tc       = _c(line.text_color if line else None, "#ffffff")
    s_stroke = "#1f3c88"
    tb_fill  = "#1f3c88"
    lw       = str(RAIL_W_T if is_tec else RAIL_W)

    has_cl = any(l.type == "c_left"  for l in leds)
    has_cr = any(l.type == "c_right" for l in leds)

    first_led_x = bgx + dims["delta_x_mm"]

    def led_x(idx1: int) -> float:          # ledstrip_index is 1-based
        return first_led_x + (idx1 - 1) * LED_PITCH_MM

    AH   = 3.0   # arrow half-height mm
    AW   = 3.5   # arrow half-width mm (tip-to-tail distance = AW, centred at mid)
    HALF = AW / 2  # distance from mid to tip / to tail

    parts: list[str] = []

    # A light line color makes the rail itself vanish against the board's own
    # white background — not just the route-number square. Back every
    # rail/arrow stroke with a wider black copy first (drawn behind, same
    # shape) instead of a filter, since this SVG is consumed by physical
    # fabrication tooling that may not render SVG filters at all. Uses the
    # same threshold as the badge text (_is_light_color) — a thin line has
    # even less visual weight than bold digits, so it needs contrast help at
    # least as readily, not less.
    rail_light = _is_light_color(lc)

    def _railed(svg_fragment: str, width_str: str) -> str:
        """Prepend a wider black copy of `svg_fragment` behind it — `width_str`
        must match the literal `stroke-width="..."` value already baked into
        the fragment, so it can be swapped for a thicker one."""
        if not rail_light:
            return svg_fragment
        w = float(width_str) + 1.0
        backing = (
            svg_fragment
            .replace(f'stroke="{lc}"', 'stroke="#000000"')
            .replace(f'stroke-width="{width_str}"', f'stroke-width="{_p(w)}"')
        )
        return backing + "\n" + svg_fragment

    # ── Rail segments: drawn first, circles cover the ends — no gap needed ────
    for i in range(len(leds) - 1):
        if not leds[i].trip_stops or not leds[i + 1].trip_stops:
            continue
        x1 = led_x(leds[i].ledstrip_index     or (i + 1))
        x2 = led_x(leds[i + 1].ledstrip_index or (i + 2))

        if _need_arrow(i, max_led, has_cl, has_cr):
            mid  = (x1 + x2) / 2
            d    = _arrow_dir(i, leds)
            # Centre the chevron at mid: tip at mid±HALF, tail at mid∓HALF.
            seg  = HALF + 1.5   # clear space from mid to where rail resumes

            parts.append(_railed(
                f'<line x1="{_p(x1 - 0.5)}" y1="{_p(rail_y)}" '
                f'x2="{_p(mid - seg)}" y2="{_p(rail_y)}" '
                f'stroke="{lc}" stroke-width="{lw}" stroke-linecap="round"/>',
                lw,
            ))
            if d == "right":
                parts.append(_railed(
                    f'<path d="M {_p(mid - HALF - 0.5)} {_p(rail_y - AH)} '
                    f'L {_p(mid + HALF - 0.5)} {_p(rail_y)} '
                    f'L {_p(mid - HALF - 0.5)} {_p(rail_y + AH)}" '
                    f'fill="none" stroke="{lc}" stroke-width="1.2" '
                    f'stroke-linecap="round" stroke-linejoin="round"/>',
                    "1.2",
                ))
            else:
                parts.append(_railed(
                    f'<path d="M {_p(mid + HALF + 0.5)} {_p(rail_y - AH)} '
                    f'L {_p(mid - HALF + 0.5)} {_p(rail_y)} '
                    f'L {_p(mid + HALF + 0.5)} {_p(rail_y + AH)}" '
                    f'fill="none" stroke="{lc}" stroke-width="1.2" '
                    f'stroke-linecap="round" stroke-linejoin="round"/>',
                    "1.2",
                ))
            parts.append(_railed(
                f'<line x1="{_p(mid + seg)}" y1="{_p(rail_y)}" '
                f'x2="{_p(x2 + 0.5)}" y2="{_p(rail_y)}" '
                f'stroke="{lc}" stroke-width="{lw}" stroke-linecap="round"/>',
                lw,
            ))
        else:
            # Extend 0.5 mm beyond each circle centre so the cap is hidden under it.
            parts.append(_railed(
                f'<line x1="{_p(x1 - 0.5)}" y1="{_p(rail_y)}" '
                f'x2="{_p(x2 + 0.5)}" y2="{_p(rail_y)}" '
                f'stroke="{lc}" stroke-width="{lw}" stroke-linecap="round"/>',
                lw,
            ))

    # ── LED circles (drawn after rails so circles cover line ends) ────────────
    for led in leds:
        if not led.trip_stops:
            continue
        x       = led_x(led.ledstrip_index or 1)
        central = led.type in ("c_left", "c_right")
        led_on  = lit.get(led.id) if lit else None
        if led_on:
            # Halo of the lit LED, behind the station ring(s).
            parts.append(
                f'<circle cx="{_p(x)}" cy="{_p(rail_y)}" r="{_p(R_OUTER + 1.5)}" '
                f'fill="{led_on}" fill-opacity="0.35"/>'
            )
        if central:
            parts.append(
                f'<circle cx="{_p(x)}" cy="{_p(rail_y)}" r="{_p(R_OUTER)}" '
                f'fill="white" stroke="#d84b3a" stroke-width="{_p(R_SW)}"/>'
            )
        parts.append(
            f'<circle cx="{_p(x)}" cy="{_p(rail_y)}" r="{_p(R)}" '
            f'fill="{led_on or "white"}" stroke="{led_on or s_stroke}" stroke-width="{_p(R_SW)}"/>'
        )

    # ── Terminus data (needed for both top boxes and integrated badges) ──────────
    route_label = (line.short_name if line and line.short_name else "") or ""
    if not route_label and strip.line_id is not None:
        route_label = str(strip.line_id)

    integrated = bool(getattr(strip, "integrated_terminus", False))

    left_t  = _shorten(strip.custom_terminus_left_name  or "")
    right_t = _shorten(strip.custom_terminus_right_name or "")

    # ── Leftmost / rightmost occupied LEDs (have at least one trip stop) ──────
    # Badge anchor: normally the leftmost/rightmost occupied LED, except when
    # that LED is the central stop itself — then the badge moves one slot
    # further out, onto the deliberately-unoccupied LED reserved for it, so
    # the central stop's own label is never overwritten.
    occupied_idxs = [i for i, l in enumerate(leds) if l.trip_stops]
    leftmost_idx  = occupied_idxs[0]  if occupied_idxs else -1
    rightmost_idx = occupied_idxs[-1] if occupied_idxs else -1

    def _is_central_idx(i: int) -> bool:
        return i != -1 and leds[i].type in ("c_left", "c_right")

    left_badge_idx = (
        leftmost_idx - 1
        if _is_central_idx(leftmost_idx) and leftmost_idx > 0
        else leftmost_idx
    )
    right_badge_idx = (
        rightmost_idx + 1
        if _is_central_idx(rightmost_idx) and rightmost_idx < len(leds) - 1
        else rightmost_idx
    )

    leftmost_occ  = leds[left_badge_idx]  if left_badge_idx  != -1 else None
    rightmost_occ = leds[right_badge_idx] if right_badge_idx != -1 else None

    # ── Station labels (rotated -60° above each circle) ───────────────────────
    label_y = rail_y - (R + 1.5)
    # Constants for inline integrated terminus badge (mm)
    IB_H       = 6.0   # badge height
    IB_ROUTE_W = 6.0   # route square width = height
    IB_GAP     = 0.7   # gap between square and name rect
    IB_RX      = 1.0   # corner radius
    IB_FS      = IB_H * 0.52  # font size inside badge
    IB_LIFT    = 1.5   # mm — lift badge above normal label_y to clear LED circle

    for led in leds:
        x       = led_x(led.ledstrip_index or 1)
        central = led.type in ("c_left", "c_right")
        ly      = label_y - 3.0 if central else label_y

        is_left_end  = integrated and led is leftmost_occ
        is_right_end = integrated and led is rightmost_occ

        if is_left_end or is_right_end:
            # Render inline terminus badge rotated like the stop label
            term = left_t if is_left_end else right_t
            ly   = label_y - IB_LIFT          # lift badge clear of LED circle
            bx   = x                           # badge starts at label x anchor
            by   = ly - IB_H / 2              # vertically centred on label y
            # Name rect width fitted to text: ~1.6 mm/char + 2.5 mm padding
            ib_name_w = max(10.0, len(term) * 1.6 + 2.5)
            # A white/near-white route square vanishes against the board's
            # white background, and the default text color would then also
            # be invisible on it — outline the square in black and force
            # dark text instead of a grey backing plate (too little contrast).
            ib_light   = _is_light_color(lc)
            ib_stroke  = ' stroke="#000000" stroke-width="0.4"' if ib_light else ""
            ib_tc      = "#1a1a1a" if ib_light else tc
            parts.append(
                f'<g transform="rotate(-60,{_p(x)},{_p(ly)})">'
                f'<rect x="{_p(bx)}" y="{_p(by)}" width="{_p(IB_ROUTE_W)}" height="{_p(IB_H)}" '
                f'rx="{_p(IB_RX)}" fill="{lc}"{ib_stroke}/>'
                f'<text x="{_p(bx + IB_ROUTE_W / 2)}" y="{_p(ly)}" '
                f'text-anchor="middle" dominant-baseline="central" '
                f'font-family="Brusseline,Arial Narrow,Arial,sans-serif" font-size="{_p(IB_FS)}" '
                f'font-weight="900" fill="{ib_tc}">{_esc(route_label[:5])}</text>'
                f'<rect x="{_p(bx + IB_ROUTE_W + IB_GAP)}" y="{_p(by)}" width="{_p(ib_name_w)}" height="{_p(IB_H)}" rx="{_p(IB_RX)}" fill="{tb_fill}"/>'
                f'<text x="{_p(bx + IB_ROUTE_W + IB_GAP + 1.0)}" y="{_p(ly)}" '
                f'dominant-baseline="central" '
                f'font-family="Brusseline,Arial Narrow,Arial,sans-serif" font-size="{_p(IB_FS)}" '
                f'font-weight="700" fill="white">{_esc(term)}</text>'
                f'</g>'
            )
        else:
            raw  = led.custom_name or ""
            if not raw and led.trip_stops:
                ts  = led.trip_stops[0]
                raw = (ts.stop.name if ts.stop else None) or ""
            name = _shorten(raw)
            weight  = "900" if central else "700"
            tx      = x + 1.0
            subname = getattr(led, "custom_subname", None)
            if subname:
                parts.append(
                    f'<g transform="rotate(-60,{_p(tx)},{_p(ly)})">'
                    f'<text x="{_p(tx)}" y="{_p(ly)}" '
                    f'font-family="Brusseline,Arial Narrow,Arial,sans-serif" font-size="4.0" '
                    f'font-weight="{weight}" text-transform="uppercase" fill="{tb_fill}">'
                    f'{_esc(name)}</text>'
                    f'<text x="{_p(tx)}" y="{_p(ly + 3.2)}" '
                    f'font-family="Brusseline,Arial Narrow,Arial,sans-serif" font-size="2.4" '
                    f'font-weight="500" text-transform="uppercase" fill="{tb_fill}">'
                    f'{_esc(" " + subname)}</text>'
                    f'</g>'
                )
            else:
                parts.append(
                    f'<text x="{_p(tx)}" y="{_p(ly)}" '
                    f'transform="rotate(-60,{_p(tx)},{_p(ly)})" '
                    f'font-family="Brusseline,Arial Narrow,Arial,sans-serif" font-size="4.0" '
                    f'font-weight="{weight}" text-transform="uppercase" fill="{tb_fill}">'
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

    # ── Terminus boxes at top of strip area (skipped when integrated terminus) ─
    if not integrated:
        left_x  = led_x(leds[0].ledstrip_index  or 1)
        right_x = led_x(leds[-1].ledstrip_index or max_led)
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
# Board outline (rounded rect) traced directly on the board's own bounding
# box, plus 4 corner mounting holes — matches the reference layer supplied
# for the physical enclosure, no separate bezel/overlap geometry needed.
_FRAME_HOLE_INSET = 10.0  # mm from each edge to its mounting-hole centre
_FRAME_HOLE_R     = 3.8   # mm — mounting-hole radius
_FRAME_CORNER_RX  = 10.0  # mm — outline corner radius
_FRAME_STROKE     = 'fill="none" stroke="#000" stroke-width=".1"'


def _frame(bgx: float, bgy: float, dims: dict) -> str:
    w, h = dims["max_width_mm"], dims["max_height_mm"]
    parts = [
        f'<rect x="{_p(bgx)}" y="{_p(bgy)}" width="{_p(w)}" height="{_p(h)}" '
        f'rx="{_p(_FRAME_CORNER_RX)}" {_FRAME_STROKE}/>'
    ]
    for cx, cy in (
        (bgx + _FRAME_HOLE_INSET,     bgy + _FRAME_HOLE_INSET),
        (bgx + w - _FRAME_HOLE_INSET, bgy + _FRAME_HOLE_INSET),
        (bgx + _FRAME_HOLE_INSET,     bgy + h - _FRAME_HOLE_INSET),
        (bgx + w - _FRAME_HOLE_INSET, bgy + h - _FRAME_HOLE_INSET),
    ):
        parts.append(f'<circle cx="{_p(cx)}" cy="{_p(cy)}" r="{_p(_FRAME_HOLE_R)}" {_FRAME_STROKE}/>')
    return "\n".join(parts)


# ── Public entry point ────────────────────────────────────────────────────────
def _terminus_name_w(max_led: int) -> float:
    """Fixed terminus name-box width — sized for the longest possible shortened
    label (17 chars + "..." = 20 chars, see _shorten). Clamped to half the
    available strip width so left/right boxes never overlap."""
    est_strip_w = (max_led - 1) * LED_PITCH_MM
    half_avail  = max(10.0, (est_strip_w - 2 * (ROUTE_SZ + TB_GAP)) / 2)
    return min(20 * _CHAR_W + _NAME_PAD, half_avail)


def _font_defs() -> str:
    if not _BRUSSELINE_B64:
        return ""
    return (
        f'<defs><style>'
        f'@font-face{{font-family:"Brusseline";font-weight:700;'
        f'src:url("data:font/woff2;base64,{_BRUSSELINE_B64}") format("woff2");}}'
        f'</style></defs>'
    )


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
    _name_w = _terminus_name_w(max_led)

    strips_by_slot: dict[int, LedStrip] = {}
    for s in board.led_strips:
        strips_by_slot[s.order_index or 1] = s

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{canvas_w}mm" height="{canvas_h}mm" '
        f'viewBox="0 0 {canvas_w} {canvas_h}">',
        _font_defs(),
        f'<rect width="{_p(canvas_w)}" height="{_p(canvas_h)}" fill="white"/>',
        f'<rect x="{_p(bgx)}" y="{_p(bgy)}" '
        f'width="{_p(dims["max_width_mm"])}" height="{_p(dims["max_height_mm"])}" '
        f'fill="white"/>',
    ]

    for slot in range(1, max_strips + 1):
        # order_index=1 is the bottom-most physical strip (matches the ESP32's
        # own hardware numbering), ascending upward — see the 20260722_01
        # migration for the historical-data half of this fix.
        rail_y = bottom_rail_y - (slot - 1) * STRIP_H_MM
        strip  = strips_by_slot.get(slot)
        if strip and strip.leds:
            out.append(_build_strip(strip, rail_y, bgx, dims, max_led, db, _name_w))

    out.append(_cut_marks(bgx, bgy, dims["max_width_mm"], dims["max_height_mm"]))

    if with_frame:
        out.append(_frame(bgx, bgy, dims))

    out.append("</svg>")
    return "\n".join(out)


# ── Single-strip render (app, widget) ─────────────────────────────────────────
# Horizontal room kept right of the last LED: its label leans right (-60°).
_STRIP_RIGHT_OVERHANG_MM = 24.0
_STRIP_LEFT_PAD_MM       = 3.0
# The longest tilted labels reach the strip's own top edge.
_STRIP_TOP_PAD_MM        = 3.0


def build_strip_svg(board: Board, strip_id: int, lit: dict[int, str] | None, db: Session) -> str:
    """One strip of `board`, drawn by the very same `_build_strip` as the
    physical export (same geometry, font, colours, labels, arrows, terminus
    boxes), cropped to that strip. `lit` (led id → colour) lights LEDs up for
    live views. This is the single source of the line visual shown by the
    website, the Android app and its widgets.

    Raises LookupError if the strip isn't on the board, ValueError if the
    board has no board type (same as the export).
    """
    bt = board.board_type
    if not bt:
        raise ValueError("Board has no board type")
    strip = next((s for s in board.led_strips if s.id == strip_id), None)
    if strip is None:
        raise LookupError(f"Strip {strip_id} not on board {board.id}")

    dims    = _dims(bt)
    max_led = bt.max_led or 12
    rail_y  = STRIP_H_MM + _STRIP_TOP_PAD_MM

    last_idx = max([max_led] + [l.ledstrip_index or 0 for l in strip.leds])
    first_x  = dims["delta_x_mm"]
    last_x   = first_x + (last_idx - 1) * LED_PITCH_MM
    x0 = first_x - R_OUTER - _STRIP_LEFT_PAD_MM
    x1 = last_x + _STRIP_RIGHT_OVERHANG_MM
    y0 = 0.0
    y1 = rail_y + R_OUTER + 2.0
    w, h = x1 - x0, y1 - y0

    body = _build_strip(strip, rail_y, 0.0, dims, max_led, db, _terminus_name_w(max_led), lit=lit)
    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{_p(w)}mm" height="{_p(h)}mm" '
        f'viewBox="{_p(x0)} {_p(y0)} {_p(w)} {_p(h)}">',
        _font_defs(),
        f'<rect x="{_p(x0)}" y="{_p(y0)}" width="{_p(w)}" height="{_p(h)}" fill="white"/>',
        body,
        "</svg>",
    ])
