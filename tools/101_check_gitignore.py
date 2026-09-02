"""Simulate what git would track under .gitignore, before anything is committed.

Uses `pathspec`, which implements the real gitignore matching rules, so this is
an accurate preview rather than a guess.
"""
import os
import pathspec

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
lines = open(os.path.join(BASE, ".gitignore"), encoding="utf-8").read().splitlines()
spec = pathspec.PathSpec.from_lines("gitwildmatch", lines)

tracked, ignored_bytes, tracked_bytes = [], 0, 0
for root, dirs, files in os.walk(BASE):
    rel_root = os.path.relpath(root, BASE).replace("\\", "/")
    if rel_root == ".":
        rel_root = ""
    if ".git" in dirs:
        dirs.remove(".git")
    # prune ignored directories early so we do not walk 1.7 GB of SAR
    keep = []
    for d in dirs:
        rd = f"{rel_root}/{d}" if rel_root else d
        if spec.match_file(rd + "/"):
            tot = sum(os.path.getsize(os.path.join(dp, f))
                      for dp, _, fs in os.walk(os.path.join(root, d)) for f in fs)
            ignored_bytes += tot
        else:
            keep.append(d)
    dirs[:] = keep
    for f in files:
        rf = f"{rel_root}/{f}" if rel_root else f
        size = os.path.getsize(os.path.join(root, f))
        if spec.match_file(rf):
            ignored_bytes += size
        else:
            tracked.append((rf, size)); tracked_bytes += size

tracked.sort()
print("=" * 78)
print("FILES GIT WOULD TRACK")
print("=" * 78)
groups = {}
for f, s in tracked:
    groups.setdefault(f.split("/")[0] if "/" in f else "(root)", []).append((f, s))
for g in sorted(groups):
    gs = sum(s for _, s in groups[g])
    print(f"\n{g}/   —  {len(groups[g])} files, {gs/1024/1024:.2f} MB")
    for f, s in sorted(groups[g])[:60]:
        print(f"    {s/1024:9.1f} KB  {f}")

big = [(f, s) for f, s in tracked if s > 50 * 1024 * 1024]
print("\n" + "=" * 78)
print(f"TOTAL TRACKED : {len(tracked)} files, {tracked_bytes/1024/1024:.1f} MB")
print(f"TOTAL IGNORED : {ignored_bytes/1024/1024/1024:.2f} GB")
print(f"files >50 MB (GitHub warns at 50, blocks at 100): {len(big)}")
for f, s in big:
    print(f"   !! {s/1024/1024:.1f} MB  {f}")
must = ["SUBMISSION/WRITEUP.md", "SUBMISSION/METHODOLOGY.md",
        "SUBMISSION/aisehack_round3_sar_yield_forecast_EXECUTED.ipynb",
        "SUBMISSION/plot_level_yield_forecast.csv",
        "SUBMISSION/village_level_yield_forecast.csv",
        "output/midnight_checkin/Team8bit_Midnight_Checkin.pdf",
        "output/midnight_checkin/Team8bit_Midnight_Checkin.tex",
        "round_2_submmision_files/farm_level_results.csv",
        "pipeline/sarlib.py", "pipeline/cropmodel.py",
        "tools/80_make_notebook.py", "pipeline/README.md", "tools/README.md",
        ".gitignore", "README.md"]
names = {f for f, _ in tracked}
print("\nrequired files present in the tracked set:")
for m in must:
    print(("   ok   " if m in names else "   MISSING  ") + m)

# deliberately withheld from the push, but must still exist on disk because the
# Kaggle Writeup requires them as attachments
held = ["SUBMISSION/Team8bit_Round3_GoaFinals.pptx"]
print("\nheld back from the push (must still exist locally):")
for h in held:
    on_disk = os.path.exists(os.path.join(BASE, h))
    ignored = h not in names
    state = "ok   " if (on_disk and ignored) else "CHECK"
    print(f"   {state} {h}  on-disk={on_disk}  excluded-from-git={ignored}")
