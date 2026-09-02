"""Adjudicate the Round-3 crop labels against the Round-2 labels using data
that NEITHER classification saw: Sentinel-2 NDVI.

The decisive physical test is November greenness. Of the five permitted crops,
cotton alone is still standing in mid-November (picking runs Oct-Jan in
Gujarat); rice is being harvested around then; maize, bajra and groundnut were
cleared in September / early October. A correct label set must therefore show
cotton clearly greenest on 12 Nov and the short-duration crops clearly bare.
"""
import os, sys
import numpy as np, pandas as pd
from scipy.stats import kruskal, spearmanr
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, FIG = os.path.join(BASE, "pipeline", "out"), os.path.join(BASE, "pipeline", "fig")
sys.path.insert(0, os.path.join(BASE, "pipeline"))
from cropmodel import CROP_NAMES

crop = pd.read_csv(os.path.join(OUT, "plot_crop.csv")).set_index("plot_id")
nd = pd.read_csv(os.path.join(OUT, "plot_ndvi.csv")).set_index("plot_id")
r2 = pd.read_csv(os.path.join(BASE, "round_2_submmision_files",
                              "farm_level_results.csv")).set_index("farm_id")
NDC = [c for c in nd.columns if c.startswith("ndvi_") and nd[c].notna().sum() > 500]
DATES = [c.replace("ndvi_", "") for c in NDC]

df = crop.join(nd[NDC]).join(r2["crop_type"].rename("r2_crop"))
df = df[df.observed]                      # only plots the SAR actually saw
print(f"validating on {len(df)} SAR-observed plots\n")


def eta2(H, n, k):
    return (H - k + 1) / (n - k)


def report(labcol, name):
    print("=" * 74); print(name); print("=" * 74)
    sub = df[df[labcol].notna()]
    print(sub.groupby(labcol)[NDC].mean().round(3).to_string())
    print("\nplots per class:", sub[labcol].value_counts().to_dict())
    res = {}
    for c in ["ndvi_2025-11-12", "ndvi_2025-10-13"]:
        grps = [gg[c].dropna().values for _, gg in sub.groupby(labcol)]
        grps = [x for x in grps if len(x) > 3]
        H, p = kruskal(*grps)
        e = eta2(H, sum(len(x) for x in grps), len(grps))
        res[c] = (H, p, e)
        print(f"  {c}: Kruskal H={H:7.1f}  p={p:.2e}  eta2={e:.3f}")
    # the physical ordering test
    nov = sub.groupby(labcol)["ndvi_2025-11-12"].mean().sort_values(ascending=False)
    print(f"  November greenness ranking: {' > '.join(nov.index)}")
    print(f"  cotton is greenest in Nov: {nov.index[0] == 'Cotton'}")
    short = [c for c in ["Maize", "Bajra", "Groundnut"] if c in nov.index]
    if short and "Cotton" in nov.index:
        gap = nov["Cotton"] - nov[short].mean()
        print(f"  NDVI gap cotton - (maize/bajra/groundnut) = {gap:+.3f}")
        res["gap"] = gap
    print()
    return res


r3res = report("crop_type", "ROUND 3  (6 passes, this work)")
r2res = report("r2_crop", "ROUND 2  (4 passes, previous submission)")

print("=" * 74)
print("HEAD-TO-HEAD on independent optical")
print("=" * 74)
for k in ["ndvi_2025-11-12", "ndvi_2025-10-13"]:
    print(f"  {k}: eta2  Round3={r3res[k][2]:.3f}   Round2={r2res[k][2]:.3f}   "
          f"-> {'Round 3' if r3res[k][2] > r2res[k][2] else 'Round 2'} separates better")
print(f"  Nov cotton-vs-short-crop NDVI gap: Round3={r3res.get('gap', np.nan):+.3f}  "
      f"Round2={r2res.get('gap', np.nan):+.3f}")

# ------------------------------------------------------------------ figure
fig, ax = plt.subplots(1, 3, figsize=(17.5, 5.4))
for a, (col, ttl) in zip(ax[:2], [("crop_type", "Round 3 labels (6 passes)"),
                                  ("r2_crop", "Round 2 labels (4 passes)")]):
    sub = df[df[col].notna()]
    for c in CROP_NAMES:
        s = sub[sub[col] == c]
        if len(s) > 3:
            a.plot(DATES, s[NDC].mean(), marker="o", label=f"{c} (n={len(s)})")
    a.set_ylabel("Sentinel-2 NDVI"); a.set_title(ttl + "\nNDVI never used in classification")
    a.tick_params(axis="x", rotation=45); a.grid(alpha=.3); a.legend(fontsize=8)
    a.set_ylim(0.25, 0.75)
sub = df[df.crop_type.notna()]
bp = [sub[sub.crop_type == c]["ndvi_2025-11-12"].dropna().values for c in CROP_NAMES]
try:
    ax[2].boxplot(bp, tick_labels=CROP_NAMES, showfliers=False)
except TypeError:
    ax[2].boxplot(bp, labels=CROP_NAMES, showfliers=False)
ax[2].set_ylabel("NDVI, 12 Nov 2025")
ax[2].set_title("November greenness by Round-3 label\n(cotton alone is still standing)")
ax[2].tick_params(axis="x", rotation=20); ax[2].grid(alpha=.3)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "val_crop_labels.png"), dpi=130)
print("\nwrote fig/val_crop_labels.png")
