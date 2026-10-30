# STATUS — Algorithm lock (30 Ukwakira 2026 14:15 CAT)

## OVERALL: 40%
Algorithm locked. GH4 chunks + pyramid built. Full A1–A7 SEED-TEST not yet run in Actions.

## TABLE
| Item | status | evidence |
|------|--------|----------|
| Algorithm | DONE-UNVERIFIED | runtime/locate_v2.ts |
| GH4 chunks | DONE-VERIFIED | 50 prefixes, ~3.3 MB gz |
| Summary pyramid | DONE-VERIFIED | **39.3 KB gz** (≤300 KB target) |
| never_primary | IN PROGRESS | force applied; CI recount |
| CI workflow | DONE-UNVERIFIED | .github/workflows/grid.yml |
| A1–A7 | NOT STARTED | needs Actions matrix |
| Demo v2 | IN PROGRESS | |

## Algorithm (locked — no deviation without measurement)
- Input accuracy a (m, Android 68% radius)
- σ = a / 1.51; a ≤ 10 m → point lookup
- precision p: 7 if σ≤450 m; 6 if σ≤1.8 km; else 5
- Cells whose centres within 3σ; weight w = exp(−d²/(2σ²))
- P(village) = Σ w·share / Σ w; hierarchy = sum over member villages
- Chosen level: finest with top-1 ≥ τ=0.80; else coarser
- Always top 3 villages + full path; never empty
- Chunks keyed by **geohash-4** (≤4 files / lookup)
- Outside country bbox → flag `outside_rwanda` (Kivu-inside = INSIDE)

## Why old 46.9% @ 500 m vs PostGIS ~93%
Old grid used single primary cell + scored vs **origin** village after noise (not PIP at noisy point). At 500 m the true village often changes. PostGIS border suite kept points inside polygons. New Gaussian weights + PIP truth + level backoff fix this class of error.

## Seeds
- SEED-TUNE = 424242
- SEED-TEST = 20261030

## Sizes
- Pyramid: 39.3 KB gz
- GH4 total: ~3.3 MB gz (50 files, mean ~65 KB)

## Acceptance A1–A7
All **UNVERIFIED** until Actions validate job completes on SEED-TEST with PIP ground truth.

## Next
1. Complete build_algo_grid.py + validate_district.py (PIP)
2. Run workflow; collect run URL
3. Fix failing district×noise slices; redeploy demo
