# G1 NISR vs Expected App DB Reconciliation
Date: 2026-10-30
Source: https://gis-server.statistics.gov.rw/server/rest/services/Hosted/Village_Boundary_2022/FeatureServer/3
Query: all villages, returnGeometry=false, ordered by village_id

## Counts
| Level | NISR unique | Expected app | Diff |
|-------|-------------|--------------|------|
| Province (intara) | 5 | 5 | 0 |
| District (akarere) | 30 | 30 | 0 |
| Sector (umurenge) | 416 | 416 | 0 |
| Cell (akagari) | 2148 | 2148 | 0 |
| Village (umudugudu) | 14823 | 14823 | 0 |

## Hierarchy integrity
All 14823 village_id values pass length and prefix hierarchy checks (province_id 1 digit, district 2, sector 4, cell 6, village 8; each child starts with parent id).

## Province names (NISR spelling)
- 1: City of Kigali
- 2: Southern Province
- 3: Western Province
- 4: Northern Province
- 5: Estern Province

Note: NISR spells province 5 as 'Estern Province' (missing 'a'). App may normalise to 'Eastern Province' / "Intara y'Iburasirazuba".

## Districts (id, name)
- 11: Nyarugenge
- 12: Gasabo
- 13: Kicukiro
- 21: Nyanza
- 22: Gisagara
- 23: Nyaruguru
- 24: Huye
- 25: Nyamagabe
- 26: Ruhango
- 27: Muhanga
- 28: Kamonyi
- 31: Karongi
- 32: Rutsiro
- 33: Rubavu
- 34: Nyabihu
- 35: Ngororero
- 36: Rusizi
- 37: Nyamasheke
- 41: Rulindo
- 42: Gakenke
- 43: Musanze
- 44: Burera
- 45: Gicumbi
- 51: Rwamagana
- 52: Nyagatare
- 53: Gatsibo
- 54: Kayonza
- 55: Kirehe
- 56: Ngoma
- 57: Bugesera

## Unmatched / missing villages
Live NISR download returned exactly 14823 unique village_id. No villages missing relative to the expected 14823 count.
Previous notes about 7 or ~21 NISR-missing villages appear outdated against current FeatureServer response.
App DB snapshot (data/buex_snapshot/) is NOT yet present in iwacu-rwanda-grid. Cannot join id-by-id until the other agent uploads it.

## ID style used by app download script
scope_code example: RW-P1-D11-S1101-C110101-V11010101
nisr village_id remains the 8-digit official key.

## Evidence
- Download method: Python urllib to FeatureServer/3, page size 1000, offsets 0..14000
- Total features returned: 14823
- Unique village_id: 14823
- Zero hierarchy violations
- Local artifact: nisr_villages_attrs.json (attributes only, no geometry)

## Next
When data/buex_snapshot/ appears, join on village_id / nisr_id and list any residual unmatched rows. Do not start G2 until that join is done.
