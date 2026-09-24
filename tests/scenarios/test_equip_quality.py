"""Scenario: "Equip [quality] [cost]" - an equip ability that may target only a
creature with the quality (CR 702.6c).

CR 702.6c: "Equip abilities may further restrict what creatures may be chosen
as legal targets. Such restrictions usually appear in the form 'Equip
[quality]' or 'Equip [quality] creature.' These equip abilities may legally
target only a creature that's controlled by the player activating the ability
and that has the chosen quality. Additional restrictions for an equip ability
don't restrict what the Equipment may be attached to."

Cards: Mjolnir, Hammer of Thor's "Equip worthy {1}" (CR 700.16: "A creature
is worthy if it's legendary, isn't a Villain, and is red and/or white.");
proof printing Steelclaw Lance's "Equip Knight {1}" beside a plain "Equip
{3}" - the target decides which of the two can be activated. The equip
ability itself is CR 702.6a's "[Cost]: Attach this permanent to target
creature you control. Activate only as a sorcery."

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: 702.6a, 702.6c, 700.16, 608.2b.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import ManaCost, Zone
from tests.scenarios.harness import Scenario, mana_from


def _equip(scenario, equipment, creature, *sources):
    activation = equip_activation(scenario.game, equipment, creature, "alice")
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()
    return activation


def _mjolnir_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=[
                "Mjölnir, Hammer of Thor",
                "Isamaru, Hound of Konda",
                "Goblin Guide",
                "Azusa, Lost but Seeking",
                "Mister Negative",
                "Mountain",
            ],
        )
        .player("bob", library=["Forest"])
    )


def test_mjolnir_equips_a_worthy_creature_for_one():
    scenario = _mjolnir_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hammer = scenario.find("Mjölnir, Hammer of Thor", Zone.BATTLEFIELD, "alice")
    isamaru = scenario.creature("Isamaru, Hound of Konda", "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    activation = _equip(scenario, hammer, isamaru, mountain)

    assert activation.cost.mana == ManaCost.parse("{1}")
    assert hammer.attached_to == isamaru.id


@pytest.mark.parametrize(
    "name",
    [
        "Goblin Guide",  # red, not legendary
        "Azusa, Lost but Seeking",  # legendary, green
        "Mister Negative",  # legendary and white, but a Villain
    ],
)
def test_mjolnir_refuses_an_unworthy_creature(name):
    scenario = _mjolnir_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hammer = scenario.find("Mjölnir, Hammer of Thor", Zone.BATTLEFIELD, "alice")
    creature = scenario.creature(name, "alice")

    with pytest.raises(ValueError, match="worthy"):
        equip_activation(scenario.game, hammer, creature, "alice")


def test_an_attached_mjolnir_is_unaffected_by_what_the_ability_restricts():
    """CR 702.6c's last sentence: the restriction is on the target, not on
    what the Equipment may be attached to - an effect may attach it to any
    creature."""
    scenario = _mjolnir_board().build()
    hammer = scenario.find("Mjölnir, Hammer of Thor", Zone.BATTLEFIELD, "alice")
    guide = scenario.creature("Goblin Guide", "alice")

    hammer.attach_to(guide)

    assert hammer.attached_to == guide.id


# -- Steelclaw Lance (proof): "Equip Knight {1}" beside "Equip {3}" -----------


def _lance_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Steelclaw Lance", "Alaborn Cavalier", "Grizzly Bears", *["Plains"] * 3],
        )
        .player("bob", library=["Forest"])
    )


def test_the_knight_equip_costs_one_on_a_knight():
    scenario = _lance_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lance = scenario.find("Steelclaw Lance", Zone.BATTLEFIELD, "alice")
    knight = scenario.creature("Alaborn Cavalier", "alice")
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    activation = _equip(scenario, lance, knight, plains)

    assert activation.cost.mana == ManaCost.parse("{1}")
    assert lance.attached_to == knight.id
    assert scenario.game.characteristics_of(knight).power == 4


def test_a_non_knight_needs_the_plain_equip():
    scenario = _lance_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lance = scenario.find("Steelclaw Lance", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", username="alice")

    activation = _equip(scenario, lance, bears, *plains)

    assert activation.cost.mana == ManaCost.parse("{3}")
    assert lance.attached_to == bears.id


def test_neither_equip_can_target_an_opponents_knight():
    """CR 702.6c: "a creature that's controlled by the player activating the
    ability and that has the chosen quality" - both halves."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Steelclaw Lance", *["Plains"] * 3])
        .player("bob", library=["Forest"], battlefield=["Alaborn Cavalier"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lance = scenario.find("Steelclaw Lance", Zone.BATTLEFIELD, "alice")
    knight = scenario.creature("Alaborn Cavalier", "bob")

    with pytest.raises(ValueError):
        equip_activation(scenario.game, lance, knight, "alice")
