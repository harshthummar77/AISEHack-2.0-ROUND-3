"""Exploratory analysis of the 966-plot x 6-date gamma0 series, before any
model is imposed. Purpose: find out what structure is actually present."""
import os, sys, json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT, FIG = os.path.join(BASE, "pipeline", "out"), os.path.join(BASE, "pipeline", "fig")
os.makedirs(FIG, exist_ok=True)
sys.path.insert(0, os.path.join(BASE, "pipeline"))
from cropmodel import ACQ_DATES, CROPS, CROP_NAMES, forward_dgamma_db

long = pd.read_csv(os.path.join(OUT, "plot_stats_long.csv"))
D = [d.replace("-", "") for d in ACQ_DATES]
g = long.pivot(index="plot_id", columns="date", values="g0_db")[ACQ_DATES]
st = long.pivot(index="plot_id", columns="date", values="struct_db")[ACQ_DATES]
area = long.groupby("plot_id").area_ha.first()

print("=" * 74)
print("gamma0 (dB) per date, over plots")
print("=" * 74)
print(g.describe(percentiles=[.05, .25, .5, .75, .95]).T.to_string())

# baseline-referenced change: removes each plot's own soil roughness term
dg = g.sub(g[ACQ_DATES[0]], axis=0)
print("\n" + "=" * 74)
print("delta gamma0 vs 6 June bare-soil baseline (dB)")
print("=" * 74)
print(dg.describe(percentiles=[.05, .25, .5, .75, .95]).T.to_string())

print("\ncorrelation between dates (dB):")
print(g.corr().round(2).to_string())

full = g.dropna()
print(f"\nplots with all 6 dates: {len(full)}")

# very dark plots = specular surfaces (ponded / puddled fields)
for d in ACQ_DATES:
    dark = (g[d] < -26).sum()
    print(f"  {d}: plots < -26 dB (near/below NESZ, specular): {dark}")

# ---------------------------------------------------------------- PCA + kmeans
Xfull = full.sub(full[ACQ_DATES[0]], axis=0)
X = Xfull[ACQ_DATES[1:]].values          # drop the identically-zero baseline column
Xs = (X - X.mean(0)) / X.std(0)
p = PCA(5).fit(Xs)
print("\nPCA explained variance ratio:", np.round(p.explained_variance_ratio_, 3))
print("PC loadings (rows = PC, cols = dates):")
print(pd.DataFrame(p.components_[:4], columns=ACQ_DATES[1:],
                   index=[f"PC{i+1}" for i in range(4)]).round(2).to_string())

for k in range(2, 8):
    km = KMeans(k, n_init=10, random_state=0).fit(Xs)
    print(f"  k={k}: inertia={km.inertia_:9.1f}  sizes={np.bincount(km.labels_)}")

km = KMeans(5, n_init=20, random_state=0).fit(Xs)
full_lab = pd.Series(km.labels_, index=full.index)
print("\nk=5 cluster mean delta-gamma0 profiles (dB vs 6 Jun):")
prof = Xfull.groupby(full_lab).mean()
prof["n"] = full_lab.value_counts().sort_index()
prof["mean_area_ha"] = area.reindex(full.index).groupby(full_lab).mean()
print(prof.round(2).to_string())

# ------------------------------------------------------------------- figures
fig, axes = plt.subplots(2, 3, figsize=(16, 9))
for ax, d in zip(axes.ravel(), ACQ_DATES):
    ax.hist(g[d].dropna(), bins=70, color="#3b6ea5")
    ax.set_title(f"{d}  (n={g[d].notna().sum()})"); ax.set_xlabel("$\\gamma^0$ dB")
fig.suptitle("Per-plot mean $\\gamma^0$ distribution by acquisition")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "explore_hist.png"), dpi=125)

fig, ax = plt.subplots(1, 3, figsize=(17, 5.2))
ax[0].scatter(dg[ACQ_DATES[2]], dg[ACQ_DATES[5]], s=7, alpha=.5)
ax[0].set_xlabel("$\\Delta\\gamma^0$ 14 Aug (dB)"); ax[0].set_ylabel("$\\Delta\\gamma^0$ 12 Nov (dB)")
ax[0].set_title("peak-season vs end-season")
ax[1].scatter(dg[ACQ_DATES[1]], dg[ACQ_DATES[3]], s=7, alpha=.5, color="darkgreen")
ax[1].set_xlabel("$\\Delta\\gamma^0$ 19 Jun (dB)"); ax[1].set_ylabel("$\\Delta\\gamma^0$ 13 Oct (dB)")
ax[1].set_title("establishment vs late season")
for c in CROP_NAMES:
    ax[2].plot(range(6), forward_dgamma_db(c), marker="o", label=c)
ax[2].set_xticks(range(6)); ax[2].set_xticklabels([d[5:] for d in ACQ_DATES], rotation=45)
ax[2].set_ylabel("$\\Delta\\gamma^0$ (dB)"); ax[2].legend(fontsize=8)
ax[2].set_title("forward-model signatures (prior)")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "explore_scatter.png"), dpi=125)

fig, ax = plt.subplots(figsize=(9, 5.5))
for c in sorted(prof.index):
    ax.plot(range(6), prof.loc[c, ACQ_DATES].values, marker="o",
            label=f"cluster {c} (n={int(prof.loc[c,'n'])})")
ax.set_xticks(range(6)); ax.set_xticklabels([d[5:] for d in ACQ_DATES], rotation=45)
ax.set_ylabel("$\\Delta\\gamma^0$ vs 6 Jun (dB)"); ax.legend(); ax.grid(alpha=.3)
ax.set_title("Unsupervised k=5 temporal clusters (no labels used)")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "explore_clusters.png"), dpi=125)
print("\nwrote fig/explore_hist.png, explore_scatter.png, explore_clusters.png")

print("\nstruct_db (10 m within-plot heterogeneity, dB) by date:")
print(st.describe(percentiles=[.25, .5, .75, .95]).T.to_string())
