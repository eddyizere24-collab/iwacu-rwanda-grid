-- WORK ORDER 06 / W2
-- Read-only deterministic Kivu bounding-box lakeshore-proxy sampler.
-- No hydrography layer exists in Production. Points are therefore defined
-- exactly as requested: inside the union of active village polygons, in the
-- Kivu bbox, within 100m of the boundary of that village union.
-- Exact truth is re-established using ST_Contains on the village polygon.

CREATE OR REPLACE FUNCTION public.w2_sample_kivu_lakeshore_truth(
  p_seed integer
)
RETURNS TABLE (
  sample_kind text,
  sample_index integer,
  seed integer,
  longitude double precision,
  latitude double precision,
  true_village_scope_code text,
  true_village_path text,
  distance_to_union_edge_m double precision,
  kivu_bbox_village_count integer,
  contributing_village_count integer
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
  v_returned_rows integer;
BEGIN
  IF COALESCE(current_setting('request.jwt.claims', true)::jsonb ->> 'role', '') <> 'anon' THEN
    RAISE EXCEPTION 'w2 Kivu sampler is available only to the anon test role';
  END IF;

  IF p_seed IS NULL OR p_seed NOT IN (424242, 20261030) THEN
    RAISE EXCEPTION 'unsupported W2 seed';
  END IF;

  RETURN QUERY
  WITH
  bbox AS MATERIALIZED (
    SELECT extensions.ST_MakeEnvelope(28.85, -2.85, 29.35, -1.65, 4326) AS geom
  ),
  selected AS MATERIALIZED (
    SELECT v.id, v.scope_code, v.path, v.geom
    FROM public.boundaries v
    CROSS JOIN bbox b
    WHERE v.level::text = 'village'
      AND v.valid_to IS NULL
      AND v.geom IS NOT NULL
      AND v.geom OPERATOR(extensions.&&) b.geom
      AND extensions.ST_Intersects(v.geom, b.geom)
  ),
  unioned AS MATERIALIZED (
    SELECT extensions.ST_UnaryUnion(extensions.ST_Collect(geom)) AS geom
    FROM selected
  ),
  outer_edge AS MATERIALIZED (
    SELECT extensions.ST_Boundary(u.geom) AS geom
    FROM unioned u
  ),
  inner_strip AS MATERIALIZED (
    SELECT extensions.ST_Intersection(
      extensions.ST_Intersection(
        u.geom,
        extensions.ST_Buffer(e.geom::extensions.geography, 100)::extensions.geometry
      ),
      b.geom
    ) AS geom
    FROM unioned u
    CROSS JOIN outer_edge e
    CROSS JOIN bbox b
  ),
  generated AS MATERIALIZED (
    SELECT
      (extensions.ST_Dump(
        extensions.ST_GeneratePoints(s.geom, 400, p_seed)
      )).geom AS geom
    FROM inner_strip s
  ),
  truth AS MATERIALIZED (
    SELECT
      g.geom,
      v.scope_code,
      v.path
    FROM generated g
    JOIN LATERAL (
      SELECT v.scope_code, v.path
      FROM selected v
      WHERE extensions.ST_Contains(v.geom, g.geom)
      ORDER BY v.scope_code
      LIMIT 1
    ) v ON true
  ),
  stats AS MATERIALIZED (
    SELECT count(DISTINCT scope_code)::integer AS contributing_count
    FROM truth
  ),
  totals AS MATERIALIZED (
    SELECT count(*)::integer AS bbox_village_count
    FROM selected
  )
  SELECT
    'kivu_union_outer_edge_100m'::text AS sample_kind,
    row_number() OVER (ORDER BY extensions.ST_Y(t.geom), extensions.ST_X(t.geom))::integer AS sample_index,
    p_seed AS seed,
    extensions.ST_X(t.geom) AS longitude,
    extensions.ST_Y(t.geom) AS latitude,
    t.scope_code AS true_village_scope_code,
    t.path::text AS true_village_path,
    extensions.ST_Distance(
      t.geom::extensions.geography,
      e.geom::extensions.geography
    ) AS distance_to_union_edge_m,
    totals.bbox_village_count AS kivu_bbox_village_count,
    stats.contributing_count AS contributing_village_count
  FROM truth t
  CROSS JOIN outer_edge e
  CROSS JOIN stats
  CROSS JOIN totals
  ORDER BY sample_index;

  GET DIAGNOSTICS v_returned_rows = ROW_COUNT;
  IF v_returned_rows < 200 THEN
    RAISE EXCEPTION 'W2 Kivu sampler expected at least 200 verified points, returned %', v_returned_rows;
  END IF;
END;
$function$;

REVOKE ALL ON FUNCTION public.w2_sample_kivu_lakeshore_truth(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.w2_sample_kivu_lakeshore_truth(integer) FROM anon;
GRANT EXECUTE ON FUNCTION public.w2_sample_kivu_lakeshore_truth(integer) TO anon;
