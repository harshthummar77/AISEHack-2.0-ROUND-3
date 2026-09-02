"""Does sub-look coherence earn its place in the model?

Tested honestly, against three questions:
  1. Is the per-plot signal real, or scene-wide noise? (temporal repeatability)
  2. Is it independent of the amplitude we already use?
  3. Does it separate crops or track independent optical vegetation?

A feature that fails all three gets reported as a negative result, not shipped.
"""
import os, sys
import numpy as np, pandas as pd
from scipy.stats import spearmanr, kruskal

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "pipeline", "out")
sys.path.insert(0, os.path.join(BASE, "pipeline"))
from cropmodel import ACQ_DATES, CROP_NAMES

long = pd.read_csv(os.path.join(OUT, "plot_stats_long.csv"))
sc = long.pivot(index="plot_id", columns="date", values="subcoh")[ACQ_DATES]
g = long.pivot(index="plot_id", columns="date", values="g0_db")[ACQ_DATES]
cv = long.pivot(index="plot_id", columns="date", values="cv_lin")[ACQ_DATES]
nd = pd.read_csv(os.path.join(OUT, "plot_ndvi.csv")).set_index("plot_id")
r2 = pd.read_csv(os.path.join(BASE, "round_2_submmision_files",
                              "farm_level_results.csv")).set_index("farm_id")
crop = r2["crop_type"].reindex(sc.index)

print("per-plot sub-look coherence by date")
print(sc.describe(percentiles=[.1, .5, .9]).T.to_string())

print("\n1. TEMPORAL REPEATABILITY  (is the per-plot pattern real?)")
C = sc.corr()
iu = np.triu_indices(len(ACQ_DATES), 1)
print(C.round(2).to_string())
print(f"   mean off-diagonal correlation between dates: {C.values[iu].mean():.3f}")
print("   a stable plot-level property should repeat across independent acquisitions")

print("\n2. INDEPENDENCE FROM AMPLITUDE")
for d in ACQ_DATES:
    m = sc[d].notna() & g[d].notna()
    r_amp, _ = spearmanr(sc[d][m], g[d][m])
    r_cv, _ = spearmanr(sc[d][m], cv[d][m])
    print(f"   {d}: rho(subcoh, gamma0) = {r_amp:+.3f}   rho(subcoh, CV) = {r_cv:+.3f}")

print("\n3. AGRONOMIC CONTENT")
smean = sc.mean(axis=1)
for label, series in [("season-mean subcoh", smean),
                      ("subcoh 14 Aug", sc[ACQ_DATES[2]]),
                      ("subcoh 12 Nov", sc[ACQ_DATES[5]])]:
    for s2 in ["ndvi_2025-10-13", "ndvi_2025-11-12"]:
        m = series.notna() & nd[s2].notna()
        r, p = spearmanr(series[m], nd[s2][m])
        print(f"   {label:20s} vs {s2}: rho={r:+.3f} p={p:.2g} n={m.sum()}")

print("\n   by crop (season-mean sub-look coherence):")
df = pd.DataFrame({"crop": crop, "sc": smean}).dropna()
print(df.groupby("crop").sc.agg(["count", "mean", "std"]).round(4).to_string())
grps = [x["sc"].values for _, x in df.groupby("crop") if len(x) > 3]
H, p = kruskal(*grps)
eta2 = (H - len(grps) + 1) / (len(df) - len(grps))
print(f"   Kruskal H={H:.1f}  p={p:.2g}  eta2={eta2:.4f}")

print("\n   temporal CHANGE in coherence (structure appearing / disappearing):")
d_est = sc[ACQ_DATES[2]] - sc[ACQ_DATES[1]]      # 19 Jun -> 14 Aug
d_sen = sc[ACQ_DATES[5]] - sc[ACQ_DATES[3]]      # 13 Oct -> 12 Nov
for nm, s in [("subcoh 14Aug-19Jun", d_est), ("subcoh 12Nov-13Oct", d_sen)]:
    dd = pd.DataFrame({"crop": crop, "v": s}).dropna()
    gg = [x["v"].values for _, x in dd.groupby("crop") if len(x) > 3]
    H, p = kruskal(*gg)
    e = (H - len(gg) + 1) / (len(dd) - len(gg))
    print(f"   {nm}: Kruskal H={H:6.1f} p={p:.2g} eta2={e:.4f}")
    print("     " + dd.groupby("crop").v.mean().round(4).to_string().replace("\n", "\n     "))

print("\nVERDICT INPUTS: repeatability, independence, and agronomic separation above.")
