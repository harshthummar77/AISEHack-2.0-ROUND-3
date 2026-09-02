"""System architecture diagram for the Round-3 pipeline.

Boxes are sized from their content rather than hardcoded, so text can never
overflow its container.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(BASE, "SUBMISSION", "figures")
os.makedirs(FIG, exist_ok=True)

INK, MUTE = "#141B24", "#5B6876"
SIG, SIG_BG = "#15678A", "#E4EFF4"
GRN, GRN_BG = "#2C7254", "#E3F0E9"
AMB, AMB_BG = "#8F5F14", "#F7EEDC"
RED, RED_BG = "#9C3529", "#F8E7E4"
GREY_BG, GREY_EC = "#EDF1F3", "#C2CDD6"

TITLE_GAP, LINE_GAP, PAD_TOP, PAD_BOT = 3.1, 2.20, 1.7, 1.5
STAGE_GAP = 2.6

fig, ax = plt.subplots(figsize=(16.5, 9.6))
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
fig.patch.set_facecolor("white")


def box_h(lines):
    return PAD_TOP + TITLE_GAP + max(0, len(lines)) * LINE_GAP + PAD_BOT


def box(x, ytop, w, title, lines, fc, ec, ts=11.2, ls=8.9, lw=1.5):
    """Draw a box whose TOP edge is at `ytop`; height follows the content."""
    h = box_h(lines)
    y = ytop - h
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.30,rounding_size=0.9",
                                fc=fc, ec=ec, lw=lw, zorder=2))
    ax.text(x + w / 2, ytop - PAD_TOP, title, ha="center", va="top",
            fontsize=ts, fontweight="bold", color=INK, zorder=3)
    for i, ln in enumerate(lines):
        ax.text(x + 1.7, ytop - PAD_TOP - TITLE_GAP - i * LINE_GAP, ln,
                ha="left", va="top", fontsize=ls, color=MUTE, zorder=3)
    return y


def arrow(p1, p2, color=SIG, lw=2.0, ls="-", style="-|>"):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=16,
                                 lw=lw, color=color, linestyle=ls, zorder=1,
                                 shrinkA=1, shrinkB=1))


ax.text(50, 98.0, "Six Looks, One Harvest — system architecture",
        ha="center", fontsize=18.5, fontweight="bold", color=INK)
ax.text(50, 94.6, "Capella X-band SLC  →  final at-harvest yield forecast · 966 plots · Sokhda, Vadodara",
        ha="center", fontsize=11.2, color=MUTE)

# ------------------------------------------------------------ centre column
X, W = 25.5, 47.5
TOP = 91.0
stages = [
    ("1 · MEASUREMENT   SLC → calibrated γ⁰", [
        "β⁰ = (|DN|·scale)²  →  γ⁰ = β⁰·tan θ,  incidence per range sample",
        "RPC00B geocoding — 0.0000 px against the 225 embedded GCPs",
        "terrain-referenced: GLO-30 DEM, datum solved from GCPs (N = −62.02 m)",
        "bounded co-registration ≤ 0.12 m  →  2 m γ⁰ stack, six dates"]),
    ("2 · FEATURES   removing what we cannot separate", [
        "village-anomaly transform — cancels gain, incidence, look direction",
        "and the soil-moisture excursion common to every field",
        "geometry-safe pairs only:  19 Jun→14 Aug (Δθ 0.08°),  13 Oct→12 Nov (1.78°)",
        "zonal statistics on 4 m-eroded plots  →  0.13 dB plot-mean precision"]),
    ("3 · CROP LABELS   carried forward, uncertainty measured", [
        "primary: Round-1/2 carry-forward, area-constrained transportation LP",
        "independent 6-pass re-derivation agrees on 46% of observed plots",
        "adjudicated on withheld Sentinel-2 — carry-forward separates better,",
        "so it stays primary and the disagreement becomes label uncertainty"]),
    ("4 · YIELD FORECAST", [
        "Y_p  =  Y_ref(c) · S(c) · exp( σ_c ρ z_p  −  ½(σ_c ρ)² )",
        "z_p: establishment · Oct canopy · Nov retention · within-field evenness",
        "cotton late-picking extrapolation — the one genuine forecast term",
        "Monte Carlo ×4000, systematic and plot-independent errors separated"]),
    ("5 · AGGREGATION & OUTPUT", [
        "area-weighted roll-up by crop (plot areas span 3 orders of magnitude)",
        "crop-mix scenarios:  Round-1 763 t   vs   district statistics 570 t",
        "→ 966 plot forecasts with P10/P90  +  village table by crop"]),
]
tops, bots = [], []
y = TOP
for title, lines in stages:
    tops.append(y)
    yb = box(X, y, W, title, lines, SIG_BG, SIG)
    bots.append(yb)
    y = yb - STAGE_GAP
for i in range(len(stages) - 1):
    arrow((X + W / 2, bots[i]), (X + W / 2, tops[i + 1]))

# ------------------------------------------------------------- left column
in_top = 91.0
in_bot = box(1.0, in_top, 21.5, "INPUT DATA", [
    "6 × Capella X-band HH SLC",
    "complex, slant-range, 1 look",
    "28.7°–35.2°,  5 left + 1 right",
    "",
    "966 farm-plot polygons",
    "1 village boundary",
    "— no crop label in the file"], GREY_BG, GREY_EC)

ex_top = in_bot - 2.8
ex_bot = box(1.0, ex_top, 21.5, "EXTERNAL INPUTS", [
    "Copernicus GLO-30 DEM",
    "→ terrain referencing",
    "DoA Gujarat district yields",
    "→ absolute yield anchor",
    "ICAR-CRIDA crop calendar",
    "IMD 2025 monsoon, +16%",
    "→ season factor"], AMB_BG, AMB)

va_top = ex_bot - 2.8
va_bot = box(1.0, va_top, 21.5, "VALIDATION ONLY", [
    "Sentinel-2 L2A NDVI",
    "2 scenes same-day with SAR",
    "",
    "Withheld from every fitting",
    "step — the only reason the",
    "test carries any weight"], GRN_BG, GRN)

# ------------------------------------------------------------ right column
wy_top = 91.0
wy_bot = box(75.5, wy_top, 23.5, "WHY SAR AT ALL", [
    "46 Sentinel-2 overpasses",
    "Jun–Nov;  10 usable.",
    "",
    "19 Jun → 8 Oct: 29 passes,",
    "none below 23.3% cloud —",
    "a 111-day optical blackout.",
    "All six SAR passes clean."], AMB_BG, AMB)

tn_top = wy_bot - 2.8
tn_bot = box(75.5, tn_top, 23.5, "TESTED, NOT USED", [
    "Repeat-pass InSAR",
    "14 of 15 pairs impossible:",
    "5 opposite-look, 9 beyond",
    "the critical baseline. The one",
    "viable pair is 56 days apart —",
    "no X-band coherence survives.",
    "",
    "Sub-look coherence",
    "single-pass, so immune to",
    "temporal decorrelation.",
    "Estimator verified (points 0.98",
    "vs clutter 0.25) but the plot",
    "signal is null: repeatability",
    "r = 0.02,  crop η² = 0.02."], RED_BG, RED, ls=8.6)

# ---------------------------------------------------------------- arrows
arrow((22.5, in_top - 6), (X, tops[0] - 5))                      # SLC → stage 1
arrow((22.5, in_top - 17), (X, tops[0] - 10))                    # polygons → stage 1
arrow((22.5, ex_top - 4), (X, tops[0] - 14), color=AMB, ls=(0, (5, 3)), lw=1.6)
ax.text(23.6, ex_top - 1.0, "DEM", fontsize=8.6, color=AMB, ha="left")
arrow((22.5, ex_top - 15), (X, tops[3] - 8), color=AMB, ls=(0, (5, 3)), lw=1.6)

arrow((75.5, wy_top - 8), (X + W, tops[0] - 6), color=AMB, lw=1.6)
arrow((75.5, tn_top - 8), (X + W, tops[1] - 8), color=RED, lw=1.6, ls=(0, (4, 3)))
ax.text(74.5, tops[1] - 5.5, "phase", fontsize=8.6, color=RED, ha="right")

# validation touches the labels and the outputs, never the fitting
arrow((22.5, va_top - 6), (X, tops[2] - 13), color=GRN, ls=(0, (4, 3)), lw=1.8)
arrow((22.5, va_top - 13), (X, bots[4] + 6), color=GRN, ls=(0, (4, 3)), lw=1.8)

# ---------------------------------------------------------------- legend
LEG_Y = 3.4
items = [("data flow", SIG, "-"), ("external input", AMB, (0, (5, 3))),
         ("validation — never fitted", GRN, (0, (4, 3))),
         ("tested, rejected", RED, (0, (4, 3)))]
lx = 25.5
for lbl, col, ls in items:
    ax.plot([lx, lx + 3.4], [LEG_Y, LEG_Y], color=col, lw=2.0, ls=ls,
            solid_capstyle="butt")
    ax.text(lx + 4.1, LEG_Y, lbl, fontsize=9.0, color=MUTE, va="center", ha="left")
    lx += 4.1 + len(lbl) * 0.53 + 3.2

ax.text(50, 0.2, "Team 8bit · Harsh Thummar, Viraj Suhagiya · ANRF AISEHack 2.0 · Round 3",
        ha="center", fontsize=9.6, color=MUTE)

fig.savefig(os.path.join(FIG, "00_architecture.png"), dpi=150,
            facecolor="white", bbox_inches="tight", pad_inches=0.25)
print("wrote", os.path.join(FIG, "00_architecture.png"))
print("stage box bottoms:", [round(b, 1) for b in bots])
print("right column bottom:", round(tn_bot, 1), " left column bottom:", round(va_bot, 1))
