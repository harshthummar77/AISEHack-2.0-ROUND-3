"""Fetch the Copernicus GLO-30 DEM and solve the ellipsoid/geoid datum shift.

Capella RPCs expect ELLIPSOIDAL heights; Copernicus DEM stores ORTHOMETRIC
(EGM2008) heights. The 225 GCPs embedded in each SLC carry ellipsoidal z, so the
offset N = h_ellipsoidal - H_orthometric can be solved rather than assumed.

This validates the assumption before it is used: if the GCP z values were a
synthetic multi-layer height grid rather than terrain, the within-scene scatter
of (z - H_ortho) would be tens of metres and the solve would be meaningless.
"""
import json, os, sys, urllib.request
import numpy as np
import rasterio
from rasterio.transform import Affine

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarlib import find_scenes, RPC, UTM43N

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(BASE, "pipeline")
DEM_LOCAL = os.path.join(WORK, "copdem_N22E073.tif")
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_N22_00_E073_00_DEM/"
           "Copernicus_DSM_COG_10_N22_00_E073_00_DEM.tif")


def fetch_dem():
    if os.path.exists(DEM_LOCAL) and os.path.getsize(DEM_LOCAL) > 1_000_000:
        print(f"DEM cached: {DEM_LOCAL} ({os.path.getsize(DEM_LOCAL)/1e6:.1f} MB)")
        return DEM_LOCAL
    print("downloading Copernicus GLO-30 tile N22E073 ...")
    urllib.request.urlretrieve(DEM_URL, DEM_LOCAL)
    print(f"  got {os.path.getsize(DEM_LOCAL)/1e6:.1f} MB")
    return DEM_LOCAL


def make_dem_sampler(path):
    ds = rasterio.open(path)
    dem = ds.read(1).astype(np.float64)
    if ds.nodata is not None:
        dem[dem == ds.nodata] = np.nan
    inv = ~ds.transform
    H, W = dem.shape

    def sample(lon, lat):
        """Bilinear sample of orthometric height at geographic coordinates."""
        lon = np.asarray(lon, dtype=np.float64)
        lat = np.asarray(lat, dtype=np.float64)
        c, r = inv * (lon, lat)
        c = np.clip(c - 0.5, 0, W - 1.001)
        r = np.clip(r - 0.5, 0, H - 1.001)
        c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
        fc, fr = c - c0, r - r0
        v = (dem[r0, c0] * (1 - fc) * (1 - fr) + dem[r0, c0 + 1] * fc * (1 - fr) +
             dem[r0 + 1, c0] * (1 - fc) * fr + dem[r0 + 1, c0 + 1] * fc * fr)
        return v

    return sample, ds


if __name__ == "__main__":
    path = fetch_dem()
    sample, ds = make_dem_sampler(path)
    print(f"DEM: {ds.width}x{ds.height} @ {ds.res[0]*3600:.1f} arcsec, crs {ds.crs}")

    scenes = find_scenes(os.path.join(BASE, "DATA"))
    print("\n" + "=" * 84)
    print("GEOID OFFSET FROM THE 225 EMBEDDED GCPs")
    print("=" * 84)
    offs = []
    for s in scenes:
        with rasterio.open(s.slc) as d:
            gcps, _ = d.get_gcps()
            rpc = RPC(d.rpcs.to_gdal())
        lon = np.array([g.x for g in gcps]); lat = np.array([g.y for g in gcps])
        z = np.array([g.z for g in gcps])
        row = np.array([g.row for g in gcps]); col = np.array([g.col for g in gcps])
        ho = sample(lon, lat)
        ok = np.isfinite(ho)
        diff = z[ok] - ho[ok]
        offs.append(diff.mean())
        # round-trip: DEM height vs a single constant height
        ln1, sm1 = rpc.forward(lon, lat, ho + diff.mean())
        e1 = float(np.sqrt(np.mean((ln1 - row) ** 2 + (sm1 - col) ** 2)))
        ln2, sm2 = rpc.forward(lon, lat, np.full_like(lon, -20.0))
        e2 = float(np.sqrt(np.mean((ln2 - row) ** 2 + (sm2 - col) ** 2)))
        print(f"{s.date}: N = {diff.mean():8.3f} m   within-scene sd = {diff.std():6.3f} m   "
              f"n={ok.sum()}")
        print(f"            GCP z {z.min():7.1f}..{z.max():7.1f} m | DEM ortho "
              f"{ho[ok].min():5.1f}..{ho[ok].max():5.1f} m")
        print(f"            RPC round-trip RMSE:  DEM heights {e1:8.4f} px   "
              f"constant -20 m {e2:9.3f} px")
    N = float(np.mean(offs))
    print(f"\nmean geoid offset N = {N:.3f} m   (scene-to-scene sd {np.std(offs):.3f} m)")

    # terrain statistics over the farm AOI
    import geopandas as gpd
    farms = gpd.read_file(os.path.join(BASE, "DATA", "Farm_boundaries_shp",
                                       "Farm_boundaries_shp", "Sokhda_Farms.shp"))
    b = farms.total_bounds
    lo = np.linspace(b[0] - .004, b[2] + .004, 300)
    la = np.linspace(b[1] - .004, b[3] + .004, 300)
    LO, LA = np.meshgrid(lo, la)
    Ho = sample(LO, LA)
    print(f"\nterrain over the farm AOI (orthometric, EGM2008): "
          f"{np.nanmin(Ho):.1f} .. {np.nanmax(Ho):.1f} m, relief {np.nanmax(Ho)-np.nanmin(Ho):.1f} m")
    print(f"  ellipsoidal equivalent: {np.nanmin(Ho)+N:.1f} .. {np.nanmax(Ho)+N:.1f} m "
          f"(constant used previously: -20.0 m)")
    inc = np.radians(30.0)
    print(f"  ground-range displacement from ignoring this relief at 30 deg incidence: "
          f"up to {(np.nanmax(Ho)-np.nanmin(Ho))/np.tan(inc):.1f} m")
    json.dump({"geoid_offset_m": N, "dem": "Copernicus GLO-30 (EGM2008 orthometric)",
               "terrain_ortho_min": float(np.nanmin(Ho)),
               "terrain_ortho_max": float(np.nanmax(Ho))},
              open(os.path.join(WORK, "dem_solution.json"), "w"), indent=1)
    print("\nwrote pipeline/dem_solution.json")
