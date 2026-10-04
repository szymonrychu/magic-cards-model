"""Tests for scripts/split/baselines.py (compare rules and hashing helpers).

Never runs the real suite or sweep.
"""

from __future__ import annotations

import copy
import json
import pathlib

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
