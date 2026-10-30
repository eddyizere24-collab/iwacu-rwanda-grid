# iwacu-rwanda-grid STATUS
Date: 2026-10-30 10:55 CAT

## OVERALL: 22%
G0 DONE. G1 DONE-VERIFIED. G2 IN PROGRESS (scaffold + prototype). G3-G8 NOT STARTED.

## TABLE
| ID | status | evidence |
|----|--------|----------|
| G0 | DONE-VERIFIED | https://github.com/eddyizere24-collab/iwacu-rwanda-grid |
| G1 | DONE-VERIFIED | data/fingerprints.json + data/G1_geometry_report.md | SHA 221fc8ab33af578dea62416d6139152b1c705da9 |
| G2 | IN PROGRESS | scripts/build_grid.py (adaptive geohash point-sample v1) |
| G3 | NOT STARTED | |
| G4 | NOT STARTED | |
| G5 | NOT STARTED | |
| G6 | NOT STARTED | |
| G7 | NOT STARTED | |
| G8 | NOT STARTED | |

## G1 Fingerprints (for app-DB inspector)
```
province  5      afe805e5a3c3ec7fa05645a6a2a6e607
district  30     8822d07b9bf93fced58f74993711d7f4
sector    416    2cd4f8f2744cb41a0189a15b33561102
cell      2148   07df2a69eb3057bb4c9fc833b48349a8
village   14823  2ef478393ca9657e6af4d426a329f9e2
```

## G1 Geometry
- 14823 villages, **0 null, 0 invalid** geometry
- BBOX lon [28.86, 30.90] lat [-2.84, -1.05]
- Known gap: Lake Kivu (no polygons over water)

## G2 method (current)
- Point-sample proxy (~110 m) for speed; exact polygon area shares next iteration
- Per-district JSON chunks + manifest
- dataset_version: 2026.10.30.1

## Next
1. Run full 30-district build (local or GH Actions)
2. Exact area-share refinement + adaptive gh8
3. G4 validation harness (500 pts/district)
