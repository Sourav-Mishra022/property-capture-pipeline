#!/usr/bin/env python3
"""
One command per capture:

    python run.py --capture data/<capture_id> --tier lidar --out outputs/

Produces outputs/<capture_id>.json (to schemas/output_schema.json) and
outputs/<capture_id>_plan.png. The live path always runs; see --help.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from io_capture import Capture          # noqa: E402
from reconstruct import reconstruct     # noqa: E402
from render import render_plan          # noqa: E402
from schema_io import build_output      # noqa: E402
from openings import detect_openings    # noqa: E402
from drift import drift_ablation        # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture", required=True, help="path to a capture folder")
    ap.add_argument("--tier", default="lidar", choices=["lidar", "video", "photos"])
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--frame-stride", type=int, default=6)
    ap.add_argument("--no-drift-ablation", action="store_true",
                    help="skip the on/off drift ablation (faster)")
    args = ap.parse_args()

    cap_path = Path(args.capture)
    capture_id = cap_path.name
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    command = (f"python run.py --capture {args.capture} "
               f"--tier {args.tier} --out {args.out}")

    print(f"[1/5] loading capture {capture_id} ({args.tier}) ...")
    cap = Capture(cap_path)

    print(f"[2/5] reconstructing from {len(cap.frames)} frames ...")
    recon = reconstruct(cap, frame_stride=args.frame_stride)
    recon._frames = cap.frames

    print("[3/5] detecting openings ...")
    openings = detect_openings(recon)

    drift = {"method": "none_single_room"}
    if not args.no_drift_ablation:
        print("[4/5] drift ablation (correction on vs off) ...")
        drift = drift_ablation(cap, frame_stride=args.frame_stride)
    else:
        print("[4/5] drift ablation skipped")

    print("[5/5] writing outputs ...")
    doc = build_output(recon, capture_id, args.tier, command,
                       openings=openings, drift=drift)
    # enforce the output contract on every run
    try:
        import jsonschema
        schema = json.loads((Path(__file__).parent / "schemas"
                             / "output_schema.json").read_text())
        jsonschema.validate(doc, schema)
        print("      schema: valid ✓")
    except ImportError:
        print("      schema: jsonschema not installed, skipping validation")
    (out / f"{capture_id}.json").write_text(json.dumps(doc, indent=2))
    render_plan(recon, str(out / f"{capture_id}_plan.png"), openings=openings,
                title=f"{capture_id} ({args.tier})")

    # console summary
    r = doc["rooms"][0]
    print("\n==== SUMMARY ====")
    print(f"ceiling height : {r['ceiling_height']['value']:.3f} m  "
          f"[{r['ceiling_height']['ci']['low']:.3f}, {r['ceiling_height']['ci']['high']:.3f}]"
          f"  ({r['ceiling_height']['bias_or_noise']})")
    print(f"floor area     : {r['floor_area']['value']:.2f} m²  "
          f"[{r['floor_area']['ci']['low']:.2f}, {r['floor_area']['ci']['high']:.2f}]")
    for w in r["walls"]:
        ci = w["length"]["ci"]
        print(f"  {w['wall_id']}: {w['length']['value']:.2f} m "
              f"[{ci['low']:.2f}, {ci['high']:.2f}]")
    print(f"openings       : {len(r['openings'])}")
    print(f"drift          : {drift.get('method')}")
    print(f"\nwrote {out/f'{capture_id}.json'} and {out/f'{capture_id}_plan.png'}")


if __name__ == "__main__":
    main()
