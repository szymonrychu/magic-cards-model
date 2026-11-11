"""`scripts/ironsmith_compare/scenarios.py`: MCM goldens translated into scenario specs
for ironsmith's data-driven test runner, and that runner's JUnit output read back as
per-golden verdicts.

Goldens are MCM's own (`tests/golden/`). The JUnit XML is hand-written in the shape
Node's built-in `junit` reporter documents; nothing here comes from ironsmith.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from scripts.ironsmith_compare.scenarios import (
    SOURCE_PATH,
    Untranslated,
    behaviour_rows,
    golden_id,
    parse_junit,
    translate,
    write_specs,
)

GOLDEN = Path(__file__).parent / "golden"


def _golden(rel: str) -> dict:
    return json.loads((GOLDEN / rel).read_text())


def _setup(ops: list[dict]) -> list[dict]:
    return [op for op in ops if op["op"] == "addCard"]


def _rest(ops: list[dict]) -> list[dict]:
    return [op for op in ops if op["op"] != "addCard"]


def _cards(ops: list[dict], player: int, zone: str) -> int:
    return sum(op["count"] for op in _setup(ops) if op["player"] == player and op["zone"] == zone)


def test_golden_id_is_the_card_slug_and_file_stem():
    assert golden_id(GOLDEN / "aerial-doombot" / "activated-0.json") == "aerial-doombot/activated-0"
    assert (
        golden_id(GOLDEN / "aangs-iceberg" / "triggered-0.no-targets.json")
        == "aangs-iceberg/triggered-0.no-targets"
    )


def test_an_activated_ability_with_counters_and_new_stats():
    golden = _golden("aerial-doombot/activated-0.json")
    ops = translate(golden)
    board = golden["board"]["players"]
    assert _cards(ops, 0, "BATTLEFIELD") == len(board["alice"]["battlefield"])
    assert _cards(ops, 1, "BATTLEFIELD") == len(board["bob"]["battlefield"])
    assert _cards(ops, 0, "HAND") == len(board["alice"]["hand"])
    assert _cards(ops, 0, "LIBRARY") == len(board["alice"]["library"])
    assert _cards(ops, 1, "GRAVEYARD") == len(board["bob"]["graveyard"])
    assert _rest(ops) == [
        {
            "op": "activateAbility",
            "turn": 1,
            "phase": "PRECOMBAT_MAIN",
            "player": 0,
            "ability": "{5}{U}:",
        },
        {"op": "setStopAt", "turn": 1, "phase": "BEGIN_COMBAT"},
        {"op": "execute"},
        {
            "op": "assertCounterCount",
            "player": 0,
            "name": "Aerial Doombot",
            "counter": "+1/+1",
            "count": 3,
        },
        {
            "op": "assertPowerToughness",
            "player": 0,
            "name": "Aerial Doombot",
            "power": 4,
            "toughness": 4,
        },
    ]


def test_a_loyalty_ability_that_gains_life():
    ops = translate(_golden("ajani-strength-of-the-pride/activated-0.json"))
    assert _rest(ops)[0]["ability"] == "+1:"
    assert {"op": "assertLife", "player": 0, "life": 23} in ops


def test_an_enters_trigger_is_raised_by_casting_the_source_from_hand():
    golden = _golden("aatchik-emerald-radian/triggered-0.json")
    ops = translate(golden)
    hand = golden["board"]["players"]["alice"]["hand"]
    assert _cards(ops, 0, "HAND") == len(hand)
    insects_before = golden["board"]["players"]["alice"]["battlefield"].count("Insect Token")
    assert _rest(ops) == [
        {
            "op": "castSpell",
            "turn": 1,
            "phase": "PRECOMBAT_MAIN",
            "player": 0,
            "name": "Aatchik, Emerald Radian",
        },
        {"op": "setStopAt", "turn": 1, "phase": "BEGIN_COMBAT"},
        {"op": "execute"},
        {
            "op": "assertPermanentCount",
            "player": 0,
            "name": "Insect Token",
            "count": insects_before + 5,
        },
    ]


def test_targets_are_queued_and_zone_moves_become_counts():
    golden = _golden("aangs-iceberg/triggered-0.json")
    ops = translate(golden)
    alice = golden["board"]["players"]["alice"]
    memnites = alice["battlefield"].count("Memnite")
    rest = _rest(ops)
    assert rest[:2] == [
        {
            "op": "castSpell",
            "turn": 1,
            "phase": "PRECOMBAT_MAIN",
            "player": 0,
            "name": "Aang's Iceberg",
        },
        {"op": "addTarget", "player": 0, "target": "Memnite"},
    ]
    assert {
        "op": "assertPermanentCount",
        "player": 0,
        "name": "Memnite",
        "count": memnites - 1,
    } in rest
    assert {"op": "assertExileCount", "count": 1} in rest


def test_a_player_target_is_named_the_runner_way():
    golden = _golden("ajani-strength-of-the-pride/activated-0.json")
    golden["action"]["targets"] = ["bob"]
    assert {"op": "addTarget", "player": 0, "target": "playerB"} in translate(golden)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda g: g["board"].update(variant="busy"), "board variant busy"),
        (lambda g: g["board"].update(step=None), "board step None"),
        (lambda g: g["board"].update(tapped=["Memnite@alice#1"]), "tapped"),
        (lambda g: g["board"].update(tokens=[{"name": "Treasure"}]), "predefined tokens"),
        (lambda g: g["delta"].update(decisions=[{"kind": "may"}]), "decision may"),
        (lambda g: g["delta"].update(stack=["x"]), "left on the stack"),
        (lambda g: g["delta"].update(notices={"x": 1}), "notices"),
        (lambda g: g["action"].update(modes=[1]), "modes"),
        (lambda g: g["action"].update(x=2), "X"),
        (lambda g: g["action"].update(on_stack=False), "never on the stack"),
        (lambda g: g["recipe"].update(enters=True), "entered this turn"),
        (lambda g: g["recipe"].update(off_zone=True), "outside the battlefield"),
        (lambda g: g.update(ability="Waterbend {8}"), "cost:"),
    ],
)
def test_each_unmapped_shape_is_untranslated_with_its_reason(change, reason):
    golden = copy.deepcopy(_golden("ajani-strength-of-the-pride/activated-0.json"))
    change(golden)
    result = translate(golden)
    assert isinstance(result, Untranslated)
    assert reason in result.reason


def test_a_golden_with_nothing_assertable_is_untranslated():
    golden = _golden("ajani-strength-of-the-pride/activated-0.json")
    golden["delta"]["players"] = {}
    result = translate(golden)
    assert result == Untranslated("no recorded change the runner can assert")


def test_an_unmapped_trigger_kind_is_untranslated():
    result = translate(_golden("abhorrent-oculus/triggered-0.json"))
    assert isinstance(result, Untranslated)


def test_write_specs_chunks_specs_and_shims_and_lists_the_untranslated(tmp_path):
    paths = [
        GOLDEN / "aerial-doombot" / "activated-0.json",
        GOLDEN / "aatchik-emerald-radian" / "triggered-0.json",
        GOLDEN / "abhorrent-oculus" / "triggered-0.json",
    ]
    runner = Path("/home/user/ironsmith/scripts/mage-port-runner.mjs")
    manifest = write_specs(paths, tmp_path, runner, chunk=1)
    assert manifest["translated"] == [
        "aatchik-emerald-radian/triggered-0",
        "aerial-doombot/activated-0",
    ]
    assert list(manifest["untranslated"]) == ["abhorrent-oculus/triggered-0"]
    shims = sorted(tmp_path.glob("*.test.mjs"))
    assert [s.name for s in shims] == ["mcm-goldens-000.test.mjs", "mcm-goldens-001.test.mjs"]
    spec = json.loads((tmp_path / "mcm-goldens-000.json").read_text())
    assert spec["sourcePath"] == SOURCE_PATH
    assert [t["name"] for t in spec["tests"]] == ["aatchik-emerald-radian/triggered-0"]
    shim = shims[0].read_text()
    assert "file:///home/user/ironsmith/scripts/mage-port-runner.mjs" in shim
    assert "mcm-goldens-000.json" in shim
    assert len(shim.splitlines()) <= 6
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest


_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testcase name="mcm-goldens :: card-a/activated-0" time="0.1" classname="test"/>
  <testcase name="mcm-goldens :: card-b/triggered-0" time="0.1" classname="test">
    <failure type="testCodeFailure" message="expected 2 Memnite permanents, got 1">
Error: expected 2 Memnite permanents, got 1
    at assert (file:///x.mjs:1:1)
    </failure>
  </testcase>
  <testcase name="mcm-goldens :: card-c/triggered-1" time="0.1" classname="test">
    <failure type="testCodeFailure" message="card not found in hand: Foo">
Error: card not found in hand: Foo
    </failure>
  </testcase>
  <testcase name="mcm-goldens :: card-d/activated-1" time="0" classname="test">
    <skipped type="skipped" message="skip"/>
  </testcase>
  <testcase name="some other suite :: unrelated" time="0" classname="test"/>
</testsuites>
"""


def test_junit_cases_become_per_golden_verdicts():
    assert parse_junit(_JUNIT) == {
        "card-a/activated-0": {"verdict": "agree", "message": ""},
        "card-b/triggered-0": {
            "verdict": "disagree",
            "message": "expected 2 Memnite permanents, got 1",
        },
        "card-c/triggered-1": {
            "verdict": "ironsmith-error",
            "message": "card not found in hand: Foo",
        },
        "card-d/activated-1": {"verdict": "ironsmith-error", "message": "skipped"},
    }


def test_nested_suites_are_read_too():
    nested = _JUNIT.replace("<testsuites>", "<testsuites><testsuite name='x'>").replace(
        "</testsuites>", "</testsuite></testsuites>"
    )
    assert len(parse_junit(nested)) == 4


def test_every_golden_translates_or_says_why():
    reasons: dict[str, int] = {}
    translated = 0
    for path in sorted(GOLDEN.glob("*/*.json")):
        result = translate(json.loads(path.read_text()))
        if isinstance(result, Untranslated):
            assert result.reason
            reasons[result.reason] = reasons.get(result.reason, 0) + 1
        else:
            translated += 1
            assert result[-1]["op"].startswith("assert")
    assert translated > 1000


def test_behaviour_rows_join_the_manifest_with_the_junit_verdicts():
    manifest = {
        "translated": ["a/activated-0", "b/activated-0"],
        "untranslated": {"c/triggered-0": "decision may (answers are not recorded)"},
    }
    verdicts = {"a/activated-0": {"verdict": "agree", "message": ""}}
    cards = {"a/activated-0": "A", "b/activated-0": "B", "c/triggered-0": "C"}
    assert behaviour_rows(manifest, verdicts, cards) == [
        {"id": "a/activated-0", "card": "A", "verdict": "agree", "message": ""},
        {
            "id": "b/activated-0",
            "card": "B",
            "verdict": "ironsmith-error",
            "message": "no JUnit result",
        },
        {
            "id": "c/triggered-0",
            "card": "C",
            "verdict": "untranslated",
            "message": "decision may (answers are not recorded)",
        },
    ]
