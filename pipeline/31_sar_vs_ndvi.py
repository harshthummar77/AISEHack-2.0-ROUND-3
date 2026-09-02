"""Out-of-model check: does the SAR signal track independent optical vegetation?

Two Sentinel-2 acquisitions (13 Oct 2025, 12 Nov 2025) are same-day coincident
with Capella passes, so the comparison needs no temporal interpolation.
"""
import os, sys
import numpy as np, pandas as pd
from scipy.stats import spearmanr, pearsonr
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, FIG = os.path.join(BASE, "pipeline", "out"), os.path.join(BASE, "pipeline", "fig")
sys.path.insert(0, os.path.join(BASE, "pipeline"))
from cropmodel import ACQ_DATES

long = pd.read_csv(os.path.join(OUT, "plot_stats_long.csv"))
g = long.pivot(index="plot_id", columns="date", values="g0_db")[ACQ_DATES]
st = long.pivot(index="plot_id", columns="date", values="struct_db")[ACQ_DATES]
nd = pd.read_csv(os.path.join(OUT, "plot_ndvi.csv")).set_index("plot_id")
area = long.groupby("plot_id").area_ha.first()

dg = g.sub(g[ACQ_DATES[0]], axis=0)                       # vs bare-soil baseline
ag = dg.sub(dg.median(axis=0), axis=1)                    # village anomaly per date

print("=" * 78)
print("SAME-DAY SAR vs SENTINEL-2 NDVI")
print("=" * 78)
for sar_d, s2_d in [("2025-10-13", "ndvi_2025-10-13"), ("2025-11-12", "ndvi_2025-11-12")]:
    for label, series in [("gamma0 dB", g[sar_d]), ("dgamma0 vs 6Jun", dg[sar_d]),
                          ("village anomaly", ag[sar_d]), ("struct_db", st[sar_d])]:
        m = series.notna() & nd[s2_d].notna() & (area > 0.05)
        if m.sum() > 50:
            r, p = pearsonr(series[m], nd[s2_d][m])
            rs, _ = spearmanr(series[m], nd[s2_d][m])
            print(f"  {sar_d}  {label:18s} vs NDVI : r={r:+.3f}  rho={rs:+.3f}  n={m.sum()}")
    print()

print("=" * 78)
print("NDVI SEASONAL BEHAVIOUR (all 966 plots)")
print("=" * 78)
nc = [c for c in nd.columns if c.startswith("ndvi_")]
print(nd[nc].median().to_string())
# a plot still green in mid-November is a long-duration crop (cotton / castor /
# pigeon pea); one that has gone bare has been harvested
green_nov = nd["ndvi_2025-11-12"] > 0.55
print(f"\nplots with NDVI > 0.55 on 12 Nov (long-duration / still standing): "
      f"{green_nov.sum()} ({100*green_nov.mean():.1f}%)")
print(f"plots with NDVI < 0.35 on 12 Nov (harvested / bare):             "
      f"{(nd['ndvi_2025-11-12'] < 0.35).sum()}")
print(f"\nJune 10 NDVI > 0.45 (NOT bare at the 6 June SAR baseline): "
      f"{(nd['ndvi_2025-06-10'] > 0.45).sum()} plots")

print("\nSAR anomaly by November-greenness group (dB, village-anomaly):")
grp = pd.cut(nd["ndvi_2025-11-12"], [0, .35, .45, .55, .65, 1.0])
print(ag.groupby(grp, observed=True).median().round(2).to_string())
print("\ncounts:"); print(grp.value_counts().sort_index().to_string())

# ------------------------------------------------------------------- figure
fig, ax = plt.subplots(1, 3, figsize=(17, 5.2))
for a, (sd, s2) in zip(ax[:2], [("2025-10-13", "ndvi_2025-10-13"),
                                ("2025-11-12", "ndvi_2025-11-12")]):
    m = ag[sd].notna() & nd[s2].notna() & (area > 0.05)
    a.scatter(nd[s2][m], ag[sd][m], s=8, alpha=.45, color="#2b6c4f")
    r, _ = pearsonr(ag[sd][m], nd[s2][m])
    a.set_xlabel(f"Sentinel-2 NDVI, {sd}")
    a.set_ylabel(f"SAR village anomaly $\\Delta\\gamma^0$, {sd} (dB)")
    a.set_title(f"same-day SAR vs optical  (r={r:+.2f}, n={m.sum()})")
    a.grid(alpha=.3)
ndc = [c for c in nc if nd[c].notna().sum() > 500]
ax[2].plot([c[5:] for c in ndc], nd[ndc].median(), marker="o", color="darkgreen")
ax[2].fill_between([c[5:] for c in ndc], nd[ndc].quantile(.1), nd[ndc].quantile(.9),
                   alpha=.2, color="green")
ax[2].set_ylabel("NDVI"); ax[2].set_title("village NDVI (median, 10-90%)")
ax[2].tick_params(axis="x", rotation=45); ax[2].grid(alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "val_sar_vs_ndvi.png"), dpi=130)
print("\nwrote fig/val_sar_vs_ndvi.png")
