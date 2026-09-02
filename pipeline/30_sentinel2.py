"""Independent optical reference: Sentinel-2 L2A NDVI over the same 966 plots.

This is used ONLY as an out-of-model validation of the SAR-derived crop map and
vigour index -- never as an input to the forecast. Two of the Sentinel-2 passes
(13 Oct 2025 and 12 Nov 2025) are same-day coincident with Capella acquisitions,
which makes the comparison exact in time.

Note the availability pattern itself is part of the argument for SAR: across the
whole June-September monsoon there is one usable optical scene (10 June, 21%
cloud), whereas all six SAR acquisitions are unaffected by cloud.
"""
import json, os, sys, urllib.request
import numpy as np, pandas as pd, geopandas as gpd
import rasterio
from rasterio.warp import reproject, Resampling
from rasterio.transform import Affine
from shapely.geometry import MultiPolygon
from matplotlib.path import Path as MPath

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarlib import UTM43N

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO, OUT = os.path.join(BASE, "pipeline", "geo"), os.path.join(BASE, "pipeline", "out")
S2 = os.path.join(BASE, "pipeline", "s2"); os.makedirs(S2, exist_ok=True)

man = json.load(open(os.path.join(GEO, "manifest.json")))
tr = Affine(*man["transform"]); W, H = man["width"], man["height"]; RES = man["res"]

WANT = ["2025-06-10", "2025-10-08", "2025-10-13", "2025-10-18",
        "2025-11-07", "2025-11-12", "2025-11-22"]

body = {"collections": ["sentinel-2-l2a"], "bbox": [73.133, 22.408, 73.181, 22.443],
        "datetime": "2025-06-01T00:00:00Z/2025-12-01T00:00:00Z",
        "query": {"eo:cloud_cover": {"lt": 30}}, "limit": 100}
req = urllib.request.Request("https://earth-search.aws.element84.com/v1/search",
                             data=json.dumps(body).encode(),
                             headers={"Content-Type": "application/json"})
feats = json.load(urllib.request.urlopen(req, timeout=60))["features"]

# the AOI straddles the 43QBE / 43QCE MGRS tile boundary, so both are kept and
# mosaicked per date (first valid observation wins)
by_date = {}
for f in feats:
    d = f["properties"]["datetime"][:10]
    if d in WANT:
        by_date.setdefault(d, []).append(f)
print("using scenes:", {d: [x["id"] for x in v] for d, v in sorted(by_date.items())})

env = rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                   AWS_NO_SIGN_REQUEST="YES",
                   GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="2")


def grab(href, dst_shape, dst_tr, resamp=Resampling.bilinear):
    out = np.full(dst_shape, np.nan, dtype=np.float32)
    with rasterio.open(href) as ds:
        reproject(rasterio.band(ds, 1), out,
                  src_transform=ds.transform, src_crs=ds.crs, src_nodata=0,
                  dst_transform=dst_tr, dst_crs=UTM43N, dst_nodata=np.nan,
                  resampling=resamp)
    return out


# work on a 10 m grid (native S2) covering the same AOI
R10 = 10.0
f10 = int(R10 / RES)
W10, H10 = W // f10, H // f10
tr10 = Affine(R10, 0, tr.c, 0, -R10, tr.f)

ndvi = {}
with env:
    for d in sorted(by_date):
        v = np.full((H10, W10), np.nan, dtype=np.float32)
        for f in by_date[d]:
            a = f["assets"]
            red = grab(a["red"]["href"], (H10, W10), tr10)
            nir = grab(a["nir"]["href"], (H10, W10), tr10)
            scl = grab(a["scl"]["href"], (H10, W10), tr10, Resampling.nearest)
            # SCL: 4 vegetation, 5 bare, 6 water, 7 unclassified are usable;
            # 3 shadow, 8/9/10 cloud, 11 snow are not
            bad = np.isin(np.nan_to_num(scl, nan=0).astype(int), [0, 1, 2, 3, 8, 9, 10, 11])
            vi = (nir - red) / np.maximum(nir + red, 1e-6)
            vi = np.where(bad | ~np.isfinite(vi), np.nan, vi)
            v = np.where(np.isfinite(v), v, vi)          # mosaic the two tiles
        ndvi[d] = v.astype(np.float32)
        print(f"  {d}: valid {100*np.isfinite(v).mean():5.1f}%   "
              f"NDVI p10/p50/p90 = {np.nanpercentile(v,10):.2f} / "
              f"{np.nanpercentile(v,50):.2f} / {np.nanpercentile(v,90):.2f}")
        np.save(os.path.join(S2, f"ndvi_{d}.npy"), ndvi[d])

# ---------------------------------------------------------- zonal NDVI per plot
gdf = gpd.read_file(os.path.join(BASE, "DATA", "Farm_boundaries_shp",
                                 "Farm_boundaries_shp", "Sokhda_Farms.shp")).to_crs(UTM43N)
gdf["geometry"] = gdf.geometry.buffer(0)
gdf["plot_id"] = gdf["FID"].astype(int)
inv = ~tr10
rows = []
for pid, geom in zip(gdf.plot_id, gdf.geometry):
    core = geom.buffer(-6.0)
    if core.is_empty or core.area < 100:
        core = geom
    if core.is_empty or core.area <= 0:
        core = geom.centroid.buffer(5.0)
    minx, miny, maxx, maxy = core.bounds
    c0, r0 = inv * (minx, maxy); c1, r1 = inv * (maxx, miny)
    c0, r0 = max(int(np.floor(c0)) - 1, 0), max(int(np.floor(r0)) - 1, 0)
    c1, r1 = min(int(np.ceil(c1)) + 1, W10), min(int(np.ceil(r1)) + 1, H10)
    rec = {"plot_id": pid}
    if c1 > c0 and r1 > r0:
        yy, xx = np.mgrid[r0:r1, c0:c1]
        X = tr10.c + (xx + .5) * R10; Y = tr10.f - (yy + .5) * R10
        pts = np.column_stack([X.ravel(), Y.ravel()])
        polys = core.geoms if isinstance(core, MultiPolygon) else [core]
        m = np.zeros(X.shape, bool)
        for p in polys:
            m |= MPath(np.asarray(p.exterior.coords)).contains_points(pts).reshape(X.shape)
        if m.sum() == 0:
            cc, rr = inv * (core.centroid.x, core.centroid.y)
            rr, cc = int(rr) - r0, int(cc) - c0
            if 0 <= rr < m.shape[0] and 0 <= cc < m.shape[1]:
                m[rr, cc] = True
        for d, v in ndvi.items():
            vals = v[r0:r1, c0:c1][m]
            vals = vals[np.isfinite(vals)]
            rec[f"ndvi_{d}"] = float(vals.mean()) if vals.size else np.nan
            rec[f"ndvin_{d}"] = int(vals.size)
    rows.append(rec)

df = pd.DataFrame(rows).set_index("plot_id")
df.to_csv(os.path.join(OUT, "plot_ndvi.csv"))
print(f"\nwrote plot_ndvi.csv {df.shape}")
print(df[[c for c in df.columns if c.startswith('ndvi_')]]
      .describe(percentiles=[.1, .5, .9]).T.to_string())
