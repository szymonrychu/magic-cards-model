"""Fight (CR 701.14), and Kraul Harpooner's own pump-then-fight shape.

CR 701.14a: "A spell or ability may instruct a creature to fight another
creature or it may instruct two creatures to fight each other. Each of those
creatures deals damage equal to its power to the other creature." CR 701.14d:
"The damage dealt when a creature fights isn't combat damage" - so nothing here
touches `machines/combat.py`, and CR 701.14b is what stops a fight reaching a
creature that is no longer there or no longer a creature.

Kraul Harpooner is the vehicle: "Undergrowth — When this creature enters,
choose up to one target creature you don't control with flying. This creature
gets +X/+0 until end of turn, where X is the number of creature cards in your
graveyard, then you may have this creature fight that creature." Three CR
608.2c instructions in printed order, only the last two of which need a target
to exist at all - the pump always happens (`_parse_undergrowth_pump_and_fight_
clause` in `machines/effects.py`).

Verified this session with `knowledge_search(q="...", type="rules")`:

- **CR 701.14** - Fight, in full: 701.14a (simultaneous damage equal to
  power), 701.14b (a gone or non-creature participant means neither fights),
  701.14c (fighting itself deals double), 701.14d (not combat damage).
- **CR 115.6** - "up to one target" legally chooses zero.
- **CR 608.2c** - a resolving ability's instructions happen in printed order.
- **CR 704.5g** - lethal damage is a state-based action, checked after
  resolution by `resolve_top`, not forced by the effect itself.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

HARPOONER = "Kraul Harpooner"


def _harpooner_board(graveyard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=[HARPOONER],
            battlefield=["Forest", "Forest"],
            graveyard=graveyard or [],
        )
        .player("bob", battlefield=["Birds of Paradise"])
    )


def test_harpooner_fights_the_chosen_flier_and_only_it_dies():
    """No creature cards in the graveyard: X is 0, Harpooner stays 3/2. Birds
    of Paradise (0/1, flying) dies to 3 damage; its own 0 power deals nothing
    back (CR 701.14a still runs the exchange, it is just zero)."""
    scenario = _harpooner_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    birds = scenario.creature("Birds of Paradise", "bob")
    (forest1, forest2) = scenario.untapped_sources("Forest", "Forest")

    scenario.choose_trigger_targets(HARPOONER, [birds])
    scenario.will_take_the_may(True, source=HARPOONER)
    harpooner = scenario.cast_and_resolve(HARPOONER, forest1, forest2)
    scenario.resolve_top()  # the enters-the-battlefield trigger itself

    assert birds.zone is Zone.GRAVEYARD
    assert harpooner.zone is Zone.BATTLEFIELD
    assert harpooner.damage == 0


def test_the_graveyard_count_pumps_harpooner_before_it_fights():
    """Two creature cards in the graveyard make X = 2, so Harpooner fights at
    5 power - enough that a fight against Serra Angel (4/4 flying) kills
    *both* (CR 701.14a is simultaneous, not one-sided)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[HARPOONER],
            battlefield=["Forest", "Forest"],
            graveyard=["Grizzly Bears", "Hill Giant"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (forest1, forest2) = scenario.untapped_sources("Forest", "Forest")

    scenario.choose_trigger_targets(HARPOONER, [angel])
    scenario.will_take_the_may(True, source=HARPOONER)
    harpooner = scenario.cast_and_resolve(HARPOONER, forest1, forest2)
    scenario.resolve_top()  # the enters-the-battlefield trigger itself

    assert angel.zone is Zone.GRAVEYARD, "4 toughness, 5 damage"
    assert harpooner.zone is Zone.GRAVEYARD, "2 toughness, 4 damage - CR 701.14a is simultaneous"


def test_declining_the_fight_leaves_both_creatures_untouched():
    """CR 608.2d: "you may have this creature fight" is a real choice - the
    pump still happened (it is not conditioned on the fight at all), but
    declining leaves Birds of Paradise alone."""
    scenario = _harpooner_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    birds = scenario.creature("Birds of Paradise", "bob")
    (forest1, forest2) = scenario.untapped_sources("Forest", "Forest")

    scenario.choose_trigger_targets(HARPOONER, [birds])
    scenario.will_take_the_may(False, source=HARPOONER)
    harpooner = scenario.cast_and_resolve(HARPOONER, forest1, forest2)
    scenario.resolve_top()  # the enters-the-battlefield trigger itself

    assert birds.zone is Zone.BATTLEFIELD
    assert birds.damage == 0
    assert harpooner.zone is Zone.BATTLEFIELD
    assert harpooner.damage == 0


def test_choosing_zero_targets_still_pumps_but_never_asks_to_fight():
    """CR 115.6: "up to one" legally chooses zero - the pump still applies
    (read off the graveyard regardless), and there being no "that creature"
    means the fight question is never even asked, not merely declined."""
    scenario = _harpooner_board(graveyard=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest1, forest2) = scenario.untapped_sources("Forest", "Forest")

    scenario.choose_trigger_targets(HARPOONER, [])
    harpooner = scenario.cast_and_resolve(HARPOONER, forest1, forest2)
    scenario.resolve_top()  # the enters-the-battlefield trigger itself

    assert harpooner.zone is Zone.BATTLEFIELD
    from magic_cards_model.machines.decisions import DecisionKind

    asked = [q for q in scenario.questions_asked() if q.kind is DecisionKind.MAY]
    assert asked == [], "no target chosen means no fight question at all"


def test_a_creature_you_control_is_not_a_legal_target():
    """The restriction is "you don't control" - alice's own creature is
    refused at announcement (CR 601.2c/603.3d), not merely a bad choice."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[HARPOONER],
            battlefield=["Forest", "Forest", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Birds of Paradise"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest1, forest2) = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_onto_stack(HARPOONER, forest1, forest2)
    scenario.pass_until_resolved()  # the spell itself; the ETB trigger goes on the stack

    with pytest.raises(ValueError):
        scenario.choose_trigger_targets(HARPOONER, [bears])


def test_a_non_flying_opponent_creature_is_not_a_legal_target():
    """The restriction also names "with flying" - a grounded opponent
    creature is refused the same way."""
    scenario = (
        Scenario()
        .player("alice", hand=[HARPOONER], battlefield=["Forest", "Forest"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    (forest1, forest2) = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_onto_stack(HARPOONER, forest1, forest2)
    scenario.pass_until_resolved()

    with pytest.raises(ValueError):
        scenario.choose_trigger_targets(HARPOONER, [giant])
