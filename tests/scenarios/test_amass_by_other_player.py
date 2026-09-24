"""Scenario: amass performed by another player, CR 701.47a's keyword action
read off "Its controller amasses <subtype> X" rather than the ordinary "amass
<subtype> N" this engine already reads (see tests/scenarios/test_amass.py).

Azog, Moria's Ruin: "When Azog enters, destroy up to one other target
creature. Its controller amasses Goblins X, where X is that creature's
power. If you controlled that creature, draw a card."

Verified this session with `mise run rules:find`:

- **CR 608.2i** - a look-back reader takes the object's characteristics as
  they were immediately before the event, not after: the destroyed
  creature's power has to be read before `Game.destroy` empties the husk.
- **CR 701.47a/b** - amass's own four-step process, already covered by
  test_amass.py; this file is only about *who* performs it and *whose*
  card draws.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def test_amass_goes_to_the_destroyed_creatures_own_controller():
    """Alice casts Azog targeting Bob's Grizzly Bears (power 2). Bob, not
    Alice, amasses - and since Alice never controlled that creature, she does
    not draw a card."""
    scenario = (
        Scenario()
        .player("alice", hand=["Azog, Moria's Ruin"], battlefield=["Swamp"] * 3)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    hand_before = len(scenario.player("alice").hand)

    scenario.choose_trigger_targets("Azog, Moria's Ruin", [bears])
    scenario.cast_and_resolve("Azog, Moria's Ruin", *scenario.untapped_sources(*["Swamp"] * 3))
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    army = scenario.creature("Goblin Army Token", "bob")
    assert army.counters[Counter.PLUS_ONE] == 2
    assert "Goblin" in scenario.game.characteristics_of(army).subtypes
    assert not any(
        state.name == "Goblin Army Token"
        for state in scenario.game.battlefield
        if scenario.game.controller_of(state).username == "alice"
    )
    assert len(scenario.player("alice").hand) == hand_before - 1  # cast Azog, drew nothing


def test_draw_a_card_only_when_you_controlled_the_destroyed_creature():
    """Alice targets her own Grizzly Bears this time: she amasses her own
    Goblin Army and draws a card, since she controlled the destroyed
    creature."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Azog, Moria's Ruin"],
            battlefield=["Swamp"] * 3 + ["Grizzly Bears"],
            library=["Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.choose_trigger_targets("Azog, Moria's Ruin", [bears])
    scenario.cast_and_resolve("Azog, Moria's Ruin", *scenario.untapped_sources(*["Swamp"] * 3))
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    army = scenario.creature("Goblin Army Token", "alice")
    assert army.counters[Counter.PLUS_ONE] == 2
    # Cast Azog (-1) and destroyed her own Bears, then drew one card (+1).
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1


def test_choosing_no_target_amasses_nothing():
    """CR 115.6: "up to one" may choose zero - Azog then destroys nothing,
    and CR 400.7's anaphora has no referent left to amass for or draw off
    of."""
    scenario = (
        Scenario()
        .player("alice", hand=["Azog, Moria's Ruin"], battlefield=["Swamp"] * 3)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    hand_before = len(scenario.player("alice").hand)

    scenario.choose_trigger_targets("Azog, Moria's Ruin", [])
    scenario.cast_and_resolve("Azog, Moria's Ruin", *scenario.untapped_sources(*["Swamp"] * 3))
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").hand) == hand_before - 1
    assert not any(state.name == "Goblin Army Token" for state in scenario.game.battlefield)
