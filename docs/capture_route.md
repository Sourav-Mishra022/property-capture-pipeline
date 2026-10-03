# Capture Route & Device Matrix

## Chosen route: Route 2 (stock capture protocol)

A TestFlight/dev build (Route 1) needs a Mac + Apple Developer account, which I
do not have. Route 2 is a stock app plus a one-page protocol a non-engineer
follows. **Note:** the protocol below is written to the ARKit data contract the
pipeline consumes (the exact format of the provided sample — see below) but has
**not been field-tested on a device**, because I have no iPhone 15+. That is
the one honest gap in this route.

### App
**Stray Scanner** (iOS, App Store) — or any LiDAR logger that exports per-frame
depth, confidence, RGB and ARKit poses. The pipeline consumes exactly the
sample's layout:

```
<capture_id>/
  rgb.mp4               # 1920x1440, one frame per depth frame
  depth/NNNNNN.png      # 256x192, uint16 millimetres
  confidence/NNNNNN.png # 256x192, {0,1,2} ARKit confidence
  camera_matrix.csv     # 3x3 intrinsics at RGB resolution
  odometry.csv          # per-frame: frame,x,y,z,qx,qy,qz,qw,fx,fy,cx,cy
  imu.csv               # accel + gyro (not required by the pipeline)
```

### Protocol a non-engineer follows (literal)
1. **Install** Stray Scanner. Grant camera permission.
2. **Stand** in a doorway or corner so you can see two walls and the floor.
3. **Start** recording. Hold the phone at chest height, screen facing you.
4. **Walk** the perimeter of the room slowly (≈ one wall every 10 s), keeping
   the far wall and the floor-wall line in view. Sweep the phone up once per
   wall so the **ceiling** is seen (the sample under-images the ceiling — this
   step fixes that).
5. **Pass through** each doorway you want connected, then come back.
6. **Stop** after returning to where you started (this gives a loop to close).
7. **Export** the capture folder and hand it to the pipeline:
   `python run.py --capture <capture_id> --tier lidar`.
8. **Avoid:** mirrors and windows pointed at directly (stand at an angle),
   fast motion, and recordings over ~3 minutes per room.

If this page is ambiguous, the capture reflects that — e.g. skipping step 4's
ceiling sweep reproduces exactly the under-observed-ceiling failure documented
in the technical report.

## Device matrix

| Tier | Minimum device | Capture app | Pipeline status | Honest accuracy target |
|------|----------------|-------------|-----------------|------------------------|
| LiDAR | iPhone 15 **Pro**+ | Stray Scanner | **shipped** | area ≤2%, walls ≤2 cm when well-observed |
| Video | any iPhone 15+ | native camera | designed | ≤3% (metric from ARKit intrinsics) |
| Photos | any iPhone 15+ | native camera | designed | ≤8%, intervals widened; must stitch |

Accuracy numbers are **design targets honestly labelled**, not measured claims —
measuring them needs the laser-GT benchmark (hardware). The LiDAR tier's
*repeatability* (not absolute accuracy) is measured here: area 0.03% on the
even/odd split.
