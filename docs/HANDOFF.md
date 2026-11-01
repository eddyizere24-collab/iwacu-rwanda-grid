# HANDOFF — iwacu-rwanda-grid

Standing rule: append a dated entry for every change. Never delete earlier entries.

Commit message format: `[GROK] area: what - why - next`
Logic changes: short comment `CHANGED YYYY-MM-DD GROK: <what/why>; see docs/HANDOFF.md`

---

## 2026-11-01 — GROK — DESIGN: packages/offline-locate (no DB)

**Agent:** GROK

**What:** Design (code follows) for offline `locate(lat, lng, accuracy_m)` over shipped IRG2 grid + optional compact mixed-cell polygons + national polygon (Kivu piece).

**Why:** App must answer hierarchical place with honest probabilities without Supabase.

### Algorithm (locked)

1. **Sigma:** `sigma = accuracy_m / 1.51` (Android 68% radius → isotropic Gaussian). If `accuracy_m <= 10` treat as point (`sigma ≈ 0`).
2. **Precision:** choose geohash precision `p` from sigma: `p=7` if `sigma ≤ 450 m`; `p=6` if `sigma ≤ 1.8 km`; else `p=5`.
3. **Cell set:** enumerate precision-`p` cells whose **centres** lie within `3·sigma` of the reported point. Weight `w = exp(-d² / (2·sigma²))`. No plain circle-overlap.
4. **Shares:** from IRG2 index (exact area shares at build). `P(village v) = Σ_c w_c · share(c,v) / Σ w_c`.
5. **Hierarchy:** `P(akagari|umurenge|akarere|intara) = sum of P over contained villages` (from village meta codes in root payload).
6. **Answer level:** finest level whose top-1 probability ≥ `TAU` (start **0.80**). Else one level coarser. Never empty: fall back up to province; if national polygon flags outside → `{ outside: true }`.
7. **Mixed / fine path:** for `sigma ≤ 15 m` (≈ accuracy ≤ 20 m), resolve **finest leaf** containing the point (gh8/gh9) via longest-prefix on IRG2; if leaf is mixed, optional compact polygon PIP among candidate villages for that leaf only.
8. **Large sigma / pyramid:** for `sigma > 150 m` do **not** fetch all fine gh6 leaves. Use precomputed **summary pyramid** stored in root (or gh5/gh6 summary files): top-20 village distribution + aggregated akagari/umurenge/akarere/intara per coarse cell. Ship target ≤ 300 KB gz national coarse index.

### Data structures

| Asset | Role |
|-------|------|
| `root.bin.gz` | IRG2 pure coarse cells (≤ gh5) + JSON meta (`vid_order`, villages path codes) |
| `gh6/{prefix}.bin.gz` | Fine pure/mixed leaves for mixed neighbourhoods |
| `pyramid` (in root or `pyramid.bin.gz`) | Sparse top-20 village + hierarchy for every gh5/gh6 |
| `rwanda_national.geojson` (simplified) | Outside check including Kivu water piece |
| Optional `mixed_polys/{gh6}.bin` | Compact polygons only for mixed leaves (size-gated) |

### API

```ts
locate(lat, lng, accuracy_m) -> {
  level: 'village'|'akagari'|'umurenge'|'akarere'|'intara'|null,
  path: { village?, cell?, sector?, district?, province? },
  per_level_candidates: Record<level, {code,name,p}[]>,
  top3_villages: {code,name,p}[],
  outside: boolean,
  tau: number,
  sigma: number
}
```

### Tests (planned)

- Pure unit: weight normalisation, TAU selection, outside flag.
- 10,000 random interior points at accuracy 20 m: chosen village == PIP truth ≥ 99%.
- Codec parity with Python IRG2 remains 0/100k.

**Next:** implement `packages/offline-locate` + validation harness (item I) on `wip/offline`.

---

## 2026-11-01 — GROK — dissolve hierarchy started

See branch `wip/g-dissolve`, script `scripts/dissolve_hierarchy.py`, snap **1.0 m** UTM 32736.

---

## Prior entries

See main branch history for IRG2, PMTiles, export, HANDOFF rules.
