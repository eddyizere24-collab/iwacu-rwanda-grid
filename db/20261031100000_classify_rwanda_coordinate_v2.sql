-- Additive replacement for the anonymous-country classifier.
-- This national geometry is privately seeded from the active Country boundary.
-- Replacing the national polygon later only requires updating the single row.
CREATE TABLE public.rwanda_national_geom (
  is_current boolean PRIMARY KEY DEFAULT true CHECK (is_current IS TRUE),
  geom extensions.geometry(MultiPolygon, 4326) NOT NULL,
  source text NOT NULL,
  sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  loaded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX rwanda_national_geom_geom_gist
  ON public.rwanda_national_geom
  USING gist (geom);

ALTER TABLE public.rwanda_national_geom ENABLE ROW LEVEL SECURITY;

-- No Data API access to the national geometry; only the definer-owned RPC reads it.
REVOKE ALL ON TABLE public.rwanda_national_geom
  FROM PUBLIC, anon, authenticated, service_role;

DO $seed_check$
DECLARE
  v_country_count integer;
BEGIN
  SELECT count(*) INTO v_country_count
  FROM public.boundaries
  WHERE scope_code = 'RW'
    AND level::text = 'country'
    AND valid_to IS NULL;

  IF v_country_count <> 1 THEN
    RAISE EXCEPTION
      'Expected exactly one active Rwanda Country polygon (scope_code RW); found %',
      v_country_count;
  END IF;
END;
$seed_check$;

-- Copy the Country geometry entirely inside PostgreSQL; no geometry is exported.
INSERT INTO public.rwanda_national_geom (
  is_current, geom, source, sha256, loaded_at
)
SELECT
  true,
  b.geom,
  'public.boundaries:scope_code=RW,level=country,valid_to IS NULL',
  pg_catalog.encode(
    extensions.digest(extensions.ST_AsEWKB(b.geom), 'sha256'),
    'hex'
  ),
  clock_timestamp()
FROM public.boundaries AS b
WHERE b.scope_code = 'RW'
  AND b.level::text = 'country'
  AND b.valid_to IS NULL;

CREATE FUNCTION public.classify_rwanda_coordinate_v2(
  p_lng double precision,
  p_lat double precision,
  p_buffer_m double precision DEFAULT 100
)
RETURNS TABLE (
  is_inside_rwanda boolean,
  distance_to_border_m double precision,
  nearest_border_district text,
  nearest_border_district_code text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $function$
  WITH input_point AS (
    SELECT extensions.ST_SetSRID(
      extensions.ST_MakePoint(p_lng, p_lat),
      4326
    ) AS geom
  ),
  country AS (
    SELECT g.geom
    FROM public.rwanda_national_geom AS g
    WHERE g.is_current IS TRUE
  ),
  border_distance AS (
    SELECT
      extensions.ST_Covers(c.geom, p.geom) AS covered,
      extensions.ST_Distance(
        p.geom::extensions.geography,
        c.geom::extensions.geography
      ) AS distance_m
    FROM country AS c
    CROSS JOIN input_point AS p
  )
  SELECT
    (
      bd.covered
      OR bd.distance_m <= LEAST(
        GREATEST(COALESCE(p_buffer_m, 100), 0),
        250
      )
    ) AS is_inside_rwanda,
    CASE
      WHEN bd.covered THEN 0::double precision
      ELSE bd.distance_m
    END AS distance_to_border_m,
    NULL::text AS nearest_border_district,
    NULL::text AS nearest_border_district_code
  FROM border_distance AS bd;
$function$;

-- Keep this SECURITY DEFINER RPC callable only by the two intended API roles.
REVOKE ALL ON FUNCTION public.classify_rwanda_coordinate_v2(
  double precision, double precision, double precision
) FROM PUBLIC, anon, authenticated, service_role;

GRANT EXECUTE ON FUNCTION public.classify_rwanda_coordinate_v2(
  double precision, double precision, double precision
) TO anon, authenticated;

COMMENT ON TABLE public.rwanda_national_geom IS
  'Private singleton holding the authoritative Rwanda Country polygon used by classify_rwanda_coordinate_v2. Replace the current row when a new national polygon is approved.';

COMMENT ON FUNCTION public.classify_rwanda_coordinate_v2(
  double precision, double precision, double precision
) IS
  'Classifies Rwanda country coverage from the private singleton national polygon. Border tolerance equals p_buffer_m capped at 250 m; no additional 250 m allowance. District columns remain NULL because this function reads only the country geometry table.';
