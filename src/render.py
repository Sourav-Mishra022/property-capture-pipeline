"""Top-down floor-plan renderer."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def render_plan(recon, out_path: str, openings=None, title: str = "Floor plan"):
    fp = recon.footprint
    poly = np.vstack([fp.polygon_xz, fp.polygon_xz[:1]])

    fig, ax = plt.subplots(figsize=(7, 7))
    # wall cells (faint) for context
    if fp.band_xz is not None and len(fp.band_xz):
        ax.scatter(fp.band_xz[:, 0], fp.band_xz[:, 1], s=1, c="#c9d6e5",
                   alpha=0.5, linewidths=0, label="wall points")
    ax.plot(poly[:, 0], poly[:, 1], "-", color="#1f3a5f", lw=2.5, label="footprint")

    # label only the major edges to avoid clutter on irregular footprints
    major = sorted(fp.walls, key=lambda w: w.length, reverse=True)[:6]
    for w in major:
        mid = (np.array(w.p0) + np.array(w.p1)) / 2
        ax.annotate(f"{w.length:.2f} m", mid, color="#1f3a5f",
                    fontsize=9, ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))

    # camera trajectory
    cam = np.array([[f.pose_world_cam[0, 3], f.pose_world_cam[2, 3]]
                    for f in recon_frames(recon)])
    if len(cam):
        ax.plot(cam[:, 0], cam[:, 1], "-", color="#e07b39", lw=1, alpha=0.7,
                label="camera path")

    if openings:
        for op in openings:
            c = op["center_xz"]
            ax.plot(c[0], c[1], "s", color="#2e8b57", ms=10)
            ax.annotate(f"{op['type']}\n{op['width']:.2f} m", (c[0], c[1]),
                        color="#2e8b57", fontsize=8, ha="center", va="bottom")

    ax.set_aspect("equal")
    ax.set_xlabel("X (m)"); ax.set_ylabel("Z (m)")
    ax.set_title(f"{title}  |  area {fp.area:.1f} m²  |  ceiling {recon.ceiling_height:.2f} m")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, ls=":", alpha=0.4)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


# small indirection so render doesn't import Capture types
def recon_frames(recon):
    return getattr(recon, "_frames", [])
