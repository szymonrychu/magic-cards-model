"""`CardRequirement.why_not` reads the computed board (CR 613.5), not the
printed type line, for a card already on the battlefield.

CR 613.1's "actual object" is only the *starting point* - "the values of the
characteristics printed on that card" - and CR 613.5 is the rest of the
sentence: "the application of continuous effects as described by the layer
system is continually and automatically performed by the game." A cost that
names a quality - "Sacrifice a creature" (Fling), "Tap an untapped creature
you control" (Swallow Whole) - is asking what a permanent *is right now*, and
CR 613.1d puts type-changing effects in layer 4, so a land animated by
earthbend (CR 701.66a) is a creature "in addition to its other types"
(CR 205.1b) the instant the ability resolves, whatever its own printed type
line says.

`why_not` used to read `card.card` - the raw Scryfall printing - unconditio-
nally, so an earthbent land could never pay either cost: the printed type
line for a land never says creature. This file is written against that
failure, and against the opposite one a fix could introduce just as easily -
a plain, unanimated land accepted because the check stopped discriminating at
all. Both `test_costs.py::test_an_additional_cost_of_sacrificing_a_creature_
is_paid_on_the_way_to_the_stack` and `::test_tapping_a_creature_as_an_
additional_cost` already cover the ordinary, never-animated case for both
costs; this file is what an animated permanent adds on top.

`Fling` has no entry in `machines/effects.py`'s registry, so nothing here
asserts on the damage it deals - only on the cost, which is the whole of what
this file is about. Registering its effect is a different piece of work.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import CardState, Zone
from tests.scenarios.harness import PlayedScenario, Scenario
from tests.scenarios.test_costs import announce


def _earthbend_a_fresh_forest(
    extra_battlefield: int = 2,
) -> tuple[PlayedScenario, CardState, CardState]:
    """alice casts Badgermole Cub off `extra_battlefield` Forests, earthbending
    one further Forest that was already on the battlefield before this turn -
    the same shape `test_earthbend.py::_earthbend_a_fresh_forest` uses, kept
    local here so this file's board also carries Fling/Swallow Whole and their
    own mana, and so a change to that helper's signature cannot silently
    change what this file is testing.

    Returns `(scenario, animated_forest, plain_island)`: an Island, never
    touched by anything, is what the inverse tests below tap or sacrifice - a
    land distinct in name from every Forest on the board, so there is no
    ambiguity about which permanent an assertion is reading.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub", "Fling", "Swallow Whole"],
            battlefield=[
                "Forest",
                *(["Forest"] * extra_battlefield),
                "Mountain",
                "Mountain",
                "Plains",
                "Island",
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * (extra_battlefield + 1)))
    pay_sources, target_forest = sources[:extra_battlefield], sources[extra_battlefield]
    scenario.choose_trigger_targets("Badgermole Cub", [target_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources)
    scenario.pass_until_resolved()
    island = scenario.untapped_sources("Island")[0]
    return scenario, target_forest, island


# --------------------------------------------------------------------------
# CR 118.8a's additional cost: "Sacrifice a creature" (Fling)
# --------------------------------------------------------------------------


def test_an_earthbent_land_can_be_sacrificed_to_pay_sacrifice_a_creature():
    """The positive case: the animated Forest is a creature on the computed
    board (`test_earthbend.py` already asserts this directly), so Fling's
    additional cost accepts it exactly as it would accept an ordinary
    creature, and the sacrifice happens on the way to the stack (CR 601.2h).
    """
    scenario, forest, _island = _earthbend_a_fresh_forest()
    assert scenario.game.characteristics_of(forest).is_creature
    assert "Creature" not in forest.card.type_line, "the printed type line never says creature"

    casting = announce(scenario, "Fling", sacrificing=[forest])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    spell = scenario.put_on_stack(casting)

    assert forest.zone is Zone.GRAVEYARD
    assert spell.zone is Zone.STACK


def test_a_plain_unanimated_land_cannot_be_sacrificed_to_pay_sacrifice_a_creature():
    """The inverse: an Island earthbend never touched is only ever a land, so
    the same requirement that now accepts the animated Forest must still
    refuse this one - a fix that stopped discriminating at all would pass the
    test above and fail this one.
    """
    scenario, _forest, island = _earthbend_a_fresh_forest()
    assert not scenario.game.characteristics_of(island).is_creature

    casting = announce(scenario, "Fling", sacrificing=[island])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="is not a creature"):
        scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))

    assert island.zone is Zone.BATTLEFIELD, "a refused payment sacrifices nothing"


# --------------------------------------------------------------------------
# CR 118.8a's additional cost: "Tap an untapped creature you control"
# (Swallow Whole)
# --------------------------------------------------------------------------


def test_an_earthbent_land_can_be_tapped_to_pay_tap_a_creature_you_control():
    """The positive case for the tap-quality cost: haste (CR 701.66a's own
    grant) is what makes the freshly animated land untapped and eligible the
    same turn it was earthbent - CR 302.6 would otherwise hold it back the way
    it holds back an ordinary summoning-sick creature.
    """
    scenario, forest, _island = _earthbend_a_fresh_forest()
    assert not forest.tapped
    theirs = scenario.untapped_sources("Grizzly Bears", username="bob")[0]
    theirs.tap()  # Swallow Whole exiles a *tapped* creature

    casting = announce(scenario, "Swallow Whole", tapping=[forest])
    casting.choose_targets([theirs])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains"))
    scenario.put_on_stack(casting)

    assert forest.tapped


def test_a_plain_unanimated_land_cannot_be_tapped_to_pay_tap_a_creature_you_control():
    """The inverse: an untapped Island satisfies "untapped" and "you control"
    but not "creature", so the requirement still refuses it.
    """
    scenario, _forest, island = _earthbend_a_fresh_forest()
    theirs = scenario.untapped_sources("Grizzly Bears", username="bob")[0]
    theirs.tap()

    casting = announce(scenario, "Swallow Whole", tapping=[island])
    casting.choose_targets([theirs])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="is not a creature"):
        scenario.pay_with(payment, *scenario.untapped_sources("Plains"))

    assert not island.tapped, "a refused payment taps nothing"
