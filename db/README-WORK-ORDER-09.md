# Work Order 09 database assets

All SQL is maintained here, not in the Next.js application repository.

- Existing location RPC and feedback migrations were moved out of the app repo.
- The approved W2 spatial-index sampler migration is preserved.
- The empty ST_GeneratePoints repair is additive and has a narrow rollback.
- The truth-samples table has RLS enabled, with SELECT granted only to anon.
- Run the one-time manual population script with a privileged DB session. It fills
  30 districts x 2 seeds x 500 rows = 30,000 verified samples.

The live database work was applied to Supabase project `buexgewxypvkqmphvfec`.

## Historical SQL archive and verification scripts

Legacy SQL that previously lived under the application repository's `sql/`
folder has been preserved below `db/archive/` and `db/verification/`.
These are source archives and read-only diagnostic scripts, not migration
instructions. In particular, do not execute the old broad schema snapshot or
the pre-change function backup as part of a deployment. The canonical additive
migrations and rollback files above are the maintained database change path.
