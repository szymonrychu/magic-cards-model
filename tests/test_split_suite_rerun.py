"""A suite failure that passes when rerun alone is reported, not gated.

Dry run r12, full-F4e: `mise run test` failed one test,
tests/test_card_support.py::test_the_full_pool_classifies_within_budget (a CPU budget,
a known load flake on unmodified main, MEMORY 2026-09-27), while `mise run test:full`
over the same tree minutes later passed it. measure_suite reruns the failed node ids
once on their own; a failure that passes there is a rerun note, one that fails again
still fails the gate.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from scripts.split import baselines as B

from tests.test_split_gates import GATES, GIT_ENV, git, sh

FLAKE = "tests/test_card_support.py::test_the_full_pool_classifies_within_budget"
REAL = "tests/test_x.py::test_real"


def _fake(results: list[tuple[int, str]], calls: list):
    def run(cmd, check=True, cwd=None):
        calls.append(cmd)
        rc, out = results[len(calls) - 1]
        return subprocess.CompletedProcess(cmd, rc, out, ""), 1.0, 0.5

    return run


def _summary(*failed: str, passed: int = 5) -> str:
    lines = [f"FAILED {f}" for f in failed]
    return "\n".join([*lines, f"== {len(failed)} failed, {passed} passed in 1.0s =="]) + "\n"


def test_a_failure_that_passes_alone_is_recorded_as_rerun_passed():
    calls: list = []
    run = _fake([(1, _summary(FLAKE)), (0, "== 1 passed in 1.0s ==\n")], calls)
    s = B.measure_suite("test", run=run)
    assert s["failed_tests"] == [FLAKE]
    assert s["rerun_passed"] == [FLAKE]
    assert calls[1][-1] == FLAKE and "pytest" in calls[1]


def test_a_failure_that_fails_again_is_not_rerun_passed():
    calls: list = []
    run = _fake([(1, _summary(FLAKE, REAL)), (1, _summary(REAL, passed=1))], calls)
    s = B.measure_suite("test", run=run)
    assert s["rerun_passed"] == [FLAKE]


def test_no_rerun_when_nothing_failed_or_too_many_failed():
    calls: list = []
    B.measure_suite("test", run=_fake([(0, "== 5 passed in 1.0s ==\n")], calls))
    assert len(calls) == 1
    many = [f"tests/t.py::test_{i}" for i in range(B.RERUN_MAX + 1)]
    calls = []
    s = B.measure_suite("test", run=_fake([(1, _summary(*many))], calls))
    assert len(calls) == 1 and s.get("rerun_passed", []) == []


def _base() -> dict:
    suite = {"wall_s": 100.0, "cpu_s": 90.0, "passed": 10, "failed": 0, "returncode": 0}
    return {
        "engine_sha": "abc",
        "import_time": {"cumulative_us": 1000, "self_us": {}},
        "suite": dict(suite),
        "suite_full": dict(suite),
        "test_count": 30,
        "sweep_sha256": "s",
        "goldens_sha256": "g",
        "fingerprint": {"sha256": "f", "results_sha256": "r", "chains": {}},
    }


def test_compare_drops_failures_that_passed_on_rerun_and_keeps_the_rest():
    after = _base()
    after["suite"].update(returncode=1, failed=1, failed_tests=[FLAKE], rerun_passed=[FLAKE])
    assert B.compare(_base(), after, "F1") == []
    after["suite"].update(failed=2, failed_tests=[FLAKE, REAL])
    out = B.compare(_base(), after, "F1")
    assert len(out) == 1 and REAL in out[0] and FLAKE not in out[0]


# ----- gates.sh: the suite check honours rerun_passed -----

STUB = """\
import json, os, sys

args = sys.argv[1:]
if args[0] == "measure":
    out = args[args.index("--out") + 1]
    open(out, "w").write(json.dumps({"suite": json.loads(os.environ["STUB_SUITE"])}))
"""


@pytest.fixture
def gate(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "gates.sh").write_text(GATES.read_text())
    (tools / "baselines.py").write_text(STUB)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "mise").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "mise").chmod(0o755)
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    for name in ("test_module_hygiene", "test_split_surface"):
        (repo / "tests" / f"{name}.py").write_text("def test_ok():\n    pass\n")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "x"],
        cwd=repo,
        env={**os.environ, **GIT_ENV},
        check=True,
    )
    (tmp_path / "before.json").write_text('{"engine_sha": "cafe123"}')

    def run(suite: dict):
        env = {
            "SPLIT_PY": sys.executable,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "STUB_SUITE": json.dumps(suite),
        }
        args = ("cheap", "--baseline", str(tmp_path / "before.json"), "--step", "F1")
        return sh(tools / "gates.sh", *args, cwd=repo, env=env)

    return run


def _line(res, prefix: str) -> str:
    return next(ln for ln in res.stdout.splitlines() if ln.startswith(prefix))


def test_gate_passes_a_suite_whose_only_failures_passed_on_rerun_and_says_so(gate):
    suite = {"wall_s": 1.0, "returncode": 1, "failed": 1}
    res = gate({**suite, "failed_tests": [FLAKE], "rerun_passed": [FLAKE]})
    assert _line(res, "PASS mise run test")
    assert f"RERUN passed alone: {FLAKE}" in res.stdout
    res = gate({**suite, "failed": 2, "failed_tests": [FLAKE, REAL], "rerun_passed": [FLAKE]})
    assert _line(res, "FAIL mise run test")
