"""A resolving ability asking about the permanent that paid its cost.

Witch's Oven: "{T}, Sacrifice a creature: Create a Food token. If the
sacrificed creature's toughness was 4 or greater, create two Food tokens
instead."

CR 602.2b: "The remainder of the process for activating an ability is
identical to the process for casting a spell listed in rules 601.2b-i" - and
601.2h is where costs are paid. So by the time the ability is an object on the
stack, the creature has already been sacrificed: CR 701.21a moves it "from the
battlefield directly to its owner's graveyard". The printed "was" is the tell -
the sentence is asking about a permanent that no longer exists.

It was never a target either. CR 115.10a: "Just because an object or player is
being affected by a spell or ability doesn't make that object or player a
target of that spell or ability" - Witch's Oven's sentence never says "target",
so `AbilityOnStack.targets` is not where the choice can live. It lives on
`AbilityOnStack.cost_sacrificed_card_ids`, the sacrifice twin of the
`cost_exiled_card_id` Back from the Brink already needed for the same reason;
`Game.activate_ability(sacrificed_for_cost=...)` records it and the scenario
harness forwards its own `sacrificing=` into that parameter.

"Instead" is a substitution, not an addition - CR 608.2c's "In some cases,
later text on the card may modify the meaning of earlier text" - so exactly one
of the two counts happens.

The token itself is CR 111.10b: "A Food token is a colorless Food artifact
token with '{2}, {T}, Sacrifice this token: You gain 3 life.'"

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import Scenario


def oven_board(*creatures: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Witch's Oven", *creatures],
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Mountain"] * 5)
    )


def bake(scenario, victim_name: str):
    """Activate the Oven sacrificing `victim_name`, then resolve everything -
    a sacrificed creature may have a dies trigger of its own on the stack
    above the Oven's ability."""
    oven = scenario.creature("Witch's Oven", "alice")
    victim = scenario.creature(victim_name, "alice")
    scenario.activate(oven, sacrificing=[victim])
    while scenario.game.stack:
        scenario.pass_until_resolved()
    return victim


def foods(scenario) -> list:
    return [state for state in scenario.game.battlefield if state.name == "Food Token"]


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_a_small_creature_bakes_one_food():
    """Grizzly Bears is a 2/2, under the printed threshold, so the first
    sentence stands unmodified."""
    scenario = oven_board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bake(scenario, "Grizzly Bears")

    assert len(foods(scenario)) == 1


# --------------------------------------------------------------------------
# Corner cases
# --------------------------------------------------------------------------


def test_a_toughness_four_or_greater_creature_bakes_two():
    """Wurmcoil Engine is a 6/6, so CR 608.2c's later text modifies the
    earlier instruction and two Food tokens are created."""
    scenario = oven_board("Wurmcoil Engine").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bake(scenario, "Wurmcoil Engine")

    assert len(foods(scenario)) == 2


def test_instead_is_a_substitution_not_an_addition():
    """Two, never three: the "instead" replaces the first sentence's count
    rather than adding to it."""
    scenario = oven_board("Wurmcoil Engine").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bake(scenario, "Wurmcoil Engine")

    assert len(foods(scenario)) == 2, "not 1 + 2"


def test_the_sacrificed_creature_is_already_in_the_graveyard_when_this_resolves():
    """CR 602.2b/601.2h pay the cost as the ability is activated, and
    CR 701.21a puts the sacrificed permanent straight into its owner's
    graveyard - so the question the effect asks is about a card that has
    already left the battlefield."""
    scenario = oven_board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    oven = scenario.creature("Witch's Oven", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(oven, sacrificing=[bears])

    assert bears.zone is Zone.GRAVEYARD, "the cost was paid before the ability existed"
    assert scenario.stack_names() == ["Witch's Oven's activated ability"]

    scenario.pass_until_resolved()
    assert len(foods(scenario)) == 1


def test_the_food_token_is_the_predefined_one():
    """CR 111.10b names it: a colorless Food artifact token carrying its own
    printed activated ability."""
    scenario = oven_board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bake(scenario, "Grizzly Bears")

    (food,) = foods(scenario)
    computed = scenario.game.computed_board().of(food)
    assert is_token(food)
    assert computed.colors == ()
    assert "Food" in food.subtypes
    assert "artifact" in [one.value for one in computed.types]
    assert "Sacrifice this token" in (food.card.oracle_text or "")


def test_the_toughness_read_is_the_sacrificed_creatures_and_not_a_survivors():
    """With a big creature left standing and a small one eaten, the count is
    one - the effect reads the card recorded on the ability, not whatever
    else is on the battlefield."""
    scenario = oven_board("Grizzly Bears", "Wurmcoil Engine").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bake(scenario, "Grizzly Bears")

    assert len(foods(scenario)) == 1
    assert scenario.creature("Wurmcoil Engine", "alice").zone is Zone.BATTLEFIELD


def test_the_toughness_read_is_the_printed_one_once_the_card_is_in_a_graveyard():
    """CR 400.7: "An object that moves from one zone to another becomes a new
    object with no memory of, or relation to, its previous existence." A
    Giant Growth on the creature would be gone with the object it was
    modifying, so the only toughness left to read is the printed one - which
    is what this asserts, honestly, rather than pretending the engine tracks
    last-known toughness for this clause.

    Ornithopter is a 0/2, so its printed toughness is under the threshold and
    one Food is baked, whatever happened to it on the battlefield.
    """
    scenario = oven_board("Ornithopter").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    thopter = scenario.creature("Ornithopter", "alice")
    assert thopter.card.toughness == "2"

    bake(scenario, "Ornithopter")

    assert len(foods(scenario)) == 1


def test_the_tap_half_of_the_cost_is_paid_too():
    """ "{T}, Sacrifice a creature" is one cost with two components. Both are
    paid as the ability is activated (CR 602.2b via CR 601.2h), so the Oven is
    tapped afterwards and a second activation the same turn is refused."""
    scenario = oven_board("Grizzly Bears", "Ornithopter").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    oven = scenario.creature("Witch's Oven", "alice")
    bake(scenario, "Grizzly Bears")
    assert oven.tapped

    thopter = scenario.creature("Ornithopter", "alice")
    with pytest.raises(ValueError, match="already tapped"):
        scenario.activate(oven, sacrificing=[thopter])
    assert thopter.zone is Zone.BATTLEFIELD, "the refusal cost nothing"
    assert len(foods(scenario)) == 1
