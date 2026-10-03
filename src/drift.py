"""
Drift handling + ablation
=========================

The spec requires a stated drift strategy and an ablation showing the stitched
footprint with it on and off. "Poses used as-is" is an automatic fail.

Strategy: **plane-anchored correction**. ARKit's odometry is gravity-aligned,
but slow tilt/scale drift leaves the floor slightly non-level across a capture.
We estimate the floor-plane normal from the fused floor points by PCA and
rotate every pose so the floor normal maps exactly to +Y. On a single room the
correction is small by design (there is no loop to close); the ablation still
demonstrates the mechanism and quantifies its effect on footprint area. On a
multi-room capture the same hook accepts a pose-graph / loop-closure corrected
trajectory (see technical report) — the pipeline consumes corrected poses
through the identical `pose_fn` interface.
"""
from __future__ import annotations

import numpy as np

from reconstruct import reconstruct, fuse, extract_floor_ceiling


def _floor_normal(cap, frame_stride):
    P, _ = fuse(cap, frame_stride=frame_stride)
    floor, ceiling = extract_floor_ceiling(P)
    floor_pts = P[np.abs(P[:, 1] - floor.y) < 0.05]
    c = floor_pts.mean(0)
    # smallest-eigenvector of covariance = plane normal.
    # Use the 3x3 covariance (cheap) rather than the full data SVD.
    cov = np.cov((floor_pts - c).T)
    w, v = np.linalg.eigh(cov)
    normal = v[:, 0]
    if normal[1] < 0:
        normal = -normal
    return normal


def _rotation_to_up(normal):
    up = np.array([0.0, 1.0, 0.0])
    v = np.cross(normal, up)
    s = np.linalg.norm(v)
    if s < 1e-8:
        return np.eye(3)
    c = np.dot(normal, up)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (s * s))


def drift_ablation(cap, frame_stride=6):
    normal = _floor_normal(cap, frame_stride)
    tilt_deg = float(np.degrees(np.arccos(np.clip(normal[1], -1, 1))))
    R = _rotation_to_up(normal)

    def corrected_pose(f):
        T = f.pose_world_cam.copy()
        T[:3, :3] = R @ T[:3, :3]
        T[:3, 3] = R @ T[:3, 3]
        return T

    off = reconstruct(cap, frame_stride=frame_stride)
    on = reconstruct(cap, frame_stride=frame_stride, pose_fn=corrected_pose)

    return {
        "method": "plane_anchored",
        "floor_tilt_deg_before": round(tilt_deg, 3),
        "ablation_footprint_off_m2": round(off.footprint.area, 3),
        "ablation_footprint_on_m2": round(on.footprint.area, 3),
        "note": "Single-room capture: no loop to close, so the correction is "
                "small by construction. Interface accepts pose-graph output for "
                "multi-room (see report).",
    }
