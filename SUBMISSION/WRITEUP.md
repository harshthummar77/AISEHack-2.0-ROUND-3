# Six Looks, One Harvest

### A final yield forecast for 966 plots in Sokhda, Vadodara — anchored to what X-band can measure, explicit about what it cannot

**Team 8bit** · Harsh Thummar, Viraj Suhagiya
Sokhda village (ID 22), Vadodara district, Gujarat · 966 plots · 447.5 ha
Capella X-band HH stripmap SLC: 6 Jun / 19 Jun / 14 Aug / 13 Oct / 29 Oct / 12 Nov 2025

---

## 1. What Round 3 actually changes

Round 2 asked how the crop was doing on 13 October. Round 3 asks what comes off the field. Those are different problems, and the six-pass series answers them unevenly. The honest starting point is a table of how much of each crop's yield-forming cycle these six looks actually cover:

| Crop | Cycle covered | What the forecast is |
|---|---|---|
| Rice | 100% | reconstruction of a completed season |
| Cotton | 78% | genuine extrapolation past 12 Nov |
| Groundnut | 60% | one in-season look |
| Maize | 55% | one in-season look |
| Bajra | 50% | one in-season look |

The 60-day gap between 14 August and 13 October brackets the entire maturity and harvest of maize, bajra and groundnut — their yield-determining period is sampled **once**. Cotton is the opposite: still standing on 12 November with picking running to January, so its forecast is real extrapolation. This asymmetry drives the uncertainty structure, and is why bajra carries the widest interval and rice the narrowest.

## 2. From raw SLC to calibrated γ⁰

Everything between the complex SLC and the output CSV is built from the Capella metadata and the RPC model — calibration, geocoding, co-registration, zonal statistics. No SNAP, no ISCE, no `gdalwarp`.

Capella ships SLC as `beta_nought` with `calibration: full`, so β⁰ = (|DN|·scale_factor)² and γ⁰ = β⁰·tan θ, with θ computed per range sample from the product state vectors. γ⁰ is the right choice because the passes span **28.69°–35.24°** incidence.

Geocoding uses our own RPC00B implementation, validated against the 225 GCPs in each product: **RMS 0.0000 px in line and sample**.

**Geocoding is terrain-referenced, and the datum solved rather than assumed.** Capella's RPCs expect *ellipsoidal* heights; the Copernicus GLO-30 DEM stores *orthometric* ones. The GCPs carry ellipsoidal z, so **N = h_ellipsoidal − H_orthometric** is solved directly: **N = −62.02 m, sd 0.12 m**.

That the DEM is necessary is not an assumption either. The block carries **26.6 m of relief**, which a flat-earth height turns into up to **46 m of ground-range displacement** at 30° incidence — about one field width. On the GCP round trip:

| Height model | RPC round-trip RMSE |
|---|---|
| Best single constant height (−20 m) | 15.1–16.6 px |
| Copernicus GLO-30 + solved datum | **4.1–4.7 px** |

Against Capella's own DEM-geocoded previews, mean correlation rises **0.769 → 0.840**, improving on all six passes. The sharpest confirmation is geometric: the right-looking 29 October pass needed a 2.54 m co-registration shift under a constant height and **0.12 m** once terrain is carried — as expected, since a height error displaces opposite look directions in opposite senses. Residual co-registration is now **≤0.12 m on all six passes**. Plots are eroded 4 m inward to reject bunds; the plot-mean γ⁰ is precise to ~0.13 dB.

The downstream yield metrics barely moved (same-day ρ 0.564 against 0.584). We report it anyway: correct geometry is the defensible geometry, and the science holding steady under a real change in the measurement is itself evidence the result is not a processing artefact.

## 3. The constraint that shaped the model

Backscatter depends on incidence and look direction, differently for soil than canopy, so no single normalisation removes geometry from a mixed scene. Two things follow.

First, **every feature is a village anomaly** — a plot minus the village median for that same acquisition. In one step this cancels calibration, gain, incidence response, look direction, and the soil-moisture excursion common to all fields. What survives is plot-to-plot difference, which is what a yield map needs.

Second, differences are only taken between geometry-safe pairs:

- **19 Jun → 14 Aug**, Δθ = 0.08°, same look — canopy establishment
- **13 Oct → 12 Nov**, Δθ = 1.78°, same look — late retention versus harvest

The second pair is new in Round 3 and is what separates a crop still standing from one already cut.

## 4. What X-band HH can and cannot do

Measured on this village: the median Δγ⁰ at peak season is **−0.58 dB relative to pre-monsoon bare soil**. Peak-season fields are *darker* than bare ground. That is not an error — at HH a developed canopy attenuates a rough, freshly-tilled soil surface more than its own volume return replaces. Combined with the well-documented early saturation of X-band against LAI, it means **inverting X-band HH for absolute biomass here would be indefensible**.

So the model does not do that. It uses what X-band at metre scale genuinely measures: the *timing* of canopy development, the *retention* of canopy late in the season, and within-field evenness. Phenology, not biomass.

## 5. Six SLCs — so why only the amplitude?

Because we checked rather than assumed. Of the fifteen pass pairs, **five are opposite-look and nine exceed the critical baseline**, some by a factor of a hundred. Exactly one is geometrically viable — 19 Jun / 14 Aug, B⊥ 844 m against B⊥crit 3975 m — and it is **56 days apart**, far beyond X-band coherence over a growing canopy. Repeat-pass InSAR is structurally unavailable here.

So we used the phase another way. **Sub-aperture decomposition** splits one acquisition's Doppler spectrum in two — single-pass, so temporal decorrelation cannot touch it. The estimator is sound: point scatterers reach γ = 0.98 against 0.25 for distributed clutter. But at plot level it carries nothing — repeatability r = 0.02, crop separation η² = 0.02, NDVI ρ ≤ 0.11. Field-averaged X-band sub-look coherence is dominated by speckle statistics. **A null result, reported as a null**, and kept out of the model.

## 6. The forecast model

With no ground truth, SAR can set the ranking and spread between plots but not the absolute level. We therefore separate the two explicitly:

**Y_p = Y_ref(c) · S(c) · exp( σ_c·ρ·z_p − (σ_c·ρ)²/2 )**

- **Y_ref(c)** — Vadodara district yield (Directorate of Agriculture, Gujarat, 2022-23): rice 1690, cotton 776 (lint), maize 2312, bajra 2714, groundnut 2514 kg/ha.
- **S(c)** — 2025 season factor. East-Central Gujarat closed the monsoon at **934.1 mm, 116% of normal**, with an early onset. Response is crop-specific: rainfed coarse cereals gain most (bajra 1.080), irrigated rice barely (1.016), groundnut takes a small waterlogging penalty on vertisols (0.976).
- **z_p** — stage-weighted SAR index, standardised within crop, built from establishment, standing canopy on 13 Oct, late retention, and speckle-corrected uniformity. Weights differ by crop: cotton leans on late retention (boll load), the short-duration crops on establishment, because that is all that was observed.
- **σ_c** — farm-to-farm yield CV within a village (0.28–0.35); **ρ = 0.55** — the fraction of that spread a six-pass X-band series plausibly explains, varied 0.40–0.70.

The lognormal form makes the area-weighted village mean reproduce Y_ref·S **by construction**, so the anchor is an explicit assumption rather than a hidden result, and every plot-to-plot difference beneath it is SAR-driven.

Uncertainty is Monte-Carlo (4,000 draws) with the error budget split into terms that are **systematic across a crop** (district reference ±12%, season factor ±6%, most forecast-horizon risk — the weather over the remaining cotton picking is common to every cotton plot) and terms **independent between plots**. Only the second kind averages away on aggregation; conflating them is the usual reason village intervals come out implausibly tight.

## 7. Crop labels — an honest negative result

We re-derived the crop map independently from all six passes using phenological templates and an area-constrained transportation LP. It agrees with the Round-2 carry-forward on only **46%** of plots.

We then tested both label sets against data neither had seen — Sentinel-2 NDVI. The Round-2 labels separate November greenness **better** (η² 0.138 vs 0.085; 13 Oct: 0.280 vs 0.217). Our new classifier is not an improvement, so we did not adopt it.

The Round-1/2 carry-forward is therefore primary — it is the official continuity *and* it wins on independent optical. The 46% agreement is not discarded; the disagreement becomes a **measurement of label uncertainty**, propagated into the results.

## 8. Validation

Two Sentinel-2 scenes are *same-day* coincident with Capella passes, so no temporal interpolation is needed. NDVI is used only for validation and never enters the model.

| Test | Result |
|---|---|
| γ⁰ vs same-day NDVI, 13 Oct | ρ = **+0.56**, n = 923 |
| γ⁰ vs same-day NDVI, 12 Nov | ρ = **+0.48**, n = 937 |

The sharper result is within-crop. The SAR yield index correlates with NDVI for **rice (ρ +0.36, p = 2×10⁻⁸)** and **cotton (ρ +0.36, p = 1×10⁻¹²)** — the two crops still standing on 13 October — and is **null for maize (+0.02), bajra (−0.07) and groundnut (+0.11)**, the three already cut, where both sensors see bare soil. An artefact would correlate everywhere or nowhere; this validates precisely where a crop remains in the field.

**Why this has to be SAR, measured.** Across 46 Sentinel-2 overpasses of this AOI from June to November, only 10 were usable. Between 19 June and 8 October there were **29 overpasses and not one below 23.3% cloud** — a 111-day blackout spanning sowing, establishment and peak vegetative growth. All six SAR passes were unaffected.

## 9. Results

**Village-level forecast — Sokhda (ID 22), 447.5 ha**

| Crop | Plots | Area (ha) | Forecast (kg/ha) | P10–P90 | Production (t) | Product |
|---|---|---|---|---|---|---|
| Rice | 226 | 60.4 | **1,717** | 1,401–2,021 | 103.7 | paddy grain |
| Cotton | 364 | 192.7 | **820** | 674–971 | 158.0 | lint (≈2,342 kg/ha kapas) |
| Maize | 74 | 34.3 | **2,479** | 2,009–2,968 | 85.0 | grain |
| Bajra | 54 | 34.6 | **2,932** | 2,378–3,576 | 101.4 | grain |
| Groundnut | 248 | 125.6 | **2,453** | 2,005–2,922 | 308.1 | pod |
| **Total** | **966** | **447.5** | — | — | **756.1** | |

Plot-level forecasts, P10/P90 intervals, the four SAR index components, all six γ⁰ values and a quality flag ship for all 966 plots. Coverage: 832 plots on all six dates, 91 partial, 43 outside every swath (the AOI is wider than one Capella stripmap) — those 43 receive the crop mean with inflated uncertainty and are flagged, not hidden.

**The one number that would move the answer is not the radar.** The carry-forward puts groundnut at **28% of Sokhda**; the Directorate of Agriculture puts it at **0.35% of the district**. Both cannot be close to right, and groundnut carries a high per-hectare reference. Running the assignment under both area constraints:

| Crop | A · Round-1 carry-forward | B · District statistics |
|---|---|---|
| Rice | 61 ha → 106 t | 79 ha → 135 t |
| Cotton | 188 ha → 154 t | 292 ha → 239 t |
| Maize | 35 ha → 88 t | 64 ha → 159 t |
| Bajra | 35 ha → 103 t | 11 ha → 32 t |
| Groundnut | **127 ha → 313 t** | **1.7 ha → 4 t** |
| **Village total** | **763 t** | **570 t** |

A **25% swing**, essentially all of it groundnut. We publish both rather than choose silently. Scenario A also reproduces the primary result to within 0.9% despite reaching it by a different labelling route.

## 10. Where this is weakest

- **No ground truth exists**, so absolute accuracy is untestable. Only internal consistency and independent optical agreement can be checked; both are reported above.
- **Maize, bajra and groundnut rest on one in-season observation.** Their intervals are wide by construction.
- **Crop labels are the dominant uncertainty**, not the radar — a 25% swing between two defensible mixes.
- **Vadodara also grows castor and pigeon pea** at areas comparable to maize; only five classes are permitted, so some plots are certainly another crop.
- **Cotton's last 22% is extrapolated.** A poor post-monsoon spell would move it more than anything the radar has seen.

This is the best available reading of six radar looks — not a measurement of the harvest, and it does not pretend to be one.

---

*Data: Capella X-band SLC (competition) · Copernicus GLO-30 DEM · Sentinel-2 L2A, validation only · Directorate of Agriculture, Gujarat · ICAR-CRIDA Vadodara Contingency Plan · IMD/Gujarat SEOC 2025 monsoon.*
