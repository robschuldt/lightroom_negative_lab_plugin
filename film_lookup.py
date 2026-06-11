"""
film_lookup.py — resolve obscure / unlisted film stocks on demand.

When someone asks for a stock that isn't in film_profiles.PROFILES, we look up its
characteristics and synthesize a profile in our own schema, then cache it on disk so
the lookup only happens once per stock.

The backend is pluggable. The default asks an LLM (Anthropic API) that knows film-stock
characteristics to emit our profile parameters — the most reliable way to turn "this
film is warm and low-contrast" into numbers. Swap `_describe_film` for a web-search
backend if you prefer.

Live lookups need a network connection and an API key (env ANTHROPIC_API_KEY). Without
them, resolution returns None and the caller falls back to a generic profile, so the
tool still works offline — it just won't tailor unknown stocks.
"""

import json
import os
import urllib.request

CACHE_PATH = os.path.join(os.path.dirname(__file__), "learned_profiles.json")
MODEL = os.environ.get("NLP_LOOKUP_MODEL", "claude-haiku-4-5-20251001")
API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Allowed keys and the range each is clamped to. Anything else from the backend
# is ignored — we never trust raw model output directly.
_NUMERIC = {
    "cast_correction":   (0.0, 1.0),
    "temp_bias":         (-1.0, 1.0),
    "tint_bias":         (-1.0, 1.0),
    "contrast_gain":     (0.5, 1.5),
    "vibrance_gain":     (0.0, 1.2),
    "highlight_protect": (1.0, 1.5),
    "shadow_gain":       (0.8, 1.3),
    "black_gain":        (0.9, 1.2),
    "white_gain":        (0.9, 1.2),
    "target_black":      (0.0, 0.10),
    "target_white":      (0.85, 1.0),
}

_SCHEMA_PROMPT = """You estimate the look of a photographic film stock as numeric tuning parameters.
For the stock named below, return ONLY a JSON object (no prose, no code fence) with any of these keys:
  is_bw (boolean: true if black & white)
  cast_correction (0..1: ~0.35 for very characterful/warm stocks, ~0.7 for neutral)
  temp_bias (-1..1: positive = warmer signature, negative = cooler)
  tint_bias (-1..1: positive = magenta, negative = green)
  contrast_gain (0.5..1.5: <1 for low-contrast film, >1 for contrasty)
  vibrance_gain (0..1.2: low for already-saturated film)
  highlight_protect (1.0..1.5: higher for slide / narrow-latitude film)
  shadow_gain (0.8..1.3)
  black_gain (0.9..1.2)
  label (the proper, corrected stock name as a string)
Base the numbers on the stock's real character. If you do not recognize the stock, return {}.
Film stock: """


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache):
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2, sort_keys=True)
    except Exception:
        pass


def _sanitize(raw, name):
    """Whitelist keys and clamp ranges; ignore anything unexpected or malformed."""
    prof = {}
    for key, (lo, hi) in _NUMERIC.items():
        if key in raw:
            try:
                prof[key] = round(_clamp(float(raw[key]), lo, hi), 3)
            except (TypeError, ValueError):
                pass
    if isinstance(raw.get("is_bw"), bool):
        prof["is_bw"] = raw["is_bw"]
    prof["label"] = str(raw.get("label") or name)[:60]
    return prof


def _describe_film(name):
    """Default backend: ask an LLM for the stock's parameters. Returns dict or None."""
    if not API_KEY:
        return None
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": _SCHEMA_PROMPT + name}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "content-type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        text = "".join(b.get("text", "") for b in data.get("content", [])).strip()
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < 0:
            return None
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def resolve_unknown_film(name):
    """Return a sanitized profile dict for an unlisted stock, or None.

    Checks the on-disk cache first, then the lookup backend. Caches useful results so
    each obscure stock is only looked up once.
    """
    key = (name or "").strip().lower()
    if not key:
        return None

    cache = _load_cache()
    if key in cache:
        return cache[key]

    raw = _describe_film(name)
    if not raw:
        return None

    prof = _sanitize(raw, name)
    if len(prof) <= 1:                      # only a label came back -> not useful
        return None

    cache[key] = prof
    _save_cache(cache)
    return prof
