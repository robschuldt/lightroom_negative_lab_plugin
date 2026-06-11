# NLP Optimizer

A local analysis app + Lightroom Classic plugin that adds a gentle, automatic
"polish" layer on top of negatives you've already converted with Negative Lab Pro.

Lightroom's plugin SDK **cannot read pixel data**, so the analysis has to happen
outside Lightroom. The plugin exports a small preview of the converted positive,
a local Python server measures it (tonal range, clipping, color cast, saturation)
and returns adjustment deltas, and the plugin stacks those onto the existing
conversion using standard develop sliders.

```
Lightroom (NLP positive) --export JPEG--> Python server --deltas--> plugin applies
```

## What it does

For each selected photo it measures the converted look and applies, on top of NLP:

- **Black & white points** — opens up milky shadows / dull highlights, without clipping
- **Highlight & shadow recovery** — pulls back any blown or blocked detail (matters for print)
- **Contrast** — a small bump only when the image is flat
- **Exposure** — a gentle nudge only for gross under/over-exposure
- **White balance** — removes ~60% of a measured color cast (keeps some film character)
- **Vibrance** — a small lift only when the frame is dull

All corrections are clamped per frame so nothing swings too hard. Tune everything
in `analyzer.py` — `STRENGTH` scales the whole effect at once.

## Setup

### 1. The local server (Python 3.9+)

```bash
cd nlp-optimizer
pip install -r requirements.txt
python server.py
```

Leave it running. It listens only on `127.0.0.1:8765` — it is never exposed to
the network.

### 2. The Lightroom plugin

1. Copy the `nlp-optimizer.lrdevplugin` folder somewhere permanent (not a temp dir).
2. In Lightroom Classic: **File > Plug-in Manager > Add**, select the folder.
3. Open `Info.lua` once and change `LrToolkitIdentifier` to your own reverse-domain
   string (e.g. `com.jane.nlpoptimizer`).

## Usage

1. Convert your negatives with Negative Lab Pro as usual.
2. Select one or more converted positives.
3. **File > Plug-in Extras > Optimize Converted Negative(s)** (or the Library menu).

You'll get a summary dialog. Adjustments are normal develop edits, so **Cmd/Ctrl+Z**
undoes them and you can fine-tune by hand afterward.

## Important caveats

- **Re-editing in NLP.** Negative Lab Pro stores its analysis in metadata and warns
  that changing the underlying Lightroom settings can confuse it if you reopen NLP on
  that frame later. This tool changes those sliders by design. If you think you'll want
  to re-edit a frame inside NLP, finish your NLP work first, or switch the plugin to
  apply to a virtual copy (in `OptimizeNegative.lua`, call
  `photo:createVirtualCopy()` and optimize that instead).
- **Print.** This gives a clean, unclipped baseline. Final soft-proofing for a specific
  paper/printer profile is still a manual step in Lightroom.
- **Color profile on export.** Current LrC SDK builds have a bug forcing some exports to
  sRGB. That's fine here — the preview is only for measurement; the real edits are applied
  to your original file.

## Files

- `analyzer.py` — all the measurement + tuning constants
- `server.py` — the local HTTP server (`/analyze`, `/health`)
- `nlp-optimizer.lrdevplugin/` — the Lightroom plugin (`Info.lua`, `OptimizeNegative.lua`)
