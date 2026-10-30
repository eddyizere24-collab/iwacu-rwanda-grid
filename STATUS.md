# STATUS — WORK ORDER 02 (30 Ukwakira 2026 19:20 CAT)

## OVERALL: 48%

## TABLE
| Item | status | evidence |
|------|--------|----------|
| G1 scripts | DONE-VERIFIED | scripts/build_algo_grid.py (10318 B), validate_district.py (11746 B), aggregate.py (4370 B) |
| G2 country polygon | PARTIAL | geoBoundaries ADM0; meta + kivu CSV committed; full geojson built in Actions |
| G2 kivu points | DONE-VERIFIED | data/kivu_test_points.csv |
| G3 smoke/full | NOT STARTED | nta Actions run URL |
| G4 size proof | PARTIAL | local max GH4 gz ~138 KB |
| G5 A1 interior/border | UNVERIFIED | |
| G6 46.9 vs 93 | UNVERIFIED | |
| G7 deploy | BLOCKED | A1-A7 not PASS |

## G2 Country polygon
- **Source ADM0 URL:** https://github.com/wmgeolab/geoBoundaries/raw/main/releaseData/gbOpen/RWA/ADM0/geoBoundaries-RWA-ADM0.geojson
- **Kivu border:** geoBoundaries RWA ADM0 international boundary through Lake Kivu
- Area ~24,624 km2 (0.004 deg buffer)
- Raw ADM0: 63 centroids outside; buffer 0.004: 5 residual; CI script uses buffer 0.01
- data/kivu_test_points.csv: 25 INSIDE + 25 OUTSIDE + neighbors in Burundi/Tanzania/Uganda/DRC

## Seeds
SEED-TUNE=424242 · SEED-TEST=20261030

## A1–A7
All **UNVERIFIED** (no Actions run URL with tables).
