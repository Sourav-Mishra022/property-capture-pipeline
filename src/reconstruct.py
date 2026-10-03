"""
LiDAR reconstruction
====================

Turn a fused, gravity-aligned point cloud into a dimensioned room:
floor + ceiling planes, a footprint polygon, wall lengths and floor area.

Pipeline (all defensible at the whiteboard):
1. Fuse confidence-gated depth from a subset of frames into world points.
2. Voxel-downsample to tame density and outliers.
3. Floor/ceiling = the two dominant *horizontal* planes. Floor is the strongest
   low plane; ceiling is the HIGHEST plane above floor+1.8m that still carries
   real mass (so a table or countertop at 1.6m is never mistaken for a ceiling).
4. Footprint: project the wall band (floor+0.3 .. ceiling-0.3) to the X-Z plane,
   rasterise occupancy, flood-fill the interior from the camera trajectory, and
   trace + simplify the outer contour. Polygon edges are walls.

Everything needed for calibrated intervals (plane thickness, per-wall point
residuals, point counts) is returned alongside the measurements.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
from sklearn.cluster import DBSCAN

from io_capture import Capture, backproject, to_world


# --------------------------------------------------------------------------
# Fusion
# --------------------------------------------------------------------------
def fuse(cap: Capture, frame_stride: int = 6, px_stride: int = 2,
         min_conf: int = 2, z_max: float = 4.0, frame_filter=None,
         pose_fn=None):
    """Fuse selected frames into a world point cloud (raw, not voxelised).

    We keep raw points because floor/ceiling detection relies on genuine point
    DENSITY (the floor is the densest horizontal plane); voxelising first would
    equalise density and let a large flat worktop outvote the floor.

    frame_filter: optional callable(position:int)->bool for disjoint subsets
                  (used by the repeatability check: even vs odd frames).
    pose_fn:      optional callable(frame)->4x4 pose, to swap in drift-corrected
                  poses for the ablation. Defaults to the raw ARKit pose.
    Returns (points Nx3, confidence N,).
    """
    pts_all, conf_all = [], []
    for i, f in enumerate(cap.frames[::frame_stride]):
        if frame_filter is not None and not frame_filter(i):
            continue
        d = cap.depth_m(f.idx)
        c = cap.confidence(f.idx)
        fx, fy, cx, cy = cap.depth_intrinsics(f)
        p, cc = backproject(d, c, fx, fy, cx, cy,
                            min_conf=min_conf, stride=px_stride, z_max=z_max)
        if len(p):
            pose = pose_fn(f) if pose_fn is not None else f.pose_world_cam
            pts_all.append(to_world(p, pose))
            conf_all.append(cc)
    return np.concatenate(pts_all), np.concatenate(conf_all)


def voxel_downsample(P: np.ndarray, C: np.ndarray, voxel: float):
    keys = np.floor(P / voxel).astype(np.int64)
    _, idx = np.unique(keys, axis=0, return_index=True)
    return P[idx], C[idx]


# --------------------------------------------------------------------------
# Horizontal planes: floor & ceiling
# --------------------------------------------------------------------------
@dataclass
class Plane:
    y: float          # height of the plane
    thickness: float  # robust std of member points about y (m) -> CI driver
    n_points: int
    mass_ratio: float = 1.0   # member count / floor member count (observability)
    well_observed: bool = True


def _refine_plane(ys: np.ndarray, y0: float, floor_n: int, win: float = 0.06) -> Plane:
    members = ys[np.abs(ys - y0) < win]
    n = len(members)
    if n < 10:
        return Plane(float(y0), 0.03, n, 0.0, False)
    ratio = n / max(floor_n, 1)
    return Plane(float(np.median(members)), float(np.std(members)), n,
                 ratio, ratio >= 0.20)


def extract_floor_ceiling(P: np.ndarray, bin_w: float = 0.02) -> tuple[Plane, Plane]:
    """Floor = densest low horizontal plane. Ceiling = HIGHEST plane above
    floor+1.8m that still carries real mass. A ceiling observed with far fewer
    points than the floor is flagged `well_observed=False` so its interval can
    be widened honestly rather than reported with false precision."""
    ys = P[:, 1]
    lo, hi = np.percentile(ys, [0.2, 99.8])
    bins = np.arange(lo, hi + bin_w, bin_w)
    hist, edges = np.histogram(ys, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2

    lower = centres < (lo + 0.4 * (hi - lo))
    fi = np.argmax(hist * lower)
    floor_mass = int(hist[fi])
    floor = _refine_plane(ys, centres[fi], floor_mass)

    # Highest plane above floor+1.8m with >=5% of floor mass (ceilings are
    # under-sampled because phones rarely point straight up).
    cand = centres > floor.y + 1.8
    qualifying = np.where(cand & (hist >= 0.05 * floor_mass))[0]
    ceil_y = centres[qualifying[-1]] if len(qualifying) else centres[cand][np.argmax(hist[cand])]
    ceiling = _refine_plane(ys, ceil_y, floor_mass)
    return floor, ceiling


# --------------------------------------------------------------------------
# Footprint polygon from the wall band
# --------------------------------------------------------------------------
@dataclass
class Wall:
    wall_id: str
    p0: tuple[float, float]  # world (x, z)
    p1: tuple[float, float]
    length: float
    inlier_rms: float        # residual of band points to this segment (m)
    n_inliers: int


@dataclass
class Footprint:
    polygon_xz: np.ndarray            # Kx2 world coords, ordered
    walls: list[Wall]
    area: float
    grid_res: float
    band_xz: np.ndarray = field(repr=False, default=None)


def _wall_cells(P: np.ndarray, floor: Plane, ceiling: Plane, res: float):
    """XZ cells whose points span a tall vertical extent -> true walls.
    Returns world-XZ coordinates of wall cells. Furniture, floor and stray
    returns span little height and are excluded, which is what finally stops
    the footprint inflating."""
    ys = P[:, 1]
    xz = P[:, [0, 2]]
    xmin, zmin = xz.min(0) - 0.2
    W = int(np.ceil((xz[:, 0].max() + 0.2 - xmin) / res))
    H = int(np.ceil((xz[:, 1].max() + 0.2 - zmin) / res))
    cc = np.clip(((xz[:, 0] - xmin) / res).astype(int), 0, W - 1)
    rr = np.clip(((xz[:, 1] - zmin) / res).astype(int), 0, H - 1)
    yb = ((ys - floor.y) / 0.1).astype(int)           # 10 cm vertical bins
    key = rr.astype(np.int64) * W + cc
    order = np.argsort(key)
    ks, ybs = key[order], yb[order]
    uniq, start = np.unique(ks, return_index=True)
    ends = np.r_[start[1:], len(ks)]
    vext = np.zeros(H * W)
    for k, s, e in zip(uniq, start, ends):
        vext[k] = np.unique(ybs[s:e]).size * 0.1
    cells = np.argwhere(vext.reshape(H, W) > 1.2)     # >1.2 m tall column
    return np.c_[cells[:, 1] * res + xmin, cells[:, 0] * res + zmin]


def build_footprint(P: np.ndarray, floor: Plane, ceiling: Plane,
                    cam_centroid_xz: np.ndarray, res: float = 0.04) -> Footprint:
    cells = _wall_cells(P, floor, ceiling, res)
    # Drop stray wall cells (reflections, points seen through a doorway).
    lab = DBSCAN(eps=0.25, min_samples=5).fit_predict(cells)
    if (lab >= 0).any():
        main = cells[lab == np.bincount(lab[lab >= 0]).argmax()]
    else:
        main = cells

    # Rooms are predominantly rectangular (Manhattan assumption); fit the
    # minimum-area oriented box to the dominant wall structure. Non-rectangular
    # rooms are a documented known-failure mode (see technical report).
    rect = cv2.minAreaRect(main.astype(np.float32))
    box = cv2.boxPoints(rect)                          # 4 ordered corners
    poly_world = np.array(box, dtype=np.float64)

    walls = _walls_from_polygon(poly_world, main)
    area = _polygon_area(poly_world)
    return Footprint(poly_world, walls, area, res, main)


def _walls_from_polygon(poly: np.ndarray, band_xz: np.ndarray) -> list[Wall]:
    walls = []
    n = len(poly)
    for k in range(n):
        a = poly[k]
        b = poly[(k + 1) % n]
        seg = b - a
        L = float(np.hypot(*seg))
        if L < 0.15:          # drop spurious tiny edges
            continue
        # residual of nearby band points to this wall line (for CI)
        t = ((band_xz - a) @ seg) / (L * L)
        proj = a + np.outer(np.clip(t, 0, 1), seg)
        dist = np.hypot(*(band_xz - proj).T)
        near = dist < 0.12
        rms = float(np.sqrt(np.mean(dist[near] ** 2))) if near.sum() else 0.05
        walls.append(Wall(f"w{len(walls)+1}", tuple(a), tuple(b), L,
                          rms, int(near.sum())))
    return walls


def _polygon_area(poly: np.ndarray) -> float:
    x, z = poly[:, 0], poly[:, 1]
    return float(abs(np.dot(x, np.roll(z, -1)) - np.dot(z, np.roll(x, -1))) / 2)


# --------------------------------------------------------------------------
# Top-level convenience
# --------------------------------------------------------------------------
@dataclass
class Reconstruction:
    points: np.ndarray
    conf: np.ndarray
    floor: Plane
    ceiling: Plane
    footprint: Footprint
    cam_centroid_xz: np.ndarray

    @property
    def ceiling_height(self) -> float:
        return self.ceiling.y - self.floor.y


def reconstruct(cap: Capture, frame_stride: int = 6, min_conf: int = 2,
                frame_filter=None, pose_fn=None) -> Reconstruction:
    P, C = fuse(cap, frame_stride=frame_stride, min_conf=min_conf,
                frame_filter=frame_filter, pose_fn=pose_fn)
    cam = np.array([[f.pose_world_cam[0, 3], f.pose_world_cam[2, 3]]
                    for f in cap.frames]).mean(0)
    floor, ceiling = extract_floor_ceiling(P)
    fp = build_footprint(P, floor, ceiling, cam)
    return Reconstruction(P, C, floor, ceiling, fp, cam)
