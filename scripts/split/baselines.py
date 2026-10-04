#!/usr/bin/env python
"""Baselines for the engine module split: measure once, compare per step.

    uv run python scripts/split/baselines.py measure --out before.json [--full] [--skip-test]
    uv run python scripts/split/baselines.py compare before.json after.json --step F2

`measure` records the engine sha, import time of `import magic_cards_model`
(median of 5 fresh interpreters, `-X importtime`; measured on
`magic_cards_model.models.game` because the package root is empty), `mise run test` wall time
and counts (and `mise run test:full` with --full), the collected test count
(and how many of them are the split's own tests, which the gate does not count),
the sha256 of `scripts/sweep_pool.py --effects` stdout, a sha256 over
tests/golden, and the dispatch fingerprint hash (whole, results-only, and
per-ladder chain name sets).

`compare` applies the design's "Gates before and after" and exits 1, naming
every violation. A field missing on either side is reported as "not measured"
and counts as a violation: absence is never a pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGE = "magic_cards_model"
# The package root's __init__ is empty, so `import magic_cards_model` alone costs
# microseconds; the real import cost is the engine's heavy entry module, which
# pulls in machines.effects, layers and the rest.
TARGET = f"{PACKAGE}.models.game"
SELF_MODULES = ("machines.effects", "models.game", "machines.layers")
IMPORT_RUNS = 5
IMPORT_LIMIT = 1.15
SUITE_LIMIT = 0.05
STEPS = ("F1", "F2", "F3", "F4", "F4a", "F4b", "F4c", "F4d", "F4e")
NOT_MEASURED = "not measured"


# ----- hashing helpers -----


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def hash_tree(root: Path) -> str:
    """sha256 over sorted relative paths and file bytes (independent of walk order)."""
    digest = hashlib.sha256()
    files = sorted(p for p in root.rglob("*") if p.is_file())
    for path in files:
        rel = path.relative_to(root).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(rel).to_bytes(8, "big") + rel)
        digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def fingerprint_summary(text: str) -> dict:
    """Whole-text hash, results-only hash and per-ladder sorted chain name lists."""
    data = json.loads(text)
    results = {ladder: body.get("results", {}) for ladder, body in data.items()}
    results_text = json.dumps(results, sort_keys=True, separators=(",", ":"))
    return {
        "sha256": hash_text(text),
        "results_sha256": hash_text(results_text),
        "chains": {ladder: sorted(body.get("chain", [])) for ladder, body in sorted(data.items())},
    }


# ----- output parsers -----


def parse_importtime(stderr: str) -> tuple[int, dict[str, int]]:
    """Return (cumulative us of the TARGET import, {short module name: self us}).

    The target's own line comes last in the output (the top-level import); an
    earlier, indented line carries the real self time (the top-level one is ~0).
    """
    cumulative = 0
    selfs: dict[str, int] = {}
    for line in stderr.splitlines():
        m = re.match(r"import time:\s+(\d+) \|\s+(\d+) \|(\s*)(\S+)\s*$", line)
        if not m:
            continue
        self_us, cum_us, name = int(m.group(1)), int(m.group(2)), m.group(4)
        if name == TARGET:
            cumulative = cum_us
        if name.startswith(PACKAGE + "."):
            short = name[len(PACKAGE) + 1 :]
            if short in SELF_MODULES:
                selfs.setdefault(short, self_us)
    return cumulative, selfs


def parse_pytest_summary(output: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "xfailed": 0}
    summary = ""
    for line in output.splitlines():
        if re.search(r"\d+ (passed|failed|xfailed|skipped|error)", line) and " in " in line:
            summary = line
    for n, word in re.findall(r"(\d+) (passed|failed|xfailed)", summary):
        counts[word] = int(n)
    return counts


#: tests the split itself adds (F2's dispatch order test); not a test count change
SPLIT_TESTS = ("tests/test_dispatch_order.py",)


def parse_split_test_count(output: str) -> int:
    """How many collected node ids (`pytest --collect-only -q`) the split's own tests are."""
    return sum(1 for line in output.splitlines() if line.startswith(SPLIT_TESTS))


def parse_failed_tests(output: str) -> list[str]:
    """Node ids of the FAILED/ERROR lines of pytest's short test summary."""
    found = re.findall(r"^(?:FAILED|ERROR) (\S+)", output, flags=re.MULTILINE)
    return list(dict.fromkeys(found))


def parse_collect_count(output: str) -> int:
    found = re.findall(r"(\d+) tests? collected", output)
    if not found:
        raise RuntimeError("no 'N tests collected' line in pytest --collect-only output")
    return int(found[-1])


# ----- measuring -----


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({proc.returncode}):\n{proc.stderr[-2000:]}")
    return proc


def _py(*args: str) -> list[str]:
    return ["mise", "exec", "--", "uv", "run", *args]


def measure_import_time() -> dict:
    cums: list[int] = []
    selfs: dict[str, list[int]] = {m: [] for m in SELF_MODULES}
    for _ in range(IMPORT_RUNS):
        proc = _run(_py("python", "-X", "importtime", "-c", f"import {TARGET}"))
        cum, per = parse_importtime(proc.stderr)
        if not cum:
            raise RuntimeError("could not find the target module line in -X importtime output")
        cums.append(cum)
        for name in SELF_MODULES:
            if name in per:
                selfs[name].append(per[name])
    return {
        "runs": IMPORT_RUNS,
        "cumulative_us": int(statistics.median(cums)),
        "self_us": {n: int(statistics.median(v)) for n, v in selfs.items() if v},
    }


def measure_suite(task: str) -> dict:
    start = time.monotonic()
    proc = _run(["mise", "run", task], check=False)
    wall = time.monotonic() - start
    output = proc.stdout + proc.stderr
    counts = parse_pytest_summary(output)
    failed = parse_failed_tests(output)
    return {
        "wall_s": round(wall, 2),
        "returncode": proc.returncode,
        **counts,
        "failed_tests": failed,
    }


def measure(full: bool, skip_test: bool) -> dict:
    out: dict = {"engine_sha": _run(["git", "rev-parse", "HEAD"]).stdout.strip()}
    out["import_time"] = measure_import_time()
    if not skip_test:
        out["suite"] = measure_suite("test")
        if full:
            out["suite_full"] = measure_suite("test:full")
    collect = _run(_py("pytest", "-o", "addopts=", "--collect-only", "-q"))
    out["test_count"] = parse_collect_count(collect.stdout)
    out["split_test_count"] = parse_split_test_count(collect.stdout)
    out["sweep_sha256"] = hash_text(
        _run(_py("python", "scripts/sweep_pool.py", "--effects")).stdout
    )
    out["goldens_sha256"] = hash_tree(REPO / "tests" / "golden")
    fingerprint = _run(_py("python", "scripts/dispatch_fingerprint.py")).stdout
    out["fingerprint"] = fingerprint_summary(fingerprint)
    committed = REPO / "tests" / "dispatch_fingerprint_baseline.json"
    out["fingerprint"]["matches_committed"] = committed.is_file() and json.loads(
        fingerprint
    ) == json.loads(committed.read_text())
    return out


# ----- comparing -----


def _get(data: dict, path: str):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _chain_sets(before: dict, after: dict, out: list[str]) -> None:
    b, a = _get(before, "fingerprint.chains"), _get(after, "fingerprint.chains")
    if b is None or a is None:
        out.append(f"fingerprint chains: {NOT_MEASURED} in {'before' if b is None else 'after'}")
        return
    for ladder in sorted(set(b) | set(a)):
        bs, as_ = set(b.get(ladder, [])), set(a.get(ladder, []))
        if bs != as_:
            out.append(
                f"fingerprint chain set changed for {ladder}: "
                f"missing {sorted(bs - as_)}, added {sorted(as_ - bs)}"
            )


def compare(before: dict, after: dict, step: str) -> list[str]:
    if step not in STEPS:
        raise ValueError(f"unknown step {step!r}, expected one of {', '.join(STEPS)}")
    out: list[str] = []

    def both(path: str, label: str | None = None):
        b, a = _get(before, path), _get(after, path)
        if b is None or a is None:
            side = "before" if b is None else "after"
            out.append(f"{label or path}: {NOT_MEASURED} in {side}")
            return None
        return b, a

    def identical(path: str, label: str):
        pair = both(path, label)
        if pair and pair[0] != pair[1]:
            out.append(f"{label} changed: {pair[0]} -> {pair[1]}")

    identical("sweep_sha256", "sweep hash")
    identical("goldens_sha256", "goldens hash")
    pair = both("test_count", "test count")
    if pair:
        b = pair[0] - (before.get("split_test_count") or 0)
        a = pair[1] - (after.get("split_test_count") or 0)
        if a != b:
            out.append(f"test count changed: {b} -> {a} (without the split's own tests)")

    if step == "F2":
        identical("fingerprint.results_sha256", "fingerprint results hash")
        _chain_sets(before, after, out)
    elif step == "F1" or _get(before, "fingerprint.sha256") == _get(after, "fingerprint.sha256"):
        identical("fingerprint.sha256", "fingerprint hash")
    else:
        # after F2 the chain order is F2's: held to the baseline F2 committed, plus the
        # pre-split results and chain sets
        if not _get(after, "fingerprint.matches_committed"):
            out.append(
                "fingerprint hash changed and is not the committed "
                "tests/dispatch_fingerprint_baseline.json"
            )
        identical("fingerprint.results_sha256", "fingerprint results hash")
        _chain_sets(before, after, out)

    pair = both("import_time.cumulative_us", "import time")
    if pair and pair[1] > pair[0] * IMPORT_LIMIT:
        out.append(
            f"import time {pair[0]} -> {pair[1]} us exceeds +15%: needs -X importtime review"
        )

    for key, label in (("suite", "suite"), ("suite_full", "suite_full")):
        pair = both(f"{key}.wall_s", f"{label} wall time")
        if pair and pair[1] - pair[0] > pair[0] * SUITE_LIMIT:
            out.append(f"{label} wall time {pair[0]}s -> {pair[1]}s is more than 5% slower")
        failed = _get(after, f"{key}.failed")
        if failed:
            names = _get(after, f"{key}.failed_tests") or []
            out.append(
                f"{label} has {failed} failed in after"
                + (f": {', '.join(names[:10])}" if names else "")
            )
    return out


# ----- cli -----


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--out", required=True)
    m.add_argument("--full", action="store_true", help="also run mise run test:full")
    m.add_argument("--skip-test", action="store_true", help="skip suite timing runs")
    c = sub.add_parser("compare")
    c.add_argument("before")
    c.add_argument("after")
    c.add_argument("--step", required=True, choices=STEPS)
    args = parser.parse_args(argv)

    if args.cmd == "measure":
        result = measure(args.full, args.skip_test)
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.out}")
        return 0
    before = json.loads(Path(args.before).read_text())
    after = json.loads(Path(args.after).read_text())
    violations = compare(before, after, args.step)
    for v in violations:
        print(f"VIOLATION: {v}")
    if not violations:
        print(f"baselines {args.step}: ok")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
