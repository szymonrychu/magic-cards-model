"""Scenario: the symmetric "each player ..." sentence.

Burning Inquiry, Geier Reach Sanitarium and Field of Ruin all print one
instruction whose subject is "each player" and whose later steps drop that
subject entirely ("..., then discards three cards at random"). The engine used
to read none of them, so every one of these cards resolved and did nothing.

The half-read version would have been worse than the unread one, which is why
a step this engine cannot read fails the whole sentence closed: a Burning
Inquiry that discarded without drawing empties a hand and refills nobody's.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 101.4** - "If multiple players would make choices and/or take actions
  at the same time, the active player ... makes any choices required, then the
  next player in turn order", which is APNAP order.
- **CR 608.2e** - "Some spells and abilities have multiple steps or actions,
  denoted by separate sentences or clauses, that involve multiple players. In
  these cases, the choices for the first action are made in APNAP order" - so
  every player finishes step one before anybody starts step two.
- **CR 608.2c** - a resolving spell follows its instructions in the order
  written.
- **CR 701.9b** - "By default, effects that cause a player to discard a card
  allow the affected player to choose which card to discard. Some effects,
  however, require a random discard", so no player is asked here.
- **CR 701.23a / CR 701.23b** - searching a library, and why failing to find a
  stated quality is always legal.
- **CR 701.24a** - shuffling randomises the library.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

TWENTY_ISLANDS = ["Island"] * 20


def test_burning_inquiry_draws_and_discards_for_both_players():
    """Both halves, both sides. The discard is CR 701.9b's random one, so
    neither player is asked which cards to pitch."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Burning Inquiry"],
            battlefield=["Mountain"],
            library=list(TWENTY_ISLANDS),
        )
        .player("bob", library=list(TWENTY_ISLANDS))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Burning Inquiry", *scenario.untapped_sources("Mountain"))

    alice = scenario.player("alice")
    bob = scenario.player("bob")
    # Alice drew three and discarded three; the spell itself is also in her
    # graveyard, so the graveyard holds four and the hand is empty again.
    assert alice.hand == []
    assert len(alice.graveyard) == 4
    assert len(alice.library) == 17
    # Bob was never targeted and never chose anything - "each player" reached
    # him all the same.
    assert len(bob.hand) == 0
    assert len(bob.graveyard) == 3
    assert len(bob.library) == 17


def test_a_player_with_fewer_cards_than_the_discard_just_empties_their_hand():
    """The count is a maximum, not a requirement: a player whose library ran
    out mid-draw discards what they have and nothing more."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Burning Inquiry"],
            battlefield=["Mountain"],
            library=list(TWENTY_ISLANDS),
        )
        .player("bob", library=["Plains", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Burning Inquiry", *scenario.untapped_sources("Mountain"))

    bob = scenario.player("bob")
    assert bob.hand == [], "a two-card library draws two, and both are discarded"
    assert len(bob.graveyard) == 2


def test_geier_reach_sanitarium_runs_the_same_sentence_off_an_activated_ability():
    """The fan-out is a property of the sentence, not of being a spell: the
    identical shape on a land's activated ability reaches both players."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Geier Reach Sanitarium", "Island", "Island"],
            library=list(TWENTY_ISLANDS),
        )
        .player("bob", library=list(TWENTY_ISLANDS))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sanitarium = scenario.find("Geier Reach Sanitarium", Zone.BATTLEFIELD, "alice")
    scenario.activate(sanitarium, *scenario.untapped_sources("Island", "Island"), index=1)
    scenario.resolve_top()

    for username in ("alice", "bob"):
        player = scenario.player(username)
        assert len(player.graveyard) == 1, f"{username} drew one and discarded one"
        assert len(player.library) == 19


def test_field_of_ruin_fetches_a_basic_for_every_player_not_just_its_controller():
    """The point of the card: destroying an opponent's land is symmetric,
    because "each player" - including the one whose land just died - searches
    (CR 701.23a) and puts a basic onto the battlefield."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Field of Ruin", "Island", "Island"],
            library=["Island", "Island", "Island"],
        )
        .player("bob", battlefield=["Hallowed Fountain"], library=["Plains", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    fountain = scenario.find("Hallowed Fountain", Zone.BATTLEFIELD, "bob")
    field = scenario.find("Field of Ruin", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        field,
        *scenario.untapped_sources("Island", "Island"),
        index=1,
        targets=[fountain],
    )
    scenario.resolve_top()

    assert fountain.zone is Zone.GRAVEYARD
    alice_lands = [state.name for state in scenario.game.battlefield if state.controller == "alice"]
    bob_lands = [state.name for state in scenario.game.battlefield if state.controller == "bob"]
    assert alice_lands.count("Island") == 3, "two in play plus the one just fetched"
    assert "Plains" in bob_lands, "the opponent replaces the land they lost"


# -- Weird Harvest: a printed count wider than one, a per-player "may", and
# a reveal-to-hand destination instead of Field of Ruin's mandatory-to-
# battlefield one - the same "each player ..." sentence with every optional
# part actually used at once. `_EACH_PLAYER_SEARCH_RE` used to accept only
# the mandatory singular "a <quality> card, puts it onto the battlefield"
# shape, so this whole sentence - "Each player may search their library for
# up to X creature cards, reveal those cards, put them into their hand, then
# shuffle." - never matched at all.


def test_weird_harvest_each_player_may_search_up_to_x_creature_cards():
    """CR 107.3a: X is announced once, here 2, and applies through the whole
    spell for both players alike - it is not re-announced per player."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Weird Harvest"],
            battlefield=["Forest", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears", "Elvish Mystic", "Island"],
        )
        .player("bob", library=["Grizzly Bears", "Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice_bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    alice_mystic = scenario.find("Elvish Mystic", Zone.LIBRARY, "alice")
    bob_bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "bob")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    scenario.will_take_the_may(True, username="alice", source="Weird Harvest")
    scenario.will_choose_cards(alice_bears, alice_mystic, username="alice", source="Weird Harvest")
    scenario.will_take_the_may(True, username="bob", source="Weird Harvest")
    scenario.will_choose_cards(bob_bears, username="bob", source="Weird Harvest")

    casting = scenario.cast("Weird Harvest")
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    alice = scenario.player("alice")
    bob = scenario.player("bob")
    assert {c.name for c in alice.hand} == {"Grizzly Bears", "Elvish Mystic"}
    assert {c.name for c in bob.hand} == {"Grizzly Bears"}
    assert "Island" in [c.name for c in bob.library], "bob's own non-creature card was untouched"


def test_weird_harvest_a_declining_player_takes_nothing():
    """CR 608.2d: each player's own "may" is a separate, real choice - one
    player taking it never forces the other's answer."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Weird Harvest"],
            battlefield=["Forest", "Forest", "Forest"],
            library=["Grizzly Bears"],
        )
        .player("bob", library=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.will_take_the_may(False, username="alice", source="Weird Harvest")
    scenario.will_take_the_may(False, username="bob", source="Weird Harvest")

    casting = scenario.cast("Weird Harvest")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("alice").hand == []
    assert scenario.player("bob").hand == []
    assert scenario.find("Grizzly Bears", Zone.LIBRARY, "alice").zone is Zone.LIBRARY
    assert scenario.find("Grizzly Bears", Zone.LIBRARY, "bob").zone is Zone.LIBRARY
