"""Build the public Kaggle notebook containing the full Round-3 pipeline.

The notebook embeds the real module sources (sarlib, cropmodel) and the real
pipeline stages, so what is published is what produced the numbers.
"""
import json, os, re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(BASE, "pipeline")
DEL = os.path.join(BASE, "SUBMISSION")
os.makedirs(DEL, exist_ok=True)


def src(name, strip_main=True):
    t = open(os.path.join(WORK, name), encoding="utf-8").read()
    return t.rstrip() + "\n"


def md(s):
    # nbformat accepts a plain string for `source`; splitting on "\n" without
    # keeping the newlines silently concatenates every line into one.
    return {"cell_type": "markdown", "metadata": {}, "source": s.strip()}


def code(s):
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [], "source": s.strip()}


C = []

C.append(md("""
# Six Looks, One Harvest — final kharif 2025 yield forecast for Sokhda, Vadodara

**ANRF AISEHack 2.0 · Round 3 · Team 8bit** (Harsh Thummar, Viraj Suhagiya)

966 farm plots · 447.5 ha · Capella X-band HH stripmap SLC, six passes:
**6 Jun / 19 Jun / 14 Aug / 13 Oct / 29 Oct / 12 Nov 2025**

This notebook runs the complete chain from the raw complex SLC to the plot-level
and village-level yield forecasts. Everything geometric and radiometric is
implemented from the Capella extended metadata and the RPC model — no SNAP, no
ISCE, no `gdalwarp`.

**Pipeline**

1. Scene inventory, calibration constants, per-range-sample incidence angle
2. RPC00B forward model, validated against the 225 GCPs in each product
3. Solve the reference height from the imagery (it is *not* the RPC default)
4. Geocode all six passes to a common 2 m UTM-43N γ⁰ grid
5. Bounded inter-pass co-registration and radiometric cross-checks
6. Per-plot zonal statistics for 966 plots × 6 dates
7. Agronomic knowledge base for Vadodara kharif (external data, all sourced)
8. Crop labels: carry-forward, plus an independent 6-pass re-derivation
9. Independent validation against same-day Sentinel-2 NDVI
10. Yield forecast, Monte-Carlo uncertainty, village aggregation

**Key design decision.** X-band HH saturates early against LAI, and on this
village the median Δγ⁰ at peak season is *negative* relative to bare soil —
a closed canopy attenuates a rough tilled surface more than it scatters at HH.
Inverting X-band for absolute biomass would therefore be indefensible. The model
instead uses phenological **timing**, late-season **retention**, and within-field
**evenness**, and anchors the absolute level to district statistics.
"""))

C.append(md("## 0 · Environment and paths"))
C.append(code('''
import os, sys, json, glob, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

# Works on Kaggle (competition dataset attached) or locally with a DATA/ folder.
CANDIDATES = [
    "/kaggle/input/anrf-aise-hack-2-0-round-3-sar-crop-yield-forecasting",
    "/kaggle/input",
]
# also walk upward from the working directory, so the notebook runs unchanged
# from a subfolder of a local checkout
_p = os.path.abspath(".")
for _ in range(5):
    CANDIDATES += [os.path.join(_p, "DATA"), _p]
    _p = os.path.dirname(_p)
DATA_ROOT = None
for c in CANDIDATES:
    if os.path.isdir(c) and glob.glob(os.path.join(c, "**", "CAPELLA_*"), recursive=True):
        hits = glob.glob(os.path.join(c, "**", "CAPELLA_*"), recursive=True)
        DATA_ROOT = os.path.dirname(sorted(hits)[0])
        break
assert DATA_ROOT, "could not locate the Capella scenes"
FARM_SHP = sorted(glob.glob(os.path.join(DATA_ROOT, "**", "*Farms.shp"), recursive=True))[0]
VILL_SHP = sorted(glob.glob(os.path.join(DATA_ROOT, "**", "*Village.shp"), recursive=True))[0]
WORKDIR = "/kaggle/working" if os.path.isdir("/kaggle/working") else "."
GEO = os.path.join(WORKDIR, "geo"); OUT = os.path.join(WORKDIR, "out")
FIG = os.path.join(WORKDIR, "figures")
for d in (GEO, OUT, FIG): os.makedirs(d, exist_ok=True)
print("DATA_ROOT :", DATA_ROOT)
print("farms     :", FARM_SHP)
print("scenes    :", len([p for p in glob.glob(os.path.join(DATA_ROOT, "CAPELLA_*")) if os.path.isdir(p)]))
'''))

C.append(md("""## 1 · SAR core — calibration, geometry, geocoding

Capella delivers SLC as `beta_nought` with `calibration: full`, so

$$\\beta^0 = (|DN|\\cdot s)^2, \\qquad \\sigma^0 = \\beta^0\\sin\\theta, \\qquad
\\gamma^0 = \\beta^0\\tan\\theta$$

γ⁰ is used throughout because the six passes span **28.69°–35.24°** incidence and
γ⁰ is, to first order, the incidence-invariant quantity for volume scatterers.
The local incidence angle per range sample comes from a spherical-Earth solution
on the product state vectors, pinned to the metadata centre value."""))
C.append(code(src("sarlib.py")))

C.append(md("""## 2 · Scene inventory and geometry validation

The RPC implementation is checked against the 225 ground control points that
Capella ships inside each product. Agreement is exact to the printed precision,
which means any later mis-registration is a *height* problem, not a model
problem — and that is exactly what we find next."""))
C.append(code('''
scenes = find_scenes(DATA_ROOT)
import rasterio
rows = []
for s in scenes:
    with rasterio.open(s.slc) as ds:
        rpc = RPC(ds.rpcs.to_gdal()); gcps, _ = ds.get_gcps()
    lon = np.array([g.x for g in gcps]); lat = np.array([g.y for g in gcps])
    z = np.array([g.z for g in gcps]); r = np.array([g.row for g in gcps])
    c = np.array([g.col for g in gcps])
    ln, sm = rpc.forward(lon, lat, z)
    inc = np.degrees(s.incidence_per_column())
    rows.append({"date": s.date, "incidence_deg": round(s.inc_centre, 2), "look": s.look,
                 "orbit": s.orbit, "azimuth": round(s.az, 1),
                 "rows": s.rows, "cols": s.cols,
                 "nesz_peak_dB": round(s.nesz_peak, 2),
                 "inc_near_far": f"{inc.min():.2f}-{inc.max():.2f}",
                 "rpc_rms_line_px": round(float(np.sqrt(np.mean((ln - r) ** 2))), 5),
                 "rpc_rms_samp_px": round(float(np.sqrt(np.mean((sm - c) ** 2))), 5)})
inv = pd.DataFrame(rows)
print(inv.to_string(index=False))
'''))

C.append(md("""## 3 · Terrain referencing — DEM and the datum solution

Capella's RPCs expect **ellipsoidal** heights; the Copernicus GLO-30 DEM stores
**orthometric** (EGM2008) heights. The 225 GCPs embedded in each product carry
ellipsoidal z, so the datum shift `N = z_GCP − H_DEM` is solved rather than assumed.

The within-scene scatter of that difference is the check on the method: had the
GCP z values been a synthetic multi-layer height grid rather than terrain
samples, the scatter would be tens of metres and the solve would be meaningless.

Terrain cannot be neglected here — the farm block carries **26.6 m of relief**,
which a flat-earth height converts into up to **46 m of ground-range
displacement** at 30° incidence, comparable to the width of a whole field."""))
C.append(code(src("13_dem.py").split('if __name__ == "__main__":')[0]
              .replace('sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\nfrom sarlib import find_scenes, RPC, UTM43N\n\nBASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\nWORK = os.path.join(BASE, "pipeline")\nDEM_LOCAL = os.path.join(WORK, "copdem_N22E073.tif")',
                       'WORK = WORKDIR\nDEM_LOCAL = os.path.join(WORK, "copdem_N22E073.tif")')
              + '''

scenes = find_scenes(DATA_ROOT)
DEM_SAMPLE, _dem_ds = make_dem_sampler(fetch_dem())
offs = []
for s in scenes:
    with rasterio.open(s.slc) as d:
        gcps, _ = d.get_gcps(); rpc = RPC(d.rpcs.to_gdal())
    lon = np.array([g.x for g in gcps]); lat = np.array([g.y for g in gcps])
    z = np.array([g.z for g in gcps])
    row = np.array([g.row for g in gcps]); col = np.array([g.col for g in gcps])
    ho = DEM_SAMPLE(lon, lat); ok = np.isfinite(ho)
    diff = z[ok] - ho[ok]; offs.append(diff.mean())
    ln1, sm1 = rpc.forward(lon, lat, ho + diff.mean())
    ln2, sm2 = rpc.forward(lon, lat, np.full_like(lon, -20.0))
    e1 = float(np.sqrt(np.mean((ln1-row)**2 + (sm1-col)**2)))
    e2 = float(np.sqrt(np.mean((ln2-row)**2 + (sm2-col)**2)))
    print(f"{s.date}: N = {diff.mean():8.3f} m  within-scene sd = {diff.std():5.2f} m   "
          f"RPC round-trip RMSE: DEM {e1:6.3f} px vs constant-height {e2:7.3f} px")
GEOID_N = float(np.mean(offs))
print(f"\\nadopted geoid offset N = {GEOID_N:.3f} m "
      f"(scene-to-scene sd {np.std(offs):.3f} m)")
'''))

C.append(md("""## 3b · Why a constant height is not good enough

An earlier version of this work geocoded at a single constant height, solved by
minimising misregistration against Capella's own DEM-geocoded previews. All six
passes agreed on −20 m ellipsoidal with a residual global shift ≤2.8 m, which is
why the error was not obvious: **a global shift metric recovers the mean
alignment and leaves the spatially varying terrain component untouched.**

The cell below reproduces that scan for comparison. Terrain-referenced
geocoding raises mean correlation against Capella's product from 0.769 to 0.840,
improving on every pass, and — the sharper diagnostic — collapses the
co-registration residual of the single **right-looking** 29 Oct pass from 2.54 m
to 0.12 m. A height error displaces opposite look directions in opposite senses,
so a residual appearing only on that pass is a terrain signature.

Geocoding at the RPC's own `HEIGHT_OFF` leaves every pass misregistered by about
43 m in ground range — and the 29 October pass, the only **right-looking** one,
is displaced in the *opposite* sense. A constant height error `dh` shifts a
geocoded pixel by `dh / tan(theta)` along ground range with a sign set by the
look direction, so that flip is the signature of a height error and makes the
height identifiable from the imagery alone.

We scan height against Capella's own DEM-geocoded GEO previews (an independent
product) and take the minimum. All six passes agree on **−20 m ellipsoidal**,
residual ≤ 2.8 m, with correlation against Capella's geocoding rising from ~0.05
to **0.68–0.83**. Cross-check: with a Gujarat geoid undulation near −60 m that is
~37–42 m orthometric, against the **37.5 m** district altitude published in the
ICAR-CRIDA Vadodara contingency plan."""))
C.append(code('''
import geopandas as gpd
from rasterio.transform import Affine
from rasterio.warp import reproject, Resampling
from skimage.registration import phase_cross_correlation
from scipy import ndimage

vill = gpd.read_file(VILL_SHP).to_crs(UTM43N)
farms = gpd.read_file(FARM_SHP).to_crs(UTM43N)
farms["geometry"] = farms.geometry.buffer(0)
farms["plot_id"] = farms["FID"].astype(int)
farms["area_ha"] = farms.geometry.area / 1e4
b, bf = np.array(vill.total_bounds), np.array(farms.total_bounds)
MARGIN, RES = 250.0, 2.0
bounds = (min(b[0], bf[0]) - MARGIN, min(b[1], bf[1]) - MARGIN,
          max(b[2], bf[2]) + MARGIN, max(b[3], bf[3]) + MARGIN)
transform, W, H = make_grid(bounds, RES)
GRID_W, GRID_H = W, H          # stable aliases: later cells reuse short names
print(f"AOI grid {W} x {H} @ {RES} m  ({W*RES/1000:.2f} x {H*RES/1000:.2f} km), "
      f"{len(farms)} plots, {farms.area_ha.sum():.1f} ha")

# coarse 10 m grid for the height scan
R10 = 10.0
tr10, W10, H10 = make_grid(bounds, R10)
refs = {}
for s in scenes:
    a = np.zeros((H10, W10), np.float32)
    with rasterio.open(s.preview) as ds:
        reproject(rasterio.band(ds, 1), a, src_transform=ds.transform, src_crs=ds.crs,
                  dst_transform=tr10, dst_crs=UTM43N, resampling=Resampling.average)
    v = np.where(a > 0, np.log10(np.maximum(a, 1)), np.nan)
    refs[s.date] = ndimage.gaussian_filter(np.nan_to_num(v - np.nanmedian(v)), 1.0)

HEIGHTS = [-30, -20, -10]
scan = []
for s in scenes:
    for h in HEIGHTS:
        g, frac, _ = geocode_scene(s, tr10, W10, H10, R10, height_m=h, ss=2,
                                   chunk_rows=64, verbose=False)
        d = to_db(np.where(frac > .75, g, np.nan))
        d = ndimage.gaussian_filter(np.nan_to_num(d - np.nanmedian(d)), 1.0)
        sh, _, _ = phase_cross_correlation(refs[s.date], d, upsample_factor=10,
                                           normalization=None)
        m = np.isfinite(d) & np.isfinite(refs[s.date])
        scan.append({"date": s.date, "height_m": h,
                     "shift_m": round(float(np.hypot(*sh) * R10), 1),
                     "corr": round(float(np.corrcoef(d[m], refs[s.date][m])[0, 1]), 3)})
scan = pd.DataFrame(scan)
best = scan.loc[scan.groupby("date").shift_m.idxmin()]
print(best.to_string(index=False))
REF_HEIGHT_M = float(best.height_m.median())
print("\\nbest single constant height:", REF_HEIGHT_M, "m ellipsoidal "
      "(kept only as a fallback where the DEM has no data)")
'''))

C.append(md("""## 4 · Geocode all six passes to a common 2 m γ⁰ grid

Every 4×4 sub-sample within each 2 m output cell is projected at its own terrain
height, `H_ortho(lon, lat) + N`. The multi-look therefore happens in the map
domain, on correctly located samples."""))
C.append(code('''
import time
gamma, nesz_g = {}, {}
for s in scenes:
    t0 = time.time()
    g, frac, nz = geocode_scene(s, transform, W, H, RES, height_m=REF_HEIGHT_M,
                                dem_sample=DEM_SAMPLE, geoid_offset=GEOID_N,
                                ss=4, chunk_rows=32, verbose=False)
    g = np.where(frac > 0.75, g, np.nan).astype(np.float32)
    gamma[s.date], nesz_g[s.date] = g, nz.astype(np.float32)
    db = to_db(g)
    print(f"{s.date} inc={s.inc_centre:5.2f} {s.look:>5}  "
          f"gamma0 dB p05/p50/p95 = {np.nanpercentile(db,5):6.2f} / "
          f"{np.nanpercentile(db,50):6.2f} / {np.nanpercentile(db,95):6.2f}   "
          f"valid={100*np.isfinite(g).mean():4.1f}%   [{time.time()-t0:.0f}s]")
DATES = [s.date for s in scenes]
stack = np.stack([gamma[d] for d in DATES])
nesz = np.stack([nesz_g[d] for d in DATES])
'''))

C.append(md("""## 5 · Co-registration and zonal statistics

The phase-correlation search is **bounded** to a few metres. Left unbounded it
locks onto a spurious peak for the right-looking 29 October pass — its speckle
and shadow structure differs too much from a left-looking reference. Residuals
are ≤0.1 m for the five left-looking passes and 2.54 m for the right-looking one.

Plots are eroded 4 m inward to reject bunds and edge mixing. Within-field
structural heterogeneity is measured on 10 m block means with the speckle
variance removed in quadrature."""))
C.append(code('''
from shapely.geometry import MultiPolygon
from matplotlib.path import Path as MPath

def prep(a):
    d = to_db(a).astype(np.float32); med = np.nanmedian(d)
    return ndimage.gaussian_filter(np.where(np.isfinite(d), d, med) - med, 2.0)

def bounded_shift(ref, mov, maxpx=8):
    F = np.fft.rfft2(ref) * np.conj(np.fft.rfft2(mov))
    F /= np.maximum(np.abs(F), 1e-12)
    cc = np.fft.fftshift(np.fft.irfft2(F, s=ref.shape).real)
    cy, cx = ref.shape[0] // 2, ref.shape[1] // 2
    win = cc[cy-maxpx:cy+maxpx+1, cx-maxpx:cx+maxpx+1]
    p = np.unravel_index(np.argmax(win), win.shape)
    dy, dx = p[0] - maxpx, p[1] - maxpx
    def sub(v0, vm, vp):
        den = vm - 2*v0 + vp
        return 0.0 if abs(den) < 1e-12 else 0.5*(vm - vp)/den
    if 0 < p[0] < win.shape[0]-1: dy += sub(win[p], win[p[0]-1,p[1]], win[p[0]+1,p[1]])
    if 0 < p[1] < win.shape[1]-1: dx += sub(win[p], win[p[0],p[1]-1], win[p[0],p[1]+1])
    return np.array([-dy, -dx])

ref_img = prep(stack[0])
for i in range(1, len(DATES)):
    sh = bounded_shift(ref_img, prep(stack[i]))
    print(f"  coreg {DATES[i]}: dE={-sh[1]*RES:+.2f} m  dN={-sh[0]*RES:+.2f} m")
    a = stack[i].copy(); bad = ~np.isfinite(a); a[bad] = np.nanmedian(a)
    a = ndimage.shift(a, sh, order=1, mode="nearest")
    m = ndimage.shift(bad.astype(np.float32), sh, order=1, mode="nearest")
    stack[i] = np.where(m > .5, np.nan, a)

EROSION_M, BLOCK, SPECKLE_DB, ENL2 = 4.0, 5, 5.57, 2.9
inv_tr = ~transform
recs = []
for pid, geom, ar in zip(farms.plot_id, farms.geometry, farms.area_ha):
    core, lvl = geom.buffer(-EROSION_M), "eroded4m"
    if core.is_empty or core.area < 12*RES*RES: core, lvl = geom.buffer(-1.0), "eroded1m"
    if core.is_empty or core.area < 12*RES*RES: core, lvl = geom, "full"
    if core.is_empty or core.area <= 0: core, lvl = geom.centroid.buffer(3.0), "centroid"
    mnx, mny, mxx, mxy = core.bounds
    c0, r0 = inv_tr * (mnx, mxy); c1, r1 = inv_tr * (mxx, mny)
    c0, r0 = max(int(c0)-1, 0), max(int(r0)-1, 0)
    c1, r1 = min(int(c1)+2, W), min(int(r1)+2, H)
    if c1 <= c0 or r1 <= r0:
        recs += [{"plot_id": pid, "date": d, "area_ha": ar, "n_pix": 0} for d in DATES]; continue
    yy, xx = np.mgrid[r0:r1, c0:c1]
    X = transform.c + (xx+.5)*RES; Y = transform.f - (yy+.5)*RES
    pts = np.column_stack([X.ravel(), Y.ravel()])
    polys = core.geoms if isinstance(core, MultiPolygon) else [core]
    mask = np.zeros(X.shape, bool)
    for p in polys:
        mask |= MPath(np.asarray(p.exterior.coords)).contains_points(pts).reshape(X.shape)
    if mask.sum() == 0:
        cc, rr = inv_tr * (core.centroid.x, core.centroid.y)
        rr, cc = int(rr)-r0, int(cc)-c0
        if 0 <= rr < mask.shape[0] and 0 <= cc < mask.shape[1]:
            mask[max(rr-1,0):rr+2, max(cc-1,0):cc+2] = True
    for i, d in enumerate(DATES):
        v = stack[i, r0:r1, c0:c1][mask]; nv = nesz[i, r0:r1, c0:c1][mask]
        ok = np.isfinite(v) & (v > 0); v, nv = v[ok], nv[ok]
        rec = {"plot_id": pid, "date": d, "area_ha": ar, "n_pix": int(v.size),
               "mask_level": lvl}
        if v.size >= 5:
            vdb = 10*np.log10(v)
            rec.update({"g0_db": float(10*np.log10(v.mean())),
                        "g0_db_std": float(vdb.std()),
                        "cv_lin": float(v.std()/v.mean()),
                        "frac_below_nesz": float((v < nv).mean())})
        recs.append(rec)
long = pd.DataFrame(recs)
long.to_csv(os.path.join(OUT, "plot_stats_long.csv"), index=False)
nobs = long.pivot(index="plot_id", columns="date", values="g0_db").notna().sum(axis=1)
print(f"\\nplots with all 6 dates: {(nobs==6).sum()},  >=4: {(nobs>=4).sum()},  0: {(nobs==0).sum()}")
'''))

C.append(md("""## 6 · Agronomic knowledge base

Every input that is not derived from the SAR itself is declared here with its
source, so each assumption in the forecast is auditable."""))
C.append(code(src("cropmodel.py")))

C.append(md("""## 7 · Crop labels

Two label sets are compared:

* the **Round-1/2 carry-forward**, area-constrained to the Round-1 village crop
  composition through a transportation LP;
* an **independent re-derivation** from all six passes using phenological
  templates in village-anomaly space.

They agree on 48% of plots. Adjudicated against Sentinel-2 NDVI — which neither
saw — the carry-forward separates November greenness better (η² 0.138 vs 0.089),
so it stays primary, and the disagreement is carried forward as *label
uncertainty* rather than discarded. Reporting this honestly matters more than
claiming an improvement we did not achieve."""))
_cls = src("40_classify.py")
_cls_old_hdr = ('BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n'
                'OUT = os.path.join(BASE, "pipeline", "out")\n'
                'sys.path.insert(0, os.path.join(BASE, "pipeline"))\n'
                'from cropmodel import ACQ_DATES, CROP_NAMES, DISTRICT_AREA_00HA')
_cls_new_hdr = ('# ACQ_DATES, CROP_NAMES come from the cropmodel cell above\n'
                'BASE = os.path.dirname(DATA_ROOT.rstrip("/\\\\"))')
assert _cls_old_hdr in _cls, "classify header changed; notebook surgery is stale"
_cls = _cls.replace(_cls_old_hdr, _cls_new_hdr)
assert 'long = pd.read_csv(os.path.join(OUT, "plot_stats_long.csv"))\n' in _cls
_cls = _cls.replace('long = pd.read_csv(os.path.join(OUT, "plot_stats_long.csv"))\n', '')
# 40_classify.py already tolerates a missing Round-2 file, so no further surgery
assert 'if os.path.exists(R2_PATH) else None' in _cls
C.append(code(_cls))

C.append(md("""## 7b · Using the phase: what we tried, and what we found

The products are Single Look **Complex**, so the obvious question is why the
forecast rests on amplitude alone. Answered by measurement rather than assertion.

**Repeat-pass InSAR is structurally unavailable.** Of the fifteen pass pairs,
five are opposite-look and nine exceed the critical baseline. The single viable
pair (19 Jun / 14 Aug, B⊥ 844 m against B⊥crit 3975 m) is 56 days apart — far
beyond X-band coherence over a growing canopy.

**Sub-aperture coherence** avoids that entirely: splitting one acquisition's
Doppler spectrum into two sub-looks is single-pass, so temporal decorrelation
cannot touch it. Two details decide whether the estimator works — the sub-looks
must be demodulated to baseband before correlation, and the split must happen
inside the occupied band (the product is azimuth-oversampled, so ~40% of the
sampled band is empty). With both handled, point scatterers reach γ ≈ 0.98
against 0.25 for distributed clutter.

At plot level it is nonetheless **null**, and is excluded from the model."""))
C.append(code(src("15_baselines.py")
              .replace('sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\nfrom sarlib import find_scenes\n\n', '')
              .replace('BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\nC = 299792458.0\n\nscenes = find_scenes(os.path.join(BASE, "DATA"))',
                       'C_LIGHT = 299792458.0')
              .replace('C / (s.collect["radar"]["center_frequency"])',
                       'C_LIGHT / (s.collect["radar"]["center_frequency"])')
              .replace('json.dump(rows, open(os.path.join(BASE, "pipeline", "baselines.json"), "w"), indent=1)\nprint("\\nwrote pipeline/baselines.json")',
                       'json.dump(rows, open(os.path.join(OUT, "baselines.json"), "w"), indent=1)')))

C.append(md("""## 8 · Independent validation — same-day Sentinel-2

Two Sentinel-2 L2A scenes are *same-day coincident* with Capella passes
(13 Oct, 12 Nov 2025), so the comparison needs no temporal interpolation.
NDVI is used only to test the result and never enters the model.

Requires internet enabled in the notebook settings; the cell skips cleanly if
unavailable."""))
C.append(code(src("30_sentinel2.py").split("import json, os, sys, urllib.request")[1]
              .replace('sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\nfrom sarlib import UTM43N\n', '')
              .replace('BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\nGEO, OUT = os.path.join(BASE, "pipeline", "geo"), os.path.join(BASE, "pipeline", "out")\nS2 = os.path.join(BASE, "pipeline", "s2"); os.makedirs(S2, exist_ok=True)\n\nman = json.load(open(os.path.join(GEO, "manifest.json")))\ntr = Affine(*man["transform"]); W, H = man["width"], man["height"]; RES = man["res"]',
                       'import urllib.request\nS2 = os.path.join(WORKDIR, "s2"); os.makedirs(S2, exist_ok=True)\ntr = transform\nW, H = GRID_W, GRID_H')
              .replace('gdf = gpd.read_file(os.path.join(BASE, "DATA", "Farm_boundaries_shp",\n                                 "Farm_boundaries_shp", "Sokhda_Farms.shp")).to_crs(UTM43N)\ngdf["geometry"] = gdf.geometry.buffer(0)\ngdf["plot_id"] = gdf["FID"].astype(int)',
                       'gdf = farms')))

C.append(md("""## 9 · Yield forecast and village aggregation

$$Y_p = Y_{ref}(c)\\cdot S(c)\\cdot
\\exp\\!\\left(\\sigma_c\\rho z_p - \\tfrac{1}{2}(\\sigma_c\\rho)^2\\right)$$

The lognormal form makes the area-weighted village mean reproduce
`Y_ref(c)·S(c)` **by construction**, so the absolute anchor is an explicit
assumption and everything beneath it is SAR-driven.

The Monte-Carlo error budget separates terms that are **systematic across a
crop** (district reference, season factor, most forecast-horizon risk) from
terms **independent between plots**. Only the second kind averages away on
aggregation — conflating them is the usual reason village intervals come out
implausibly tight."""))
C.append(code(src("50_yield.py")
              .replace('BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\nOUT = os.path.join(BASE, "pipeline", "out")\nsys.path.insert(0, os.path.join(BASE, "pipeline"))\nfrom cropmodel import ACQ_DATES, CROP_NAMES, CROPS, season_factor',
                       '# cropmodel symbols come from the cell above')
              .replace('long = pd.read_csv(os.path.join(OUT, "plot_stats_long.csv"))\n', '')
              .replace('mine = pd.read_csv(os.path.join(OUT, "plot_crop.csv")).set_index("plot_id")\nr2 = pd.read_csv(os.path.join(BASE, "round_2_submmision_files",\n                              "farm_level_results.csv")).set_index("farm_id")',
                       'mine = out.copy()\n# primary labels: the Round-1/2 carry-forward where available, else the 6-pass result')
              .replace('crop = r2["crop_type"].reindex(g.index)',
                       'crop = (r2["crop_type"].reindex(g.index) if r2 is not None\n        else mine["crop_type"].reindex(g.index))')))

C.append(md("""## 9b · Crop-mix scenarios — the dominant uncertainty

The carry-forward puts groundnut at 28.5% of Sokhda; the Directorate of
Agriculture puts it at 0.35% of the district. Both cannot be close to right, and
groundnut carries a high per-hectare reference. We run the assignment under both
area constraints and publish both village tables rather than choose silently."""))
C.append(code(src("51_scenarios.py")
              .replace('BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\nOUT = os.path.join(BASE, "pipeline", "out")\nsys.path.insert(0, os.path.join(BASE, "pipeline"))\nfrom cropmodel import CROP_NAMES, CROPS, DISTRICT_AREA_00HA, season_factor',
                       '# CROP_NAMES, CROPS, DISTRICT_AREA_00HA, season_factor from the cropmodel cell')
              .replace('crop3 = pd.read_csv(os.path.join(OUT, "plot_crop.csv")).set_index("plot_id")\nres = pd.read_csv(os.path.join(OUT, "plot_yield_forecast.csv")).set_index("farm_id")',
                       'crop3 = out.copy()\n# `res` is the plot-level forecast table produced above')))

C.append(md("## 10 · Outputs and self-check"))
C.append(code('''
plot_out = res.reset_index()
plot_out.to_csv(os.path.join(OUT, "plot_level_yield_forecast.csv"), index=False)
vil.to_csv(os.path.join(OUT, "village_level_yield_forecast.csv"), index=False)

assert len(plot_out) == 966, "every plot must carry a forecast"
assert plot_out.yield_forecast_kg_ha.notna().all(), "no missing forecasts"
assert (plot_out.yield_forecast_kg_ha > 0).all()
for _, r in vil.iterrows():
    assert r.yield_p10_kg_ha <= r.yield_forecast_kg_ha <= r.yield_p90_kg_ha, \\
        f"interval must bracket the central forecast for {r.crop_type}"
    ref = CROPS[r.crop_type]["yield_ref"] * season_factor(r.crop_type)
    assert abs(r.yield_forecast_kg_ha / ref - 1) < 0.02, \\
        f"village mean must reproduce the anchor for {r.crop_type}"
print("all assertions passed\\n")
print(vil[["crop_type","n_plots","area_ha","yield_forecast_kg_ha",
           "yield_p10_kg_ha","yield_p90_kg_ha","production_t","product"]].to_string(index=False))
print(f"\\nvillage total production: {vil.production_t.sum():.1f} t over {res.area_ha.sum():.1f} ha")
'''))

nb = {"cells": C,
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                  "name": "python3"},
                   "language_info": {"name": "python", "version": "3.11"}},
      "nbformat": 4, "nbformat_minor": 5}
p = os.path.join(DEL, "aisehack_round3_sar_yield_forecast.ipynb")
json.dump(nb, open(p, "w", encoding="utf-8"), indent=1)
print("wrote", p, f"({os.path.getsize(p)/1024:.0f} KB, {len(C)} cells)")
