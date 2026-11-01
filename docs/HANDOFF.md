# HANDOFF — iwacu-rwanda-grid

Standing rule: append a dated entry for every change. Never delete earlier entries.

Commit format: `[GROK] area: what - why - next`
Code: `CHANGED YYYY-MM-DD GROK: <what/why>; see docs/HANDOFF.md`

---

## 2026-11-01 20:20 — GROK — S0 INTEGRATION (wip/integrate)

**Agent:** GROK

**What:** Merged all WIP branches into `wip/integrate`. Single HANDOFF table. Stale "Java 17 / do not resume" lines removed (Planetiler Java 21 fix already on main; PMTiles built).

**Branch status table**

| branch | head SHA (40) | what it holds | verified | evidence |
|--------|---------------|---------------|----------|----------|
| main | ada1c59401589fadb1b785c95ac2cef483adb82f | offline_parity workflow registration; basemap vendor licences | partial | runs 41325735730 vendor; Pages 404 until owner enables |
| wip/g2 | 9d59f3e0770c73c8e601751cd5cdbe38834d39e1 | matrix exact-build invariants 11/12/13/37 | partial | run 41326892301 builds OK; merge missing geojson |
| wip/g3 | 03d2facaff46bc060d023bc3cdd00cbbe7a9899d | packages/grid-lookup IRG2 TS + basemap-style | partial | package present; full 100k parity fail path |
| wip/g4 | 5335eca1c06cc224fae828eb4049e39bdad3cd8d | export-boundaries + Kivu comparison docs | yes counts | run 41323271866 counts 1/5/30/416/2148/14823 |
| wip/g-dissolve | d95f726a703cf31ac066b00e303633b85196f4c0 | dissolve hierarchy snap 1m | yes tables | run 41325727657 invalid=0 sibling≪0.1% |
| wip/offline | 7d517a261d63440839d447a5650011fb71bd8096 | offline-locate + offline_validate harness | partial | smoke green 41325771621; parity path bug |
| wip/j | f3d94b82ab914ee57fa49f85582a7f8e3c77ecef | landmarks OSM extract + packages/landmarks | partial extract | run 41327676630 count 2552 tiles 556 |
| wip/k | c553e86385365cd22f57a9980b8915b7a61a2a8e | packages/places-search | smoke only | run 41327703444 |
| wip/integrate | (see latest commit on this branch) | all of the above combined | CI pending | integrate_ci.yml |

**Verified (historical)**
- IRG2 codec round-trip 0/100k (run 41285615471)
- rwanda.pmtiles on gh-pages 45,127,285 B
- dissolve parent/sibling metrics (run 41325727657)
- landmarks extract 2552 POIs (run 41327676630)

**Not verified / open**
- Pages demo 404 (owner Settings → Pages → gh-pages root)
- E invariants c/d national targets
- H 100k TS parity + 10k PIP
- K 1000 typo top-3
- J 200 brute-force nearby
- No NISR data committed (artifact only)

**Next:** light CI green on integrate; unit tests; overnight heavy runs after 22:00 only when ordered.

---

## Prior entries (summary)

- Planetiler Java 21 + Temurin setup-java (fixed; PMTiles success).
- IRG2 binary format; exclusive pure; hierarchical merge.
- Do not reintroduce "Java 17 failed, do not resume" — resolved.
