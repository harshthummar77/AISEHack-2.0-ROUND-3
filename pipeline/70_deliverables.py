"""Assemble the Round-3 deliverable files and a machine-readable validation report."""
import json, os, sys
import numpy as np, pandas as pd
from scipy.stats import spearmanr, pearsonr, kruskal

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "pipeline", "out")
DEL = os.path.join(BASE, "SUBMISSION")
os.makedirs(DEL, exist_ok=True)
sys.path.insert(0, os.path.join(BASE, "pipeline"))
from cropmodel import ACQ_DATES, CROP_NAMES, CROPS, season_factor

res = pd.read_csv(os.path.join(OUT, "plot_yield_forecast.csv"))
vil = pd.read_csv(os.path.join(OUT, "village_yield_forecast.csv"))
sens = pd.read_csv(os.path.join(OUT, "label_sensitivity.csv"))
nd = pd.read_csv(os.path.join(OUT, "plot_ndvi.csv")).set_index("plot_id")
crop3 = pd.read_csv(os.path.join(OUT, "plot_crop.csv")).set_index("plot_id")
coreg = json.load(open(os.path.join(OUT, "coreg.json")))
long = pd.read_csv(os.path.join(OUT, "plot_stats_long.csv"))

# ------------------------------------------------------- 1. plot-level file
sub = res[["village_id", "village_name", "farm_id", "crop_type", "area_ha",
           "yield_forecast_kg_ha", "yield_p10_kg_ha", "yield_p90_kg_ha",
           "production_t", "sar_yield_index_z", "z_est", "z_oct", "z_ret", "z_uni",
           "season_observed_frac", "n_sar_dates", "observed", "crop_confidence_r3"] +
          [c for c in res.columns if c.startswith("gamma0_dB_")]].copy()
sub["quality_flag"] = np.where(~res.observed, "not_observed_swath_edge",
                        np.where(res.n_sar_dates < 6, "partial_coverage", "ok"))
sub = sub.rename(columns={"yield_forecast_kg_ha": "final_yield_forecast_kg_ha"})
sub.to_csv(os.path.join(DEL, "plot_level_yield_forecast.csv"), index=False)

# ------------------------------------------------------- 2. village-level file
vil.to_csv(os.path.join(DEL, "village_level_yield_forecast.csv"), index=False)

# ------------------------------------------------------- 3. Excel workbook
try:
    with pd.ExcelWriter(os.path.join(DEL, "Team8bit_Round3_results.xlsx")) as xl:
        sub.to_excel(xl, sheet_name="plot_forecast", index=False)
        vil.to_excel(xl, sheet_name="village_forecast", index=False)
        sens.to_excel(xl, sheet_name="label_sensitivity", index=False)
    print("wrote Excel workbook")
except Exception as e:
    print("Excel skipped:", e)

# ------------------------------------------------------- 4. validation report
g = long.pivot(index="plot_id", columns="date", values="g0_db")[ACQ_DATES]
lab = res.set_index("farm_id").crop_type
rep = {"site": {"village": "Sokhda", "village_id": 22, "district": "Vadodara",
                "state": "Gujarat", "agroclimatic_zone": "Middle Gujarat (GJ-3)",
                "n_plots": int(len(res)), "mapped_area_ha": float(res.area_ha.sum())},
       "sar": {"sensor": "Capella X-band (9.65 GHz) HH stripmap SLC",
               "n_passes": 6, "dates": ACQ_DATES,
               "incidence_deg_range": [28.69, 35.24],
               "look_directions": {"left": 5, "right": 1},
               "product_radiometry": "beta_nought, calibration=full",
               "geocoding": ("own RPC00B model, RMS 0.0000 px vs 225 product GCPs; "
                             "terrain-referenced using Copernicus GLO-30"),
               "terrain": {
                   "dem": "Copernicus GLO-30 (EGM2008 orthometric), tile N22E073",
                   "geoid_offset_m": -62.023,
                   "geoid_offset_scene_sd_m": 0.124,
                   "relief_over_farm_block_m": 26.6,
                   "rpc_roundtrip_rmse_px_dem": [4.10, 4.70],
                   "rpc_roundtrip_rmse_px_constant_height": [15.13, 16.61],
                   "corr_vs_capella_geocoding_constant_height": 0.769,
                   "corr_vs_capella_geocoding_terrain": 0.840,
                   "note": ("an earlier version used a single constant height of -20 m "
                            "ellipsoidal; its residual global shift was <=2.8 m because a "
                            "global shift metric recovers the mean alignment and leaves the "
                            "spatially varying terrain component untouched. The tell was the "
                            "single right-looking pass, whose co-registration residual fell "
                            "from 2.54 m to 0.12 m once terrain was carried."),
               },
               "coregistration_residual_m": {s["date"]: round(abs(s["d_east_m"]) +
                                             abs(s["d_north_m"]), 2)
                                             for s in coreg["shifts"]}}}

# same-day SAR vs NDVI
sd = {}
for sar_d, s2 in [("2025-10-13", "ndvi_2025-10-13"), ("2025-11-12", "ndvi_2025-11-12")]:
    m = g[sar_d].notna() & nd[s2].notna()
    r, p = pearsonr(g[sar_d][m], nd[s2][m]); rs, _ = spearmanr(g[sar_d][m], nd[s2][m])
    sd[sar_d] = {"pearson_r": round(float(r), 4), "spearman_rho": round(float(rs), 4),
                 "p_value": float(p), "n": int(m.sum()), "same_day": True}
rep["validation_same_day_optical"] = sd

# yield index vs NDVI, within crop
wc = {}
for c in CROP_NAMES:
    idx = lab[lab == c].index
    z = res.set_index("farm_id").sar_yield_index_z.reindex(idx)
    v = nd["ndvi_2025-10-13"].reindex(idx)
    m = z.notna() & v.notna()
    if m.sum() > 20:
        rs, p = spearmanr(z[m], v[m])
        wc[c] = {"spearman_rho": round(float(rs), 4), "p_value": float(p), "n": int(m.sum())}
rep["validation_yield_index_vs_ndvi_within_crop"] = wc

# crop label separation of independent optical
obs = crop3[crop3.observed].index
for name, series in [("round3_6pass", crop3.crop_type.reindex(obs)),
                     ("round2_carryforward", lab.reindex(obs))]:
    d = pd.DataFrame({"c": series, "n": nd["ndvi_2025-11-12"].reindex(obs)}).dropna()
    grps = [x["n"].values for _, x in d.groupby("c") if len(x) > 3]
    H, p = kruskal(*grps)
    rep.setdefault("crop_label_separation_nov_ndvi", {})[name] = {
        "kruskal_H": round(float(H), 2), "p_value": float(p),
        "eta_squared": round(float((H - len(grps) + 1) / (len(d) - len(grps))), 4)}
rep["crop_label_agreement_round2_vs_round3"] = float(
    (crop3.crop_type.reindex(obs) == lab.reindex(obs)).mean())

rep["optical_availability"] = {
    "sentinel2_overpasses_jun_nov": 46, "usable_below_20pct_cloud": 10,
    "overpasses_19jun_to_08oct": 29, "best_cloud_pct_in_that_window": 23.3,
    "blackout_days": 111,
    "note": "no usable optical scene between 19 June and 8 October 2025; "
            "all six SAR passes were unaffected"}

rep["village_forecast"] = vil.to_dict(orient="records")
rep["assumptions"] = {
    "absolute_level": "area-weighted village mean yield per crop is set to the "
                      "Vadodara district yield (Directorate of Agriculture, Gujarat, "
                      "2022-23) times a 2025 season factor; SAR determines only the "
                      "distribution about that mean",
    "season_factor": {c: round(season_factor(c), 3) for c in CROP_NAMES},
    "district_reference_kg_ha": {c: CROPS[c]["yield_ref"] for c in CROP_NAMES},
    "rho_sar_explains_yield_spread": 0.55,
    "crop_labels": "Round-1/2 carry-forward, area-constrained; an independent "
                   "6-pass re-derivation agrees on 46% of the SAR-observed plots "
                   "and that disagreement is propagated as label uncertainty",
    "cotton_reported_as": "lint (seed cotton = lint / 0.35)",
}
rep["limitations"] = [
    "No ground-truth yield exists for any plot, so absolute accuracy cannot be "
    "verified; only internal consistency and independent optical agreement are testable.",
    "A 60-day gap between 14 Aug and 13 Oct brackets the entire maturity and harvest "
    "of maize, bajra and groundnut, so their yield-forming period is sampled once.",
    "The AOI is wider than one Capella stripmap swath; 43 plots fall outside all six "
    "footprints and receive the crop mean with inflated uncertainty.",
    "Vadodara also grows castor and pigeon pea at areas comparable to maize, but the "
    "task permits only five classes, so some plots are certainly another crop.",
    "X-band HH saturates early and is weakly related to biomass at high LAI; the method "
    "therefore uses phenological timing and canopy retention, not biomass inversion.",
]
json.dump(rep, open(os.path.join(DEL, "validation_report.json"), "w"), indent=1)

print("\n=== DELIVERABLES ===")
for f in sorted(os.listdir(DEL)):
    p = os.path.join(DEL, f)
    if os.path.isfile(p):
        print(f"  {f:45s} {os.path.getsize(p)/1024:8.1f} KB")
print("\nsame-day SAR vs NDVI:", json.dumps(sd, indent=1))
print("\nwithin-crop yield index vs NDVI:", json.dumps(wc, indent=1))
print("\nplot file rows:", len(sub), " village rows:", len(vil))
print(sub.quality_flag.value_counts().to_string())
