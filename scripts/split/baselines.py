#!/usr/bin/env python
"""Baselines for the engine module split: measure once, compare per step.

    uv run python scripts/split/baselines.py measure --out before.json [--full] [--skip-test]
    uv run python scripts/split/baselines.py compare before.json after.json --step F2

`measure` records the engine sha, import time of `import magic_cards_model`
(7 fresh interpreters, `-X importtime`: median wall, minimum CPU; measured on
`magic_cards_model.models.game` because the package root is empty), `mise run test` wall time
and counts with their CPU time (and `mise run test:full` with --full), the collected test count
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
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PACKAGE = "magic_cards_model"
# The package root's __init__ is empty, so `import magic_cards_model` alone costs
# microseconds; the real import cost is the engine's heavy entry module, which
# pulls in machines.effects, layers and the rest.
TARGET = f"{PACKAGE}.models.game"
SELF_MODULES = ("machines.effects", "models.game", "machines.layers")
IMPORT_RUNS = 7
IMPORT_LIMIT = 1.15
SUITE_LIMIT = 0.05
OUTPUT_TAIL_LINES = 20  # lines of a failed suite run kept in the measure json
RERUN_MAX = 10  # failed node ids rerun alone once; more than this is no flake
STEPS = ("F1", "F2", "F3", "F4", "F4a", "F4b", "F4c", "F4d", "F4e")
NOT_MEASURED = "not measured"


# ----- hashing helpers -----


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def hash_tree(root: Path) -> str:
    """sha256 over sorted relative paths and file bytes (independent of walk order).

    Bytecode caches are skipped: a .pyc header carries its source's mtime, which a fresh
    checkout changes.
    """
    digest = hashlib.sha256()
    files = sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.relative_to(root).parts
    )
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


def _children_cpu() -> float:
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


def timed_run(
    cmd: list[str], check: bool = True, cwd: Path = REPO
) -> tuple[subprocess.CompletedProcess, float, float]:
    """Run cmd; return (proc, wall seconds, CPU seconds of it and its reaped descendants).

    CPU time is what the timing gates compare: on a shared machine other sessions'
    suites stretch wall time without touching it."""
    cpu0, start = _children_cpu(), time.monotonic()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    wall, cpu = time.monotonic() - start, _children_cpu() - cpu0
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({proc.returncode}):\n{proc.stderr[-2000:]}")
    return proc, wall, cpu


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return timed_run(cmd, check)[0]


def _py(*args: str) -> list[str]:
    return ["mise", "exec", "--", "uv", "run", *args]


def measure_import_time() -> dict:
    cums: list[int] = []
    cpus: list[float] = []
    selfs: dict[str, list[int]] = {m: [] for m in SELF_MODULES}
    for _ in range(IMPORT_RUNS):
        # this interpreter is the repo venv's (run via `uv run`): no mise/uv startup in the CPU time
        proc, _, cpu = timed_run([sys.executable, "-X", "importtime", "-c", f"import {TARGET}"])
        cpus.append(cpu)
        cum, per = parse_importtime(proc.stderr)
        if not cum:
            raise RuntimeError("could not find the target module line in -X importtime output")
        cums.append(cum)
        for name in SELF_MODULES:
            if name in per:
                selfs[name].append(per[name])
    return import_summary(cums, cpus, selfs)


def import_summary(cums: list[int], cpus: list[float], selfs: dict[str, list[int]]) -> dict:
    """Medians of the wall-clock `-X importtime` figures; the gated CPU time is the
    minimum, the run that other load on the machine disturbed least."""
    return {
        "runs": len(cums),
        "cumulative_us": int(statistics.median(cums)),
        "cpu_us": int(min(cpus) * 1e6),
        "self_us": {n: int(statistics.median(v)) for n, v in selfs.items() if v},
    }


def measure_suite(task: str, run=timed_run) -> dict:
    """Counts, times and return code of `mise run <task>`; a failed run also keeps the
    last OUTPUT_TAIL_LINES lines, so a suite that errored before running a test says why."""
    proc, wall, cpu = run(["mise", "run", task], check=False)
    output = proc.stdout + proc.stderr
    out = {
        "wall_s": round(wall, 2),
        "cpu_s": round(cpu, 2),
        "returncode": proc.returncode,
        **parse_pytest_summary(output),
        "failed_tests": parse_failed_tests(output),
    }
    if proc.returncode != 0:
        out["output_tail"] = "\n".join(output.rstrip().splitlines()[-OUTPUT_TAIL_LINES:])
    failed = out["failed_tests"]
    if failed and len(failed) <= RERUN_MAX:
        # a load-sensitive test (a CPU budget) can fail under a busy machine: rerun the
        # failures once on their own; one that fails again stays a failure
        again, _, _ = run(
            _py("pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider", *failed), check=False
        )
        still = (
            set() if again.returncode == 0 else set(parse_failed_tests(again.stdout + again.stderr))
        )
        if again.returncode != 0 and not still:
            still = set(failed)
        out["rerun_passed"] = [t for t in failed if t not in still]
    return out


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


def _suite_cpu(cwd: Path, task: str) -> float:
    return timed_run(["mise", "run", task], check=False, cwd=cwd)[2]


def _prepare(worktree: Path) -> None:
    _run(["mise", "trust", "-q", str(worktree)])
    timed_run(["mise", "run", "install"], cwd=worktree)


def recheck(
    before_sha: str,
    task: str,
    rounds: int = 1,
    measure=_suite_cpu,
    prepare=_prepare,
    repo: Path = REPO,
) -> tuple[bool, str]:
    """A/B re-measure behind a suite timing violation: the baseline's commit in a throwaway
    worktree, then this tree, back to back, `rounds` times; the minimum CPU time of each
    side is held to the 5% limit. CPU time on a machine with performance and efficiency
    cores still moves with the load, so a baseline taken hours earlier is no yardstick."""
    with tempfile.TemporaryDirectory(prefix="split-recheck-") as tmp:
        worktree = Path(tmp) / "before"
        subprocess.run(
            ["git", "worktree", "add", "-q", "--detach", str(worktree), before_sha],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        try:
            prepare(worktree)
            b_cpu, a_cpu = [], []
            for _ in range(rounds):
                b_cpu.append(measure(worktree, task))
                a_cpu.append(measure(repo, task))
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=repo,
                capture_output=True,
            )
    b, a = min(b_cpu), min(a_cpu)
    ok = a - b <= b * SUITE_LIMIT
    return ok, f"{task} A/B cpu before {b}s, after {a}s ({(a / b - 1) * 100:+.1f}%, limit +5%)"


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

    # Timing gates hold CPU time to the limits when both sides measured it (wall time
    # on a shared machine measures the other sessions too); older measurements fall
    # back to wall time.
    def timing(path: str, cpu_key: str, wall_key: str) -> tuple[str, tuple] | None:
        if (
            _get(before, f"{path}.{cpu_key}") is not None
            and _get(after, f"{path}.{cpu_key}") is not None
        ):
            return "cpu", both(f"{path}.{cpu_key}")
        pair = both(f"{path}.{wall_key}", f"{path} wall time")
        return ("wall", pair) if pair else None

    found = timing("import_time", "cpu_us", "cumulative_us")
    if found and found[1][1] > found[1][0] * IMPORT_LIMIT:
        kind, (b, a) = found
        out.append(f"import time ({kind}) {b} -> {a} us exceeds +15%: needs -X importtime review")

    for key in ("suite", "suite_full"):
        found = timing(key, "cpu_s", "wall_s")
        if found and found[1][1] - found[1][0] > found[1][0] * SUITE_LIMIT:
            kind, (b, a) = found
            out.append(f"{key} {kind} time {b}s -> {a}s is more than 5% slower")
        names = _get(after, f"{key}.failed_tests") or []
        rerun_ok = set(_get(after, f"{key}.rerun_passed") or [])
        failed = raw_failed = _get(after, f"{key}.failed")
        if failed and names and rerun_ok:  # failures that passed alone are not gated
            names = [n for n in names if n not in rerun_ok]
            failed = len(names)
        rc = _get(after, f"{key}.returncode")
        if rc and not raw_failed:
            tail = (_get(after, f"{key}.output_tail") or "").strip().splitlines()
            out.append(
                f"{key} exited {rc} without a failed test"
                + (f": {' | '.join(tail[-3:])}" if tail else "")
            )
        if failed:
            out.append(
                f"{key} has {failed} failed in after"
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
    r = sub.add_parser("recheck", help="A/B re-measure a suite timing violation")
    r.add_argument("before")
    r.add_argument("after")
    r.add_argument("--key", required=True, choices=("suite", "suite_full"))
    args = parser.parse_args(argv)

    if args.cmd == "measure":
        result = measure(args.full, args.skip_test)
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.out}")
        return 0
    before = json.loads(Path(args.before).read_text())
    after = json.loads(Path(args.after).read_text())
    if args.cmd == "recheck":
        task, rounds = ("test", 2) if args.key == "suite" else ("test:full", 1)
        ok, msg = recheck(before["engine_sha"], task, rounds)
        print(f"RECHECK {'ok' if ok else 'slower'}: {msg}")
        return 0 if ok else 1
    violations = compare(before, after, args.step)
    for v in violations:
        print(f"VIOLATION: {v}")
    if not violations:
        print(f"baselines {args.step}: ok")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
