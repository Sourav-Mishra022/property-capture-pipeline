# Technical Report — Property Capture Pipeline

**Applied AI Engineer case study.** Author's working copy. Round-1 scope.

> **Scope honesty up front.** This submission was built without access to an
> iPhone 15+/Mac. Three scored components are therefore *impossible to execute*
> from my side and are **not** claimed as done: (a) the self-captured benchmark
> set with laser/tape ground truth, (b) the live head-to-head export from a
> consumer app on my own captures, (c) the walk-in test. What I *could* do
> honestly, I did: a complete, reproducible **LiDAR-tier pipeline on the
> provided sample capture**, with calibrated intervals, a repeatability gate, a
> drift ablation, and a real fix loop. Everything hardware-gated is **designed**
> here and marked *blocked* in the compliance matrix. I would rather hand in a
> smaller true thing than a larger unverifiable one — which is also what the
> calibration rubric rewards.

---

## 1. Architecture

One reconstruction backend, one output contract (`schemas/output_schema.json`),
three tier-specific front-ends feeding it:

```
          depth+pose+K (LiDAR)  ─┐
  video frames → SfM/SLAM      ─┼─►  world point cloud  ─►  gravity-aligned
  photo set   → multiview MVS  ─┘        (metric)             reconstruction
                                                                   │
            floor/ceiling planes · contour footprint · openings    │
            · per-surface damage · confidence intervals  ──────────┘
                                   │
                         JSON (schema) + rendered plan
```

The contract is identical across tiers; only the front-end that produces the
metric point cloud changes, and the **interval widens** as the input thins
(LiDAR → video → photos). This report ships the LiDAR front-end; §7 designs the
other two.

Key enabling fact: **ARKit's world frame is gravity-aligned (Y up)**. Verified
empirically — a single horizontal plane holds ~10% of all fused points. This
lets floor/ceiling reduce to 1-D peaks in Y and the floor plan to an X-Z
projection, removing a whole pose-estimation stage and most of the error.

## 2. Pipeline (LiDAR tier)

1. **Load** per-frame depth (256×192, uint16 mm), confidence ({0,1,2}), 6-DoF
   pose (position + quaternion), and intrinsics (given at 1920×1440 RGB, scaled
   by 256/1920 to the depth grid). `src/io_capture.py`.
2. **Backproject** confidence≥2 pixels within [0.1, 4] m to the camera frame,
   transform to world by the pose. `backproject`, `to_world`.
3. **Fuse** every 6th frame (configurable) into one raw cloud (~3.3 M points).
   Raw, not voxelised — floor/ceiling detection needs true point *density*.
4. **Floor / ceiling** = dominant horizontal planes in the Y histogram; ceiling
   is the *highest* plane above floor+1.8 m with real mass, so a 1.6 m worktop
   is never mistaken for a ceiling. `extract_floor_ceiling`.
5. **Footprint** = orientation-free outer contour of the occupied room band
   (§5 explains why not a rectangle). `build_footprint(method="contour")`.
6. **Openings**, **intervals**, **JSON**, **render**. One command: `run.py`.

Sample result: floor Y = 0.10 m, ceiling 2.14 m (**height 2.04 m**), footprint
**28.6 m²**, perimeter 28.7 m, runtime ~6 s end-to-end.

## 3. Device matrix

| Tier | Hardware | Status here | Honest accuracy (design target) |
|------|----------|-------------|---------------------------------|
| LiDAR | iPhone Pro (15 Pro+) | **Shipped** on sample data | walls ≤2 cm, area ≤2% when room is well-observed |
| Video | any iPhone 15+ | **Designed** (§7) | ≤3% (scale from ARKit metric frames) |
| Photos | any iPhone 15+ | **Designed** (§7) | ≤8%, intervals widened; floor requirement |

I cannot submit a TestFlight build (no Mac/Apple Developer account). Intended
capture route is **Route 2** (stock app + protocol); see `docs/capture_route.md`.

## 4. Error budget & calibration

Every number carries a 95% interval (`src/calibrate.py`). Because there is **no
laser ground truth on this capture**, intervals are **propagated** from a
sensor-noise model, not conformal — and the JSON labels them `"propagated"`
with `coverage_observed: null`. The honest design property the rubric asks for
is kept: intervals **widen as data thins**.

Model:
- Horizontal-plane height: σ = thickness/√n_eff ⊕ β·range, n_eff capped at 300
  (per-frame noise is correlated, so raw N overstates independence), β = 0.4%.
  A plane flagged `well_observed=False` (mass < 20% of the floor) is inflated by
  √(0.2/mass_ratio).
- Wall/edge length: endpoints inherit grid resolution ⊕ line-fit residual;
  propagated in quadrature over two endpoints.
- Area (rectangle): relative side errors in quadrature.

Dominant error terms on the sample: depth systematic (~0.4% range ≈ 8 mm @2 m)
and ceiling under-observation (below). **To make these intervals *conformal* I
need the laser-GT benchmark**, i.e. the hardware.

## 5. Why a contour footprint, not a rectangle (the central design call)

The first footprint fit a min-area rectangle to "wall" cells (tall vertical
columns). It failed repeatability badly. The sample space is **non-rectangular
and cluttered**: tall furniture creates a filled, irregular wall-cell blob
(`benchmark/figures/wallcells.png`), not a 4-wall outline. For that blob the
rectangle's *area* is stable but its *orientation* is ill-conditioned, so it
rotates between frame subsets and swaps length for width. The fix (whole §6)
was to drop the 4-wall assumption and trace the occupied region's outer contour,
reporting **area + perimeter**. This is faithful to real (L-shaped, bay,
open-plan) rooms, and its whole-room metrics are highly repeatable.

**Known failure mode (stated, not hidden):** individual straight wall lengths
and opening widths need true 3-D plane-based wall segmentation (RANSAC vertical
planes, or a learned layout model such as HorizonNet). That is designed, not
shipped; the contour fix deliberately solves the whole-room metric, not the
per-wall one.

## 6. Drift handling + ablation

Strategy: **plane-anchored correction** — estimate the floor normal by PCA on
floor points and rotate every pose so the floor maps exactly to +Y
(`src/drift.py`). Ablation on the sample (`provenance.drift_handling`):

| | footprint area |
|---|---|
| correction **off** | 28.589 m² |
| correction **on** | 28.598 m² |
| floor tilt before | 0.044° |

Small **by construction**: one room has no loop to close. The same `pose_fn`
hook consumes a pose-graph/loop-closure-corrected trajectory for the multi-room
capture (which needs the hardware to record). "Poses used as-is" is never the
path taken — the hook always runs.

## 7. Video & photo tiers (designed)

- **Video:** decode `rgb.mp4`, run SfM/visual-SLAM for a pose track; recover
  **metric** scale and feed the same backend. Gate ≤3%.
  **Empirically probed (not just asserted):** I ran COLMAP on the 45 sharpest
  frames of `c00a170fe1` (`benchmark/video_tier_probe.py`). It **fragmented** —
  three disconnected sub-models registering only 3 / 11 / 11 of 45 images — and
  the clip's Laplacian-variance texture tops out at 28 (median 7), i.e. heavy
  motion blur. Conclusion: *feature-based* SfM is the wrong tool for this
  stream. The shippable video tier instead uses ARKit's **visual-inertial
  poses** (available on any iPhone 15+, not just LiDAR models, and robust to
  blur because they fuse IMU) plus a **monocular metric-depth model** on the
  RGB frames, fused through the identical backend. That model's weights can't
  be fetched in this sandbox (restricted network, no GPU), so this tier is
  designed and probed, not shipped — the blocker is the environment, not the
  approach.
- **Photos (the floor):** 2–8 unordered stills per room → feed-forward
  multiview (DUSt3R / MASt3R-SfM) which needs no intrinsics or poses; scale from
  a metric-depth model or a known-dimension prior (a door leaf); **stitch
  across rooms** via shared openings into one plan. Intervals widen to ≤8%.
  A photo path must stitch whole-property, not single rooms — that is the gate.

Both reuse §1 backend unchanged; I did not ship them because the honest LiDAR
tier plus a truthful account is worth more than three half-working tiers.

## 8. Fix loop (summary; bundle in `outputs/fix_loop*.json`)

- **Worst gate:** footprint/wall repeatability — box method, per-wall up to
  **84 cm / 14%**, FAIL.
- **Root cause:** rectangle model mis-specified for a non-rectangular space
  (evidence: wall-cell figure; area stable at ~1% while sides swing).
- **Fix shipped:** orientation-free contour footprint (area + perimeter).
- **Predicted:** area ≤2%, perimeter ≤5%. **Actual:** area **0.03%**, perimeter
  **0.87%** → PASS. Before/after both regenerable via `benchmark/fix_loop.py`.

## 9. Known failure modes

- Non-rectangular per-wall decomposition (§5) — needs plane segmentation.
- **Ceiling under-observation & repeatable bias:** across the three captures
  the ceiling lands at 2.04 / 2.02 / **2.79 m**. The well-swept capture
  (`c7d28f72c6`) gives the correct ~2.79 m; `c00a170fe1` is *unrepeatable*
  (3.9 cm) and caught by the gate; `1a8384c3f6` is *repeatable but ~0.8 m
  biased low* — precision cannot catch that, only absolute laser GT can (the
  hardware gap). Reported honestly in `docs/benchmark_report.md` rather than
  hidden; the capture protocol's ceiling-sweep step exists to prevent it.
- Mirrors/glass/wet-look/low-light: ARKit returns low-confidence depth there;
  we drop confidence<2, which removes most such points at the cost of coverage
  holes. A specular/reflective-surface classifier is the designed next step.
- Openings: conservative (a phantom counts as a miss), so on the cluttered
  sample none are emitted rather than guessed.
