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


CARD_COVERAGE_SCRIPT = Path(__file__).parent.parent / "scripts" / "card_coverage.py"


def _write_fake_engine(
    repo: Path,
    *,
    bolt_status: str = "handled",
    fog_status: str = "notice",
    quote_bolt: bool = True,
    name_status: dict[str, str] | None = None,
    keyword_status: dict[str, str] | None = None,
    card_coverage: str | None = "real",
    baseline: str | None = None,
) -> None:
    """A minimal stand-in for `magic_cards_model` (plain dataclasses, no
    pydantic): just enough surface - `models.card.Card.model_validate` and
    `support.card_support` (with `name`/`status`/`clauses`) - for the
    classify-worker subprocess and the real `scripts/card_coverage.py`'s
    `classify_card_raw` to import and call. A printing's status is its
    `_status` field; an oracle card's is `name_status[name]` (default
    handled) worsened by any `keyword_status[keyword]` - so the head and
    base commits can disagree about one card while sharing one bulk file.

    `card_coverage` is `"real"` (a copy of this repo's own script), `None`
    (no script: the worker falls back to `card_support`), or literal source
    for a tampered classifier. `baseline` is the committed
    `docs/card_coverage/support-baseline.json` content, if any."""
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
        "from dataclasses import dataclass, field\n\n"
        f"NAME_STATUS = {name_status or {}!r}\n"
        f"KEYWORD_STATUS = {keyword_status or {}!r}\n"
        "_RANK = {'silent': 0, 'unaudited': 1, 'notice': 2, 'handled': 3}\n\n\n"
        "@dataclass\n"
        "class Clause:\n"
        "    kind: str\n"
        "    text: str\n"
        "    status: str\n"
        "    reason: str = ''\n\n\n"
        "@dataclass\n"
        "class Support:\n"
        "    status: str\n"
        "    name: str = ''\n"
        "    clauses: list = field(default_factory=list)\n\n\n"
        "def card_support(card):\n"
        "    data = card.data\n"
        "    name = data.get('name', '')\n"
        "    rules = NAME_STATUS.get(name, data.get('_status', 'handled'))\n"
        "    clauses = [Clause('rules', data.get('oracle_text') or '', rules)]\n"
        "    for kw in data.get('keywords') or []:\n"
        "        clauses.append(Clause('keyword', kw, KEYWORD_STATUS.get(kw, 'handled')))\n"
        "    worst = min(clauses, key=lambda c: _RANK[c.status])\n"
        "    return Support(status=worst.status, name=name, clauses=clauses)\n",
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
    script = repo / "scripts" / "card_coverage.py"
    if card_coverage is None:
        if script.exists():
            script.unlink()
    else:
        _write(
            repo,
            "scripts/card_coverage.py",
            CARD_COVERAGE_SCRIPT.read_text() if card_coverage == "real" else card_coverage,
        )
    baseline_path = repo / "docs" / "card_coverage" / "support-baseline.json"
    if baseline is None:
        if baseline_path.exists():
            baseline_path.unlink()
    else:
        _write(repo, "docs/card_coverage/support-baseline.json", baseline)


def _oracle_card(
    name: str,
    *,
    oracle_id: str | None = None,
    oracle_text: str = "",
    keywords: list[str] | None = None,
    modern: str = "legal",
) -> dict:
    return {
        "oracle_id": oracle_id or _slug_id(name),
        "name": name,
        "oracle_text": oracle_text,
        "keywords": keywords or [],
        "layout": "normal",
        "games": ["paper"],
        "legalities": {"standard": "not_legal", "pioneer": "not_legal", "modern": modern},
    }


def _slug_id(name: str) -> str:
    return "oid-" + "-".join(name.lower().split())


def _write_bulk(path: Path, cards: list[dict]) -> Path:
    path.write_text(json.dumps(cards))
    return path


def _baseline(cards: list[dict], statuses: dict[str, str]) -> str:
    """A committed baseline for `cards`, each at `statuses[name]`."""
    from scripts import card_coverage as cc

    results = [
        cc.ClassificationResult(
            name=c["name"],
            status=statuses[c["name"]],
            clause_kind="",
            clause_text="",
            reason="",
            error=False,
        )
        for c in cards
    ]
    return cc.render_support_baseline(cards, results)


@pytest.fixture(autouse=True)
def default_bulk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every ratchet run in this file reads a tiny local bulk (one
    unchanging vanilla card) unless a test passes its own, so no test ever
    reaches the network for Scryfall's real snapshot."""
    path = _write_bulk(tmp_path / "default-bulk.json", [_oracle_card("Grizzly Bears")])
    monkeypatch.setenv("REGRESSION_GUARD_BULK", str(path))
    return path


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


# ---------------------------------------------------------------------------
# Card-status ratchet: every format-legal oracle card, not just the pool
# ---------------------------------------------------------------------------


SHADOW = "Thousand-Faced Shadow"


def test_ratchet_flags_regression_on_a_non_pool_oracle_card(repo: Path, tmp_path: Path):
    bulk = _write_bulk(
        tmp_path / "bulk.json", [_oracle_card(SHADOW, oracle_text="Ninjutsu {2}{U}{U}")]
    )
    _write_fake_engine(repo, name_status={SHADOW: "notice"})
    base = _commit(repo, "base")
    _write_fake_engine(repo, name_status={SHADOW: "silent"})
    head = _commit(repo, "regress the shadow")

    result = rg.run_ratchet(repo, base, head, workers=2, bulk_path=bulk)

    assert result["cards_checked"] == 2
    assert result["cards_checked_oracle"] == 1
    oracle = [o for o in result["offenders"] if o["source"] == "oracle"]
    assert [o["name"] for o in oracle] == [SHADOW]
    assert "status regressed: notice -> silent" in oracle[0]["reasons"]
    assert all(o["source"] == "pool" for o in result["offenders"] if o not in oracle)


def test_ratchet_flags_keyword_clause_regression(repo: Path, tmp_path: Path):
    card = _oracle_card("Warded Knight", oracle_text="Protection from red", keywords=["Protection"])
    bulk = _write_bulk(tmp_path / "bulk.json", [card])
    _write_fake_engine(repo)
    base = _commit(repo, "base")
    _write_fake_engine(repo, keyword_status={"Protection": "notice"})
    head = _commit(repo, "protection quality goes to notice")

    result = rg.run_ratchet(repo, base, head, workers=2, bulk_path=bulk)

    oracle = [o for o in result["offenders"] if o["source"] == "oracle"]
    assert [o["name"] for o in oracle] == ["Warded Knight"]
    assert "status regressed: handled -> notice" in oracle[0]["reasons"]


def test_ratchet_ignores_out_of_format_cards(repo: Path, tmp_path: Path):
    bulk = _write_bulk(
        tmp_path / "bulk.json",
        [_oracle_card("Old Relic", modern="not_legal"), _oracle_card("Grizzly Bears")],
    )
    _write_fake_engine(repo)
    base = _commit(repo, "base")
    _write_fake_engine(repo, name_status={"Old Relic": "silent"})
    head = _commit(repo, "regress an out-of-format card")

    result = rg.run_ratchet(repo, base, head, workers=2, bulk_path=bulk)

    assert result["cards_checked_oracle"] == 1
    assert result["offenders"] == []


def test_ratchet_baseline_floor_catches_regression_against_a_stale_base(repo: Path, tmp_path: Path):
    card = _oracle_card(SHADOW)
    bulk = _write_bulk(tmp_path / "bulk.json", [card])
    # The committed baseline says handled, but the base code already reads
    # the card silent (a regression that slipped in under a stale base).
    _write_fake_engine(
        repo, name_status={SHADOW: "silent"}, baseline=_baseline([card], {SHADOW: "handled"})
    )
    base = _commit(repo, "base")
    _write_fake_engine(
        repo,
        name_status={SHADOW: "silent"},
        baseline=_baseline([card], {SHADOW: "handled"}),
        bolt_status="handled",
    )
    _write(repo, "README.md", "touch\n")
    head = _commit(repo, "unrelated change")

    result = rg.run_ratchet(repo, base, head, workers=2, bulk_path=bulk)

    oracle = [o for o in result["offenders"] if o["source"] == "oracle"]
    assert [o["name"] for o in oracle] == [SHADOW]
    assert oracle[0]["baseline_status"] == "handled"
    assert "below baseline floor: handled -> silent" in oracle[0]["reasons"]
    assert result["baseline"]["present"] is True


def test_ratchet_oracle_text_change_is_reported_not_failed(repo: Path, tmp_path: Path):
    old_card = _oracle_card(SHADOW, oracle_text="Ninjutsu {2}{U}{U}")
    new_card = _oracle_card(SHADOW, oracle_text="Ninjutsu {1}{U}. Something new.")
    bulk = _write_bulk(tmp_path / "bulk.json", [new_card])
    baseline = _baseline([old_card], {SHADOW: "handled"})
    _write_fake_engine(repo, name_status={SHADOW: "silent"}, baseline=baseline)
    base = _commit(repo, "base")

    result = rg.run_ratchet(repo, base, base, workers=2, bulk_path=bulk)

    assert result["offenders"] == []
    changed = result["oracle_changed"]
    assert changed["count"] == 1
    assert changed["cards"][0]["name"] == SHADOW
    assert changed["cards"][0]["baseline_status"] == "handled"
    assert changed["cards"][0]["head_status"] == "silent"


def test_ratchet_new_card_absent_from_baseline_is_reported_not_failed(repo: Path, tmp_path: Path):
    known = _oracle_card("Known Card")
    fresh = _oracle_card("Spoiler Card")
    bulk = _write_bulk(tmp_path / "bulk.json", [known, fresh])
    baseline = _baseline([known], {"Known Card": "handled"})
    _write_fake_engine(repo, name_status={"Spoiler Card": "silent"}, baseline=baseline)
    base = _commit(repo, "base")

    result = rg.run_ratchet(repo, base, base, workers=2, bulk_path=bulk)

    assert result["offenders"] == []
    assert result["new_cards"]["count"] == 1
    assert result["new_cards"]["cards"][0]["name"] == "Spoiler Card"


def test_ratchet_reports_improvement_over_baseline_with_regenerate_hint(repo: Path, tmp_path: Path):
    card = _oracle_card(SHADOW)
    bulk = _write_bulk(tmp_path / "bulk.json", [card])
    _write_fake_engine(repo, baseline=_baseline([card], {SHADOW: "silent"}))
    base = _commit(repo, "base")

    result = rg.run_ratchet(repo, base, base, workers=2, bulk_path=bulk)

    assert result["offenders"] == []
    improved = result["improved_vs_baseline"]
    assert improved["count"] == 1
    assert improved["cards"][0]["name"] == SHADOW
    assert "coverage:baseline" in improved["hint"]


def test_ratchet_worker_uses_each_worktrees_own_card_coverage(repo: Path, tmp_path: Path):
    bulk = _write_bulk(tmp_path / "bulk.json", [_oracle_card(SHADOW)])
    _write_fake_engine(repo)
    base = _commit(repo, "base")
    tampered = (
        "from dataclasses import dataclass\n\n\n"
        "@dataclass\n"
        "class R:\n"
        "    status: str\n\n\n"
        "def classify_card_raw(raw):\n"
        "    return R(status='unaudited')\n"
    )
    _write_fake_engine(repo, card_coverage=tampered)
    head = _commit(repo, "head classifier reads everything unaudited")

    result = rg.run_ratchet(repo, base, head, workers=2, bulk_path=bulk)

    oracle = [o for o in result["offenders"] if o["source"] == "oracle"]
    assert [o["name"] for o in oracle] == [SHADOW]
    assert "status regressed: handled -> unaudited" in oracle[0]["reasons"]


def test_ratchet_falls_back_to_card_support_without_card_coverage(repo: Path, tmp_path: Path):
    bulk = _write_bulk(tmp_path / "bulk.json", [_oracle_card(SHADOW)])
    _write_fake_engine(repo, card_coverage=None)
    base = _commit(repo, "base")
    _write_fake_engine(repo, card_coverage=None, name_status={SHADOW: "silent"})
    head = _commit(repo, "regress")

    result = rg.run_ratchet(repo, base, head, workers=2, bulk_path=bulk)

    assert [o["name"] for o in result["offenders"] if o["source"] == "oracle"] == [SHADOW]


def test_ratchet_missing_bulk_fails_closed(repo: Path, tmp_path: Path):
    _write_fake_engine(repo)
    base = _commit(repo, "base")

    with pytest.raises(rg.RegressionGuardError, match="fails closed"):
        rg.run_ratchet(repo, base, base, workers=2, bulk_path=tmp_path / "missing.json")


def test_resolve_bulk_path_fails_closed_when_cache_missing_and_download_fails(tmp_path: Path):
    def offline_download(kind: str, *, cache_dir: Path) -> Path:
        raise OSError("network unreachable")

    with pytest.raises(rg.RegressionGuardError, match="fails closed"):
        rg.resolve_bulk_path(tmp_path, None, download=offline_download)


def test_resolve_bulk_path_downloads_into_the_repo_cache_when_missing(tmp_path: Path):
    calls = []

    def fake_download(kind: str, *, cache_dir: Path) -> Path:
        calls.append((kind, cache_dir))
        dest = cache_dir / f"{kind}.jsonl.gz"
        cache_dir.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"")
        return dest

    path = rg.resolve_bulk_path(tmp_path, None, download=fake_download)

    assert calls == [("oracle-cards", tmp_path / ".scryfall-cache")]
    assert path == tmp_path / ".scryfall-cache" / "oracle-cards.jsonl.gz"


def test_ratchet_bulk_with_no_legal_cards_fails_closed(repo: Path, tmp_path: Path):
    bulk = _write_bulk(tmp_path / "bulk.json", [_oracle_card("Old Relic", modern="not_legal")])
    _write_fake_engine(repo)
    base = _commit(repo, "base")

    with pytest.raises(rg.RegressionGuardError, match="fails closed"):
        rg.run_ratchet(repo, base, base, workers=2, bulk_path=bulk)


def test_cli_ratchet_missing_bulk_exits_nonzero(repo: Path, tmp_path: Path):
    _write_fake_engine(repo)
    base = _commit(repo, "base")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(repo),
            "--base",
            base,
            "--ratchet",
            "--bulk",
            str(tmp_path / "missing.json"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "fails closed" in result.stderr


def test_cli_ratchet_oracle_regression_exits_nonzero(repo: Path, tmp_path: Path):
    bulk = _write_bulk(tmp_path / "bulk.json", [_oracle_card(SHADOW)])
    _write_fake_engine(repo)
    base = _commit(repo, "base")
    _write_fake_engine(repo, name_status={SHADOW: "silent"})
    head = _commit(repo, "regress")

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
            "--bulk",
            str(bulk),
            "--workers",
            "2",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ratchet"]["cards_checked_oracle"] == 1
    assert [o["source"] for o in payload["ratchet"]["offenders"]] == ["oracle"]
