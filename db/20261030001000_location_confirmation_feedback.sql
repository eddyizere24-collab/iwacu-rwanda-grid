-- Optional, consent-based, privacy-minimised location confirmation feedback.
-- No account/user ID, phone, full IP, or precise coordinates are stored.
CREATE TABLE IF NOT EXISTS public.location_confirmation_feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  village_id uuid NOT NULL REFERENCES public.boundaries(id) ON DELETE CASCADE,
  method text NOT NULL CHECK (method IN ('gps', 'map', 'manual', 'nearest', 'offline')),
  accuracy_m numeric(8,2) NULL CHECK (accuracy_m IS NULL OR (accuracy_m >= 1 AND accuracy_m <= 50000)),
  latitude_coarse numeric(4,2) NULL CHECK (latitude_coarse IS NULL OR (latitude_coarse >= -90 AND latitude_coarse <= 90)),
  longitude_coarse numeric(5,2) NULL CHECK (longitude_coarse IS NULL OR (longitude_coarse >= -180 AND longitude_coarse <= 180)),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((latitude_coarse IS NULL AND longitude_coarse IS NULL) OR
         (latitude_coarse IS NOT NULL AND longitude_coarse IS NOT NULL))
);

ALTER TABLE public.location_confirmation_feedback ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.location_confirmation_feedback FROM PUBLIC, anon, authenticated, service_role;
GRANT INSERT ON TABLE public.location_confirmation_feedback TO service_role;
CREATE POLICY location_confirmation_feedback_deny_browser_access
  ON public.location_confirmation_feedback
  FOR ALL TO anon, authenticated
  USING (false)
  WITH CHECK (false);

COMMENT ON TABLE public.location_confirmation_feedback IS
  'Optional consent-based anonymous location-quality feedback. Contains no user identifier, contact detail, full IP, or precise coordinates; coordinates are rounded to two decimal places by the server.';
