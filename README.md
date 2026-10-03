# Property Capture Pipeline

Handheld consumer capture → a dimensioned, stitched floor plan with a
**confidence interval on every measurement**, from one output contract
(`schemas/output_schema.json`) produced by three input tiers (LiDAR / video /
photos).

## Honest status (read first)

Built **without an iPhone 15+/Mac**. The **LiDAR tier is shipped and fully
reproducible** on the provided sample capture; the video and photo tiers are
**designed** (technical report §7); the self-captured benchmark, head-to-head,
and walk-in test are **blocked by hardware**. See `docs/compliance_matrix.md`
for the per-requirement breakdown and `docs/technical_report.md` for the
engineering. I chose a smaller true submission over a larger unverifiable one.

## Install (clean machine, < 2 min)

```bash
pip install -r requirements.txt
```

Dependencies: numpy, scipy, Pillow, matplotlib, opencv-python, scikit-learn,
shapely, jsonschema. No GPU, no network, no model weights needed for the LiDAR
tier.

## Run on a capture (one command, < 1 min on the sample)

```bash
python run.py --capture data/<capture_id> --tier lidar --out outputs/
```

Produces, deterministically:
- `outputs/<capture_id>.json` — validated against `schemas/output_schema.json`
- `outputs/<capture_id>_plan.png` — rendered top-down plan

Expected capture layout is documented in `docs/capture_route.md`. To run on the
provided sample, unzip `single_room.zip` into `data/` so that
`data/c00a170fe1/` contains `depth/`, `confidence/`, `rgb.mp4`, `*.csv`.

## Reproduce every reported number

```bash
python run.py --capture data/c00a170fe1 --tier lidar     # plan + JSON + drift ablation
python benchmark/repeatability.py data/c00a170fe1        # even/odd repeatability
python benchmark/fix_loop.py data/c00a170fe1             # before(box) vs after(contour)
```

Headline results on the sample: footprint **28.6 m²**, ceiling **2.04 m**
(under-observed, wide interval), repeatability **area 0.03%**, fix loop
**14% → 0.03%**.

## Layout

```
run.py                     one command per capture
schemas/output_schema.json the output contract (JSON Schema draft-07)
src/
  io_capture.py            ARKit capture IO + geometry (backprojection, poses)
  reconstruct.py           planes, contour footprint, measurements
  calibrate.py             propagated confidence intervals
  openings.py              door/window detection (conservative)
  drift.py                 plane-anchored pose correction + ablation
  render.py                top-down plan renderer
  schema_io.py             fills the output contract
benchmark/
  repeatability.py         even/odd frame-split gate
  fix_loop.py              before/after, regenerable
  figures/wallcells.png    evidence for the fix-loop root cause
docs/
  technical_report.md      architecture, tiers, calibration, fix loop, failures
  compliance_matrix.md     requirement → file → status
  capture_route.md         Route 2 protocol + device matrix
```

## Notes on reproducibility & the walk-in test

The LiDAR path is deterministic and runs live (no cached outputs). The pipeline
reads only the capture folder; nothing calls external infrastructure. The parts
that cannot run live from here (on-device capture, laser ground truth) are
called out explicitly rather than faked.
