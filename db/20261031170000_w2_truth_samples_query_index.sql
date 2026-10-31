-- Additive index for the exact anonymous W2 truth-sample REST lookup.
-- Supports district + seed equality filters, idx ordering, and the minimal
-- projection used by scripts/rpc-load.mjs. The existing PK orders kind
-- before idx, so it cannot satisfy ORDER BY idx without a sort.
BEGIN;

CREATE INDEX IF NOT EXISTS w2_truth_samples_district_seed_idx_idx
  ON public.w2_truth_samples (district_scope_code, seed, idx)
  INCLUDE (lng, lat, true_village_scope_code);

ANALYZE public.w2_truth_samples;

COMMIT;
