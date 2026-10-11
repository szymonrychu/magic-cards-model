"""Strike It Rich: "Create a Treasure token." with Flashback {2}{R} (R0c T4).

CR numbers looked up with `mise run rules:find` in the session that wrote this:

- **CR 111.10a** - a Treasure is a colorless Treasure artifact token with
  "{T}, Sacrifice this token: Add one mana of any color."
- **CR 702.34a** - flashback lets the card be cast from the graveyard for the
  flashback cost, and it is exiled instead of going anywhere else when it
  would leave the stack.
- **CR 605.3b** - a mana ability does not use the stack.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from tests.scenarios.harness import Scenario

RICH = "Strike It Rich"


def _board(**kwargs):
    scenario = Scenario().player("alice", **kwargs).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _treasures(scenario):
    return [c for c in scenario.game.battlefield if c.name == "Treasure Token"]


def _flashback(scenario):
    card = scenario.find(RICH, Zone.GRAVEYARD, "alice")
    scenario.game.cast(
        card,
        "alice",
        keyword="Flashback",
        mana_sources=scenario.game.permanents_controlled_by("alice"),
    )
    while scenario.game.stack:
        scenario.resolve_top()
    return card


def test_casting_from_hand_creates_one_untapped_treasure_you_control():
    scenario = _board(hand=[RICH], battlefield=["Mountain"])
    (mountain,) = scenario.untapped_sources("Mountain")
    spell = scenario.cast_and_resolve(RICH, mountain)

    (treasure,) = _treasures(scenario)
    assert not treasure.tapped
    assert scenario.game.controller_of(treasure).username == "alice"
    assert Type.ARTIFACT in treasure.card.types
    assert "Treasure" in treasure.card.subtypes
    assert spell.zone is Zone.GRAVEYARD, "not flashed back: it goes to the graveyard"


def test_the_treasure_is_colorless():
    scenario = _board(hand=[RICH], battlefield=["Mountain"])
    scenario.cast_and_resolve(RICH, *scenario.untapped_sources("Mountain"))
    (treasure,) = _treasures(scenario)
    assert not scenario.game.computed_board().of(treasure).colors


@pytest.mark.parametrize("color", [Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN])
def test_sacrificing_the_treasure_adds_one_mana_of_any_color(color):
    """CR 111.10a: one mana of any color."""
    scenario = _board(hand=[RICH], battlefield=["Mountain"])
    scenario.cast_and_resolve(RICH, *scenario.untapped_sources("Mountain"))
    (treasure,) = _treasures(scenario)

    scenario.activate(treasure, color=color)

    assert scenario.player("alice").mana_pool.floating == {color: 1}
    assert treasure.zone is not Zone.BATTLEFIELD, "sacrificed as a cost"
    assert _treasures(scenario) == []
    assert scenario.stack_names() == [], "CR 605.3b"


def test_a_treasure_cannot_be_used_twice():
    scenario = _board(hand=[RICH], battlefield=["Mountain"])
    scenario.cast_and_resolve(RICH, *scenario.untapped_sources("Mountain"))
    (treasure,) = _treasures(scenario)
    scenario.activate(treasure, color=Color.RED)
    with pytest.raises(ValueError):
        scenario.activate(treasure, color=Color.RED)


def test_flashback_from_the_graveyard_costs_two_and_red_and_makes_a_treasure():
    scenario = _board(graveyard=[RICH], battlefield=["Mountain", "Mountain", "Mountain"])
    card = _flashback(scenario)

    assert len(_treasures(scenario)) == 1
    assert card.zone is Zone.EXILE, "CR 702.34a: exiled instead of the graveyard"
    mountains = [c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Mountain"]
    assert len(mountains) == 3
    assert all(m.tapped for m in mountains)


def test_flashback_cannot_be_paid_without_the_red_mana():
    scenario = _board(graveyard=[RICH], battlefield=["Island", "Island", "Island"])
    card = scenario.find(RICH, Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        scenario.game.cast(
            card,
            "alice",
            keyword="Flashback",
            mana_sources=scenario.game.permanents_controlled_by("alice"),
        )
    assert card.zone is Zone.GRAVEYARD
    assert _treasures(scenario) == []


def test_flashback_cannot_be_paid_with_only_two_lands():
    scenario = _board(graveyard=[RICH], battlefield=["Mountain", "Mountain"])
    card = scenario.find(RICH, Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        scenario.game.cast(
            card,
            "alice",
            keyword="Flashback",
            mana_sources=scenario.game.permanents_controlled_by("alice"),
        )
    assert card.zone is Zone.GRAVEYARD


def test_a_flashed_back_spell_is_not_castable_a_second_time():
    scenario = _board(graveyard=[RICH], battlefield=["Mountain"] * 6)
    card = _flashback(scenario)
    assert card.zone is Zone.EXILE
    with pytest.raises(AssertionError, match="not in graveyard"):
        scenario.find(RICH, Zone.GRAVEYARD, "alice")


def test_treasure_mana_pays_for_the_flashback_cost():
    """A Treasure's red mana plus two Mountains pays {2}{R}: the Treasure's
    sacrifice is a mana ability, so it can be used before paying."""
    scenario = _board(
        hand=[RICH], graveyard=[RICH], battlefield=["Mountain", "Mountain", "Mountain"]
    )
    first = scenario.find(RICH, Zone.HAND, "alice")
    (m1, m2, m3) = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve(RICH, m1)
    assert first.zone is Zone.GRAVEYARD
    (treasure,) = _treasures(scenario)

    graveyard_copy = scenario.find(RICH, Zone.GRAVEYARD, "alice")
    scenario.activate(treasure, color=Color.RED)
    scenario.game.cast(graveyard_copy, "alice", keyword="Flashback", mana_sources=[m2, m3])
    while scenario.game.stack:
        scenario.resolve_top()
    assert graveyard_copy.zone is Zone.EXILE
    assert len(_treasures(scenario)) == 1
