-- PRE-CHANGE BACKUP: public.calculate_location_confidence
-- Captured read-only from Supabase project buexgewxypvkqmphvfec on 2026-10-30.
-- Do not apply as a normal migration. Restore only if rolling back this RPC.
-- Owner before change: postgres
-- Original ACL snapshot: postgres=X/postgres,service_role=X/postgres
CREATE OR REPLACE FUNCTION public.calculate_location_confidence(p_lng double precision, p_lat double precision, p_accuracy_m double precision)
 RETURNS TABLE(scope_code text, name_kiny text, name_eng text, level boundary_level, confidence numeric, intersection_area_m2 double precision, path ltree)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public', 'extensions'
AS $function$
  WITH circle AS (
    SELECT ST_Buffer(
      ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326)::geography,
      p_accuracy_m
    )::geometry AS geom,
    ST_Area(
      ST_Buffer(
        ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326)::geography,
        p_accuracy_m
      )
    ) AS area_m2
  ),
  intersections AS (
    SELECT
      b.scope_code,
      b.name_kiny,
      b.name_eng,
      b.level,
      b.path,
      ST_Area(
        ST_Intersection(b.geom::geography, c.geom::geography)
      ) AS inter_area_m2,
      c.area_m2 AS circle_area_m2
    FROM boundaries b
    CROSS JOIN circle c
    WHERE b.valid_to IS NULL
      AND b.level = 'village'
      AND ST_Intersects(b.geom, c.geom)
  )
  SELECT
    i.scope_code,
    i.name_kiny,
    i.name_eng,
    i.level,
    ROUND(
      (LEAST(i.inter_area_m2 / NULLIF(i.circle_area_m2, 0), 1.0) * 100)::numeric,
      2
    ) AS confidence,
    i.inter_area_m2 AS intersection_area_m2,
    i.path
  FROM intersections i
  WHERE i.inter_area_m2 > 0
  ORDER BY confidence DESC;
$function$;

-- Prior effective execute permissions before the change:
REVOKE ALL ON FUNCTION public.calculate_location_confidence(double precision, double precision, double precision) FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.calculate_location_confidence(double precision, double precision, double precision) TO service_role;
