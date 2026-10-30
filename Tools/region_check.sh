#!/usr/bin/env bash
# Checks that your changes to the world map (/Game/azrothreborn) stay inside your own region.
#
#   Tools/region_check.sh <region>             check working-tree changes and commits not yet on origin/main
#   Tools/region_check.sh <region> --staged    check only staged files (what the pre-commit hook runs)
#   Tools/region_check.sh <region> --install   install a git pre-commit hook that runs the --staged check
#
# <region> is a number (1-11) or a key such as 05_EmberwoodForest; see Docs/Regions/README.md.
# Ownership comes from Docs/Regions/actor_owners.tsv. Exit code 1 means a file owned by another region or by
# everyone (Shared) is changed; commit anyway with `git commit --no-verify` only after agreeing it with the owner.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
TABLE="$ROOT/Docs/Regions/actor_owners.tsv"
cd "$ROOT"

[ $# -ge 1 ] || { sed -n '2,11p' "$0"; exit 2; }
REGION="$1"
MODE="${2:-all}"

KEYS=$(cut -f2 "$TABLE" | tail -n +2 | grep -v '^Shared$' | sort -u)
if [[ "$REGION" =~ ^[0-9]+$ ]]; then
  REGION=$(echo "$KEYS" | grep "^$(printf '%02d' "$REGION")_" || true)
else
  REGION=$(echo "$KEYS" | grep -ix "$REGION" || true)
fi
[ -n "$REGION" ] || { echo "Unknown region '$1'. Regions:"; echo "$KEYS"; exit 2; }

if [ "$MODE" = "--install" ]; then
  HOOK="$(git rev-parse --git-path hooks)/pre-commit"
  printf '#!/usr/bin/env bash\nexec "$(git rev-parse --show-toplevel)/Tools/region_check.sh" %s --staged\n' "$REGION" > "$HOOK"
  chmod +x "$HOOK"
  echo "Installed pre-commit hook for $REGION ($HOOK)"
  exit 0
fi

if [ "$MODE" = "--staged" ]; then
  FILES=$(git diff --cached --name-only --diff-filter=ACMRD)
else
  BASE=$(git merge-base HEAD origin/main 2>/dev/null || git rev-parse HEAD)
  FILES=$( { git diff --name-only "$BASE"; git ls-files --others --exclude-standard; } | sort -u)
fi

echo "$FILES" | awk -F'\t' -v me="$REGION" '
  NR == FNR { if (FNR > 1) owner[$1] = $2; label[$1] = $4; next }
  $0 == "" { next }
  {
    f = $0
    if (f in owner) {
      o = owner[f]
      if (o == me) mine++
      else if (o == "Shared") { print "SHARED      " f "  (" label[f] ")"; bad++ }
      else { print "OTHER REGION " o "  " f "  (" label[f] ")"; bad++ }
    } else if (f ~ /^Content\/__ExternalObjects__\/azrothreborn\//) {
      print "SHARED      " f "  (world object, e.g. a data layer)"; bad++
    } else if (f ~ /^Content\/__ExternalActors__\/azrothreborn\//) {
      print "NEW ACTOR   " f "  (not in the ownership table yet; make sure you placed it inside " me ")"; newc++
    } else if (f == "Content/azrothreborn.umap" || f ~ /^Content\/Maps\/Regions\//) {
      print "SHARED      " f; bad++
    } else if (f ~ "^Content/Regions/" me "/") {
      mine++
    } else if (f ~ /^Content\//) {
      print "SHARED ASSET " f "  (outside Content/Regions/" me "/)"; warn++
    }
  }
  END {
    printf "\n%s: %d of your files, %d new actors, %d shared assets, %d conflicts\n", me, mine, newc, warn, bad
    exit (bad > 0)
  }' "$TABLE" -
