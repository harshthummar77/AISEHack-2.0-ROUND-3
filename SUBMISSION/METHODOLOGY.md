# Written Documentation — Methodology

**ANRF AISEHack 2.0 · Round 3 · Remote Sensing: Yield Estimation**
**Team 8bit** — Harsh Thummar, Viraj Suhagiya

Site: Sokhda village (ID 22), Vadodara district, Gujarat — Middle Gujarat agro-climatic zone (GJ-3)
Scope: 966 farm plots, 447.5 ha mapped
Data: Capella Space X-band (9.65 GHz) HH stripmap SLC, six passes, kharif 2025

---

## 1. Summary

We produce a **final (at-harvest) yield forecast** for each of 966 plots, plus village-level aggregates by crop, from a six-pass Capella X-band HH SLC time series, with no ground-truth yield anywhere in the chain.

The method has three separable parts, deliberately kept separable so each can be audited:

1. **A physically calibrated SAR measurement.** Raw complex SLC → γ⁰ on a common 2 m UTM grid, using our own RPC geocoding, a reference height solved from the imagery, and bounded inter-pass co-registration.
2. **A relative yield index.** Village-anomaly features built only from geometry-safe date pairs, weighted by which phenological stage each crop's yield actually depends on.
3. **An absolute anchor.** District yield statistics adjusted for the 2025 season set the village mean; SAR sets the distribution about it.

Point 3 is the honest response to having no labels: **SAR determines ranking and spread, official statistics determine level.** We state this as an assumption rather than presenting an absolute yield the radar cannot support.

---

## 2. Data

### 2.1 SAR (provided)

| Date (UTC) | Local (IST) | θ centre | Look | Orbit | Azimuth | NESZ peak |
|---|---|---|---|---|---|---|
| 2025-06-06 07:25 | 12:55 | 35.24° | left | asc | 134.7° | −26.13 dB |
| 2025-06-19 02:14 | 07:44 | 28.77° | left | asc | 135.1° | −27.76 dB |
| 2025-08-14 03:11 | 08:41 | 28.69° | left | asc | 135.1° | −27.97 dB |
| 2025-10-13 02:26 | 07:56 | 31.53° | left | asc | 135.0° | −27.35 dB |
| 2025-10-29 20:07 | 01:37+1 | 29.84° | **right** | asc | 318.4° | −27.74 dB |
| 2025-11-12 13:52 | 19:22 | 29.75° | left | asc | 135.2° | −27.72 dB |

Stripmap_20, 1 look, ~0.74 m azimuth × 1.07–1.29 m slant-range pixel spacing, `CInt16`, product radiometry `beta_nought`, `calibration: full`.

### 2.2 Vector (provided)
`Sokhda_Farms.shp` — 966 polygons, EPSG:4326, attributes FID / id / ID_1 / VILLAGE only (**no crop label**). Median plot 0.27 ha, mean 0.46 ha, max 3.49 ha; 9 invalid rings repaired with `buffer(0)`; 2 degenerate (zero-area) polygons. `Sokhda_Village.shp` — one polygon, 1174 ha.

### 2.3 External data used

| Source | Used for | Values |
|---|---|---|
| Directorate of Agriculture, Gujarat (2024), via Parmar & Bhatt (2025) Table 3 | Absolute yield anchor | Vadodara-Chhotaudepur 2022-23 yields: rice 1690, maize 2312, groundnut 2514, cotton 776 (lint), bajra 2714 kg/ha |
| Same, Table 1 | District area shares (sensitivity only) | 2022-23 areas ('00 ha): cotton 1854.8, rice 498.2, maize 407.9, bajra 70.2, groundnut 10.0 |
| ICAR-CRIDA / AAU-Anand, *Agriculture Contingency Plan for District: Vadodara* | Crop calendar, rainfall normals, soils, altitude | Normal SW monsoon 1004 mm / 35 rainy days; onset 3rd week June, cessation 3rd week Sept; altitude 37.5 m; medium black vertisols dominant (290.2 k ha); 41% of net sown area irrigated; sowing windows per crop |
| IMD / Gujarat SEOC, 2025 monsoon summary | Season adjustment | Gujarat 1034.26 mm = 117.28% of normal; **East-Central Gujarat 934.1 mm = 116.06%**; early onset, ~30% of seasonal rain by mid-June |
| Copernicus DEM GLO-30 (AWS Open Data), tile N22E073 | Terrain-referenced geocoding | 1 arcsec; 24.4–51.0 m orthometric over the farm block, 26.6 m relief |
| Sentinel-2 L2A (AWS Open Data, Element84 STAC) | **Validation only** | 7 dates Jun–Nov 2025; two same-day coincident with Capella |
| Round-1 village crop composition (own, carried forward) | Area constraint on labels | Cotton 136.03, Groundnut 92.38, Rice 44.59, Maize 25.80, Bajra 25.70 ha |

**Sentinel-2 never enters the model.** It is used exclusively to test the output, which is only meaningful because it is withheld from every fitting step.

---

## 3. SAR processing chain

Implemented from the Capella extended metadata and the RPC model. No SNAP, ISCE or `gdalwarp`.

### 3.1 Radiometric calibration
Capella SLC ships as `beta_nought`, `calibration: full`:

```
β⁰ = (|DN| · scale_factor)²        σ⁰ = β⁰ sin θ        γ⁰ = β⁰ tan θ
```

γ⁰ is used throughout: the passes span 28.69°–35.24°, and γ⁰ is to first order the incidence-invariant quantity for volume scatterers. The NESZ polynomial is evaluated per range sample and carried through, so every plot statistic reports the fraction of pixels below the noise floor.

### 3.2 Local incidence angle
Per range sample, from a spherical-Earth triangle closed on the satellite radius `Rs`, local Earth radius `Re` (both from the product ECEF reference positions) and slant range `r = r₀ + n·Δr`:

```
cos θ = (Rs² − Re² − r²) / (2 Re r)
```

This reproduces the metadata centre incidence to ~0.1°; the profile is then shifted so the centre sample matches the metadata exactly, so the term contributes its **across-range gradient** (~0.4° over the AOI) rather than an absolute value.

### 3.3 Geocoding
Own RPC00B rational-polynomial implementation (20-term cubic, GDAL/NITF term order). Inverse geocoding: each output cell → (lon, lat) → DEM height + datum shift → RPC → (line, sample), nearest-neighbour gathered at 4×4 sub-samples per 2 m cell and block-averaged. Every sub-sample is projected at its own terrain height (§3.4). This performs the spatial multi-look in the map domain and yields ~2.9 effective looks per 2 m cell; over a median 0.27 ha plot that is ~2,000 independent looks, giving a plot-mean precision near **0.13 dB**.

**Validation:** against the 225 GCPs shipped in each product, RMS error is **0.0000 px** in both line and sample, for all six scenes.

### 3.4 Terrain referencing and the datum solution

Capella's RPCs expect **ellipsoidal** heights; the Copernicus GLO-30 DEM stores **orthometric** (EGM2008) heights. The 225 GCPs embedded in each product carry ellipsoidal z, so the datum shift is solved rather than assumed:

```
N = mean( z_GCP_ellipsoidal  −  H_DEM_orthometric )
```

| Pass | N (m) | within-scene sd |
|---|---|---|
| 2025-06-06 | −62.075 | 3.34 m |
| 2025-06-19 | −62.178 | 3.31 m |
| 2025-08-14 | −62.036 | 3.19 m |
| 2025-10-13 | −62.044 | 3.08 m |
| 2025-10-29 | −61.768 | 2.92 m |
| 2025-11-12 | −62.035 | 3.25 m |

**N = −62.023 m, scene-to-scene sd 0.124 m.** The within-scene scatter of ~3.2 m matters as a check on the method itself: had the GCP z values been a synthetic multi-layer height grid rather than terrain samples, that scatter would be tens of metres and the solve would be meaningless. It is not, so the solve is valid. The value independently reproduces the −62.1 m geoid separately solved in our Round-2 work.

**Terrain cannot be neglected here.** The farm block carries **26.6 m of relief** (24.4–51.0 m orthometric), which a flat-earth height converts into up to **46 m of ground-range displacement** at 30° incidence — comparable to the width of a whole field on a 0.27 ha median plot. Measured on the GCP round trip:

| Height model | RPC round-trip RMSE |
|---|---|
| Best single constant height (−20 m) | 15.1 – 16.6 px |
| Copernicus GLO-30 + solved datum N | **4.1 – 4.7 px** |

Against Capella's own DEM-geocoded previews (10 m grid, log domain, at best alignment), mean correlation rises **0.769 → 0.840**, improving on every one of the six passes:

| Pass | constant height | terrain-referenced |
|---|---|---|
| 2025-06-06 | 0.792 | **0.896** |
| 2025-06-19 | 0.744 | 0.751 |
| 2025-08-14 | 0.787 | 0.824 |
| 2025-10-13 | 0.675 | 0.763 |
| 2025-10-29 | 0.830 | 0.898 |
| 2025-11-12 | 0.787 | **0.910** |

An earlier version of this work used a single constant height of −20 m ellipsoidal, solved by minimising misregistration against those same previews. All six passes agreed on that value, and its residual global shift was ≤2.8 m — which is why the error was not obvious. A global shift metric recovers the *mean* alignment while leaving the spatially varying terrain component untouched. The residual is what exposed it (§3.5).

### 3.5 Co-registration
Bounded phase correlation (search restricted to ±8 px) on Gaussian-smoothed dB imagery. The bound matters: unconstrained, the right-looking 29 October pass locks onto a spurious peak 242 m away, because its speckle and shadow structure differs too much from a left-looking reference.

| Pass | residual, constant height | residual, terrain-referenced |
|---|---|---|
| 19 Jun | 0.06 m | 0.08 m |
| 14 Aug | 0.03 m | 0.05 m |
| 13 Oct | 0.04 m | 0.06 m |
| **29 Oct (right-look)** | **2.54 m** | **0.12 m** |
| 12 Nov | 0.03 m | 0.04 m |

The 29 October row is the diagnostic. A height error displaces opposite look directions in *opposite* senses, so a residual that appears only on the single right-looking pass is a terrain signature, not a registration failure. Carrying per-pixel terrain removes it — 2.54 m to 0.12 m — which is independent confirmation that the DEM correction is doing what it claims.

### 3.6 Zonal statistics
Plots eroded 4 m inward to reject bunds and edge mixing (falling back to 1 m, then full polygon, then a 3×3 centroid window for the 10 sub-200 m² plots). Per plot and date: mean γ⁰ (linear, reported in dB), median, standard deviation, P10/P90, linear CV, fraction below NESZ, and a speckle-corrected structural heterogeneity computed from 10 m block means with the speckle floor `5.57/√(ENL·25)` removed in quadrature.

**Coverage.** The farm block is slightly wider than one Capella stripmap swath, so a straight NW–SE swath edge clips its north-west corner. Result: 832 plots with all six dates, 91 partial, 43 outside every footprint. Partial plots are scored on the dates they have; the 43 receive the crop mean with inflated uncertainty and a `not_observed_swath_edge` flag.

---

## 4. The geometry constraint, and the anomaly formulation

Backscatter depends on incidence angle and look direction, and differently for bare soil than for canopy, so no single normalisation (σ⁰, γ⁰, or a cosine power law) removes geometry exactly from a mixed scene. Two consequences shaped everything downstream.

**(a) Every feature is a village anomaly** — a plot's value minus the village median for that same acquisition. In a single step this removes absolute calibration error, receiver gain, incidence response, look direction, and the seasonal soil-moisture excursion common to all fields. What survives is plot-to-plot difference, which is what a yield map requires.

**(b) Differences only between geometry-safe pairs:**

| Pair | Δθ | Look | Measures |
|---|---|---|---|
| 19 Jun → 14 Aug | **0.08°** | same | canopy establishment |
| 13 Oct → 12 Nov | **1.78°** | same | late retention vs harvest |
| 29 Oct → 14 Aug | 1.15° | **opposite** | corroboration only |

The second pair is new in Round 3 and is what distinguishes a crop still standing from one already cut. The 29 October pass is never used alone.

---

## 5. What X-band HH actually measures here

Measured on this village: the median Δγ⁰ at peak season is **−0.58 dB relative to the pre-monsoon bare-soil baseline**. Peak-season fields are *darker* than bare ground.

This is physically expected, not an artefact: at HH a developed canopy attenuates a rough, freshly-tilled soil surface more than its own volume return replaces, and X-band saturates early against LAI. Two further facts point the same way — the 10 June Sentinel-2 scene shows **326 plots already green** at our "bare soil" baseline date, so a naive plot-specific baseline is itself contaminated; and within-field structural texture shows no correlation with NDVI (r ≈ 0.03), so it is not a greenness proxy.

**Therefore we do not invert X-band HH for biomass.** The model uses phenological *timing*, late-season *retention*, and within-field *evenness* — the quantities a metre-scale X-band series genuinely resolves.

---

## 5b. Using the phase: what we tried and what we found

The products are Single Look **Complex**. The obvious question is why the forecast rests on amplitude alone. We answered it by measurement, not assertion.

### 5b.1 Repeat-pass interferometry is structurally unavailable

For each of the fifteen pass pairs we computed, from the product state vectors, the perpendicular baseline at the scene reference target and the critical baseline `B_crit = λ·R·tan θ / (2·ρ_ground)`:

| Outcome | Pairs |
|---|---|
| Opposite look direction (one pass is right-looking) | 5 |
| Perpendicular baseline beyond `B_crit` | 9 |
| **Geometrically viable** | **1** |

The single viable pair is **19 Jun / 14 Aug**: B⊥ = 844 m against B⊥crit = 3975 m, giving geometric coherence 0.79, with Δθ = 0.08° and the same look direction. It is also **56 days apart**. X-band coherence over a developing canopy is typically 0.2–0.3 at 12 days and indistinguishable from noise beyond about three weeks, so temporal decorrelation removes the one remaining candidate.

Note the coincidence: the only interferometrically viable pair is the same pair we use as the geometry-safe establishment feature, and for the same underlying reason — it is the only pair acquired in near-identical geometry.

### 5b.2 Sub-aperture coherence — tested, and null

Sub-look processing avoids the problem entirely. Splitting the azimuth (Doppler) spectrum of a **single** acquisition into two halves yields two looks separated only in viewing angle, so there is no temporal decorrelation and no co-registration problem. Their complex correlation

```
gamma_sub = |<s1 s2*>| / sqrt(<|s1|²><|s2|²>)
```

is high where one deterministic scatterer dominates the resolution cell and low where the cell holds many comparable random scatterers. Agronomically it should separate fields whose return is dominated by strong structural elements — stalks, standing residue, bunds, row structure — from those returning diffuse clutter.

Two implementation details decide whether the estimator works at all, and both cost us a wrong answer first:

1. **The sub-looks must be demodulated to baseband before correlation.** They sit at different Doppler centroids, so `s1·conj(s2)` otherwise carries a phase ramp along azimuth that box-averaging cancels to zero. Our first attempt returned a uniform γ ≈ 0.04 everywhere.
2. **The split must happen inside the occupied band.** The product is azimuth-oversampled (0.735 m spacing against 1.23 m resolution), so only ~60% of the sampled band carries signal — measured directly, the occupied band is f ∈ [−0.30, +0.32] with power ~30 dB down outside. Splitting the full band loads ~45% empty spectrum into each sub-look and flattens the result.

With both fixed, the estimator behaves correctly:

| Amplitude class | mean γ_sublook |
|---|---|
| clutter (< p50) | 0.251 |
| bright (p90–p99) | 0.268 |
| very bright (p99–p99.9) | 0.346 |
| point-like (> p99.9) | **0.602** (max 0.977) |

Distributed clutter sits near the value expected for the number of independent looks in the window; dominant scatterers climb toward 1. The near-zero *global* correlation with amplitude (r = +0.04) is the point — this measures scatterer **dominance**, not brightness.

**At plot level, however, it carries no usable agronomic information:**

| Test | Result |
|---|---|
| Temporal repeatability (mean off-diagonal r across the six dates) | **0.017** |
| Crop separation, season-mean (Kruskal η²) | **0.020** |
| vs independent NDVI (13 Oct / 12 Nov) | ρ ≤ 0.11 |
| Scatterer-density variant (plot p90) | repeatability 0.082, η² 0.026, NDVI ρ ≈ 0.05 (n.s.) |

A stable plot property — bunds, row orientation, field structure — would repeat across independent acquisitions. It does not. Field-*averaged* X-band sub-look coherence is dominated by the speckle statistics of the estimator, and the few genuinely dominant scatterers are diluted by averaging over a whole field.

**Conclusion: reported as a null and excluded from the model.** We include it because the negative result is itself informative — it tells a future campaign that sub-aperture metrics on single-pol X-band will not substitute for the multi-temporal amplitude signal at field scale.

---

## 6. Crop labels

The brief specifies that crop classification is carried forward from prior rounds. We used two label sets and adjudicated between them.

1. **Carry-forward (primary).** Round-1 village crop composition imposed as a hard area constraint via a transportation LP over phenological template scores (our Round-2 method).
2. **Independent 6-pass re-derivation.** Village-anomaly templates over five features including the new 13 Oct → 12 Nov retention axis, again area-constrained.

They agree on **46%** of plots.

Adjudicating against Sentinel-2 NDVI — withheld from both — the carry-forward separates November greenness better:

| Label set | η², 12 Nov NDVI | η², 13 Oct NDVI |
|---|---|---|
| Round-2 carry-forward | **0.138** | **0.280** |
| Round-3 re-derivation | 0.085 | 0.217 |

Our new classifier is **not** an improvement, so we did not adopt it. The carry-forward stays primary. The disagreement is retained as a quantitative estimate of label uncertainty and propagated (§8.5, §9).

Both label sets rank November greenness Cotton > Rice > Groundnut > Maize > Bajra, which is the correct kharif ordering: cotton alone is still standing in mid-November.

---

## 7. Yield forecast model

### 7.1 Structure

```
Y_p = Y_ref(c) · S(c) · exp( σ_c·ρ·z_p − ½(σ_c·ρ)² )
```

### 7.2 SAR yield index `z_p`
Robustly standardised (median/IQR, clipped ±3) village anomalies of four components, combined with crop-specific stage weights and renormalised to unit variance:

| Component | Definition |
|---|---|
| `est` | establishment, 14 Aug − 19 Jun (Δθ 0.08°) |
| `oct` | standing canopy level, 13 Oct |
| `ret` | late retention, 12 Nov − 13 Oct (Δθ 1.78°) |
| `uni` | within-field uniformity, −(mean in-season linear CV) |

| Crop | est | oct | ret | uni | Rationale |
|---|---|---|---|---|---|
| Rice | 0.35 | 0.40 | 0.00 | 0.25 | grain fill visible on 13 Oct |
| Cotton | 0.25 | 0.25 | 0.25 | 0.25 | boll load persists into Nov |
| Maize | 0.55 | 0.15 | 0.00 | 0.30 | only one in-season look |
| Bajra | 0.55 | 0.15 | 0.00 | 0.30 | only one in-season look |
| Groundnut | 0.55 | 0.15 | 0.00 | 0.30 | only one in-season look |

### 7.3 Absolute anchor
`Y_ref(c)` is the Vadodara district yield (§2.3). `S(c)` is the 2025 season factor from the +16.06% East-Central Gujarat rainfall anomaly, with crop-specific sensitivity — rainfed coarse cereals gain most, irrigated rice barely, groundnut takes a small waterlogging penalty on vertisols:

| Crop | Y_ref (kg/ha) | S(c) | Anchor (kg/ha) |
|---|---|---|---|
| Rice | 1690 | 1.016 | 1717 |
| Cotton | 776 (lint) | 1.056 | 820 |
| Maize | 2312 | 1.072 | 2479 |
| Bajra | 2714 | 1.080 | 2932 |
| Groundnut | 2514 | 0.976 | 2453 |

The lognormal form makes the **area-weighted** village mean reproduce the anchor by construction (enforced by an explicit per-crop rescaling), so the anchor is a stated assumption, not an emergent claim.

### 7.4 Forecast versus reconstruction
`σ_c` is the farm-to-farm yield CV within a village (rice 0.28, cotton 0.35, maize 0.32, bajra 0.35, groundnut 0.33). `ρ = 0.55` is the fraction of that spread a six-pass X-band series plausibly explains, varied over 0.40–0.70.

The fraction of each crop's yield-forming cycle actually observed drives an additional forecast-horizon term `σ_c · 0.45 · (1 − f_obs)`:

| Crop | f_obs | Interpretation |
|---|---|---|
| Rice | 1.00 | completed season, reconstruction |
| Cotton | 0.78 | genuine extrapolation past 12 Nov to final picking |
| Groundnut | 0.60 | one in-season look |
| Maize | 0.55 | one in-season look |
| Bajra | 0.50 | one in-season look |

The 60-day gap between 14 Aug and 13 Oct brackets the entire maturity and harvest of maize, bajra and groundnut.

### 7.5 Uncertainty
Monte Carlo, 4,000 draws, with the error budget split by how it aggregates:

- **Systematic across a crop** — district reference ±12%, season factor ±6%, and 85% of the forecast-horizon term (the weather over the remaining cotton picking period is common to every cotton plot). Drawn once per crop per iteration.
- **Independent between plots** — the part of plot-to-plot spread the SAR index does not explain, `σ_c√(1−ρ²)`, inflated ×1.6 for unobserved plots; plus the remaining 15% of forecast-horizon risk.

Only independent terms average away on aggregation. Treating the systematic terms as independent is the usual reason village-level intervals come out implausibly tight — with 364 cotton plots it would have understated the village interval roughly five-fold.

---

## 8. Aggregation to village level

Aggregation is **area-weighted**, never a plain mean over plots: plot areas here span three orders of magnitude.

For crop *c*: `Ȳ_c = Σ(a_i · Y_i) / Σ a_i` and `P_c = Σ(a_i · Y_i)`.

Village-level intervals are taken from the same Monte-Carlo draws with the crop group held fixed, so an interval labelled "cotton yield" is genuinely an interval for cotton. Crop-label uncertainty is handled **separately** — resampling labels inside a fixed crop group would contaminate it with other crops' yield levels (an early version of this analysis did exactly that and produced intervals that did not bracket the central estimate).

The label sensitivity is therefore run as its own experiment: labels are drawn from the blended six-pass posterior, each simulated crop group is re-anchored to its own district reference, and both area and production move.

---

## 9. Validation and sanity checks

**Same-day optical.** Two Sentinel-2 scenes are same-day coincident with Capella passes:

| Comparison | Spearman ρ | n |
|---|---|---|
| γ⁰ vs NDVI, 13 Oct 2025 | +0.564 | 923 |
| γ⁰ vs NDVI, 12 Nov 2025 | +0.482 | 937 |

**The discriminating test — within crop.** The SAR yield index vs 13 Oct NDVI:

| Crop | ρ | p | Field status on 13 Oct |
|---|---|---|---|
| Rice | **+0.365** | 2×10⁻⁸ | standing |
| Cotton | **+0.361** | 1×10⁻¹² | standing |
| Groundnut | +0.112 | 0.079 | harvesting |
| Maize | +0.019 | 0.88 | harvested |
| Bajra | −0.071 | 0.61 | harvested |

The index correlates precisely where a crop is still in the field and is null precisely where it has been cut and both sensors see bare soil. A speckle-driven or spurious index would correlate everywhere or nowhere; this pattern is difficult to produce by accident.

**Why SAR is required, measured.** Of 46 Sentinel-2 overpasses of this AOI between June and November 2025, 10 were usable (<20% cloud). Between 19 June and 8 October there were **29 overpasses and none below 23.3% cloud** — a 111-day blackout covering sowing, establishment and peak vegetative growth. All six SAR passes were unaffected.

**Plausibility checks.** All village means sit within 2% of their stated anchors by construction; every plot forecast is positive and finite; all village P10–P90 intervals bracket their central forecast; interval width orders correctly with `f_obs` (bajra widest at ±20%, rice tightest); the yield map shows coherent spatial clustering rather than plot-level noise.

---

## 10. Results

| Crop | Plots | Area (ha) | Forecast (kg/ha) | P10 | P90 | Production (t) | Product |
|---|---|---|---|---|---|---|---|
| Rice | 226 | 60.39 | 1,717 | 1,401 | 2,021 | 103.7 | paddy grain |
| Cotton | 364 | 192.73 | 820 | 674 | 971 | 158.0 | lint |
| Maize | 74 | 34.27 | 2,479 | 2,009 | 2,968 | 85.0 | grain |
| Bajra | 54 | 34.58 | 2,932 | 2,378 | 3,576 | 101.4 | grain |
| Groundnut | 248 | 125.58 | 2,453 | 2,005 | 2,922 | 308.1 | pod |
| **Total** | **966** | **447.54** | — | — | — | **756.1** | |

Cotton at 820 kg/ha lint ≈ **2,342 kg/ha seed cotton (kapas)** at a 35% ginning outturn.

### 10.1 Crop-mix scenarios — the dominant uncertainty

The carry-forward puts groundnut at **28.5% of Sokhda's cropped area**. The Directorate of Agriculture puts groundnut at **0.35%** of Vadodara-Chhotaudepur's cropped area (10.04 of 2841.17 '00 ha, 2022-23). Those two statements cannot both be close to right, and it matters because groundnut carries a high per-hectare reference (2514 kg/ha) against cotton lint at 776.

Rather than choose silently, the assignment was run under both area constraints and both village tables are published:

| Crop | A · Round-1 carry-forward | B · District statistics |
|---|---|---|
| Rice | 61.5 ha → 105.6 t | 78.9 ha → 135.4 t |
| Cotton | 188.0 ha → 154.1 t | 291.8 ha → 239.2 t |
| Maize | 35.4 ha → 87.9 t | 64.2 ha → 159.1 t |
| Bajra | 35.1 ha → 102.9 t | 11.1 ha → 32.4 t |
| Groundnut | **127.5 ha → 312.8 t** | **1.7 ha → 4.0 t** |
| **Village total** | **763.2 t** | **570.2 t** |

A **25.3% swing in village production**, essentially all of it groundnut. Scenario A is primary because the brief specifies the carry-forward; scenario B is the alternative a reviewer is most likely to propose, and a reader who believes the district statistics should read B.

Two useful robustness observations. First, scenario A reproduces the primary result (756.1 t) to within **0.9%** despite reaching it by a different labelling route — the Round-1 area constraint applied to our six-pass posterior, rather than the Round-2 plot labels. Second, a separate experiment that resamples labels from the blended posterior *without* an area constraint gives a village total of 813–845 t, confirming that the total is far less sensitive to which individual plot carries which label than to the overall mix.

**This, not the radar, is the largest single uncertainty in the deliverable.**

---

## 11. Limitations

1. **No ground truth exists.** Absolute accuracy is untestable; only internal consistency and independent optical agreement can be checked.
2. **Maize, bajra and groundnut rest on one in-season observation.** Their intervals are wide by construction.
3. **Crop labels dominate the uncertainty**, not the radar. Two defensible methods disagree on half the plots.
4. **Only five classes are permitted**, but Vadodara also grows castor (425 '00 ha) and pigeon pea (422 '00 ha) at areas comparable to maize. Some plots are certainly another crop, and that error is not representable in this output.
5. **Cotton's final 22% is extrapolated.** A poor post-monsoon spell would move it more than anything already observed.
6. **43 plots were never observed** and receive the crop mean with inflated uncertainty.
7. **The district anchor is a 2022-23 statistic** for the combined Vadodara-Chhotaudepur district, not a Sokhda-specific figure.

---

## 12. Reproducibility

The public notebook runs the full chain from raw SLC to both output CSVs from a fresh restart, and ends with assertions verifying that all 966 plots carry a positive finite forecast, that every village interval brackets its central value, and that every village mean reproduces its stated anchor to within 2%.

## 13. References

- Directorate of Agriculture, Gujarat (2024). *Area, Production and Yield.*
- Parmar, K. & Bhatt, B. (2025). Evaluating agricultural patterns and crop shifts in Vadodara-Chhotaudepur District of Gujarat. *Int. J. Agriculture and Food Science* 7(5), 55–61.
- ICAR-CRIDA / AAU-Anand. *Agriculture Contingency Plan for District: Vadodara.* Govt. of India.
- IMD / Gujarat State Emergency Operations Centre — 2025 south-west monsoon summary.
- Capella Space — SAR Imagery Products Format Specification (radiometric conventions, RPC, NESZ).
- Attema, E.P.W. & Ulaby, F.T. (1978). Vegetation modeled as a water cloud. *Radio Science* 13(2), 357–364.
- Chakraborty, M. et al. — multi-temporal SAR crop monitoring for cotton and groundnut, Gujarat (RISAT-1).
