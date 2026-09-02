"""Sub-aperture (sub-look) coherence — using the SLC phase without interferometry.

Repeat-pass InSAR is not available in this dataset: of the fifteen pass pairs,
five are opposite-look and nine exceed the critical baseline, and the single
geometrically viable pair (19 Jun / 14 Aug, B_perp 844 m against B_crit 3975 m)
is 56 days apart, far beyond X-band temporal coherence over a growing canopy
(see 15_baselines.py).

Sub-look processing sidesteps that entirely. Splitting the azimuth spectrum of a
SINGLE acquisition into two halves yields two looks of the same scene, separated
only in Doppler, i.e. in viewing angle by a fraction of the synthetic aperture.
The complex correlation between them,

    gamma_sub = |<s1 s2*>| / sqrt(<|s1|^2><|s2|^2>)

is high where one deterministic scatterer dominates the resolution cell (its
response is stable across the aperture) and low where the cell contains many
comparable random scatterers (speckle decorrelates between sub-looks). It is a
single-pass quantity, so there is no temporal decorrelation and no
co-registration problem at all.

Agronomically this separates fields whose X-band return is dominated by a few
strong structural elements — stems, stalks, standing residue, bunds, row
structure — from fields returning diffuse volume or rough-surface clutter. That
is information the amplitude alone does not carry, and it is available only
because the products are SLC rather than detected imagery.
"""
import json, os, sys, time
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.windows import Window

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarlib import (find_scenes, geocode_slant_array, write_tif, UTM43N)
import importlib.util as _ilu

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(BASE, "pipeline", "geo")
_spec = _ilu.spec_from_file_location("demmod", os.path.join(BASE, "pipeline", "13_dem.py"))
demmod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(demmod)
DEM_SAMPLE, _ = demmod.make_dem_sampler(demmod.fetch_dem())

man = json.load(open(os.path.join(GEO, "manifest.json")))
tr = Affine(*man["transform"]); W, H = man["width"], man["height"]; RES = man["res"]
GEOID_N = man["geoid_offset_m"]
REF_H = man["ref_height_m"]

WIN_AZ, WIN_RG = 9, 5          # coherence estimation window (slant-range pixels)
GAP = 0.10                      # spectral gap between the two sub-looks


def occupied_band(Z, drop_db=15.0):
    """Index range of the occupied azimuth band in an fftshifted spectrum.

    The product is azimuth-oversampled (0.735 m spacing against 1.23 m
    resolution), so only ~60% of the sampled band carries signal; the rest is
    ~30 dB down. Splitting the FULL band puts that empty spectrum into both
    sub-looks and flattens the coherence, which is what the first attempt did.
    """
    P = (np.abs(Z) ** 2).mean(axis=1)
    k = max(3, len(P) // 200)
    P = np.convolve(P, np.ones(k) / k, mode="same")
    pdb = 10 * np.log10(np.maximum(P, 1e-30))
    occ = np.where(pdb > pdb.max() - drop_db)[0]
    return int(occ[0]), int(occ[-1]) + 1


def sublook_coherence(z, gap=GAP, win_az=WIN_AZ, win_rg=WIN_RG, return_band=False):
    """Complex correlation between two azimuth sub-looks of one SLC."""
    n = z.shape[0]
    Z = np.fft.fftshift(np.fft.fft(z, axis=0), axes=0)
    i0, i1 = occupied_band(Z)
    Bw = i1 - i0
    g = max(1, int(Bw * gap / 2))
    mid = i0 + Bw // 2
    b1 = Z[i0:mid - g]                     # low-Doppler half of the APERTURE
    b2 = Z[mid + g:i1]                     # high-Doppler half
    L = min(b1.shape[0], b2.shape[0])
    if L < 8:
        out = np.full(z.shape, np.nan, dtype=np.float32)
        return (out, (i0, i1)) if return_band else out
    b1, b2 = b1[:L], b2[-L:]

    # Each sub-look must be brought to baseband before they are correlated:
    # they sit at different Doppler centroids, so s1 * conj(s2) would otherwise
    # carry a phase ramp along azimuth that box-averaging cancels to zero. That
    # is what produced a uniform ~0.04 on the first attempt.
    def to_baseband(band):
        out = np.zeros_like(Z)
        start = (n - L) // 2
        out[start:start + L] = band
        return np.fft.ifft(np.fft.ifftshift(out, axes=0), axis=0)

    s1 = to_baseband(b1)
    s2 = to_baseband(b2)

    num = s1 * np.conj(s2)
    p1 = (s1.real ** 2 + s1.imag ** 2)
    p2 = (s2.real ** 2 + s2.imag ** 2)

    # A cumulative-sum integral image loses catastrophic precision over an array
    # this large in float32 and produced |gamma| >> 1, which is impossible by
    # Cauchy-Schwarz. A separable moving average is numerically stable, and the
    # window size cancels between numerator and denominator, so means suffice.
    from scipy.ndimage import uniform_filter
    ksz = (win_az, win_rg)
    mre = uniform_filter(num.real.astype(np.float32), ksz, mode="nearest")
    mim = uniform_filter(num.imag.astype(np.float32), ksz, mode="nearest")
    m1 = uniform_filter(p1.astype(np.float32), ksz, mode="nearest")
    m2 = uniform_filter(p2.astype(np.float32), ksz, mode="nearest")

    den = np.sqrt(np.maximum(m1, 0) * np.maximum(m2, 0))
    with np.errstate(invalid="ignore", divide="ignore"):
        gam = np.sqrt(mre ** 2 + mim ** 2) / den
    # zero-power cells (outside the collect) carry no information
    floor = 1e-6 * float(np.nanmedian(m1[np.isfinite(m1) & (m1 > 0)]) or 1.0)
    gam = np.where(den > floor, gam, np.nan)
    gam = np.clip(gam, 0.0, 1.0).astype(np.float32)
    return (gam, (i0, i1)) if return_band else gam


def window_for(scene, rpc_pad=96):
    """Slant-range window covering the AOI, same convention as geocode_scene."""
    from pyproj import Transformer
    rpc = scene.rpc()
    to_ll = Transformer.from_crs(UTM43N, "EPSG:4326", always_xy=True)
    xs = tr.c + np.linspace(0, W, 40) * RES
    ys = tr.f - np.linspace(0, H, 40) * RES
    gx, gy = np.meshgrid(xs, ys)
    lon, lat = to_ll.transform(gx, gy)
    h = DEM_SAMPLE(lon, lat) + GEOID_N
    h = np.where(np.isfinite(h), h, REF_H)
    ln, sm = rpc.forward(lon, lat, h)
    r_lo = max(0, int(np.floor(np.nanmin(ln))) - rpc_pad)
    r_hi = min(scene.rows, int(np.ceil(np.nanmax(ln))) + rpc_pad)
    c_lo = max(0, int(np.floor(np.nanmin(sm))) - rpc_pad)
    c_hi = min(scene.cols, int(np.ceil(np.nanmax(sm))) + rpc_pad)
    return r_lo, r_hi, c_lo, c_hi


if __name__ == "__main__":
    scenes = find_scenes(os.path.join(BASE, "DATA"))
    summary = []
    for s in scenes:
        t0 = time.time()
        r_lo, r_hi, c_lo, c_hi = window_for(s)
        with rasterio.open(s.slc) as ds:
            z = ds.read(1, window=Window(c_lo, r_lo, c_hi - c_lo, r_hi - r_lo))
        z = z.astype(np.complex64)
        gam = sublook_coherence(z)
        del z
        g = geocode_slant_array(s, gam, r_lo, c_lo, tr, W, H, RES,
                                height_m=REF_H, dem_sample=DEM_SAMPLE,
                                geoid_offset=GEOID_N, ss=2, chunk_rows=64)
        del gam
        tag = s.date.replace("-", "")
        write_tif(os.path.join(GEO, f"subcoh_{tag}.tif"), g, tr)
        q = np.nanpercentile(g, [5, 25, 50, 75, 95])
        summary.append({"date": s.date, "p05": float(q[0]), "p50": float(q[2]),
                        "p95": float(q[4])})
        print(f"{s.date}: sub-look coherence p05/p25/p50/p75/p95 = "
              f"{q[0]:.3f} / {q[1]:.3f} / {q[2]:.3f} / {q[3]:.3f} / {q[4]:.3f}"
              f"   [{time.time()-t0:.0f}s]")
    json.dump(summary, open(os.path.join(GEO, "sublook_summary.json"), "w"), indent=1)
    print("\nwrote subcoh_*.tif and geo/sublook_summary.json")
