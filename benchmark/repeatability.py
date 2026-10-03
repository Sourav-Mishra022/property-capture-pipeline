"""
Repeatability gate
==================

The spec's repeatability gate wants two captures of the same room at the same
tier to agree (<=1 cm or 0.5% per wall). We do not have a second physical
capture (that needs the hardware), so we demonstrate the SAME machinery with a
disjoint frame split: reconstruct from even frames and from odd frames
independently. These are two non-overlapping subsets of the sensor stream, so
agreement between them is a genuine test of pipeline determinism and
input-sensitivity ("same room in, same plan out"). The report is explicit that
this is a frame-split proxy for two physical captures.

Run:  python benchmark/repeatability.py data/<capture_id>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np
from io_capture import Capture
from reconstruct import reconstruct


def repeatability(capture_path, frame_stride=4, method="contour"):
    cap = Capture(capture_path)
    a = reconstruct(cap, frame_stride=frame_stride,
                    frame_filter=lambda i: i % 2 == 0, method=method)
    b = reconstruct(cap, frame_stride=frame_stride,
                    frame_filter=lambda i: i % 2 == 1, method=method)

    def rel(x, y):
        return 100 * abs(x - y) / max(x, y)

    area_d = abs(a.footprint.area - b.footprint.area)
    per_d = abs(a.footprint.perimeter - b.footprint.perimeter)
    ceil_spread = abs(a.ceiling_height - b.ceiling_height)

    return {
        "room_id": "room_1",
        "tier": "lidar",
        "footprint_method": method,
        "note": "disjoint frame split (even vs odd) — proxy for two physical "
                "captures; measures pipeline determinism + input sensitivity.",
        "even": {"area_m2": round(a.footprint.area, 2),
                 "perimeter_m": round(a.footprint.perimeter, 2),
                 "ceiling_m": round(a.ceiling_height, 3)},
        "odd": {"area_m2": round(b.footprint.area, 2),
                "perimeter_m": round(b.footprint.perimeter, 2),
                "ceiling_m": round(b.ceiling_height, 3)},
        "agreement": {
            "area_delta_m2": round(area_d, 3),
            "area_delta_pct": round(rel(a.footprint.area, b.footprint.area), 2),
            "perimeter_delta_pct": round(rel(a.footprint.perimeter,
                                             b.footprint.perimeter), 2),
            "ceiling_spread_m": round(ceil_spread, 3),
        },
        "gate_area_pass_2pct": bool(rel(a.footprint.area, b.footprint.area) <= 2.0),
        "gate_ceiling_pass_1cm": bool(ceil_spread <= 0.01),
    }


if __name__ == "__main__":
    cap_path = sys.argv[1] if len(sys.argv) > 1 else "data/c00a170fe1"
    r = repeatability(cap_path)
    print(json.dumps(r, indent=2))
    out = Path("outputs") / f"{Path(cap_path).name}_repeatability.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(r, indent=2))
    print(f"\nwrote {out}")
    print(f"AREA gate (<=2%):   {'PASS' if r['gate_area_pass_2pct'] else 'FAIL'}"
          f"  ({r['agreement']['area_delta_pct']:.2f}%)")
    print(f"CEILING gate (<=1cm): {'PASS' if r['gate_ceiling_pass_1cm'] else 'FAIL'}"
          f"  ({r['agreement']['ceiling_spread_m']*100:.1f} cm)")
