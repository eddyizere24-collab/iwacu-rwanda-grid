-- WORK ORDER 15: additive sampler-based village confidence RPC.
-- Target Supabase project: buexgewxypvkqmphvfec (iwacu-rwanda-2).
-- This function deliberately does not call ST_Buffer or ST_Intersection.
-- no_village_mass is the fraction [0,1] of total sample weight whose sample
-- point was not contained by a current village and therefore used KNN fallback.
-- sample_count is the number of sampled points assigned to this returned village.
-- intersection_area_m2 is retained for the v1 response shape. It is an
-- area-equivalent support estimate, not a polygon intersection measurement.

CREATE OR REPLACE FUNCTION public.calculate_location_confidence_v2(
  p_lng double precision,
  p_lat double precision,
  p_accuracy_m double precision
)
RETURNS TABLE (
  scope_code text,
  name_kiny text,
  name_eng text,
  level public.boundary_level,
  confidence numeric,
  intersection_area_m2 double precision,
  path extensions.ltree,
  sample_count integer,
  no_village_mass double precision
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $function$
  WITH input AS (
    SELECT
      extensions.ST_SetSRID(extensions.ST_MakePoint(p_lng, p_lat), 4326) AS center_geom,
      LEAST(GREATEST(COALESCE(p_accuracy_m, 100.0), 1.0), 50000.0) / 1.51 AS sigma_m,
      p_lat AS latitude
  ),
  sample_points AS (
    SELECT 1::integer AS sample_no, i.center_geom AS sample_geom,
      1.0::double precision AS sample_weight
    FROM input AS i
    WHERE i.sigma_m <= 10.0
    UNION ALL
    SELECT
      (g.k + 1)::integer AS sample_no,
      extensions.ST_SetSRID(
        extensions.ST_MakePoint(
          extensions.ST_X(i.center_geom)
            + (
                (LEAST(3.0 * i.sigma_m, 60000.0)
                  * pg_catalog.sqrt((g.k + 0.5) / g.sample_n)
                  * pg_catalog.cos(g.k * 2.399963229728653))
                / (111320.0 * GREATEST(
                    pg_catalog.abs(pg_catalog.cos(pg_catalog.radians(i.latitude))),
                    0.000001
                  ))
              ),
          extensions.ST_Y(i.center_geom)
            + (
                (LEAST(3.0 * i.sigma_m, 60000.0)
                  * pg_catalog.sqrt((g.k + 0.5) / g.sample_n)
                  * pg_catalog.sin(g.k * 2.399963229728653))
                / 110574.0
              )
        ),
        4326
      ) AS sample_geom,
      pg_catalog.exp(
        -(
          pg_catalog.power(
            LEAST(3.0 * i.sigma_m, 60000.0)
              * pg_catalog.sqrt((g.k + 0.5) / g.sample_n),
            2
          )
        ) / (2.0 * pg_catalog.power(i.sigma_m, 2))
      ) AS sample_weight
    FROM input AS i
    CROSS JOIN LATERAL (
      SELECT
        series.k,
        CASE WHEN i.sigma_m < 500.0 THEN 128.0 ELSE 256.0 END AS sample_n
      FROM pg_catalog.generate_series(
        0,
        CASE WHEN i.sigma_m < 500.0 THEN 127 ELSE 255 END
      ) AS series(k)
    ) AS g
    WHERE i.sigma_m > 10.0
  ),
  resolved AS (
    SELECT
      s.sample_no,
      s.sample_weight,
      hit.scope_code AS hit_scope_code,
      COALESCE(hit.scope_code, nearest.scope_code) AS assigned_scope_code,
      COALESCE(hit.name_kiny, nearest.name_kiny) AS assigned_name_kiny,
      COALESCE(hit.name_eng, nearest.name_eng) AS assigned_name_eng,
      COALESCE(hit.level, nearest.level) AS assigned_level,
      COALESCE(hit.path, nearest.path) AS assigned_path
    FROM sample_points AS s
    LEFT JOIN LATERAL (
      SELECT
        b.scope_code,
        b.name_kiny,
        b.name_eng,
        b.level,
        b.path
      FROM public.boundaries AS b
      WHERE b.valid_to IS NULL
        AND b.level = 'village'::public.boundary_level
        AND b.geom IS NOT NULL
        AND b.geom OPERATOR(extensions.&&) s.sample_geom
        AND extensions.ST_Contains(b.geom, s.sample_geom)
      LIMIT 1
    ) AS hit ON TRUE
    LEFT JOIN LATERAL (
      SELECT
        b.scope_code,
        b.name_kiny,
        b.name_eng,
        b.level,
        b.path
      FROM public.boundaries AS b
      WHERE hit.scope_code IS NULL
        AND b.valid_to IS NULL
        AND b.level = 'village'::public.boundary_level
        AND b.geom IS NOT NULL
      ORDER BY b.geom OPERATOR(extensions.<->) s.sample_geom
      LIMIT 1
    ) AS nearest ON hit.scope_code IS NULL
  ),
  totals AS (
    SELECT
      pg_catalog.sum(sample_weight) AS total_weight,
      COALESCE(
        pg_catalog.sum(sample_weight) FILTER (WHERE hit_scope_code IS NULL)
          / NULLIF(pg_catalog.sum(sample_weight), 0.0),
        0.0
      ) AS no_village_mass
    FROM resolved
  ),
  scored AS (
    SELECT
      assigned_scope_code,
      assigned_name_kiny,
      assigned_name_eng,
      assigned_level,
      assigned_path,
      pg_catalog.sum(sample_weight) AS score_weight,
      pg_catalog.count(*)::integer AS sample_count,
      pg_catalog.count(*) FILTER (
        WHERE hit_scope_code = assigned_scope_code
      )::integer AS contained_sample_count
    FROM resolved
    WHERE assigned_scope_code IS NOT NULL
    GROUP BY
      assigned_scope_code,
      assigned_name_kiny,
      assigned_name_eng,
      assigned_level,
      assigned_path
  ),
  geometry_scale AS (
    SELECT
      CASE
        WHEN i.sigma_m <= 10.0 THEN 0.0
        ELSE LEAST(3.0 * i.sigma_m, 60000.0)
      END AS radius_m
    FROM input AS i
  )
  SELECT
    s.assigned_scope_code AS scope_code,
    s.assigned_name_kiny AS name_kiny,
    s.assigned_name_eng AS name_eng,
    s.assigned_level AS level,
    pg_catalog.round(
      (100.0 * s.score_weight / NULLIF(t.total_weight, 0.0))::numeric,
      2
    ) AS confidence,
    CASE
      WHEN s.contained_sample_count = 0 THEN 0.0
      WHEN g.radius_m = 0.0 THEN 1.0
      ELSE
        (s.score_weight / NULLIF(t.total_weight, 0.0))
          * pg_catalog.pi() * pg_catalog.power(g.radius_m, 2)
    END::double precision AS intersection_area_m2,
    s.assigned_path AS path,
    s.sample_count,
    t.no_village_mass
  FROM scored AS s
  CROSS JOIN totals AS t
  CROSS JOIN geometry_scale AS g
  ORDER BY confidence DESC, s.assigned_scope_code;
$function$;

REVOKE ALL ON FUNCTION public.calculate_location_confidence_v2(double precision, double precision, double precision) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.calculate_location_confidence_v2(double precision, double precision, double precision) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.calculate_location_confidence_v2(double precision, double precision, double precision) TO anon, authenticated;

COMMENT ON FUNCTION public.calculate_location_confidence_v2(double precision, double precision, double precision)
IS 'WO15 deterministic weighted sunflower sampler over current Rwanda village geometries; no ST_Buffer or ST_Intersection; no_village_mass is a [0,1] fraction.';
