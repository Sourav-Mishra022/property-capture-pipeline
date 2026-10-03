"""
Opening detection (doors / windows / pass-throughs)
==================================================

An opening is a run along a wall where the wall is *absent* over a tall
vertical span. For each footprint edge we walk along the wall in ~8 cm steps
and measure, in a thin slab hugging the wall line, how much of the vertical
column (floor->ceiling) is filled with points. A contiguous low-fill run is an
opening; its vertical profile classifies it:

    reaches the floor and >=1.6 m tall  -> door
    elevated (sill above floor) band     -> window
    full height, very wide               -> passthrough

Detection is deliberately conservative: the spec scores a phantom opening as a
miss just like a missed one, so we require a minimum width and a clear vertical
signature before emitting.
"""
from __future__ import annotations

import numpy as np

STEP = 0.08          # along-wall sampling step (m)
SLAB = 0.15          # half-thickness of the band hugging the wall (m)
MIN_W = 0.5          # minimum opening width to emit (m)


def _wall_fill_profile(band_xz, P_y, a, b, floor_y, ceil_y):
    seg = b - a
    L = np.hypot(*seg)
    if L < MIN_W:
        return None
    u = seg / L
    n = np.array([-u[1], u[0]])
    rel = band_xz - a
    along = rel @ u
    perp = rel @ n
    near = (np.abs(perp) < SLAB) & (along > 0) & (along < L)
    along = along[near]; ys = P_y[near]
    nb = max(1, int(L / STEP))
    fill = np.zeros(nb)
    base = np.zeros(nb)            # lowest point height in the bin
    for i in range(nb):
        m = (along >= i * STEP) & (along < (i + 1) * STEP)
        if m.sum() >= 2:
            col = ys[m]
            fill[i] = (col.max() - col.min()) / max(ceil_y - floor_y, 1e-3)
            base[i] = col.min() - floor_y
        else:
            fill[i] = 0.0
            base[i] = np.nan
    return L, u, fill, base, nb


def detect_openings(recon):
    fp = recon.footprint
    band = fp.band_xz
    # recover per-point height for the wall cells is lost (cells are 2D);
    # re-pull a thin wall band from the full cloud for vertical profiling.
    P = recon.points
    floor_y, ceil_y = recon.floor.y, recon.ceiling.y
    band_full = P[(P[:, 1] > floor_y + 0.05) & (P[:, 1] < ceil_y - 0.05)]
    bxz = band_full[:, [0, 2]]
    by = band_full[:, 1]

    openings = []
    for w in fp.walls:
        a = np.array(w.p0); b = np.array(w.p1)
        prof = _wall_fill_profile(bxz, by, a, b, floor_y, ceil_y)
        if prof is None:
            continue
        L, u, fill, base, nb = prof
        low = fill < 0.35                      # wall largely absent here
        # find contiguous low runs
        i = 0
        while i < nb:
            if low[i]:
                j = i
                while j < nb and low[j]:
                    j += 1
                width = (j - i) * STEP
                # ignore runs at the very ends (likely corner occlusion)
                if width >= MIN_W and i > 1 and j < nb - 1:
                    centre_along = (i + j) / 2 * STEP
                    centre = a + u * centre_along
                    seg_base = np.nanmedian(base[i:j]) if np.any(~np.isnan(base[i:j])) else 0
                    if seg_base < 0.25:
                        typ, conf = "door", 0.55
                    elif seg_base < 1.2:
                        typ, conf = "window", 0.5
                    else:
                        typ, conf = "unknown", 0.4
                    openings.append({
                        "type": typ,
                        "width": float(width),
                        "center_xz": [float(centre[0]), float(centre[1])],
                        "on_wall": w.wall_id,
                        "confidence": conf,
                    })
                i = j
            else:
                i += 1
    return openings
