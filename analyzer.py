"""
analyzer.py — measures a converted positive and proposes a gentle "polish" layer.

This runs on a small JPEG that Lightroom exports of the *already NLP-converted*
positive. It never touches the negative or NLP's own controls. It only measures
the look and returns adjustment deltas that the Lightroom plugin stacks on top
using standard develop sliders.

Everything here is intentionally conservative. The goal is a clean, print- and
web-friendly baseline, not a heavy "auto" stomp. Tune the constants below to
taste — STRENGTH scales the whole effect at once.
"""

import math
import numpy as np
from PIL import Image

# ----------------------------------------------------------------------------
# Tuning constants — change these to make the optimizer gentler or stronger.
# ----------------------------------------------------------------------------
STRENGTH        = 1.0    # global multiplier on every adjustment (0 = no-op)

TARGET_BLACK    = 0.02   # where we'd like the darkest tones to sit (0..1)
TARGET_WHITE    = 0.97   # where we'd like the brightest tones to sit (0..1)
TARGET_SPREAD   = 0.70   # if (white-black) range is below this, add contrast
TARGET_MID_LO   = 0.22   # below this median => image reads too dark
TARGET_MID_HI   = 0.72   # above this median => image reads too bright
TARGET_SAT      = 0.22   # below this mean saturation => add a little vibrance

CAST_CORRECTION = 0.60   # fraction of the measured color cast to remove (0..1)
                         # keep < 1 so the film character isn't fully neutralized

# Clamps so a single frame can never swing too hard.
MAX_BLACKS      = 25
MAX_WHITES      = 25
MAX_HIGHLIGHTS  = 30
MAX_SHADOWS     = 20
MAX_CONTRAST    = 18
MAX_EXPOSURE    = 0.45
MAX_VIBRANCE    = 10


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def load_image(path, max_side=2000):
    """Load any exported JPEG/TIFF as a float RGB array in [0, 1]."""
    im = Image.open(path).convert("RGB")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    arr = np.asarray(im, dtype=np.float32) / 255.0
    return arr


def analyze(rgb, profile=None):
    """Return (adjustments, report). Adjustments are deltas the plugin applies.

    `profile` is a film-stock dict (see film_profiles.py) that modulates the
    response. When None, neutral defaults are used.
    """
    p = profile or {}
    cast_correction   = p.get("cast_correction", CAST_CORRECTION)
    temp_bias         = p.get("temp_bias", 0.0)
    tint_bias         = p.get("tint_bias", 0.0)
    contrast_gain     = p.get("contrast_gain", 1.0)
    vibrance_gain     = p.get("vibrance_gain", 1.0)
    highlight_protect = p.get("highlight_protect", 1.0)
    shadow_gain       = p.get("shadow_gain", 1.0)
    black_gain        = p.get("black_gain", 1.0)
    white_gain        = p.get("white_gain", 1.0)
    target_black      = p.get("target_black", TARGET_BLACK)
    target_white      = p.get("target_white", TARGET_WHITE)
    is_bw             = p.get("is_bw", False)

    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = 0.2126 * R + 0.7152 * G + 0.0722 * B

    lo  = float(np.percentile(lum, 0.25))
    hi  = float(np.percentile(lum, 99.75))
    med = float(np.percentile(lum, 50))
    clip_black = float((lum < 0.003).mean())
    clip_white = float((lum > 0.997).mean())

    # --- Tonal range: set sensible black & white points --------------------
    if clip_black < 0.002:                     # shadows not already crushed
        blacks = -_clamp((lo - target_black) * 600, 0, MAX_BLACKS)
    else:                                       # shadows clipping -> lift them
        blacks = _clamp(clip_black * 300, 0, 15)
    blacks *= black_gain

    if clip_white < 0.002:                      # highlights have headroom
        whites = _clamp((target_white - hi) * 600, 0, MAX_WHITES)
    else:                                       # highlights clipping -> pull back
        whites = -_clamp(clip_white * 300, 0, 15)
    whites *= white_gain

    # --- Recover detail at the extremes (matters most for print) -----------
    highlights = -_clamp(clip_white * 800, 0, MAX_HIGHLIGHTS) * highlight_protect
    shadows    =  _clamp((0.10 - min(lo, 0.10)) * 300, 0, MAX_SHADOWS) * shadow_gain

    # --- Add contrast only if the image is flat ----------------------------
    spread = hi - lo
    contrast = _clamp((TARGET_SPREAD - spread) * 60, 0, MAX_CONTRAST) \
        if spread < TARGET_SPREAD else 0.0
    contrast *= contrast_gain

    # --- Gentle exposure nudge only for gross under/over-exposure ----------
    exposure = 0.0
    if med < TARGET_MID_LO:
        exposure = _clamp((0.30 - med) * 1.5, 0, MAX_EXPOSURE)
    elif med > TARGET_MID_HI:
        exposure = -_clamp((med - 0.62) * 1.5, 0, MAX_EXPOSURE)

    # --- Color cast: estimate from near-neutral pixels ---------------------
    maxc = rgb.max(axis=2)
    minc = rgb.min(axis=2)
    sat  = (maxc - minc) / np.clip(maxc, 1e-4, None)
    neutral = (sat < 0.18) & (lum > 0.15) & (lum < 0.90)
    if neutral.sum() > 0.01 * lum.size:
        mR, mG, mB = float(R[neutral].mean()), float(G[neutral].mean()), float(B[neutral].mean())
    else:                                       # fall back to whole-frame gray world
        mR, mG, mB = float(R.mean()), float(G.mean()), float(B.mean())

    eps = 1e-4
    warm = math.log((mR + eps) / (mB + eps))    # >0 => too red/warm
    green = math.log((mG + eps) / (((mR + mB) / 2) + eps))  # >0 => too green
    temp_shift = _clamp(-warm * 1.2, -1, 1) * cast_correction + temp_bias
    tint_shift = _clamp(green * 1.2, -1, 1) * cast_correction + tint_bias
    temp_shift = _clamp(temp_shift, -1, 1)
    tint_shift = _clamp(tint_shift, -1, 1)

    # --- Vibrance: small lift if the frame is dull -------------------------
    colorful = sat[lum > 0.10]
    mean_sat = float(colorful.mean()) if colorful.size else 0.0
    vibrance = _clamp((TARGET_SAT - mean_sat) * 60, 0, MAX_VIBRANCE) \
        if mean_sat < TARGET_SAT else 0.0
    vibrance *= vibrance_gain

    # Black & white: no color work at all (the film has no color signature).
    if is_bw:
        temp_shift = 0.0
        tint_shift = 0.0
        vibrance = 0.0

    s = STRENGTH
    adjustments = {
        "BlacksDelta":     round(blacks * s, 1),
        "WhitesDelta":     round(whites * s, 1),
        "HighlightsDelta": round(highlights * s, 1),
        "ShadowsDelta":    round(shadows * s, 1),
        "ContrastDelta":   round(contrast * s, 1),
        "ExposureDelta":   round(exposure * s, 3),
        "VibranceDelta":   round(vibrance * s, 1),
        "TempShiftNorm":   round(temp_shift * s, 3),   # normalized -1..1
        "TintShiftNorm":   round(tint_shift * s, 3),   # normalized -1..1
    }
    report = {
        "profile":       p.get("label", "Generic color negative"),
        "black_point":   round(lo, 3),
        "white_point":   round(hi, 3),
        "median":        round(med, 3),
        "clip_black_pct": round(clip_black * 100, 2),
        "clip_white_pct": round(clip_white * 100, 2),
        "cast_warm":     round(warm, 3),
        "cast_green":    round(green, 3),
        "mean_sat":      round(mean_sat, 3),
    }
    return adjustments, report
