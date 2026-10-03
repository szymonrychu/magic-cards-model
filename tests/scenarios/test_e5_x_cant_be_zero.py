"""Katara, Water Tribe's Hope: "Waterbend {X}: Creatures you control have base
power and toughness X/X until end of turn. X can't be 0. Activate only during
your turn."

"X can't be 0." is a restriction on the value announced for X, not an effect
sentence: substituting the announced X into the whole text used to turn it into
"0 can't be 0." and leave it as an unread remainder.

- **CR 107.3a** X is announced as the ability is activated.
- **CR 107.3b** a stated restriction on X applies to the announced value.
- **CR 602.5b** an activation that breaks a restriction is refused.
- **CR 613.4b** base power and toughness set in layer 7b.
"""

import pytest

from magic_cards_model.machines import Step

from .harness import Scenario

KATARA = "Katara, Water Tribe's Hope"


def _scenario():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[KATARA, "Island", "Island", "Plains", "Hill Giant", "Serra Angel"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_x_of_two_sets_every_creature_you_control_to_two_two():
    scenario = _scenario()
    katara = scenario.creature(KATARA, "alice")
    giant = scenario.creature("Hill Giant", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.activate(katara, *scenario.untapped_sources("Island", "Island"), x_value=2)
    scenario.resolve_top()
    for creature in (katara, giant, angel):
        chars = scenario.game.characteristics_of(creature)
        assert (chars.power, chars.toughness) == (2, 2), creature.name
    chars = scenario.game.characteristics_of(bears)
    assert (chars.power, chars.toughness) == (2, 2), "an opponent's creature is untouched"


def test_x_of_one_shrinks_the_big_ones_instead():
    scenario = _scenario()
    katara = scenario.creature(KATARA, "alice")
    angel = scenario.creature("Serra Angel", "alice")
    scenario.activate(katara, *scenario.untapped_sources("Island"), x_value=1)
    scenario.resolve_top()
    chars = scenario.game.characteristics_of(angel)
    assert (chars.power, chars.toughness) == (1, 1)


def test_x_of_zero_is_refused():
    scenario = _scenario()
    katara = scenario.creature(KATARA, "alice")
    with pytest.raises(ValueError, match="X can't be 0"):
        scenario.activate(katara, x_value=0)
    assert scenario.stack_names() == []
