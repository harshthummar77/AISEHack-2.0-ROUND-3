import json, glob, os
import geopandas as gpd
import rasterio
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DATA")
scenes = sorted(glob.glob(os.path.join(ROOT, "CAPELLA_*")))

print("="*70, "\nRPC / GCP CHECK ON SLC\n", "="*70)
for s in scenes:
    tif = [t for t in glob.glob(os.path.join(s, "*.tif")) if "_SLC_" in os.path.basename(t)]
    for t in tif:
        with rasterio.open(t) as ds:
            print(os.path.basename(t)[:60], "| rpcs:", bool(ds.rpcs), "| gcps:", len(ds.get_gcps()[0]) if ds.get_gcps() else 0)
            if ds.rpcs:
                print("    rpc keys:", sorted(ds.rpcs.to_gdal().keys())[:8])

print("\n", "="*70, "\nPREVIEW GEO HEADERS\n", "="*70)
for s in scenes:
    for t in glob.glob(os.path.join(s, "*_preview.tif")):
        with rasterio.open(t) as ds:
            print(os.path.basename(t)[:65])
            print("   ", ds.width, ds.height, ds.dtypes, ds.crs, "res", ds.res, "nodata", ds.nodata)
            print("    bounds", [round(x,1) for x in ds.bounds])
            print("    overviews", ds.overviews(1))

print("\n", "="*70, "\nSCENE GEOMETRY SUMMARY\n", "="*70)
for s in scenes:
    b = [x for x in glob.glob(os.path.join(s, "*.json")) if "extended" not in x and "digest" not in x]
    d = json.load(open(b[0])); p = d["properties"]
    print(f"{p['datetime'][:19]} | orbit={p['sat:orbit_state']:>10} | inc={p.get('view:incidence_angle'):.2f} "
          f"| look={p.get('sar:observation_direction')} | az={p.get('view:azimuth'):.1f} "
          f"| scale={p.get('capella:scale_factor')} | bbox={[round(x,3) for x in d['bbox']]}")
    print("     extra:", {k: v for k, v in p.items() if k.startswith(("capella:", "sar:", "view:", "sat:"))})

print("\n", "="*70, "\nFARM SHP\n", "="*70)
f = gpd.read_file(os.path.join(ROOT, "Farm_boundaries_shp", "Farm_boundaries_shp", "Sokhda_Farms.shp"))
print("n =", len(f), "| crs =", f.crs, "| cols =", f.columns.tolist())
print(f.head(8).to_string(max_colwidth=40))
for c in [c for c in f.columns if c != "geometry"]:
    print(f"\n-- {c}: dtype={f[c].dtype} nunique={f[c].nunique()} nulls={f[c].isna().sum()}")
    print(f[c].value_counts(dropna=False).head(12).to_string())
fm = f.to_crs(32643)
print("\narea_ha:\n", (fm.geometry.area/1e4).describe().to_string())
print("total_bounds ll:", f.to_crs(4326).total_bounds)
print("valid geoms:", fm.geometry.is_valid.sum(), "/", len(fm))

print("\n", "="*70, "\nVILLAGE SHP\n", "="*70)
v = gpd.read_file(os.path.join(ROOT, "Village_Shp", "Village_Shp", "Sokhda_Village.shp"))
print("n =", len(v), "crs", v.crs, v.columns.tolist())
print(v.drop(columns="geometry").to_string(max_colwidth=40))
print("area ha:", (v.to_crs(32643).geometry.area/1e4).values)
print("bounds ll:", v.to_crs(4326).total_bounds)
