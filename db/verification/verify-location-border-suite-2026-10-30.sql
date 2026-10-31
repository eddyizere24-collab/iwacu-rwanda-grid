-- Read-only hard-case verification against the current backward-compatible RPC.
-- Run in the populated project buexgewxypvkqmphvfec.
-- No INSERT/UPDATE/DELETE. Border samples are diagnostics, not surveyed ground truth.

-- A. Near-border test: choose up to five villages per district, take a point
-- on one boundary segment, project 10 m toward the polygon interior, and test
-- uncertainty radii of 20 m, 100 m and 300 m. Some geometry rows may be skipped
-- if no suitable segment/inside point is available.
WITH village_hierarchy AS (
  SELECT v.scope_code AS true_village, d.scope_code AS district_scope, v.geom
  FROM public.boundaries v
  JOIN public.boundaries c ON c.id=v.parent_id AND c.level='cell'
  JOIN public.boundaries s ON s.id=c.parent_id AND s.level='sector'
  JOIN public.boundaries d ON d.id=s.parent_id AND d.level='district'
  WHERE v.level='village' AND v.valid_to IS NULL AND c.valid_to IS NULL
    AND s.valid_to IS NULL AND d.valid_to IS NULL AND v.geom IS NOT NULL
),
sampled AS (
  SELECT *, row_number() OVER(PARTITION BY district_scope ORDER BY md5(true_village)) AS sample_n
  FROM village_hierarchy
),
edge_choice AS (
  SELECT s.*, edge.geom AS edge_line, ST_PointOnSurface(s.geom)::geography AS interior
  FROM sampled s
  CROSS JOIN LATERAL (
    SELECT (dmp).geom AS geom
    FROM ST_Dump(ST_Boundary(s.geom)) AS dmp
    WHERE ST_GeometryType((dmp).geom)='ST_LineString'
      AND ST_Length(((dmp).geom)::geography)>100
    ORDER BY md5(s.true_village || (dmp).path::text)
    LIMIT 1
  ) edge
  WHERE s.sample_n<=5
),
border_points AS (
  SELECT true_village,district_scope,
    ST_Project(
      ST_LineInterpolatePoint(edge_line,0.5)::geography,
      10,
      ST_Azimuth(ST_LineInterpolatePoint(edge_line,0.5)::geography,interior)
    )::geometry AS point_geom
  FROM edge_choice
),
test_points AS (
  SELECT b.*, d.accuracy_m
  FROM border_points b
  CROSS JOIN LATERAL unnest(ARRAY[20,100,300]::double precision[]) AS d(accuracy_m)
  WHERE ST_Covers(
    (SELECT v.geom FROM public.boundaries v
     WHERE v.scope_code=b.true_village AND v.valid_to IS NULL LIMIT 1),
    b.point_geom
  )
),
predictions AS (
  SELECT t.*, p.top1_scope_code, p.candidate_scope_codes
  FROM test_points t
  LEFT JOIN LATERAL (
    SELECT (array_agg(r.scope_code ORDER BY r.confidence DESC))[1] AS top1_scope_code,
           array_agg(r.scope_code ORDER BY r.confidence DESC) AS candidate_scope_codes
    FROM (
      SELECT x.scope_code,x.confidence
      FROM public.calculate_location_confidence(ST_X(t.point_geom),ST_Y(t.point_geom),t.accuracy_m) x
      ORDER BY x.confidence DESC LIMIT 3
    ) r
  ) p ON TRUE
)
SELECT accuracy_m,COUNT(*) AS samples,
  ROUND(100.0*COUNT(*) FILTER(WHERE top1_scope_code=true_village)/NULLIF(COUNT(*),0),2) AS top1_correct_pct,
  ROUND(100.0*COUNT(*) FILTER(WHERE true_village=ANY(candidate_scope_codes))/NULLIF(COUNT(*),0),2) AS true_village_in_top3_pct,
  ROUND(100.0*COUNT(*) FILTER(WHERE candidate_scope_codes IS NULL)/NULLIF(COUNT(*),0),2) AS no_candidate_pct
FROM predictions
GROUP BY accuracy_m ORDER BY accuracy_m;

-- B. Lake Kivu / shore / outside-country diagnostics. The points are approximate
-- probes, not surveyed shoreline markers. This SQL tests only the RPC; application
-- NISR nearest fallback still must be tested through /api/locate.
WITH points(name,geom) AS (
 VALUES
 ('Gisenyi shore A',ST_SetSRID(ST_MakePoint(29.25,-1.68),4326)),
 ('Gisenyi shore B',ST_SetSRID(ST_MakePoint(29.28,-1.70),4326)),
 ('Rubavu shore C',ST_SetSRID(ST_MakePoint(29.30,-1.72),4326)),
 ('Kivu lake sample',ST_SetSRID(ST_MakePoint(29.20,-1.75),4326)),
 ('Kivu south shore sample',ST_SetSRID(ST_MakePoint(29.35,-2.10),4326)),
 ('Kigali control',ST_SetSRID(ST_MakePoint(30.0619,-1.9441),4326)),
 ('Outside west check',ST_SetSRID(ST_MakePoint(28.70,-1.90),4326)),
 ('Outside north check',ST_SetSRID(ST_MakePoint(29.90,-0.90),4326))
),
country AS (
 SELECT geom FROM public.boundaries WHERE level='country' AND valid_to IS NULL LIMIT 1
),
probe AS (
 SELECT p.name,ST_Covers(c.geom,p.geom) AS inside_country,
  EXISTS(SELECT 1 FROM public.boundaries v
    WHERE v.level='village' AND v.valid_to IS NULL AND v.geom IS NOT NULL
      AND ST_Covers(v.geom,p.geom)) AS inside_village,
  r.scope_code,r.name_kiny,r.confidence,r.intersection_area_m2
 FROM points p CROSS JOIN country c
 LEFT JOIN LATERAL public.calculate_location_confidence(ST_X(p.geom),ST_Y(p.geom),100) r ON TRUE
)
SELECT name,inside_country,inside_village,COUNT(scope_code) AS candidate_rows,
 (array_agg(name_kiny ORDER BY confidence DESC) FILTER(WHERE scope_code IS NOT NULL))[1] AS top1,
 BOOL_OR(intersection_area_m2=0) AS any_nearest_estimates
FROM probe
GROUP BY name,inside_country,inside_village
ORDER BY name;
