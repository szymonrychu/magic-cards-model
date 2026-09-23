"""CR 601.2f: "This spell costs {N} less to cast if you control a <permanent>
with <characteristic> N or greater."

Bolt Bend (read off its own printing): "This spell costs {3} less to cast if
you control a creature with power 4 or greater." - `Game.cost_reduction_for`'s
conditional shape, asking `Game.condition_holds`. Bolt Bend is the only
cost reduction with this condition in the three formats (Scryfall search,
2026-09-23), so the reader is proven on the same condition in another place
and with another characteristic: Baxter Building (proof printing, legal in
Modern/Pioneer/Standard, in no deck), "{4}, {T}: Draw a card. Activate only
if you control a creature with toughness 4 or greater." (CR 602.5).

Rules, verified with `mise run rules:find` in the session that wrote this
file:

- CR 601.2f: the total cost is determined "minus all cost reductions", and
  once determined it is "locked in".
- CR 118.7a: a generic reduction reduces only the generic component - {3}
  off {3}{R} leaves {R}.
- CR 208.1: power "can be modified or set to particular values by
  effects", so it is read as it stands (CR 613.4c's layer 7c pump counts).
- CR 602.5: "A player can't begin to activate an ability that's prohibited
  from being activated" - an unmet "Activate only if" is such a prohibition.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def bend_board(*alice_creatures: str, bob_creatures: tuple[str, ...] = ()) -> Scenario:
    """Bob bolts Alice's face; Alice has one Mountain for Bolt Bend's {R}."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bolt Bend", "Giant Growth"],
            battlefield=["Mountain", "Forest", *alice_creatures],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain", *bob_creatures])
        .build()
    )


def bob_bolts(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    return bolt


def reduction(scenario, name="Bolt Bend", username="alice") -> str:
    return str(scenario.game.cost_reduction_for(scenario.find(name, Zone.HAND, username), username))


def test_a_power_four_creature_takes_three_off():
    """Bonecrusher Giant (4/3) on the battlefield: {3}{R} costs {R}, paid with
    one Mountain."""
    scenario = bend_board("Bonecrusher Giant")
    bolt = bob_bolts(scenario)

    assert reduction(scenario) == "{3}"
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bend = scenario.cast_onto_stack("Bolt Bend", mountain, username="alice", targets=[bolt])

    assert bend.zone is Zone.STACK


def test_power_three_is_not_enough():
    """Hill Giant is 3/3: "4 or greater" is not met, so the full {3}{R} is
    owed and one Mountain cannot pay it (CR 118.3)."""
    scenario = bend_board("Hill Giant")
    bolt = bob_bolts(scenario)

    assert reduction(scenario) == ""
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    with pytest.raises(ValueError):
        scenario.cast_onto_stack("Bolt Bend", mountain, username="alice", targets=[bolt])


def test_an_opponents_creature_does_not_count():
    """ "if *you* control": Bob's Bonecrusher Giant is not Alice's."""
    scenario = bend_board(bob_creatures=("Bonecrusher Giant",))
    bob_bolts(scenario)

    assert reduction(scenario) == ""


def test_power_is_read_as_it_stands_now():
    """CR 208.1/613.4c: Hill Giant pumped by Giant Growth is a 6/6 until end of
    turn, and that computed power is what "power 4 or greater" reads."""
    scenario = bend_board("Hill Giant")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "alice")
    assert reduction(scenario) == ""
    (forest,) = scenario.untapped_sources("Forest", username="alice")

    scenario.cast_and_resolve("Giant Growth", forest, username="alice", targets=[giant])

    assert scenario.game.power_of(giant) == 6
    assert reduction(scenario) == "{3}"


def test_the_reduction_never_touches_the_coloured_half():
    """CR 118.7a: the {3} comes off the generic part only, so {R} is still
    owed - a Forest cannot pay it."""
    scenario = bend_board("Bonecrusher Giant")
    bolt = bob_bolts(scenario)
    (forest,) = scenario.untapped_sources("Forest", username="alice")

    with pytest.raises(ValueError):
        scenario.cast_onto_stack("Bolt Bend", forest, username="alice", targets=[bolt])


def test_the_discount_is_locked_in_when_the_cost_is_determined():
    """CR 601.2f: "Once the total cost is determined ... the resulting total
    cost becomes 'locked in.'" The Bonecrusher Giant leaving after the cost
    was determined changes nothing: one Mountain still pays it."""
    scenario = bend_board("Bonecrusher Giant")
    bolt = bob_bolts(scenario)
    giant = scenario.creature("Bonecrusher Giant", "alice")

    casting = scenario.cast("Bolt Bend", "alice", targets=[bolt])
    payment = casting.begin_paying()
    scenario.game.sacrifice(giant)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.pay_with(payment, mountain)
    bend = scenario.put_on_stack(casting)

    assert bend.zone is Zone.STACK


# -- proof printing: Baxter Building -----------------------------------------


def baxter_board(*alice_creatures: str, bob_creatures: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island", "Island"],
            battlefield=["Baxter Building", *["Wastes"] * 4, *alice_creatures],
        )
        .player("bob", library=["Island"], battlefield=list(bob_creatures))
        .build()
    )


def draw_ability_refusal(scenario) -> str | None:
    building = scenario.find("Baxter Building", Zone.BATTLEFIELD, "alice")
    return scenario.game.why_cannot_activate(building, 2, "alice")


def test_a_toughness_four_creature_lets_baxter_building_draw():
    """Spellskite is 0/4: toughness 4 meets "toughness 4 or greater"."""
    scenario = baxter_board("Spellskite")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    building = scenario.find("Baxter Building", Zone.BATTLEFIELD, "alice")
    hand_before = len(scenario.player("alice").hand)

    assert draw_ability_refusal(scenario) is None
    scenario.activate(building, *scenario.untapped_sources(*["Wastes"] * 4), index=2)
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == hand_before + 1


def test_toughness_three_does_not_let_baxter_building_draw():
    """Hill Giant is 3/3; its power is irrelevant to a toughness condition."""
    scenario = baxter_board("Hill Giant")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert draw_ability_refusal(scenario) is not None


def test_an_opponents_tough_creature_does_not_let_baxter_building_draw():
    scenario = baxter_board(bob_creatures=("Spellskite",))
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert draw_ability_refusal(scenario) is not None
