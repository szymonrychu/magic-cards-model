#!/usr/bin/env bash
# Cheap and full gates for one landing of the engine module split.
#
#   scripts/split/gates.sh [--dry-print] cheap|full --baseline <json> --step <step> [--base <sha>]
#                          [--keep <json>]
#
# cheap: mise run lint; baselines.py measure (runs mise run test, the collected test
#        count, the sweep hash, the golden hash, the dispatch fingerprint and the import
#        time) then baselines.py compare --step; tests/test_module_hygiene.py,
#        tests/test_split_surface.py (+ tests/test_dispatch_order.py from F2 on).
# full:  cheap + mise run test:full (measure --full), goldens byte-identical
#        (git diff --exit-code -- tests/golden), the regression guard with --ratchet from
#        the pre-split sha (the baseline's engine_sha unless --base), collected test
#        count identical (part of compare).
#
# --keep <json> also saves the gate's own measurement there (the freeze record).
# One PASS/FAIL line per check with its wall time; exits 1 on any FAIL, 2 on bad
# arguments. --dry-print prints the commands instead of running them.
# Overrides: SPLIT_PY (default "mise exec -- uv run python"). bash 3.2 compatible.
set -o pipefail

TOOLS="$(cd "$(dirname "$0")" && pwd)"
PY="${SPLIT_PY:-mise exec -- uv run python}"
STEPS="F1 F2 F3 F4a F4b F4c F4d F4e"

usage() {
  echo "usage: gates.sh [--dry-print] cheap|full --baseline <json> --step <$(echo $STEPS | tr ' ' '|')> [--base <sha>] [--keep <json>]" >&2
  exit 2
}

DRY=0 MODE="" BASELINE="" STEP="" BASE="" KEEP=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-print) DRY=1 ;;
    --baseline) [ $# -ge 2 ] || usage; BASELINE="$2"; shift ;;
    --step) [ $# -ge 2 ] || usage; STEP="$2"; shift ;;
    --base) [ $# -ge 2 ] || usage; BASE="$2"; shift ;;
    --keep) [ $# -ge 2 ] || usage; KEEP="$2"; shift ;;
    -*) usage ;;
    *) [ -z "$MODE" ] || usage; MODE="$1" ;;
  esac
  shift
done

case "$MODE" in cheap | full) ;; *) usage ;; esac
[ -n "$BASELINE" ] || usage
case " $STEPS " in *" $STEP "*) ;; *) usage ;; esac
if [ "$DRY" = 0 ] && [ ! -f "$BASELINE" ]; then
  echo "baseline not found: $BASELINE" >&2
  usage
fi

LOGDIR="$(mktemp -d)"
trap 'rm -rf "$LOGDIR"' EXIT
AFTER="$LOGDIR/after.json"
FAILS=0

now() { date +%s; }

# report <name> <0|1> <seconds>
report() {
  if [ "$2" = 0 ]; then
    echo "PASS $1 (${3}s)"
  else
    echo "FAIL $1 (${3}s)"
    FAILS=$((FAILS + 1))
  fi
}

# check <name> <command...>: run it, one PASS/FAIL line, tail of its output on FAIL.
check() {
  local name="$1"
  shift
  if [ "$DRY" = 1 ]; then
    echo "CHECK $name: $*"
    return 0
  fi
  local start rc
  start=$(now)
  "$@" > "$LOGDIR/check.log" 2>&1
  rc=$?
  report "$name" "$rc" $(($(now) - start))
  [ "$rc" = 0 ] || tail -25 "$LOGDIR/check.log" | sed 's/^/    /'
  return 0
}

# the engine sha the baseline was measured at, the pre-split sha for the guard
if [ -z "$BASE" ]; then
  if [ "$DRY" = 1 ]; then
    BASE="\$(engine_sha of $BASELINE)"
  else
    BASE="$($PY -c 'import json,sys; print(json.load(open(sys.argv[1]))["engine_sha"])' "$BASELINE")" ||
      { echo "baseline has no engine_sha" >&2; exit 2; }
  fi
fi

MEASURE_ARGS=""
[ "$MODE" = full ] && MEASURE_ARGS="--full"

SPLIT_TESTS="tests/test_module_hygiene.py tests/test_split_surface.py"
[ "$STEP" = F1 ] || SPLIT_TESTS="$SPLIT_TESTS tests/test_dispatch_order.py"

check "lint" mise run lint
check "split tests (hygiene, surface$([ "$STEP" = F1 ] || echo ', dispatch order'))" \
  $PY -m pytest $SPLIT_TESTS -q -o addopts=

# measure runs mise run test (and test:full for full), the counts and the hashes
check "baselines measure (wall time includes mise run test$([ "$MODE" = full ] && echo ' and test:full'))" \
  $PY "$TOOLS/baselines.py" measure --out "$AFTER" $MEASURE_ARGS
if [ "$DRY" = 1 ]; then
  echo "CHECK mise run test: from $AFTER suite.returncode"
  [ "$MODE" = full ] && echo "CHECK mise run test:full: from $AFTER suite_full.returncode"
  echo "CHECK fingerprint, sweep hash, import time, test count, goldens hash: $PY $TOOLS/baselines.py compare $BASELINE $AFTER --step $STEP"
  if [ "$MODE" = full ]; then
    echo "CHECK goldens byte-identical: git diff --exit-code -- tests/golden"
    echo "CHECK regression guard: mise run regression:guard -- --repo . --base $BASE --ratchet"
  fi
  exit 0
fi

if [ ! -f "$AFTER" ]; then
  echo "FAIL baselines compare (0s): measure wrote no result"
  exit 1
fi

if [ -n "$KEEP" ]; then
  mkdir -p "$(dirname "$KEEP")" && cp "$AFTER" "$KEEP"
fi

# suite results straight from the measure run: no second run of the suite
suite_check() { # <json key> <task name>
  local out rc
  out="$($PY -c '
import json, sys
s = json.load(open(sys.argv[1])).get(sys.argv[2]) or {}
ok = bool(s) and s.get("returncode") == 0 and not s.get("failed")
print(s.get("wall_s", 0))
sys.exit(0 if ok else 1)' "$AFTER" "$1")"
  rc=$?
  report "$2" "$rc" "${out%%.*}"
}
suite_check suite "mise run test"
[ "$MODE" = full ] && suite_check suite_full "mise run test:full"

# compare, then one line per gate: a violation is attributed by its label
start=$(now)
$PY "$TOOLS/baselines.py" compare "$BASELINE" "$AFTER" --step "$STEP" > "$LOGDIR/compare.txt" 2>&1
cmp_rc=$?
cmp_secs=$(($(now) - start))
grep '^VIOLATION' "$LOGDIR/compare.txt" > "$LOGDIR/violations.txt"
SEEN=0
[ -s "$LOGDIR/violations.txt" ] && SEEN=1
if [ "$MODE" = cheap ]; then
  # cheap does not run test:full, so a missing suite_full measurement is not a violation
  grep -v '^VIOLATION: suite_full' "$LOGDIR/violations.txt" > "$LOGDIR/v2.txt"
  mv "$LOGDIR/v2.txt" "$LOGDIR/violations.txt"
fi

# a suite timing violation is re-measured A/B (pre-split commit, then this tree) before it
# counts: a baseline taken hours earlier under different machine load is no yardstick
for key in suite suite_full; do
  if grep -Eq "^VIOLATION: $key (wall|cpu) time" "$LOGDIR/violations.txt"; then
    if $PY "$TOOLS/baselines.py" recheck "$BASELINE" "$AFTER" --key "$key" > "$LOGDIR/recheck-$key.txt" 2>&1; then
      grep -Ev "^VIOLATION: $key (wall|cpu) time" "$LOGDIR/violations.txt" > "$LOGDIR/rest.txt"
      mv "$LOGDIR/rest.txt" "$LOGDIR/violations.txt"
    fi
    sed 's/^/    /' "$LOGDIR/recheck-$key.txt"
  fi
done

claim() { # <name> <pattern>: report the gate, consume its violations
  if grep -Eq "$2" "$LOGDIR/violations.txt"; then
    report "$1" 1 "$cmp_secs"
    grep -E "$2" "$LOGDIR/violations.txt" | sed 's/^/    /'
    grep -Ev "$2" "$LOGDIR/violations.txt" > "$LOGDIR/rest.txt"
    mv "$LOGDIR/rest.txt" "$LOGDIR/violations.txt"
  else
    report "$1" 0 "$cmp_secs"
  fi
}
claim "fingerprint compare" '^VIOLATION: fingerprint'
claim "sweep hash" '^VIOLATION: sweep hash'
claim "import time" '^VIOLATION: import time'
claim "collected test count" '^VIOLATION: test count'
claim "goldens hash" '^VIOLATION: goldens hash'
claim "suite time" '^VIOLATION: suite (wall|cpu|has)'
[ "$MODE" = full ] && claim "suite_full time" '^VIOLATION: suite_full'
if [ -s "$LOGDIR/violations.txt" ]; then
  report "baselines compare (other)" 1 "$cmp_secs"
  sed 's/^/    /' "$LOGDIR/violations.txt"
elif [ "$cmp_rc" != 0 ] && [ "$SEEN" = 0 ]; then
  report "baselines compare" 1 "$cmp_secs"
  tail -25 "$LOGDIR/compare.txt" | sed 's/^/    /'
fi

if [ "$MODE" = full ]; then
  check "goldens byte-identical" git diff --exit-code -- tests/golden
  check "regression guard (0 offenders, 0 protected-test changes)" \
    mise run regression:guard -- --repo . --base "$BASE" --ratchet
fi

if [ "$FAILS" -gt 0 ]; then
  echo "GATES $MODE $STEP: FAIL ($FAILS failing)"
  exit 1
fi
echo "GATES $MODE $STEP: PASS"
