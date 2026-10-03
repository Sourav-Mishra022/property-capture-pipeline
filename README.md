# Property Capture Pipeline

Handheld-capture → dimensioned, stitched floor plan with a confidence interval on
every measurement. One output contract (`schemas/output_schema.json`) produced from
three input tiers (LiDAR / video / photos).

## Status
Built against the provided sample capture (ARKit LiDAR, single room). See
`docs/technical_report.md` for the device matrix, calibration analysis, and an
honest account of what is demonstrated vs. designed vs. hardware-blocked.

## Run (one command per capture)
```
python run.py --capture data/<capture_id> --tier lidar --out outputs/
```

## Install
```
pip install -r requirements.txt
```
