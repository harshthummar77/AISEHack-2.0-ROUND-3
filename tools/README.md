# Tools

Packaging and quality-assurance scripts. These produce and check the submission
artifacts; they are **not** part of the processing chain — that is `../pipeline/`.

Kept in the repo so every deliverable has provenance: nothing in `SUBMISSION/` or
`output/` was assembled by hand.

| Script | Produces / checks |
|---|---|
| `61_architecture.py` | `SUBMISSION/figures/00_architecture.png` — the system diagram |
| `62_checkin_figs.py` | the two figures used by the 2-page Goa check-in brief |
| `80_make_notebook.py` | builds the public notebook by embedding the real `pipeline/` sources, so the published code cannot drift from the code that produced the numbers |
| `90_make_ppt.py` | the 16-slide Goa deck, with speaker notes |
| `99_consistency.py` | sweeps every shipped document for numbers left over from an earlier run, and enforces the 2,000-word writeup limit |
| `100_preflight.py` | pre-submission gate: 39 checks over file presence, 966-row completeness, interval bracketing, plot/village reconciliation, notebook error outputs, deck integrity |
| `101_check_gitignore.py` | simulates what `git` would track, using real gitignore semantics, before anything is committed |
| `102_verify_checkin.py` | verifies the check-in PDF is exactly 2 pages and carries every section the organisers' template requires |

## Order

Run after the pipeline has produced `pipeline/out/`:

```bash
python tools/61_architecture.py
python tools/90_make_ppt.py
python tools/80_make_notebook.py
python tools/62_checkin_figs.py     # then compile output/midnight_checkin/*.tex
python tools/99_consistency.py
python tools/100_preflight.py       # must end "NO BLOCKERS"
python tools/101_check_gitignore.py
```

All scripts resolve paths from the repo root, so they run from anywhere.
