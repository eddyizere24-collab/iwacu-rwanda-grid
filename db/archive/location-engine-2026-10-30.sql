-- IWACU RWANDA 2: backward-compatible location confidence RPC.
-- Keeps the original function signature and return-column names/types.
-- Returns only villages whose polygons intersect the GPS uncertainty circle.
-- Gap/nearest fallback is handled by the application using the official NISR
-- layer, so code on main does not mistake a nearest estimate for a GPS hit.

CREATE OR REPLACE FUNCTION public.calculate_location_confidence(
  p_lng double precision,
  p_lat double precision,
  p_accuracy_m double precision
)
RETURNS TABLE(
  scope_code text,
  name_kiny text,
  name_eng text,
  level public.boundary_level,
  confidence numeric,
  intersection_area_m2 double precision,
  path extensions.ltree
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path TO 'pg_catalog', 'public', 'extensions'
AS $function$
  WITH settings AS (
    SELECT LEAST(GREATEST(COALESCE(p_accuracy_m, 100), 1), 50000) AS accuracy_m
  ),
  point AS (
    SELECT ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326) AS geom
  ),
  circle AS (
    SELECT
      ST_Buffer(point.geom::geography, settings.accuracy_m)::geometry AS geom,
      ST_Area(ST_Buffer(point.geom::geography, settings.accuracy_m)) AS area_m2
    FROM point
    CROSS JOIN settings
  ),
  intersections AS (
    SELECT
      b.scope_code,
      b.name_kiny,
      b.name_eng,
      b.level,
      b.path,
      ST_Area(ST_Intersection(b.geom::geography, c.geom::geography)) AS inter_area_m2,
      c.area_m2 AS circle_area_m2
    FROM public.boundaries AS b
    CROSS JOIN circle AS c
    WHERE b.valid_to IS NULL
      AND b.level = 'village'
      AND b.geom IS NOT NULL
      AND ST_Intersects(b.geom, c.geom)
  )
  SELECT
    i.scope_code,
    i.name_kiny,
    i.name_eng,
    i.level,
    ROUND(
      (
        LEAST(i.inter_area_m2 / NULLIF(i.circle_area_m2, 0), 1.0) * 100
      )::numeric,
      2
    ) AS confidence,
    i.inter_area_m2 AS intersection_area_m2,
    i.path
  FROM intersections AS i
  WHERE i.inter_area_m2 > 0
  ORDER BY confidence DESC;
$function$;

-- These are all public boundary metadata/geometry used by the invoker RPC.
-- Row access remains limited by the existing boundaries_public_read RLS policy.
GRANT SELECT (scope_code, name_kiny, name_eng, level, valid_to, geom, path)
  ON TABLE public.boundaries TO anon, authenticated;

REVOKE ALL ON FUNCTION public.calculate_location_confidence(double precision, double precision, double precision)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.calculate_location_confidence(double precision, double precision, double precision)
  TO anon, authenticated, service_role;

COMMENT ON FUNCTION public.calculate_location_confidence(double precision, double precision, double precision)
  IS 'Backward-compatible GPS overlap query. Returns only real active village polygons intersecting the accuracy circle; fallback candidate estimation is performed by the app and labelled as an estimate.';
