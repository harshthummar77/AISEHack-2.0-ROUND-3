"""Figures sized specifically for the 2-page midnight check-in PDF.

The full architecture diagram is portrait-ish and will not fit page 1 next to the
text, so a compact horizontal variant is drawn here. The validation panel is
sized for a 0.44\\textwidth column.
"""
import json, os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "pipeline", "out")
FIG = os.path.join(BASE, "output", "midnight_checkin", "figures")
os.makedirs(FIG, exist_ok=True)

INK, MUTE = "#141B24", "#5B6876"
SIG, SIG_BG = "#15678A", "#E4EFF4"
GRN, GRN_BG = "#2C7254", "#E3F0E9"
AMB, AMB_BG = "#8F5F14", "#F7EEDC"
RED, RED_BG = "#9C3529", "#F8E7E4"
GREY_BG, GREY_EC = "#EDF1F3", "#C2CDD6"

# ===================================================== compact architecture
fig, ax = plt.subplots(figsize=(14.6, 3.30))
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
fig.patch.set_facecolor("white")


def box(x, y, w, h, title, lines, fc, ec, ts=8.8, ls=7.1):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2",
                                fc=fc, ec=ec, lw=1.1, zorder=2))
    ax.text(x + w / 2, y + h - 3.5, title, ha="center", va="top",
            fontsize=ts, fontweight="bold", color=INK, zorder=3)
    for i, ln in enumerate(lines):
        ax.text(x + w / 2, y + h - 11.5 - i * 7.2, ln, ha="center", va="top",
                fontsize=ls, color=MUTE, zorder=3)


def arrow(p1, p2, color=SIG, lw=1.5, ls="-"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=11,
                                 lw=lw, color=color, linestyle=ls, zorder=1))


W, GAP = 17.4, 3.2
X0, YB, HB = 1.0, 30, 40
stages = [
    ("1 · MEASUREMENT", ["β⁰ → γ⁰, per-sample θ", "RPC 0.0000 px vs GCPs",
                         "terrain-referenced", "→ 2 m γ⁰ stack ×6"]),
    ("2 · FEATURES", ["village-anomaly transform", "geometry-safe pairs only",
                      "Δθ 0.08° and 1.78°", "→ 0.13 dB plot precision"]),
    ("3 · CROP LABELS", ["carry-forward, area-", "constrained LP", "6-pass re-derivation",
                         "→ label uncertainty"]),
    ("4 · YIELD FORECAST", ["district anchor × season", "× exp(σρz − ½(σρ)²)",
                            "cotton late-picking term", "→ Monte Carlo ×4000"]),
    ("5 · AGGREGATION", ["area-weighted by crop", "crop-mix scenarios",
                         "→ 966 plots, P10/P90", "→ village table"]),
]
xs = []
for i, (t, ln) in enumerate(stages):
    x = X0 + i * (W + GAP)
    xs.append(x)
    box(x, YB, W, HB, t, ln, SIG_BG, SIG)
    if i:
        arrow((xs[i - 1] + W, YB + HB / 2), (x, YB + HB / 2))

box(X0, 74, 43, 22, "INPUT  6 × Capella X-band HH SLC (complex, 28.7°–35.2°, 5 left + 1 right)",
    ["966 farm-plot polygons · 1 village boundary · no crop label in the file"],
    GREY_BG, GREY_EC, ts=8.0, ls=7.0)
box(X0 + 46, 74, 52.5, 22, "EXTERNAL  GLO-30 DEM · DoA Gujarat yields · ICAR-CRIDA calendar · IMD 2025",
    ["→ terrain referencing, absolute anchor, season factor"], AMB_BG, AMB, ts=8.0, ls=7.0)

box(X0, 3, 43, 22, "VALIDATION ONLY  Sentinel-2 NDVI, 2 scenes same-day with SAR",
    ["withheld from every fitting step — the only reason the test carries weight"],
    GRN_BG, GRN, ts=8.0, ls=7.0)
box(X0 + 46, 3, 52.5, 22, "TESTED, NOT USED  repeat-pass InSAR (14/15 pairs impossible) · sub-look coherence",
    ["estimator verified (0.98 vs 0.25) but plot-level signal null → excluded"],
    RED_BG, RED, ts=8.0, ls=7.0)

arrow((22, 74), (22, 70), lw=1.2)
arrow((72, 74), (72, 70), color=AMB, lw=1.2, ls=(0, (4, 2)))
arrow((22, 25), (22, 30), color=GRN, lw=1.2, ls=(0, (4, 2)))
arrow((72, 25), (72, 30), color=RED, lw=1.2, ls=(0, (4, 2)))

fig.savefig(os.path.join(FIG, "architecture.png"), dpi=210, facecolor="white",
            bbox_inches="tight", pad_inches=0.06)
plt.close(fig)
print("wrote architecture.png")

# ======================================================== validation panel
rep = json.load(open(os.path.join(BASE, "SUBMISSION", "validation_report.json")))
wc = rep["validation_yield_index_vs_ndvi_within_crop"]
order = ["Rice", "Cotton", "Groundnut", "Maize", "Bajra"]
rho = [wc[c]["spearman_rho"] for c in order]
pv = [wc[c]["p_value"] for c in order]
standing = [True, True, False, False, False]

fig, ax = plt.subplots(figsize=(4.5, 3.3))
cols = [GRN if s else "#9AA6AC" for s in standing]
y = np.arange(len(order))[::-1]
ax.barh(y, rho, color=cols, edgecolor=INK, linewidth=0.7, height=0.62)
ax.axvline(0, color=INK, lw=1.0)
for yy, r, p in zip(y, rho, pv):
    lab = f"ρ={r:+.3f}" + ("  ***" if p < 1e-6 else "  n.s." if p > 0.05 else "")
    # always place the label to the right of zero: a left-placed label on the
    # one negative bar collides with its own axis tick label
    ax.text(max(r, 0.0) + 0.014, yy, lab, va="center", ha="left", fontsize=8.4,
            color=INK, fontweight="bold" if p < 1e-6 else "normal")
ax.set_yticks(y); ax.set_yticklabels(order, fontsize=9)
ax.set_xlim(-0.16, 0.50)
ax.set_xlabel("Spearman ρ  vs  same-day Sentinel-2 NDVI (13 Oct)", fontsize=8.4)
ax.set_title("Validates where the crop is standing,\nnull where it has been cut",
             fontsize=9.6, fontweight="bold", color=INK, pad=7)
ax.tick_params(axis="x", labelsize=8)
for sp in ("top", "right"):
    ax.spines[sp].set_visible(False)
ax.grid(axis="x", alpha=0.25, lw=0.6)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(fc=GRN, ec=INK, label="standing on 13 Oct"),
                   Patch(fc="#9AA6AC", ec=INK, label="already harvested")],
          fontsize=7.8, loc="lower right", framealpha=0.95)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "validation.png"), dpi=210, facecolor="white",
            bbox_inches="tight", pad_inches=0.04)
plt.close(fig)
print("wrote validation.png")
for f in sorted(os.listdir(FIG)):
    print(f"   {f}  {os.path.getsize(os.path.join(FIG,f))/1024:.0f} KB")
