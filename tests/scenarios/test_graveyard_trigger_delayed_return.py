"""A graveyard card's own trigger, with an intervening "if" about where the
entering creature came from, that returns the card at the next end step.

    Whenever a creature enters, if it entered from your graveyard or you cast
    it from your graveyard, return this card from your graveyard to the
    battlefield tapped at the beginning of the next end step.  (Prized Amalgam)

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 113.6m** - an ability whose effect moves the object it's on out of a
  zone functions only in that zone, so Prized Amalgam's trigger works from
  the graveyard.
- **CR 603.4** - the intervening "if" is checked when the creature enters and
  again as the ability resolves; a false condition means no trigger.
- **CR 603.7a** / **CR 603.7c** - resolving creates the delayed return, which
  affects the card only if it is still the same object in the graveyard; one
  that left and came back is a new object (CR 400.7).

Bloodghast is the creature entering from the graveyard. Archfiend's Vessel is
the proof printing for the intervening "if" (legal in Modern and Pioneer,
Scryfall legalities 2026-09-23, in no deck under `magic-cards-model-api/
decks/`): the same clause on an enters trigger about the permanent itself.
No legal printing other than Prized Amalgam carries "return this card from
your graveyard to the battlefield tapped at the beginning of the next end
step" (Scryfall search, 2026-09-23); see MEMORY.md.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _walk_to(scenario, step: Step) -> None:
    while scenario.step is not step:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _amalgam_board(*, hand: list[str], graveyard: list[str], battlefield: list[str] = ()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand,
            graveyard=["Prized Amalgam", *graveyard],
            battlefield=list(battlefield),
            library=["Swamp"] * 5,
        )
        .player("bob", graveyard=["Grizzly Bears"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.find("Prized Amalgam", Zone.GRAVEYARD, "alice")


def test_a_creature_returning_from_your_graveyard_brings_amalgam_back_tapped_at_end_step():
    scenario, amalgam = _amalgam_board(hand=["Swamp"], graveyard=["Bloodghast"])
    bloodghast = scenario.find("Bloodghast", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may(True)

    scenario.play_land("Swamp")
    _resolve_stack(scenario)

    assert bloodghast.zone is Zone.BATTLEFIELD
    assert amalgam.zone is Zone.GRAVEYARD, "not yet - it waits for the end step"
    assert len(scenario.game.delayed_triggers.triggers) == 1

    _walk_to(scenario, Step.END_STEP)

    assert amalgam.zone is Zone.BATTLEFIELD
    assert amalgam.tapped


def test_a_creature_cast_from_hand_does_not_trigger_amalgam():
    scenario, amalgam = _amalgam_board(
        hand=["Grizzly Bears"], graveyard=[], battlefield=["Forest", "Forest"]
    )

    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    _resolve_stack(scenario)
    _walk_to(scenario, Step.END_STEP)

    assert amalgam.zone is Zone.GRAVEYARD
    assert scenario.game.delayed_triggers.triggers == []


def test_a_creature_entering_from_an_opponents_graveyard_does_not_trigger_amalgam():
    """ "Your graveyard": bob's creature coming back from bob's graveyard is
    not one that entered from alice's."""
    scenario, amalgam = _amalgam_board(hand=[], graveyard=[])
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    scenario.game.put_onto_battlefield(bears, "bob")
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    _walk_to(scenario, Step.END_STEP)

    assert amalgam.zone is Zone.GRAVEYARD


def test_a_creature_cast_from_your_graveyard_triggers_amalgam():
    """Kroxa escaping is a cast from the graveyard (CR 702.138a)."""
    scenario, amalgam = _amalgam_board(
        hand=[],
        graveyard=["Kroxa, Titan of Death's Hunger", *["Mishra's Bauble"] * 5],
        battlefield=["Swamp", "Swamp", "Mountain", "Mountain"],
    )
    fuel = [c for c in scenario.player("alice").graveyard if c.name == "Mishra's Bauble"]
    casting = scenario.cast("Kroxa, Titan of Death's Hunger", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Escape", choosing=fuel)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp", "Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    _resolve_stack(scenario)

    assert len(scenario.game.delayed_triggers.triggers) == 1
    _walk_to(scenario, Step.END_STEP)

    assert amalgam.zone is Zone.BATTLEFIELD
    assert amalgam.tapped


def test_amalgam_that_left_the_graveyard_is_not_returned():
    """CR 603.7c: exiled before the end step, it is not in the graveyard the
    delayed ability expects."""
    scenario, amalgam = _amalgam_board(hand=["Swamp"], graveyard=["Bloodghast"])
    scenario.will_take_the_may(True)
    scenario.play_land("Swamp")
    _resolve_stack(scenario)

    scenario.game.exile_permanent(amalgam)
    _walk_to(scenario, Step.END_STEP)

    assert amalgam.zone is Zone.EXILE


def test_two_triggers_return_amalgam_only_once():
    """Two creatures entering from the graveyard make two delayed returns;
    the first brings Amalgam back, the second finds a new object on the
    battlefield rather than the graveyard card and does nothing."""
    scenario, amalgam = _amalgam_board(hand=["Swamp"], graveyard=["Bloodghast", "Bloodghast"])
    scenario.will_take_the_may(True, times=None)
    scenario.play_land("Swamp")
    _resolve_stack(scenario)
    assert len(scenario.game.delayed_triggers.triggers) == 2

    _walk_to(scenario, Step.END_STEP)

    assert amalgam.zone is Zone.BATTLEFIELD
    assert scenario.battlefield_names().count("Prized Amalgam") == 1


# --------------------------------------------------------------------------
# Archfiend's Vessel - the proof printing for the intervening "if"
# --------------------------------------------------------------------------


def test_archfiends_vessel_from_the_graveyard_becomes_a_demon():
    scenario = Scenario().player("alice", graveyard=["Archfiend's Vessel"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vessel = scenario.find("Archfiend's Vessel", Zone.GRAVEYARD, "alice")

    scenario.game.put_onto_battlefield(vessel, "alice")
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)

    assert vessel.zone is Zone.EXILE
    assert [s.name for s in scenario.game.battlefield if s.token] == ["Demon Token"]


def test_archfiends_vessel_cast_from_hand_stays_a_cleric():
    scenario = (
        Scenario()
        .player("alice", hand=["Archfiend's Vessel"], battlefield=["Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    vessel = scenario.cast_and_resolve("Archfiend's Vessel", *scenario.untapped_sources("Swamp"))
    _resolve_stack(scenario)

    assert vessel.zone is Zone.BATTLEFIELD
    assert not [s for s in scenario.game.battlefield if s.token]
    assert scenario.game.intervening_if_notices == []


def test_prized_amalgam_is_handled_by_the_sweep():
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    for clause in card_support(card("Prized Amalgam")).clauses:
        assert clause.outcome == HANDLED, (clause.text, clause.outcome)
