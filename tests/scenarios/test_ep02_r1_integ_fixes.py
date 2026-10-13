"""EP-02-R1 integration fixes found by the full-suite gate.

CR numbers looked up with `mise run rules:find`: 201.2, 201.5, 601.2h, 118.3.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _apostles(count: int) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Shadowborn Apostle"] * count + ["Swamp"],
            library=["Shadowborn Demon", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_shadowborn_apostle_sacrifices_six_apostles_counting_itself():
    """ "Sacrifice six creatures named Shadowborn Apostle" names any creature
    with that name (CR 201.2), not just the source (CR 201.5 is "the object it's
    on by name"), so the source is one of the six chosen, never the whole cost."""
    scenario = _apostles(6)
    apostles = [c for c in scenario.game.battlefield if c.name == "Shadowborn Apostle"]
    scenario.activate(apostles[0], *scenario.untapped_sources("Swamp"), sacrificing=apostles)
    graveyard = [c.name for c in scenario.player("alice").graveyard]
    assert graveyard.count("Shadowborn Apostle") == 6
    assert not [c for c in scenario.game.battlefield if c.name == "Shadowborn Apostle"]


def test_shadowborn_apostle_needs_six_apostles():
    scenario = _apostles(5)
    apostles = [c for c in scenario.game.battlefield if c.name == "Shadowborn Apostle"]
    with pytest.raises(ValueError):
        scenario.activate(apostles[0], *scenario.untapped_sources("Swamp"), sacrificing=apostles)
    assert len([c for c in scenario.game.battlefield if c.name == "Shadowborn Apostle"]) == 5


def test_shadowborn_apostle_cost_is_never_the_source_alone():
    """With no creatures chosen yet, the cost waits for six choices: the name
    in "creatures named Shadowborn Apostle" is a quality (CR 201.2), so the
    source is not filled in as the cost's own self-reference (CR 201.5)."""
    scenario = _apostles(6)
    source = scenario.find("Shadowborn Apostle", Zone.BATTLEFIELD, "alice")
    total = scenario.game.activation_cost(source, 0, "alice")
    sacrifice = next(c for c in total.components if c.kind.value == "sacrifice")
    assert sacrifice.required == 6
    assert sacrifice.cards == []


def test_slumbering_keepguard_pump_counts_once_as_it_resolves():
    """CR 608.2h: "for each enchantment you control" is counted as the ability
    resolves; an enchantment entering later does not grow the pump."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Slumbering Keepguard", "Plains", "Plains", "Plains"]
            + ["Honden of Cleansing Fire"],
            hand=["Honden of Seeing Winds"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    keepguard = scenario.find("Slumbering Keepguard", Zone.BATTLEFIELD, "alice")
    base = scenario.game.characteristics_of(keepguard).numeric_power
    scenario.activate(keepguard, auto=True)
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(keepguard).numeric_power == base + 1
    honden = scenario.find("Honden of Seeing Winds", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(honden, "alice")
    assert scenario.game.characteristics_of(keepguard).numeric_power == base + 1


@pytest.mark.parametrize("entering,birds", [("Grizzly Bears", 0), ("Wall of Omens", 1)])
def test_wingmantle_chaplain_watches_only_defenders_entering(entering, birds):
    """ "Whenever another creature you control with defender enters" (CR 603.2,
    CR 702.3): a creature without defender, its own Bird tokens included, does
    not trigger it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Wingmantle Chaplain", "Plains"],
            hand=[entering],
            library=["Plains"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find(entering, Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(card, "alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()
    assert len([c for c in scenario.game.battlefield if c.name == "Bird Token"]) == birds


@pytest.mark.parametrize("entering,prompted", [("Grizzly Bears", False), ("Absolute Virtue", True)])
def test_obsidian_battle_axe_watches_only_warriors_entering(entering, prompted):
    """ "Whenever a Warrior creature enters" (CR 205.3m, CR 603.2): a Bear
    entering does not trigger it, a Warrior does."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Obsidian Battle-Axe", "Plains"], hand=[entering])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find(entering, Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(card, "alice")
    scenario.game.put_triggers_on_stack()
    sources = [getattr(item, "source_name", None) for item in scenario.game.stack]
    assert ("Obsidian Battle-Axe" in sources) is prompted
