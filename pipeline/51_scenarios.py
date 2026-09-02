"""Crop-mix scenarios — confronting the groundnut question with numbers.

The Round-1 village composition carried forward puts groundnut at 28.5% of
Sokhda's cropped area. The Directorate of Agriculture puts groundnut at 0.35%
of Vadodara-Chhotaudepur's cropped area, and rice/maize/cotton far higher. Those
two statements cannot both be close to right, and the difference moves village
production because the per-hectare references differ by a factor of three.

Rather than pick silently, we run the assignment under both area constraints and
publish both village tables. The Round-1 mix stays primary because the brief
specifies the carry-forward; the district mix is reported as the alternative a
reviewer is most likely to propose.
"""
import json, os, sys
import numpy as np, pandas as pd
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "pipeline", "out")
sys.path.insert(0, os.path.join(BASE, "pipeline"))
from cropmodel import CROP_NAMES, CROPS, DISTRICT_AREA_00HA, season_factor

RHO = 0.55
YIELD_CV = {"Rice": 0.28, "Cotton": 0.35, "Maize": 0.32,
            "Bajra": 0.35, "Groundnut": 0.33}
F_SET_COTTON, KAPPA_RET = 0.70, 0.35

ROUND1_HA = {"Cotton": 136.03, "Groundnut": 92.38, "Rice": 44.59,
             "Maize": 25.80, "Bajra": 25.70}

crop3 = pd.read_csv(os.path.join(OUT, "plot_crop.csv")).set_index("plot_id")
res = pd.read_csv(os.path.join(OUT, "plot_yield_forecast.csv")).set_index("farm_id")
area = crop3["area_ha"]
post = crop3[["p_" + c for c in CROP_NAMES]].copy()
post.columns = CROP_NAMES
# the 43 plots outside every swath footprint have no posterior; give them a
# uniform prior so the LP places them purely on the area constraint
post = post.fillna(1.0 / len(CROP_NAMES))
post = post.div(post.sum(axis=1), axis=0).clip(lower=1e-6)
cost = -np.log(post)                              # LP cost = -log posterior
zcols = {k: res["z_" + k] for k in ["est", "oct", "ret", "uni"]}

WEIGHTS = {
    "Rice":      {"est": 0.35, "oct": 0.40, "ret": 0.00, "uni": 0.25},
    "Cotton":    {"est": 0.25, "oct": 0.25, "ret": 0.25, "uni": 0.25},
    "Maize":     {"est": 0.55, "oct": 0.15, "ret": 0.00, "uni": 0.30},
    "Bajra":     {"est": 0.55, "oct": 0.15, "ret": 0.00, "uni": 0.30},
    "Groundnut": {"est": 0.55, "oct": 0.15, "ret": 0.00, "uni": 0.30},
}


def z_for(cn):
    w = WEIGHTS[cn]
    num = pd.Series(0.0, index=area.index); den = pd.Series(0.0, index=area.index)
    for k, wk in w.items():
        if wk == 0:
            continue
        v = zcols[k].reindex(area.index)
        num = num.add((v * wk).fillna(0.0))
        den = den.add(pd.Series(np.where(v.notna(), wk, 0.0), index=area.index))
    z = num / den.replace(0, np.nan)
    return ((z - z.median()) / max(z.std(), 1e-9)).fillna(0.0)


ZI = {c: z_for(c).values for c in CROP_NAMES}
Z_RET = zcols["ret"].reindex(area.index).fillna(0.0).values
observed = crop3["observed"].reindex(area.index).fillna(False).values


def assign(target_ha):
    idx = area.index
    A = area.values
    Cm = cost.loc[idx, CROP_NAMES].values
    n, k = Cm.shape
    tgt = np.array([target_ha[c] for c in CROP_NAMES], float)
    tgt = tgt / tgt.sum() * A.sum()
    rows, cols, vals = [], [], []
    for i in range(n):
        for jj in range(k):
            rows.append(i); cols.append(i * k + jj); vals.append(1.0)
    for jj in range(k):
        for i in range(n):
            rows.append(n + jj); cols.append(i * k + jj); vals.append(A[i])
    Aeq = coo_matrix((vals, (rows, cols)), shape=(n + k, n * k))
    beq = np.concatenate([np.ones(n), tgt])
    r = linprog((Cm * A[:, None]).ravel(), A_eq=Aeq, b_eq=beq,
                bounds=(0, 1), method="highs")
    lab = r.x.reshape(n, k).argmax(axis=1)
    return pd.Series([CROP_NAMES[j] for j in lab], index=idx), tgt


def village(labels):
    j = np.array([CROP_NAMES.index(c) for c in labels])
    Yref = np.array([CROPS[c]["yield_ref"] for c in CROP_NAMES])[j]
    Sf = np.array([season_factor(c) for c in CROP_NAMES])[j]
    sc = np.array([YIELD_CV[c] for c in CROP_NAMES])[j]
    z = np.array([ZI[CROP_NAMES[jj]][i] for i, jj in enumerate(j)])
    z = np.where(observed, z, 0.0)
    shape = np.exp(sc * RHO * z - 0.5 * (sc * RHO) ** 2)
    isc = np.array([c == "Cotton" for c in labels])
    lm = np.ones(len(j))
    lm[isc] = F_SET_COTTON + (1 - F_SET_COTTON) * np.clip(1 + KAPPA_RET * Z_RET[isc], .3, 1.9)
    shape = shape * lm
    a = area.values
    out = []
    for jj, c in enumerate(CROP_NAMES):
        m = j == jj
        if m.sum() == 0:
            continue
        wm = (shape[m] * a[m]).sum() / a[m].sum()
        y = shape[m] * (Yref[m][0] * Sf[m][0]) / wm
        out.append({"crop_type": c, "n_plots": int(m.sum()),
                    "area_ha": round(float(a[m].sum()), 2),
                    "yield_kg_ha": round(float((y * a[m]).sum() / a[m].sum()), 1),
                    "production_t": round(float((y * a[m]).sum() / 1000), 2)})
    return pd.DataFrame(out)


DISTRICT_MIX = {c: DISTRICT_AREA_00HA[c] for c in CROP_NAMES}
scen = {}
for name, tgt in [("A_round1_carryforward", ROUND1_HA),
                  ("B_district_statistics", DISTRICT_MIX)]:
    lab, t = assign(tgt)
    v = village(lab)
    scen[name] = v
    print("=" * 88)
    print(f"SCENARIO {name}")
    print("=" * 88)
    print(v.to_string(index=False))
    print(f"  total production {v.production_t.sum():.1f} t over {v.area_ha.sum():.1f} ha")
    print()

print("=" * 88)
print("SIDE BY SIDE")
print("=" * 88)
a = scen["A_round1_carryforward"].set_index("crop_type")
b = scen["B_district_statistics"].set_index("crop_type")
cmp = pd.DataFrame({
    "area_A_ha": a.area_ha, "area_B_ha": b.area_ha,
    "shareA_%": (100 * a.area_ha / a.area_ha.sum()).round(1),
    "shareB_%": (100 * b.area_ha / b.area_ha.sum()).round(1),
    "prod_A_t": a.production_t, "prod_B_t": b.production_t,
}).loc[CROP_NAMES]
print(cmp.to_string())
print(f"\nvillage total: A {a.production_t.sum():.1f} t   B {b.production_t.sum():.1f} t   "
      f"difference {100*(b.production_t.sum()/a.production_t.sum()-1):+.1f}%")

pd.concat([a.assign(scenario="A_round1"), b.assign(scenario="B_district")]).to_csv(
    os.path.join(OUT, "crop_mix_scenarios.csv"))
json.dump({"scenario_A_total_t": float(a.production_t.sum()),
           "scenario_B_total_t": float(b.production_t.sum()),
           "round1_ha": ROUND1_HA, "district_00ha": DISTRICT_AREA_00HA},
          open(os.path.join(OUT, "scenario_meta.json"), "w"), indent=1)
print("\nwrote crop_mix_scenarios.csv, scenario_meta.json")
