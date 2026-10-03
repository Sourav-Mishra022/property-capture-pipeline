"""
Calibration / confidence intervals
==================================

Every reported measurement carries a 95% interval. We have NO laser ground
truth for the provided capture (building the specified benchmark needs an
iPhone 15+ and a laser measurer we do not have), so intervals here are
**propagated** from a sensor-noise model, not **conformal**. The output
labels them `method="propagated"` and the technical report is explicit that
empirical coverage is therefore unvalidated on this capture. The design goal
the spec rewards is kept: intervals widen honestly as the supporting data
thins (a sparsely observed ceiling gets a wide interval, not false precision).

Noise model (defensible at the whiteboard):
- Surface-location error of a horizontal plane:
      sigma = thickness / sqrt(n_eff)              (statistical)
            (+)  beta * range                      (systematic depth scale)
  n_eff is capped (correlated noise within a frame means raw N overstates
  independence). A plane flagged `well_observed=False` is additionally
  inflated by a sparsity factor.
- Wall length: endpoints inherit grid resolution + line-fit residual;
  length error propagates from both endpoints in quadrature.
- Floor area (rectangle a*b): relative errors of the two sides add in
  quadrature.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Z95 = 1.959963985

# sensor-model constants
N_EFF_CAP = 300          # independence cap for correlated per-frame noise
BETA_RANGE = 0.004       # 0.4% of range, systematic depth scale (ARKit-class)
TYPICAL_RANGE = 2.0      # m, representative capture distance for the sample


@dataclass
class Meas:
    value: float
    unit: str
    low: float
    high: float
    method: str = "propagated"
    note: str = ""

    def as_dict(self):
        d = {"value": round(self.value, 4), "unit": self.unit,
             "ci": {"low": round(self.low, 4), "high": round(self.high, 4),
                    "level": 0.95, "method": self.method}}
        if self.note:
            d["ci"]["note"] = self.note
        return d


def _plane_sigma(thickness: float, n: int, well_observed: bool,
                 mass_ratio: float) -> float:
    n_eff = min(max(n, 1), N_EFF_CAP)
    stat = thickness / np.sqrt(n_eff)
    syst = BETA_RANGE * TYPICAL_RANGE
    sigma = float(np.hypot(stat, syst))
    if not well_observed:
        # widen for thin data: the thinner vs the floor, the wider
        sigma *= float(np.clip(np.sqrt(0.20 / max(mass_ratio, 1e-3)), 1.0, 6.0))
    return sigma


def ceiling_height(floor, ceiling) -> Meas:
    sf = _plane_sigma(floor.thickness, floor.n_points, floor.well_observed, 1.0)
    sc = _plane_sigma(ceiling.thickness, ceiling.n_points,
                      ceiling.well_observed, ceiling.mass_ratio)
    sigma = float(np.hypot(sf, sc))
    h = ceiling.y - floor.y
    note = "" if ceiling.well_observed else "ceiling under-observed; interval widened"
    return Meas(h, "m", h - Z95 * sigma, h + Z95 * sigma, note=note)


def _endpoint_sigma(res: float, rms: float, n: int) -> float:
    n_eff = min(max(n, 1), N_EFF_CAP)
    return float(np.hypot(res, rms / np.sqrt(n_eff)))


def wall_length(wall, res: float) -> Meas:
    se = _endpoint_sigma(res, wall.inlier_rms, wall.n_inliers)
    sigma = np.sqrt(2) * se                     # two independent endpoints
    L = wall.length
    return Meas(L, "m", L - Z95 * sigma, L + Z95 * sigma)


def floor_area(walls, res: float, area: float) -> Meas:
    # rectangle: pick the two distinct side lengths
    lengths = sorted({round(w.length, 2) for w in walls})
    if len(lengths) >= 2:
        a, b = lengths[0], lengths[-1]
        wa = next(w for w in walls if round(w.length, 2) == a)
        wb = next(w for w in walls if round(w.length, 2) == b)
        ra = (Z95 * np.sqrt(2) * _endpoint_sigma(res, wa.inlier_rms, wa.n_inliers)) / a
        rb = (Z95 * np.sqrt(2) * _endpoint_sigma(res, wb.inlier_rms, wb.n_inliers)) / b
        rel = float(np.hypot(ra, rb))
    else:
        rel = 0.1
    return Meas(area, "m2", area * (1 - rel), area * (1 + rel))


def opening_width(width: float, res: float, edge_rms: float = 0.03) -> Meas:
    sigma = float(np.hypot(res, edge_rms)) * np.sqrt(2)
    return Meas(width, "m", width - Z95 * sigma, width + Z95 * sigma)
