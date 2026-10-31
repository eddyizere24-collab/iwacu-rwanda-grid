-- Precomputed W2 truth samples. The browser role can read only these rows.
CREATE TABLE public.w2_truth_samples (
  district_scope_code text NOT NULL,
  seed integer NOT NULL CHECK (seed IN (424242, 20261030)),
  idx integer NOT NULL CHECK (idx BETWEEN 1 AND 400),
  lng double precision NOT NULL,
  lat double precision NOT NULL,
  true_village_scope_code text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('interior', 'shared_boundary_50m')),
  CONSTRAINT w2_truth_samples_pk
    PRIMARY KEY (district_scope_code, seed, kind, idx)
);

ALTER TABLE public.w2_truth_samples ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.w2_truth_samples FROM PUBLIC, anon, authenticated, service_role;

CREATE POLICY w2_truth_samples_anon_select
  ON public.w2_truth_samples
  FOR SELECT TO anon
  USING (true);

GRANT SELECT ON TABLE public.w2_truth_samples TO anon;
