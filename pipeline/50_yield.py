"""Stage 4 -- final yield FORECAST for 966 plots, and village aggregation.

Framing
-------
Round 2 delivered yield *to date* on 13 October. Round 3 must deliver the yield
at harvest. The six passes cover the five crops very unevenly, and the method
is built around that fact rather than around it:

    crop        cycle covered by the 6 passes        forecast content
    Rice        sowing -> harvest, fully             reconstruction
    Maize       sowing -> (60-day gap) -> stubble    partial, 1 in-season look
    Bajra       sowing -> (60-day gap) -> stubble    partial, 1 in-season look
    Groundnut   sowing -> (60-day gap) -> stubble    partial, 1 in-season look
    Cotton      sowing -> mid-picking (12 Nov)       genuine extrapolation

The 14 Aug -> 13 Oct gap of 60 days brackets the entire maturity and harvest of
the three short-duration crops, so for those the yield-determining period is
sampled once. That is not hidden; it is what drives their wider intervals.

Absolute level
--------------
With no ground truth, SAR cannot set the absolute yield level, only the
*ranking and spread* between plots. So the level is anchored to the Vadodara
district yield for each crop (Directorate of Agriculture, Gujarat, 2022-23),
adjusted for the 2025 season, and the SAR supplies the within-village
distribution. This is stated as an assumption, not a result.

    Y_p = Y_ref(c) . S(c) . exp( s_c.rho.z_p  -  (s_c.rho)^2 / 2 )

z_p is the standardised SAR yield index within crop c, s_c the farm-to-farm
yield CV within a village, and rho the fraction of that spread the SAR index
actually explains. The lognormal form makes the area-weighted village mean
reproduce Y_ref(c).S(c) by construction while giving a right-skewed plot
distribution, which is what farm yield distributions look like.
"""
import json, os, sys
import numpy as np, pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "pipeline", "out")
sys.path.insert(0, os.path.join(BASE, "pipeline"))
from cropmodel import ACQ_DATES, CROP_NAMES, CROPS, season_factor

RNG = np.random.default_rng(20260902)
NSIM = 4000

# farm-to-farm yield CV within one village (s_c), and the fraction of that
# spread a 6-pass X-band series can explain (rho)
YIELD_CV = {"Rice": 0.28, "Cotton": 0.35, "Maize": 0.32,
            "Bajra": 0.35, "Groundnut": 0.33}
RHO = 0.55
RHO_RANGE = (0.40, 0.70)

# fraction of the yield-determining cycle actually observed by the six passes
SEASON_OBS = {"Rice": 1.00, "Cotton": 0.78, "Maize": 0.55,
              "Bajra": 0.50, "Groundnut": 0.60}

# ---------------------------------------------------------------------------
# Cotton is the only crop still in the field at the last acquisition, so it is
# the only one whose forecast is a genuine extrapolation rather than a
# reconstruction. Gujarat BT cotton is picked from late October into January;
# the first two pickings carry roughly 70% of final lint, and the remainder
# depends on whether the plant holds a green canopy through November to support
# later flushes. We therefore split the cotton forecast explicitly:
#
#   Y_cotton = Y_base * [ F_SET + (1 - F_SET) * (1 + KAPPA_RET * z_ret) ]
#
# F_SET is the fraction of final lint already determined by 12 Nov; the second
# term forecasts the later pickings from the plot's own late-season canopy
# retention (13 Oct -> 12 Nov, the geometry-safe pair). This is what makes the
# 12 Nov acquisition do real work rather than merely being another sample.
F_SET_COTTON = 0.70
KAPPA_RET = 0.35

# stage weights for the SAR yield index, per crop
#   est = establishment (14 Aug - 19 Jun, geometry-safe)
#   oct = standing canopy on 13 Oct
#   ret = late retention (12 Nov - 13 Oct, geometry-safe) -- boll load for cotton
#   uni = within-field uniformity (speckle-corrected CV, inverted)
WEIGHTS = {
    "Rice":      {"est": 0.35, "oct": 0.40, "ret": 0.00, "uni": 0.25},
    "Cotton":    {"est": 0.25, "oct": 0.25, "ret": 0.25, "uni": 0.25},
    "Maize":     {"est": 0.55, "oct": 0.15, "ret": 0.00, "uni": 0.30},
    "Bajra":     {"est": 0.55, "oct": 0.15, "ret": 0.00, "uni": 0.30},
    "Groundnut": {"est": 0.55, "oct": 0.15, "ret": 0.00, "uni": 0.30},
}

# ------------------------------------------------------------------ inputs
long = pd.read_csv(os.path.join(OUT, "plot_stats_long.csv"))
g = long.pivot(index="plot_id", columns="date", values="g0_db")[ACQ_DATES]
cvl = long.pivot(index="plot_id", columns="date", values="cv_lin")[ACQ_DATES]
area = long.groupby("plot_id").area_ha.first()
D6, D19, DAU, DOC, DO2, DNV = ACQ_DATES

mine = pd.read_csv(os.path.join(OUT, "plot_crop.csv")).set_index("plot_id")
r2 = pd.read_csv(os.path.join(BASE, "round_2_submmision_files",
                              "farm_level_results.csv")).set_index("farm_id")

# Primary labels = Round-2 carry-forward (official continuity, and the label set
# that separates independent Sentinel-2 NDVI better; see 41_validate_crop.py).
crop = r2["crop_type"].reindex(g.index)
# Posterior from the independent 6-pass classifier, used ONLY to propagate how
# uncertain the labels are into the yield intervals.
PCOLS = ["p_" + c for c in CROP_NAMES]
post = mine[PCOLS].reindex(g.index)
post.columns = CROP_NAMES
post = post.div(post.sum(axis=1), axis=0)

# blend: keep the carry-forward label as the mode, let the SAR posterior spread
# probability onto the alternatives
LBL_W = 0.60
lblp = pd.DataFrame(0.0, index=g.index, columns=CROP_NAMES)
for c in CROP_NAMES:
    lblp[c] = (1 - LBL_W) * post[c].fillna(1.0 / 5)
for i, c in crop.items():
    if isinstance(c, str):
        lblp.loc[i, c] += LBL_W
lblp = lblp.div(lblp.sum(axis=1), axis=0)

# ------------------------------------------------------- SAR yield index
def anom(s):
    return s - s.median()

feat = pd.DataFrame(index=g.index)
feat["est"] = anom(g[DAU] - g[D19])
feat["oct"] = anom(g[DOC])
feat["ret"] = anom(g[DNV] - g[DOC])
# uniformity: mean in-season within-field CV, inverted (low CV = even stand)
uni_raw = cvl[[DAU, DOC]].mean(axis=1)
feat["uni"] = -anom(uni_raw)

# robust standardisation, computed once over the whole village
Zf = pd.DataFrame(index=g.index)
for c in ["est", "oct", "ret", "uni"]:
    v = feat[c]
    s = max((v.quantile(.75) - v.quantile(.25)) / 1.349, 1e-9)
    Zf[c] = ((v - v.median()) / s).clip(-3, 3)

print("standardised SAR index components:")
print(Zf.describe(percentiles=[.1, .5, .9]).T.to_string())


def zindex(crop_name):
    """Stage-weighted, renormalised SAR yield index for one crop."""
    w = WEIGHTS[crop_name]
    num = pd.Series(0.0, index=Zf.index)
    den = pd.Series(0.0, index=Zf.index)
    for k, wk in w.items():
        if wk == 0:
            continue
        v = Zf[k]
        num = num.add((v * wk).fillna(0.0))
        den = den.add(pd.Series(np.where(v.notna(), wk, 0.0), index=Zf.index))
    z = num / den.replace(0, np.nan)
    # renormalise to unit variance so s_c keeps its meaning
    return (z - z.median()) / max(z.std(), 1e-9), den > 0


ZIDX = {c: zindex(c) for c in CROP_NAMES}

# --------------------------------------------------------- Monte Carlo
n = len(g.index)
crops_arr = np.array(CROP_NAMES)
P = lblp[CROP_NAMES].values
Yref = np.array([CROPS[c]["yield_ref"] for c in CROP_NAMES])
Sfac = np.array([season_factor(c) for c in CROP_NAMES])
Scv = np.array([YIELD_CV[c] for c in CROP_NAMES])
Zmat = np.column_stack([ZIDX[c][0].reindex(g.index).values for c in CROP_NAMES])
Zok = np.column_stack([ZIDX[c][1].reindex(g.index).fillna(False).values for c in CROP_NAMES])
Zmat = np.where(Zok, Zmat, 0.0)
Zmat = np.nan_to_num(Zmat, nan=0.0)
observed = pd.Series(Zok.any(axis=1), index=g.index)

jbest = np.array([CROP_NAMES.index(c) if isinstance(c, str) else 1 for c in crop])
zb = np.where(observed.values, Zmat[np.arange(n), jbest], 0.0)
scb = Scv[jbest]
areav = area.reindex(g.index).values
obsfrac_b = np.array([SEASON_OBS[c] for c in CROP_NAMES])[jbest]

# Central forecast, conditional on the carry-forward label. The multiplicative
# shape comes from the SAR index; the level is then rescaled within each crop so
# that the AREA-WEIGHTED village mean is exactly the district reference for that
# crop times the 2025 season factor. Without ground truth there is no basis for
# claiming Sokhda departs from its district mean, so that anchor is imposed
# rather than estimated, and every plot-to-plot difference below it is SAR-driven.
shape = np.exp(scb * RHO * zb - 0.5 * (scb * RHO) ** 2)

# explicit forecast extension for the one crop still standing on 12 Nov
z_ret = np.nan_to_num(Zf["ret"].reindex(g.index).values, nan=0.0)
is_cotton = jbest == CROP_NAMES.index("Cotton")
late_mult = np.ones(n)
late_mult[is_cotton] = (F_SET_COTTON
                        + (1 - F_SET_COTTON) * np.clip(1 + KAPPA_RET * z_ret[is_cotton],
                                                       0.3, 1.9))
shape = shape * late_mult
print(f"\ncotton forecast extension: {is_cotton.sum()} plots, "
      f"late-picking multiplier {late_mult[is_cotton].min():.3f}-"
      f"{late_mult[is_cotton].max():.3f} (mean {late_mult[is_cotton].mean():.3f})")

central = np.empty(n)
anchor_scale = {}
for jj, c in enumerate(CROP_NAMES):
    m = jbest == jj
    if not m.any():
        continue
    target = Yref[jj] * Sfac[jj]
    wmean = (shape[m] * areav[m]).sum() / areav[m].sum()
    k = target / wmean
    anchor_scale[c] = float(k)
    central[m] = shape[m] * k

# Monte Carlo CONDITIONAL ON THE LABEL: the crop group is held fixed, so the
# interval for "cotton yield" is genuinely an interval for cotton. Label
# uncertainty is handled separately below, where it belongs -- as uncertainty in
# which plots are cotton at all.
kvec = np.array([anchor_scale.get(CROP_NAMES[j], 1.0) for j in jbest])

# The error budget is deliberately split into terms that are SYSTEMATIC across a
# crop and terms that are INDEPENDENT between plots, because only the second
# kind averages away on aggregation. Getting this wrong is the usual reason
# village-level intervals come out implausibly tight:
#   systematic  - the district reference yield, the 2025 season adjustment, and
#                 most of the forecast-horizon risk (the weather over the
#                 remaining cotton picking period is common to every cotton plot)
#   independent - the part of plot-to-plot yield spread the SAR index does not
#                 explain, and a small idiosyncratic forecast term
SYS_FCAST = 0.85
sims = np.empty((NSIM, n), dtype=np.float32)
for s in range(NSIM):
    rho = RNG.uniform(*RHO_RANGE)
    # one draw per crop, shared by every plot of that crop
    eps_ref_c = RNG.normal(1.0, 0.12, len(CROP_NAMES))
    eps_sea_c = RNG.normal(1.0, 0.06, len(CROP_NAMES))
    fsys_c = RNG.normal(0.0, 1.0, len(CROP_NAMES))
    eps_ref = eps_ref_c[jbest]
    eps_sea = eps_sea_c[jbest]
    fh = scb * 0.45 * (1 - obsfrac_b)
    fcast_sys = fh * SYS_FCAST * fsys_c[jbest]
    fcast_idio = fh * np.sqrt(max(1 - SYS_FCAST ** 2, 0.0)) * RNG.normal(0, 1, n)
    expl = scb * rho * zb
    unexp = scb * np.sqrt(max(1 - rho ** 2, 0.0)) * RNG.normal(0, 1, n)
    unexp = unexp * np.where(observed.values, 1.0, 1.6)    # unobserved plots wider
    sims[s] = kvec * late_mult * eps_ref * eps_sea * np.exp(
        expl + unexp + fcast_sys + fcast_idio
        - 0.5 * (scb * rho) ** 2 - 0.5 * (scb ** 2) * (1 - rho ** 2))

print(f"\nMonte Carlo (label-conditional): {NSIM} draws x {n} plots done")
p10 = np.percentile(sims, 10, axis=0)
p50 = np.percentile(sims, 50, axis=0)
p90 = np.percentile(sims, 90, axis=0)

res = pd.DataFrame({
    "village_id": 22, "village_name": "Sokhda", "farm_id": g.index,
    "crop_type": crop.values, "area_ha": area.reindex(g.index).values,
    "yield_forecast_kg_ha": np.round(central, 1),
    "yield_p10_kg_ha": np.round(p10, 1),
    "yield_p50_kg_ha": np.round(p50, 1),
    "yield_p90_kg_ha": np.round(p90, 1),
    "sar_yield_index_z": np.round(zb, 3),
    "season_observed_frac": [SEASON_OBS[c] if isinstance(c, str) else np.nan for c in crop],
    "crop_confidence_r3": mine["crop_confidence"].reindex(g.index).values,
    "observed": observed.values,
    "n_sar_dates": g.notna().sum(axis=1).values,
}).set_index("farm_id")
res["production_t"] = (res.yield_forecast_kg_ha * res.area_ha / 1000).round(3)
for k in ["est", "oct", "ret", "uni"]:
    res["z_" + k] = Zf[k].round(3).values
for d, nm in zip(ACQ_DATES, ["06Jun", "19Jun", "14Aug", "13Oct", "29Oct", "12Nov"]):
    res["gamma0_dB_" + nm] = g[d].round(3).values
res.to_csv(os.path.join(OUT, "plot_yield_forecast.csv"))

print("\nplot-level forecast (kg/ha) by crop:")
print(res.groupby("crop_type").yield_forecast_kg_ha
      .describe(percentiles=[.1, .5, .9]).round(1).to_string())

# --------------------------------------------------------- village roll-up
rows = []
for c in CROP_NAMES:
    m = (res.crop_type == c).values
    if m.sum() == 0:
        continue
    a = res.area_ha.values[m]
    A = a.sum()
    # area-weighted village mean yield in each Monte-Carlo draw
    vy = (sims[:, m] * a[None, :]).sum(axis=1) / A
    prod = (sims[:, m] * a[None, :]).sum(axis=1) / 1000.0
    rows.append({
        "village_id": 22, "village_name": "Sokhda", "crop_type": c,
        "n_plots": int(m.sum()), "area_ha": round(A, 2),
        "area_share_pct": round(100 * A / res.area_ha.sum(), 1),
        "yield_forecast_kg_ha": round(float((res.yield_forecast_kg_ha.values[m] * a).sum() / A), 1),
        "yield_p10_kg_ha": round(float(np.percentile(vy, 10)), 1),
        "yield_p50_kg_ha": round(float(np.percentile(vy, 50)), 1),
        "yield_p90_kg_ha": round(float(np.percentile(vy, 90)), 1),
        "production_t": round(float((res.yield_forecast_kg_ha.values[m] * a).sum() / 1000), 2),
        "production_p10_t": round(float(np.percentile(prod, 10)), 2),
        "production_p90_t": round(float(np.percentile(prod, 90)), 2),
        "district_ref_kg_ha": CROPS[c]["yield_ref"],
        "season_factor_2025": round(season_factor(c), 3),
        "season_observed_frac": SEASON_OBS[c],
        "product": CROPS[c]["product"],
    })
vil = pd.DataFrame(rows)
tot_a = res.area_ha.sum()
# cotton statistics are reported as lint; farmers and markets quote seed cotton
# (kapas), of which lint is about 35%
vil["yield_seed_cotton_kg_ha"] = np.where(vil.crop_type == "Cotton",
                                          (vil.yield_forecast_kg_ha / 0.35).round(0), np.nan)
vil.to_csv(os.path.join(OUT, "village_yield_forecast.csv"), index=False)

# ---------------------------------------------- label-uncertainty sensitivity
# Here the crop label itself is resampled from the blended posterior, so both
# the AREA under each crop and its production move. This is the honest place for
# the 48% Round-2 / Round-3 label disagreement to show up.
cum = P.cumsum(axis=1)
lab_area = {c: [] for c in CROP_NAMES}
lab_prod = {c: [] for c in CROP_NAMES}
tot_prod = []
NL = 1500
for s in range(NL):
    u = RNG.random(n)[:, None]
    j = (u > cum).sum(axis=1).clip(0, len(CROP_NAMES) - 1)
    y = np.array([anchor_scale.get(CROP_NAMES[jj], 1.0) for jj in j]) * \
        np.exp(Scv[j] * RHO * np.where(observed.values, Zmat[np.arange(n), j], 0.0)
               - 0.5 * (Scv[j] * RHO) ** 2)
    # re-anchor each simulated crop group to its own district reference
    for jj, c in enumerate(CROP_NAMES):
        m = j == jj
        if m.sum() == 0:
            lab_area[c].append(0.0); lab_prod[c].append(0.0); continue
        wm = (y[m] * areav[m]).sum() / areav[m].sum()
        yy = y[m] * (Yref[jj] * Sfac[jj]) / wm
        lab_area[c].append(float(areav[m].sum()))
        lab_prod[c].append(float((yy * areav[m]).sum() / 1000))
    tot_prod.append(sum(lab_prod[c][-1] for c in CROP_NAMES))

sens = pd.DataFrame([{
    "crop_type": c,
    "area_ha_primary": float(res.area_ha[res.crop_type == c].sum()),
    "area_ha_p10": round(float(np.percentile(lab_area[c], 10)), 1),
    "area_ha_p90": round(float(np.percentile(lab_area[c], 90)), 1),
    "production_t_p10": round(float(np.percentile(lab_prod[c], 10)), 1),
    "production_t_p90": round(float(np.percentile(lab_prod[c], 90)), 1),
} for c in CROP_NAMES])
sens.to_csv(os.path.join(OUT, "label_sensitivity.csv"), index=False)
print("\n" + "=" * 90)
print("LABEL-UNCERTAINTY SENSITIVITY (crop label resampled from the 6-pass posterior)")
print("=" * 90)
print(sens.to_string(index=False))
print(f"\nvillage TOTAL production under label uncertainty: "
      f"P10 {np.percentile(tot_prod,10):.0f} t / P50 {np.percentile(tot_prod,50):.0f} t "
      f"/ P90 {np.percentile(tot_prod,90):.0f} t")

print("\n" + "=" * 100)
print("VILLAGE-LEVEL FORECAST -- SOKHDA (village_id 22)")
print("=" * 100)
print(vil[["crop_type", "n_plots", "area_ha", "area_share_pct", "yield_forecast_kg_ha",
           "yield_p10_kg_ha", "yield_p90_kg_ha", "production_t", "district_ref_kg_ha",
           "season_observed_frac", "product"]].to_string(index=False))
print(f"\ntotal mapped area {tot_a:.1f} ha over {len(res)} plots; "
      f"total production {vil.production_t.sum():.1f} t")

json.dump({"nsim": NSIM, "rho": RHO, "rho_range": RHO_RANGE, "yield_cv": YIELD_CV,
           "season_observed": SEASON_OBS, "weights": WEIGHTS,
           "label_weight_carryforward": LBL_W,
           "cotton_f_set": F_SET_COTTON, "cotton_kappa_ret": KAPPA_RET,
           "season_factor": {c: season_factor(c) for c in CROP_NAMES}},
          open(os.path.join(OUT, "yield_meta.json"), "w"), indent=1)
print("\nwrote plot_yield_forecast.csv, village_yield_forecast.csv, yield_meta.json")
