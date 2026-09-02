"""Sweep every shipped document for numbers left over from an earlier run."""
import json, os, re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["SUBMISSION/WRITEUP.md", "SUBMISSION/METHODOLOGY.md",
         "SUBMISSION/README.md", "pipeline/artifact_src.html"]
txt = {f: open(os.path.join(BASE, f), encoding="utf-8").read() for f in FILES}

STALE = {
    "same-day rho +0.58 (was)": r"\+0\.58\b",
    "same-day rho +0.49 (was)": r"\+0\.49\b",
    "within-crop 0.395 (was)": r"0\.395",
    "within-crop 0.351 (was)": r"0\.351",
    "eta2 0.089 (was)": r"0\.089",
    "eta2 0.222 (was)": r"0\.222",
    "48% agreement (was)": r"\b48%",
    "'-20 m ellipsoidal' as the method": r"minimise[sd]? at \*\*-20 m",
    "corr 0.68-0.83 (was)": r"0\.68[^\d]{1,3}0\.83",
}
print("STALE-NUMBER SWEEP")
bad = 0
for name, pat in STALE.items():
    hits = [f for f, t in txt.items() if re.search(pat, t)]
    if hits:
        bad += 1
        print(f"  !! {name:36s} -> {hits}")
if not bad:
    print("  clean - no superseded values found")

print("\nCURRENT-VALUE PRESENCE")
for name, pat in {"same-day 0.56": r"\+?0\.56", "same-day 0.48": r"\+?0\.48",
                  "rice 0.365": r"0\.365", "cotton 0.361": r"0\.361",
                  "agreement 46%": r"46%", "geoid -62.02": r"62\.02",
                  "corr 0.840": r"0\.840", "relief 26.6": r"26\.6",
                  "RMSE 4.1": r"4\.1", "coreg 0.12 m": r"0\.12 m"}.items():
    print(f"  {name:16s}", [os.path.basename(f) for f, t in txt.items() if re.search(pat, t)])

w = len(re.sub(r"\|", "", txt["SUBMISSION/WRITEUP.md"]).split())
print(f"\nwriteup word count: {w}  (limit 2000)  ->", "OK" if w <= 2000 else "OVER")

rep = json.load(open(os.path.join(BASE, "SUBMISSION/validation_report.json")))
print("\nvalidation_report.json cross-check:")
print("  same-day:", {k: v["spearman_rho"] for k, v in rep["validation_same_day_optical"].items()})
print("  within-crop:", {k: v["spearman_rho"]
                         for k, v in rep["validation_yield_index_vs_ndvi_within_crop"].items()})
print("  label agreement (observed):", round(rep["crop_label_agreement_round2_vs_round3"], 4))
print("  coreg residual m:", rep["sar"]["coregistration_residual_m"])
print("  ref height field:", rep["sar"].get("reference_height_m_ellipsoidal"))
