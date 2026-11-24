"""Guards for the FR/EN translations in web/i18n.js.

The frontend falls back silently (to English, then to the raw key), so a missing
translation never crashes anything — it just shows "item.foo" to a visitor.
These tests turn that silent failure into a red CI run.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
SERVER = ROOT / "server"

KEY = r"[a-z]+(?:\.[\w]+)+"


def _dictionaries() -> dict[str, set[str]]:
    src = (WEB / "i18n.js").read_text(encoding="utf-8")
    fr_part, _, en_part = src.partition("\n    en: {")
    assert en_part, "could not find the `en: {` block in i18n.js"
    pattern = re.compile(rf'^\s+"({KEY})":\s', re.MULTILINE)
    return {"fr": set(pattern.findall(fr_part)), "en": set(pattern.findall(en_part))}


def test_both_languages_define_the_same_keys():
    d = _dictionaries()
    assert d["fr"], "no French keys parsed"
    assert d["fr"] - d["en"] == set(), "keys missing in English"
    assert d["en"] - d["fr"] == set(), "keys missing in French"


def test_html_translation_attributes_point_to_existing_keys():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    used = set(re.findall(rf'data-i18n(?:-ph|-title|-aria)?="({KEY})"', html))
    assert used, "no data-i18n attributes found"
    assert used - _dictionaries()["fr"] == set()


def test_keys_used_in_app_js_exist():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    # Any quoted string shaped like a translation key (t("x.y"), ternaries, stored keys…).
    prefixes = "meta|hero|paste|status|pwa|opt|item|clip|run|feat|foot|err"
    used = set(re.findall(rf'"((?:{prefixes})\.[\w.]+)"', js))
    assert used, "no translation keys found in app.js"
    assert used - _dictionaries()["fr"] == set()


def test_every_server_error_code_is_translated():
    """A new error code raised by the API must come with an `err.<code>` message."""
    codes: set[str] = set()
    for path in SERVER.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        codes |= set(re.findall(r'_http_error\("(\w+)"', src))
        codes |= set(re.findall(r'DownloaderError\("(\w+)"', src))
        codes |= set(re.findall(r'_fail\(job, "(\w+)"', src))
        codes |= set(re.findall(r'^\s+"(\w+)":\s+\d{3},', src, re.MULTILINE))  # main._STATUS
    assert {"invalid_url", "rate_limited", "too_large"} <= codes, "code scan looks broken"

    translated = _dictionaries()["fr"]
    missing = {c for c in codes if f"err.{c}" not in translated}
    assert missing == set(), f"error codes without an err.* translation: {sorted(missing)}"
