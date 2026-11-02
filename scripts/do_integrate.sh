#!/usr/bin/env bash
# CHANGED 2026-11-02 CLAUDE: real git merges of the seven GROK branches (g2 g3 g4 g-dissolve offline j k) into
# one branch; g2/g3/g4 have unrelated histories, so --allow-unrelated-histories is required; see docs/HANDOFF.md
set -euo pipefail
REMOTE_PREFIX="${REMOTE_PREFIX:-origin}"
TARGET="${TARGET:-wip/integrate3}"
git config user.name "grok-integrate"
git config user.email "noreply@example.invalid"
git checkout -q -B "$TARGET" "$REMOTE_PREFIX/main"
for b in g2 g3 g4 g-dissolve offline j k; do
  echo "== merging wip/$b"
  git merge --no-ff --allow-unrelated-histories -X theirs -q \
    -m "[GROK] integrate3: real merge of wip/$b - keep branch code - proof via integration_guard" \
    "$REMOTE_PREFIX/wip/$b"
done
# the branch copies of the demo page load third-party CDNs; keep main's self-hosted page
git checkout "$REMOTE_PREFIX/main" -- basemap/demo/index.html
git commit -q -m "[GROK] integrate3: keep main's self-hosted basemap/demo/index.html - no third-party URLs"
echo "== guard"
fail=0
for b in g2 g3 g4 g-dissolve offline j k; do
  head=$(git rev-parse "$REMOTE_PREFIX/wip/$b")
  if git merge-base --is-ancestor "$head" HEAD; then echo "ANCESTOR YES wip/$b $head"; else echo "ANCESTOR NO  wip/$b $head"; fail=1; fi
  missing=0
  while IFS= read -r f; do
    case "$f" in basemap/demo/index.html|docs/HANDOFF.md) continue;; esac
    if ! git cat-file -e "HEAD:$f" 2>/dev/null; then echo "MISSING $f (from wip/$b)"; missing=$((missing+1)); fi
  done < <(git ls-tree -r --name-only "$REMOTE_PREFIX/wip/$b")
  echo "wip/$b missing_files=$missing"; [ "$missing" -eq 0 ] || fail=1
done
echo "KEY FILE SIZES (bytes)"
for f in scripts/dissolve_hierarchy.py scripts/export_boundaries.py scripts/extract_landmarks.py \
         scripts/offline_validate_district.py .github/workflows/grid_invariants_g2.yml \
         packages/grid-lookup/test/parity.test.js packages/offline-locate/src/index.ts \
         packages/basemap-style/src/style.json; do
  printf "%s %s\n" "$f" "$(git cat-file -s "HEAD:$f" 2>/dev/null || echo MISSING)"
done
echo "THIRD-PARTY URL CHECK in demo page:"; git show HEAD:basemap/demo/index.html | grep -c -E 'https?://' || true
[ "$fail" -eq 0 ] || { echo "GUARD FAILED"; exit 1; }
echo "GUARD OK"
