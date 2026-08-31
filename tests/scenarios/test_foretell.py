"""Foretell: pay {2}, exile it face down, cast it later (CR 702.143, CR 116.2h).

CR 702.143a: "Foretell is a keyword that functions while the card with foretell
is in a player's hand. Any time a player has priority during their turn, that
player may pay {2} and exile a card with foretell from their hand face down."
CR 116.2h says the same from the special-actions side, and CR 702.143b confirms
it does not use the stack.

The two costs are easy to swap and this file is where that would show: the {2}
puts the card away, and the *foretell cost* printed on the card - Lupine
Harbingers' `Foretell {4}{G}{G}` - is what it is later cast for.

Unlike plot (CR 702.170a), foretell is not restricted to a main phase or an
empty stack. It only has to be the foretelling player's own turn.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import MarkedExile, keyword_cast_options
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileMarker
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lupine Harbingers"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Island"])
    )


def foretell_it(scenario, *, sources: int = 2) -> None:
    harbingers = scenario.find("Lupine Harbingers", Zone.HAND, "alice")
    action = MarkedExile.foretell(scenario.game, harbingers, "alice")
    forests = scenario.untapped_sources(*["Forest"] * sources, username="alice")
    scenario.pay_with(action.begin_paying(), *forests)
    action.take()


def alices_next_main(scenario) -> None:
    for _ in range(60):
        scenario.advance()
        if scenario.step is Step.UNTAP:
            # Turn-based actions are off for this board, so the untap step is
            # driven by hand - without it every Forest is still tapped.
            scenario.game.untap_step()
        if scenario.turn.active_player == "alice" and scenario.step is Step.PRECOMBAT_MAIN:
            return
    raise AssertionError("never got back to alice's main phase")


# -- the special action -----------------------------------------------------


def test_foretelling_costs_two_generic_and_not_the_foretell_cost():
    """CR 116.2h: the special action's cost is {2}. `Foretell {4}{G}{G}` is not it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    harbingers = scenario.find("Lupine Harbingers", Zone.HAND)
    action = MarkedExile.foretell(scenario.game, harbingers, "alice")

    assert action.cost.mana == ManaCost.parse("{2}")


def test_a_foretold_card_is_exiled_face_down_and_marked():
    """CR 702.143a exiles it face down; CR 406.3 is why that is worth recording."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    foretell_it(scenario)

    foretold = scenario.find("Lupine Harbingers", Zone.EXILE)
    assert foretold.zone is Zone.EXILE
    assert foretold.face_down is True
    assert foretold.exile_annotation is not None
    assert foretold.exile_annotation.marker is ExileMarker.FORETOLD


def test_foretell_is_allowed_outside_a_main_phase():
    """CR 116.2h: "any time they have priority during their turn" - unlike plot."""
    scenario = board().build()
    scenario.start_at(Step.UPKEEP)

    foretell_it(scenario)

    assert scenario.find("Lupine Harbingers", Zone.EXILE).zone is Zone.EXILE


def test_foretell_is_refused_on_an_opponents_turn():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.turn.active_player == "alice":
        scenario.advance()

    harbingers = scenario.find("Lupine Harbingers", Zone.HAND, "alice")

    with pytest.raises(ValueError, match="own turn"):
        MarkedExile.foretell(scenario.game, harbingers, "alice")


def test_a_card_without_foretell_cannot_be_foretold():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND)

    with pytest.raises(ValueError, match="no foretell ability"):
        MarkedExile.foretell(scenario.game, bears, "alice")


# -- casting it later -------------------------------------------------------


def test_the_foretell_cost_is_what_it_is_cast_for():
    (option,) = keyword_cast_options(card("Lupine Harbingers"))

    assert option.zone is Zone.EXILE
    assert option.pays_mana_cost is False
    assert str(option.cost) == "{4}{G}{G}"


def test_a_foretold_card_cannot_be_cast_the_turn_it_was_foretold():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    foretell_it(scenario)

    casting = scenario.cast("Lupine Harbingers", from_zone=Zone.EXILE)

    with pytest.raises(ValueError, match="later turn"):
        casting.use_keyword("Foretell")


def test_a_foretold_card_is_cast_from_exile_for_its_foretell_cost():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    foretell_it(scenario)
    alices_next_main(scenario)

    casting = scenario.cast("Lupine Harbingers", from_zone=Zone.EXILE)
    casting.use_keyword("Foretell")

    assert casting.total_cost.mana == ManaCost.parse("{4}{G}{G}")

    forests = scenario.untapped_sources(*["Forest"] * 6, username="alice")
    scenario.pay_with(casting.begin_paying(), *forests)
    on_stack = scenario.put_on_stack(casting)
    # A foretold card is cast out of exile, a shared zone. Casting it must
    # take it out of exile as it goes onto the stack, not leave it in both -
    # the bug `Game.put_on_stack` used to have (see `zones_containing`).
    assert scenario.zones_containing(on_stack) == ["shared:stack"]

    wolf = scenario.resolve_top()

    assert wolf.zone is Zone.BATTLEFIELD
    assert wolf not in scenario.game.exile
    assert wolf.face_up is True


def test_foretell_cannot_be_used_on_a_card_still_in_hand():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lupine Harbingers")

    with pytest.raises(ValueError, match="from the exile"):
        casting.use_keyword("Foretell")


def test_an_unmarked_card_in_exile_is_not_foretold():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", exile=["Lupine Harbingers"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lupine Harbingers", from_zone=Zone.EXILE)

    with pytest.raises(ValueError, match="not foretold"):
        casting.use_keyword("Foretell")


def test_put_on_stack_takes_a_card_out_of_exile_not_just_the_owners_hand():
    """`Game.put_on_stack` used to only search the caster's own player-zones.

    Exile is a shared zone (CR 400.2), so a card sitting there when
    `put_on_stack` is called - foretold, plotted, an Adventure's exiled half,
    or anything else exiled with "you may cast this" - was left in exile
    *and* appended to the stack. Called here directly, without going through
    `Casting`, so nothing else can be papering over the bug.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", exile=["Lupine Harbingers"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    harbingers = scenario.find("Lupine Harbingers", Zone.EXILE, "alice")

    scenario.game.put_on_stack(harbingers, "alice")

    assert scenario.zones_containing(harbingers) == ["shared:stack"]


@pytest.mark.xfail(
    reason=(
        "measured, and not what an earlier reason here claimed: "
        "machines/replacement.py *is* wired in - Game.enter_the_battlefield "
        "calls apply_replacements, _self_enters_modifiers reads the card's own "
        "CR 614.12 line, and parse_replacement_effects already returns this one "
        "as ENTERS_WITH with variable_amount set. What is missing is the value "
        "of X. ExileAnnotation.turn_exiled does record the turn (turn_exiled=1 "
        "in exile), but CR 400.7 makes the spell a new object: "
        "CardState.move_to drops exile_annotation on the exile-to-stack move, "
        "and machines/casting.py makes that move *before* it calls "
        "Game.note_cast, so nothing captures the annotation on the way past. "
        "CastRecord (models/game.py) has no field for it either, so "
        "_self_enters_modifiers falls through to CR 107.3m's announced X, which "
        "is 0 for a spell with no {X} in its cost. Three files: capture the "
        "annotation before the move (machines/casting.py), carry it "
        "(models/game.py's CastRecord), and read 'the number of turns you've "
        "begun since it was foretold' off it (machines/replacement.py)."
    ),
    strict=True,
)
def test_it_enters_with_a_counter_for_each_turn_since_it_was_foretold():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    foretell_it(scenario)
    alices_next_main(scenario)

    casting = scenario.cast("Lupine Harbingers", from_zone=Zone.EXILE)
    casting.use_keyword("Foretell")
    forests = scenario.untapped_sources(*["Forest"] * 6, username="alice")
    scenario.pay_with(casting.begin_paying(), *forests)
    scenario.put_on_stack(casting)
    wolf = scenario.resolve_top()

    assert wolf.counter_count("+1/+1") >= 1
