"""Exile and the battlefield are shared zones - no player has one of their own.

CR 400.1, read whole from disk with `mise run rules:find 400.1` in the session
that wrote this file: "A zone is a place where objects can be during a game.
There are normally seven zones: library, hand, battlefield, graveyard, stack,
exile, and command. Some older cards also use the ante zone. Each player has
their own library, hand, and graveyard. The other zones are shared by all
players."

CR 406.2 (same source): "To exile an object is to put it into the exile zone
from whatever zone it's currently in. An exiled card is a card that's been put
into the exile zone." *The* exile zone - `Game.shared_zones[Zone.EXILE]`, the
one every seat can see - not a pile belonging to whoever's effect moved the
card.

Writing a card into `Player.zones[Zone.EXILE]` builds a per-player exile pile
that has no name in the rules. The card is then invisible to `Game.exile`, to
`Game.targetable_objects` (which walks `shared_zones` for the battlefield and
exile precisely because "`Player.zones` never holds either one"), and to every
seat's board view, so from the table it leaves its old zone and arrives
nowhere. Where the site also appended to `Game.exile` by hand the card ends up
listed *twice* instead, in one real zone and one phantom one, which CR 400.1's
"a zone is a place where objects can be" has no room for either.

Every one of those defects passed its own tests, because `Player.cards_in` was
`zones.setdefault(zone, [])`: an assertion reading `player.cards_in(Zone.EXILE)`
minted the very pile it then read. So the first half of this file is about the
door rather than about any card - a `Player` asked for a shared zone now
refuses, loudly, naming CR 400.1 - and the second half walks the cards that
were going through it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.models import CardState, Player, Zone
from magic_cards_model.models.zone import SharedZoneError
from tests.scenarios.harness import Scenario

# -- the door: a player refuses to be asked for a shared zone ---------------


def _one_player_board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", life=20)
        .build()
    )


@pytest.mark.parametrize(
    ("zone", "accessor"),
    [
        (Zone.BATTLEFIELD, "Game.battlefield"),
        (Zone.EXILE, "Game.exile"),
        (Zone.STACK, "Game.stack"),
        (Zone.COMMAND, "Game.shared_zones[Zone.COMMAND]"),
        (Zone.ANTE, "Game.ante_zone"),
    ],
)
def test_asking_a_player_for_a_shared_zone_is_refused(zone: Zone, accessor: str):
    """`cards_in` is the read that used to mint the pile. It now raises, and
    the message says both why (CR 400.1) and where the real zone is."""
    alice = _one_player_board().player("alice")

    with pytest.raises(SharedZoneError) as raised:
        alice.cards_in(zone)

    assert "CR 400.1" in str(raised.value)
    assert accessor in str(raised.value)


def test_a_refused_read_leaves_no_pile_behind():
    """The whole point: the refusal is not a warning printed on the way to
    minting the pile anyway."""
    alice = _one_player_board().player("alice")

    with pytest.raises(SharedZoneError):
        alice.cards_in(Zone.EXILE)

    assert Zone.EXILE not in alice.zones


def test_adding_a_card_to_a_players_exile_is_refused():
    scenario = _one_player_board()
    alice = scenario.player("alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    with pytest.raises(SharedZoneError) as raised:
        alice.add(bolt, Zone.EXILE)

    assert "Game.exile" in str(raised.value)
    assert bolt.zone is Zone.HAND, "the refused move did not half-happen"
    assert scenario.zones_containing(bolt) == ["alice:hand"]


def test_moving_a_card_into_a_players_battlefield_is_refused():
    scenario = _one_player_board()
    alice = scenario.player("alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    with pytest.raises(SharedZoneError) as raised:
        alice.move(bolt, Zone.BATTLEFIELD)

    assert "Game.battlefield" in str(raised.value)
    assert scenario.zones_containing(bolt) == ["alice:hand"]


def test_moving_a_card_out_of_a_shared_zone_through_a_player_is_refused():
    """The other end of `Player.move`: it reads `cards_in(card.zone)` to lift
    the card out, so a permanent has never been a thing a *player* could move.
    It used to fail with a bare `list.remove(x): x not in list` off an empty
    phantom pile; now it says what is actually wrong."""
    scenario = _one_player_board()
    alice = scenario.player("alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    with pytest.raises(SharedZoneError) as raised:
        alice.move(mountain, Zone.HAND)

    assert "CR 400.1" in str(raised.value)
    assert scenario.zones_containing(mountain) == ["shared:battlefield"]


def test_writing_a_shared_zone_key_into_a_players_zones_is_refused():
    """`Player.zones` is the storage `cards_in` was reaching through. Closing
    only the accessor would leave the dict itself writable."""
    alice = _one_player_board().player("alice")

    with pytest.raises(SharedZoneError):
        alice.zones[Zone.EXILE] = []
    with pytest.raises(SharedZoneError):
        alice.zones.setdefault(Zone.BATTLEFIELD, [])
    with pytest.raises(SharedZoneError):
        alice.zones[Zone.EXILE]

    assert set(alice.zones) == {Zone.LIBRARY, Zone.HAND, Zone.GRAVEYARD, Zone.SIDEBOARD}


def test_a_player_decoded_with_a_shared_zone_pile_is_refused():
    """A game written by an older engine - or by a defect - must not decode
    back into one, silently, as a per-player exile pile."""
    with pytest.raises(SharedZoneError):
        Player.model_validate({"username": "alice", "zones": {"exile": []}})


def test_the_per_player_zones_are_still_perfectly_ordinary():
    """CR 400.1's other half: "Each player has their own library, hand, and
    graveyard." Nothing above may cost a player their own zones."""
    scenario = _one_player_board()
    alice = scenario.player("alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    # Inside the game's own allocator scope, because `CardState.move_to` mints
    # CR 400.7's new zone-change stamp and a raw `Player.move` outside one is
    # the only caller in the engine that would not have opened it.
    with scenario.game._id_allocator_scope():  # noqa: SLF001
        alice.move(bolt, Zone.GRAVEYARD)

    assert alice.cards_in(Zone.GRAVEYARD) == [bolt]
    assert alice.cards_in(Zone.HAND) == []
    assert scenario.zones_containing(bolt) == ["alice:graveyard"]


# -- the sites that were going through it ----------------------------------


def test_cascade_exiles_into_the_shared_exile_zone():
    """CR 702.85a's "exile cards from the top of your library until you exile a
    nonland card". `machines/keywords.cascade` moved each card into the
    caster's own phantom exile pile *and* appended it to `Game.exile`, so every
    exiled card was listed in two zones at once."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Shardless Agent"],
            library=["Mountain", "Lightning Bolt", "Counterspell"],
            battlefield=["Forest", "Island", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Shardless Agent", *scenario.untapped_sources("Forest", "Island", "Forest")
    )
    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(False, source="Shardless Agent")
    scenario.resolve_top()

    # The "you may cast it" was declined, so CR 702.85a's own last clause -
    # "Put the exiled cards on the bottom of that library in a random order" -
    # sends both of them back. That bottoming took each card out of
    # `Game.exile`; nothing took it out of the pile of alice's own it had also
    # been put in, so a card that is on the bottom of a library was still
    # listed in an exile zone as well.
    alice = scenario.player("alice")
    assert Zone.EXILE not in alice.zones
    assert scenario.game.exile == []
    for state in alice.library:
        scenario.assert_in_exactly_one_zone(state)
    assert sorted(state.name for state in alice.library) == [
        "Counterspell",
        "Lightning Bolt",
        "Mountain",
    ]


def test_the_wished_for_card_arrives_in_the_shared_exile_zone():
    """Wish: "You may play a card you own from outside the game this turn."
    CR 108.3b brings the card in; CR 406.2 says which exile zone it lands in."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wish"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            sideboard=["Lightning Bolt"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (bolt,) = [state for state in alice.outside_the_game if state.name == "Lightning Bolt"]

    scenario.will_choose_cards(bolt, username="alice", source="Wish")
    scenario.cast_and_resolve(
        "Wish", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )

    assert scenario.zones_containing(bolt) == ["shared:exile"]
    assert bolt in scenario.game.exile
    assert bolt in scenario.game.targetable_objects()
    permission = scenario.game.play_permission_for(bolt, "alice", PlayAction.PLAY)
    assert permission is not None


def test_hex_magic_exiles_the_hand_into_the_shared_exile_zone():
    """Hex Magic: "Exile all the cards from your hand, then draw that many
    cards. Until the end of your next turn, you may play cards exiled this
    way." """
    scenario = (
        Scenario()
        .automatic_turn_based_actions()
        .player(
            "alice",
            hand=["Hex Magic", "Lightning Bolt", "Grizzly Bears"],
            library=["Mountain"] * 20,
            battlefield=["Mountain"] * 5,
        )
        .player("bob", life=20, library=["Mountain"] * 20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Hex Magic", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )

    exiled = [scenario.find(name, Zone.EXILE) for name in ("Lightning Bolt", "Grizzly Bears")]
    scenario.assert_in_exactly_one_zone(*exiled)
    for state in exiled:
        assert scenario.zones_containing(state) == ["shared:exile"]
        assert state in scenario.game.targetable_objects()


def test_the_web_watchs_two_cards_land_in_the_shared_exile_zone():
    """Interdimensional Web Watch: "exile the top two cards of your library.
    Until the end of your next turn, you may play those cards." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Interdimensional Web Watch"],
            battlefield=["Mountain"],
            library=["Lightning Bolt", "Forest", "Island"],
        )
        .player("bob", library=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Interdimensional Web Watch", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    exiled = [scenario.find(name, Zone.EXILE) for name in ("Lightning Bolt", "Forest")]
    scenario.assert_in_exactly_one_zone(*exiled)
    for state in exiled:
        assert scenario.zones_containing(state) == ["shared:exile"]
        assert state in scenario.game.targetable_objects()


def test_possibility_storms_dig_lands_in_the_shared_exile_zone():
    """Possibility Storm's own dig: "exile cards from the top of their library
    until they exile a card that shares a card type with it"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Possibility Storm"],
            battlefield=["Forest", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            library=["Mountain", "Giant Growth"],
            battlefield=["Mountain", "Llanowar Elves"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Possibility Storm",
        *scenario.untapped_sources("Forest", "Mountain", "Mountain", "Mountain", "Mountain"),
    )
    scenario.pass_priority("alice")
    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", bob_mountain, username="bob", targets=["alice"]
    )
    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(False, source="Possibility Storm")
    scenario.resolve_top()

    # Nothing was cast, so every card this ability touched is bottomed rather
    # than left in exile - what matters here is that nothing was left behind
    # in a pile of bob's own on the way through.
    bob = scenario.player("bob")
    for state in [bolt, *bob.library]:
        scenario.assert_in_exactly_one_zone(state)
    assert Zone.EXILE not in bob.zones
    assert scenario.game.exile == []


def test_gemstone_caverns_exiles_into_the_shared_exile_zone():
    """Gemstone Caverns' CR 103.6a rider: "you may begin the game with Gemstone
    Caverns on the battlefield with a luck counter on it. If you do, exile a
    card from your hand." The exiled card went into a pile of its holder's own,
    which is why four opening-hand tests could read it back off
    `player.cards_in(Zone.EXILE)` and see nothing wrong."""
    from tests.scenarios.test_opening_hand_actions import (
        broodscale,
        dealt,
        devoted,
        series,
        will_take,
    )

    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Gemstone Caverns"}, on_the_play="bob")
    alice = game.player("alice")
    will_take(game, "alice", "Gemstone Caverns")

    match.run_mulligans(game)

    (exiled,) = game.exile
    assert isinstance(exiled, CardState)
    assert exiled.zone is Zone.EXILE
    assert Zone.EXILE not in alice.zones
    assert exiled in game.targetable_objects()
