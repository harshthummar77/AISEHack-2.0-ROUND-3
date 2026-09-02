import json, glob, os, sys
import geopandas as gpd
import rasterio
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DATA")

print("="*80)
print("SCENE METADATA")
print("="*80)
scenes = sorted(glob.glob(os.path.join(ROOT, "CAPELLA_*")))
for s in scenes:
    ext = glob.glob(os.path.join(s, "*_extended.json"))
    base = glob.glob(os.path.join(s, "CAPELLA_C14_SM_SLC_HH_2*.json"))
    base = [b for b in base if "extended" not in b and "digest" not in b]
    print("\n---", os.path.basename(s))
    if base:
        d = json.load(open(base[0]))
        print("  top keys:", list(d.keys()))
        print(json.dumps(d, indent=1)[:2500])
    if ext:
        e = json.load(open(ext[0]))
        print("  EXT keys:", list(e.keys()))

print("\n" + "="*80)
print("RASTER HEADERS")
print("="*80)
for s in scenes:
    for t in sorted(glob.glob(os.path.join(s, "*.tif"))):
        with rasterio.open(t) as ds:
            print(os.path.basename(t))
            print("   size", ds.width, ds.height, "count", ds.count, "dtype", ds.dtypes,
                  "crs", ds.crs, "nodata", ds.nodata)
            print("   bounds", ds.bounds)
            print("   transform", ds.transform)
            print("   tags", {k: v for k, v in ds.tags().items()})

print("\n" + "="*80)
print("FARM SHAPEFILE")
print("="*80)
f = gpd.read_file(os.path.join(ROOT, "Farm_boundaries_shp", "Farm_boundaries_shp", "Sokhda_Farms.shp"))
print("n =", len(f), "crs", f.crs)
print(f.columns.tolist())
print(f.head(10).to_string())
print(f.dtypes)
for c in f.columns:
    if c != "geometry":
        u = f[c].unique()
        print(f"\ncol {c}: nunique={len(u)}")
        if len(u) < 40:
            print("  ", u)
        print("   value_counts head:\n", f[c].value_counts().head(15).to_string())
print("\ntotal bounds", f.total_bounds)
fm = f.to_crs(32643) if f.crs and f.crs.to_epsg() == 4326 else f
print("area ha stats:\n", (fm.geometry.area/1e4).describe().to_string())

print("\n" + "="*80)
print("VILLAGE SHAPEFILE")
print("="*80)
v = gpd.read_file(os.path.join(ROOT, "Village_Shp", "Village_Shp", "Sokhda_Village.shp"))
print("n =", len(v), "crs", v.crs)
print(v.drop(columns="geometry").to_string())
print("bounds", v.total_bounds)
