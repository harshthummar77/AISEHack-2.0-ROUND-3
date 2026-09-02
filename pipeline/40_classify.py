"""Stage 3 -- crop assignment for 966 plots from the full six-pass series.

Design decisions, and why:

* Village-anomaly features. Every feature is a plot value minus the village
  median for that same acquisition. This removes, in one step and without
  fitting anything, the per-scene effects we cannot separate otherwise:
  absolute calibration, receiver gain, incidence-angle response, look
  direction, and the seasonal soil-moisture excursion common to all fields.

* Geometry-safe differences. The six passes span 28.7-35.2 deg incidence, so a
  difference between two arbitrary dates mixes crop signal with geometry. Two
  pairs are effectively geometry-free:
      19 Jun -> 14 Aug   incidence 28.77 -> 28.69 deg  (0.08 deg), same look
      13 Oct -> 12 Nov   incidence 31.53 -> 29.75 deg  (1.78 deg), same look
  The first measures canopy establishment; the second, new in Round 3, measures
  late-season retention versus harvest. The 29 Oct pass is right-looking from
  the opposite azimuth and is used only as a corroborating feature, never on
  its own.

* No optical data enters the classification, so Sentinel-2 NDVI remains a
  genuinely independent test of the labels.

* Area-constrained assignment. The Round-1 village crop composition is the
  official carry-forward and is imposed as a hard area constraint through a
  transportation LP, exactly as in Round 2, so the two rounds stay comparable.
"""
import json, os, sys
import numpy as np, pandas as pd
from scipy.optimize import linprog

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "pipeline", "out")
sys.path.insert(0, os.path.join(BASE, "pipeline"))
from cropmodel import ACQ_DATES, CROP_NAMES, DISTRICT_AREA_00HA

# Round-1 village composition for Sokhda, carried forward (ha).
ROUND1_HA = {"Cotton": 136.03, "Groundnut": 92.38, "Rice": 44.59,
             "Maize": 25.80, "Bajra": 25.70}

# ---------------------------------------------------------------- load
long = pd.read_csv(os.path.join(OUT, "plot_stats_long.csv"))
g = long.pivot(index="plot_id", columns="date", values="g0_db")[ACQ_DATES]
cv = long.pivot(index="plot_id", columns="date", values="cv_lin")[ACQ_DATES]
area = long.groupby("plot_id").area_ha.first()
nobs = g.notna().sum(axis=1)
D6, D19, DAU, DOC, DO2, DNV = ACQ_DATES

# ---------------------------------------------------------------- features
def anom(s):
    return s - s.median()

F = pd.DataFrame(index=g.index)
F["a_jun"] = anom(g[D19])                       # monsoon-onset response
F["a_est"] = anom(g[DAU] - g[D19])              # establishment  (0.08 deg pair)
F["a_oct"] = anom(g[DOC])                       # standing canopy at grain fill
F["a_sen"] = anom(g[DNV] - g[DOC])              # late retention (1.78 deg pair)
F["a_lat"] = anom(g[DO2] - g[DAU])              # corroborating late-season change
FEATS = ["a_jun", "a_est", "a_oct", "a_sen", "a_lat"]

# robust standardisation (median / IQR) so a few built-up plots cannot dominate
Z = pd.DataFrame(index=F.index)
scale = {}
for c in FEATS:
    v = F[c]
    q1, q3 = v.quantile(.25), v.quantile(.75)
    s = max((q3 - q1) / 1.349, 1e-6)
    scale[c] = {"med": float(v.median()), "iqr_sd": float(s)}
    Z[c] = ((v - v.median()) / s).clip(-4, 4)

print("feature summary (village-anomaly, dB):")
print(F[FEATS].describe(percentiles=[.1, .5, .9]).T.to_string())

# ------------------------------------------------- phenological templates
# Expected sign and relative magnitude of each feature per crop, in the same
# robust-z units. Derived from the Gujarat kharif calendar (see cropmodel.py)
# and X-band HH scattering behaviour, NOT fitted to these data.
TEMPLATE = pd.DataFrame(
    {"a_jun": {"Rice": -1.00, "Cotton": +0.20, "Maize": +0.10, "Bajra": +0.10, "Groundnut": +0.10},
     "a_est": {"Rice": +1.00, "Cotton": +0.50, "Maize": +1.00, "Bajra": +0.20, "Groundnut": -1.00},
     "a_oct": {"Rice": +0.80, "Cotton": +0.90, "Maize": -0.70, "Bajra": -1.00, "Groundnut": -0.50},
     "a_sen": {"Rice": -1.20, "Cotton": +0.90, "Maize": +0.20, "Bajra": +0.20, "Groundnut": +0.10},
     "a_lat": {"Rice": +0.50, "Cotton": +0.90, "Maize": -0.80, "Bajra": -1.10, "Groundnut": -0.60}}
)[FEATS].loc[CROP_NAMES]
print("\nphenological templates (robust-z units):")
print(TEMPLATE.to_string())

# --------------------------------------------------- cost = template mismatch
# Missing dates simply drop out of the sum, so partially observed plots are
# scored on what they do have rather than being discarded.
FEAT_W = np.array([1.0, 1.3, 1.2, 1.4, 0.8])     # weight: new Round-3 pair highest
cost = pd.DataFrame(index=Z.index, columns=CROP_NAMES, dtype=float)
navail = pd.Series(0, index=Z.index)
for crop in CROP_NAMES:
    t = TEMPLATE.loc[crop].values
    d = (Z[FEATS].values - t[None, :]) ** 2 * FEAT_W[None, :]
    ok = np.isfinite(d)
    navail = pd.Series(ok.sum(1), index=Z.index)
    cost[crop] = np.where(ok.sum(1) > 0,
                          np.nansum(d, axis=1) / np.maximum((ok * FEAT_W[None, :]).sum(1), 1e-9),
                          np.nan)

soft = np.exp(-0.5 * cost.values)
soft = soft / np.nansum(soft, axis=1, keepdims=True)
POST = pd.DataFrame(soft, index=cost.index, columns=CROP_NAMES)

scorable = cost.dropna(how="all").index
print(f"\nplots scorable: {len(scorable)} / {len(cost)}")
print("unconstrained argmin-cost assignment (area ha):")
raw = cost.loc[scorable].idxmin(axis=1)
print(area.reindex(scorable).groupby(raw).sum().round(1).to_string())

# ------------------------------------------------ area-constrained assignment
A = area.reindex(scorable).fillna(0.0).values
C = cost.loc[scorable, CROP_NAMES].values
n, k = C.shape

tot_target = A.sum()
share = np.array([ROUND1_HA[c] for c in CROP_NAMES], dtype=float)
share = share / share.sum()
target_ha = share * tot_target
print(f"\narea-constrained targets (scaled to {tot_target:.1f} ha of scorable plots):")
for c, t in zip(CROP_NAMES, target_ha):
    print(f"   {c:10s} {t:7.2f} ha")

# variables x[i,j] = fraction of plot i assigned to crop j; objective = area-
# weighted mismatch. Row sums = 1, column area sums = target.
cvec = (C * A[:, None]).ravel()
rows, cols, vals = [], [], []
for i in range(n):
    for j in range(k):
        rows.append(i); cols.append(i * k + j); vals.append(1.0)
Aeq_rows = n
for j in range(k):
    for i in range(n):
        rows.append(Aeq_rows + j); cols.append(i * k + j); vals.append(A[i])
from scipy.sparse import coo_matrix
Aeq = coo_matrix((vals, (rows, cols)), shape=(n + k, n * k))
beq = np.concatenate([np.ones(n), target_ha])
res = linprog(cvec, A_eq=Aeq, b_eq=beq, bounds=(0, 1), method="highs")
print(f"\nLP status: {res.message} (obj={res.fun:.1f})")

Xlp = res.x.reshape(n, k)
lab_idx = Xlp.argmax(axis=1)
labels = pd.Series([CROP_NAMES[j] for j in lab_idx], index=scorable, name="crop_type")
frac = pd.Series(Xlp.max(axis=1), index=scorable)
print(f"fractional at vertex (max frac < 0.99): {(frac < 0.99).sum()}")

# confidence: posterior of the assigned class, tempered by how many features
# the plot actually had
conf = pd.Series([POST.loc[i, labels[i]] for i in scorable], index=scorable)
conf = conf * (navail.reindex(scorable) / len(FEATS)).clip(0, 1)

crop = pd.Series(index=g.index, dtype=object)
crop.loc[scorable] = labels
# unobserved plots: assign the village's dominant crop with zero confidence and
# flag them, rather than dropping them from the deliverable
unobs = crop[crop.isna()].index
crop.loc[unobs] = "Cotton"
conf = conf.reindex(g.index).fillna(0.0)

out = pd.DataFrame({"crop_type": crop, "crop_confidence": conf.round(4),
                    "area_ha": area, "n_obs": nobs,
                    "observed": (~g.index.isin(unobs))})
for c in FEATS:
    out[c] = F[c].round(3)
for c in CROP_NAMES:
    out["p_" + c] = POST[c].round(4)
out.to_csv(os.path.join(OUT, "plot_crop.csv"))

print("\nFINAL ASSIGNMENT")
summ = out.groupby("crop_type").agg(plots=("area_ha", "size"), area_ha=("area_ha", "sum"),
                                    med_conf=("crop_confidence", "median"))
summ["target_ha"] = [ROUND1_HA[c] / sum(ROUND1_HA.values()) * tot_target for c in summ.index]
print(summ.round(2).to_string())
print(f"\nunobserved plots defaulted (flagged): {len(unobs)}")

# ------------------------------------------------- comparison with Round 2
R2_PATH = os.path.join(BASE, "round_2_submmision_files", "farm_level_results.csv")
r2 = pd.read_csv(R2_PATH).set_index("farm_id") if os.path.exists(R2_PATH) else None
agree_obs = pd.Series(dtype=float)
if r2 is None:
    print("\nRound-2 results not present; skipping the label comparison.")
else:
    j = out.join(r2["crop_type"].rename("r2_crop"))
    agree = (j.crop_type == j.r2_crop)
    # The headline figure counts only plots the SAR actually observed: the 43
    # unobserved plots were defaulted to the dominant crop, so letting them
    # count as "agreement" would flatter both label sets.
    jo = j[j.observed]
    agree_obs = (jo.crop_type == jo.r2_crop)
    print(f"\nagreement with Round-2 labels, SAR-observed plots: "
          f"{agree_obs.sum()}/{len(jo)} = {100*agree_obs.mean():.1f}%")
    print(f"  (including the {len(j)-len(jo)} defaulted unobserved plots: "
          f"{agree.sum()}/{len(j)} = {100*agree.mean():.1f}%)")
    print(pd.crosstab(j.r2_crop, j.crop_type).to_string())

json.dump({"round1_ha": ROUND1_HA, "target_ha": dict(zip(CROP_NAMES, target_ha.tolist())),
           "feature_scale": scale, "lp_status": res.message,
           "agreement_with_round2_observed": (float(agree_obs.mean())
                                              if len(agree_obs) else None)},
          open(os.path.join(OUT, "classify_meta.json"), "w"), indent=1)
print("\nwrote plot_crop.csv, classify_meta.json")
