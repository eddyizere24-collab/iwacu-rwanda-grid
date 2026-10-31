# W2 district truth sampler

Files:
- `20261031060000_w2_district_truth_sampler.sql`: additive, SELECT-only SECURITY DEFINER RPC. For a valid district and one of the two W2 seeds, it returns 400 uniform-area interior village points and 100 points in strips up to 49 metres from shared village boundaries. The true village is independently resolved by exact `extensions.ST_Contains`.
- `rollback/20261031060000_w2_district_truth_sampler.rollback.sql`: removes only this function and its EXECUTE permission.

Security:
- Only the Supabase `anon` role is granted EXECUTE.
- The function does not grant table access and contains no INSERT/UPDATE/DELETE.
- It validates the JWT role, district-code shape, and the two fixed W2 seeds; output is exactly 500 rows or it raises.
- Because this is a SECURITY DEFINER function against an RLS-protected table, it MUST be reviewed and applied deliberately. It has not been applied to Production.

Limit:
- The current Production database has no lake/hydrography polygons. This sampler cannot generate the separately required 200 national lakeshore points until an authoritative lake/waterbody dataset is provided and loaded.
