# G1 Geometry + Fingerprints
Date: 2026-10-30

## Geometry coverage
- Source: NISR Village_Boundary_2022 FeatureServer/3, returnGeometry=true, outSR=4326
- Villages returned: **14823**
- Null / empty geometry: **0**
- Invalid type or short rings: **0**
- BBOX: lon [28.86173, 30.89975], lat [-2.84023, -1.04717]
- Known gap: Lake Kivu (no village polygons over water). G2 will flag gap/near-water cells with nearest village + lower confidence.

No village IDs with missing geometry to list.

## ID fingerprints (md5 of sorted IDs joined by ",")
| level | count | md5 |
|-------|------:|-----|
| province | 5 | afe805e5a3c3ec7fa05645a6a2a6e607 |
| district | 30 | 8822d07b9bf93fced58f74993711d7f4 |
| sector | 416 | 2cd4f8f2744cb41a0189a15b33561102 |
| cell | 2148 | 07df2a69eb3057bb4c9fc833b48349a8 |
| village | 14823 | 2ef478393ca9657e6af4d426a329f9e2 |

Owner inspector: compute same from app DB and compare.

## Names
- Keep original NISR names in data.
- Display provinces (Kinyarwanda):
  - 1 Umujyi wa Kigali
  - 2 Amajyepfo
  - 3 Iburengerazuba
  - 4 Amajyaruguru
  - 5 Iburasirazuba
- Do not propagate NISR typo "Estern Province".

## Evidence
- Local full GeoJSON ~133 MB (not committed; rebuild via script).
- fingerprints.json committed.
