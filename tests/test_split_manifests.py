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
    # the literal `neighbour` count of check's reason histogram, against every
    # statement it resolved (imports and docstrings carry their own reasons)
    statements = sum(rep.reasons.values())
    assert rep.reasons["neighbour"] < NEIGHBOUR_CEILING * statements, rep.render()


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


def test_effects_ladder_guard_helpers_in_dispatch():
    # the ladders' guard helpers: every `_unreadable_*` refusal check (and the
    # one helper only such a check calls) and the clause-list rebind only
    # _parse_mixed_clauses uses
    _, p = resolved("effects")
    guards = [i for i in p.items if i.kind == "def" and i.key and i.key.startswith("_unreadable_")]
    assert len(guards) >= 11
    assert {i.key: i.target for i in guards} == dict.fromkeys((i.key for i in guards), "dispatch")
    assert p.target_of("_reorder_token_named_after_tail") == "dispatch"


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


# A safe facade import order must exist.  The new modules import each other's
# names at the top (eager uses) or at the bottom (deferred uses); a bottom
# import that reaches a module still running its own top imports finds its
# names missing.  Mirrors the split codemod's order search on the resolved
# graph (whose eager edges include the unquoted function annotations of a
# module without `from __future__ import annotations`).


def _import_plan(module: str) -> tuple[dict[str, tuple[set[str], set[str]]], dict[str, set[str]]]:
    manifest, p = resolved(module)
    graph = ml.build_graph(p)
    refs = list(graph.refs)
    edges = dict(graph.edges)
    leading = []
    for item in p.items:
        if item.kind not in ("import", "docstring") and not item.is_doc:
            break
        leading.append(item)
    defined = [i for i in p.items if i not in leading]
    last_owner = {n: i.target for i in defined for n in i.names}
    used = ({i.target for i in defined} | {m.target for m in p.members}) - {ml.STAY}
    targets = [t for t in manifest.targets if t in used] + sorted(used - set(manifest.targets))
    plan: dict[str, tuple[set[str], set[str]]] = {}
    for t in targets:
        need: dict[str, tuple[str, bool]] = {}
        for r in refs:
            if r.source_target != t or last_owner.get(r.name) != r.target:
                continue
            was = need.get(r.name)
            need[r.name] = (r.target, r.eager or (was is not None and was[1]))
        top = {d for d, eager in need.values() if eager and d != ml.STAY}
        bottom = {d for d, eager in need.values() if not eager and d != ml.STAY}
        plan[t] = (top, bottom)
    eager_deps = {
        t: {b for (a, b), k in edges.items() if k == "eager" and a == t and b in plan} for t in plan
    }
    return plan, eager_deps


def _safe_order(module: str) -> tuple[list[str] | None, list[str]]:
    plan, eager_deps = _import_plan(module)
    targets = list(plan)
    failures: list[str] = []
    dead: set[frozenset[str]] = set()

    def load(m: str, state: dict[str, str], done: list[str]) -> str | None:
        top, bottom = plan[m]
        for phase, mods in (("top", top), ("defs", bottom)):
            state[m] = phase
            for d in sorted(mods, key=str.lower):
                if state[d] == "unloaded":
                    err = load(d, state, done)
                    if err:
                        return err
                if state[d] == "top":
                    return f"{m} imports names from {d} while {d} is still at its own imports"
        state[m] = "loaded"
        done.append(m)
        return None

    def search(order: list[str], state: dict[str, str]) -> list[str] | None:
        loaded = frozenset(t for t, v in state.items() if v == "loaded")
        if len(loaded) == len(targets):
            return order
        if loaded in dead:
            return None
        for cand in targets:
            if state[cand] != "unloaded" or any(state[d] != "loaded" for d in eager_deps[cand]):
                continue
            nxt, done = dict(state), []
            err = load(cand, nxt, done)
            if err:
                failures.append(f"importing {cand} first: {err}")
                continue
            found = search([*order, cand, *(d for d in done if d != cand)], nxt)
            if found:
                return found
        dead.add(loaded)
        return None

    return search([], dict.fromkeys(targets, "unloaded")), failures


@pytest.mark.parametrize("module", MODULES)
def test_manifest_has_safe_import_order(module):
    order, failures = _safe_order(module)
    assert order is not None, "\n".join(failures[-6:])
