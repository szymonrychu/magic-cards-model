"""P0-T03: manifest format and resolver library (scripts/split/manifest_lib.py).

Tooling tests on small fixture modules under tests/fixtures/split/manifest/;
nothing here touches the real engine modules.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
from scripts.split import manifest_lib as ml

FIX = Path(__file__).parent / "fixtures" / "split" / "manifest"
ROOT = Path(__file__).resolve().parent.parent


def source(name: str) -> str:
    return (FIX / name).read_text()


def manifest_dict(**over):
    base = {"module": "m", "source": "m.py", "package": "p", "mode": "module"}
    base["targets"] = ["a", "b"]
    base.update(over)
    return base


def by_key(placement: ml.Placement) -> dict[str, ml.Item]:
    return {i.key: i for i in placement.items if i.key}


# --------------------------------------------------------------- manifest format


def test_load_manifest_reads_every_field():
    m = ml.load_manifest(FIX / "mod_basic.toml")
    assert (m.module, m.source, m.package, m.mode) == (
        "pkg.mod_basic",
        "mod_basic.py",
        "out/basic",
        "module",
    )
    assert m.targets == ["gamma", "alpha", "beta"]
    assert m.names == {"alpha_special": "gamma"}
    assert [r.target for r in m.rules] == ["alpha", "beta", "beta"]
    assert m.rules[0].kinds == ("def",)
    assert m.placed == {"alpha_other": "beta", "helper_two": "gamma"}


def test_load_class_manifest():
    m = ml.load_manifest(FIX / "class_game.toml")
    assert m.mode == "class"
    assert (m.class_name, m.records) == ("Game", "records")
    assert m.stay == ["model_config", "named_stay"]


@pytest.mark.parametrize(
    "bad",
    [
        {"mode": "nonsense"},
        {"targets": []},
        {"names": {"x": "nowhere"}},
        {"rules": [{"pattern": "(", "target": "a"}]},
        {"rules": [{"pattern": "x", "target": "zzz"}]},
        {"rules": [{"pattern": "x", "target": "a", "kinds": ["bogus"]}]},
        {"placed": {"x": "zzz"}},
        {"mode": "class", "class": "G"},
        {"mode": "class", "records": "a"},
        {"mode": "class", "class": "G", "records": "zzz"},
    ],
)
def test_invalid_manifest_rejected(bad):
    with pytest.raises(ml.ManifestError):
        ml.parse_manifest(manifest_dict(**bad))


def test_common_target_is_always_allowed():
    m = ml.parse_manifest(manifest_dict(names={"x": "_common"}))
    assert m.names == {"x": "_common"}


def _class_dict(**over):
    return manifest_dict(**{"mode": "class", "class": "G", "records": "a", **over})


def test_class_mode_accepts_init_as_a_target_for_module_statements():
    """A module-level statement before the class may stay in the package __init__."""
    m = ml.parse_manifest(
        _class_dict(
            names={"helper": "__init__"},
            rules=[{"pattern": "CONST_.*", "target": "__init__"}],
            placed={"other": "__init__"},
        )
    )
    text = (
        "CONST_A = 1\n\ndef helper():\n    return CONST_A\n\n"
        "class G:\n    def m(self):\n        return helper()\n"
    )
    top = by_key(ml.resolve(text, m))
    assert (top["helper"].target, top["helper"].reason) == ("__init__", "name")
    assert (top["CONST_A"].target, top["CONST_A"].reason) == ("__init__", "rule")


@pytest.mark.parametrize("table", ["names", "placed"])
def test_module_mode_still_rejects_init_as_a_target(table):
    with pytest.raises(ml.ManifestError):
        ml.parse_manifest(manifest_dict(**{table: {"x": "__init__"}}))
    with pytest.raises(ml.ManifestError):
        ml.parse_manifest(manifest_dict(rules=[{"pattern": "x", "target": "__init__"}]))


def test_class_mode_records_cannot_be_init():
    with pytest.raises(ml.ManifestError):
        ml.parse_manifest(_class_dict(records="__init__"))


# ---------------------------------------------------------------------- precedence


def test_every_statement_gets_exactly_one_target_and_reason():
    m = ml.load_manifest(FIX / "mod_basic.toml")
    p = ml.resolve(source("mod_basic.py"), m)
    assert p.items
    for item in p.items:
        assert item.target in {*m.targets, "_common"}
        assert item.reason
    assert [i.start for i in p.items] == sorted(i.start for i in p.items)


def test_precedence_steps():
    m = ml.load_manifest(FIX / "mod_basic.toml")
    items = by_key(ml.resolve(source("mod_basic.py"), m))
    # explicit name beats the rule that also matches
    assert (items["alpha_special"].target, items["alpha_special"].reason) == ("gamma", "name")
    # rule beats placed
    assert (items["alpha_other"].target, items["alpha_other"].reason) == ("alpha", "rule")
    assert items["alpha_parse"].reason == "rule"
    assert (items["BetaRecord"].target, items["BetaRecord"].reason) == ("beta", "rule")
    # placed table
    assert (items["helper_two"].target, items["helper_two"].reason) == ("gamma", "placed")
    # nearest preceding placed neighbour
    assert (items["helper_one"].target, items["helper_one"].reason) == ("alpha", "neighbour")
    assert (items["trailing"].target, items["trailing"].reason) == ("gamma", "neighbour")


def test_statements_before_any_placed_go_to_first_target():
    m = ml.load_manifest(FIX / "mod_basic.toml")
    items = by_key(ml.resolve(source("mod_basic.py"), m))
    assert (items["early"].target, items["early"].reason) == ("gamma", "neighbour")


def test_constant_rule():
    m = ml.load_manifest(FIX / "mod_basic.toml")
    items = by_key(ml.resolve(source("mod_basic.py"), m))
    # one user (alpha_parse) -> its target
    assert (items["PATTERN"].target, items["PATTERN"].reason) == ("alpha", "const-single")
    # two users in different targets -> _common
    assert (items["SHARED_LIMIT"].target, items["SHARED_LIMIT"].reason) == (
        "_common",
        "const-shared",
    )
    # unreferenced -> neighbour (helper_two is gamma)
    assert (items["NOTE"].target, items["NOTE"].reason) == ("gamma", "const-unreferenced")


def test_const_used_by_same_target_twice_is_single():
    text = "K = 1\n\ndef a_x():\n    return K\n\ndef a_y():\n    return K\n"
    m = ml.parse_manifest(manifest_dict(rules=[{"pattern": "a_.*", "target": "b"}]))
    items = by_key(ml.resolve(text, m))
    assert (items["K"].target, items["K"].reason) == ("b", "const-single")


def test_const_used_only_via_another_const_follows_the_def():
    text = "K = 1\nL = K + 1\n\ndef b_x():\n    return L\n"
    m = ml.parse_manifest(manifest_dict(rules=[{"pattern": "b_.*", "target": "b"}]))
    items = by_key(ml.resolve(text, m))
    assert (items["L"].target, items["K"].target) == ("b", "b")


def test_rule_first_match_wins_and_kinds_filter():
    text = "def foo():\n    pass\n\nclass foo2:\n    pass\n\nfoo3 = 1\n"
    rules = [
        {"pattern": "foo.*", "target": "a", "kinds": ["class"]},
        {"pattern": "foo.*", "target": "b", "kinds": ["def", "const"]},
        {"pattern": "foo.*", "target": "a"},
    ]
    items = by_key(ml.resolve(text, ml.parse_manifest(manifest_dict(rules=rules))))
    assert items["foo"].target == "b"
    assert items["foo2"].target == "a"
    assert items["foo3"].target == "b"


def test_rule_uses_fullmatch():
    text = "def prefix_foo():\n    pass\n"
    m = ml.parse_manifest(manifest_dict(rules=[{"pattern": "foo", "target": "b"}]))
    assert by_key(ml.resolve(text, m))["prefix_foo"].reason == "neighbour"


def test_unseen_names_never_fail():
    m = ml.load_manifest(FIX / "mod_basic.toml")
    text = source("mod_basic.py") + "\n\ndef brand_new_thing():\n    return 1\n\nNEW = [1]\n"
    p = ml.resolve(text, m)
    items = by_key(p)
    assert items["brand_new_thing"].target == items["NOTE"].target
    assert items["brand_new_thing"].reason == "neighbour"
    assert "NEW" in items


def test_stale_manifest_names_are_ignored():
    m = ml.parse_manifest(manifest_dict(names={"gone": "a"}, placed={"gone2": "b"}))
    assert ml.resolve("def here():\n    pass\n", m).items[0].target == "a"


def test_item_line_ranges_include_decorators():
    text = "import x\n\n@deco\n@deco2\ndef f():\n    return 1\n"
    p = ml.resolve(text, ml.parse_manifest(manifest_dict()))
    f = by_key(p)["f"]
    assert (f.start, f.end) == (3, 6)
    assert p.lines_by_target()["a"] == 1 + 4


def test_target_of_maps_every_defined_name():
    text = "A, B = 1, 2\n\ndef f():\n    return A\n"
    m = ml.parse_manifest(manifest_dict(names={"f": "b"}))
    p = ml.resolve(text, m)
    assert p.target_of("f") == "b"
    assert p.target_of("A") == p.target_of("B") == "b"  # one statement, one target
    assert p.target_of("missing") is None


# ------------------------------------------------------------------------- bake


def bake_manifest(**over):
    return ml.parse_manifest(
        manifest_dict(
            targets=["a", "b", "c"],
            rules=[
                {"pattern": "a_.*", "target": "a"},
                {"pattern": "b_.*", "target": "b"},
                {"pattern": "c_.*", "target": "c"},
            ],
            **over,
        )
    )


def test_bake_caller_majority_tie_callee_tie_neighbour():
    placed = ml.bake(source("mod_bake.py"), bake_manifest())
    assert placed["h_major"] == "a"  # callers a, a, b
    assert placed["h_tie"] == "c"  # callers a, b tie; callees c, c
    assert placed["h_tie2"] == "c"  # callers tie, callees tie -> neighbour c_three
    assert placed["h_chain"] == "a"  # caller h_major baked in the same run
    assert placed["h_orphan"] == "a"  # no callers, no callees -> neighbour h_chain
    assert list(placed) == sorted(placed)
    assert not any(k.startswith(("a_", "b_", "c_")) for k in placed)


def test_bake_is_idempotent():
    text = source("mod_bake.py")
    m1 = bake_manifest()
    placed = ml.bake(text, m1)
    m2 = bake_manifest(placed=placed)
    assert ml.bake(text, m2) == placed


def test_bake_keeps_existing_placed_and_prunes_stale():
    text = source("mod_bake.py")
    m = bake_manifest(placed={"h_major": "b", "no_longer_exists": "c"})
    placed = ml.bake(text, m)
    assert placed["h_major"] == "b"  # human-reviewed value is kept
    assert placed["h_chain"] == "b"  # and propagates to its callee
    assert "no_longer_exists" not in placed


def test_bake_does_not_override_names_or_rules():
    text = "def a_x():\n    return 1\n"
    m = bake_manifest(names={"a_x": "c"})
    assert ml.bake(text, m) == {}


def test_bake_file_rewrites_placed_section_and_is_noop_second_time(tmp_path):
    for n in ("mod_bake.py", "mod_bake.toml"):
        shutil.copy(FIX / n, tmp_path / n)
    toml = tmp_path / "mod_bake.toml"
    assert ml.bake_file(toml) is True
    first = toml.read_text()
    assert "[placed]" in first and 'h_major = "a"' in first
    assert ml.load_manifest(toml).placed["h_tie"] == "c"
    assert ml.bake_file(toml) is False
    assert toml.read_text() == first


def test_bake_file_replaces_existing_placed_table_in_place(tmp_path):
    for n in ("mod_bake.py", "mod_bake.toml"):
        shutil.copy(FIX / n, tmp_path / n)
    toml = tmp_path / "mod_bake.toml"
    toml.write_text(toml.read_text() + '\n[placed]\nstale = "a"\n\n[names]\nh_orphan = "b"\n')
    # [placed] may precede other tables; only its own lines are replaced
    ml.bake_file(toml)
    m = ml.load_manifest(toml)
    assert "stale" not in m.placed
    assert m.names == {"h_orphan": "b"}
    assert m.placed["h_major"] == "a"


# ------------------------------------------------------------------ import graph


def graph_manifest():
    names = {}
    for n in [
        "base_dec",
        "BaseThing",
        "base_default",
        "base_body",
        "BaseAnn",
        "base_lazy",
        "base_str",
    ]:
        names[n] = "base"
    for n in ["user_decorated", "UserChild", "user_default", "MODULE_EXPR", "TYPED"]:
        names[n] = "user"
    for n in ["late_body", "late_ann", "late_lazy", "late_lambda"]:
        names[n] = "late"
    return ml.parse_manifest(manifest_dict(targets=["base", "user", "late"], names=names))


def test_reference_classification():
    p = ml.resolve(source("mod_graph.py"), graph_manifest())
    g = ml.build_graph(p)
    got: dict[str, set[tuple[str, bool]]] = {}
    for ref in g.refs:
        got.setdefault(ref.source_key, set()).add((ref.name, ref.eager))
    assert got["user_decorated"] == {("base_dec", True)}
    assert got["UserChild"] == {("BaseThing", True), ("base_default", True)}
    assert got["user_default"] == {("base_default", True)}
    assert got["MODULE_EXPR"] == {("base_body", True)}
    assert got["TYPED"] == {("BaseAnn", True)}  # string annotation parsed, conservative
    assert got["late_body"] == {("base_body", False)}
    assert got["late_ann"] == {("BaseAnn", False), ("BaseThing", False)}
    assert got["late_lambda"] == {("base_str", False)}
    # a name bound by a lazy in-function import is not a reference
    assert "late_lazy" not in got


_ANN_BASE = "class Shape:\n    pass\n\n"


def _ann_refs(text: str, user: str = "a") -> set[tuple[str, bool]]:
    """(name, eager) references from target `a` to `Shape` in target `b`."""
    m = ml.parse_manifest(
        manifest_dict(names={"Shape": "b"}, rules=[{"pattern": ".*", "target": user}])
    )
    g = ml.build_graph(ml.resolve(text, m))
    return {(r.name, r.eager) for r in g.refs if r.source_target == user}


def test_unquoted_function_annotations_without_future_import_are_eager():
    """Without `from __future__ import annotations` a def's annotations run at def time."""
    assert _ann_refs(_ANN_BASE + "def f(x: Shape) -> None:\n    return x\n") == {("Shape", True)}
    assert _ann_refs(_ANN_BASE + "def f(x) -> Shape:\n    return x\n") == {("Shape", True)}
    kw = "def f(*a: Shape, k: list[Shape] = (), **kw: Shape):\n    return a\n"
    assert _ann_refs(_ANN_BASE + kw) == {("Shape", True)}


def test_quoted_function_annotations_without_future_import_are_deferred():
    text = _ANN_BASE + 'def f(x: "Shape") -> "list[Shape]":\n    return x\n'
    assert _ann_refs(text) == {("Shape", False)}


def test_function_annotations_with_future_import_are_deferred():
    text = (
        "from __future__ import annotations\n\n"
        + _ANN_BASE
        + "def f(x: Shape) -> Shape:\n    return x\n"
    )
    assert _ann_refs(text) == {("Shape", False)}


def test_method_annotations_without_future_import_are_eager():
    """A method's annotations run when the class body runs, at import time."""
    text = _ANN_BASE + "class K:\n    def m(self, x: Shape) -> None:\n        return x\n"
    assert _ann_refs(text) == {("Shape", True)}


def test_nested_def_annotations_run_only_when_the_outer_function_runs():
    text = _ANN_BASE + "def f():\n    def g(x: Shape) -> Shape:\n        return x\n    return g\n"
    assert _ann_refs(text) == {("Shape", False)}


def test_class_mode_member_annotations_follow_the_future_import():
    body = "class G:\n    def combat_a(self, s: Shape) -> Shape:\n        return s\n"
    for future, eager in (("", True), ("from __future__ import annotations\n\n", False)):
        m = ml.parse_manifest(
            manifest_dict(
                mode="class",
                targets=["combat", "recs"],
                records="recs",
                rules=[{"pattern": "combat_.*", "target": "combat"}],
                **{"class": "G"},
            )
        )
        g = ml.build_graph(ml.resolve(future + _ANN_BASE + body, m))
        assert {(r.name, r.eager) for r in g.refs if r.source_target == "combat"} == {
            ("Shape", eager)
        }


def test_edges_eager_beats_deferred():
    g = ml.build_graph(ml.resolve(source("mod_graph.py"), graph_manifest()))
    assert g.edges == {("user", "base"): "eager", ("late", "base"): "deferred"}
    assert g.eager_edges() == {("user", "base")}
    assert g.cycles() == []


def test_deferred_edges_never_form_a_cycle():
    text = "def a_f():\n    return b_f()\n\ndef b_f():\n    return a_f()\n"
    m = ml.parse_manifest(manifest_dict(names={"a_f": "a", "b_f": "b"}))
    g = ml.build_graph(ml.resolve(text, m))
    assert set(g.edges.values()) == {"deferred"}
    assert g.cycles() == []


def test_function_locals_shadow_top_level_names():
    text = "def helper():\n    pass\n\ndef f(helper):\n    x = 1\n    return helper(x)\n"
    m = ml.parse_manifest(manifest_dict(names={"helper": "b", "f": "a"}))
    assert ml.build_graph(ml.resolve(text, m)).edges == {}


def test_eager_cycle_reported():
    m = ml.load_manifest(FIX / "mod_cycle.toml")
    g = ml.build_graph(ml.resolve(source("mod_cycle.py"), m))
    assert g.edges == {("a", "b"): "eager", ("b", "a"): "eager"}
    assert g.cycles() == [["a", "b"]]


def test_three_target_cycle_is_one_component():
    text = "class A1(C1):\n    pass\n\nclass B1(A1):\n    pass\n\nclass C1(B1):\n    pass\n"
    m = ml.parse_manifest(
        manifest_dict(targets=["a", "b", "c"], names={"A1": "a", "B1": "b", "C1": "c"})
    )
    assert ml.build_graph(ml.resolve(text, m)).cycles() == [["a", "b", "c"]]


# --------------------------------------------------------------------- class mode


def test_class_mode_stay_records_and_rules():
    m = ml.load_manifest(FIX / "class_game.toml")
    p = ml.resolve(source("class_game.py"), m)
    top = by_key(p)
    assert (top["Game"].target, top["Game"].reason) == ("__init__", "class-shell")
    assert (top["Record"].target, top["Record"].reason) == ("records", "records")
    mem = {i.key: i for i in p.members}
    assert (mem["model_config"].target, mem["model_config"].reason) == ("__init__", "stay")
    assert (mem["named_stay"].target, mem["named_stay"].reason) == ("__init__", "stay")
    assert (mem["life"].target, mem["life"].reason) == ("__init__", "field")
    assert (mem["check_life"].target, mem["check_life"].reason) == ("__init__", "decorated")
    assert (mem["combat_a"].target, mem["combat_a"].reason) == ("combat", "rule")
    assert (mem["draw_one"].target, mem["draw_one"].reason) == ("library", "rule")
    assert mem["shared_helper"].reason == "neighbour"
    assert Counter(i.target for i in p.members)["__init__"] == 4


def test_class_mode_bake_uses_self_attribute_calls():
    m = ml.load_manifest(FIX / "class_game.toml")
    placed = ml.bake(source("class_game.py"), m)
    assert placed == {"only_draw": "library", "shared_helper": "library"}


def test_class_mode_missing_class_is_an_error():
    m = ml.parse_manifest(manifest_dict(mode="class", **{"class": "Nope"}, records="a"))
    with pytest.raises(ml.ManifestError):
        ml.resolve("class Other:\n    pass\n", m)


def test_class_mode_graph_edges_come_from_member_targets():
    text = (
        "def util():\n    return 1\n\n"
        "class G:\n"
        "    def combat_a(self, x=util()):\n        return util()\n"
    )
    m = ml.parse_manifest(
        manifest_dict(
            mode="class",
            targets=["combat", "recs", "_common"],
            records="recs",
            names={"util": "_common"},
            rules=[{"pattern": "combat_.*", "target": "combat"}],
            **{"class": "G"},
        )
    )
    g = ml.build_graph(ml.resolve(text, m))
    assert g.edges == {("combat", "_common"): "eager"}


# ---------------------------------------------------------------------------- CLI


def test_check_report_counts(capsys):
    assert ml.main(["check", str(FIX / "mod_basic.toml")]) == 0
    out = capsys.readouterr().out
    assert "gamma" in out and "alpha" in out and "beta" in out and "_common" in out
    assert "unplaced: " in out
    assert "reasons:" in out and "name=1" in out and "rule=4" in out
    assert "eager cycles: none" in out


def test_check_report_object():
    rep = ml.check(FIX / "mod_basic.toml")
    assert rep.statements["alpha"] == 4
    assert rep.statements["beta"] == 2
    assert rep.lines["beta"] > 0
    assert rep.reasons["placed"] == 1
    # early, helper_one, trailing (neighbour) + PATTERN, SHARED_LIMIT, NOTE (constant rule)
    assert rep.unplaced == 6
    assert rep.cycles == [] and rep.empty_targets == []


def test_check_exits_1_on_eager_cycle(capsys):
    assert ml.main(["check", str(FIX / "mod_cycle.toml")]) == 1
    out = capsys.readouterr().out
    assert "eager cycles:" in out and "a, b" in out and "a -> b via B1" in out


def test_check_exits_1_on_empty_target(capsys):
    assert ml.main(["check", str(FIX / "mod_empty_target.toml")]) == 1
    assert "delta" in capsys.readouterr().out


def test_bake_cli_writes_toml(tmp_path, capsys):
    for n in ("mod_bake.py", "mod_bake.toml"):
        shutil.copy(FIX / n, tmp_path / n)
    toml = tmp_path / "mod_bake.toml"
    assert ml.main(["bake", str(toml)]) == 0
    first = toml.read_text()
    assert ml.main(["bake", str(toml)]) == 0
    assert toml.read_text() == first
    assert ml.load_manifest(toml).placed["h_major"] == "a"


def test_script_runs_as_documented_command():
    proc = subprocess.run(
        [sys.executable, "scripts/split/manifest_lib.py", "check", str(FIX / "mod_cycle.toml")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "eager cycles" in proc.stdout


# ------------------------------------------- non-definition statements, class mode


def test_imports_and_docstrings_get_their_own_reasons_not_neighbour():
    text = (
        '"""Module docstring."""\n\n'
        "from typing import TYPE_CHECKING\n"
        "import re\n\n"
        "if TYPE_CHECKING:\n    from pkg.other import Thing\n\n"
        "def f():\n    return re\n"
    )
    m = ml.parse_manifest(manifest_dict(names={"f": "b"}))
    reasons = [(i.kind, i.reason) for i in ml.resolve(text, m).items]
    assert reasons == [
        ("other", "docstring"),
        ("import", "import"),
        ("import", "import"),
        ("import", "import"),
        ("def", "name"),
    ]


def test_type_checking_block_defines_nothing_for_the_graph():
    text = "if TYPE_CHECKING:\n    from x import Thing\n\ndef f(t: Thing):\n    return t\n"
    m = ml.parse_manifest(manifest_dict(names={"f": "b"}))
    assert ml.build_graph(ml.resolve(text, m)).edges == {}


CLASS_TEXT = (
    "import re\n\n"
    "_ONLY_COMBAT = re.compile('x')\n"
    "_BOTH = 1\n"
    "_VIA_FIELD = 2\n\n"
    "class G:\n"
    "    life: int = _VIA_FIELD\n"
    '    """Attribute docstring of life."""\n\n'
    "    def combat_a(self):\n        return _ONLY_COMBAT, _BOTH\n\n"
    "    def draw_a(self):\n        return _BOTH\n\n"
    "    _combat_alias = combat_a\n\n"
    "    def stay_a(self):\n        return self.helper() + self.other()\n\n"
    "    def stay_b(self):\n        return self.helper()\n\n"
    "    def draw_b(self):\n        return self.helper() + self.other()\n\n"
    "    def helper(self):\n        return 1\n\n"
    "    def other(self):\n        return self.combat_a()\n"
)


def class_manifest(**over):
    return ml.parse_manifest(
        manifest_dict(
            mode="class",
            targets=["combat", "library", "recs"],
            records="recs",
            stay=["stay_a", "stay_b"],
            rules=[
                {"pattern": "combat_.*", "target": "combat"},
                {"pattern": "draw_.*", "target": "library"},
            ],
            **{"class": "G"},
            **over,
        )
    )


def test_class_mode_module_constants_follow_the_members_that_use_them():
    p = ml.resolve(CLASS_TEXT, class_manifest())
    top = by_key(p)
    assert (top["_ONLY_COMBAT"].target, top["_ONLY_COMBAT"].reason) == ("combat", "const-single")
    assert (top["_BOTH"].target, top["_BOTH"].reason) == ("_common", "const-shared")
    assert (top["_VIA_FIELD"].target, top["_VIA_FIELD"].reason) == ("__init__", "const-single")


def test_class_mode_attribute_docstring_travels_with_its_member():
    p = ml.resolve(CLASS_TEXT, class_manifest())
    (doc,) = [m for m in p.members if m.kind == "other"]
    assert (doc.target, doc.reason) == ("__init__", "docstring")


def test_class_body_alias_follows_the_method_it_names():
    p = ml.resolve(CLASS_TEXT, class_manifest(placed={"_combat_alias": "library"}))
    mem = {i.key: i for i in p.members}
    assert (mem["_combat_alias"].target, mem["_combat_alias"].reason) == ("combat", "alias")


def test_class_mode_bake_never_votes_for_the_class_shell():
    m = class_manifest()
    placed = ml.bake(CLASS_TEXT, m)
    assert ml.STAY not in placed.values()
    # helper: callers stay_a, stay_b (stay, not votes) and draw_b -> library
    assert placed["helper"] == "library"
    # other: callers stay_a (no vote), draw_b -> library
    assert placed["other"] == "library"
    ml.parse_manifest(
        manifest_dict(
            mode="class", targets=m.targets, records=m.records, placed=placed, **{"class": "G"}
        )
    )


def test_read_source_after_the_split_reads_the_monolith_the_split_commit_removed(tmp_path):
    """After a split step the manifest's source is gone from the tree; the manifest is
    still checked against the monolith it split (the dry run's F1 broke the effects
    manifest tests), read from the commit that deleted it."""
    fix = Path(__file__).parent / "fixtures" / "split" / "port" / "reg"
    repo = tmp_path / "repo"
    shutil.copytree(fix / "pkg", repo / "pkg")
    (repo / "m").mkdir()
    shutil.copy(fix / "reg.toml", repo / "m" / "reg.toml")
    env = {
        **os.environ,
        **{
            f"GIT_{w}_{k}": v
            for w in ("AUTHOR", "COMMITTER")
            for k, v in (("NAME", "t"), ("EMAIL", "t@e"))
        },
    }

    def git(*args):
        subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)

    git("init", "-q")
    git("config", "commit.gpgsign", "false")
    git("add", "-A")
    git("commit", "-q", "-m", "pre-split")
    old = (repo / "pkg" / "mono.py").read_text()
    git("rm", "-q", "pkg/mono.py")
    (repo / "pkg" / "mono").mkdir()
    (repo / "pkg" / "mono" / "__init__.py").write_text("")
    git("add", "-A")
    git("commit", "-q", "-m", "split F1: pkg.mono")
    manifest = ml.load_manifest(repo / "m" / "reg.toml")
    assert ml.read_source(manifest) == old
