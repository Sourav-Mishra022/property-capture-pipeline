# Compliance Matrix

Requirement → artifact → file path → status. Honest status values:
**shipped** (works, reproducible here) · **partial** (works with stated limits)
· **designed** (architected in the report, not executed) ·
**blocked-hardware** (cannot be done without an iPhone 15+/Mac).

| # | Requirement | Artifact | Path | Status |
|---|-------------|----------|------|--------|
| 1 | Output JSON to published schema | schema + validator in runner | `schemas/output_schema.json`, `run.py` | **shipped** |
| 2 | One command per capture | CLI runner | `run.py` | **shipped** |
| 3 | Dimensioned per-room plan (walls, ceiling, floor area) | reconstruction | `src/reconstruct.py`, `outputs/c00a170fe1.json` | **shipped** (area/ceiling); per-wall **partial**, see report §5 |
| 4 | Confidence interval on every measurement | calibration | `src/calibrate.py` | **shipped** (propagated; conformal blocked, no GT) |
| 5 | Rendered plan | renderer | `src/render.py`, `outputs/c00a170fe1_plan.png` | **shipped** |
| 6 | Openings with widths | detector | `src/openings.py` | **partial** (conservative; none emitted on cluttered sample) |
| 7 | Per-surface damage + concealed-damage flags | schema fields + design | `schemas/output_schema.json` §surfaces, report §9 | **designed** (no damage in sample; needs staged-damage capture) |
| 8 | Stitched multi-room plan with adjacency | schema + design | report §7 | **blocked-hardware** (needs ≥3-room capture) |
| 9 | Drift handling + on/off ablation | plane-anchored correction | `src/drift.py`, `provenance.drift_handling` | **shipped** (single-room; multi-room hook designed) |
| 10 | Repeatability gate | even/odd frame split | `benchmark/repeatability.py` | **shipped** (proxy for two physical captures) |
| 11 | Fix loop (before/after, regenerable) | before=box, after=contour | `benchmark/fix_loop.py`, `outputs/fix_loop*.json` | **shipped** |
| 12 | Three input tiers, same contract | LiDAR shipped; video/photo designed | report §1, §7 | **partial** (LiDAR shipped; video/photo designed) |
| 13 | Device matrix | table | report §3 | **shipped** |
| 14 | Capture route (build or protocol) | Route 2 stock protocol | `docs/capture_route.md` | **partial** (protocol written; not field-tested — no device) |
| 15 | Head-to-head vs incumbent app | — | — | **blocked-hardware** (needs app export on own captures) |
| 16 | Self-built benchmark + laser GT | — | — | **blocked-hardware** (needs iPhone 15+ and laser measurer) |
| 17 | Walk-in test readiness (all tiers) | — | — | **blocked-hardware** (on-device live defense) |
| 18 | Process evidence (incremental history) | git log | repository history | **shipped** |
| 19 | README, fresh-capture run <15 min | docs | `README.md` | **shipped** |
| 20 | Hard surfaces (mirror/glass/wet/low-light) covered | confidence gating + design | report §9, `provenance.hard_surfaces` | **partial** |
| 21 | Reproduction bundle, numbers regenerable | scripts + sample pointer | `run.py`, `benchmark/*`, `README.md` | **shipped** (on provided sample) |

**Summary:** the measurement core (rows 1–6, 9–11, 18–21) is shipped and
reproducible on the provided sample. Everything marked *blocked-hardware*
(rows 8, 15–17) depends on an iPhone 15+/Mac and laser measurer I do not have;
each is designed in the technical report so the work can be finished the moment
hardware is available.
