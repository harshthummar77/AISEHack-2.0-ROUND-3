"""Break the tracked file set into must-have / should-have / optional tiers."""
import os
import pathspec

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = pathspec.PathSpec.from_lines(
    "gitwildmatch", open(os.path.join(BASE, ".gitignore"), encoding="utf-8").read().splitlines())

tracked = []
for root, dirs, files in os.walk(BASE):
    rel = os.path.relpath(root, BASE).replace("\\", "/")
    rel = "" if rel == "." else rel
    if ".git" in dirs:
        dirs.remove(".git")
    dirs[:] = [d for d in dirs
               if not spec.match_file((f"{rel}/{d}" if rel else d) + "/")]
    for f in files:
        rf = f"{rel}/{f}" if rel else f
        if not spec.match_file(rf):
            tracked.append((rf, os.path.getsize(os.path.join(root, f))))


def tier(p):
    if p in ("README.md", ".gitignore") or p.endswith("round3-submission.ipynb"):
        return "1 MUST"
    if p.startswith("SUBMISSION/"):
        return "1 MUST"
    if p.startswith("output/"):
        return "2 SHOULD"
    if p.startswith("pipeline/") and p.endswith((".py", ".md")):
        return "2 SHOULD"
    if p.startswith("round_2_submmision_files/"):
        return "2 SHOULD"
    if p.startswith("pipeline/"):
        return "3 OPTIONAL"        # regenerable intermediates
    if p.startswith("tools/"):
        return "3 OPTIONAL"
    return "3 OPTIONAL"


groups = {}
for p, s in tracked:
    groups.setdefault(tier(p), []).append((p, s))

note = {
    "1 MUST": "the submission itself — without these there is nothing to judge",
    "2 SHOULD": "source code and provenance — the repo is judged as a codebase",
    "3 OPTIONAL": "regenerable or convenience — safe to drop",
}
total = sum(s for _, s in tracked)
for t in sorted(groups):
    files = sorted(groups[t])
    sz = sum(s for _, s in files)
    print(f"\n{'='*74}\n{t}   {len(files)} files, {sz/1024/1024:.2f} MB   ({note[t]})\n{'='*74}")
    by = {}
    for p, s in files:
        by.setdefault(p.split("/")[0] if "/" in p else "(root)", []).append((p, s))
    for g in sorted(by):
        gs = sum(s for _, s in by[g])
        print(f"  {g+'/':<28} {len(by[g]):3d} files  {gs/1024/1024:7.2f} MB")

print(f"\nTOTAL {len(tracked)} files, {total/1024/1024:.1f} MB")
opt = sum(s for _, s in groups.get("3 OPTIONAL", []))
print(f"dropping every OPTIONAL file would save {opt/1024/1024:.2f} MB "
      f"({len(groups.get('3 OPTIONAL', []))} files)")

print("\npipeline/ breakdown:")
py = [(p, s) for p, s in tracked if p.startswith("pipeline/") and p.endswith((".py", ".md"))]
other = [(p, s) for p, s in tracked if p.startswith("pipeline/") and not p.endswith((".py", ".md"))]
print(f"  source (.py/.md) : {len(py):3d} files, {sum(s for _,s in py)/1024:8.1f} KB")
print(f"  intermediates    : {len(other):3d} files, {sum(s for _,s in other)/1024:8.1f} KB")
for p, s in sorted(other, key=lambda x: -x[1])[:6]:
    print(f"      {s/1024:8.1f} KB  {p}")
