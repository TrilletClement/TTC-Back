"""
Validation for board SVG content submitted by clients when creating an order.

Order creation is a public endpoint that accepts svg_content/svg as raw text
in the request body — while the normal flow round-trips a string generated
by board_svg_service.build_export_svg, nothing stops a direct API call from
sending arbitrary markup. Rather than trying to sanitize/rewrite untrusted
SVG (easy to get subtly wrong), this validates against the exact narrow
dialect the generator produces and rejects anything outside it (fail closed).
"""
import re
import xml.etree.ElementTree as ET

from fastapi import HTTPException

_MAX_LENGTH = 200_000

_ALLOWED_TAGS = {
    "svg", "defs", "style", "g", "rect", "circle", "line", "path", "text", "tspan",
}

_ALLOWED_ATTRS = {
    "xmlns", "width", "height", "viewBox",
    "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "d", "transform", "fill", "stroke", "stroke-width", "stroke-linecap",
    "stroke-linejoin", "opacity", "text-anchor", "dominant-baseline",
    "font-family", "font-size", "font-weight", "text-transform",
}

# DOCTYPE/ENTITY enable XML entity-expansion (billion-laughs) DoS; an
# xml-stylesheet PI can point at an external XSLT that carries a script.
_DANGEROUS_MARKUP = re.compile(r"<!DOCTYPE|<!ENTITY|<\?xml-stylesheet", re.IGNORECASE)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def validate_board_svg(svg_content: str | None) -> None:
    """No-op when svg_content is empty/None — some callers legitimately store
    no SVG (order_item.svg_content is nullable). Only enforce the allowlist
    once content is actually present."""
    if not svg_content:
        return
    if len(svg_content) > _MAX_LENGTH:
        raise HTTPException(status_code=400, detail="Invalid SVG content.")
    if _DANGEROUS_MARKUP.search(svg_content):
        raise HTTPException(status_code=400, detail="Invalid SVG content.")

    try:
        root = ET.fromstring(svg_content)
    except ET.ParseError:
        raise HTTPException(status_code=400, detail="Invalid SVG content.")

    if _local_name(root.tag) != "svg":
        raise HTTPException(status_code=400, detail="Invalid SVG content.")

    for el in root.iter():
        tag = _local_name(el.tag)
        if tag not in _ALLOWED_TAGS:
            raise HTTPException(status_code=400, detail=f"Disallowed SVG element: {tag}")
        for attr in el.attrib:
            if _local_name(attr) not in _ALLOWED_ATTRS:
                raise HTTPException(status_code=400, detail=f"Disallowed SVG attribute: {attr}")
        if tag == "style" and el.text and "javascript:" in el.text.lower():
            raise HTTPException(status_code=400, detail="Invalid SVG content.")
