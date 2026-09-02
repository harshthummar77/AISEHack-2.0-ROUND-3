"""Stage 2 -- inter-pass co-registration, radiometric cross-checks, and
per-plot zonal statistics for all 966 Sokhda farm plots x 6 acquisitions.

Notes on two data realities handled here:
  * The AOI is slightly wider than one Capella stripmap swath, so a straight
    NW-SE swath edge clips the north-west corner of the farm block. Plots there
    are observed on a subset of the six dates; they are kept with an explicit
    per-plot observation count rather than discarded.
  * The 2025-10-29 pass is right-looking from the opposite azimuth (318 deg vs
    135 deg). Unconstrained phase correlation against a left-looking reference
    locks onto a spurious peak, so the search is bounded to the few metres of
    residual expected after the reference-height solution.

Outputs
  pipeline/out/plot_stats_long.csv   one row per (plot, date)
  pipeline/out/plot_stats_wide.csv   one row per plot
  pipeline/out/coreg.json            shifts + radiometric diagnostics
"""
import json, os, sys, warnings
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.transform import Affine
from scipy import ndimage
from shapely.geometry import MultiPolygon
from matplotlib.path import Path as MPath

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarlib import UTM43N, to_db

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(BASE, "pipeline", "geo")
OUT = os.path.join(BASE, "pipeline", "out")
os.makedirs(OUT, exist_ok=True)

EROSION_M = 4.0
MIN_PIX = 12
BLOCK = 5                # 5 x 2 m = 10 m structural blocks
MAX_SHIFT_PX = 8         # bounded co-registration search (+-16 m)

man = json.load(open(os.path.join(GEO, "manifest.json")))
RES = man["res"]; W, H = man["width"], man["height"]
tr = Affine(*man["transform"])
dates = [s["date"] for s in man["scenes"]]
tags = [s["tag"] for s in man["scenes"]]
print(f"grid {W}x{H} @ {RES} m; ref height {man['ref_height_m']} m; scenes {dates}\n")

stack, nesz, subc = [], [], []
for t in tags:
    with rasterio.open(os.path.join(GEO, f"gamma0_{t}.tif")) as ds:
        stack.append(ds.read(1).astype(np.float32))
    with rasterio.open(os.path.join(GEO, f"nesz_{t}.tif")) as ds:
        nesz.append(ds.read(1).astype(np.float32))
    sp = os.path.join(GEO, f"subcoh_{t}.tif")
    if os.path.exists(sp):
        with rasterio.open(sp) as ds:
            subc.append(ds.read(1).astype(np.float32))
stack = np.stack(stack); nesz = np.stack(nesz)
subc = np.stack(subc) if len(subc) == len(tags) else None
print(f"sub-look coherence layers: {'loaded' if subc is not None else 'absent'}")
finite0 = np.isfinite(stack)

# ------------------------------------------------------------ co-registration
def prep(a):
    d = to_db(a).astype(np.float32)
    med = np.nanmedian(d)
    d = np.where(np.isfinite(d), d, med)
    return ndimage.gaussian_filter(d - med, 2.0)


def bounded_shift(ref, mov, maxpx):
    """Sub-pixel translation of `mov` relative to `ref`, searched only within
    +-maxpx of zero lag (guards against spurious far-field correlation peaks)."""
    F = np.fft.rfft2(ref) * np.conj(np.fft.rfft2(mov))
    F /= np.maximum(np.abs(F), 1e-12)                  # phase correlation
    cc = np.fft.irfft2(F, s=ref.shape).real
    cc = np.fft.fftshift(cc)
    cy, cx = ref.shape[0] // 2, ref.shape[1] // 2
    win = cc[cy - maxpx:cy + maxpx + 1, cx - maxpx:cx + maxpx + 1]
    p = np.unravel_index(np.argmax(win), win.shape)
    peak = float(win[p])
    dy, dx = p[0] - maxpx, p[1] - maxpx
    # parabolic sub-pixel refinement
    def sub(v0, vm, vp):
        den = (vm - 2 * v0 + vp)
        return 0.0 if abs(den) < 1e-12 else 0.5 * (vm - vp) / den
    if 0 < p[0] < win.shape[0] - 1:
        dy += sub(win[p], win[p[0] - 1, p[1]], win[p[0] + 1, p[1]])
    if 0 < p[1] < win.shape[1] - 1:
        dx += sub(win[p], win[p[0], p[1] - 1], win[p[0], p[1] + 1])
    return np.array([-dy, -dx]), peak / (win.std() + 1e-12)


REF = 0
ref_img = prep(stack[REF])
shifts, coreg = [], {"reference": dates[REF], "res_m": RES,
                     "max_search_px": MAX_SHIFT_PX, "shifts": []}
for i in range(len(tags)):
    if i == REF:
        sh, snr = np.array([0.0, 0.0]), np.inf
    else:
        sh, snr = bounded_shift(ref_img, prep(stack[i]), MAX_SHIFT_PX)
    shifts.append(sh)
    coreg["shifts"].append({"date": dates[i], "d_row_px": float(sh[0]),
                            "d_col_px": float(sh[1]),
                            "d_east_m": float(-sh[1] * RES),
                            "d_north_m": float(-sh[0] * RES),
                            "peak_snr": float(snr)})
    print(f"  coreg {dates[i]}: dE={-sh[1]*RES:+6.2f} m  dN={-sh[0]*RES:+6.2f} m  "
          f"(|d|={np.hypot(*sh)*RES:.2f} m, snr={snr:.1f})")

for i, sh in enumerate(shifts):
    if np.abs(sh).max() > 1e-6:
        a = stack[i].copy(); bad = ~np.isfinite(a)
        a[bad] = np.nanmedian(a)
        a = ndimage.shift(a, sh, order=1, mode="nearest")
        m = ndimage.shift(bad.astype(np.float32), sh, order=1, mode="nearest")
        stack[i] = np.where(m > 0.5, np.nan, a)
        n = nesz[i].copy(); nb = ~np.isfinite(n); n[nb] = np.nanmedian(n)
        nesz[i] = ndimage.shift(n, sh, order=1, mode="nearest")
        if subc is not None:
            c = subc[i].copy(); cb = ~np.isfinite(c); c[cb] = np.nanmedian(c)
            c = ndimage.shift(c, sh, order=1, mode="nearest")
            m2 = ndimage.shift(cb.astype(np.float32), sh, order=1, mode="nearest")
            subc[i] = np.where(m2 > 0.5, np.nan, c)

db = to_db(stack)

# -------------------------------------- radiometric cross-check, stable targets
# hard targets = pixels in the top 0.5% of every scene (built-up, walls, poles)
thr = np.array([np.nanpercentile(db[i], 99.5) for i in range(len(dates))])
persistent = np.all(np.isfinite(db), axis=0) & np.all(db > thr[:, None, None], axis=0)
print(f"\n  persistent hard targets: {persistent.sum()} px "
      f"({100*persistent.mean():.3f}% of grid)")
coreg["radiometric"] = []
base = float(np.nanmedian(db[REF][persistent])) if persistent.sum() > 50 else np.nan
for i, d in enumerate(dates):
    m = float(np.nanmedian(db[i][persistent])) if persistent.sum() > 50 else np.nan
    coreg["radiometric"].append({"date": d, "median_db_stable": m,
                                 "delta_vs_ref_db": float(m - base),
                                 "scene_median_db": float(np.nanmedian(db[i])),
                                 "incidence": man["scenes"][i]["incidence"]})
    print(f"  {d} (inc {man['scenes'][i]['incidence']:4.1f}): hard-target median "
          f"{m:6.2f} dB (D={m-base:+5.2f})   scene median {np.nanmedian(db[i]):6.2f} dB")
json.dump(coreg, open(os.path.join(OUT, "coreg.json"), "w"), indent=1)

# ------------------------------------------------------------------- plots
gdf = gpd.read_file(os.path.join(BASE, "DATA", "Farm_boundaries_shp",
                                 "Farm_boundaries_shp", "Sokhda_Farms.shp")).to_crs(UTM43N)
gdf["geometry"] = gdf.geometry.buffer(0)
gdf["plot_id"] = gdf["FID"].astype(int)
gdf["area_ha"] = gdf.geometry.area / 1e4
print(f"\n  {len(gdf)} plots, {gdf.area_ha.sum():.1f} ha total")

inv_tr = ~tr
SPECKLE_DB = 5.57
ENL2 = 2.9                       # effective looks in one 2 m cell

rows = []
for pid, geom, area in zip(gdf["plot_id"], gdf.geometry, gdf.area_ha):
    core, level = geom.buffer(-EROSION_M), "eroded4m"
    if core.is_empty or core.area < MIN_PIX * RES * RES:
        core, level = geom.buffer(-1.0), "eroded1m"
    if core.is_empty or core.area < MIN_PIX * RES * RES:
        core, level = geom, "full"
    if core.is_empty or core.area <= 0:
        core, level = geom.centroid.buffer(3.0), "centroid3m"

    minx, miny, maxx, maxy = core.bounds
    c0, r0 = inv_tr * (minx, maxy); c1, r1 = inv_tr * (maxx, miny)
    c0, r0 = max(int(np.floor(c0)) - 1, 0), max(int(np.floor(r0)) - 1, 0)
    c1, r1 = min(int(np.ceil(c1)) + 1, W), min(int(np.ceil(r1)) + 1, H)
    if c1 <= c0 or r1 <= r0:
        for d in dates:
            rows.append({"plot_id": pid, "date": d, "area_ha": area,
                         "n_pix": 0, "mask_level": "offgrid"})
        continue

    yy, xx = np.mgrid[r0:r1, c0:c1]
    X = tr.c + (xx + 0.5) * RES; Y = tr.f - (yy + 0.5) * RES
    pts = np.column_stack([X.ravel(), Y.ravel()])
    polys = core.geoms if isinstance(core, MultiPolygon) else [core]
    mask = np.zeros(X.shape, dtype=bool)
    for p in polys:
        mask |= MPath(np.asarray(p.exterior.coords)).contains_points(pts).reshape(X.shape)
        for ring in p.interiors:
            mask &= ~MPath(np.asarray(ring.coords)).contains_points(pts).reshape(X.shape)
    if mask.sum() == 0:                       # sub-pixel polygon: take nearest cell
        cc, rr = inv_tr * (core.centroid.x, core.centroid.y)
        rr, cc = int(rr) - r0, int(cc) - c0
        if 0 <= rr < mask.shape[0] and 0 <= cc < mask.shape[1]:
            mask[max(rr - 1, 0):rr + 2, max(cc - 1, 0):cc + 2] = True
            level = "nn3x3"

    n_in_poly = int(mask.sum())
    sub = stack[:, r0:r1, c0:c1]; subn = nesz[:, r0:r1, c0:c1]
    subf = finite0[:, r0:r1, c0:c1]
    for i, d in enumerate(dates):
        v = sub[i][mask]; nv = subn[i][mask]
        ok = np.isfinite(v) & (v > 0)
        v, nv = v[ok], nv[ok]
        n = v.size
        rec = {"plot_id": pid, "date": d, "area_ha": area, "n_pix": int(n),
               "n_poly_pix": n_in_poly, "mask_level": level,
               "cover_frac": float(subf[i][mask].mean()) if n_in_poly else 0.0}
        if n >= 5:
            vdb = 10 * np.log10(v)
            rec.update({
                "g0_lin": float(v.mean()),
                "g0_db": float(10 * np.log10(v.mean())),
                "g0_db_med": float(np.median(vdb)),
                "g0_db_std": float(vdb.std()),
                "g0_db_p10": float(np.percentile(vdb, 10)),
                "g0_db_p90": float(np.percentile(vdb, 90)),
                "cv_lin": float(v.std() / v.mean()),
                "frac_below_nesz": float((v < nv).mean()),
            })
            if subc is not None:
                sc = subc[i, r0:r1, c0:c1][mask]
                sc = sc[np.isfinite(sc)]
                if sc.size >= 5:
                    rec["subcoh"] = float(sc.mean())
                    rec["subcoh_p90"] = float(np.percentile(sc, 90))
            hh = (mask.shape[0] // BLOCK) * BLOCK; ww = (mask.shape[1] // BLOCK) * BLOCK
            if hh >= BLOCK and ww >= BLOCK:
                mm = mask[:hh, :ww] & np.isfinite(sub[i][:hh, :ww])
                arr = np.where(mm, sub[i][:hh, :ww], 0.0)
                cnt = mm.reshape(hh // BLOCK, BLOCK, ww // BLOCK, BLOCK).sum(axis=(1, 3))
                tot = arr.reshape(hh // BLOCK, BLOCK, ww // BLOCK, BLOCK).sum(axis=(1, 3))
                good = cnt >= BLOCK * BLOCK * 0.8
                if good.sum() >= 4:
                    bm = tot[good] / cnt[good]
                    bm = bm[bm > 0]
                    if bm.size >= 4:
                        obs = float((10 * np.log10(bm)).std())
                        floor = SPECKLE_DB / np.sqrt(ENL2 * BLOCK * BLOCK)
                        rec["struct_db"] = float(np.sqrt(max(obs ** 2 - floor ** 2, 0.0)))
                        rec["n_blocks"] = int(bm.size)
        rows.append(rec)

long = pd.DataFrame(rows)
long.to_csv(os.path.join(OUT, "plot_stats_long.csv"), index=False)

nobs = long.groupby("plot_id").g0_db.apply(lambda s: s.notna().sum())
print(f"\nwrote plot_stats_long.csv {long.shape}")
print("\nobservations per plot:")
print(nobs.value_counts().sort_index().to_string())
print(f"\nplots with all 6 dates: {(nobs == 6).sum()}   >=4 dates: {(nobs >= 4).sum()}   "
      f"0 dates: {(nobs == 0).sum()}")
print("\nmask level used:")
print(long.groupby('plot_id').mask_level.first().value_counts().to_string())
print("\nmean gamma0 (dB) per date over plots:")
print(long.groupby("date").g0_db.agg(["count", "mean", "std", "min", "max"]).to_string())
print("\nmean struct_db per date:")
print(long.groupby("date").struct_db.agg(["count", "mean", "median"]).to_string())

keep = ["g0_db", "g0_db_med", "g0_db_std", "cv_lin", "struct_db",
        "frac_below_nesz", "n_pix", "cover_frac", "subcoh", "subcoh_p90"]
keep = [k for k in keep if k in long.columns]
wide = long.pivot_table(index="plot_id", columns="date", values=keep)
wide.columns = [f"{a}_{b.replace('-', '')}" for a, b in wide.columns]
wide = long.groupby("plot_id")[["area_ha"]].first().join(wide)
wide["n_obs"] = nobs
wide["mask_level"] = long.groupby("plot_id").mask_level.first()
wide.to_csv(os.path.join(OUT, "plot_stats_wide.csv"))
print(f"\nwrote plot_stats_wide.csv {wide.shape}")
