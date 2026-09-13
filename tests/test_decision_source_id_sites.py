"""Every place the engine builds a question says which object asks it.

`Decision.source_id` is only as good as its least careful call site: one
`Decision(...)` or one `game.may(...)` that forgets it publishes a question a
client cannot anchor to anything, and nothing at runtime would notice. So the
rule is structural - every construction and every call into a `Game` funnel
that builds a `Decision` passes `source_id` explicitly, `source_id=None`
included where no object asks (a turn-based action, a state-based action, the
pregame). Forgetting it fails here, naming the file and line.
"""

import ast
from pathlib import Path

import magic_cards_model

SOURCE_ROOT = Path(magic_cards_model.__file__).parent

#: Functions that build a `Decision` from their arguments.
FUNNELS = frozenset(
    {
        "may",
        "may_pay_life",
        "may_pay_energy",
        "may_pay_mana",
        "may_pay_mana_cost",
        "pay_any_amount_of_energy",
        "pay_any_amount_of_life",
        "scry",
        "surveil",
        "look_at_top_and_split",
        "search_library",
        "offer_new_targets_for_copy",
        # `machines/effects.py` helpers that ask on their caller's behalf.
        "_choose_a_color",
        "_search_library",
        "_choose_land_from_hand",
        "_discard_cards",
        "amass",
        "learn",
        "manifest_dread",
        "_search_and_exile_matching_name",
        "_explore",
    }
)


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _sites_missing_source_id() -> list[str]:
    missing: list[str] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name != "Decision" and name not in FUNNELS:
                continue
            keywords = {keyword.arg for keyword in node.keywords}
            if None in keywords:
                continue  # `**kwargs` forwarding - the caller's own call is checked.
            if "source_id" not in keywords:
                missing.append(f"{path.relative_to(SOURCE_ROOT)}:{node.lineno} {name}(...)")
    return missing


def test_every_decision_construction_and_funnel_call_passes_source_id():
    assert _sites_missing_source_id() == []


def test_the_scan_actually_finds_the_call_sites():
    """Guard against a scan that silently matches nothing and passes."""
    count = 0
    for path in SOURCE_ROOT.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and _call_name(node) == "Decision":
                count += 1
    assert count > 50
