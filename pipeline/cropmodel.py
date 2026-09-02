"""
cropmodel.py -- agronomic knowledge base and canopy/backscatter forward model
for kharif 2025, Sokhda village, Vadodara district, Gujarat (Middle Gujarat
agro-climatic zone GJ-3).

Everything that is *not* derived from the SAR data itself is declared here, in
one place, with its source, so that every assumption in the forecast is
auditable.

SOURCES
-------
[S1] ICAR-CRIDA / AAU-Anand, "Agriculture Contingency Plan for District:
     Vadodara", Govt. of India.  Normal SW-monsoon rainfall 1004 mm in 35 rainy
     days; normal onset 3rd week of June, cessation 3rd week of September;
     district altitude 37.5 m; soils dominated by medium black (290.2 k ha) and
     heavy black (61.8 k ha) vertisols plus loamy sand (122.5 k ha); net sown
     510.7 k ha of which 208.2 k ha irrigated (41%).  Normal sowing windows:
     cotton rainfed 3rd wk Jun - 2nd wk Jul (irrigated 1st wk May - 2nd wk Jul),
     paddy rainfed 3rd wk Jun - 2nd wk Jul (irrigated 1st - 4th wk Jul), maize
     3rd wk Jun - 2nd wk Jul.
[S2] Parmar & Bhatt (2025), Int. J. Agric. Food Sci. 7(5):55-61, Table 1 and
     Table 3 -- crop-wise area and yield for Vadodara-Chhotaudepur district,
     sourced from Directorate of Agriculture, Gujarat (2024).
[S3] IMD / Gujarat SEOC via DeshGujarat (Oct 2025): Gujarat monsoon 2025 closed
     at 1034.26 mm = 117.28% of the 30-year average; East-Central Gujarat (the
     region containing Vadodara) 934.1 mm = 116.06%.  Onset was early, with
     ~30% of seasonal rain already banked by mid-June.
[S4] Standard agronomic literature for harvest index and radiation-use
     efficiency; values used are mid-range and are varied in the Monte-Carlo.
"""

from __future__ import annotations
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Acquisition calendar
# ---------------------------------------------------------------------------
ACQ_DATES = ["2025-06-06", "2025-06-19", "2025-08-14",
             "2025-10-13", "2025-10-29", "2025-11-12"]
ACQ_DOY = np.array([pd.Timestamp(d).dayofyear for d in ACQ_DATES], dtype=float)

# 2025 monsoon onset over Middle Gujarat.  Normal onset is the 3rd week of June
# [S1]; 2025 was an early-onset, above-normal year [S3], so the effective
# sowing anchor is pulled ~7-10 days earlier than climatology.
ONSET_DOY_2025 = 162.0          # ~11 June 2025
SEASON_RAIN_FRAC = 1.1606       # East-Central Gujarat 2025 / normal  [S3]

# ---------------------------------------------------------------------------
# 2. Crop knowledge base
# ---------------------------------------------------------------------------
# sow_doy      : central sowing/transplanting day-of-year for kharif 2025,
#                anchored to the 2025 onset and the [S1] sowing windows
# sow_sd       : spread of sowing dates across farmers (days)
# dur          : sowing -> physiological maturity (days)
# harvest_lag  : maturity -> field cleared (days)
# yield_ref    : district yield 2022-23, kg/ha  [S2]
# area_share   : district area share among these five crops, 2022-23  [S2]
# hi, rue      : harvest index and radiation-use efficiency (g DM / MJ APAR) [S4]
# peak_dgamma  : expected peak rise of gamma0 above the plot's own bare-soil
#                baseline, dB -- set by canopy structure at X band
# flooded      : crop is grown on ponded/puddled soil early in the cycle
# standing_at_end : canopy still present at the last acquisition (12 Nov)
CROPS = {
    "Rice": dict(
        sow_doy=ONSET_DOY_2025 + 26, sow_sd=10, dur=120, harvest_lag=7,
        yield_ref=1690.0, area_share=0.1753, hi=0.45, rue=2.2,
        peak_dgamma=6.0, flooded=True, standing_at_end=False,
        product="paddy grain", duration_covered=1.00,
    ),
    "Cotton": dict(
        sow_doy=ONSET_DOY_2025 - 4, sow_sd=12, dur=200, harvest_lag=30,
        yield_ref=776.0, area_share=0.6528, hi=0.32, rue=1.7,
        peak_dgamma=7.5, flooded=False, standing_at_end=True,
        product="lint", duration_covered=0.78,
    ),
    "Maize": dict(
        sow_doy=ONSET_DOY_2025 + 8, sow_sd=10, dur=95, harvest_lag=7,
        yield_ref=2312.0, area_share=0.1436, hi=0.45, rue=3.3,
        peak_dgamma=8.0, flooded=False, standing_at_end=False,
        product="grain", duration_covered=1.00,
    ),
    "Bajra": dict(
        sow_doy=ONSET_DOY_2025 + 6, sow_sd=10, dur=82, harvest_lag=7,
        yield_ref=2714.0, area_share=0.0247, hi=0.30, rue=2.9,
        peak_dgamma=5.0, flooded=False, standing_at_end=False,
        product="grain", duration_covered=1.00,
    ),
    "Groundnut": dict(
        sow_doy=ONSET_DOY_2025 + 6, sow_sd=10, dur=110, harvest_lag=7,
        yield_ref=2514.0, area_share=0.0035, hi=0.38, rue=1.9,
        peak_dgamma=4.0, flooded=False, standing_at_end=False,
        product="pod", duration_covered=1.00,
    ),
}
CROP_NAMES = list(CROPS.keys())

# 2022-23 district areas ('00 ha) from [S2] Table 1, used only as a weak prior
DISTRICT_AREA_00HA = {"Rice": 498.18, "Maize": 407.94, "Cotton": 1854.79,
                      "Bajra": 70.22, "Groundnut": 10.04}


# ---------------------------------------------------------------------------
# 3. Canopy development curve
# ---------------------------------------------------------------------------
def canopy_cover(doy, sow_doy, dur, harvest_lag=7, k_rise=0.10, sen_frac=0.72):
    """Fractional green canopy cover C(t) in [0, 1].

    A double-logistic: a rising limb from emergence to canopy closure and a
    falling limb through senescence, truncated hard at harvest.  `sen_frac` is
    the fraction of the cycle at which senescence begins (later for
    indeterminate crops such as cotton).
    """
    doy = np.asarray(doy, dtype=float)
    t = (doy - sow_doy) / float(dur)                    # 0 = sowing, 1 = maturity
    rise = 1.0 / (1.0 + np.exp(-(t - 0.28) / 0.085))
    fall = 1.0 / (1.0 + np.exp((t - sen_frac) / 0.115))
    c = rise * fall
    c = np.where(t < 0.0, 0.0, c)
    c = np.where(t > 1.0 + harvest_lag / float(dur), 0.0, c)
    return np.clip(c, 0.0, 1.0)


def canopy_integral(sow_doy, dur, harvest_lag=7, **kw):
    """Integral of C(t) over the cycle, in canopy-days -- the SAR analogue of
    an integrated vegetation index, and the light-interception term of a
    Monteith yield model."""
    g = np.arange(sow_doy - 10, sow_doy + dur + harvest_lag + 20, 1.0)
    return float(np.trapezoid(canopy_cover(g, sow_doy, dur, harvest_lag, **kw), g))


# ---------------------------------------------------------------------------
# 4. Forward model: canopy cover -> X-band HH gamma0
# ---------------------------------------------------------------------------
# Two-layer water-cloud form written directly in the observable we use, the
# rise of gamma0 above each plot's OWN pre-season bare-soil baseline:
#
#   gamma0(t) = C(t)^p * Gveg + (1 - C(t))^2 * Gsoil(t)
#
# Working in "delta above own baseline" removes the plot-constant soil
# roughness / permittivity term, which is exactly what X-band cannot separate
# from biomass.  Gsoil(t) carries the seasonal soil-moisture excursion, common
# to all plots, estimated from the antecedent precipitation index.
CANOPY_EXP = 0.9

# Seasonal soil-moisture term, dB relative to the 6 June pre-monsoon baseline.
# 6 Jun is pre-onset and dry; 19 Jun is 8 days after the 2025 onset with soils
# wetting and many fields puddled/tilled; Aug is peak monsoon; by mid-Oct the
# monsoon has withdrawn and soils are drying; 12 Nov is dry post-harvest.
SOIL_DGAMMA_DB = np.array([0.0, +1.6, +1.2, +0.3, -0.1, -0.6])


def forward_dgamma_db(crop, sow_shift=0.0, vigour=1.0, doy=None):
    """Predicted gamma0 rise above the plot's own bare-soil baseline, in dB,
    at the six acquisition times."""
    p = CROPS[crop]
    if doy is None:
        doy = ACQ_DOY
    c = canopy_cover(doy, p["sow_doy"] + sow_shift, p["dur"], p["harvest_lag"],
                     sen_frac=0.80 if crop == "Cotton" else 0.72)
    veg = (vigour * c) ** CANOPY_EXP * p["peak_dgamma"]
    soil = SOIL_DGAMMA_DB.copy() if len(doy) == len(SOIL_DGAMMA_DB) else np.zeros_like(doy)
    # transplanted rice is ponded through establishment: specular loss at X band
    if p["flooded"]:
        pond = np.exp(-0.5 * ((doy - (p["sow_doy"] + sow_shift - 6.0)) / 12.0) ** 2)
        veg = veg - 5.5 * pond * (1.0 - c)
    # attenuation of the soil term by the canopy
    return veg + soil * (1.0 - c) ** 2


def signature_matrix(sow_shifts=(-12, -6, 0, 6, 12), vigours=(0.7, 0.85, 1.0, 1.15)):
    """Bank of simulated 6-date signatures spanning plausible sowing dates and
    vigour levels, for model-driven (label-free) crop assignment."""
    recs = []
    for c in CROP_NAMES:
        for s in sow_shifts:
            for v in vigours:
                recs.append({"crop": c, "sow_shift": s, "vigour": v,
                             "sig": forward_dgamma_db(c, s, v)})
    return recs


# ---------------------------------------------------------------------------
# 5. Season adjustment
# ---------------------------------------------------------------------------
def season_factor(crop):
    """Multiplier on the district reference yield for the 2025 kharif season.

    2025 delivered 116% of normal rainfall over East-Central Gujarat with an
    early, well-distributed onset [S3].  Response is capped and crop-specific:
    rainfed coarse cereals and cotton gain most from a surplus year; irrigated
    rice gains little because it is not water-limited; excess rain carries a
    small waterlogging penalty on vertisols for groundnut.
    """
    excess = SEASON_RAIN_FRAC - 1.0             # +0.1606
    sens = {"Rice": 0.10, "Cotton": 0.35, "Maize": 0.45,
            "Bajra": 0.50, "Groundnut": -0.15}[crop]
    return float(np.clip(1.0 + sens * excess, 0.85, 1.20))
