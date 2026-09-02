"""
sarlib.py -- Capella X-band SLC -> calibrated, geocoded gamma-nought.

Core utilities shared by the Round-3 pipeline:
  * RPC00B rational-polynomial forward model (ground -> image), vectorised.
  * Capella radiometric calibration  (DN -> beta0 -> sigma0 -> gamma0).
  * Per-range-sample local incidence angle from a spherical-Earth solution
    using the product state vectors.
  * Inverse geocoding of the slant-plane image onto a UTM grid by
    super-sampled nearest-neighbour gather + block averaging (this performs
    the spatial multi-look in the map domain).

Radiometry reference: Capella SLC products are delivered with
`collect.image.radiometry == "beta_nought"` and `calibration == "full"`,
so that
        beta0 = (|DN| * scale_factor)^2
        sigma0 = beta0 * sin(theta_inc)
        gamma0 = sigma0 / cos(theta_inc) = beta0 * tan(theta_inc)
gamma0 is used throughout because it is the quantity that is (to first
order) invariant to incidence angle for volume scatterers -- essential
here, because the six passes span theta = 28.7 deg .. 35.2 deg.
"""

from __future__ import annotations

import glob
import json
import os

import numpy as np
import rasterio
from pyproj import Transformer

# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------
UTM43N = "EPSG:32643"
WGS84 = "EPSG:4326"


# --------------------------------------------------------------------------
# RPC00B forward model
# --------------------------------------------------------------------------
def _rpc_terms(L: np.ndarray, P: np.ndarray, H: np.ndarray) -> np.ndarray:
    """20 monomials of the RPC00B cubic, in GDAL/NITF order.

    L = normalised longitude, P = normalised latitude, H = normalised height.
    Returns an array of shape (20, n).
    """
    return np.stack([
        np.ones_like(L),
        L, P, H,
        L * P, L * H, P * H,
        L * L, P * P, H * H,
        P * L * H,
        L ** 3, L * P * P, L * H * H,
        L * L * P, P ** 3, P * H * H,
        L * L * H, P * P * H, H ** 3,
    ])


class RPC:
    """Ground (lon, lat, h) -> image (line, sample) rational polynomial."""

    def __init__(self, gdal_rpc: dict):
        g = {k: v for k, v in gdal_rpc.items()}

        def _f(key):
            return float(g[key])

        def _c(key):
            v = g[key]
            if isinstance(v, str):
                v = [float(x) for x in v.split()]
            return np.asarray(v, dtype=np.float64)

        self.line_off, self.line_scale = _f("LINE_OFF"), _f("LINE_SCALE")
        self.samp_off, self.samp_scale = _f("SAMP_OFF"), _f("SAMP_SCALE")
        self.lat_off, self.lat_scale = _f("LAT_OFF"), _f("LAT_SCALE")
        self.long_off, self.long_scale = _f("LONG_OFF"), _f("LONG_SCALE")
        self.height_off, self.height_scale = _f("HEIGHT_OFF"), _f("HEIGHT_SCALE")
        self.line_num = _c("LINE_NUM_COEFF")
        self.line_den = _c("LINE_DEN_COEFF")
        self.samp_num = _c("SAMP_NUM_COEFF")
        self.samp_den = _c("SAMP_DEN_COEFF")

    def forward(self, lon, lat, h=None):
        """(lon, lat, height) -> (line, sample). Arrays broadcast; float64."""
        lon = np.asarray(lon, dtype=np.float64)
        lat = np.asarray(lat, dtype=np.float64)
        if h is None:
            h = np.full(lon.shape, self.height_off, dtype=np.float64)
        h = np.broadcast_to(np.asarray(h, dtype=np.float64), lon.shape)

        L = (lon - self.long_off) / self.long_scale
        P = (lat - self.lat_off) / self.lat_scale
        H = (h - self.height_off) / self.height_scale

        T = _rpc_terms(L.ravel(), P.ravel(), H.ravel())      # (20, n)
        line = self.line_off + self.line_scale * ((self.line_num @ T) / (self.line_den @ T))
        samp = self.samp_off + self.samp_scale * ((self.samp_num @ T) / (self.samp_den @ T))
        return line.reshape(lon.shape), samp.reshape(lon.shape)


# --------------------------------------------------------------------------
# scene discovery / metadata
# --------------------------------------------------------------------------
class Scene:
    """One Capella acquisition: paths, STAC properties, product metadata."""

    def __init__(self, folder: str):
        self.folder = folder
        self.name = os.path.basename(folder.rstrip("\\/"))
        # the June-19 directory also ships a stray copy of the June-06 SLC,
        # so the SLC is selected by exact name match with its own folder.
        want = self.name + ".tif"
        cand = [p for p in glob.glob(os.path.join(folder, "*.tif"))
                if os.path.basename(p) == want]
        if not cand:
            raise FileNotFoundError(f"no SLC matching {want}")
        self.slc = cand[0]
        prev = glob.glob(os.path.join(folder, "*_preview.tif"))
        self.preview = prev[0] if prev else None
        stac = [p for p in glob.glob(os.path.join(folder, "*.json"))
                if "extended" not in p and "digest" not in p]
        self.stac = json.load(open(stac[0]))
        self.props = self.stac["properties"]
        self.meta = json.load(open(glob.glob(os.path.join(folder, "*_extended.json"))[0]))
        self.collect = self.meta["collect"]
        self.image = self.collect["image"]

        self.datetime = self.props["datetime"]
        self.date = self.datetime[:10]
        self.scale_factor = float(self.image["scale_factor"])
        self.inc_centre = float(self.image["center_pixel"]["incidence_angle"])
        self.look = self.collect["radar"]["pointing"]
        self.orbit = self.props["sat:orbit_state"]
        self.az = float(self.props["view:azimuth"])
        self.nesz_peak = float(self.image["nesz_peak"])
        self.rows = int(self.image["rows"])
        self.cols = int(self.image["columns"])
        ig = self.image["image_geometry"]
        self.r0 = float(ig["range_to_first_sample"])
        self.dr = float(ig["delta_range_sample"])

    def __repr__(self):
        return (f"<Scene {self.date} inc={self.inc_centre:.1f} "
                f"look={self.look} az={self.az:.0f}>")

    # ---- geometry -------------------------------------------------------
    def incidence_per_column(self) -> np.ndarray:
        """Local incidence angle (radians) for every range sample.

        Spherical-Earth triangle closed on the satellite radius Rs, the local
        Earth radius Re at the scene reference target, and the slant range r.
        The incidence angle is measured from the local *up* direction, i.e.
        the supplement of the apex angle at the target:
            cos(theta_inc) = (Rs^2 - Re^2 - r^2) / (2 * Re * r)
        The spherical approximation reproduces the metadata centre incidence
        to ~0.1 deg; the profile is therefore shifted by a constant so that
        the centre sample matches `center_pixel.incidence_angle` exactly.
        The residual across-range *gradient* (~0.4 deg over the AOI) is what
        this term actually contributes.
        """
        sat = np.asarray(self.image["reference_antenna_position"], dtype=float)
        tgt = np.asarray(self.image["reference_target_position"], dtype=float)
        Rs = np.linalg.norm(sat)
        Re = np.linalg.norm(tgt)
        r = self.r0 + np.arange(self.cols, dtype=np.float64) * self.dr
        cos_i = (Rs ** 2 - Re ** 2 - r ** 2) / (2.0 * Re * r)
        inc = np.arccos(np.clip(cos_i, -1.0, 1.0))
        inc += np.radians(self.inc_centre) - inc[self.cols // 2]
        return inc

    def nesz_per_column(self) -> np.ndarray:
        """Noise-equivalent sigma-zero (linear power) per range sample."""
        c = np.asarray(self.image["nesz_polynomial"]["coefficients"], dtype=float)
        r = self.r0 + np.arange(self.cols, dtype=np.float64) * self.dr
        db = np.polyval(c[::-1], r)
        return 10.0 ** (db / 10.0)

    def rpc(self) -> RPC:
        with rasterio.open(self.slc) as ds:
            return RPC(ds.rpcs.to_gdal())


def find_scenes(data_root: str):
    folders = sorted(glob.glob(os.path.join(data_root, "CAPELLA_*")))
    folders = [f for f in folders if os.path.isdir(f)]
    return [Scene(f) for f in folders]


# --------------------------------------------------------------------------
# inverse geocoding
# --------------------------------------------------------------------------
def make_grid(bounds_utm, res):
    """Snap bounds to a `res`-metre grid; return (transform, width, height)."""
    from rasterio.transform import from_origin
    xmin, ymin, xmax, ymax = bounds_utm
    xmin = np.floor(xmin / res) * res
    ymin = np.floor(ymin / res) * res
    xmax = np.ceil(xmax / res) * res
    ymax = np.ceil(ymax / res) * res
    w = int(round((xmax - xmin) / res))
    h = int(round((ymax - ymin) / res))
    return from_origin(xmin, ymax, res, res), w, h


def geocode_scene(scene: Scene, transform, width, height, res,
                  height_m=None, dem_sample=None, geoid_offset=0.0,
                  ss=4, chunk_rows=64, verbose=True):
    """Geocode one SLC to gamma0 on a UTM grid.

    Each output cell of size `res` is filled with the mean of ss*ss
    super-sampled nearest-neighbour lookups into the slant-plane image; with
    ss=4 at res=2 m that is 16 sub-samples of ~0.9 m native pixels, i.e. an
    effective ~14-look average in the map domain.

    Terrain handling. Pass `dem_sample`, a callable (lon, lat) -> ORTHOMETRIC
    height, together with `geoid_offset` N, and every sub-sample is projected at
    its own ellipsoidal height H_ortho + N. This is terrain-referenced
    geocoding. Falling back to the scalar `height_m` assumes a flat surface,
    which over this AOI (26.6 m of relief) displaces ground range by up to 46 m
    at 30 deg incidence -- comparable to a whole field.

    Returns (gamma0_linear, valid_fraction, nesz_linear) as float32 arrays.
    """
    rpc = scene.rpc()
    if height_m is None:
        height_m = rpc.height_off

    def heights_for(lon, lat):
        if dem_sample is None:
            return height_m
        h = dem_sample(lon, lat) + geoid_offset
        return np.where(np.isfinite(h), h, height_m)

    inc = scene.incidence_per_column()          # (cols,)
    nesz_col = scene.nesz_per_column()          # (cols,)
    tan_inc = np.tan(inc).astype(np.float32)

    to_ll = Transformer.from_crs(UTM43N, WGS84, always_xy=True)

    # ---- source window covering the output grid --------------------------
    xs = transform.c + np.linspace(0, width, 40) * res
    ys = transform.f - np.linspace(0, height, 40) * res
    gx, gy = np.meshgrid(xs, ys)
    glon, glat = to_ll.transform(gx, gy)
    ln, sm = rpc.forward(glon, glat, heights_for(glon, glat))
    pad = 96
    r_lo = max(0, int(np.floor(np.nanmin(ln))) - pad)
    r_hi = min(scene.rows, int(np.ceil(np.nanmax(ln))) + pad)
    c_lo = max(0, int(np.floor(np.nanmin(sm))) - pad)
    c_hi = min(scene.cols, int(np.ceil(np.nanmax(sm))) + pad)
    if verbose:
        print(f"    src window rows {r_lo}:{r_hi} cols {c_lo}:{c_hi} "
              f"({(r_hi-r_lo)*(c_hi-c_lo)/1e6:.1f} Mpx)")

    # ---- read + calibrate the window ------------------------------------
    from rasterio.windows import Window
    with rasterio.open(scene.slc) as ds:
        z = ds.read(1, window=Window(c_lo, r_lo, c_hi - c_lo, r_hi - r_lo))
    sf = scene.scale_factor
    beta0 = (z.real.astype(np.float32) ** 2 + z.imag.astype(np.float32) ** 2) * np.float32(sf * sf)
    del z
    gam = beta0 * tan_inc[c_lo:c_hi][None, :]     # gamma0 = beta0 * tan(theta)
    del beta0
    src_h, src_w = gam.shape

    # noise floor, expressed as gamma0, for the same columns
    nesz_gam = (nesz_col[c_lo:c_hi] / np.sin(inc[c_lo:c_hi]) * np.tan(inc[c_lo:c_hi])).astype(np.float32)

    out = np.zeros((height, width), dtype=np.float32)
    cnt = np.zeros((height, width), dtype=np.float32)
    nz = np.zeros((height, width), dtype=np.float32)

    sub = (np.arange(ss) + 0.5) / ss            # sub-cell centres
    for r0 in range(0, height, chunk_rows):
        r1 = min(height, r0 + chunk_rows)
        # sub-sample coordinate mesh for this row block
        yy = transform.f - (np.repeat(np.arange(r0, r1), ss) + np.tile(sub, r1 - r0)) * res
        xx = transform.c + (np.repeat(np.arange(width), ss) + np.tile(sub, width)) * res
        X, Y = np.meshgrid(xx, yy)
        lon, lat = to_ll.transform(X, Y)
        ln, sm = rpc.forward(lon, lat, heights_for(lon, lat))
        li = np.rint(ln).astype(np.int64) - r_lo
        si = np.rint(sm).astype(np.int64) - c_lo
        ok = (li >= 0) & (li < src_h) & (si >= 0) & (si < src_w)
        li = np.where(ok, li, 0)
        si = np.where(ok, si, 0)
        vals = np.where(ok, gam[li, si], 0.0).astype(np.float32)
        nvals = np.where(ok, nesz_gam[si], 0.0).astype(np.float32)
        okf = ok.astype(np.float32)
        # block-average ss x ss -> one output cell
        nr = r1 - r0
        out[r0:r1] = vals.reshape(nr, ss, width, ss).sum(axis=(1, 3))
        cnt[r0:r1] = okf.reshape(nr, ss, width, ss).sum(axis=(1, 3))
        nz[r0:r1] = nvals.reshape(nr, ss, width, ss).sum(axis=(1, 3))

    with np.errstate(invalid="ignore", divide="ignore"):
        g = np.where(cnt > 0, out / np.maximum(cnt, 1), np.nan).astype(np.float32)
        n = np.where(cnt > 0, nz / np.maximum(cnt, 1), np.nan).astype(np.float32)
    frac = (cnt / (ss * ss)).astype(np.float32)
    return g, frac, n


def geocode_slant_array(scene: Scene, arr, r_lo, c_lo, transform, width, height, res,
                        height_m=None, dem_sample=None, geoid_offset=0.0,
                        ss=2, chunk_rows=64):
    """Geocode an arbitrary real-valued slant-range array onto the UTM grid.

    `arr` is a slant-plane raster whose (0, 0) element corresponds to image
    (row, col) = (r_lo, c_lo) -- i.e. the same window convention geocode_scene
    uses internally. Used for products derived from the SLC (sub-look coherence)
    rather than the backscatter itself.
    """
    rpc = scene.rpc()
    if height_m is None:
        height_m = rpc.height_off

    def heights_for(lon, lat):
        if dem_sample is None:
            return height_m
        h = dem_sample(lon, lat) + geoid_offset
        return np.where(np.isfinite(h), h, height_m)

    to_ll = Transformer.from_crs(UTM43N, WGS84, always_xy=True)
    src_h, src_w = arr.shape
    out = np.zeros((height, width), dtype=np.float32)
    cnt = np.zeros((height, width), dtype=np.float32)
    sub = (np.arange(ss) + 0.5) / ss

    for r0 in range(0, height, chunk_rows):
        r1 = min(height, r0 + chunk_rows)
        yy = transform.f - (np.repeat(np.arange(r0, r1), ss) + np.tile(sub, r1 - r0)) * res
        xx = transform.c + (np.repeat(np.arange(width), ss) + np.tile(sub, width)) * res
        X, Y = np.meshgrid(xx, yy)
        lon, lat = to_ll.transform(X, Y)
        ln, sm = rpc.forward(lon, lat, heights_for(lon, lat))
        li = np.rint(ln).astype(np.int64) - r_lo
        si = np.rint(sm).astype(np.int64) - c_lo
        ok = (li >= 0) & (li < src_h) & (si >= 0) & (si < src_w)
        li = np.where(ok, li, 0); si = np.where(ok, si, 0)
        vals = np.where(ok, arr[li, si], 0.0).astype(np.float32)
        okf = ok.astype(np.float32)
        nr = r1 - r0
        out[r0:r1] = vals.reshape(nr, ss, width, ss).sum(axis=(1, 3))
        cnt[r0:r1] = okf.reshape(nr, ss, width, ss).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cnt > 0, out / np.maximum(cnt, 1), np.nan).astype(np.float32)


def to_db(x):
    x = np.asarray(x, dtype=np.float64)
    return 10.0 * np.log10(np.where(x > 0, x, np.nan))


def write_tif(path, arr, transform, crs=UTM43N, nodata=np.nan, dtype="float32"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    h, w = arr.shape
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=1,
                       dtype=dtype, crs=crs, transform=transform, nodata=nodata,
                       compress="deflate", predictor=3, tiled=True,
                       blockxsize=256, blockysize=256) as ds:
        ds.write(arr.astype(dtype), 1)
