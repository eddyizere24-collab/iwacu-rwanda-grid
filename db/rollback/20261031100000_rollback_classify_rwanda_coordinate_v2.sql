-- Roll back only the additive v2 national classifier.
-- The existing classify_rwanda_coordinate v1 and boundaries grants are untouched.
REVOKE ALL ON FUNCTION public.classify_rwanda_coordinate_v2(
  double precision, double precision, double precision
) FROM PUBLIC, anon, authenticated, service_role;

DROP FUNCTION IF EXISTS public.classify_rwanda_coordinate_v2(
  double precision, double precision, double precision
);

DROP TABLE IF EXISTS public.rwanda_national_geom;
