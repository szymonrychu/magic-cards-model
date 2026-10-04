#!/usr/bin/env bash
# One landing of the engine module split, as one script-made commit.
#
#   scripts/split/run_step.sh [--dry-print] <F1|F2|F3|F4a|F4b|F4c|F4d|F4e>
#
#   F1  codemod effects            F4a codemod layers       F4d codemod triggers
#   F2  overlap.py, then            F4b codemod replacement  F4e codemod cost
#       to_registry on the effects  F4c codemod casting
#       package
#   F3  codemod game
#
# Then `ruff format` + `ruff check --fix` on the new package only, then exactly
# one commit titled "split <step>: <module>" with the trailer "Split-Step: <step>".
# Refuses on a dirty tree, and when the previous step's trailer is not in the
# history. --dry-print prints the commands instead of running them (no git checks).
#
# Test/override hooks (defaults are the real tools): SPLIT_PY, SPLIT_RUFF,
# SPLIT_MANIFEST_DIR, SPLIT_SURFACE. bash 3.2 compatible.
set -eo pipefail

TOOLS="$(cd "$(dirname "$0")" && pwd)"
PY="${SPLIT_PY:-mise exec -- uv run python}"
RUFF="${SPLIT_RUFF:-mise exec -- ruff}"
MANIFESTS="${SPLIT_MANIFEST_DIR:-$TOOLS/manifest}"
SURFACE="${SPLIT_SURFACE:-$TOOLS/surface}"

usage() {
  echo "usage: run_step.sh [--dry-print] <F1|F2|F3|F4a|F4b|F4c|F4d|F4e>" >&2
  exit 2
}

DRY=0
STEP=""
for arg in "$@"; do
  case "$arg" in
    --dry-print) DRY=1 ;;
    -*) usage ;;
    *) [ -z "$STEP" ] || usage; STEP="$arg" ;;
  esac
done

case "$STEP" in
  F1) MODULE=effects; PREV="" ;;
  F2) MODULE=effects; PREV=F1 ;;
  F3) MODULE=game; PREV=F2 ;;
  F4a) MODULE=layers; PREV=F3 ;;
  F4b) MODULE=replacement; PREV=F4a ;;
  F4c) MODULE=casting; PREV=F4b ;;
  F4d) MODULE=triggers; PREV=F4c ;;
  F4e) MODULE=cost; PREV=F4d ;;
  *) usage ;;
esac

MANIFEST="$MANIFESTS/$MODULE.toml"
manifest_value() { sed -n "s/^$1 *= *\"\(.*\)\"/\1/p" "$MANIFEST" | head -1; }

run() {
  if [ "$DRY" = 1 ]; then
    echo "+ $*"
  else
    "$@"
  fi
}

if [ "$DRY" = 0 ]; then
  if [ -n "$(git status --porcelain)" ]; then
    echo "refusing: dirty tree (commit or stash first)" >&2
    exit 1
  fi
  if [ -n "$PREV" ] && ! git log --format=%B | grep -qx "Split-Step: $PREV"; then
    echo "refusing: precondition missing, no commit with trailer 'Split-Step: $PREV' in history" >&2
    exit 1
  fi
fi

[ "$DRY" = 1 ] || [ -f "$MANIFEST" ] || { echo "no manifest $MANIFEST" >&2; exit 1; }
if [ -f "$MANIFEST" ]; then
  SOURCE="$(manifest_value source)"
  PACKAGE="$(manifest_value package)"
else
  SOURCE="<source of manifest/$MODULE.toml>"
  PACKAGE="<package of manifest/$MODULE.toml>"
fi

TARGETS="$PACKAGE"
if [ "$STEP" = F2 ]; then
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  # overlap.py reads the monolith source; after F1 it only exists in history.
  F1_COMMIT="<commit with trailer Split-Step: F1>"
  [ "$DRY" = 1 ] || F1_COMMIT="$(git log -1 --format=%H --grep='^Split-Step: F1$')"
  if [ "$DRY" = 1 ]; then
    echo "+ git show $F1_COMMIT^:$SOURCE > $TMP/monolith.py"
  else
    git show "$F1_COMMIT^:$SOURCE" > "$TMP/monolith.py"
  fi
  run $PY "$TOOLS/overlap.py" --source "$TMP/monolith.py" --manifest "$MANIFEST" --out "$TMP/overlap.json"
  run $PY "$TOOLS/to_registry.py" "$PACKAGE" --manifest "$MANIFEST" --overlap "$TMP/overlap.json"
  TARGETS="$PACKAGE tests/test_dispatch_order.py"
else
  run $PY "$TOOLS/codemod.py" "$MANIFEST" --surface "$SURFACE"
fi

run $RUFF format $TARGETS
run $RUFF check --fix $TARGETS

if [ "$DRY" = 1 ]; then
  echo "+ git add -A"
  echo "+ git commit -m \"split $STEP: $MODULE\" -m \"Split-Step: $STEP\""
  exit 0
fi

git add -A
if git diff --cached --quiet; then
  echo "refusing: step $STEP produced no change" >&2
  exit 1
fi
git commit -q -m "split $STEP: $MODULE" -m "Split-Step: $STEP"
echo "committed: split $STEP: $MODULE"
