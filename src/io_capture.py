"""
Capture IO + geometry core
===========================

Loads an ARKit-style LiDAR capture and provides the geometry needed to turn
per-frame depth + pose into a single world-frame point cloud.

Capture layout (one folder per capture), as provided in the sample data:
    camera_matrix.csv   3x3 pinhole intrinsics at RGB resolution (1920x1440)
    odometry.csv        per-frame 6-DoF pose: x,y,z + quaternion qx,qy,qz,qw
                        (plus per-frame fx,fy,cx,cy, also at RGB resolution)
    depth/NNNNNN.png     256x192 uint16 depth in millimetres
    confidence/NNNNNN.png 256x192 uint8 ARKit confidence {0=low,1=med,2=high}
    rgb.mp4             1920x1440 RGB, one frame per depth frame

Design decisions worth defending:
- Depth is stored at 256x192 but intrinsics are given at 1920x1440, so we
  scale intrinsics by (depth_w / rgb_w). This is exact because ARKit's depth
  map shares the colour camera's optical centre and is a pure downscale.
- ARKit's world frame is gravity-aligned: +Y points up, against gravity.
  We rely on this so that "floor" and "ceiling" are planes of constant Y and
  the floor plan is the X-Z projection. This removes a whole pose-estimation
  step and is the single biggest reason the LiDAR tier is accurate.
- Pose in odometry is world_from_camera (camera-to-world). ARKit camera
  convention: +X right, +Y up, +Z toward the viewer (i.e. camera looks down
  its own -Z). We keep that convention end to end.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

DEPTH_W, DEPTH_H = 256, 192
RGB_W, RGB_H = 1920, 1440


@dataclass
class Frame:
    idx: int
    pose_world_cam: np.ndarray  # 4x4 camera-to-world
    # per-frame intrinsics at RGB res; scaled to depth res on demand
    fx: float
    fy: float
    cx: float
    cy: float


class Capture:
    """Lazy reader over a capture folder."""

    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self.K_rgb = self._load_intrinsics(self.folder / "camera_matrix.csv")
        self.frames = self._load_odometry(self.folder / "odometry.csv")
        self.depth_dir = self.folder / "depth"
        self.conf_dir = self.folder / "confidence"
        self._depth_files = sorted(self.depth_dir.glob("*.png"))
        # Keep only frames that have a matching depth file.
        have = {int(p.stem) for p in self._depth_files}
        self.frames = [f for f in self.frames if f.idx in have]

    # ---- loaders -------------------------------------------------------
    @staticmethod
    def _load_intrinsics(path: Path) -> np.ndarray:
        rows = []
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append([float(x) for x in line.split(",")])
        K = np.array(rows, dtype=np.float64)
        assert K.shape == (3, 3), f"expected 3x3 intrinsics, got {K.shape}"
        return K

    @staticmethod
    def _load_odometry(path: Path) -> list[Frame]:
        frames: list[Frame] = []
        with open(path) as fh:
            reader = csv.DictReader(fh, skipinitialspace=True)
            # normalise header whitespace
            reader.fieldnames = [c.strip() for c in reader.fieldnames]
            for row in reader:
                row = {k.strip(): (v.strip() if v else v) for k, v in row.items()}
                idx = int(row["frame"])
                t = np.array([float(row["x"]), float(row["y"]), float(row["z"])])
                q = np.array(
                    [float(row["qx"]), float(row["qy"]),
                     float(row["qz"]), float(row["qw"])]
                )
                R = quat_to_rot(q)
                T = np.eye(4)
                T[:3, :3] = R
                T[:3, 3] = t
                frames.append(
                    Frame(
                        idx=idx,
                        pose_world_cam=T,
                        fx=float(row["fx"]),
                        fy=float(row["fy"]),
                        cx=float(row["cx"]),
                        cy=float(row["cy"]),
                    )
                )
        return frames

    # ---- per-frame access ---------------------------------------------
    def depth_m(self, idx: int) -> np.ndarray:
        """Depth in metres, shape (H, W). 0 = no return."""
        arr = np.asarray(Image.open(self.depth_dir / f"{idx:06d}.png")).astype(np.float32)
        return arr / 1000.0  # mm -> m

    def confidence(self, idx: int) -> np.ndarray:
        return np.asarray(Image.open(self.conf_dir / f"{idx:06d}.png")).astype(np.uint8)

    def depth_intrinsics(self, f: Frame) -> tuple[float, float, float, float]:
        """Scale RGB-resolution intrinsics down to the 256x192 depth grid."""
        s = DEPTH_W / RGB_W  # == DEPTH_H / RGB_H, verified equal for this device
        return f.fx * s, f.fy * s, f.cx * s, f.cy * s


# ---- rotation math -----------------------------------------------------
def quat_to_rot(q: np.ndarray) -> np.ndarray:
    """Quaternion (qx,qy,qz,qw) -> 3x3 rotation. Hamilton convention (ARKit)."""
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w),     2 * (x * z + y * w)],
        [2 * (x * y + z * w),     1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w),     2 * (y * z + x * w),     1 - 2 * (x * x + y * y)],
    ])


def backproject(depth: np.ndarray, conf: np.ndarray, fx, fy, cx, cy,
                min_conf: int = 1, stride: int = 1,
                z_min: float = 0.1, z_max: float = 5.0):
    """
    Backproject a depth image to camera-frame 3D points.

    Returns (points_cam Nx3, confidence N,). Pixels below `min_conf`, with no
    return, or outside [z_min, z_max] are dropped. ARKit depth pixel (u,v)
    maps to a camera ray with +Z forward; we flip to ARKit's camera frame
    (camera looks down -Z, +Y up) at the end so poses apply cleanly.
    """
    H, W = depth.shape
    vs, us = np.mgrid[0:H:stride, 0:W:stride]
    us = us.ravel(); vs = vs.ravel()
    z = depth[vs, us]
    c = conf[vs, us]
    keep = (c >= min_conf) & (z > z_min) & (z < z_max)
    us, vs, z, c = us[keep], vs[keep], z[keep], c[keep]
    # pinhole backprojection (image +X right, +Y down, +Z into scene)
    x = (us - cx) * z / fx
    y = (vs - cy) * z / fy
    pts = np.stack([x, y, z], axis=1)
    # convert image-frame (+Y down, +Z forward) to ARKit camera frame
    # (+Y up, +Z backward): negate Y and Z.
    pts[:, 1] *= -1.0
    pts[:, 2] *= -1.0
    return pts, c


def to_world(pts_cam: np.ndarray, pose_world_cam: np.ndarray) -> np.ndarray:
    R = pose_world_cam[:3, :3]
    t = pose_world_cam[:3, 3]
    return pts_cam @ R.T + t
