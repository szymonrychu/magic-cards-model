"""Tests for `scripts/regression_guard.py`.

Every test that exercises the protected-test report or the card-status
ratchet builds a small, real, throwaway git repository (`tmp_path`) rather
than mocking git or the engine - the guard's whole job is reading real git
history and (for the ratchet) real engine code in real worktrees, so a faked
git plumbing layer would prove nothing about whether it actually works.

The ratchet tests use a tiny hand-written fake `magic_cards_model` package
(plain dataclasses, no pydantic) rather than the real engine: the ratchet's
own logic (worktree isolation, subprocess classification, the regression
rules) does not depend on any real card behaviour, and driving it against
the real ~2600-printing pool would make these tests as slow as the sweep
itself. The guard's own self-run against the real engine (its own landing
gate) is what proves it against the real pool.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts import regression_guard as rg

SCRIPT = Path(__file__).parent.parent / "scripts" / "regression_guard.py"


# ---------------------------------------------------------------------------
# git repo fixture helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    d = tmp_path / "repo"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "test@example.com")
    _git(d, "config", "user.name", "Test")
    _git(d, "commit", "--allow-empty", "-q", "-m", "root")
    return d


def _write(repo: Path, path: str, content: str) -> None:
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _delete(repo: Path, path: str) -> None:
    (repo / path).unlink()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


# ---------------------------------------------------------------------------
# Pure parsing helpers
# ---------------------------------------------------------------------------


def test_parse_test_functions_finds_bare_and_method_tests():
    source = (
        "def test_top():\n"
        "    assert 1\n\n"
        "class TestFoo:\n"
        "    def test_a(self):\n"
        "        assert 1\n\n"
        "    def helper(self):\n"
        "        pass\n"
    )
    functions = rg.parse_test_functions(source)
    assert set(functions) == {"test_top", "TestFoo.test_a"}


def test_module_constants_ignores_private_names():
    source = "PUBLIC = 1\n_PRIVATE = 2\n"
    assert rg.module_constants(source) == {"PUBLIC": "1"}


# ---------------------------------------------------------------------------
# Protected-test report: assert / raises changes
# ---------------------------------------------------------------------------


def test_deleted_test_function_flagged(repo: Path):
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 1\n")
    base = _commit(repo, "base")
    _write(repo, "tests/test_foo.py", "# nothing here\n")
    head = _commit(repo, "delete the test")

    findings = rg.protected_test_report(repo, base, head)

    assert len(findings) == 1
    assert findings[0]["kind"] == "deleted_test"
    assert findings[0]["test"] == "test_bolt"
    assert findings[0]["file"] == "tests/test_foo.py"


def test_deleted_test_file_flags_every_test_it_had(repo: Path):
    _write(
        repo,
        "tests/test_foo.py",
        "def test_bolt():\n    assert 1 == 1\n\ndef test_shock():\n    assert 2 == 2\n",
    )
    base = _commit(repo, "base")
    _delete(repo, "tests/test_foo.py")
    head = _commit(repo, "delete file")

    findings = rg.protected_test_report(repo, base, head)

    assert {f["test"] for f in findings} == {"test_bolt", "test_shock"}
    assert {f["kind"] for f in findings} == {"deleted_test"}


def test_changed_assert_flagged_with_before_after(repo: Path):
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 1\n")
    base = _commit(repo, "base")
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 2\n")
    head = _commit(repo, "weaken the assertion")

    findings = rg.protected_test_report(repo, base, head)

    assert len(findings) == 1
    finding = findings[0]
    assert finding["kind"] == "assert_changed"
    assert finding["before"] == "assert 1 == 1"
    assert finding["after"] == "assert 1 == 2"


def test_removed_assert_flagged_with_after_none(repo: Path):
    _write(
        repo,
        "tests/test_foo.py",
        "def test_bolt():\n    assert 1 == 1\n    assert 2 == 2\n",
    )
    base = _commit(repo, "base")
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 1\n")
    head = _commit(repo, "drop the second assert")

    findings = rg.protected_test_report(repo, base, head)

    assert len(findings) == 1
    assert findings[0]["kind"] == "assert_changed"
    assert findings[0]["before"] == "assert 2 == 2"
    assert findings[0]["after"] is None


def test_changed_pytest_raises_flagged(repo: Path):
    _write(
        repo,
        "tests/test_foo.py",
        "import pytest\n\n"
        "def test_bolt():\n"
        "    with pytest.raises(ValueError):\n"
        "        raise ValueError\n",
    )
    base = _commit(repo, "base")
    _write(
        repo,
        "tests/test_foo.py",
        "import pytest\n\n"
        "def test_bolt():\n"
        "    with pytest.raises(TypeError):\n"
        "        raise ValueError\n",
    )
    head = _commit(repo, "loosen the expected exception")

    findings = rg.protected_test_report(repo, base, head)

    assert len(findings) == 1
    assert findings[0]["kind"] == "assert_changed"
    assert "ValueError" in findings[0]["before"]
    assert "TypeError" in findings[0]["after"]


def test_xfail_marker_added_to_existing_test_flagged(repo: Path):
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 1\n")
    base = _commit(repo, "base")
    _write(
        repo,
        "tests/test_foo.py",
        "import pytest\n\n@pytest.mark.xfail(reason='wip')\ndef test_bolt():\n    assert 1 == 1\n",
    )
    head = _commit(repo, "mark it xfail")

    findings = rg.protected_test_report(repo, base, head)

    kinds = {f["kind"] for f in findings}
    assert "marker_added" in kinds


def test_skip_marker_added_to_existing_test_flagged(repo: Path):
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 1\n")
    base = _commit(repo, "base")
    _write(
        repo,
        "tests/test_foo.py",
        "import pytest\n\n@pytest.mark.skip(reason='flaky')\ndef test_bolt():\n    assert 1 == 1\n",
    )
    head = _commit(repo, "skip it")

    findings = rg.protected_test_report(repo, base, head)

    kinds = {f["kind"] for f in findings}
    assert "marker_added" in kinds


def test_expectation_constant_changed_when_referenced_flagged(repo: Path):
    _write(
        repo,
        "tests/test_foo.py",
        "EXPECTED = {'a', 'b'}\n\ndef test_bolt():\n    assert EXPECTED == {'a', 'b'}\n",
    )
    base = _commit(repo, "base")
    _write(
        repo,
        "tests/test_foo.py",
        "EXPECTED = {'a'}\n\ndef test_bolt():\n    assert EXPECTED == {'a', 'b'}\n",
    )
    head = _commit(repo, "narrow the expectation")

    findings = rg.protected_test_report(repo, base, head)

    matches = [
        f
        for f in findings
        if f["kind"] == "expectation_constant_changed" and f["test"] == "EXPECTED"
    ]
    assert len(matches) == 1


def test_unreferenced_constant_change_not_flagged(repo: Path):
    _write(
        repo,
        "tests/test_foo.py",
        "UNUSED = 1\n\ndef test_bolt():\n    assert 1 == 1\n",
    )
    base = _commit(repo, "base")
    _write(
        repo,
        "tests/test_foo.py",
        "UNUSED = 2\n\ndef test_bolt():\n    assert 1 == 1\n",
    )
    head = _commit(repo, "change an unused constant")

    assert rg.protected_test_report(repo, base, head) == []


# ---------------------------------------------------------------------------
# Protected-test report: purely additive changes are never flagged
# ---------------------------------------------------------------------------


def test_added_test_function_in_existing_file_not_flagged(repo: Path):
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 1\n")
    base = _commit(repo, "base")
    _write(
        repo,
        "tests/test_foo.py",
        "def test_bolt():\n    assert 1 == 1\n\ndef test_shock():\n    assert 2 == 2\n",
    )
    head = _commit(repo, "add a new test")

    assert rg.protected_test_report(repo, base, head) == []


def test_purely_added_file_not_flagged(repo: Path):
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 1\n")
    base = _commit(repo, "base")
    _write(repo, "tests/test_new.py", "def test_shock():\n    assert 1 == 1\n")
    head = _commit(repo, "add a new file")

    assert rg.protected_test_report(repo, base, head) == []


# ---------------------------------------------------------------------------
# Protected-test report: tests/golden/
# ---------------------------------------------------------------------------


def test_golden_file_changed_flagged(repo: Path):
    _write(repo, "tests/golden/bolt/triggered-1.json", json.dumps({"a": 1}))
    base = _commit(repo, "base")
    _write(repo, "tests/golden/bolt/triggered-1.json", json.dumps({"a": 2}))
    head = _commit(repo, "change the golden")

    findings = rg.protected_test_report(repo, base, head)

    assert len(findings) == 1
    assert findings[0]["kind"] == "golden_changed"
    assert findings[0]["file"] == "tests/golden/bolt/triggered-1.json"


def test_golden_file_deleted_flagged(repo: Path):
    _write(repo, "tests/golden/bolt/triggered-1.json", json.dumps({"a": 1}))
    base = _commit(repo, "base")
    _delete(repo, "tests/golden/bolt/triggered-1.json")
    head = _commit(repo, "delete the golden")

    findings = rg.protected_test_report(repo, base, head)

    assert len(findings) == 1
    assert findings[0]["kind"] == "golden_changed"
    assert findings[0]["after"] is None


def test_golden_file_added_not_flagged(repo: Path):
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 1\n")
    base = _commit(repo, "base")
    _write(repo, "tests/golden/bolt/triggered-1.json", json.dumps({"a": 1}))
    head = _commit(repo, "add a golden")

    assert rg.protected_test_report(repo, base, head) == []


# ---------------------------------------------------------------------------
# CLI: protected-test report
# ---------------------------------------------------------------------------


def test_cli_nonzero_exit_and_json_on_finding(repo: Path):
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 1\n")
    base = _commit(repo, "base")
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 2\n")
    head = _commit(repo, "weaken it")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--base", base, "--head", head],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["protected_test_findings"]) == 1


def test_cli_zero_exit_when_clean(repo: Path):
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 1\n")
    base = _commit(repo, "base")
    _write(repo, "tests/test_new.py", "def test_shock():\n    assert 1 == 1\n")
    head = _commit(repo, "purely additive")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--base", base, "--head", head],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["protected_test_findings"] == []


# ---------------------------------------------------------------------------
# Card-status ratchet: pure decision logic
# ---------------------------------------------------------------------------


def test_ratchet_offenders_flags_status_regression():
    stems = {"bolt": "Lightning Bolt"}
    idx = rg.TestedIndex(quoted_names=frozenset({"Lightning Bolt"}), golden_slugs=frozenset())

    offenders = rg.ratchet_offenders(stems, {"bolt": "handled"}, {"bolt": "silent"}, idx, idx)

    assert len(offenders) == 1
    assert "status regressed: handled -> silent" in offenders[0]["reasons"]


def test_ratchet_offenders_flags_untested_regression():
    stems = {"bolt": "Lightning Bolt"}
    status = {"bolt": "handled"}
    base_idx = rg.TestedIndex(quoted_names=frozenset({"Lightning Bolt"}), golden_slugs=frozenset())
    head_idx = rg.TestedIndex(quoted_names=frozenset(), golden_slugs=frozenset())

    offenders = rg.ratchet_offenders(stems, status, status, base_idx, head_idx)

    assert len(offenders) == 1
    assert "tested at base, untested at head" in offenders[0]["reasons"]


def test_ratchet_offenders_clean_on_improvement_or_no_change():
    stems = {"bolt": "Lightning Bolt", "fog": "Fog"}
    idx = rg.TestedIndex(quoted_names=frozenset(), golden_slugs=frozenset())

    offenders = rg.ratchet_offenders(
        stems,
        {"bolt": "notice", "fog": "handled"},
        {"bolt": "handled", "fog": "handled"},
        idx,
        idx,
    )

    assert offenders == []


def test_ratchet_offenders_flags_removed_printing_as_worst():
    stems = {"bolt": "Lightning Bolt"}
    idx = rg.TestedIndex(quoted_names=frozenset(), golden_slugs=frozenset())

    offenders = rg.ratchet_offenders(stems, {"bolt": "handled"}, {}, idx, idx)

    assert len(offenders) == 1
    assert offenders[0]["head_status"] == "removed"


# ---------------------------------------------------------------------------
# Card-status ratchet: end to end, against a small fake engine
# ---------------------------------------------------------------------------


def _write_fake_engine(
    repo: Path, *, bolt_status: str = "handled", fog_status: str = "notice", quote_bolt: bool = True
) -> None:
    """A minimal stand-in for `magic_cards_model` (plain dataclasses, no
    pydantic): just enough surface - `models.card.Card.model_validate` and
    `support.card_support` - for `regression_guard.py`'s classify-worker
    subprocess to import and call, with the "status" driven directly by a
    `_status` field in the fixture printing rather than by real oracle-text
    parsing."""
    _write(repo, "src/magic_cards_model/__init__.py", "")
    _write(repo, "src/magic_cards_model/models/__init__.py", "")
    _write(
        repo,
        "src/magic_cards_model/models/card.py",
        "class Card:\n"
        "    def __init__(self, data):\n"
        "        self.data = data\n"
        "        self.name = data.get('name')\n\n"
        "    @classmethod\n"
        "    def model_validate(cls, data):\n"
        "        return cls(data)\n",
    )
    _write(
        repo,
        "src/magic_cards_model/support.py",
        "from dataclasses import dataclass\n\n\n"
        "@dataclass\n"
        "class Support:\n"
        "    status: str\n\n\n"
        "def card_support(card):\n"
        "    return Support(status=card.data.get('_status', 'handled'))\n",
    )
    _write(
        repo,
        "src/magic_cards_model/data/printings/bolt.json",
        json.dumps({"name": "Lightning Bolt", "_status": bolt_status}),
    )
    _write(
        repo,
        "src/magic_cards_model/data/printings/fog.json",
        json.dumps({"name": "Fog", "_status": fog_status}),
    )
    quoted = '"Lightning Bolt"' if quote_bolt else '"nothing"'
    _write(repo, "tests/test_cards.py", f"def test_bolt():\n    assert {quoted} == {quoted}\n")


def test_ratchet_engine_only_guard(repo: Path):
    _write(repo, "tests/test_foo.py", "def test_bolt():\n    assert 1 == 1\n")
    base = _commit(repo, "base")

    with pytest.raises(rg.RegressionGuardError):
        rg.run_ratchet(repo, base, base, workers=2)


def test_ratchet_end_to_end_status_regression(repo: Path):
    _write_fake_engine(repo, bolt_status="handled")
    base = _commit(repo, "base")
    _write_fake_engine(repo, bolt_status="silent")
    head = _commit(repo, "regress Lightning Bolt")

    result = rg.run_ratchet(repo, base, head, workers=2)

    assert result["cards_checked"] == 2
    offender_stems = {o["stem"] for o in result["offenders"]}
    assert offender_stems == {"bolt"}


def test_ratchet_end_to_end_untested_regression(repo: Path):
    _write_fake_engine(repo, quote_bolt=True)
    base = _commit(repo, "base")
    _write_fake_engine(repo, quote_bolt=False)
    head = _commit(repo, "stop testing Lightning Bolt")

    result = rg.run_ratchet(repo, base, head, workers=2)

    offender = next(o for o in result["offenders"] if o["stem"] == "bolt")
    assert "tested at base, untested at head" in offender["reasons"]


def test_ratchet_end_to_end_clean_when_nothing_changed(repo: Path):
    _write_fake_engine(repo)
    base = _commit(repo, "base")

    result = rg.run_ratchet(repo, base, base, workers=2)

    assert result["offenders"] == []
    assert result["cards_checked"] == 2


def test_cli_ratchet_flag_nonzero_exit_on_regression(repo: Path):
    _write_fake_engine(repo, bolt_status="handled")
    base = _commit(repo, "base")
    _write_fake_engine(repo, bolt_status="silent")
    head = _commit(repo, "regress it")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(repo),
            "--base",
            base,
            "--head",
            head,
            "--ratchet",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ratchet"]["offenders"]
