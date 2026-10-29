"""Tiny gettext-style translation layer. Message ids are English; Hungarian is built in."""
import os

_lang = "en"
_catalog = {}


def detect(configured="auto"):
    """NANGER_LANG env > config value > locale environment (hu_* -> Hungarian)."""
    for value in (os.environ.get("NANGER_LANG"), configured):
        if value and value.lower() in ("en", "hu"):
            return value.lower()
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if val:
            return "hu" if val.lower().startswith("hu") else "en"
    return "en"


def set_language(lang):
    global _lang, _catalog
    _lang = lang
    if lang == "hu":
        from .catalog_hu import HU
        _catalog = HU
    else:
        _catalog = {}


def language():
    return _lang


def tr(msg):
    """Translate a message id; unknown ids are returned unchanged."""
    return _catalog.get(msg, msg)
