"""Did terrain-referenced geocoding actually improve the product?

Compares the new DEM-geocoded gamma0 against Capella's own DEM-geocoded GEO
previews, using the same metric as the earlier constant-height experiment
(10 m grid, log domain, mildly smoothed, at best alignment) so the two are
directly comparable.

Constant-height baseline from 12_solve_height.py, at its optimum of -20 m:
    2025-06-06 0.792 | 2025-06-19 0.744 | 2025-08-14 0.787
    2025-10-13 0.675 | 2025-10-29 0.830 | 2025-11-12 0.787
"""
import json, os, sys
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import reproject, Resampling
from scipy import ndimage
from skimage.registration import phase_cross_correlation

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarlib import find_scenes, to_db, UTM43N

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(BASE, "pipeline", "geo")
man = json.load(open(os.path.join(GEO, "manifest.json")))
tr = Affine(*man["transform"]); W, H = man["width"], man["height"]; RES = man["res"]

BASELINE = {"2025-06-06": 0.792, "2025-06-19": 0.744, "2025-08-14": 0.787,
            "2025-10-13": 0.675, "2025-10-29": 0.830, "2025-11-12": 0.787}

F = int(round(10.0 / RES))
W10, H10 = W // F, H // F
tr10 = Affine(10.0, 0, tr.c, 0, -10.0, tr.f)
scenes = {s.date: s for s in find_scenes(os.path.join(BASE, "DATA"))}

print(f"{'date':12s} {'corr const-h':>13s} {'corr DEM':>10s} {'change':>9s} {'shift(m)':>10s}")
print("-" * 60)
out = {}
for s in man["scenes"]:
    with rasterio.open(os.path.join(GEO, f"gamma0_{s['tag']}.tif")) as ds:
        g = ds.read(1)[:H10 * F, :W10 * F]
    blk = g.reshape(H10, F, W10, F)
    with np.errstate(invalid="ignore"):
        gm = np.nanmean(blk, axis=(1, 3))
    mine = to_db(gm)

    prev = np.zeros((H10, W10), np.float32)
    with rasterio.open(scenes[s["date"]].preview) as ds:
        reproject(rasterio.band(ds, 1), prev, src_transform=ds.transform, src_crs=ds.crs,
                  dst_transform=tr10, dst_crs=UTM43N, resampling=Resampling.average)
    ref = np.where(prev > 0, np.log10(np.maximum(prev, 1)), np.nan)

    a = ndimage.gaussian_filter(np.nan_to_num(mine - np.nanmedian(mine)), 1.0)
    b = ndimage.gaussian_filter(np.nan_to_num(ref - np.nanmedian(ref)), 1.0)
    sh, _, _ = phase_cross_correlation(b, a, upsample_factor=10, normalization=None)
    if np.abs(sh).max() > 0:
        a = ndimage.shift(a, sh, order=1, mode="nearest")
    m = np.isfinite(a) & np.isfinite(b) & (prev > 0)
    r = float(np.corrcoef(a[m], b[m])[0, 1])
    base = BASELINE[s["date"]]
    out[s["date"]] = {"corr_dem": round(r, 3), "corr_constant_height": base,
                      "residual_shift_m": round(float(np.hypot(*sh) * 10.0), 2)}
    print(f"{s['date']:12s} {base:13.3f} {r:10.3f} {r-base:+9.3f} "
          f"{np.hypot(*sh)*10:10.2f}")

mn_b = np.mean(list(BASELINE.values()))
mn_d = np.mean([v["corr_dem"] for v in out.values()])
print("-" * 60)
print(f"{'mean':12s} {mn_b:13.3f} {mn_d:10.3f} {mn_d-mn_b:+9.3f}")
json.dump(out, open(os.path.join(GEO, "dem_validation.json"), "w"), indent=1)
print("\nwrote geo/dem_validation.json")
