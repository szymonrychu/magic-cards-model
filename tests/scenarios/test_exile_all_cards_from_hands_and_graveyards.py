"""Scenario: "exile all cards from `<players>`'s hand(s) and graveyard(s)" -
one untargeted-or-targeted instruction that empties two of a player's zones
at once, read off the printed text for every player scope it is printed with:

- **all** - Worldfire: "Exile all cards from all hands and graveyards."
  (covered in `test_life_total_becomes.py`, where the rest of Worldfire is).
- **all opponents'** - Ashiok, Nightmare Weaver's `-10`: "Exile all cards from
  all opponents' hands and graveyards."
- **target player's** - Identity Crisis: "Exile all cards from target
  player's hand and graveyard." (singular zones, one player target).

Every CR number was looked up with `mise run rules:find` in the session that
wrote this file:

- **CR 402.1** - "The hand is where a player holds cards that have been
  drawn."
- **CR 404.1** - "A player's graveyard is their discard pile."
- **CR 406.2** - "To exile an object is to put it into the exile zone from
  whatever zone it's currently in."
- **CR 102.2** - "In a two-player game, a player's opponent is the other
  player." - so the controller's own hand and graveyard are spared.
- **CR 115.1** - "The targets are object(s) and/or player(s) the spell or
  ability will affect." - Identity Crisis targets the player, not a card.
- **CR 606.3** - a loyalty ability is activated at sorcery speed, once per
  turn per permanent.

Card data is the real Scryfall printing for every name below.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def test_ashiok_minus_ten_exiles_every_opponents_hand_and_graveyard_only():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ashiok, Nightmare Weaver"],
            hand=["Lightning Bolt"],
            graveyard=["Shock"],
        )
        .player(
            "bob",
            hand=["Giant Growth", "Island"],
            graveyard=["Grizzly Bears", "Swamp"],
            battlefield=["Runeclaw Bear"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ashiok = scenario.find("Ashiok, Nightmare Weaver", Zone.BATTLEFIELD, "alice")
    ashiok.add_counters(Counter.LOYALTY, 8)

    scenario.activate(ashiok, index=2)
    scenario.pass_until_resolved()

    bob = scenario.player("bob")
    alice = scenario.player("alice")
    assert bob.hand == []
    assert bob.graveyard == []
    assert sorted(card.name for card in scenario.game.exile) == [
        "Giant Growth",
        "Grizzly Bears",
        "Island",
        "Swamp",
    ]
    assert [card.name for card in alice.hand] == ["Lightning Bolt"]
    assert [card.name for card in alice.graveyard] == ["Shock"]
    assert "Runeclaw Bear" in [card.name for card in scenario.game.battlefield]
    assert ashiok.zone is Zone.BATTLEFIELD, "11 loyalty minus 10 leaves Ashiok on 1"


def test_identity_crisis_exiles_the_target_players_hand_and_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Identity Crisis", "Lightning Bolt"],
            graveyard=["Shock"],
            battlefield=["Plains", "Plains", "Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", hand=["Giant Growth"], graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Identity Crisis",
        *scenario.untapped_sources("Plains", "Plains", "Swamp", "Swamp", "Swamp", "Swamp"),
        targets=["bob"],
    )

    bob = scenario.player("bob")
    alice = scenario.player("alice")
    assert bob.hand == []
    assert bob.graveyard == []
    assert sorted(card.name for card in scenario.game.exile) == ["Giant Growth", "Grizzly Bears"]
    assert [card.name for card in alice.hand] == ["Lightning Bolt"]
    assert sorted(card.name for card in alice.graveyard) == ["Identity Crisis", "Shock"]


def test_identity_crisis_may_target_its_own_caster():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Identity Crisis", "Lightning Bolt"],
            graveyard=["Shock"],
            battlefield=["Plains", "Plains", "Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", hand=["Giant Growth"], graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Identity Crisis",
        *scenario.untapped_sources("Plains", "Plains", "Swamp", "Swamp", "Swamp", "Swamp"),
        targets=["alice"],
    )

    alice = scenario.player("alice")
    assert alice.hand == []
    assert sorted(card.name for card in scenario.game.exile) == ["Lightning Bolt", "Shock"]
    # The spell itself finishes resolving after its instruction, so it is the
    # one card in alice's graveyard afterwards (CR 608.2n).
    assert [card.name for card in alice.graveyard] == ["Identity Crisis"]
    assert [card.name for card in scenario.player("bob").hand] == ["Giant Growth"]
