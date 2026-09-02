"""Verify the midnight check-in PDF against the organisers' template."""
import os, zipfile
import pymupdf

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(BASE, "output", "midnight_checkin")
pdf = os.path.join(D, "Team8bit_Midnight_Checkin.pdf")

d = pymupdf.open(pdf)
t = "".join(p.get_text() for p in d)
print(f"pages: {d.page_count}  ->  {'OK (limit 2)' if d.page_count == 2 else 'WRONG'}")
print(f"size : {os.path.getsize(pdf)/1024:.0f} KB")

need = ["Project Title", "Team Name", "Primary Domain", "Data Sources Used",
        "Proposed Strategy", "Ancillary Grounding", "Preliminary Salient Results",
        "Technical Challenges", "Final Sprint Roadmap", "Appendix",
        "Page 1: Problem, Strategy, and Novelty",
        "Page 2: Evidence, Obstacles, and Execution"]
print("\ntemplate sections present:")
missing = [n for n in need if n not in t]
for n in need:
    print(("  ok        " if n not in missing else "  MISSING   ") + n)
print("\n  github link :", "github.com/harshthummar77" in t)
print("  authors     :", "Harsh Thummar" in t and "Viraj Suhagiya" in t)
print("  headline t  :", "756.1" in t)

zp = os.path.join(D, "Overleaf_upload.zip")
if os.path.exists(zp):
    print("\nOverleaf zip contents:")
    for n in zipfile.ZipFile(zp).namelist():
        print("   ", n)

print("\nfolder:")
for root, _, files in os.walk(D):
    for f in sorted(files):
        p = os.path.join(root, f)
        print(f"   {os.path.getsize(p)/1024:8.1f} KB  "
              f"{os.path.relpath(p, D)}")
print("\nBLOCKERS:" if missing or d.page_count != 2 else "\nNo blockers.")
