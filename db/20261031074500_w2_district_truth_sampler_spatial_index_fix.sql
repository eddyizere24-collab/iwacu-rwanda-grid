-- W2 sampler optimization: preserve exact truth semantics while restoring GiST use.
-- Evidence before this change: the MATERIALIZED CTE self-join produced two CTE Scan
-- nodes (no spatial index); the equivalent base-table join used idx_boundaries_geom_gist
-- and completed for Nyamasheke in 936.899 ms (1618 touching pairs).
CREATE OR REPLACE FUNCTION public.w2_sample_district_village_truth(
  p_district_scope_code text,
  p_seed integer
)
RETURNS TABLE(
  sample_kind text,
  sample_index integer,
  seed integer,
  longitude double precision,
  latitude double precision,
  true_village_scope_code text,
  true_village_path text,
  distance_to_shared_boundary_m double precision
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
AS $function$
DECLARE
  v_returned_rows integer;
  v_district_exists boolean;
BEGIN
  IF COALESCE(current_setting('request.jwt.claims', true)::jsonb ->> 'role', '') <> 'anon' THEN
    RAISE EXCEPTION 'w2 sampler is available only to the anon test role';
  END IF;

  IF p_seed NOT IN (424242, 20261030) THEN
    RAISE EXCEPTION 'unsupported W2 seed';
  END IF;

  IF p_district_scope_code !~ '^RW-P[1-5]-D[0-9]{2}$' THEN
    RAISE EXCEPTION 'invalid district scope code';
  END IF;

  SELECT EXISTS (
    SELECT 1
    FROM public.boundaries d
    WHERE d.level::text = 'district'
      AND d.valid_to IS NULL
      AND d.scope_code = p_district_scope_code
  ) INTO v_district_exists;

  IF NOT v_district_exists THEN
    RAISE EXCEPTION 'district not found in active public.boundaries';
  END IF;

  RETURN QUERY
  WITH RECURSIVE
  district AS MATERIALIZED (
    SELECT d.scope_code
    FROM public.boundaries d
    WHERE d.level::text = 'district'
      AND d.valid_to IS NULL
      AND d.scope_code = p_district_scope_code
  ),
  villages AS MATERIALIZED (
    SELECT v.id, v.scope_code, v.path, v.geom
    FROM public.boundaries v
    CROSS JOIN district d
    WHERE v.level::text = 'village'
      AND v.valid_to IS NULL
      AND v.scope_code LIKE d.scope_code || '-%'
      AND v.geom IS NOT NULL
      AND NOT extensions.ST_IsEmpty(v.geom)
  ),
  interior_points AS MATERIALIZED (
    SELECT
      i.sample_index,
      generated.point_geom
    FROM pg_catalog.generate_series(1, 400) AS i(sample_index)
    CROSS JOIN LATERAL (
      SELECT v.geom
      FROM villages v
      ORDER BY pg_catalog.md5(
        p_seed::text || ':interior:' || i.sample_index::text || ':' || v.scope_code
      )
      LIMIT 1
    ) AS selected_village
    CROSS JOIN LATERAL (
      SELECT extensions.ST_GeometryN(
        extensions.ST_GeneratePoints(
          selected_village.geom,
          1,
          p_seed + i.sample_index
        ),
        1
      ) AS point_geom
    ) AS generated
  ),
  interior_truth AS (
    SELECT
      'interior'::text AS sample_kind,
      p.sample_index,
      p_seed AS seed,
      extensions.ST_X(p.point_geom) AS longitude,
      extensions.ST_Y(p.point_geom) AS latitude,
      truth.scope_code AS true_village_scope_code,
      truth.path::text AS true_village_path,
      NULL::double precision AS distance_to_shared_boundary_m
    FROM interior_points p
    JOIN LATERAL (
      SELECT v.scope_code, v.path
      FROM villages v
      WHERE extensions.ST_Contains(v.geom, p.point_geom)
      ORDER BY v.scope_code
      LIMIT 1
    ) AS truth ON true
  ),
  shared_edges AS MATERIALIZED (
    /*
     * Do not self-join the MATERIALIZED villages CTE here. A CTE Scan has
     * no GiST index, so its bbox predicate becomes an O(n^2) nested-loop
     * filter. Joining the base boundaries table exposes
     * idx_boundaries_geom_gist to the planner while retaining the exact
     * active-village/district predicates and ST_Touches truth.
     */
    SELECT
      a.scope_code AS village_a_scope_code,
      b.scope_code AS village_b_scope_code,
      a.geom AS village_a_geom,
      extensions.ST_CollectionExtract(
        extensions.ST_Intersection(
          extensions.ST_Boundary(a.geom),
          extensions.ST_Boundary(b.geom)
        ),
        2
      ) AS shared_line
    FROM public.boundaries a
    JOIN public.boundaries b
      ON a.id::text < b.id::text
     AND a.geom OPERATOR(extensions.&&) b.geom
    WHERE a.level::text = 'village'
      AND a.valid_to IS NULL
      AND a.scope_code LIKE p_district_scope_code || '-%'
      AND a.geom IS NOT NULL
      AND NOT extensions.ST_IsEmpty(a.geom)
      AND b.level::text = 'village'
      AND b.valid_to IS NULL
      AND b.scope_code LIKE p_district_scope_code || '-%'
      AND b.geom IS NOT NULL
      AND NOT extensions.ST_IsEmpty(b.geom)
      AND extensions.ST_Touches(a.geom, b.geom)
  ),
  usable_edges AS MATERIALIZED (
    SELECT
      e.village_a_scope_code,
      e.village_b_scope_code,
      e.village_a_geom,
      e.shared_line
    FROM shared_edges e
    WHERE NOT extensions.ST_IsEmpty(e.shared_line)
      AND extensions.ST_Length(e.shared_line::extensions.geography) >= 1
  ),
  border_points AS MATERIALIZED (
    SELECT
      i.sample_index,
      picked.shared_line,
      generated.point_geom
    FROM pg_catalog.generate_series(1, 100) AS i(sample_index)
    CROSS JOIN LATERAL (
      SELECT
        e.village_a_geom,
        e.shared_line
      FROM usable_edges e
      ORDER BY pg_catalog.md5(
        p_seed::text || ':border:' || i.sample_index::text || ':' ||
        e.village_a_scope_code || ':' || e.village_b_scope_code
      )
      LIMIT 1
    ) AS picked
    CROSS JOIN LATERAL (
      SELECT extensions.ST_GeometryN(
        extensions.ST_GeneratePoints(
          extensions.ST_Intersection(
            picked.village_a_geom,
            extensions.ST_Buffer(picked.shared_line::extensions.geography, 49)::extensions.geometry
          ),
          1,
          p_seed + 50000 + i.sample_index
        ),
        1
      ) AS point_geom
    ) AS generated
  ),
  border_truth AS (
    SELECT
      'shared_boundary_50m'::text AS sample_kind,
      p.sample_index,
      p_seed AS seed,
      extensions.ST_X(p.point_geom) AS longitude,
      extensions.ST_Y(p.point_geom) AS latitude,
      truth.scope_code AS true_village_scope_code,
      truth.path::text AS true_village_path,
      extensions.ST_Distance(
        p.point_geom::extensions.geography,
        p.shared_line::extensions.geography
      ) AS distance_to_shared_boundary_m
    FROM border_points p
    JOIN LATERAL (
      SELECT v.scope_code, v.path
      FROM villages v
      WHERE extensions.ST_Contains(v.geom, p.point_geom)
      ORDER BY v.scope_code
      LIMIT 1
    ) AS truth ON true
  )
  SELECT * FROM interior_truth
  UNION ALL
  SELECT * FROM border_truth
  ORDER BY sample_kind, sample_index;

  GET DIAGNOSTICS v_returned_rows = ROW_COUNT;
  IF v_returned_rows <> 500 THEN
    RAISE EXCEPTION 'W2 district sampler expected 500 verified points, returned %', v_returned_rows;
  END IF;
END;
$function$;
