"""Build the JSON output contract from a reconstruction."""
from __future__ import annotations

import datetime as dt

import calibrate as cal


def build_output(recon, capture_id: str, tier: str, command: str,
                 openings=None, drift=None, device: str = "sample-dataset"):
    fp = recon.footprint
    res = fp.grid_res

    walls_json = []
    for w in fp.walls:
        m = cal.wall_length(w, res)
        walls_json.append({"wall_id": w.wall_id,
                           "length": m.as_dict(),
                           "endpoints": [list(w.p0), list(w.p1)]})

    ch = cal.ceiling_height(recon.floor, recon.ceiling)
    fa = cal.floor_area(fp.area, fp.perimeter, res)

    openings_json = []
    for i, op in enumerate(openings or []):
        ow = cal.opening_width(op["width"], res)
        openings_json.append({
            "opening_id": f"o{i+1}",
            "type": op["type"],
            "width": ow.as_dict(),
            "on_wall": op.get("on_wall", ""),
            "detection_confidence": round(op.get("confidence", 0.5), 3),
        })

    surfaces = (
        [{"surface_id": "floor", "kind": "floor", "damage": []},
         {"surface_id": "ceiling", "kind": "ceiling", "damage": []}]
        + [{"surface_id": f"{w.wall_id}", "kind": "wall", "damage": []}
           for w in fp.walls]
    )

    room = {
        "room_id": "room_1",
        "floor_polygon": [[round(x, 3), round(z, 3)] for x, z in fp.polygon_xz],
        "walls": walls_json,
        "floor_area": fa.as_dict(),
        "ceiling_height": {**ch.as_dict(),
                           "bias_or_noise": ("within_gate" if recon.ceiling.well_observed
                                             else "unrepeatable")},
        "openings": openings_json,
        "surfaces": surfaces,
    }

    drift = drift or {"method": "none_single_room"}

    return {
        "schema_version": "0.1.0",
        "capture": {
            "capture_id": capture_id,
            "tier": tier,
            "device": device,
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "command": command,
        },
        "rooms": [room],
        "property_plan": {
            "footprint_area": fa.as_dict(),
            "footprint_perimeter_m": round(fp.perimeter, 3),
            "footprint_method": fp.method,
            "adjacency": [],
            "overlaps_detected": False,
            "rendered_plan_path": f"{capture_id}_plan.png",
        },
        "provenance": {
            "tier": tier,
            "drift_handling": drift,
            "calibration": {
                "interval_method": "propagated (sensor-noise model)",
                "coverage_observed": None,
                "note": "No laser ground truth available on this capture; "
                        "empirical coverage unvalidated. Intervals widen with "
                        "data sparsity by construction.",
            },
            "hard_surfaces": {
                "notes": "Low-confidence ARKit depth (conf<2) dropped, which "
                         "removes most mirror/glass/wet-look returns; see report.",
            },
        },
    }
