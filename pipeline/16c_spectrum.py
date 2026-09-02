"""Measure the azimuth spectrum of the SLC before splitting it.

Sub-look processing is only valid inside the OCCUPIED Doppler band. The product
is azimuth-oversampled (0.735 m spacing against 1.23 m resolution), so a naive
split of the full sampled band puts a large fraction of empty spectrum into each
sub-look, which depresses and flattens the coherence.
"""
import os, sys
import numpy as np, rasterio
from rasterio.windows import Window
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sarlib import find_scenes

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
s = find_scenes(os.path.join(BASE, "DATA"))[0]
img = s.image
print(f"azimuth pixel spacing {img['pixel_spacing_row']:.4f} m, "
      f"azimuth resolution {img['azimuth_resolution']:.4f} m")
print(f"oversampling factor  {img['azimuth_resolution']/img['pixel_spacing_row']:.3f}")
print(f"processed azimuth bandwidth {img['processed_azimuth_bandwidth']:.1f} Hz")
prf = s.collect["radar"]["prf"][0]["prf"] if isinstance(s.collect["radar"]["prf"][0], dict) else None
print("prf entry:", str(s.collect["radar"]["prf"])[:160])

with rasterio.open(s.slc) as ds:
    z = ds.read(1, window=Window(2000, 21000, 1024, 4096)).astype(np.complex64)
print("patch", z.shape)

Z = np.fft.fftshift(np.fft.fft(z, axis=0), axes=0)
P = (np.abs(Z) ** 2).mean(axis=1)
P /= P.max()
n = len(P)
f = (np.arange(n) - n // 2) / n            # normalised frequency, -0.5 .. 0.5

pdb = 10 * np.log10(np.maximum(P, 1e-12))
print("\nazimuth power spectrum (normalised freq -> dB), every 5%:")
for frac in np.arange(-0.5, 0.51, 0.05):
    i = int((frac + 0.5) * (n - 1))
    print(f"  f={frac:+.2f}  {pdb[i]:7.2f} dB")

# occupied band = where power is within 6 dB of the peak
occ = pdb > (pdb.max() - 6.0)
lo, hi = f[occ][0], f[occ][-1]
print(f"\noccupied band (-6 dB): {lo:+.3f} .. {hi:+.3f}  "
      f"(width {hi-lo:.3f} of sampled band)")
print(f"implied usable fraction vs oversampling prediction "
      f"{1/(img['azimuth_resolution']/img['pixel_spacing_row']):.3f}")
