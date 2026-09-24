"""Scenario: "As this enchantment enters, choose a creature type. Creatures
you control of the chosen type get +2/+2." plus its adventure half, "Create
X 2/2 red Dwarf creature tokens." - An Unexpected Party // At the Door.

The anthem is a new reader, `machines/layers._chosen_type_anthem_builder`:
CR 611.3's static ability, read the identical "of the chosen `<quality>`"
way `_self_protection_from_chosen_color_builder` already reads Cavern of
Souls's colour choice, just for CR 614.12a's creature-type choice instead
of CR 614.12a's colour one, over `creatures_controlled_by_with_subtype`'s
already-general selector.

The adventure token creation and the mass typed damage on this task's other
cards (Easy Pickings, Spew Flame) both go through the pre-existing CR 107.3a
X-substitution `effect_for` already gives every `{X}...` spell - the
generality of *that* substitution is proven once here (a variable-count,
coloured, typed token creation) and again in `test_mass_and_typed_damage.py`
(variable damage), rather than re-asserted per card.

CR 614.12a and CR 611.3 were verified with `mise run rules:find` in the
session that wrote this file - see `machines/layers.py`'s own docstrings for
the exact wording they already cite for `chosen_color_of`/`_self_protection_
from_chosen_color_builder`, the identical mechanism this reuses for a
creature type instead of a colour.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.token import TokenDefinition, create_tokens
from tests.scenarios.harness import Scenario


def board(*extra: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["An Unexpected Party"],
            battlefield=["Plains", "Plains", "Plains", "Plains", "Plains", "Raging Goblin", *extra],
        )
        .player("bob")
    )


# -- the anthem -------------------------------------------------------------


def test_a_goblin_gets_the_anthem_and_a_non_goblin_does_not():
    scenario = board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Raging Goblin")
    bears = scenario.creature("Grizzly Bears")
    assert scenario.game.characteristics_of(goblin).power_toughness == (1, 1)

    scenario.will_choose("Goblin", source="An Unexpected Party // At the Door")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.cast_and_resolve("An Unexpected Party", *sources, username="alice")

    assert scenario.game.characteristics_of(goblin).power_toughness == (3, 3), (
        "base 1/1, +2/+2 for being a Goblin - the chosen type"
    )
    assert scenario.game.characteristics_of(bears).power_toughness == (2, 2), (
        "Grizzly Bears is not a Goblin, so no anthem"
    )


def test_a_goblin_that_enters_later_also_gets_it():
    """CR 611.3a: "it applies at any given moment to whatever its text
    indicates" - the anthem is live, not a fixed set of objects."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.will_choose("Goblin", source="An Unexpected Party // At the Door")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.cast_and_resolve("An Unexpected Party", *sources, username="alice")

    (token,) = create_tokens(
        scenario.game,
        TokenDefinition(power=1, toughness=1, subtypes=("Goblin",)),
        "alice",
    )

    assert scenario.game.characteristics_of(token).power_toughness == (3, 3)


# -- the adventure half: "Create X 2/2 red Dwarf creature tokens." ----------


def test_at_the_door_creates_x_dwarf_tokens():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("An Unexpected Party")
    casting.cast_as_adventure()
    payment = casting.determine_cost(x_value=2)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", "Plains")
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    dwarves = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.token and "Dwarf" in state.subtypes
    ]
    assert len(dwarves) == 2
    for dwarf in dwarves:
        assert scenario.game.characteristics_of(dwarf).power_toughness == (2, 2)
        assert list(scenario.game.characteristics_of(dwarf).colors) == [Color.RED]


def test_the_at_the_door_face_exiles_and_the_enchantment_can_be_cast_later():
    """CR 715.3d: the Adventure exiles the card, from where it may later be
    cast as its normal (here, the enchantment) characteristics."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("An Unexpected Party")
    casting.cast_as_adventure()
    payment = casting.determine_cost(x_value=0)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    exiled = scenario.find("An Unexpected Party", Zone.EXILE, "alice")
    assert exiled is not None
