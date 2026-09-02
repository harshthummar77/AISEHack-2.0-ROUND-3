"""Media gallery for the Round-3 writeup."""
import json, os, sys, urllib.request
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.transform import Affine
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, ListedColormap
from matplotlib.patches import Patch
import matplotlib.patheffects as pe

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO, OUT = os.path.join(BASE, "pipeline", "geo"), os.path.join(BASE, "pipeline", "out")
FIG = os.path.join(BASE, "SUBMISSION", "figures")
os.makedirs(FIG, exist_ok=True)
sys.path.insert(0, os.path.join(BASE, "pipeline"))
from sarlib import UTM43N, to_db
from cropmodel import ACQ_DATES, CROP_NAMES, CROPS, season_factor

plt.rcParams.update({"font.size": 10, "axes.titlesize": 11.5,
                     "figure.facecolor": "white", "savefig.facecolor": "white"})
CROP_COL = {"Rice": "#3d8bcd", "Cotton": "#e8e3d3", "Maize": "#e8a33d",
            "Bajra": "#b05fce", "Groundnut": "#6dbf67"}
CROP_COL_DARK = {"Rice": "#1f5f96", "Cotton": "#a89878", "Maize": "#c07a10",
                 "Bajra": "#7d3a96", "Groundnut": "#3d8a38"}

man = json.load(open(os.path.join(GEO, "manifest.json")))
tr = Affine(*man["transform"]); W, H = man["width"], man["height"]; RES = man["res"]
EXT = [tr.c, tr.c + W * RES, tr.f - H * RES, tr.f]
TAGS = [s["tag"] for s in man["scenes"]]

stack = []
for t in TAGS:
    with rasterio.open(os.path.join(GEO, f"gamma0_{t}.tif")) as ds:
        stack.append(ds.read(1))
stack = np.stack(stack)
DB = to_db(stack)

farms = gpd.read_file(os.path.join(BASE, "DATA", "Farm_boundaries_shp",
                                   "Farm_boundaries_shp", "Sokhda_Farms.shp")).to_crs(UTM43N)
farms["geometry"] = farms.geometry.buffer(0)
farms["plot_id"] = farms["FID"].astype(int)
vill = gpd.read_file(os.path.join(BASE, "DATA", "Village_Shp", "Village_Shp",
                                  "Sokhda_Village.shp")).to_crs(UTM43N)

res = pd.read_csv(os.path.join(OUT, "plot_yield_forecast.csv")).set_index("farm_id")
vilf = pd.read_csv(os.path.join(OUT, "village_yield_forecast.csv"))
sens = pd.read_csv(os.path.join(OUT, "label_sensitivity.csv"))
nd = pd.read_csv(os.path.join(OUT, "plot_ndvi.csv")).set_index("plot_id")
G = farms.merge(res.reset_index(), left_on="plot_id", right_on="farm_id", how="left")

BB = farms.total_bounds
PAD = 250
XLIM, YLIM = (BB[0] - PAD, BB[2] + PAD), (BB[1] - PAD, BB[3] + PAD)


def stretch(a, lo=2, hi=98):
    v = a[np.isfinite(a)]
    p1, p2 = np.percentile(v, [lo, hi])
    return np.clip((a - p1) / max(p2 - p1, 1e-9), 0, 1)


def basemap(ax, idx=3, cmap="gray"):
    ax.imshow(DB[idx], extent=EXT, cmap=cmap,
              vmin=np.nanpercentile(DB[idx], 3), vmax=np.nanpercentile(DB[idx], 97))
    ax.set_xlim(*XLIM); ax.set_ylim(*YLIM); ax.set_xticks([]); ax.set_yticks([])


def scalebar(ax, length=500):
    x0 = XLIM[0] + 150; y0 = YLIM[0] + 180
    ax.plot([x0, x0 + length], [y0, y0], color="w", lw=3.5,
            path_effects=[pe.withStroke(linewidth=6, foreground="k")])
    ax.text(x0 + length / 2, y0 + 60, f"{length} m", color="w", ha="center",
            fontsize=9, path_effects=[pe.withStroke(linewidth=2.5, foreground="k")])


# ---------------------------------------------------------------- 01 cover
rgb = np.dstack([stretch(DB[2]), stretch(DB[3]), stretch(DB[1])])
rgb = np.nan_to_num(rgb)
fig, ax = plt.subplots(figsize=(13, 9.5))
ax.imshow(rgb, extent=EXT)
farms.boundary.plot(ax=ax, color="white", linewidth=0.5, alpha=.8)
vill.boundary.plot(ax=ax, color="#ffd24d", linewidth=2.0)
ax.set_xlim(*XLIM); ax.set_ylim(*YLIM); ax.set_xticks([]); ax.set_yticks([])
ax.set_title("Sokhda village, Vadodara — Capella X-band HH multi-temporal composite\n"
             "R = 14 Aug (peak vegetative)   G = 13 Oct (grain fill)   B = 19 Jun (monsoon onset)",
             fontsize=13, pad=12)
ax.text(0.015, 0.965, "966 plots · 447.5 ha · 6-pass SLC time series · 2 m $\\gamma^0$",
        transform=ax.transAxes, color="w", fontsize=11.5, va="top",
        path_effects=[pe.withStroke(linewidth=3, foreground="k")])
ax.text(0.985, 0.965, "Team 8bit", transform=ax.transAxes, color="#ffd24d",
        fontsize=12, va="top", ha="right", weight="bold",
        path_effects=[pe.withStroke(linewidth=3, foreground="k")])
scalebar(ax)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "01_cover.png"), dpi=145); plt.close(fig)

# ------------------------------------------------- 02 yield forecast map
fig, axs = plt.subplots(1, 2, figsize=(17, 8.2))
basemap(axs[0])
# relative-to-crop-mean so all five crops share one colour scale
G["rel"] = G.groupby("crop_type").yield_forecast_kg_ha.transform(
    lambda s: s / s.mean()) * 100
G.plot(ax=axs[0], column="rel", cmap="RdYlGn", vmin=70, vmax=130,
       edgecolor="k", linewidth=0.15, legend=True,
       legend_kwds={"label": "forecast yield, % of crop mean", "shrink": .75})
axs[0].set_xlim(*XLIM); axs[0].set_ylim(*YLIM); axs[0].set_xticks([]); axs[0].set_yticks([])
axs[0].set_title("Final yield forecast, relative to each crop's village mean")
scalebar(axs[0])

basemap(axs[1])
for c in CROP_NAMES:
    sub = G[G.crop_type == c]
    if len(sub):
        sub.plot(ax=axs[1], color=CROP_COL[c], edgecolor="k", linewidth=0.15)
axs[1].legend(handles=[Patch(facecolor=CROP_COL[c], edgecolor="k",
                             label=f"{c} — {vilf.set_index('crop_type').area_ha.get(c, 0):.0f} ha")
                       for c in CROP_NAMES], loc="lower right", fontsize=9, framealpha=.92)
axs[1].set_xlim(*XLIM); axs[1].set_ylim(*YLIM); axs[1].set_xticks([]); axs[1].set_yticks([])
axs[1].set_title("Crop assignment (Round-1/2 carry-forward, area-constrained)")
scalebar(axs[1])
fig.tight_layout(); fig.savefig(os.path.join(FIG, "02_yield_and_crop_map.png"), dpi=140); plt.close(fig)

# ------------------------------------- 03 absolute yield maps, per crop panel
fig, axs = plt.subplots(2, 3, figsize=(18, 11))
for ax, c in zip(axs.ravel(), CROP_NAMES):
    basemap(ax)
    farms.boundary.plot(ax=ax, color="#555", linewidth=0.12)
    sub = G[G.crop_type == c]
    if len(sub):
        sub.plot(ax=ax, column="yield_forecast_kg_ha", cmap="viridis",
                 edgecolor="k", linewidth=0.15, legend=True,
                 legend_kwds={"label": "kg/ha", "shrink": .8})
    ax.set_xlim(*XLIM); ax.set_ylim(*YLIM); ax.set_xticks([]); ax.set_yticks([])
    r = vilf.set_index("crop_type")
    ax.set_title(f"{c} — {r.area_ha.get(c,0):.0f} ha, "
                 f"{r.yield_forecast_kg_ha.get(c,0):.0f} kg/ha ({CROPS[c]['product']})")
axs.ravel()[-1].axis("off")
txt = ("Absolute forecast yield by crop\n\n"
       "Level anchored to Vadodara district\nyield (DoA Gujarat 2022-23),\n"
       "adjusted for the 2025 season.\n\n"
       "SAR sets the distribution around\nthat mean, not the mean itself.")
axs.ravel()[-1].text(0.05, .55, txt, fontsize=12, va="center")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "03_yield_by_crop.png"), dpi=135); plt.close(fig)

# --------------------------------------------- 04 village summary charts
fig, axs = plt.subplots(1, 3, figsize=(17.5, 5.6))
v = vilf.set_index("crop_type").loc[CROP_NAMES]
cols = [CROP_COL_DARK[c] for c in v.index]
axs[0].bar(v.index, v.area_ha, color=cols, edgecolor="k")
for i, (a, s) in enumerate(zip(v.area_ha, v.area_share_pct)):
    axs[0].text(i, a + 4, f"{a:.0f} ha\n{s:.0f}%", ha="center", fontsize=9)
axs[0].set_ylabel("area (ha)"); axs[0].set_title("Village crop area — Sokhda, 447.5 ha")
axs[0].tick_params(axis="x", rotation=20)

err = np.vstack([v.yield_forecast_kg_ha - v.yield_p10_kg_ha,
                 v.yield_p90_kg_ha - v.yield_forecast_kg_ha])
axs[1].bar(v.index, v.yield_forecast_kg_ha, yerr=err, capsize=5, color=cols, edgecolor="k")
axs[1].scatter(range(len(v)), v.district_ref_kg_ha, marker="_", s=420, color="k", zorder=5)
axs[1].set_ylabel("kg/ha"); axs[1].tick_params(axis="x", rotation=20)
axs[1].set_title("Forecast yield with P10–P90\n(black dash = district reference)")

perr = np.vstack([v.production_t - v.production_p10_t, v.production_p90_t - v.production_t])
axs[2].bar(v.index, v.production_t, yerr=perr, capsize=5, color=cols, edgecolor="k")
for i, p in enumerate(v.production_t):
    axs[2].text(i, p + 6, f"{p:.0f} t", ha="center", fontsize=9)
axs[2].set_ylabel("tonnes"); axs[2].tick_params(axis="x", rotation=20)
axs[2].set_title(f"Forecast production — village total {v.production_t.sum():.0f} t")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "04_village_summary.png"), dpi=140); plt.close(fig)

# ---------------------------------------- 05 temporal signatures + geometry
longdf = pd.read_csv(os.path.join(OUT, "plot_stats_long.csv"))
gp = longdf.pivot(index="plot_id", columns="date", values="g0_db")[ACQ_DATES]
lab = res.crop_type
doy = [pd.Timestamp(d).dayofyear for d in ACQ_DATES]

fig, axs = plt.subplots(1, 3, figsize=(18, 5.6))
for c in CROP_NAMES:
    idx = lab[lab == c].index.intersection(gp.index)
    axs[0].plot(doy, gp.loc[idx].median(), marker="o", color=CROP_COL_DARK[c],
                label=f"{c} (n={len(idx)})")
axs[0].set_ylabel("median $\\gamma^0$ (dB)"); axs[0].set_xlabel("day of year 2025")
axs[0].set_xticks(doy); axs[0].set_xticklabels([d[5:] for d in ACQ_DATES], rotation=45)
axs[0].legend(fontsize=8); axs[0].grid(alpha=.3)
axs[0].set_title("Per-crop X-band HH trajectory")

dgv = gp.sub(gp[ACQ_DATES[0]], axis=0)
dgv = dgv.sub(dgv.median(axis=0), axis=1)
for c in CROP_NAMES:
    idx = lab[lab == c].index.intersection(dgv.index)
    axs[1].plot(doy, dgv.loc[idx].median(), marker="o", color=CROP_COL_DARK[c], label=c)
axs[1].axhline(0, color="k", lw=.8)
axs[1].set_ylabel("village anomaly of $\\Delta\\gamma^0$ (dB)")
axs[1].set_xticks(doy); axs[1].set_xticklabels([d[5:] for d in ACQ_DATES], rotation=45)
axs[1].grid(alpha=.3); axs[1].legend(fontsize=8)
axs[1].set_title("Anomaly form used by the model\n(scene gain, incidence and look direction removed)")

inc = [s["incidence"] for s in man["scenes"]]
look = [s["look"] for s in man["scenes"]]
cl = ["#2f6fae" if l == "left" else "#c0392b" for l in look]
axs[2].bar(range(6), inc, color=cl, edgecolor="k")
for i, (a, l) in enumerate(zip(inc, look)):
    axs[2].text(i, a + .25, f"{a:.1f}°\n{l}", ha="center", fontsize=8.5)
axs[2].set_xticks(range(6)); axs[2].set_xticklabels([d[5:] for d in ACQ_DATES], rotation=45)
axs[2].set_ylabel("incidence angle (°)"); axs[2].set_ylim(0, 40)
axs[2].set_title("Acquisition geometry varies\n28.7°–35.2°, one right-looking pass")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "05_temporal_signatures.png"), dpi=140); plt.close(fig)

# ------------------------------------------- 06 uncertainty / forecast content
fig, axs = plt.subplots(1, 3, figsize=(17.5, 5.4))
w = ((v.yield_p90_kg_ha - v.yield_p10_kg_ha) / v.yield_forecast_kg_ha * 100)
axs[0].barh(v.index, w, color=cols, edgecolor="k")
for i, x in enumerate(w):
    axs[0].text(x + 1, i, f"{x:.0f}%", va="center", fontsize=9)
axs[0].set_xlabel("P10–P90 width, % of central forecast")
axs[0].set_title("Village-level forecast uncertainty")

axs[1].barh(v.index, v.season_observed_frac * 100, color=cols, edgecolor="k")
for i, x in enumerate(v.season_observed_frac * 100):
    axs[1].text(x + 1, i, f"{x:.0f}%", va="center", fontsize=9)
axs[1].set_xlim(0, 115); axs[1].set_xlabel("% of yield-forming cycle observed")
axs[1].set_title("How much of each crop the 6 passes actually saw")

for c in CROP_NAMES:
    s = res[res.crop_type == c].yield_forecast_kg_ha
    if len(s) > 5:
        axs[2].hist(s / s.mean(), bins=28, histtype="step", lw=1.8,
                    color=CROP_COL_DARK[c], label=c)
axs[2].set_xlabel("plot forecast / crop mean"); axs[2].set_ylabel("plots")
axs[2].legend(fontsize=8); axs[2].set_title("Within-village yield distribution")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "06_uncertainty.png"), dpi=140); plt.close(fig)

# ------------------------------------------------ 07 optical blackout
try:
    body = {"collections": ["sentinel-2-l2a"], "bbox": [73.133, 22.408, 73.181, 22.443],
            "datetime": "2025-06-01T00:00:00Z/2025-11-30T00:00:00Z", "limit": 200}
    rq = urllib.request.Request("https://earth-search.aws.element84.com/v1/search",
                                data=json.dumps(body).encode(),
                                headers={"Content-Type": "application/json"})
    fs = json.load(urllib.request.urlopen(rq, timeout=60))["features"]
    rec = sorted({(f["properties"]["datetime"][:10],
                   round(f["properties"]["eo:cloud_cover"], 1)) for f in fs
                  if "43QBE" in f["id"]})
    dd = [pd.Timestamp(a).dayofyear for a, _ in rec]
    cc = [b for _, b in rec]
    fig, ax = plt.subplots(figsize=(13.5, 5))
    ax.bar(dd, cc, width=2.4, color=["#2e8b57" if c < 20 else "#c0392b" for c in cc],
           edgecolor="k", linewidth=.4)
    ax.axhline(20, ls="--", color="k", lw=1)
    for d in doy:
        ax.axvline(d, color="#1f4e9c", lw=2.2, alpha=.85)
    ax.axvspan(pd.Timestamp("2025-06-19").dayofyear, pd.Timestamp("2025-10-08").dayofyear,
               color="grey", alpha=.16)
    ax.set_ylabel("Sentinel-2 cloud cover (%)"); ax.set_xlabel("day of year 2025")
    ax.set_title("The monsoon optical blackout, measured for this AOI\n"
                 "blue = the six Capella acquisitions · shaded = 111-day gap with no usable optical scene")
    ax.set_ylim(0, 105)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "07_optical_blackout.png"), dpi=140)
    plt.close(fig)
    usable = [(a, b) for a, b in rec if b < 20]
    print("optical: total overpasses", len(rec), "usable(<20% cloud)", len(usable))
    mons = [(a, b) for a, b in rec
            if pd.Timestamp("2025-06-19") <= pd.Timestamp(a) <= pd.Timestamp("2025-10-08")]
    print("  during 19 Jun - 8 Oct:", len(mons), "overpasses, best cloud",
          min([b for _, b in mons]) if mons else None)
except Exception as e:
    print("blackout figure skipped:", e)

# ----------------------------------- 08 round2 -> round3: to-date vs forecast
r2 = pd.read_csv(os.path.join(BASE, "round_2_submmision_files",
                              "farm_level_results.csv")).set_index("farm_id")
j = res.join(r2[["yield_estimate_to_date", "health_index"]])
fig, axs = plt.subplots(1, 3, figsize=(17.5, 5.4))
sc = axs[0].scatter(j.yield_estimate_to_date, j.sar_yield_index_z, s=9, alpha=.5,
                    c=[CROP_COL_DARK.get(c, "grey") for c in j.crop_type])
axs[0].set_xlabel("Round 2: yield to date (index, 13 Oct)")
axs[0].set_ylabel("Round 3: SAR yield index z")
axs[0].set_title("Round 2 (to date) vs Round 3 (final)"); axs[0].grid(alpha=.3)

axs[1].scatter(res.z_est, res.z_ret, s=9, alpha=.5,
               c=[CROP_COL_DARK.get(c, "grey") for c in res.crop_type])
axs[1].set_xlabel("establishment  z  (14 Aug − 19 Jun)")
axs[1].set_ylabel("late retention  z  (12 Nov − 13 Oct)")
axs[1].set_title("The two geometry-safe axes\n(Δincidence 0.08° and 1.78°)")
axs[1].grid(alpha=.3)
axs[1].legend(handles=[Patch(facecolor=CROP_COL_DARK[c], label=c) for c in CROP_NAMES],
              fontsize=8, loc="lower right")

sv = sens.set_index("crop_type").loc[CROP_NAMES]
y = np.arange(len(sv))
axs[2].barh(y, sv.production_t_p90 - sv.production_t_p10, left=sv.production_t_p10,
            color=[CROP_COL_DARK[c] for c in sv.index], edgecolor="k", alpha=.85)
axs[2].scatter(v.production_t.values, y, color="k", zorder=5, marker="D", s=42)
axs[2].set_yticks(y); axs[2].set_yticklabels(sv.index)
axs[2].set_xlabel("production (t)")
axs[2].set_title("Sensitivity to crop-label uncertainty\n(bars = P10–P90 when labels are resampled)")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "08_round2_to_round3.png"), dpi=140); plt.close(fig)

print("\nwrote figures to", FIG)
for f in sorted(os.listdir(FIG)):
    print("  ", f)
