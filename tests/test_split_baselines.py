"""Tests for scripts/split/baselines.py (compare rules and hashing helpers).

Never runs the real suite or sweep.
"""

from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys

import pytest
from scripts.split import baselines as B

FIX = pathlib.Path(__file__).parent / "fixtures" / "split" / "baselines"


def _fp(results_a="x", chain_a=("p", "q")):
    return {
        "sha256": "fp-full",
        "results_sha256": "fp-results",
        "chains": {"_ability_effect_or_notice": sorted(chain_a)},
    }


def _base() -> dict:
    return {
        "engine_sha": "abc",
        "import_time": {"cumulative_us": 1000, "self_us": {}},
        "suite": {"wall_s": 100.0, "passed": 10, "failed": 0, "xfailed": 1},
        "suite_full": {"wall_s": 1000.0, "passed": 20, "failed": 0, "xfailed": 1},
        "test_count": 30,
        "sweep_sha256": "s",
        "goldens_sha256": "g",
        "fingerprint": _fp(),
    }


def _violations(before, after, step):
    return B.compare(before, after, step)


def test_identical_passes_every_step():
    for step in ["F1", "F2", "F3", "F4a", "F4b", "F4c", "F4d", "F4e", "F4"]:
        assert _violations(_base(), _base(), step) == []


@pytest.mark.parametrize(
    ("field", "word"),
    [("sweep_sha256", "sweep"), ("goldens_sha256", "goldens"), ("test_count", "test count")],
)
def test_identity_fields_fail(field, word):
    after = _base()
    after[field] = "changed" if isinstance(after[field], str) else after[field] + 1
    out = _violations(_base(), after, "F1")
    assert len(out) == 1
    assert word in out[0]


def test_fingerprint_full_identity_for_f1_f3_f4_not_f2():
    after = _base()
    after["fingerprint"]["sha256"] = "other"
    for step in ["F1", "F3", "F4", "F4c"]:
        out = _violations(_base(), after, step)
        assert len(out) == 1 and "fingerprint" in out[0]
    assert _violations(_base(), after, "F2") == []


def test_f2_results_hash_must_match():
    after = _base()
    after["fingerprint"]["results_sha256"] = "other"
    out = _violations(_base(), after, "F2")
    assert len(out) == 1 and "results" in out[0]


def test_f2_chain_set_equal_order_may_change_but_set_may_not():
    before, after = _base(), _base()
    after["fingerprint"]["chains"]["_ability_effect_or_notice"] = ["q", "p"]
    assert _violations(before, after, "F2") == []
    after["fingerprint"]["chains"]["_ability_effect_or_notice"] = ["p", "z"]
    out = _violations(before, after, "F2")
    assert len(out) == 1
    assert "_ability_effect_or_notice" in out[0]
    assert "z" in out[0] and "q" in out[0]


def test_f2_chain_ladder_missing_or_added_named():
    after = _base()
    after["fingerprint"]["chains"]["_new"] = ["a"]
    out = _violations(_base(), after, "F2")
    assert len(out) == 1 and "_new" in out[0]


def test_import_time_limit_is_15_percent():
    after = _base()
    after["import_time"]["cumulative_us"] = 1150
    assert _violations(_base(), after, "F1") == []
    after["import_time"]["cumulative_us"] = 1151
    out = _violations(_base(), after, "F1")
    assert len(out) == 1 and "-X importtime" in out[0]


def test_suite_wall_within_5_percent():
    after = _base()
    after["suite"]["wall_s"] = 105.0
    assert _violations(_base(), after, "F1") == []
    after["suite"]["wall_s"] = 105.5
    out = _violations(_base(), after, "F1")
    assert len(out) == 1 and "suite" in out[0]
    after = _base()
    after["suite_full"]["wall_s"] = 1100.0
    out = _violations(_base(), after, "F1")
    assert len(out) == 1 and "full" in out[0]


def test_suite_counts_must_match_is_not_required_but_failures_reported():
    after = _base()
    after["suite"]["failed"] = 2
    out = _violations(_base(), after, "F1")
    assert len(out) == 1 and "failed" in out[0]


def test_missing_fields_reported_not_measured():
    after = _base()
    del after["suite_full"]
    before = _base()
    del before["sweep_sha256"]
    out = _violations(before, after, "F1")
    assert any("not measured" in v and "suite_full" in v for v in out)
    assert any("not measured" in v and "sweep" in v for v in out)


def test_unknown_step_rejected():
    with pytest.raises(ValueError):
        B.compare(_base(), _base(), "F9")


def test_cli_compare_exit_codes(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(_base()))
    b.write_text(json.dumps(_base()))
    assert B.main(["compare", str(a), str(b), "--step", "F1"]) == 0
    bad = copy.deepcopy(_base())
    bad["test_count"] = 1
    b.write_text(json.dumps(bad))
    assert B.main(["compare", str(a), str(b), "--step", "F1"]) == 1


def test_hash_tree_path_order_independent_and_byte_sensitive(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    for root, order in ((one, ["b/x.txt", "a.txt"]), (two, ["a.txt", "b/x.txt"])):
        for rel in order:
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(rel.encode())
    assert B.hash_tree(one) == B.hash_tree(two)
    (two / "a.txt").write_bytes(b"A.txt")
    assert B.hash_tree(one) != B.hash_tree(two)


def test_hash_tree_sensitive_to_path_names(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    (one / "a").write_bytes(b"data")
    (two / "b").write_bytes(b"data")
    assert B.hash_tree(one) != B.hash_tree(two)


def test_hash_text_is_sha256_hex():
    assert B.hash_text("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_fingerprint_summary_separates_results_and_chains():
    fp = {
        "L1": {"chain": ["b", "a"], "results": {"plain": {"i": "a"}}},
        "L2": {"chain": ["c"], "results": {}},
    }
    s = B.fingerprint_summary(json.dumps(fp))
    assert s["chains"] == {"L1": ["a", "b"], "L2": ["c"]}
    reordered = {
        "L1": {"chain": ["a", "b"], "results": {"plain": {"i": "a"}}},
        "L2": {"chain": ["c"], "results": {}},
    }
    s2 = B.fingerprint_summary(json.dumps(reordered, indent=4))
    assert s2["results_sha256"] == s["results_sha256"]
    assert s2["chains"] == s["chains"]
    reordered["L1"]["results"]["plain"]["i"] = "b"
    assert B.fingerprint_summary(json.dumps(reordered))["results_sha256"] != s["results_sha256"]


def test_parse_importtime():
    text = (FIX / "importtime_stderr.txt").read_text()
    cum, selfs = B.parse_importtime(text)
    assert cum == 10000
    assert selfs == {
        "machines.effects": 300,
        "models.game": 200,
        "machines.layers": 50,
    }


def test_parse_pytest_summary():
    text = (FIX / "pytest_summary.txt").read_text()
    assert B.parse_pytest_summary(text) == {"passed": 1200, "failed": 2, "xfailed": 5}
    assert B.parse_pytest_summary("=== 3 passed in 1s ===") == {
        "passed": 3,
        "failed": 0,
        "xfailed": 0,
    }


def test_parse_collect_count():
    assert B.parse_collect_count("a::b\n\n4321 tests collected in 2.0s\n") == 4321
    assert B.parse_collect_count("1 test collected in 0.1s") == 1


def test_tests_the_split_adds_do_not_count_as_a_test_count_change():
    """F2 adds tests/test_dispatch_order.py by design; the collected count the gate holds
    identical is the count without the split's own tests (dry run: 27410 -> 27411)."""
    after = _base()
    after["test_count"] = 31
    after["split_test_count"] = 1
    for step in ["F2", "F3", "F4e"]:
        assert _violations(_base(), after, step) == []
    after["test_count"] = 32
    out = _violations(_base(), after, "F3")
    assert len(out) == 1 and "test count" in out[0]


def test_parse_split_test_count():
    out = (
        "tests/test_dispatch_order.py::test_no_unordered_double_match\n"
        "tests/test_x.py::test_y\n"
        "tests/test_dispatch_order.py::test_z[a]\n\n"
        "3 tests collected in 1.0s\n"
    )
    assert B.parse_split_test_count(out) == 2
    assert B.parse_split_test_count("tests/test_x.py::t\n\n1 test collected in 0.1s") == 0


def test_from_f3_on_the_reordered_fingerprint_passes_as_the_committed_f2_baseline():
    """F2 reorders the chains and commits the regenerated fingerprint baseline; F3/F4 are
    held to it (the measured fingerprint equals the committed one) plus the pre-split
    results and chain sets, not to the pre-split chain order (dry run: F3 failed)."""
    after = _base()
    after["fingerprint"]["sha256"] = "reordered"
    after["fingerprint"]["matches_committed"] = True
    for step in ["F2", "F3", "F4", "F4a", "F4e"]:
        assert _violations(_base(), after, step) == [], step
    assert len(_violations(_base(), after, "F1")) == 1
    changed = copy.deepcopy(after)
    changed["fingerprint"]["results_sha256"] = "other"
    out = _violations(_base(), changed, "F3")
    assert len(out) == 1 and "results" in out[0]
    moved = copy.deepcopy(after)
    moved["fingerprint"]["chains"]["_ability_effect_or_notice"] = ["p", "z"]
    out = _violations(_base(), moved, "F4c")
    assert len(out) == 1 and "chain set changed" in out[0]
    stale = copy.deepcopy(after)
    stale["fingerprint"]["matches_committed"] = False
    out = _violations(_base(), stale, "F3")
    assert len(out) == 1 and "committed" in out[0]


def test_a_faster_suite_is_not_a_violation():
    """The suite gate guards against a slowdown; run-to-run noise made a 5.5% faster
    `mise run test` fail the dry run's F1 cheap gate."""
    after = _base()
    after["suite"]["wall_s"] = 80.0
    after["suite_full"]["wall_s"] = 800.0
    assert _violations(_base(), after, "F1") == []


def test_parse_failed_tests_names_each_failure():
    """A gate that reports "1 failed" names the test (the dry run's port gate lost it)."""
    out = (
        "....F..\n=== short test summary info ===\n"
        "FAILED tests/test_a.py::test_one - AssertionError: x\n"
        "ERROR tests/test_b.py::test_two\n"
        "1 failed, 6 passed, 1 error in 3.0s\n"
    )
    assert B.parse_failed_tests(out) == ["tests/test_a.py::test_one", "tests/test_b.py::test_two"]
    assert B.parse_failed_tests("3 passed in 1s") == []


def _with_cpu() -> dict:
    data = _base()
    data["import_time"]["cpu_us"] = 2000
    data["suite"]["cpu_s"] = 500.0
    data["suite_full"]["cpu_s"] = 5000.0
    return data


def test_timing_gates_use_cpu_time_when_both_sides_have_it():
    """The dry run's r2 failed F3's import and suite gates because other sessions' suites
    pushed the machine load to 36 on 12 cores: wall time doubled, CPU time did not. With
    CPU time on both sides the gates hold CPU time to the limits, not wall time."""
    after = _with_cpu()
    after["import_time"]["cumulative_us"] = 3000
    after["suite"]["wall_s"] = 250.0
    after["suite_full"]["wall_s"] = 2500.0
    assert _violations(_with_cpu(), after, "F3") == []


def test_cpu_import_time_limit_is_15_percent():
    after = _with_cpu()
    after["import_time"]["cpu_us"] = 2300
    assert _violations(_with_cpu(), after, "F3") == []
    after["import_time"]["cpu_us"] = 2301
    out = _violations(_with_cpu(), after, "F3")
    assert len(out) == 1 and "import" in out[0] and "cpu" in out[0]


def test_cpu_suite_limit_is_5_percent_and_one_sided():
    after = _with_cpu()
    after["suite"]["cpu_s"] = 525.0
    after["suite_full"]["cpu_s"] = 4000.0
    assert _violations(_with_cpu(), after, "F3") == []
    after["suite"]["cpu_s"] = 525.5
    out = _violations(_with_cpu(), after, "F3")
    assert len(out) == 1 and "suite" in out[0] and "cpu" in out[0]
    after = _with_cpu()
    after["suite_full"]["cpu_s"] = 5300.0
    out = _violations(_with_cpu(), after, "F3")
    assert len(out) == 1 and "suite_full" in out[0] and "cpu" in out[0]


def test_wall_time_still_gates_when_one_side_has_no_cpu_time():
    after = _with_cpu()
    after["suite"]["wall_s"] = 106.0
    assert len(_violations(_base(), after, "F1")) == 1
    after["import_time"]["cumulative_us"] = 1200
    assert len(_violations(_base(), after, "F1")) == 2


def test_timed_run_records_child_cpu_time():
    proc, wall, cpu = B.timed_run(
        [sys.executable, "-c", "sum(i * i for i in range(3_000_000))"], check=True
    )
    assert proc.returncode == 0
    assert 0.05 < cpu <= wall + 0.5


def test_import_cpu_time_is_the_least_disturbed_run():
    """r4 measured F1's import CPU time +14.6% (r2: +3%) with the machine at load 8-17:
    a median of 5 still moves with the load, the minimum is the run nothing disturbed."""
    summary = B.import_summary(
        cums=[400, 500, 410], cpus=[0.45, 0.40, 0.52], selfs={"machines.effects": [3, 1, 2]}
    )
    assert summary["cpu_us"] == 400000
    assert summary["cumulative_us"] == 410
    assert summary["self_us"] == {"machines.effects": 2}
    assert summary["runs"] == 3


def test_recheck_measures_the_pre_split_commit_and_this_tree_back_to_back(tmp_path):
    """The A/B recheck behind a timing violation: the before side runs in a throwaway
    worktree of the baseline's engine sha, alternating with this tree; the slowest-free
    (minimum) CPU of each side is compared against the 5% limit, and the worktree is gone after."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def run(*a):
        return subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)

    run("init", "-q")
    run(
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "pre",
    )
    pre = run("rev-parse", "HEAD").stdout.decode().strip()
    (repo / "marker").write_text("after")
    calls = []

    def measure(cwd, task):
        side = "after" if (pathlib.Path(cwd) / "marker").exists() else "before"
        calls.append((side, task))
        return {"before": [100.0, 98.0], "after": [103.0, 102.0]}[side][
            len([c for c in calls if c[0] == side]) - 1
        ]

    ok, msg = B.recheck(pre, "test", rounds=2, measure=measure, prepare=lambda wt: None, repo=repo)
    assert calls == [("before", "test"), ("after", "test")] * 2
    assert ok and "98.0" in msg and "102.0" in msg
    assert run("worktree", "list").stdout.decode().count("\n") == 1

    calls.clear()

    def slow(cwd, task):
        return measure(cwd, task) * (1.2 if (pathlib.Path(cwd) / "marker").exists() else 1)

    ok, _ = B.recheck(pre, "test", rounds=2, measure=slow, prepare=lambda wt: None, repo=repo)
    assert not ok
