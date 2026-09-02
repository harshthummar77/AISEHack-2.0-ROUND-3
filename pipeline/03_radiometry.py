import json, glob, os
import rasterio, numpy as np

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "DATA")
scenes = sorted(glob.glob(os.path.join(ROOT, "CAPELLA_*")))

s = scenes[0]
tif = [t for t in glob.glob(os.path.join(s, "*.tif")) if "_SLC_" in os.path.basename(t)][0]
with rasterio.open(tif) as ds:
    tags = ds.tags()
    meta = json.loads(tags["TIFFTAG_IMAGEDESCRIPTION"])
print("TIFF IMAGEDESCRIPTION top-level keys:", list(meta.keys()))
print(json.dumps({k: v for k, v in meta.items() if k != "collect"}, indent=1)[:1500])
col = meta["collect"]
print("\ncollect keys:", list(col.keys()))
img = col["image"]
print("\nimage keys:", list(img.keys()))
print(json.dumps({k: v for k, v in img.items() if not isinstance(v, (list,))}, indent=1)[:3000])
if "radiometry" in img:
    print("\nRADIOMETRY:", json.dumps(img["radiometry"], indent=1)[:1500])
for k in ["state", "radar", "geometry"]:
    if k in col:
        print(f"\ncollect[{k}] keys:", list(col[k].keys()) if isinstance(col[k], dict) else type(col[k]))

# extended json
ext = glob.glob(os.path.join(s, "*_extended.json"))[0]
e = json.load(open(ext))
print("\n\nEXTENDED keys:", list(e.keys()))
def walk(d, p="", depth=0):
    if depth > 3: return
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (dict,)):
                print("  "*depth, p+k, "{}", list(v.keys())[:14])
                walk(v, p+k+".", depth+1)
            elif isinstance(v, list):
                print("  "*depth, p+k, f"[list n={len(v)}]", str(v[:2])[:160])
            else:
                print("  "*depth, p+k, "=", str(v)[:140])
walk(e)
