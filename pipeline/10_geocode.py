"""Geocode all six Capella SLC acquisitions to calibrated gamma0 on a common
2 m UTM-43N grid covering the Sokhda AOI."""
import json, os, sys, time
import numpy as np
import geopandas as gpd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarlib import find_scenes, make_grid, geocode_scene, write_tif, to_db, UTM43N

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(BASE, "DATA")
OUT = os.path.join(BASE, "pipeline", "geo")
os.makedirs(OUT, exist_ok=True)

RES = 2.0
MARGIN = 250.0
# Terrain-referenced geocoding. The Copernicus GLO-30 DEM supplies orthometric
# height per sub-sample; the ellipsoid/geoid datum shift is solved from the 225
# GCPs embedded in each product (13_dem.py) rather than assumed:
#   N = -62.023 m, scene-to-scene sd 0.124 m
# The AOI carries 26.6 m of relief, which a constant height would convert into
# up to 46 m of ground-range displacement at 30 deg incidence. Measured on the
# GCP round trip, DEM heights give 4.1-4.7 px RMSE against 15-17 px for the best
# single constant height.
REF_HEIGHT_M = -20.0        # fallback only, where the DEM has no data

vill = gpd.read_file(os.path.join(ROOT, "Village_Shp", "Village_Shp", "Sokhda_Village.shp")).to_crs(UTM43N)
farm = gpd.read_file(os.path.join(ROOT, "Farm_boundaries_shp", "Farm_boundaries_shp", "Sokhda_Farms.shp")).to_crs(UTM43N)
b = np.array(vill.total_bounds)
bf = np.array(farm.total_bounds)
bounds = (min(b[0], bf[0]) - MARGIN, min(b[1], bf[1]) - MARGIN,
          max(b[2], bf[2]) + MARGIN, max(b[3], bf[3]) + MARGIN)
transform, W, H = make_grid(bounds, RES)
print(f"AOI grid: {W} x {H} @ {RES} m   origin=({transform.c:.1f}, {transform.f:.1f})")
print(f"extent   : {(W*RES)/1000:.2f} x {(H*RES)/1000:.2f} km\n")

from importlib import import_module
_dem = import_module("13_dem") if False else None
sys.path.insert(0, os.path.join(BASE, "pipeline"))
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("demmod", os.path.join(BASE, "pipeline", "13_dem.py"))
demmod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(demmod)
DEM_SAMPLE, _dem_ds = demmod.make_dem_sampler(demmod.fetch_dem())
GEOID_N = json.load(open(os.path.join(BASE, "pipeline", "dem_solution.json")))["geoid_offset_m"]
print(f"terrain-referenced geocoding: Copernicus GLO-30, geoid offset N = {GEOID_N:.3f} m\n")

scenes = find_scenes(ROOT)
manifest = {"res": RES, "width": W, "height": H, "crs": UTM43N,
            "ref_height_m": REF_HEIGHT_M, "geoid_offset_m": GEOID_N,
            "dem": "Copernicus GLO-30 (EGM2008 orthometric)",
            "transform": [transform.a, transform.b, transform.c,
                          transform.d, transform.e, transform.f],
            "scenes": []}

for s in scenes:
    t0 = time.time()
    print(f"[{s.date}] inc={s.inc_centre:.2f} look={s.look} az={s.az:.0f}")
    g, frac, nesz = geocode_scene(s, transform, W, H, RES, height_m=REF_HEIGHT_M,
                                  dem_sample=DEM_SAMPLE, geoid_offset=GEOID_N,
                                  ss=4, chunk_rows=32)
    valid = frac > 0.75
    g = np.where(valid, g, np.nan).astype(np.float32)
    tag = s.date.replace("-", "")
    write_tif(os.path.join(OUT, f"gamma0_{tag}.tif"), g, transform)
    write_tif(os.path.join(OUT, f"nesz_{tag}.tif"), nesz.astype(np.float32), transform)
    db = to_db(g)
    manifest["scenes"].append({
        "date": s.date, "datetime": s.datetime, "tag": tag,
        "incidence": s.inc_centre, "look": s.look, "orbit": s.orbit,
        "azimuth": s.az, "nesz_peak": s.nesz_peak,
        "scale_factor": s.scale_factor,
        "valid_frac": float(valid.mean()),
        "g0_db_p05": float(np.nanpercentile(db, 5)),
        "g0_db_p50": float(np.nanpercentile(db, 50)),
        "g0_db_p95": float(np.nanpercentile(db, 95)),
        "frac_below_nesz": float(np.nanmean(g < nesz)),
    })
    print(f"    gamma0 dB p05/p50/p95 = {manifest['scenes'][-1]['g0_db_p05']:.2f} / "
          f"{manifest['scenes'][-1]['g0_db_p50']:.2f} / {manifest['scenes'][-1]['g0_db_p95']:.2f}"
          f"   valid={valid.mean()*100:.1f}%  <NESZ={manifest['scenes'][-1]['frac_below_nesz']*100:.2f}%"
          f"   [{time.time()-t0:.0f}s]\n")

json.dump(manifest, open(os.path.join(OUT, "manifest.json"), "w"), indent=1)
print("wrote", os.path.join(OUT, "manifest.json"))
