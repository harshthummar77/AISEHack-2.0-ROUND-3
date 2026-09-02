"""Solve the RPC reference height by minimising mis-registration against
Capella's own DEM-geocoded GEO preview.

A constant height error dh displaces a geocoded pixel in the ground-range
direction by dh / tan(theta), with the sign set by the look direction. The
five left-looking passes and the single right-looking pass (2025-10-29)
therefore shift in opposite senses -- which is exactly what is observed, and
is what makes the height identifiable from the imagery alone.
"""
import json, os, sys
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import reproject, Resampling
from skimage.registration import phase_cross_correlation
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarlib import find_scenes, make_grid, geocode_scene, to_db, UTM43N

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(BASE, "pipeline", "geo")
man = json.load(open(os.path.join(GEO, "manifest.json")))

RES = 10.0
tr2 = Affine(*man["transform"])
bounds = (tr2.c, tr2.f - man["height"] * man["res"],
          tr2.c + man["width"] * man["res"], tr2.f)
tr, W, H = make_grid(bounds, RES)
print(f"coarse grid {W}x{H} @ {RES} m\n")

scenes = find_scenes(os.path.join(BASE, "DATA"))

# reference: Capella's own geocoded preview, on the coarse grid
refs = {}
for s in scenes:
    a = np.zeros((H, W), dtype=np.float32)
    with rasterio.open(s.preview) as ds:
        reproject(rasterio.band(ds, 1), a, src_transform=ds.transform, src_crs=ds.crs,
                  dst_transform=tr, dst_crs=UTM43N, resampling=Resampling.average)
    b = np.where(a > 0, np.log10(np.maximum(a, 1)), np.nan)
    b = np.nan_to_num(b - np.nanmedian(b))
    refs[s.date] = ndimage.gaussian_filter(b, 1.0)

HEIGHTS = [-60, -50, -40, -30, -25, -20, -15, -10, 0, 10]
res = {}
for s in scenes:
    print(f"--- {s.date}  (inc={s.inc_centre:.1f}, look={s.look})")
    row = []
    for h in HEIGHTS:
        g, frac, _ = geocode_scene(s, tr, W, H, RES, height_m=h, ss=2,
                                   chunk_rows=64, verbose=False)
        d = to_db(np.where(frac > 0.75, g, np.nan))
        d = np.nan_to_num(d - np.nanmedian(d))
        d = ndimage.gaussian_filter(d, 1.0)
        sh, err, _ = phase_cross_correlation(refs[s.date], d, upsample_factor=10,
                                             normalization=None)
        mag = float(np.hypot(*sh) * RES)
        m = np.isfinite(d) & np.isfinite(refs[s.date])
        r = float(np.corrcoef(d[m], refs[s.date][m])[0, 1])
        row.append((h, mag, sh[0] * RES, sh[1] * RES, r))
        print(f"    h={h:+5.0f} m  |shift|={mag:6.1f} m  (dN={-sh[0]*RES:+6.1f}, dE={-sh[1]*RES:+6.1f})  corr={r:+.3f}")
    res[s.date] = row

print("\n" + "=" * 70)
print("Best height per scene (min |shift|):")
best = []
for d, row in res.items():
    h, mag, _, _, r = min(row, key=lambda t: t[1])
    best.append(h)
    print(f"  {d}: h={h:+.0f} m  |shift|={mag:.1f} m  corr={r:+.3f}")
print(f"\nmedian best height = {np.median(best):+.1f} m (ellipsoidal)")
json.dump({"heights": HEIGHTS, "per_scene": {k: [list(map(float, t)) for t in v] for k, v in res.items()},
           "best_median": float(np.median(best))},
          open(os.path.join(GEO, "height_solution.json"), "w"), indent=1)
