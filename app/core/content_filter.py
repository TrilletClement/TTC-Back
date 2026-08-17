"""Content moderation for free-text fields the customer fully controls (LED
stop labels, terminus names, board names). These end up lasered/printed on
the physical product or visible to staff, so obviously hateful content or
slurs must be rejected outright.

The local blocklist always runs (cheap, no network) and is OR'd with
OpenAI's Moderation API (free, multilingual) when configured. Both are
needed: OpenAI catches severe/varied hate speech the blocklist doesn't
enumerate, but it does NOT flag mild "insult + nationality" phrasing
(e.g. "sale paraguayenne") — that's exactly what the local pattern below
covers. If OPENAI_API_KEY is missing or the call fails (network issue,
rate limit, billing), we simply rely on the local blocklist alone rather
than failing the request or silently skipping moderation entirely.
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

# Generic "insult + nationality/ethnicity" pattern (FR/EN). Not exhaustive —
# covers common demonyms so phrases like "sale paraguayenne" or "dirty
# mexican" are caught even though OpenAI's moderation doesn't flag them
# (verified: they score near-zero on hate/harassment, since the phrase
# itself isn't a slur or a threat).
_OFFENSIVE_PREFIXES = ("sale", "sales", "dirty", "filthy")

_NATIONALITY_TERMS: set[str] = {
    # FR demonyms (accents stripped by _normalize)
    "francais", "francaise", "belge", "suisse", "hollandais", "hollandaise",
    "neerlandais", "neerlandaise", "allemand", "allemande", "italien", "italienne",
    "espagnol", "espagnole", "portugais", "portugaise", "anglais", "anglaise",
    "britannique", "americain", "americaine", "canadien", "canadienne",
    "chinois", "chinoise", "japonais", "japonaise", "russe", "polonais", "polonaise",
    "roumain", "roumaine", "bulgare", "grec", "grecque", "turc", "turque",
    "marocain", "marocaine", "algerien", "algerienne", "tunisien", "tunisienne",
    "libanais", "libanaise", "congolais", "congolaise", "senegalais", "senegalaise",
    "malien", "malienne", "camerounais", "camerounaise", "ivoirien", "ivoirienne",
    "guineen", "guineenne", "haitien", "haitienne", "mexicain", "mexicaine",
    "bresilien", "bresilienne", "argentin", "argentine", "paraguayen", "paraguayenne",
    "colombien", "colombienne", "venezuelien", "venezuelienne", "peruvien", "peruvienne",
    "chilien", "chilienne", "cubain", "cubaine", "indien", "indienne",
    "pakistanais", "pakistanaise", "afghan", "afghane", "syrien", "syrienne",
    "irakien", "irakienne", "iranien", "iranienne", "israelien", "israelienne",
    "vietnamien", "vietnamienne", "cambodgien", "cambodgienne", "thailandais", "thailandaise",
    "coreen", "coreenne", "philippin", "philippine", "ukrainien", "ukrainienne",
    "serbe", "croate", "albanais", "albanaise", "kosovar", "kosovare",
    "tzigane", "rom", "gitan", "gitane",
    # EN demonyms
    "french", "belgian", "swiss", "dutch", "german", "italian", "spanish",
    "portuguese", "english", "british", "american", "canadian", "chinese",
    "japanese", "russian", "polish", "romanian", "bulgarian", "greek", "turkish",
    "moroccan", "algerian", "tunisian", "lebanese", "congolese", "senegalese",
    "malian", "cameroonian", "ivorian", "guinean", "haitian", "mexican",
    "brazilian", "argentinian", "paraguayan", "colombian", "venezuelan",
    "peruvian", "chilean", "cuban", "indian", "pakistani", "afghan", "syrian",
    "iraqi", "iranian", "israeli", "vietnamese", "cambodian", "thai", "korean",
    "filipino", "ukrainian", "serbian", "croatian", "albanian", "kosovar", "romani",
}

# Letters (incl. accented, via \w under Python 3's default unicode regex),
# digits, underscore (all \w), plus space, hyphen and apostrophe (straight
# and curly — needed for real stop names like "Gare de l'Ouest"). Everything
# else ($ * < > / ; @ " # etc.) is rejected: these values are stored in
# fixed-width DB columns and lasered onto the physical product, so there's
# no legitimate use for shell/HTML/SQL-special characters even though the
# ORM already parameterizes queries.
_SAFE_TEXT_PATTERN = re.compile(r"^[\w \-'’]+$", re.UNICODE)

def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", without_accents)

_BLOCKED_PATTERN = re.compile(
    r"(?<![a-z0-9])(" + "|".join(re.escape(t) for t in sorted(_BLOCKED_TERMS, key=len, reverse=True)) + r")(?![a-z0-9])"
)

_NATIONALITY_INSULT_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(_OFFENSIVE_PREFIXES) + r")\s+(?:"
    + "|".join(sorted(_NATIONALITY_TERMS, key=len, reverse=True)) + r")s?(?![a-z0-9])"
)

def _local_blocklist_hit(value: str) -> bool:
    normalized = _normalize(value)
    return bool(_BLOCKED_PATTERN.search(normalized)) or bool(_NATIONALITY_INSULT_PATTERN.search(normalized))

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

def assert_clean_text(value: str | None, field_key: str, max_length: int) -> None:
    """Raises HTTPException(400) if `value` is too long, uses disallowed
    characters, or is flagged as inappropriate.

    max_length should match the target DB column's length so an overlong
    value is rejected up front instead of erroring (or silently truncating)
    on insert. field_key is a stable identifier, not display text — the
    frontend maps it to a translated label (see stibFront
    ERRORS.CONTENT_NOT_ALLOWED / ERRORS.TEXT_TOO_LONG /
    ERRORS.INVALID_CHARACTERS / ERRORS.FIELD_*), since this detail is shown
    directly to end users.
    """
    if not value:
        return
    if len(value) > max_length:
        raise HTTPException(
            status_code=400,
            detail={"code": "text_too_long", "field": field_key, "max_length": max_length},
        )
    if not _SAFE_TEXT_PATTERN.match(value):
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_characters", "field": field_key},
        )
    if _local_blocklist_hit(value) or bool(_openai_flagged(value)):
        raise HTTPException(
            status_code=400,
            detail={"code": "content_not_allowed", "field": field_key},
        )
