"""Validate the RPC geocoding against Capella's own geocoded GEO preview and
sanity-check the absolute radiometry (bright-target tail, NESZ margin)."""
import json, os, sys
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import reproject, Resampling
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from skimage.registration import phase_cross_correlation
from scipy import ndimage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarlib import find_scenes, to_db, UTM43N

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(BASE, "pipeline", "geo")
FIG = os.path.join(BASE, "pipeline", "fig")
os.makedirs(FIG, exist_ok=True)

man = json.load(open(os.path.join(GEO, "manifest.json")))
tr = Affine(*man["transform"]); W, H = man["width"], man["height"]
scenes = {s.date: s for s in find_scenes(os.path.join(BASE, "DATA"))}

print("=" * 78)
print("A. ABSOLUTE RADIOMETRY  (gamma0, dB)")
print("=" * 78)
for s in man["scenes"]:
    with rasterio.open(os.path.join(GEO, f"gamma0_{s['tag']}.tif")) as ds:
        g = ds.read(1)
    d = to_db(g)
    d = d[np.isfinite(d)]
    q = np.percentile(d, [1, 5, 25, 50, 75, 90, 99, 99.9, 99.99])
    print(f"{s['date']} inc={s['incidence']:.1f}  n={d.size/1e6:.1f}M")
    print("   pct  1/5/25/50/75/90/99/99.9/99.99 = " + " ".join(f"{x:7.2f}" for x in q))
    print(f"   max={d.max():.2f} dB   mean(lin)->{10*np.log10(np.mean(10**(d/10))):.2f} dB"
          f"   NESZ~{s['nesz_peak']:.1f} dB   frac<NESZ={s['frac_below_nesz']*100:.2f}%")

print()
print("=" * 78)
print("B. GEOCODING CHECK vs CAPELLA GEO PREVIEW  (independent product)")
print("=" * 78)
for s in man["scenes"]:
    sc = scenes[s["date"]]
    with rasterio.open(os.path.join(GEO, f"gamma0_{s['tag']}.tif")) as ds:
        mine = ds.read(1)
    prev = np.zeros((H, W), dtype=np.float32)
    with rasterio.open(sc.preview) as ds:
        reproject(rasterio.band(ds, 1), prev,
                  src_transform=ds.transform, src_crs=ds.crs,
                  dst_transform=tr, dst_crs=UTM43N,
                  resampling=Resampling.average)

    a = to_db(mine); b = prev.astype(np.float32)
    ok = np.isfinite(a) & (b > 0)
    a2 = np.where(ok, a, np.nan); b2 = np.where(ok, b, np.nan)
    a2 = np.nan_to_num(a2 - np.nanmedian(a2)); b2 = np.nan_to_num(b2 - np.nanmedian(b2))
    a2 = ndimage.gaussian_filter(a2, 2.0); b2 = ndimage.gaussian_filter(b2, 2.0)
    sh, err, _ = phase_cross_correlation(b2, a2, upsample_factor=20, normalization=None)
    # correlation between my dB and the preview's 8-bit amplitude rendering
    m = ok & np.isfinite(a)
    r = np.corrcoef(a[m], np.log10(np.maximum(b[m], 1)))[0, 1]
    print(f"{s['date']}: shift vs Capella GEO = dRow {sh[0]:+.2f} px, dCol {sh[1]:+.2f} px "
          f"({-sh[1]*man['res']:+.1f} m E, {-sh[0]*man['res']:+.1f} m N)   corr(dB, log preview) = {r:.3f}")

    if s["date"] == man["scenes"][0]["date"]:
        fig, ax = plt.subplots(1, 2, figsize=(13, 6.5))
        sl = (slice(700, 1500), slice(900, 1700))
        ax[0].imshow(a[sl], cmap="gray", vmin=np.nanpercentile(a[sl], 2), vmax=np.nanpercentile(a[sl], 98))
        ax[0].set_title("This work: RPC-geocoded $\\gamma^0$ (2 m)")
        pv = b[sl]
        ax[1].imshow(pv, cmap="gray", vmin=np.percentile(pv[pv > 0], 2), vmax=np.percentile(pv[pv > 0], 98))
        ax[1].set_title("Capella GEO preview (resampled to same grid)")
        for x in ax: x.set_xticks([]); x.set_yticks([])
        fig.suptitle(f"Geocoding validation — {s['date']}")
        fig.tight_layout(); fig.savefig(os.path.join(FIG, "qc_geocoding.png"), dpi=130)
        print("   -> wrote fig/qc_geocoding.png")
