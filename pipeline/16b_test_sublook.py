"""Sanity-check the sub-look coherence estimator.

A correct estimator must separate deterministic scatterers from clutter:
strong point-like targets (buildings, poles, bunds) should approach 1, while
distributed speckle should sit near the value expected for the number of
independent looks in the window. A flat map is a broken estimator.
"""
import os, sys
import numpy as np, rasterio
from rasterio.windows import Window
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarlib import find_scenes
import importlib.util as _ilu
_s = _ilu.spec_from_file_location("sl", os.path.join(os.path.dirname(os.path.abspath(__file__)), "16_sublook.py"))
sl = _ilu.module_from_spec(_s); _s.loader.exec_module(sl)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
s = find_scenes(os.path.join(BASE, "DATA"))[0]
r_lo, r_hi, c_lo, c_hi = sl.window_for(s)
# a modest patch in the middle of the AOI window
R0 = (r_lo + r_hi) // 2 - 1200
C0 = (c_lo + c_hi) // 2 - 900
with rasterio.open(s.slc) as ds:
    z = ds.read(1, window=Window(C0, R0, 1800, 2400)).astype(np.complex64)
print("patch", z.shape)

amp = np.abs(z)
adb = 20 * np.log10(np.maximum(amp, 1e-6))
gam = sl.sublook_coherence(z)

ok = np.isfinite(gam)
print(f"\nsub-look coherence: p05={np.nanpercentile(gam,5):.3f} "
      f"p50={np.nanpercentile(gam,50):.3f} p95={np.nanpercentile(gam,95):.3f} "
      f"max={np.nanmax(gam):.3f}")

# the discriminating test: coherence must rise with scatterer dominance
thr = np.nanpercentile(adb[ok], [50, 90, 99, 99.9])
for name, lo, hi in [("clutter  (<p50 amp)", -1e9, thr[0]),
                     ("moderate (p50-p90)", thr[0], thr[1]),
                     ("bright   (p90-p99)", thr[1], thr[2]),
                     ("very bright (p99-p99.9)", thr[2], thr[3]),
                     ("point-like  (>p99.9)", thr[3], 1e9)]:
    m = ok & (adb > lo) & (adb <= hi)
    if m.sum() > 100:
        print(f"  {name:26s} n={m.sum():8d}  mean gamma = {np.nanmean(gam[m]):.3f}")

r = np.corrcoef(adb[ok], gam[ok])[0, 1]
print(f"\ncorrelation(amplitude dB, sub-look coherence) = {r:+.3f}")
print("expected: clearly positive, with point-like targets approaching 1")
