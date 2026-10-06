"""Support N (CR 701.41a): "Put a +1/+1 counter on each of up to N target
creatures." On a permanent's enters trigger the creatures are "other"
(CR 701.41a: "If the source is a permanent, ... other target creatures").

The keyword action is read by `machines/effects/counters._parse_support_clause`
(targets announced by `targeting._expand_support_keyword`); this file pins the
three pool printings and the support oracle's credit for the keyword
(`support.executed_keywords`), which is what makes `ignored_keywords` empty.

Printings: Nissa's Judgment (support then a group bite, covered in
`test_nw01_choose_pair_fight_bite.py`), Shoulder to Shoulder (a spell: support
then draw) and Expedition Raptor (an enters trigger: "other" creatures).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import ignored_keywords
from tests.scenarios.harness import Scenario
from tests.test_sweep_pool import card


@pytest.mark.parametrize("name", ["Nissa's Judgment", "Shoulder to Shoulder", "Expedition Raptor"])
def test_support_is_a_credited_keyword_not_an_ignored_one(name):
    assert "Support" not in ignored_keywords(card(name))


def test_shoulder_to_shoulder_puts_a_counter_on_each_target_then_draws():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shoulder to Shoulder"],
            battlefield=["Plains"] * 3 + ["Grizzly Bears", "Watchwolf"],
            library=["Plains", "Plains"],
        )
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "alice")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Shoulder to Shoulder", *sources, targets=[bears, wolf])

    assert bears.counters["+1/+1"] == 1
    assert wolf.counters["+1/+1"] == 1
    assert scenario.find("Shoulder to Shoulder", Zone.GRAVEYARD, "alice") is not None
    assert scenario.find("Plains", Zone.HAND, "alice") is not None, "drew the card"


def test_shoulder_to_shoulder_up_to_n_allows_a_single_target():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shoulder to Shoulder"],
            battlefield=["Plains"] * 3 + ["Grizzly Bears", "Watchwolf"],
            library=["Plains"],
        )
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "alice")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Shoulder to Shoulder", *sources, targets=[bears])

    assert bears.counters["+1/+1"] == 1
    assert wolf.counters["+1/+1"] == 0


def test_shoulder_to_shoulder_refuses_more_than_n_targets():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shoulder to Shoulder"],
            battlefield=["Plains"] * 3 + ["Grizzly Bears", "Watchwolf", "Elvish Lookout"],
            library=["Plains"],
        )
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    targets = [
        scenario.creature("Grizzly Bears", "alice"),
        scenario.creature("Watchwolf", "alice"),
        scenario.creature("Elvish Lookout", "alice"),
    ]
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    with pytest.raises(Exception, match=r"(?i)target"):
        scenario.cast_and_resolve("Shoulder to Shoulder", *sources, targets=targets)


def test_expedition_raptor_enters_supporting_other_creatures_only():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Expedition Raptor"],
            battlefield=["Plains"] * 5 + ["Grizzly Bears", "Watchwolf"],
            library=["Plains"],
        )
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "alice")
    sources = scenario.untapped_sources(*["Plains"] * 5)
    scenario.choose_trigger_targets("Expedition Raptor", [bears, wolf])
    scenario.cast_and_resolve("Expedition Raptor", *sources)
    scenario.pass_until_resolved()

    raptor = scenario.creature("Expedition Raptor", "alice")
    assert bears.counters["+1/+1"] == 1
    assert wolf.counters["+1/+1"] == 1
    assert raptor.counters["+1/+1"] == 0, "support on a permanent says 'other'"
