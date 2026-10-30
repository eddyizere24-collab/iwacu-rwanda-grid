# iwacu-rwanda-grid

National adaptive geohash index for **IWACU RWANDA 2**.

Public data only. No secrets. Separate from the main app so Vercel is never triggered.

## Integration (G8)

1. Copy `runtime/locate.ts` into the app (or publish as tiny package).
2. Host per-district chunks `d{district_id}.json` (or `.json.gz`) on CDN / static path.
3. Load `coarse_gh6.json` once; call `locate(lat, lng, accuracyMeters, { loadDistrict, coarseGh6 })`.
4. `dataset_version` field enables rollback: pin the chunk folder by version.
5. Kivu / gaps return `flags: ["nearest_village", "near_water_or_gap"]` — still inside Rwanda.

### API

```ts
locate(lat, lng, accuracyMeters, opts) -> {
  finestLevel, topVillages[{village_id, share, name}],
  villagePct, cellPct, sectorPct, districtPct, provincePct,
  flags, datasetVersion, ms
}
```

### Versioning
- Current: `2026.10.30.3`
- Fingerprints of NISR IDs in `data/fingerprints.json`

### Rebuild
```bash
python scripts/download_nisr_geometry.py
python scripts/build_grid.py --geojson data/rwanda_villages_full.geojson --out artifacts/grid
```

## Status
See [STATUS.md](STATUS.md).

## License
NISR Village Boundary 2022 (public official data).
