# Benchmark Report

Gates measured on the three provided sample captures. These are **not** the
self-built, laser-ground-truth benchmark the task specifies (that needs an
iPhone 15+ and a laser measurer I do not have). What they establish is the
thing achievable without hardware: the same `run.py` path produces coherent,
calibrated, repeatable output on **three captures never seen while building the
pipeline**, spanning a 4× scale range — directly countering the "only works on
the author's data" failure mode. All processed by the identical command; no
per-capture tuning.

```
python benchmark/run_all.py          # regenerates everything below over data/*
```

## Captures

| id | frames | footprint area | perimeter | ceiling height | openings |
|----|-------:|---------------:|----------:|---------------:|---------:|
| `c00a170fe1` (single_room) | 1,715 | 28.59 m² | 28.68 m | 2.04 m | 0 |
| `1a8384c3f6` (floor_only) | 5,251 | 83.43 m² | 51.68 m | 2.02 m | 1 |
| `c7d28f72c6` (with_ceiling) | 9,745 | 111.22 m² | 60.49 m | **2.79 m** | 3 |

Runtimes ~6 / 22 / 42 s end-to-end, single-threaded.

## Repeatability (disjoint even/odd frame split — proxy for two captures)

| id | area Δ | area gate (≤2%) | ceiling spread | ceiling gate (≤1 cm) |
|----|-------:|:---------------:|---------------:|:--------------------:|
| `c00a170fe1` | 0.03% | **PASS** | 3.9 cm | **FAIL** |
| `1a8384c3f6` | 0.50% | **PASS** | 0.1 cm | PASS* |
| `c7d28f72c6` | 0.77% | **PASS** | 0.1 cm | **PASS** |

- **Footprint area is repeatable at every scale** (0.03–0.77%, all ≤2%). This
  is the headline whole-room metric and it holds from 29 m² to 111 m².
- **Openings** scale with capture completeness: the fullest capture
  (`c7d28f72c6`) surfaces 3 (2 doors + 1 unknown); the cluttered single room
  surfaces 0 (conservative — a phantom counts as a miss).

## The ceiling result — precision is not accuracy (important)

The three captures expose exactly the distinction the spec's ceiling gate is
built around ("repeatable-but-biased and unrepeatable both fail"):

- `c7d28f72c6` properly images the ceiling → **2.79 m**, a normal height, and
  it is **repeatable** (0.1 cm). Genuinely *within gate*.
- `c00a170fe1` under-images the ceiling → **unrepeatable** (3.9 cm spread).
  Caught by the repeatability gate and reported as a failure, not hidden.
- `1a8384c3f6` reports 2.02 m **repeatably** (0.1 cm) — but note it is ~0.8 m
  below `c7d28f72c6`'s well-observed ceiling. This is the textbook
  **repeatable-but-biased** case: the detector consistently locks onto the
  highest *well-observed* plane, which on a capture that never sweeps the
  ceiling is not the true ceiling. *(marked PASS\* above: it passes the
  precision gate but I cannot certify it on accuracy.)*

**The honest conclusion:** repeatability measures precision; it cannot catch a
consistent bias. Separating *repeatable-and-correct* from *repeatable-but-
biased* requires absolute laser ground truth — which is precisely the hardware
I don't have. So LiDAR-tier **absolute** accuracy is reported as *unvalidated*;
the 0.8 m ceiling spread *between* captures is itself the evidence that it
matters. The capture protocol (`docs/capture_route.md`, step 4: sweep the
ceiling once per wall) is written to prevent the under-observation that causes
both the failure and the bias.

## What these captures do and do not cover

- **Do:** generalization across three unseen captures (4× scale); area/ceiling
  repeatability; opening detection on fuller captures; the full one-command →
  schema-valid JSON + plan path on each.
- **Do not:** absolute accuracy (no laser GT); multi-room segmentation +
  adjacency (the two large captures are clearly multi-area but are each traced
  as one contour — room-splitting is designed, not shipped); the photo/video
  tiers; staged damage. All tracked in `compliance_matrix.md`.

## Head-to-head vs incumbent (blocked)

Requires running poly.cam/magicplan on the *same physical rooms* and exporting —
needs an iPhone 15+ on captures I own. Not executable from here; the comparison
table format is ready in the technical report and would drop straight in.
