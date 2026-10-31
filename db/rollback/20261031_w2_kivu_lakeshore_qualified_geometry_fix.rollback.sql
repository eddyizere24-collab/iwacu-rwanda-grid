-- Rollback for the qualified-geometry fix; removes only the Kivu helper.
REVOKE ALL ON FUNCTION public.w2_sample_kivu_lakeshore_truth(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.w2_sample_kivu_lakeshore_truth(integer) FROM anon;
DROP FUNCTION IF EXISTS public.w2_sample_kivu_lakeshore_truth(integer);
