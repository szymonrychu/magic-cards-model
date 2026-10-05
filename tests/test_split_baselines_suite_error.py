"""A suite run that errored without running tests is named, with the reason.

Dry run r11: the disposable worktree's venv lost its dist-info METADATA files to the
macOS /tmp cleaner mid-run, so `mise run test` exited 4 in 0.13 s on
`pytest: error: unrecognized arguments: -n`. The measure json kept only the return code,
compare saw no failed tests and a much faster suite, and the gate log gave no reason.
"""

from __future__ import annotations

import subprocess

from scripts.split import baselines as B


def _suite(**extra) -> dict:
    return {"wall_s": 100.0, "cpu_s": 90.0, "passed": 10, "failed": 0, "xfailed": 1, **extra}


def _base() -> dict:
    return {
        "engine_sha": "abc",
        "import_time": {"cumulative_us": 1000, "self_us": {}},
        "suite": _suite(returncode=0),
        "suite_full": _suite(returncode=0),
        "test_count": 30,
        "sweep_sha256": "s",
        "goldens_sha256": "g",
        "fingerprint": {"sha256": "f", "results_sha256": "r", "chains": {}},
    }


def test_a_suite_that_exited_nonzero_without_failures_is_a_violation_with_its_reason():
    after = _base()
    after["suite"] = {
        "wall_s": 0.13,
        "cpu_s": 0.15,
        "passed": 0,
        "failed": 0,
        "xfailed": 0,
        "returncode": 4,
        "output_tail": "ERROR: usage: pytest\npytest: error: unrecognized arguments: -n",
    }
    out = B.compare(_base(), after, "F1")
    assert len(out) == 1, out
    assert "suite exited 4" in out[0]
    assert "unrecognized arguments: -n" in out[0]


def test_a_clean_suite_or_one_without_a_return_code_is_not_a_violation():
    assert B.compare(_base(), _base(), "F1") == []
    no_rc = _base()
    del no_rc["suite"]["returncode"]
    assert B.compare(_base(), no_rc, "F1") == []


def test_measure_suite_keeps_the_output_tail_only_when_the_suite_fails():
    def run(rc, out, err):
        def fake(cmd, check=True, cwd=None):
            return subprocess.CompletedProcess(cmd, rc, out, err), 1.0, 0.5

        return fake

    bad = B.measure_suite("test", run=run(4, "", "x\n" * 40 + "pytest: error: bad -n\n"))
    assert bad["returncode"] == 4
    assert bad["output_tail"].endswith("pytest: error: bad -n")
    assert len(bad["output_tail"].splitlines()) == B.OUTPUT_TAIL_LINES

    good = B.measure_suite("test", run=run(0, "== 3 passed in 1.0s ==\n", ""))
    assert good["passed"] == 3 and "output_tail" not in good
