# iwacu-rwanda-grid

National adaptive grid index for **IWACU RWANDA 2**.

Public data only. No secrets. Separate from the main app repo so Vercel is never triggered.

## Status
See [STATUS.md](STATUS.md).

## G1 (done)
- NISR source: Village_Boundary_2022 FeatureServer/3
- Counts: 5 / 30 / 416 / 2148 / 14823
- Geometry: 14823 villages, **0 null/invalid**
- ID fingerprints: see `data/fingerprints.json`

## Rebuild geometry
```bash
python scripts/download_nisr_geometry.py
python scripts/compute_fingerprints.py data/rwanda_villages_full.geojson
```

## G2 (in progress)
Adaptive geohash (primary) + H3 challenger.
- Coarse: geohash 6 national
- Village cells: geohash 7, adaptive geohash 8 on borders / tiny villages
- Border cells: top 2-3 villages with area shares
- Gaps (Kivu): nearest village + gap/near-water flag

## License / data
NISR administrative boundaries 2022. Public official data.
