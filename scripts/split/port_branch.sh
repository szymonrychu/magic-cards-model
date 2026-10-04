#!/usr/bin/env bash
# Carry an open branch across the engine module split (design: P0 item 4, risk 6).
#
#   scripts/split/port_branch.sh <branch> [--onto <post-split ref>] [--step <STEP>=<manifest>]...
#                                [--overlap <file>]
#
# Finds the split commits on <onto> (default main) by their `Split-Step: <step>`
# trailer, merges the pre-split parent of the first one into <branch>, re-runs
# for every split step the same codemod / to_registry invocation with the
# manifests as they are on <onto>, commits the result as one `re-split` commit
# carrying the same trailers, then merges <onto>.
#
# The re-split commit has the branch as first parent and the last split commit
# as second parent (tree = the re-run result), so the final merge has the split
# itself as its base: conflicts can only remain where both sides changed the
# same def, and they are reported, never resolved.
#
# Step -> manifest (override per step with --step F1=path/in/repo.toml):
#   F1, F2 effects   F3 game   F4a layers   F4b replacement   F4c casting
#   F4d triggers     F4e cost
# Every re-run is split_lib.sh's split_step, the very function run_step.sh runs, so
# the re-split tree is the tree the script-made split commits have: F2 measures
# overlap.json on the F1 commit's parent (unless --overlap is given), and each step
# ends with ruff format and ruff check --fix on its package (F2 also on
# tests/test_dispatch_order.py).
# Environment: PORT_BRANCH_PYTHON overrides the python runner (default
# `mise exec -- uv run --project <tools repo> python`), PORT_BRANCH_RUFF the ruff
# runner (default `mise exec -- ruff`), SPLIT_OVERLAP_ARGS (or PORT_BRANCH_OVERLAP_ARGS)
# adds overlap.py arguments (e.g. --corpus-json). The tools (scripts/) are copied
# from the repository this script lives in before anything is checked out, so a
# branch cut before P0 can still be ported. bash 3.2 compatible (macOS).
set -euo pipefail

die() {
    echo "port_branch: $*" >&2
    exit 1
}

usage() {
    sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//' >&2
    exit "${1:-2}"
}

branch=""
onto="main"
overlap=""
step_maps=""
while [ $# -gt 0 ]; do
    case "$1" in
        --onto)
            [ $# -ge 2 ] || usage
            onto="$2"
            shift 2
            ;;
        --step)
            [ $# -ge 2 ] || usage
            case "$2" in *=*) ;; *) die "--step wants <STEP>=<manifest>, got '$2'" ;; esac
            step_maps="$step_maps$2"$'\n'
            shift 2
            ;;
        --overlap)
            [ $# -ge 2 ] || usage
            overlap="$2"
            shift 2
            ;;
        -h | --help) usage 0 ;;
        -*) die "unknown option $1" ;;
        *)
            [ -z "$branch" ] || usage
            branch="$1"
            shift
            ;;
    esac
done
[ -n "$branch" ] || usage

tools="$(cd "$(dirname "$0")/../.." && pwd)"

manifest_for() {
    local line
    while IFS= read -r line; do
        if [ "${line%%=*}" = "$1" ]; then
            echo "${line#*=}"
            return 0
        fi
    done <<EOF
$step_maps
EOF
    case "$1" in
        F1 | F2) echo scripts/split/manifest/effects.toml ;;
        F3) echo scripts/split/manifest/game.toml ;;
        F4a) echo scripts/split/manifest/layers.toml ;;
        F4b) echo scripts/split/manifest/replacement.toml ;;
        F4c) echo scripts/split/manifest/casting.toml ;;
        F4d) echo scripts/split/manifest/triggers.toml ;;
        F4e) echo scripts/split/manifest/cost.toml ;;
        *) die "unknown split step '$1'" ;;
    esac
}

cd "$(git rev-parse --show-toplevel)"

[ -z "$(git status --porcelain)" ] || die "working tree is dirty: commit or stash first"
git rev-parse --verify --quiet "$branch^{commit}" >/dev/null || die "no such branch: $branch"
git rev-parse --verify --quiet "$onto^{commit}" >/dev/null || die "no such ref: $onto"

if git merge-base --is-ancestor "$onto" "$branch"; then
    echo "port_branch: $branch already contains $onto, nothing to do"
    exit 0
fi
work="$(mktemp -d "${TMPDIR:-/tmp}/port_branch.XXXXXX")"
trap 'rm -rf "$work"' EXIT
mkdir "$work/tools"
cp -R "$tools/scripts" "$work/tools/scripts"
cp "$tools/pyproject.toml" "$work/tools/pyproject.toml" # codemod formats with the repo ruff config
ln -s "$tools/tests" "$work/tools/tests" # scripts.dispatch_fingerprint imports tests.cards
current="$(git symbolic-ref --short -q HEAD || true)"
if [ "$current" != "$branch" ]; then
    git checkout -q "$branch"
fi

report_conflicts() {
    echo "port_branch: $1" >&2
    echo "conflicted files:" >&2
    git diff --name-only --diff-filter=U | sed 's/^/  /' >&2
    echo "resolve them, then 'git commit' and run port_branch.sh again" >&2
    exit 1
}

# Split commits not yet in the branch, oldest first, as "<sha> <step>[ <step>]".
pending_shas=""
pending_steps=""
npending=0
for sha in $(git log --topo-order --reverse --format=%H -E --grep='^Split-Step: ' "$onto"); do
    if git merge-base --is-ancestor "$sha" HEAD; then
        continue
    fi
    steps="$(git log -1 --format=%B "$sha" | sed -n 's/^Split-Step: *//p')"
    pending_shas="$pending_shas $sha"
    pending_steps="$pending_steps$steps"$'\n'
    npending=$((npending + 1))
done

if [ "$npending" -gt 0 ]; then
    first="${pending_shas# }"
    first="${first%% *}"
    last="${pending_shas##* }"
    pre="$(git rev-parse "$first^")"
    if [ "$(git rev-list --count "$pre..$last")" -ne "$npending" ]; then
        die "$onto has commits between its split steps ($pre..$last): not a plain split, port by hand"
    fi

    echo "port_branch: merging pre-split ${pre%"${pre#???????}"} into $branch"
    if ! git merge --no-edit -q "$pre" >/dev/null; then
        report_conflicts "ordinary pre-split conflicts merging $pre"
    fi

    export PYTHONPATH="$work/tools${PYTHONPATH:+:$PYTHONPATH}"
    export PYTHONDONTWRITEBYTECODE=1
    # The step itself: split_lib.sh's split_step, the one run_step.sh runs, from the
    # copied tools so the branch's own scripts/ never matter.
    . "$work/tools/scripts/split/split_lib.sh"
    SPLIT_LIB_PY="${PORT_BRANCH_PYTHON:-mise exec -- uv run --project $tools python}"
    SPLIT_LIB_RUFF="${PORT_BRANCH_RUFF:-mise exec -- ruff}"
    SPLIT_LIB_TOOLS="$work/tools/scripts/split"
    SPLIT_OVERLAP_ARGS="${SPLIT_OVERLAP_ARGS:-${PORT_BRANCH_OVERLAP_ARGS:-}}"
    trailers=""
    n=0
    while IFS= read -r step; do
        [ -n "$step" ] || continue
        n=$((n + 1))
        rel="$(manifest_for "$step")"
        manifest="$work/$n-$(basename "$rel")"
        git show "$onto:$rel" >"$manifest" 2>/dev/null || die "$rel is not on $onto (step $step)"
        stem="$(basename "$rel" .toml)"
        echo "port_branch: re-running $step with $rel from $onto"
        surface=""
        if git cat-file -e "$onto:scripts/split/surface/$stem.json" 2>/dev/null; then
            git show "$onto:scripts/split/surface/$stem.json" >"$work/$n-surface.json"
            surface="$work/$n-surface.json"
        fi
        f1=""
        if [ "$step" = "F2" ] && [ -z "$overlap" ]; then
            f1="$(git log -1 --format=%H -E --grep='^Split-Step: F1$' "$onto")"
            [ -n "$f1" ] || die "no Split-Step: F1 commit on $onto, cannot measure the F2 overlap"
        fi
        SPLIT_LIB_WORK="$work/$n"
        mkdir "$SPLIT_LIB_WORK"
        split_step "$step" "$manifest" "$f1" "$surface" "$overlap" </dev/null
        trailers="${trailers}Split-Step: $step"$'\n'
    done <<EOF
$pending_steps
EOF

    printf 're-split\n\n%s' "$trailers" >"$work/message"
    git add -A
    tree="$(git write-tree)"
    commit="$(git commit-tree "$tree" -p HEAD -p "$last" -F "$work/message")"
    git merge --ff-only -q "$commit" >/dev/null
    echo "port_branch: committed re-split ${commit%"${commit#???????}"}"
fi

if ! git merge --no-edit -q "$onto" >/dev/null; then
    report_conflicts "both sides changed the same def merging $onto"
fi
echo "port_branch: $branch ported onto $onto"
