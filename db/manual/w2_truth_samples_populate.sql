-- One-time population after the table migration.
-- Run in a privileged SQL session against project buexgewxypvkqmphvfec.
-- It deliberately runs as postgres with no timeout; the helper validates
-- 400 interior + 100 shared-boundary points for each district/seed pair.
BEGIN;
SET LOCAL ROLE postgres;
SET LOCAL statement_timeout = 0;
SET LOCAL request.jwt.claims = '{"role":"anon"}';

INSERT INTO public.w2_truth_samples (
  district_scope_code, seed, idx, lng, lat, true_village_scope_code, kind
)
SELECT
  d.scope_code,
  s.seed,
  t.sample_index,
  t.longitude,
  t.latitude,
  t.true_village_scope_code,
  t.sample_kind
FROM public.boundaries d
CROSS JOIN (VALUES (424242), (20261030)) AS s(seed)
CROSS JOIN LATERAL public.w2_sample_district_village_truth(d.scope_code, s.seed) AS t
WHERE d.level::text = 'district'
  AND d.valid_to IS NULL
  AND d.scope_code ~ '^RW-P[1-5]-D[0-9]{2}$';

COMMIT;
