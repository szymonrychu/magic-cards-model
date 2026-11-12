"""A pump and a creature-type change in one sentence - I'm a Doctor, Not a . . .:
"Put a +1/+1 counter on target creature you control. Untap it. Until end of
turn, it gets +1/+1 and becomes a Doctor. (It loses all other creature types.)"

Second printing, worded differently: Nameless Inversion, "Target creature gets
+3/-3 and loses all creature types until end of turn." (no creature type is
named, the pump is a shrink, the order is not duration-first).

Rules, each read with `mise run rules:find` in the session that wrote this:

- CR 613.4c: the pump is a sublayer 7c modification and adds to a +1/+1 counter
  (also 7c).
- CR 613.1d: the type change is layer 4; CR 205.1a: setting a creature type
  replaces the existing creature types (the card types stay), and removing a
  type leaves the card types alone.
- CR 611.2a / CR 514.2: one duration for the whole instruction, ending in the
  cleanup step; CR 611.2c: the set of affected objects is fixed when it begins.
- CR 704.5f: a creature with toughness 0 or less is put into its owner's
  graveyard as a state-based action (Nameless Inversion's -3 on a 2-toughness
  creature).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(spell, lands, *, mine=("Grizzly Bears",), theirs=(), hand=()):
    scenario = (
        Scenario()
        .player("alice", hand=[spell, *hand], battlefield=[*lands, *mine], library=["Island"] * 5)
        .player("bob", battlefield=list(theirs), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, spell, target, *land_names):
    scenario.cast_and_resolve(
        spell, *scenario.untapped_sources(*land_names, username="alice"), targets=[target]
    )


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _into_cleanup(scenario) -> None:
    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)


@pytest.mark.parametrize("name", ["I'm a Doctor, Not a . . .", "Nameless Inversion"])
def test_the_whole_card_is_handled(name):
    bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
    assert not bad, bad


# --------------------------------------------------------------------------
# I'm a Doctor, Not a . . .
# --------------------------------------------------------------------------

DOCTOR = "I'm a Doctor, Not a . . ."


def test_a_counter_a_pump_and_the_doctor_type_all_land():
    scenario = _board(DOCTOR, ["Forest"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, DOCTOR, bears, "Forest")
    chars = _chars(scenario, bears)
    assert bears.counter_count("+1/+1") == 1
    assert (chars.power, chars.toughness) == (4, 4), "2/2 + counter + the +1/+1"
    assert chars.subtypes == ("Doctor",), "CR 205.1a: Bear is replaced, not added to"
    assert Type.CREATURE in chars.types


def test_the_creature_is_untapped():
    scenario = _board(DOCTOR, ["Forest"])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tap()
    _cast(scenario, DOCTOR, bears, "Forest")
    assert not bears.tapped


def test_every_creature_type_goes_not_only_the_first():
    scenario = _board(DOCTOR, ["Forest"], mine=("Llanowar Elves",))
    elves = scenario.creature("Llanowar Elves", "alice")
    assert len(_chars(scenario, elves).subtypes) == 2
    _cast(scenario, DOCTOR, elves, "Forest")
    assert _chars(scenario, elves).subtypes == ("Doctor",)


def test_the_pump_and_the_type_end_in_cleanup_but_the_counter_stays():
    scenario = _board(DOCTOR, ["Forest"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, DOCTOR, bears, "Forest")
    _into_cleanup(scenario)
    chars = _chars(scenario, bears)
    assert (chars.power, chars.toughness) == (3, 3), "the counter is permanent"
    assert chars.subtypes == ("Bear",)


def test_a_creature_that_arrives_later_is_not_a_doctor():
    """CR 611.2c: the set of objects is fixed when the spell resolves."""
    scenario = _board(DOCTOR, ["Forest"], hand=("Hill Giant",))
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast(scenario, DOCTOR, bears, "Forest")
    giant = scenario.game.put_onto_battlefield(
        scenario.find("Hill Giant", Zone.HAND, "alice"), "alice"
    )
    assert _chars(scenario, giant).subtypes == ("Giant",)


def test_the_spell_cannot_target_an_opponents_creature():
    scenario = _board(DOCTOR, ["Forest"], theirs=("Hill Giant",))
    giant = scenario.creature("Hill Giant", "bob")
    with pytest.raises(ValueError):
        scenario.cast_onto_stack(
            DOCTOR, *scenario.untapped_sources("Forest", username="alice"), targets=[giant]
        )
    assert giant.counter_count("+1/+1") == 0


# --------------------------------------------------------------------------
# Nameless Inversion
# --------------------------------------------------------------------------

INVERSION = "Nameless Inversion"


def test_nameless_inversion_shrinks_and_strips_every_creature_type():
    scenario = _board(INVERSION, ["Swamp", "Swamp"], mine=("Indomitable Ancients",))
    ancients = scenario.creature("Indomitable Ancients", "alice")
    assert len(_chars(scenario, ancients).subtypes) == 2
    _cast(scenario, INVERSION, ancients, "Swamp", "Swamp")
    chars = _chars(scenario, ancients)
    assert (chars.power, chars.toughness) == (5, 7)
    assert chars.subtypes == ()
    assert Type.CREATURE in chars.types


def test_nameless_inversion_kills_a_creature_it_shrinks_to_zero_toughness():
    scenario = _board(INVERSION, ["Swamp", "Swamp"], theirs=("Grizzly Bears",))
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, INVERSION, bears, "Swamp", "Swamp")
    assert bears.zone is Zone.GRAVEYARD


def test_nameless_inversion_wears_off_in_cleanup():
    scenario = _board(INVERSION, ["Swamp", "Swamp"], mine=("Indomitable Ancients",))
    ancients = scenario.creature("Indomitable Ancients", "alice")
    _cast(scenario, INVERSION, ancients, "Swamp", "Swamp")
    _into_cleanup(scenario)
    chars = _chars(scenario, ancients)
    assert (chars.power, chars.toughness) == (2, 10)
    assert len(chars.subtypes) == 2
