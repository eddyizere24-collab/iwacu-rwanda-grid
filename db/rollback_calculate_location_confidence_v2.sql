-- WORK ORDER 15 rollback.
-- Additive v2 only: dropping this function leaves v1 and all tables/indexes untouched.
DROP FUNCTION IF EXISTS public.calculate_location_confidence_v2(double precision, double precision, double precision);
