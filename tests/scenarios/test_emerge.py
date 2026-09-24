"""Scenario: Emerge (CR 702.119), an alternative cost that sacrifices a creature.

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 702.119a** - "'Emerge [cost]' means 'You may cast this spell by
  paying [cost] and sacrificing a creature rather than paying its mana cost'
  and 'If you chose to pay this spell's emerge cost, its total cost is
  reduced by an amount of generic mana equal to the sacrificed creature's
  mana value.'"
- **CR 702.119b** - "Emerge from [quality]": the same, sacrificing a
  [quality] permanent.
- **CR 702.119c** - the permanent is chosen as the emerge cost is chosen
  (CR 601.2b) and sacrificed as the total cost is paid (CR 601.2h).
- **CR 601.2f** - the mana component "can't be reduced to less than {0}";
  **CR 118.7d**'s reduction of generic mana never touches coloured symbols.
- **CR 701.21a** - "A player can't sacrifice something that isn't a
  permanent, or something that's a permanent they don't control."
- **CR 118.9a** - only one alternative cost per spell.

Wretched Gryff (Emerge {5}{U}) is the reported template's first printing,
Vexing Scuttler (Emerge {6}{U}) the second, and Crabomination the only
in-format "Emerge from artifact" printing.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(hand: str, battlefield: list[str], *, bob: list[str] | None = None, graveyard=None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[hand],
            battlefield=battlefield,
            graveyard=list(graveyard or []),
            library=["Island"] * 3,
        )
        .player("bob", battlefield=list(bob or []), library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _emerge(scenario, name, sacrificed, lands, *, zone=Zone.HAND):
    spell = scenario.find(name, zone, "alice")
    return scenario.game.cast(
        spell,
        "alice",
        keyword="emerge",
        choosing=list(sacrificed),
        mana_sources=list(lands),
    )


def test_emerge_is_a_hand_cast_option_under_cr_702_119a():
    (option,) = [o for o in keyword_cast_options(card("Wretched Gryff")) if o.keyword == "Emerge"]
    assert option.zone is Zone.HAND
    assert option.rule == "CR 702.119a"
    assert option.understood


def test_a_sacrificed_creature_reduces_the_emerge_cost_by_its_mana_value():
    """Emerge {5}{U} less Grizzly Bears' mana value 2 is {3}{U}: four Islands."""
    scenario = _board("Wretched Gryff", ["Grizzly Bears", *["Island"] * 4])
    bears = scenario.creature("Grizzly Bears", "alice")
    gryff = _emerge(scenario, "Wretched Gryff", [bears], scenario.untapped_sources(*["Island"] * 4))
    assert gryff.zone is Zone.STACK
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.untapped_sources(username="alice") == []
    hand_before = len(scenario.player("alice").hand)
    scenario.pass_until_resolved()  # the "When you cast this spell, draw a card" trigger
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == hand_before + 1
    assert "Wretched Gryff" in scenario.battlefield_names()


def test_three_islands_do_not_pay_what_is_left():
    """{3}{U} is four mana: three Islands fall short and the cast is undone
    whole (CR 601.2h, CR 733.1) - the Bears is still there."""
    scenario = _board("Wretched Gryff", ["Grizzly Bears", *["Island"] * 3])
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError, match=r"\{3\}\{U\}"):
        _emerge(scenario, "Wretched Gryff", [bears], scenario.untapped_sources(*["Island"] * 3))
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.find("Wretched Gryff", Zone.HAND, "alice").zone is Zone.HAND


def test_the_reduction_takes_generic_mana_only():
    """Serra Angel's mana value 5 removes all five generic: {U} is left, and
    it is still owed (CR 601.2f, CR 118.7d)."""
    scenario = _board("Wretched Gryff", ["Serra Angel", "Island"])
    angel = scenario.creature("Serra Angel", "alice")
    gryff = _emerge(scenario, "Wretched Gryff", [angel], scenario.untapped_sources("Island"))
    assert gryff.zone is Zone.STACK
    assert angel.zone is Zone.GRAVEYARD


def test_a_bigger_creature_never_makes_the_cost_negative():
    """Vexing Scuttler's mana value 8 is more than the Gryff's five generic:
    the mana cost bottoms out at {U} (CR 601.2f: never below {0})."""
    scenario = _board("Wretched Gryff", ["Vexing Scuttler", "Island"])
    scuttler = scenario.creature("Vexing Scuttler", "alice")
    gryff = _emerge(scenario, "Wretched Gryff", [scuttler], scenario.untapped_sources("Island"))
    assert gryff.zone is Zone.STACK


def test_no_creature_chosen_is_refused_with_the_rule():
    scenario = _board("Wretched Gryff", [*["Island"] * 6])
    with pytest.raises(ValueError, match="CR 702.119a"):
        _emerge(scenario, "Wretched Gryff", [], scenario.untapped_sources(*["Island"] * 6))
    assert scenario.find("Wretched Gryff", Zone.HAND, "alice").zone is Zone.HAND


def test_a_land_is_not_a_creature_to_sacrifice():
    scenario = _board("Wretched Gryff", [*["Island"] * 6])
    (land, *others) = scenario.untapped_sources(*["Island"] * 6)
    with pytest.raises(ValueError, match="creature"):
        _emerge(scenario, "Wretched Gryff", [land], others)
    assert land.zone is Zone.BATTLEFIELD


def test_an_opponents_creature_cannot_be_sacrificed():
    """CR 701.21a: only a permanent its controller controls."""
    scenario = _board("Wretched Gryff", [*["Island"] * 4], bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    with pytest.raises(ValueError, match="control"):
        _emerge(scenario, "Wretched Gryff", [bears], scenario.untapped_sources(*["Island"] * 4))
    assert bears.zone is Zone.BATTLEFIELD


def test_emerge_does_not_cast_from_the_graveyard():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Grizzly Bears", *["Island"] * 4],
            graveyard=["Wretched Gryff"],
            library=["Island"] * 3,
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError):
        _emerge(
            scenario,
            "Wretched Gryff",
            [bears],
            scenario.untapped_sources(*["Island"] * 4),
            zone=Zone.GRAVEYARD,
        )
    # Refused for the zone (CR 702.119a casts from wherever the card may be
    # cast normally - a hand), not for anything about the Bears.
    assert bears.zone is Zone.BATTLEFIELD


def test_a_second_printing_reads_its_own_emerge_cost():
    """Vexing Scuttler: Emerge {6}{U} less the Bears' 2 is {4}{U} - five
    Islands, and four are not enough."""
    scenario = _board("Vexing Scuttler", ["Grizzly Bears", *["Island"] * 5])
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError, match=r"\{4\}\{U\}"):
        _emerge(scenario, "Vexing Scuttler", [bears], scenario.untapped_sources(*["Island"] * 4))
    scuttler = _emerge(
        scenario, "Vexing Scuttler", [bears], scenario.untapped_sources(*["Island"] * 5)
    )
    assert scuttler.zone is Zone.STACK
    assert bears.zone is Zone.GRAVEYARD


def test_emerge_from_artifact_sacrifices_an_artifact():
    """Crabomination: "Emerge from artifact {5}{B}{B}" (CR 702.119b). Market
    Gnome is an artifact creature with mana value 1: {4}{B}{B} is left."""
    scenario = _board("Crabomination", ["Market Gnome", *["Swamp"] * 6])
    gnome = scenario.creature("Market Gnome", "alice")
    crab = _emerge(scenario, "Crabomination", [gnome], scenario.untapped_sources(*["Swamp"] * 6))
    assert crab.zone is Zone.STACK
    assert gnome.zone is Zone.GRAVEYARD


def test_emerge_from_artifact_refuses_a_creature_that_is_no_artifact():
    scenario = _board("Crabomination", ["Grizzly Bears", *["Swamp"] * 7])
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError, match="artifact"):
        _emerge(scenario, "Crabomination", [bears], scenario.untapped_sources(*["Swamp"] * 7))
    assert bears.zone is Zone.BATTLEFIELD
