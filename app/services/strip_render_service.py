"""Live render of one LED strip, as SVG (app pages) or PNG (Android widgets).

The drawing itself is `board_svg_service.build_strip_svg` — the same code as
the physical board export — so a line looks identical everywhere. This module
only adds access control, the live LED state and rasterisation.
"""
import hashlib
from collections import OrderedDict
from threading import Lock

from sqlalchemy.orm import Session

from app.domain.exceptions import NotFoundError, ValidationError
from app.orm_models.auth import User
from app.orm_models.board import Board
from app.services.boardService import BoardService
from app.services.board_svg_service import build_strip_svg, load_board_for_export

PNG_MIN_WIDTH = 200
PNG_MAX_WIDTH = 1600
_PNG_CACHE_SIZE = 256


class _LruCache:
    """Small thread-safe LRU for rendered PNGs. The key is a hash of the SVG
    itself, so any change (LED state, names, colours) is a new entry and no
    invalidation is needed."""

    def __init__(self, size: int):
        self._size = size
        self._data: OrderedDict[str, bytes] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> bytes | None:
        with self._lock:
            value = self._data.get(key)
            if value is not None:
                self._data.move_to_end(key)
            return value

    def put(self, key: str, value: bytes) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._size:
                self._data.popitem(last=False)


_png_cache = _LruCache(_PNG_CACHE_SIZE)


class StripRenderService:

    def __init__(self, db: Session, board_service: BoardService):
        self.db = db
        self.board_service = board_service

    def _load_owned_board(self, board_id: int, current_user: User) -> Board:
        board = load_board_for_export(board_id, self.db)
        is_admin = any(r.name == "admin" for r in current_user.roles)
        # 404, not 403, for someone else's board: don't reveal it exists.
        if not board or (not is_admin and board.owner_id != current_user.id):
            raise NotFoundError("Board", board_id)
        return board

    def _lit_leds(self, board: Board, strip_id: int, current_user: User) -> dict[int, str]:
        """led id → colour for the strip's LEDs currently on, using the exact
        on/off rules of GET /boards/{id}/status (realtime, rt_only, …)."""
        status = self.board_service.get_board_status(board.id, current_user)
        strip_status = next((s for s in status["ledStrips"] if s["id"] == strip_id), None)
        if not strip_status:
            return {}
        on_ids = {l["ledId"] for l in strip_status["leds"] if l["isOn"]}
        strip = next(s for s in board.led_strips if s.id == strip_id)
        fallback = strip.line_color or (strip.line.color if strip.line else None) or "#FFD34E"
        colours: dict[int, str] = {}
        for led in strip.leds:
            if led.id in on_ids:
                colour = led.led_color or fallback
                colours[led.id] = colour if colour.startswith("#") else f"#{colour}"
        return colours

    def _render(self, board_id: int, strip_id: int, live: bool, current_user: User) -> tuple[str, int]:
        """(svg, number of LEDs on)."""
        board = self._load_owned_board(board_id, current_user)
        if not any(s.id == strip_id for s in board.led_strips):
            raise NotFoundError("Strip", strip_id)
        lit = self._lit_leds(board, strip_id, current_user) if live else None
        try:
            return build_strip_svg(board, strip_id, lit, self.db), len(lit or {})
        except ValueError as e:
            raise ValidationError(str(e))

    def render_svg(self, board_id: int, strip_id: int, live: bool, current_user: User) -> tuple[str, int]:
        """(svg, number of LEDs on)."""
        return self._render(board_id, strip_id, live, current_user)

    def render_png(self, board_id: int, strip_id: int, live: bool, width: int, current_user: User) -> tuple[bytes, int]:
        """(png, number of LEDs on)."""
        if not PNG_MIN_WIDTH <= width <= PNG_MAX_WIDTH:
            raise ValidationError(f"width must be between {PNG_MIN_WIDTH} and {PNG_MAX_WIDTH}")
        svg, leds_on = self._render(board_id, strip_id, live, current_user)
        key = hashlib.sha256(f"{width}:{svg}".encode()).hexdigest()
        cached = _png_cache.get(key)
        if cached is None:
            # Imported lazily: needs the system cairo library (see Dockerfile).
            import cairosvg
            cached = cairosvg.svg2png(bytestring=svg.encode(), output_width=width)
            _png_cache.put(key, cached)
        return cached, leds_on
