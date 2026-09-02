"""Diagnose plot coverage: which plots lose pixels, and why."""
import json, os, sys
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.transform import Affine
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarlib import UTM43N

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO, OUT, FIG = [os.path.join(BASE, "pipeline", x) for x in ("geo", "out", "fig")]
os.makedirs(FIG, exist_ok=True)
man = json.load(open(os.path.join(GEO, "manifest.json")))
tr = Affine(*man["transform"]); W, H = man["width"], man["height"]

valid = None
for s in man["scenes"]:
    with rasterio.open(os.path.join(GEO, f"gamma0_{s['tag']}.tif")) as ds:
        v = np.isfinite(ds.read(1))
    valid = v if valid is None else (valid & v)
print(f"grid {W}x{H}; pixels valid in ALL 6 scenes: {valid.mean()*100:.1f}%")

gdf = gpd.read_file(os.path.join(BASE, "DATA", "Farm_boundaries_shp",
                                 "Farm_boundaries_shp", "Sokhda_Farms.shp")).to_crs(UTM43N)
gdf["geometry"] = gdf.geometry.buffer(0)
gdf["plot_id"] = gdf["FID"].astype(int)
gdf["area_ha"] = gdf.geometry.area / 1e4
gdf["area_m2"] = gdf.geometry.area

print("\nplot area distribution (m2):")
print(gdf.area_m2.describe().to_string())
tiny = gdf[gdf.area_m2 < 200]
print(f"\nplots < 200 m2 : {len(tiny)}")
print(f"plots < 50 m2  : {(gdf.area_m2 < 50).sum()}")
print(f"plots == 0     : {(gdf.area_m2 < 1e-6).sum()}")
print(f"plots losing everything to a 4 m inward buffer: "
      f"{(gdf.geometry.buffer(-4.0).area < 100).sum()}")

long = pd.read_csv(os.path.join(OUT, "plot_stats_long.csv"))
n0 = long[long.n_pix == 0].plot_id.unique()
print(f"\nplots with n_pix==0 on >=1 date: {len(n0)}")
sub = gdf[gdf.plot_id.isin(n0)]
print("their areas (m2):"); print(sub.area_m2.describe().to_string())

# do any plots fall outside the all-scene valid footprint?
from matplotlib.path import Path as MPath
inv = ~tr
out_of_footprint = []
for pid, geom in zip(gdf.plot_id, gdf.geometry):
    cx, cy = geom.centroid.x, geom.centroid.y
    c, r = inv * (cx, cy)
    c, r = int(c), int(r)
    if not (0 <= r < H and 0 <= c < W and valid[r, c]):
        out_of_footprint.append(pid)
print(f"\nplots whose centroid is outside the 6-scene valid footprint: {len(out_of_footprint)}")

fig, ax = plt.subplots(figsize=(9, 8))
ax.imshow(valid, cmap="Greys_r",
          extent=[tr.c, tr.c + W * man["res"], tr.f - H * man["res"], tr.f])
gdf.boundary.plot(ax=ax, color="red", linewidth=0.35)
if out_of_footprint:
    gdf[gdf.plot_id.isin(out_of_footprint)].plot(ax=ax, color="cyan")
ax.set_title("6-scene valid footprint (white) vs 966 farm plots (red)")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "qc_footprint.png"), dpi=130)
print("wrote fig/qc_footprint.png")
