"""P0-T07: the seven split manifests under scripts/split/manifest/.

Each manifest must resolve cleanly against the engine source as it stands
(manifest_lib resolve only, no codemod run): no eager cycle between the new
modules, no empty target, few `neighbour` fallbacks, and every name it pins
explicitly (`[names]`, `stay`) still exists in the source.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

import pytest
from scripts.split import manifest_lib as ml

ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = ROOT / "scripts" / "split" / "manifest"
MODULES = ("effects", "game", "layers", "replacement", "casting", "triggers", "cost")

EFFECTS_FAMILIES = [
    "_common",
    "text",
    "amounts",
    "removal",
    "returns",
    "library",
    "continuous",
    "counters",
    "tokens",
    "damage",
    "draw_discard",
    "search",
    "life",
    "control_copy",
    "modal",
    "mana",
    "merges",
    "registries",
    "dispatch",
]
GAME_MIXINS = [
    "_zones",
    "_activation",
    "_stack_priority",
    "_costs_mana",
    "_casting",
    "_turn_sba",
    "_continuous",
    "_conditions",
    "_damage_life",
    "_combat",
    "_triggers_decisions",
]
NEIGHBOUR_CEILING = 0.02


@cache
def resolved(module: str) -> tuple[ml.Manifest, ml.Placement]:
    path = MANIFESTS / f"{module}.toml"
    if not path.is_file():
        pytest.fail(f"missing manifest {path.relative_to(ROOT)}")
    manifest = ml.load_manifest(path)
    return manifest, ml.resolve(ml.read_source(manifest), manifest)


def report(module: str) -> ml.CheckReport:
    manifest, p = resolved(module)
    graph = ml.build_graph(p)
    statements = p.statements_by_target()
    return ml.CheckReport(
        manifest=manifest,
        statements=statements,
        lines=p.lines_by_target(),
        reasons=p.reasons(),
        unplaced=p.unplaced(),
        graph=graph,
        cycles=graph.cycles(),
        empty_targets=[t for t in manifest.targets if not statements[t]],
    )


@pytest.mark.parametrize("module", MODULES)
def test_manifest_checks_clean(module):
    rep = report(module)
    assert rep.ok, rep.render()
    _, p = resolved(module)
    units = p.units()
    # manifest_lib also labels imports and bare expressions (docstrings,
    # attribute docstrings) `neighbour`; those are copied or travel with
    # their member, not placed, so the ceiling is on definitions.
    guessed = [u.key for u in units if u.reason == "neighbour" and u.kind in ml.KINDS]
    assert len(guessed) < NEIGHBOUR_CEILING * len(units), guessed


@pytest.mark.parametrize("module", MODULES)
def test_explicit_names_exist_in_source(module):
    manifest, p = resolved(module)
    present = {n for u in [*p.items, *p.members] for n in u.names}
    pinned = {*manifest.names, *manifest.stay}
    assert not sorted(pinned - present)


def test_effects_families_order_and_registries():
    manifest, p = resolved("effects")
    assert manifest.mode == "module"
    assert manifest.targets == EFFECTS_FAMILIES
    for name in ("EFFECTS", "TRIGGER_EFFECTS", "ACTIVATED_EFFECTS"):
        assert p.target_of(name) == "registries"
    for name in ("effect_for", "trigger_effect_for", "activated_effect_for"):
        assert p.target_of(name) == "registries"
    for name in (
        "_ability_effect_or_notice",
        "_spell_effect_or_notice",
        "_parse_mixed_clauses",
        "_parse_mixed_clause",
    ):
        assert p.target_of(name) == "dispatch"
    merges = [i for i in p.items if i.kind == "def" and i.key and i.key.startswith("_merge_")]
    assert merges
    assert {i.target for i in merges} == {"merges"}


def test_game_mixins_and_stay():
    manifest, p = resolved("game")
    assert manifest.mode == "class"
    assert manifest.class_name == "Game"
    assert manifest.targets[: len(GAME_MIXINS)] == GAME_MIXINS
    by_name = {n: m for m in p.members for n in m.names}
    for name in ("CURRENT_SCHEMA_VERSION", "settle_pregame"):
        assert by_name[name].target == ml.STAY
    for m in p.members:
        if m.is_field or m.pydantic:
            assert m.target == ml.STAY, m.key
    records = [i for i in p.items if i.kind == "class" and i.key != "Game"]
    assert records
    assert {i.target for i in records} == {manifest.records}


def test_casting_blight_phrase_is_placed():
    _, p = resolved("casting")
    assert p.target_of("_BLIGHT_PHRASE") is not None


# Every discriminated union stays whole: a module-level alias carrying
# `discriminator=` lands in one module together with every member class.


@pytest.mark.parametrize("module", MODULES)
def test_discriminated_unions_whole(module):
    _, p = resolved(module)
    classes = {i.key: i.target for i in p.items if i.kind == "class"}
    unions = [i for i in p.items if i.kind == "const" and "discriminator=" in _source_of(module, i)]
    for union in unions:
        members = sorted(n for n in union.uses if n in classes)
        assert {classes[n] for n in members} <= {union.target}, (union.key, members)


def test_known_unions_are_seen():
    for module, alias in (
        ("layers", "Count"),
        ("layers", "Selector"),
        ("layers", "Modification"),
        ("layers", "Condition"),
        ("replacement", "CreatedReplacementSpec"),
    ):
        _, p = resolved(module)
        (item,) = [i for i in p.items if alias in i.names]
        assert "discriminator=" in _source_of(module, item)


@cache
def _lines(module: str) -> list[str]:
    manifest, _ = resolved(module)
    return ml.read_source(manifest).splitlines()


def _source_of(module: str, item: ml.Item) -> str:
    return "\n".join(_lines(module)[item.start - 1 : item.end])
