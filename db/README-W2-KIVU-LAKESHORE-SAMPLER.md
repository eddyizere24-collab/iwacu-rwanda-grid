# W2 Kivu lakeshore proxy truth sampler

The Production project has no lake/hydrography polygon dataset, so this helper implements the approved fallback geometry exactly: the union of active village polygons intersecting the Kivu bbox (28.85–29.35 longitude, -2.85–-1.65 latitude), clipped to that bbox, and sampled inside the village union within 100m of its non-shared union boundary.

- Function: `public.w2_sample_kivu_lakeshore_truth(integer)`
- Allowed seeds: 424242 and 20261030.
- Each call requests 400 deterministic points; every returned point is resolved against a village using exact `extensions.ST_Contains`.
- The function fails unless at least 200 truth-labelled points are returned.
- It reports the number of Kivu-bbox villages and distinct contributing villages.
- Read-only SECURITY DEFINER, empty search_path, EXECUTE only for anon. It does not grant table privileges or write access.
- Rollback drops only this function.
- This is a geographic outer-edge lakeshore proxy, not an authoritative hydrographic shoreline classification.
