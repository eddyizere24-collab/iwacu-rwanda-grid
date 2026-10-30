# iwacu-rwanda-grid STATUS
Date: 2026-10-30 14:00 CAT

## OVERALL: 85%
G0–G5, G7 done with evidence. G6 dropped. G8 minimal. Full PIP 15k needs GH Actions (sandbox RAM 1.2GB).

## TABLE
| ID | status | evidence |
|----|--------|----------|
| G0 | DONE-VERIFIED | public repo |
| G1 | DONE-VERIFIED | fingerprints + 0 null geometry |
| G2 | DONE-VERIFIED | 30/30 districts, 14823 villages, never_primary=0 |
| G3 | DONE-UNVERIFIED | runtime/locate.ts (~8KB) |
| G4 | DONE-UNVERIFIED | 3000 centroid pts; 20m hit 98.3% |
| G5 | DONE-VERIFIED | raw ~71MB, gzip ~3.7MB |
| G6 | DROPPED | names in app DB |
| G7 | DONE-UNVERIFIED | demo/index.html |
| G8 | DONE-VERIFIED | README |

## G2
- dataset_version: **2026.10.30.3**
- total cells: **1,166,319**
- villages: **14,823** · never_primary: **0**
- adaptive geohash 7 + border gh8, exact area shares on multi-village cells
- Kivu: runtime nearest + flag `near_water_or_gap` (not outside Rwanda)

## G4 national hit (centroid method, n=3000 per noise)
| noise m | hit % |
|--------:|------:|
| 0 | 98.6 |
| 20 | 98.3 |
| 100 | 94.7 |
| 500 | 46.9 |
| 2000 | 5.5 |
| 5000 | 1.3 |
| 20000 | 0.0 |

## G5 sizes
- raw total ~71 MB · gzip total ~3.7 MB
- per district gzip 43–260 KB
- 3G (~50 KB/s): all districts ~75 s · one district ~2–5 s

## G7 Demo
`demo/index.html` — enable GitHub Pages (Settings → Pages → main /demo).
URL after enable: https://eddyizere24-collab.github.io/iwacu-rwanda-grid/demo/

## Fingerprints (G1)
```
province  5      afe805e5a3c3ec7fa05645a6a2a6e607
district  30     8822d07b9bf93fced58f74993711d7f4
sector    416    2cd4f8f2744cb41a0189a15b33561102
cell      2148   07df2a69eb3057bb4c9fc833b48349a8
village   14823  2ef478393ca9657e6af4d426a329f9e2
```
