"""
Printable product labels for manufactured ESP32 devices — MAC address, BLE
provisioning QR code, and standard product/compliance information.

Composes labels using ble_prov_qr_service for the QR (this service owns
layout/legal text only, it does not derive any identity itself — see that
module for the actual BLE provisioning algorithm). Multiple devices are laid
out as a grid of labels across as many A4 pages as needed, to avoid printing
one near-empty sheet per device.
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg

from app.domain.exceptions import NotFoundError, ValidationError
from app.repositories.device_repo import DeviceRepository
from app.services.adminSettingsService import _parse_json
from app.services.ble_prov_qr_service import build_provisioning_qr

# Static placeholder content — owner-provided substitutes, not yet configurable.
# TODO: move to app.core.config.Settings once these stabilize.
LEGAL_NAME = "Clément Trillet"
LEGAL_ADDRESS = ["21 avenue Adolphe Buyl", "4000 Liège, Belgium"]
MADE_IN = "Made in Belgium"
EMAIL = "contact@trillet.be"
BRAND = "Transport Trillet Company"
POWER_SPEC = "0.5 A   5 V"

# Official compliance mark artwork, sourced by the owner (not hand-drawn).
STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
CE_MARK_SVG = STATIC_DIR / "Conformité_Européenne_(logo).svg"
WEEE_SYMBOL_SVG = STATIC_DIR / "WEEE_symbol_vectors.svg"

# One label's fixed size.
BOX_W_MM = 100
BOX_H_MM = 50

# Grid layout — 2 columns fit exactly in A4's 210mm width with these margins
# (4 + 100 + 2 + 100 + 4 = 210); rows are computed to fit as many as the page
# height allows, so a full page holds 2x5 = 10 labels.
GRID_COLS = 2
MARGIN_X_MM = 4
GAP_X_MM = 2
MARGIN_TOP_MM = 10
MARGIN_BOTTOM_MIN_MM = 5
GAP_Y_MM = 5


@dataclass
class _ResolvedDevice:
    mac_address: str
    hardware_type: str
    qr_png: bytes


class DeviceLabelService:
    def __init__(self, repo: DeviceRepository):
        self.repo = repo

    def generate_labels_pdf(self, device_ids: list[int]) -> bytes:
        """One combined PDF, multiple labels per page, for all given devices.
        Raises on the first device that can't be resolved — a partially-generated
        batch would be confusing (fewer labels than selected, no clear reason)."""
        if not device_ids:
            raise ValidationError("No devices selected.")
        resolved = [self._resolve_device(device_id) for device_id in device_ids]
        return _render_labels_grid(resolved)

    def _resolve_device(self, device_id: int) -> _ResolvedDevice:
        device = self.repo.get_by_id(device_id)
        if not device:
            raise NotFoundError("Device", device_id)
        if not device.hardware:
            raise NotFoundError("Hardware for device", device_id)

        settings = _parse_json(device.hardware.json_settings)
        prefix = settings.get("ble_prov_prefix")
        salt = settings.get("ble_prov_pop_salt")
        if not prefix or not salt:
            raise ValidationError(
                f"Hardware '{device.hardware.hardware_type}' is missing "
                "ble_prov_prefix/ble_prov_pop_salt — set them via the hardware "
                "settings panel before generating a label."
            )

        # service_name/pop aren't shown on the label (the QR alone is scanned) —
        # only the raw PNG is needed here.
        qr_png, _service_name, _pop = build_provisioning_qr(device.mac_address, prefix, salt)
        return _ResolvedDevice(device.mac_address, device.hardware.hardware_type, qr_png)


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

def _render_labels_grid(devices: list[_ResolvedDevice]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _page_w, page_h = A4

    box_w, box_h = BOX_W_MM * mm, BOX_H_MM * mm
    usable_h = page_h - (MARGIN_TOP_MM * mm) - (MARGIN_BOTTOM_MIN_MM * mm)
    rows_per_page = max(1, int((usable_h + GAP_Y_MM * mm) / (box_h + GAP_Y_MM * mm)))
    per_page = GRID_COLS * rows_per_page

    for i, device in enumerate(devices):
        pos_on_page = i % per_page
        if i > 0 and pos_on_page == 0:
            c.showPage()

        col = pos_on_page % GRID_COLS
        row = pos_on_page // GRID_COLS
        box_x = (MARGIN_X_MM * mm) + col * (box_w + GAP_X_MM * mm)
        box_y = page_h - (MARGIN_TOP_MM * mm) - box_h - row * (box_h + GAP_Y_MM * mm)

        _draw_one_label(c, box_x, box_y, device.mac_address, device.hardware_type, device.qr_png)

    c.showPage()
    c.save()
    return buf.getvalue()


def _draw_one_label(c: canvas.Canvas, box_x: float, box_y: float,
                     mac_address: str, hardware_type: str, qr_png: bytes) -> None:
    """Draws one 100x50mm label with its bottom-left corner at (box_x, box_y)
    (absolute PDF points)."""
    box_w, box_h = BOX_W_MM * mm, BOX_H_MM * mm

    def pt(lx_mm: float, ly_mm: float) -> tuple[float, float]:
        """Local mm coords (origin = box bottom-left) -> absolute page points."""
        return box_x + lx_mm * mm, box_y + ly_mm * mm

    # Cut guide.
    c.saveState()
    c.setDash(2, 2)
    c.setLineWidth(0.3)
    c.rect(box_x, box_y, box_w, box_h, stroke=1, fill=0)
    c.restoreState()

    # QR code, with an instructional caption above it (no raw service_name/pop
    # shown — the QR is the only thing anyone needs to scan).
    qr_x, qr_y = pt(4, 6)
    qr_size = 30 * mm
    c.drawImage(ImageReader(BytesIO(qr_png)), qr_x, qr_y, width=qr_size, height=qr_size,
                preserveAspectRatio=True, mask="auto")

    # Caption sits in the gap between the QR's top edge (local y=36) and the
    # box's top edge (local y=50) — first line's baseline 5mm below the top
    # edge so its ascenders clear the cut line, wrapping downward from there.
    caption_font, caption_size = "Helvetica", 5.5
    caption = "Scan with ESP BLE Provisioning app (Espressif) to configure the Wi-Fi"
    lines = _wrap_text(caption, caption_font, caption_size, qr_size + 4 * mm)
    c.setFont(caption_font, caption_size)
    line_h = caption_size * 1.15
    caption_top_y = pt(0, 45)[1]
    for i, line in enumerate(lines):
        c.drawCentredString(qr_x + qr_size / 2, caption_top_y - i * line_h, line)

    # Right column: brand, model, MAC, power, legal, origin/contact.
    col_x, _ = pt(40, 0)

    c.setFont("Helvetica-Bold", 8)
    c.drawString(col_x, pt(0, 44)[1], BRAND)

    c.setFont("Helvetica", 6)
    c.drawString(col_x, pt(0, 37)[1], f"Model: {hardware_type}")
    c.setFont("Courier", 6)
    c.drawString(col_x, pt(0, 31)[1], f"MAC: {mac_address}")
    c.setFont("Helvetica", 6)
    c.drawString(col_x, pt(0, 25)[1], POWER_SPEC)

    c.setFont("Helvetica", 5)
    c.drawString(col_x, pt(0, 18)[1], LEGAL_NAME)
    for i, line in enumerate(LEGAL_ADDRESS):
        c.drawString(col_x, pt(0, 14 - i * 4)[1], line)
    c.drawString(col_x, pt(0, 4)[1], f"{MADE_IN}  ·  {EMAIL}")

    # Compliance marks, bottom-right of the box.
    _draw_svg(c, WEEE_SYMBOL_SVG, *pt(90, 3), height_mm=8)
    _draw_svg(c, CE_MARK_SVG, *pt(76, 4), height_mm=5)


def _wrap_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    """Greedy word-wrap: splits text into lines that each fit within max_width
    (points) at the given font/size."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if stringWidth(candidate, font_name, font_size) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_svg(c: canvas.Canvas, svg_path: Path, x: float, y: float,
              height_mm: float | None = None, width_mm: float | None = None) -> None:
    """Embed an SVG file at (x, y) = bottom-left corner (absolute PDF points),
    scaled to fit the given height and/or width (mm) while preserving aspect
    ratio — pass only one of height_mm/width_mm to derive the other."""
    drawing = svg2rlg(str(svg_path))
    if not drawing or not drawing.width or not drawing.height:
        return

    target_h = height_mm * mm if height_mm else None
    target_w = width_mm * mm if width_mm else None
    if target_w and target_h:
        scale = min(target_w / drawing.width, target_h / drawing.height)
    elif target_h:
        scale = target_h / drawing.height
    elif target_w:
        scale = target_w / drawing.width
    else:
        scale = 1.0

    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)
    renderPDF.draw(drawing, c, x, y)
