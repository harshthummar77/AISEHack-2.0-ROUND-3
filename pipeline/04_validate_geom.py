"""Validate the RPC forward model + incidence-angle solution against the
metadata that Capella ships with each product (225 GCPs, centre incidence)."""
import os, sys
import numpy as np
import rasterio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarlib import find_scenes, RPC

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DATA")
scenes = find_scenes(ROOT)
print(f"{len(scenes)} scenes\n")

for s in scenes:
    with rasterio.open(s.slc) as ds:
        rpc = RPC(ds.rpcs.to_gdal())
        gcps, gcrs = ds.get_gcps()
    lon = np.array([g.x for g in gcps])
    lat = np.array([g.y for g in gcps])
    z   = np.array([g.z for g in gcps])
    row = np.array([g.row for g in gcps])
    col = np.array([g.col for g in gcps])

    ln, sm = rpc.forward(lon, lat, z)
    dl, ds_ = ln - row, sm - col
    rms_l = float(np.sqrt(np.mean(dl**2)))
    rms_s = float(np.sqrt(np.mean(ds_**2)))

    # incidence angle at the image centre vs. the value in the metadata
    inc = np.degrees(s.incidence_per_column())
    inc_mid = inc[s.cols // 2]

    print(f"{s.date}  inc_meta={s.inc_centre:7.3f}  inc_model={inc_mid:7.3f} "
          f"(d={inc_mid - s.inc_centre:+.3f} deg)  range {inc.min():.2f}-{inc.max():.2f}")
    print(f"            RPC vs {len(gcps)} GCPs: RMS line={rms_l:.4f}px  samp={rms_s:.4f}px  "
          f"max|d|={max(abs(dl).max(), abs(ds_).max()):.3f}px")
    print(f"            GCP z: {z.min():.1f}..{z.max():.1f} m   RPC HEIGHT_OFF={rpc.height_off:.1f} m")
    print(f"            NESZ: peak={s.nesz_peak:.2f} dB, "
          f"per-col {10*np.log10(s.nesz_per_column()).min():.2f}..{10*np.log10(s.nesz_per_column()).max():.2f} dB")
    print()
