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

app = FastAPI(title="NLP Optimizer")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze", response_class=PlainTextResponse)
async def analyze_endpoint(request: Request):
    path = (await request.body()).decode("utf-8").strip().strip('"')
    try:
        rgb = load_image(path)
    except Exception as exc:                       # bad path / unreadable file
        return PlainTextResponse(f"# error: {exc}\n", status_code=400)

    adjustments, report = analyze(rgb)

    lines = [f"# {k}={v}" for k, v in report.items()]      # comments (ignored by plugin)
    lines += [f"{k}={v}" for k, v in adjustments.items()]   # the actual deltas
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
