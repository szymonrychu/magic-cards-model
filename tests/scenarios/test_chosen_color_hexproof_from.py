"""Becoming a chosen colour and gaining hexproof from it - Mondo Gecko: "{1},
Discard a card: Until end of turn, Mondo Gecko becomes the color of your
choice and gains hexproof from that color."

- CR 608.2d: the colour is chosen as the ability resolves.
- CR 105.3 / CR 613.1e: "becomes" a colour replaces every previous colour -
  a layer 5 effect.
- CR 702.11d: "Hexproof from [quality]" means "This permanent can't be the
  target of [quality] spells your opponents control or abilities your
  opponents control from [quality] sources" - granted in layer 6 (CR
  613.1f), so a spell of another colour, or its controller's own spell of
  that colour, can still target it.
- CR 514.2: both end at cleanup.

Off-set proof (legal in Modern, in no deck list): Distorting Lens - "{T}:
Target permanent becomes the color of your choice until end of turn." - the
same colour choice with a target instead of the source, the duration
trailing, and no hexproof rider.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone

from .harness import Scenario

GECKO = "Mondo Gecko"


def _colors(scenario, permanent):
    return scenario.game.computed_board().of(permanent).colors


def _abilities(scenario, permanent):
    return scenario.game.computed_board().of(permanent).abilities


def _board(*, hand=("Forest",), alice=(), bob_hand=()):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[GECKO, "Island", *alice],
            library=["Island"] * 5,
        )
        .player("bob", hand=list(bob_hand), battlefield=["Mountain", "Swamp"])
        .build()
    )


def _activate_gecko(scenario, color):
    gecko = scenario.creature(GECKO, "alice")
    discard = scenario.player("alice").hand[0]
    scenario.will_choose(color.value, username="alice")
    scenario.activate(
        gecko,
        *scenario.untapped_sources("Island", username="alice"),
        discarding=[discard],
    )
    scenario.resolve_top()
    return gecko


def test_gecko_becomes_the_chosen_color_only():
    """CR 105.3: red replaces blue."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    gecko = _activate_gecko(scenario, Color.RED)

    assert set(_colors(scenario, gecko)) == {Color.RED}


def test_gecko_gains_hexproof_from_the_chosen_color():
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    gecko = _activate_gecko(scenario, Color.RED)

    assert "Hexproof from red" in _abilities(scenario, gecko)


def test_the_discard_is_paid():
    scenario = _board(hand=("Forest",))
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _activate_gecko(scenario, Color.RED)

    assert [card.name for card in scenario.player("alice").graveyard] == ["Forest"]


def test_an_opponents_spell_of_that_color_cannot_target_it():
    scenario = _board(bob_hand=("Lightning Bolt",))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gecko = _activate_gecko(scenario, Color.RED)

    casting = scenario.cast("Lightning Bolt", username="bob")
    with pytest.raises(ValueError, match="hexproof from red"):
        casting.choose_targets([gecko])


def test_an_opponents_spell_of_another_color_can_target_it():
    scenario = _board(bob_hand=("Giant Growth",))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gecko = _activate_gecko(scenario, Color.RED)

    casting = scenario.cast("Giant Growth", username="bob")
    casting.choose_targets([gecko])


def test_its_controllers_own_spell_of_that_color_can_target_it():
    """CR 702.11d: only spells "your opponents control"."""
    scenario = _board(hand=("Forest", "Lightning Bolt"), alice=["Mountain"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gecko = _activate_gecko(scenario, Color.RED)

    casting = scenario.cast("Lightning Bolt", username="alice")
    casting.choose_targets([gecko])


def test_both_end_at_cleanup():
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gecko = _activate_gecko(scenario, Color.RED)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)
    scenario.turn_based_actions()

    assert set(_colors(scenario, gecko)) == {Color.BLUE}
    assert "Hexproof from red" not in _abilities(scenario, gecko)


def test_a_second_activation_changes_the_color_and_adds_a_second_hexproof():
    """The later layer 5 effect wins (CR 613.7); both hexproof grants stay
    until cleanup."""
    scenario = _board(hand=("Forest", "Forest"), alice=["Island"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_gecko(scenario, Color.RED)

    gecko = scenario.creature(GECKO, "alice")
    scenario.will_choose(Color.BLACK.value, username="alice")
    scenario.activate(
        gecko,
        *scenario.untapped_sources("Island", username="alice"),
        discarding=[scenario.player("alice").hand[0]],
    )
    scenario.resolve_top()

    assert set(_colors(scenario, gecko)) == {Color.BLACK}
    abilities = _abilities(scenario, gecko)
    assert "Hexproof from red" in abilities
    assert "Hexproof from black" in abilities


def test_the_ability_cannot_be_activated_without_a_card_to_discard():
    """CR 602.2b / CR 118.3: an unpayable discard cost refuses the
    activation, and nothing changes."""
    scenario = _board(hand=())
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gecko = scenario.creature(GECKO, "alice")

    with pytest.raises(ValueError):
        scenario.activate(gecko, *scenario.untapped_sources("Island", username="alice"))
    assert set(_colors(scenario, gecko)) == {Color.BLUE}


# -- Distorting Lens ------------------------------------------------------------


def test_distorting_lens_makes_a_colorless_permanent_the_chosen_color():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Distorting Lens"], library=["Island"] * 5)
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lens = scenario.find("Distorting Lens", Zone.BATTLEFIELD, "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.will_choose(Color.GREEN.value, username="alice")

    scenario.activate(lens, targets=[ring])
    scenario.resolve_top()

    assert set(_colors(scenario, ring)) == {Color.GREEN}
    assert "Hexproof from green" not in _abilities(scenario, ring)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup
    scenario.turn_based_actions()
    assert set(_colors(scenario, ring)) == set()
