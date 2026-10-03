#!/usr/bin/env python3
"""
Regenerate the whole benchmark across all captures under data/.
Writes per-capture JSON + plan + repeatability, and prints the summary table
that docs/benchmark_report.md reports.

    python benchmark/run_all.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmark"))

from repeatability import repeatability  # noqa: E402


def main():
    data = ROOT / "data"
    caps = [d for d in sorted(data.iterdir())
            if (d / "depth").is_dir() and (d / "odometry.csv").exists()]
    if not caps:
        print("no captures found under data/"); return

    rows = []
    for cap in caps:
        print(f"\n=== {cap.name} ===")
        subprocess.run([sys.executable, str(ROOT / "run.py"),
                        "--capture", str(cap), "--tier", "lidar",
                        "--out", str(ROOT / "outputs"), "--no-drift-ablation"],
                       check=True)
        doc = json.loads((ROOT / "outputs" / f"{cap.name}.json").read_text())
        rep = repeatability(str(cap))
        (ROOT / "outputs" / f"{cap.name}_repeatability.json").write_text(
            json.dumps(rep, indent=2))
        rows.append((cap.name,
                     doc["property_plan"]["footprint_area"]["value"],
                     doc["rooms"][0]["ceiling_height"]["value"],
                     rep["agreement"]["area_delta_pct"],
                     rep["agreement"]["ceiling_spread_m"] * 100))

    print("\n==== BENCHMARK SUMMARY ====")
    print(f"{'capture':14} {'area m2':>9} {'ceil m':>7} "
          f"{'area Δ%':>8} {'ceil cm':>8}")
    for name, area, ceil, ad, cs in rows:
        print(f"{name:14} {area:9.2f} {ceil:7.2f} {ad:8.2f} {cs:8.1f}")


if __name__ == "__main__":
    main()
