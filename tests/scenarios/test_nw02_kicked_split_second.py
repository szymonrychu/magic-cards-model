"""Scenario: "If this spell was kicked, it has split second." (Molten Disaster)

Verified this session with `mise run rules:find`:

- **CR 702.61a** - split second "functions only while the spell with split
  second is on the stack"; as long as it is on the stack, players can't cast
  other spells or activate abilities that aren't mana abilities.
- **CR 702.61b** - players may still activate mana abilities and take special
  actions while it is on the stack.
- **CR 702.33d** - a spell is "kicked" once its controller declared the
  intention to pay a kicker cost; the flag is read off the cast record.
- **CR 604.5** - a static ability of a spell functions while it is on the
  stack, so the conditional grant is checked while the spell sits there.
- **CR 608.2c** - the grant sentence is not an instruction of the resolution;
  the damage sentence after it is what the spell does.

Molten Disaster is the only printing of the "if kicked, it has split second"
template legal in Modern, Pioneer or Standard (Scryfall `o:"was kicked, it has"`
returns it alone); the reader tests the condition through the generic
condition engine, so any "if <condition>, this spell has split second" line
reads the same, and the printed split second keyword (Sudden Shock) keeps
its own file, `test_split_second.py`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(*, bob_battlefield=("Mountain", "Vampire Bats"), alice_hand=("Molten Disaster",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=list(alice_hand),
            battlefield=["Mountain"] * 6,
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            life=20,
            hand=["Lightning Bolt"],
            battlefield=list(bob_battlefield),
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_disaster(scenario, *, kicked, x=1):
    spell = scenario.find("Molten Disaster", Zone.HAND, "alice")
    lands = x + 2 + (1 if kicked else 0)
    scenario.game.cast(
        spell,
        "alice",
        x_value=x,
        kicker=1 if kicked else 0,
        mana_sources=scenario.untapped_sources(*["Mountain"] * lands),
    )
    scenario.pass_priority("alice")
    return spell


def test_kicking_adds_one_red_and_marks_the_spell_kicked():
    scenario = _board()
    spell = _cast_disaster(scenario, kicked=True)

    assert scenario.game.cast_record(spell).kicked == 1
    untapped = [
        card
        for card in scenario.game.permanents_controlled_by("alice")
        if card.name == "Mountain" and not card.tapped
    ]
    assert len(untapped) == 2, "{X}{R}{R} with X=1 plus the kicker {R} is four of six Mountains"


def test_a_kicked_disaster_stops_the_opponent_casting_in_response():
    scenario = _board()
    _cast_disaster(scenario, kicked=True)

    with pytest.raises(ValueError, match="CR 702.61a"):
        scenario.cast("Lightning Bolt", username="bob")


def test_a_kicked_disaster_stops_non_mana_activations():
    scenario = _board()
    _cast_disaster(scenario, kicked=True)
    bats = scenario.creature("Vampire Bats", "bob")

    refusal = scenario.why_cannot_activate(bats, username="bob")
    assert refusal is not None and "CR 702.61a" in refusal
    with pytest.raises(ValueError, match="CR 702.61a"):
        scenario.activate(bats, username="bob")


def test_a_kicked_disaster_still_allows_a_mana_ability():
    """CR 702.61b: mana abilities are untouched."""
    scenario = _board()
    _cast_disaster(scenario, kicked=True)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    assert scenario.why_cannot_activate(mountain, username="bob") is None
    scenario.activate(mountain, username="bob")
    assert mountain.tapped


def test_an_unkicked_disaster_has_no_split_second_so_the_opponent_may_respond():
    scenario = _board()
    spell = _cast_disaster(scenario, kicked=False)
    assert scenario.game.cast_record(spell).kicked == 0

    (source,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", source, username="bob", targets=["alice"])

    assert scenario.player("alice").life == 17


def test_the_unkicked_disaster_lets_the_opponent_activate_an_ability_too():
    scenario = _board()
    _cast_disaster(scenario, kicked=False)
    bats = scenario.creature("Vampire Bats", "bob")

    assert scenario.why_cannot_activate(bats, username="bob") is None


def test_the_kicked_disaster_still_deals_its_damage_and_split_second_ends_with_it():
    scenario = _board()
    _cast_disaster(scenario, kicked=True, x=2)
    scenario.resolve_top()
    scenario.state_based_actions()

    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 18
    assert scenario.find("Vampire Bats", Zone.BATTLEFIELD, "bob").damage == 0, "Bats fly"

    scenario.pass_priority("alice")
    (source,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", source, username="bob", targets=["alice"])
    assert scenario.player("alice").life == 15, "CR 702.61a: it functions only on the stack"


def test_a_second_spell_is_refused_even_for_the_kicked_spells_own_controller():
    """ "Players can't cast other spells": alice, holding priority over her own
    kicked Molten Disaster, cannot cast an instant of her own either."""
    scenario = _board(alice_hand=["Molten Disaster", "Lightning Bolt"])
    spell = scenario.find("Molten Disaster", Zone.HAND, "alice")
    scenario.game.cast(
        spell,
        "alice",
        x_value=0,
        kicker=1,
        mana_sources=scenario.untapped_sources(*["Mountain"] * 3),
    )
    with pytest.raises(ValueError, match="CR 702.61a"):
        scenario.cast("Lightning Bolt", username="alice")
