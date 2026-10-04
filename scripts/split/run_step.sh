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
# Then `ruff format` + `ruff check --fix` on the new package only (the step is
# split_lib.sh's split_step, which port_branch.sh runs too), then exactly one
# commit titled "split <step>: <module>" with the trailer "Split-Step: <step>".
# Refuses on a dirty tree, and when the previous step's trailer is not in the
# history. --dry-print prints the commands instead of running them (no git checks).
#
# Test/override hooks (defaults are the real tools): SPLIT_PY, SPLIT_RUFF,
# SPLIT_MANIFEST_DIR, SPLIT_SURFACE, SPLIT_OVERLAP_ARGS. bash 3.2 compatible.
set -eo pipefail

TOOLS="$(cd "$(dirname "$0")" && pwd)"
PY="${SPLIT_PY:-mise exec -- uv run python}"
RUFF="${SPLIT_RUFF:-mise exec -- ruff}"
MANIFESTS="${SPLIT_MANIFEST_DIR:-$TOOLS/manifest}"
SURFACE="${SPLIT_SURFACE:-}" # default: the codemod picks scripts/split/surface/<module>.json

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

if [ "$DRY" = 0 ]; then
  if [ -n "$(git status --porcelain)" ]; then
    echo "refusing: dirty tree (commit or stash first)" >&2
    exit 1
  fi
  if [ -n "$PREV" ] && [ -z "$(git log -1 --format=%H --grep="^Split-Step: $PREV\$")" ]; then
    echo "refusing: precondition missing, no commit with trailer 'Split-Step: $PREV' in history" >&2
    exit 1
  fi
fi

[ "$DRY" = 1 ] || [ -f "$MANIFEST" ] || { echo "no manifest $MANIFEST" >&2; exit 1; }

# The step itself is split_lib.sh's split_step, shared with port_branch.sh.
. "$TOOLS/split_lib.sh"
SPLIT_LIB_PY="$PY"
SPLIT_LIB_RUFF="$RUFF"
SPLIT_LIB_TOOLS="$TOOLS"
SPLIT_LIB_DRY="$DRY"
SPLIT_LIB_WORK="$(mktemp -d)"
trap 'rm -rf "$SPLIT_LIB_WORK"' EXIT
F1_COMMIT="<commit with trailer Split-Step: F1>"
if [ "$DRY" = 0 ] && [ "$STEP" = F2 ]; then
  F1_COMMIT="$(git log -1 --format=%H --grep='^Split-Step: F1$')"
fi
split_step "$STEP" "$MANIFEST" "$F1_COMMIT" "$SURFACE"

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
