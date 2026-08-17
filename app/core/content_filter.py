"""Content moderation for free-text fields the customer fully controls (LED
stop labels, terminus names, board names). These end up lasered/printed on
the physical product or visible to staff, so obviously hateful content or
slurs must be rejected outright.

Primary check is OpenAI's Moderation API (free, multilingual). If it's not
configured (no OPENAI_API_KEY) or the call fails (network issue, rate limit),
we fall back to a small local blocklist rather than either failing the
request or silently skipping moderation entirely.
"""
import logging
import re
import unicodedata

import requests
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

_MODERATION_URL = "https://api.openai.com/v1/moderations"
_MODERATION_MODEL = "omni-moderation-latest"

# Fallback list only — deliberately short and focused on unambiguous
# slurs/hate terms (FR/EN/NL), not a general profanity filter (too many
# false positives on ordinary stop/line names).
_BLOCKED_TERMS: set[str] = {
    # FR
    "negre", "negro", "bougnoule", "bounty", "bicot", "youpin", "youpine",
    "chintok", "niaque", "romano", "sale arabe", "sale noir", "sale juif",
    "sale musulman", "sale blanc", "nique ta mere", "nique ta race",
    "sale pd", "sale pede",
    # EN
    "nigger", "nigga", "faggot", "spic", "kike", "chink", "gook", "wetback",
    "raghead", "towelhead", "sandnigger",
    # NL
    "neger", "mocro", "kutmarokkaan", "kutneger", "kanker",
}

def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", without_accents)

_BLOCKED_PATTERN = re.compile(
    r"(?<![a-z0-9])(" + "|".join(re.escape(t) for t in sorted(_BLOCKED_TERMS, key=len, reverse=True)) + r")(?![a-z0-9])"
)

def _local_blocklist_hit(value: str) -> bool:
    return bool(_BLOCKED_PATTERN.search(_normalize(value)))

def _openai_flagged(value: str) -> bool | None:
    """True/False from OpenAI Moderation, or None if the call couldn't be made."""
    if not settings.OPENAI_API_KEY:
        return None
    try:
        resp = requests.post(
            _MODERATION_URL,
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            json={"input": value, "model": _MODERATION_MODEL},
            timeout=5,
        )
        resp.raise_for_status()
        return bool(resp.json()["results"][0]["flagged"])
    except Exception:
        logger.warning("OpenAI moderation call failed, falling back to local blocklist", exc_info=True)
        return None

def assert_clean_text(value: str | None, field_name: str = "This field") -> None:
    """Raises HTTPException(400) if `value` is flagged as inappropriate."""
    if not value:
        return
    flagged = _openai_flagged(value)
    if flagged is None:
        flagged = _local_blocklist_hit(value)
    if flagged:
        raise HTTPException(status_code=400, detail=f"{field_name} contains content that is not allowed.")
