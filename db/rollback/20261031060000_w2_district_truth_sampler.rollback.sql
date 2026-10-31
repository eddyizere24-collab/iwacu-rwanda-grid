-- Rollback for 20261031060000_w2_district_truth_sampler.sql
REVOKE ALL ON FUNCTION public.w2_sample_district_village_truth(text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.w2_sample_district_village_truth(text, integer) FROM anon;
DROP FUNCTION IF EXISTS public.w2_sample_district_village_truth(text, integer);
