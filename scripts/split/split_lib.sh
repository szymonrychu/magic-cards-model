# The one implementation of an engine module split step, sourced by run_step.sh (the
# split itself) and port_branch.sh (the re-split of an open branch), so a ported
# branch re-splits to exactly the tree main's split commit has.
#
#   . scripts/split/split_lib.sh
#   split_step <step> <manifest> <f1 commit> [<surface json>] [<overlap json>]
#
# Runs in the repository root and leaves the result uncommitted:
#   F1 F3 F4a..F4e  codemod.py <manifest> [--surface <surface json>]
#   F2              overlap.py on <f1 commit>^:<source> (skipped when <overlap json> is
#                   given), copied to $SPLIT_F2_OVERLAP (committed with the step), then
#                   to_registry.py <package> --manifest <manifest>
#                   --overlap $SPLIT_F2_OVERLAP --tests-dir tests
# then `ruff format` and `ruff check --fix` on the step's package (F2: also
# tests/test_dispatch_order.py). The generators write lint-clean code, so a ruff
# finding left over fails the step. F2 last regenerates $SPLIT_FP_BASELINE from
# dispatch_fingerprint.py (F2 reorders the chains; results stay identical).
#
# Caller settings: SPLIT_LIB_PY (python runner), SPLIT_LIB_RUFF (ruff runner),
# SPLIT_LIB_TOOLS (directory holding codemod.py etc.), SPLIT_LIB_WORK (scratch
# directory), SPLIT_LIB_DRY=1 (print the commands instead of running them).
# SPLIT_OVERLAP_ARGS adds overlap.py arguments (tests: --corpus-json <file>).
# The python tools run with the repository root appended to PYTHONPATH (the
# manifest's module is imported from there). bash 3.2 compatible.

# Where F2 records the overlap json it used, relative to the repository root.
SPLIT_F2_OVERLAP="scripts/split/state/f2-overlap.json"
# The committed dispatch fingerprint baseline F2 regenerates (when the repo has one).
SPLIT_FP_BASELINE="tests/dispatch_fingerprint_baseline.json"

split_manifest_value() {
    sed -n "s/^$2 *= *\"\(.*\)\"/\1/p" "$1" | head -1
}

split_run() {
    if [ "${SPLIT_LIB_DRY:-0}" = 1 ]; then
        echo "+ $*"
    else
        "$@"
    fi
}

split_py() {
    if [ "${SPLIT_LIB_DRY:-0}" = 1 ]; then
        echo "+ $SPLIT_LIB_PY $*"
    else
        # shellcheck disable=SC2086
        PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$PWD" $SPLIT_LIB_PY "$@"
    fi
}

split_step() {
    local step="$1" manifest="$2" f1="$3" surface="${4:-}" overlap="${5:-}"
    local source package module targets
    if [ -f "$manifest" ]; then
        source="$(split_manifest_value "$manifest" source)"
        package="$(split_manifest_value "$manifest" package)"
        module="$(split_manifest_value "$manifest" module)"
    else
        source="<source of $manifest>"
        package="<package of $manifest>"
        module="<module of $manifest>"
    fi
    targets="$package"
    if [ "$step" = F2 ]; then
        if [ -z "$overlap" ]; then
            # overlap.py reads the monolith source; after F1 it only exists in history
            if [ "${SPLIT_LIB_DRY:-0}" = 1 ]; then
                echo "+ git show $f1^:$source > $SPLIT_LIB_WORK/monolith.py"
            else
                git show "$f1^:$source" >"$SPLIT_LIB_WORK/monolith.py"
            fi
            overlap="$SPLIT_LIB_WORK/overlap.json"
            # shellcheck disable=SC2086
            split_py "$SPLIT_LIB_TOOLS/overlap.py" --source "$SPLIT_LIB_WORK/monolith.py" \
                --manifest "$manifest" --module "$module" --out "$overlap" \
                ${SPLIT_OVERLAP_ARGS:-}
        fi
        # the overlap the edges come from is committed with F2, so a port re-split reuses
        # exactly these edges instead of re-measuring them on the code present then
        split_run mkdir -p "$(dirname "$SPLIT_F2_OVERLAP")"
        split_run cp "$overlap" "$SPLIT_F2_OVERLAP"
        split_py "$SPLIT_LIB_TOOLS/to_registry.py" "$package" --manifest "$manifest" \
            --overlap "$SPLIT_F2_OVERLAP" --tests-dir tests
        targets="$package tests/test_dispatch_order.py"
    elif [ -n "$surface" ]; then
        split_py "$SPLIT_LIB_TOOLS/codemod.py" "$manifest" --surface "$surface"
    else
        split_py "$SPLIT_LIB_TOOLS/codemod.py" "$manifest"
    fi
    # shellcheck disable=SC2086
    split_run $SPLIT_LIB_RUFF format $targets
    # shellcheck disable=SC2086
    split_run $SPLIT_LIB_RUFF check --fix $targets
    if [ "$step" = F2 ] && { [ "${SPLIT_LIB_DRY:-0}" = 1 ] || [ -f "$SPLIT_FP_BASELINE" ]; }; then
        # F2 reorders the chains: the committed fingerprint baseline is regenerated once
        if [ "${SPLIT_LIB_DRY:-0}" = 1 ]; then
            echo "+ $SPLIT_LIB_PY $SPLIT_LIB_TOOLS/../dispatch_fingerprint.py > $SPLIT_FP_BASELINE"
        else
            split_py "$SPLIT_LIB_TOOLS/../dispatch_fingerprint.py" >"$SPLIT_LIB_WORK/fp.json"
            mv "$SPLIT_LIB_WORK/fp.json" "$SPLIT_FP_BASELINE"
        fi
    fi
}
