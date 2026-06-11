"""
server.py — tiny local HTTP server the Lightroom plugin talks to.

It listens on 127.0.0.1 only (never exposed to the network). The plugin POSTs
the path of an exported JPEG as the raw request body; we analyze it and return
the adjustments as plain `Key=Value` lines so the Lua side needs no JSON parser.

Run it with:   python server.py
(or:           uvicorn server:app --host 127.0.0.1 --port 8765)
"""

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import uvicorn

from analyzer import load_image, analyze
from film_profiles import PROFILES, DEFAULTS, get_profile
from film_lookup import resolve_unknown_film

app = FastAPI(title="NLP Optimizer")


def resolve_profile(film):
    """Return (profile_dict, source). Known stock -> builtin; unknown -> looked up
    on demand; otherwise a generic/B&W fallback."""
    if film in PROFILES:
        return get_profile(film), "builtin"
    learned = resolve_unknown_film(film)
    if learned:
        profile = dict(DEFAULTS)
        profile.update(learned)
        profile["key"] = film
        return profile, "looked-up"
    return get_profile(film), "generic"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze", response_class=PlainTextResponse)
async def analyze_endpoint(request: Request):
    raw = (await request.body()).decode("utf-8").strip()

    # Body is either a bare path (legacy) or `film=...` / `path=...` lines.
    film, path = "generic_color", raw
    for line in raw.splitlines():
        if line.startswith("film="):
            film = line[5:].strip()
        elif line.startswith("path="):
            path = line[5:].strip()
    path = path.strip('"')

    try:
        rgb = load_image(path)
    except Exception as exc:                       # bad path / unreadable file
        return PlainTextResponse(f"# error: {exc}\n", status_code=400)

    profile, source = resolve_profile(film)
    adjustments, report = analyze(rgb, profile)
    report = {"source": source, **report}

    lines = [f"# {k}={v}" for k, v in report.items()]      # comments (ignored by plugin)
    lines += [f"{k}={v}" for k, v in adjustments.items()]   # the actual deltas
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
