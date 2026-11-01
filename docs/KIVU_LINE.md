# Kivu shoreline comparison (one page)

**Agent:** GROK · **Date:** 2026-11-01

## Sources measured in CI (kivu_deviation.json on results branch)

| Source | Role |
|--------|------|
| **OSM Nominatim / admin_level=2 Rwanda** | Used for national polygon union with NISR villages; includes Rwanda’s share of Lake Kivu water. |
| **geoBoundaries RWA ADM0** | Independent international boundary; tends to follow shoreline differently on the lake. |
| **NISR village polygons** | Land villages only; lake surface is **outside** village union (~1009–1011 km² Kivu water piece added when unioned with OSM ADM0). |

## Numbers (from published results)

- National area after villages ∪ OSM: **~25,325 km²** (land-dominated; official land+water figures differ by definition).
- Kivu water piece (national minus villages): **~1,009.9 km²** before simplify, **~1,010.7 km²** after 100 m simplify; centroid **≈ (−2.038, 29.193)**.
- OSM vs geoBoundaries along lake (20 sample positions): **max deviation ≈ 10,081 m**, **mean ≈ 2,148 m**. Largest gaps near mid-lake sample indices (e.g. i=10…15 in published table).

## Recommendation

**Use OSM admin_level=2 (Nominatim polygon) as the reference line for Kivu / national “inside Rwanda” checks.**

Reasons:
1. Consistent with the **~1,010 km²** Rwanda-side lake piece needed so offshore points on Rwanda’s side are not false OUTSIDE.
2. geoBoundaries ADM0 systematically diverges by up to ~10 km on the lake (mean ~2 km); treating it as equal authority produces ambiguous test points.
3. NISR villages do not model open water; they remain the authority for **land** village identity, not the international water boundary.

Operational rule already in use: Kivu test points keep **≥300 m margin from the OSM line**; points within 300 m of either line are **ambiguous** and not scored.

## Risks

- OSM can be edited; pin a download date in CI artifacts when locking a release.
- Official political boundary treaties may differ from OSM; this recommendation is for **engineering consistency** of the grid/national polygon, not a legal determination.
