-- Rollback for 20261031_w2_kivu_lakeshore_truth_sampler.sql
REVOKE ALL ON FUNCTION public.w2_sample_kivu_lakeshore_truth(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.w2_sample_kivu_lakeshore_truth(integer) FROM anon;
DROP FUNCTION IF EXISTS public.w2_sample_kivu_lakeshore_truth(integer);
