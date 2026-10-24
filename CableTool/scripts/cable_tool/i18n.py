"""Interface languages.

Every string the artist sees goes through tr(), with the English text as
its key:

    tr("Rebuilt {0}.").format(name)

locales/<code>.json maps English to that language. Anything missing falls
back to English, so a gap in a translation shows English, never an error.
tests/test_cable_rig.py checks that every string has a translation and
keeps its {placeholders}.

The language is remembered in a Maya optionVar. The first time, it
follows Maya's own interface language.
"""

import io
import json
import os

import maya.cmds as cmds

# (code, name shown in the Language menu, in that language).
LANGUAGES = (
    ("en", "English"),
    ("zh", u"中文"),          # 中文 (Simplified Chinese)
    ("yue", u"粵語"),         # 粵語 (Cantonese, Traditional)
    ("es", u"Español"),          # Español
    ("fr", u"Français"),         # Français
)
OPTION_VAR = "cableToolLanguage"
LOCALES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")

_current = None
_catalogs = {}


def catalog(code):
    """English -> translation for one language ({} for English)."""
    if code == "en":
        return {}
    if code not in _catalogs:
        path = os.path.join(LOCALES, code + ".json")
        with io.open(path, encoding="utf-8") as handle:
            _catalogs[code] = json.load(handle)
    return _catalogs[code]


def _from_maya():
    """The tool language matching Maya's interface language."""
    try:
        language = (cmds.about(uiLanguage=True) or "").lower()
    except RuntimeError:
        return "en"
    if language.startswith(("zh_hk", "zh-hk", "zh_mo", "yue")):
        return "yue"
    if language.startswith("zh"):
        return "zh"
    if language.startswith("es"):
        return "es"
    if language.startswith("fr"):
        return "fr"
    return "en"


def current():
    global _current
    if _current is None:
        saved = (cmds.optionVar(query=OPTION_VAR)
                 if cmds.optionVar(exists=OPTION_VAR) else None)
        codes = [code for code, _name in LANGUAGES]
        _current = saved if saved in codes else _from_maya()
    return _current


def set_language(code, remember=True):
    """Switch language. remember=False leaves the saved choice alone (for
    tests)."""
    global _current
    if code not in [c for c, _name in LANGUAGES]:
        raise ValueError("Unknown language: " + code)
    _current = code
    if remember:
        cmds.optionVar(stringValue=(OPTION_VAR, code))


def N_(text):
    """Marks a string for translation where it's defined; tr() translates
    it where it's shown. (The gettext convention.)"""
    return text


def tr(text):
    """text in the current language (English if there's no translation)."""
    return catalog(current()).get(text) or text
