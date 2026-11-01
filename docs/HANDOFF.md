# HANDOFF — iwacu-rwanda-grid

Standing rule: append a dated entry for every change. Never delete earlier entries.

Commit message format: `[GROK] area: what - why - next`
Logic changes: short comment `CHANGED YYYY-MM-DD GROK: <what/why>; see docs/HANDOFF.md`

---

## 2026-11-01 — GROK — initial handoff (grid IRG2 + base map start)

**Agent:** GROK

**What changed**
- Established this HANDOFF log and commit-message convention for all future work on this repo.
- Grid pipeline (prior work, not modified in this commit): exact geometry lattice build, exclusive pure cells, strict 32-child hierarchical merge, binary index format **IRG2** (length-prefixed ASCII geohash keys; replaced broken IRG1 int-delta codec that caused ~94% missing lookups).
- Base map job started: Planetiler build of `rwanda.pmtiles` from Geofabrik `rwanda-latest.osm.pbf`, MapLibre + PMTiles demo, `ATTRIBUTION.md` (OSM / ODbL). Workflow `basemap.yml`.

**Why**
- Project lead requires durable cross-agent handoff; IRG2 fixed codec round-trip; own base map so runtime needs no third-party tile server.

**Files (this commit)**
- `docs/HANDOFF.md` (this file)

**Related prior commits (grid / basemap)**
- `bfe6a45accd8ad944a4576907d3bcbe4aeee42a6` — IRG2 builder + bisect tests + single invariants workflow
- `4d38314c6bec83ed088e9589e8f008ba79486e2b` — basemap Planetiler workflow, demo HTML, ATTRIBUTION.md

**Current state**

### Grid / IRG (4 districts: 11, 12, 13, 37) — run https://github.com/eddyizere24-collab/iwacu-rwanda-grid/actions/runs/41285615471
| Metric | Result |
|--------|--------|
| Codec round-trip | **PASS** (8,568,693 cells, 0 key miss, 0/100k lookup disagree) |
| a_missing | **0 / 49314 PASS** |
| b pure mismatch | **0.0% PASS** |
| c pure r0 by quartile | 99.583 / 99.341 / 99.907 / 99.805 — **FAIL** (need ≥99.9% all) |
| d interior r0 overall | **98.988% FAIL** (need ≥99%) |
| Size max lookup | **110.33 KB PASS** (≤150 KB) |
| Results branch SHA | `34fa0fe4f8bd281611cb9802ab089de45c1caab7` |

Grid work was **stopped by project lead** pending first public release; not required for that release.

### Base map (PMTiles)
| Item | Status |
|------|--------|
| Workflow | `basemap.yml` |
| Commit | `4d38314c6bec83ed088e9589e8f008ba79486e2b` |
| Run | https://github.com/eddyizere24-collab/iwacu-rwanda-grid/actions/runs/41319587186 |
| Goal | Single `rwanda.pmtiles` z0–14 under 100 MB, GitHub Pages + MapLibre demo (Kigali, Nyamasheke/Kivu, Musanze) |
| Verified | **NOT VERIFIED** until run completes (size, layers, range requests, live URL) |

**Verified vs not verified**
- **Verified:** IRG2 codec round-trip; invariants a=0; size ≤150 KB lookup (CI + results branch).
- **Not verified:** c/d targets; national 30-district matrix; PMTiles build/size/Pages demo.

**Open risks**
- c/d short of target (border / pure-cell cross-district wrong majority examples remain).
- PMTiles may exceed 100 MB at z14 → workflow falls back to z12.
- GitHub Pages must serve byte-range requests for PMTiles; peaceiris gh-pages deploy used.
- Planetiler layer names must match MapLibre style (`water`, `roads`, `places`, etc.).

**How to roll back**
- Grid: checkout pre-IRG2 commit `f3dfbd0ae3403854e4b79ac079f07dee6cbc290c` or results artifacts from run 41215566556 (IRG1, broken lookups).
- Basemap: delete workflow run / remove `gh-pages` branch content; revert commit `4d38314c…`.

**Next step**
- Wait for basemap run 41319587186; report size, layers, feature counts, build time, demo URL; no further pushes while that run is active.
- Grid: do not resume until project lead requests.
