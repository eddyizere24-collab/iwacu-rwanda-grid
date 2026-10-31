-- Roll back only the additive W2 truth-sample REST lookup index.
DROP INDEX IF EXISTS public.w2_truth_samples_district_seed_idx_idx;
