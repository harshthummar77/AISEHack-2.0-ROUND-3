# ANRF AISEHack 2.0 — Round 3 submission

**Team 8bit** — Harsh Thummar, Viraj Suhagiya
Track: *Remote Sensing: Yield Estimation*
Site: Sokhda village (ID 22), Vadodara district, Gujarat — 966 plots, 447.5 ha

---

## Submission checklist

The brief requires a Kaggle **Writeup** with four attachments. Here is what maps to what.

| Requirement | File | Status |
|---|---|---|
| **Kaggle Writeup** (≤2000 words) | `WRITEUP.md` — 1,720 words | paste into the Writeup body |
| **a. Media Gallery** (cover image required) | `figures/00_architecture.png` … `08_…png` | attach all 9; set `01_cover.png` as cover |
| **b. Public Notebook** | `aisehack_round3_sar_yield_forecast_EXECUTED.ipynb` | upload to Kaggle, **set to Public**, attach in Project Files |
| **c. Written Documentation** | `METHODOLOGY.md` | attach (no video required this round) |
| **d. Goa Finals PPT** | `Team8bit_Round3_GoaFinals.pptx` — 14 slides | attach |

Also included (not required, but they make the result auditable):

| File | Contents |
|---|---|
| `plot_level_yield_forecast.csv` | 966 rows — final forecast, P10/P90, SAR index components, all six γ⁰ values, quality flag |
| `village_level_yield_forecast.csv` | 5 rows — village aggregate by crop |
| `crop_mix_scenarios.csv` | both crop-mix scenarios side by side |
| `Team8bit_Round3_results.xlsx` | the tables above plus the label-sensitivity sheet |
| `validation_report.json` | every validation statistic, assumption and limitation, machine-readable |

The media gallery leads with `00_architecture.png` — the whole system on one page, including the two approaches we tested and rejected.

**Before you submit:** the Writeup needs a Track selected, and a saved Writeup shows a **Submit** button top-right. A draft that is never submitted is not judged.

---

## Headline results

| Crop | Plots | Area (ha) | Forecast (kg/ha) | P10–P90 | Production (t) | Product |
|---|---|---|---|---|---|---|
| Rice | 226 | 60.4 | 1,717 | 1,401–2,021 | 103.7 | paddy grain |
| Cotton | 364 | 192.7 | 820 | 674–971 | 158.0 | lint |
| Maize | 74 | 34.3 | 2,479 | 2,009–2,968 | 85.0 | grain |
| Bajra | 54 | 34.6 | 2,932 | 2,378–3,576 | 101.4 | grain |
| Groundnut | 248 | 125.6 | 2,453 | 2,005–2,922 | 308.1 | pod |
| **Total** | **966** | **447.5** | — | — | **756.1** | |

Cotton lint 820 kg/ha ≈ **2,342 kg/ha seed cotton (kapas)** at 35% ginning outturn.

---

## What is new versus Round 2

1. **Round 2 delivered yield to date on 13 October. This is a final at-harvest forecast** — and the six passes cover the five crops very unevenly, which the method treats as a first-class fact rather than a caveat.
2. **Terrain-referenced geocoding with a solved datum.** Copernicus GLO-30 supplies per-sub-sample terrain; the ellipsoid/geoid shift is solved from the 225 embedded GCPs (N = −62.02 m, sd 0.12 m), independently reproducing the −62.1 m found in Round 2. RPC round-trip RMSE improves from 15–17 px to 4.1–4.7 px.
3. **A second geometry-safe date pair** (13 Oct → 12 Nov, Δθ 1.78°, same look) measures late-season canopy retention — the axis that separates a standing crop from a harvested one, unavailable in Round 2.
4. **Validation is sharper.** Two Sentinel-2 scenes are same-day coincident with Capella passes, and the yield index correlates significantly for the two crops still standing while being statistically null for the three already harvested.
5. **An honest negative result.** We re-derived the crop map from all six passes; it separates independent optical *worse* than the Round-2 carry-forward, so we did not adopt it, and the 46% agreement is carried through as label uncertainty instead.
6. **The phase question, answered with numbers.** Repeat-pass InSAR is structurally unavailable — 5 of 15 pairs are opposite-look, 9 exceed the critical baseline, and the one viable pair is 56 days apart. Sub-aperture (sub-look) coherence *is* single-pass and was implemented and verified (point scatterers γ = 0.98 vs 0.25 clutter), but is null at plot level and excluded. Both reported.
7. **The crop mix, quantified as the dominant uncertainty.** Groundnut at 28% (carry-forward) versus 0.35% (district) moves village production from **763 t to 570 t**. Both scenarios published.
8. **An explicit cotton extrapolation.** The one crop still standing at the last pass now carries a late-picking term driven by its own 13 Oct → 12 Nov canopy retention, rather than a flat variance inflation.

## A correction we made to our own work

An earlier version of this Round-3 pipeline geocoded at a single **constant** height of −20 m ellipsoidal, solved by minimising misregistration against Capella's own previews. All six passes agreed on that value with a residual global shift ≤2.8 m, which is why the error was not obvious — a global shift metric recovers the mean alignment and leaves the spatially varying terrain component untouched.

The farm block carries **26.6 m of relief**, worth up to **46 m of ground-range displacement** at 30° incidence. The tell was the single **right-looking** pass (29 Oct): a height error displaces opposite look directions in opposite senses, so a co-registration residual appearing only there is a terrain signature. Carrying per-pixel terrain collapsed it from **2.54 m to 0.12 m** and raised correlation against Capella's geocoding from 0.769 to 0.840, improving on all six passes.

Worth stating plainly: the downstream yield metrics barely moved (same-day ρ 0.564 vs 0.584 before). The correct geometry is the defensible one regardless — and the science holding steady under a real change in the measurement is itself evidence the result is not an artefact of processing choices.

---

## Reproducing

Two copies of the notebook are included:

- `..._EXECUTED.ipynb` — **upload this one.** Identical code, with all outputs saved, so a judge sees the results without waiting for a run.
- `...forecast.ipynb` — the same notebook with outputs cleared, if you prefer a clean upload.

**Verified end-to-end.** The notebook was executed from a fresh kernel and reproduces
`plot_level_yield_forecast.csv` and `village_level_yield_forecast.csv` **exactly** — zero
difference on all 966 plot forecasts and every village aggregate. Its own run also
reproduces the headline diagnostics: RPC RMS 0.00000 px, reference height −20 m from all
six passes, 2.54 m co-registration residual on the right-looking pass, 832 / 91 / 43
coverage split, 48.0% label agreement, and all closing assertions passing.

It runs the whole chain from raw SLC to both CSVs on a fresh Kaggle session
(~25–40 min, CPU is fine — the workload is I/O and NumPy, not GPU).

1. Attach the competition dataset.
2. **Enable Internet** in notebook settings — needed only for the Sentinel-2 validation cell, which skips cleanly if unavailable. The forecast itself does not require it.
3. Run all. The final cell asserts that all 966 plots carry a positive finite forecast, that every village interval brackets its central value, and that every village mean reproduces its stated anchor to within 2%.

Local runs work too — the notebook walks up from the working directory looking for a `DATA/` folder.

---

## Honest limitations

- No ground-truth yield exists anywhere, so **absolute accuracy is untestable**. Only internal consistency and independent optical agreement can be checked; both are reported in full.
- A **60-day gap (14 Aug → 13 Oct)** brackets the entire maturity and harvest of maize, bajra and groundnut. Their yield-forming period is sampled once, and their intervals are wide accordingly.
- **Crop labelling, not the radar, dominates the error budget.** Two defensible methods disagree on half the plots.
- Only five classes are permitted, but Vadodara also grows **castor and pigeon pea** at areas comparable to maize. Some plots are certainly another crop and that error cannot be represented here.
- **43 plots fall outside all six swath footprints** (the AOI is wider than one Capella stripmap). They carry the crop mean with inflated uncertainty and are flagged `not_observed_swath_edge`.
- The district anchor is a **2022-23 statistic for the combined Vadodara-Chhotaudepur district**, not a Sokhda-specific figure.
