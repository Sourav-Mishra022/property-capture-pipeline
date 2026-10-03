"""
Video-tier feasibility probe
============================

Not a shipped tier — an honest experiment recording WHY the video tier is not
shipped from this environment (see technical_report.md §7).

It (1) scores every ~10th frame of a capture's rgb.mp4 by Laplacian variance
(a sharpness/texture proxy), (2) extracts the sharpest N, and (3) runs COLMAP
incremental SfM on them, reporting how many cameras register into a single
connected model.

On the provided `c00a170fe1` clip the frames are heavily motion-blurred
(sharpest Laplacian var ~28, median ~7) and SfM fragments into disconnected
sub-models (≈11/45 images max), which is why a feature-based video tier is not
viable here and the designed tier uses VIO poses + monocular metric depth
instead.

Run:  python benchmark/video_tier_probe.py data/c00a170fe1  [N]
Requires: pip install pycolmap
"""
import os
import sys
import tempfile

import cv2
import numpy as np


def main():
    cap_dir = sys.argv[1] if len(sys.argv) > 1 else "data/c00a170fe1"
    topN = int(sys.argv[2]) if len(sys.argv) > 2 else 45
    mp4 = os.path.join(cap_dir, "rgb.mp4")
    if not os.path.exists(mp4):
        print(f"no rgb.mp4 in {cap_dir} (video excluded from upload?)"); return

    cap = cv2.VideoCapture(mp4)
    scored, i = [], 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % 10 == 0:
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            scored.append((cv2.Laplacian(g, cv2.CV_64F).var(), i, f))
        i += 1
    cap.release()
    scored.sort(reverse=True)
    med = float(np.median([s[0] for s in scored])) if scored else 0
    print(f"scored {len(scored)} frames; sharpest Laplacian var "
          f"{scored[0][0]:.0f}, median {med:.0f}")

    try:
        import pycolmap
    except ImportError:
        print("pycolmap not installed; pip install pycolmap to run SfM step")
        return

    work = tempfile.mkdtemp(prefix="vprobe_")
    imgs = os.path.join(work, "imgs"); os.makedirs(imgs)
    for sc, idx, f in scored[:topN]:
        cv2.imwrite(os.path.join(imgs, f"{idx:06d}.jpg"), f)

    db = os.path.join(work, "db.db")
    out = os.path.join(work, "sparse"); os.makedirs(out)
    print(f"running COLMAP SfM on {min(topN, len(scored))} sharpest frames ...")
    pycolmap.extract_features(db, imgs)
    pycolmap.match_exhaustive(db)
    maps = pycolmap.incremental_mapping(db, imgs, out)
    if not maps:
        print("RESULT: 0 models — SfM failed to register any frames")
        return
    best = max(maps.values(), key=lambda m: m.num_reg_images())
    print(f"RESULT: {len(maps)} disconnected model(s); best registers "
          f"{best.num_reg_images()}/{min(topN, len(scored))} frames, "
          f"{best.num_points3D()} 3D points")
    if len(maps) > 1 or best.num_reg_images() < 0.6 * min(topN, len(scored)):
        print("VERDICT: fragmented/under-registered -> feature-based SfM not "
              "viable on this stream (motion blur). Use VIO poses + monocular "
              "metric depth (see technical_report.md §7).")


if __name__ == "__main__":
    main()
