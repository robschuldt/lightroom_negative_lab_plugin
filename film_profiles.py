"""
film_profiles.py — per-stock profiles that steer how the optimizer adjusts.

Each film stock has its own character (contrast, saturation, color bias, latitude),
so a single "auto" correction is wrong for all of them. A profile doesn't replace
the measurement in analyzer.py; it *modulates* the response — how hard to neutralize
a cast, whether to add contrast or hold it back, how much highlight headroom to
protect, and so on.

Profiles are deliberately conservative generalizations. They're starting points you
should tune to your own scanning/taste. Every key is optional; missing keys fall back
to DEFAULTS, so a new profile can override just one or two things.

Keys:
  label             display name
  is_bw             True for black & white (skips all color logic)
  cast_correction   0..1, fraction of measured color cast to remove
                    (low = keep the film's character; high = neutralize)
  temp_bias         -1..1, nudge added to temperature shift (+ = warmer)
  tint_bias         -1..1, nudge added to tint shift (+ = magenta, - = green)
  contrast_gain     multiplier on the contrast delta (<1 softer, >1 punchier)
  vibrance_gain     multiplier on the vibrance delta (0 disables)
  highlight_protect multiplier on highlight recovery (>1 for narrow-latitude film)
  shadow_gain       multiplier on shadow lift
  black_gain        multiplier on the blacks delta (>1 = richer blacks)
  white_gain        multiplier on the whites delta
  target_black      override for the target black point (0..1)
  target_white      override for the target white point (0..1)
"""

DEFAULTS = {
    "label": "Generic color negative",
    "is_bw": False,
    "cast_correction": 0.60,
    "temp_bias": 0.0,
    "tint_bias": 0.0,
    "contrast_gain": 1.0,
    "vibrance_gain": 1.0,
    "highlight_protect": 1.0,
    "shadow_gain": 1.0,
    "black_gain": 1.0,
    "white_gain": 1.0,
    "target_black": 0.02,
    "target_white": 0.97,
}

# Only the overrides are listed; everything else inherits DEFAULTS.
PROFILES = {
    "generic_color": {},

    # --- Kodak color negative ---
    "kodak_portra_160": {
        "label": "Kodak Portra 160",
        "cast_correction": 0.40, "temp_bias": 0.04,
        "contrast_gain": 0.75, "vibrance_gain": 0.6, "highlight_protect": 1.1,
    },
    "kodak_portra_400": {
        "label": "Kodak Portra 400",
        "cast_correction": 0.40, "temp_bias": 0.05,
        "contrast_gain": 0.80, "vibrance_gain": 0.7, "highlight_protect": 1.1,
    },
    "kodak_portra_800": {
        "label": "Kodak Portra 800",
        "cast_correction": 0.45, "temp_bias": 0.04,
        "contrast_gain": 0.85, "vibrance_gain": 0.7, "highlight_protect": 1.1,
    },
    "kodak_ektar_100": {
        "label": "Kodak Ektar 100",
        "cast_correction": 0.70,
        "contrast_gain": 1.15, "vibrance_gain": 0.2, "black_gain": 1.1,
    },
    "kodak_gold_200": {
        "label": "Kodak Gold 200",
        "cast_correction": 0.35, "temp_bias": 0.08,
        "contrast_gain": 0.90, "vibrance_gain": 0.8,
    },
    "kodak_ultramax_400": {
        "label": "Kodak UltraMax 400",
        "cast_correction": 0.40, "temp_bias": 0.06,
        "contrast_gain": 0.95, "vibrance_gain": 0.8,
    },

    # --- Fuji color negative (cooler, slight green lean) ---
    "fuji_pro_400h": {
        "label": "Fuji Pro 400H",
        "cast_correction": 0.45, "temp_bias": -0.03, "tint_bias": -0.03,
        "contrast_gain": 0.80, "vibrance_gain": 0.6, "highlight_protect": 1.1,
    },
    "fuji_superia_400": {
        "label": "Fuji Superia 400",
        "cast_correction": 0.50, "tint_bias": -0.03,
        "contrast_gain": 1.0, "vibrance_gain": 0.7,
    },
    "fuji_c200": {
        "label": "Fuji C200",
        "cast_correction": 0.50, "tint_bias": -0.02,
        "contrast_gain": 1.0, "vibrance_gain": 0.7,
    },

    # --- CineStill (tungsten / halation) ---
    "cinestill_800t": {
        "label": "CineStill 800T",
        "cast_correction": 0.50, "temp_bias": 0.0,
        "contrast_gain": 0.90, "vibrance_gain": 0.6, "highlight_protect": 1.3,
    },
    "cinestill_50d": {
        "label": "CineStill 50D",
        "cast_correction": 0.55,
        "contrast_gain": 1.0, "vibrance_gain": 0.5, "highlight_protect": 1.2,
    },

    # --- Slide / E-6 (high contrast, saturated, narrow latitude) ---
    "slide_e6": {
        "label": "Slide / E-6 (Velvia, Provia)",
        "cast_correction": 0.70,
        "contrast_gain": 0.50, "vibrance_gain": 0.1,
        "highlight_protect": 1.4, "shadow_gain": 1.2,
    },

    # --- Black & white ---
    "bw_generic": {
        "label": "Black & white (generic)", "is_bw": True,
        "contrast_gain": 1.0, "black_gain": 1.1,
    },
    "ilford_hp5_400": {
        "label": "Ilford HP5 Plus 400", "is_bw": True,
        "contrast_gain": 1.0, "black_gain": 1.1,
    },
    "kodak_trix_400": {
        "label": "Kodak Tri-X 400", "is_bw": True,
        "contrast_gain": 1.1, "black_gain": 1.15,
    },
    "kodak_tmax_100": {
        "label": "Kodak T-Max 100", "is_bw": True,
        "contrast_gain": 0.95, "black_gain": 1.05,
    },
}


def get_profile(name):
    """Return a fully-merged profile dict (DEFAULTS + overrides)."""
    overrides = PROFILES.get((name or "").strip(), None)
    if overrides is None:                       # unknown / empty -> sensible fallback
        overrides = PROFILES["bw_generic"] if "bw" in (name or "").lower() else {}
    merged = dict(DEFAULTS)
    merged.update(overrides)
    merged["key"] = name or "generic_color"
    return merged


def suggest_family(report):
    """Best-effort guess of a film *family* from measured stats (not an exact stock).

    Returns one of the PROFILES keys. This only pre-selects a reasonable default —
    it is not a substitute for tagging the actual stock.
    """
    sat = report.get("mean_sat", 0.0)
    spread = report.get("white_point", 1.0) - report.get("black_point", 0.0)
    warm = report.get("cast_warm", 0.0)

    if sat < 0.04:                              # almost no color -> black & white
        return "bw_generic"
    if sat > 0.32 and spread > 0.85:            # very saturated + contrasty -> slide
        return "slide_e6"
    if warm > 0.12 and sat < 0.22:              # warm, muted -> consumer/portrait neg
        return "kodak_gold_200"
    if sat > 0.26:                              # saturated negative -> Ektar-like
        return "kodak_ektar_100"
    return "generic_color"
