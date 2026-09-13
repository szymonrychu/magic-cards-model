"""Every card an effect shows from the top of a library is recorded for the
players it was shown to, following the verb the card prints.

A look shows a card to one player and a reveal shows it to all of them; the
two are otherwise the same act, and neither moves the card. `Game.known_to`
reads what was recorded, so an effect that shows cards without recording them
leaves every seat knowing less than the table does.

- **CR 701.20a** - "To reveal a card, show that card to all players for a
  brief time." Goblin Charbelcher's "Reveal cards from the top of your library
  until you reveal a land card", Atraxa, Grand Unifier's "reveal the top ten
  cards", Duskwatch Recruiter's "You may reveal a creature card from among
  them", Goblin Guide's reveal and explore's reveal are all public records.
- **CR 701.20b** - "Revealing a card doesn't cause it to leave the zone it's
  in", so each record is of a card still in the library.
- **CR 701.20e** - "Looking at a card follows the same rules as revealing a
  card, except that the card is shown only to the specified player." Mishra's
  Bauble's, Merfolk Observer's and Rootwater Mystic's "Look at the top card of
  target player's library" and Duskwatch Recruiter's "Look at the top three
  cards of your library" are records for the controller alone - one way: the
  library's owner does not learn what was seen.
- **CR 701.20d** - "If cards in a player's library are shuffled or otherwise
  reordered, any revealed cards that are reordered stop being revealed and
  become new objects." A fetchland's shuffle (CR 701.24a), a card put on top,
  and "put the rest on the bottom of your library" in any or a random order
  all end a library record.
- **CR 400.7** - a card that changes zones is a new object, so a revealed card
  that leaves the library for a graveyard is no longer the card that was shown.
- **CR 121.1** - a draw puts the top card of a library into its owner's hand;
  a record still live at that move is carried to the hand (a knowledge policy,
  not a CR rule - see `scenarios/test_known_card_drawn_stays_known.py`).
- **CR 608.2c** - each effect's sentences run in the order printed, so every
  card is shown before the sentence that moves it.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import CardSplit, DecisionKind, ScriptedAnswer
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import PlayedScenario, Scenario
from tests.scenarios.test_explore import _board as amalia_board
from tests.scenarios.test_explore import _explore
from tests.scenarios.test_reveal_one_per_card_type import TOP_TEN


def known(game: Game, viewer: str) -> list[tuple[str, Zone, int | None, bool]]:
    return [
        (entry.card_name, entry.zone, entry.index_from_top, entry.carried)
        for entry in game.known_to(viewer)
    ]


def _bauble_board(
    *bob_library: str,
    alice_library: list[str] | None = None,
    bob_battlefield: list[str] | None = None,
) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mishra's Bauble"], library=alice_library or [])
        .player("bob", library=list(bob_library), battlefield=bob_battlefield or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_bauble(scenario: PlayedScenario, target: str) -> None:
    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD)
    scenario.activate(bauble, username="alice", targets=[target])
    scenario.pass_until_resolved()


# -- a look at the top card (CR 701.20e) --------------------------------------


def test_a_bauble_look_at_the_opponents_library_is_known_to_the_looker_on_top():
    scenario = _bauble_board("Lightning Bolt", "Island")
    bob = scenario.player("bob")
    bolt = bob.library[0]

    _activate_bauble(scenario, "bob")

    game = scenario.game
    assert known(game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    (entry,) = game.known_to("alice")
    assert entry.card_id == bolt.id
    assert entry.owner == "bob"
    assert entry.source == "Mishra's Bauble"
    (look,) = game.reveals
    assert look.viewers == ["alice"], "CR 701.20e: shown only to the player who looked"
    assert look.zone is Zone.LIBRARY
    assert look.revealed_by == "bob"
    assert look.library_epoch == bob.library_epoch
    assert look.zone_change_stamp == bolt.zone_change_stamp
    assert look.turn == game.turn.turns_taken


def test_the_owner_of_the_looked_at_library_does_not_learn_the_card():
    scenario = _bauble_board("Lightning Bolt", "Island")

    _activate_bauble(scenario, "bob")

    assert known(scenario.game, "bob") == []


def test_a_look_at_your_own_library_is_known_to_you_alone():
    scenario = _bauble_board("Island", alice_library=["Lightning Bolt", "Forest"])
    alice = scenario.player("alice")

    _activate_bauble(scenario, "alice")

    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    assert known(scenario.game, "bob") == []
    (look,) = scenario.game.reveals
    assert look.viewers == ["alice"]
    assert look.library_epoch == alice.library_epoch


def test_the_owner_fetching_shuffles_the_look_away():
    scenario = _bauble_board(
        "Lightning Bolt", "Plains", "Island", bob_battlefield=["Flooded Strand"]
    )
    _activate_bauble(scenario, "bob")
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]

    scenario.pass_priority()
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    scenario.activate(strand, username="bob")
    scenario.pass_until_resolved()

    assert known(scenario.game, "alice") == []


def test_the_owner_drawing_the_looked_at_card_carries_it_to_the_looker():
    scenario = _bauble_board("Lightning Bolt", "Island")
    _activate_bauble(scenario, "bob")

    scenario.draw(username="bob")

    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.HAND, None, True)]
    assert known(scenario.game, "bob") == []


def test_a_card_put_on_top_above_the_looked_at_card_voids_the_look():
    """Subtlety puts bob's Grizzly Bears spell on top. The looked-at Bolt is
    second from the top now, not "known at index 1": the library it was on
    top of was reordered, so the record ends (CR 701.20d)."""
    scenario = (
        Scenario()
        .player(
            "bob",
            hand=["Grizzly Bears"],
            library=["Lightning Bolt", "Island"],
            battlefield=["Forest", "Forest"],
        )
        .player("alice", hand=["Subtlety"], battlefield=["Island"] * 4 + ["Mishra's Bauble"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("bob")
    _activate_bauble(scenario, "bob")
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]

    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    islands = scenario.untapped_sources(*(["Island"] * 4), username="alice")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")
    scenario.pass_priority("bob")
    scenario.choose_trigger_targets("Subtlety", [bears])
    scenario.will_choose_top(True, username="bob")
    scenario.cast_onto_stack("Subtlety", *islands, username="alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    bob = scenario.player("bob")
    assert bob.library[0] is bears
    assert bob.library[1].name == "Lightning Bolt"
    assert known(scenario.game, "alice") == []


# -- replay and round trip -----------------------------------------------------


def test_a_decoded_game_knows_the_same_look_and_still_carries_it_on_a_draw():
    scenario = _bauble_board("Lightning Bolt", "Island")
    _activate_bauble(scenario, "bob")

    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))

    assert decoded.known_to("alice") == scenario.game.known_to("alice")
    assert decoded.known_to("bob") == []
    decoded.draw_cards("bob", 1)
    assert known(decoded, "alice") == [("Lightning Bolt", Zone.HAND, None, True)]


def test_replaying_the_look_from_one_snapshot_records_it_identically():
    scenario = _bauble_board("Lightning Bolt", "Island")
    snapshot = scenario.game.model_dump(mode="json")

    replays = []
    for _ in range(2):
        game = Game.model_validate(snapshot)
        _activate_bauble(PlayedScenario(game), "bob")
        replays.append(game)

    first, second = replays
    assert known(first, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    assert first.known_to("alice") == second.known_to("alice")
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


# -- the mechanic, not the card ------------------------------------------------


def test_merfolk_observer_enters_and_looks_at_the_top_card_of_target_players_library():
    """ "When this creature enters, look at the top card of target player's
    library." - a triggered ability, not an activated one, and a printing in
    neither deck pool."""
    scenario = (
        Scenario()
        .player("alice", hand=["Merfolk Observer"])
        .player("bob", library=["Lightning Bolt", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.put_onto_battlefield("Merfolk Observer", "alice")
    scenario.choose_trigger_targets("Merfolk Observer", [bob])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    assert known(scenario.game, "bob") == []
    (look,) = scenario.game.reveals
    assert look.viewers == ["alice"]
    assert look.source == "Merfolk Observer"
    assert look.library_epoch == bob.library_epoch


def test_rootwater_mystic_looks_at_the_top_card_of_target_players_library():
    """ "{1}{U}: Look at the top card of target player's library." - also in
    neither deck pool."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rootwater Mystic", "Island", "Island"])
        .player("bob", library=["Lightning Bolt", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    mystic = scenario.creature("Rootwater Mystic", "alice")

    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.activate(mystic, *islands, username="alice", targets=[bob])
    scenario.pass_until_resolved()

    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]
    assert known(scenario.game, "bob") == []


# -- reveal until (CR 701.20a) -------------------------------------------------

FOUR_LANDS = ["Wastes"] * 4


def _belch(scenario: PlayedScenario) -> None:
    belcher = scenario.find("Goblin Charbelcher", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        belcher, *scenario.untapped_sources(*FOUR_LANDS), targets=[scenario.player("bob")]
    )
    scenario.resolve_top()


def test_every_card_charbelcher_reveals_is_recorded_publicly_then_bottomed_away():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Goblin Charbelcher", *FOUR_LANDS],
            library=["Lightning Bolt", "Lightning Bolt", "Sol Ring", "Forest", "Island"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    shown = list(alice.library[:4])
    stamps = {state.id: state.zone_change_stamp for state in shown}
    epoch = alice.library_epoch

    _belch(scenario)

    records = [r for r in scenario.game.reveals if r.source == "Goblin Charbelcher"]
    assert [r.card_id for r in records] == [state.id for state in shown]
    for record in records:
        assert record.viewers is None, "CR 701.20a: shown to all players"
        assert record.zone is Zone.LIBRARY
        assert record.revealed_by == "alice"
        assert record.library_epoch == epoch
        assert record.zone_change_stamp == stamps[record.card_id]
        assert record.turn == scenario.game.turn.turns_taken
    assert [state.name for state in alice.library] == ["Island", *(s.name for s in shown)]
    assert known(scenario.game, "alice") == []
    assert known(scenario.game, "bob") == []


def test_charbelcher_revealed_cards_that_later_go_to_hand_or_graveyard_are_not_known():
    """The bottomed cards' records ended with the reordering, so a later draw
    carries nothing and a later mill leaves nothing (CR 701.20d, CR 400.7)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Goblin Charbelcher", *FOUR_LANDS, "Island"],
            hand=["Thought Scour"],
            library=["Lightning Bolt", "Forest", "Island"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bolt, forest, _ = alice.library

    _belch(scenario)
    assert {r.card_id for r in scenario.game.reveals if r.source == "Goblin Charbelcher"} == {
        bolt.id,
        forest.id,
    }
    assert [state.name for state in alice.library] == ["Island", "Lightning Bolt", "Forest"]

    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_and_resolve("Thought Scour", island, targets=[alice])

    assert bolt.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.HAND
    assert known(scenario.game, "alice") == []
    assert known(scenario.game, "bob") == []


# -- reveal the top N, one per card type (CR 701.20a) ---------------------------


def test_atraxa_reveals_all_ten_publicly_and_the_kept_cards_stay_known_in_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Atraxa, Grand Unifier"],
            library=[*TOP_TEN, *["Swamp"] * 10],
            battlefield=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    shown = list(alice.library[:10])
    stamps = {state.id: state.zone_change_stamp for state in shown}
    epoch = alice.library_epoch

    scenario.put_onto_battlefield("Atraxa, Grand Unifier", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    records = [r for r in scenario.game.reveals if r.source == "Atraxa, Grand Unifier"]
    assert [r.card_id for r in records] == [state.id for state in shown]
    for record in records:
        assert record.viewers is None
        assert record.zone is Zone.LIBRARY
        assert record.library_epoch == epoch
        assert record.zone_change_stamp == stamps[record.card_id]

    kept = sorted(state.name for state in alice.hand)
    assert len(kept) == 5
    for viewer in ("alice", "bob"):
        assert sorted(known(scenario.game, viewer)) == sorted(
            (name, Zone.HAND, None, True) for name in kept
        ), "kept cards are carried; the rest went to the bottom in a random order"


# -- look at the top three, reveal one (CR 701.20e, then CR 701.20a) ------------


def _duskwatch_board() -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears", "Forest", "Mountain", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_recruiter(scenario: PlayedScenario, moved) -> None:
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=tuple(moved)), player="alice")
    )
    recruiter = scenario.creature("Duskwatch Recruiter")
    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    scenario.resolve_top()


def test_duskwatch_looks_at_three_privately_and_reveals_the_creature_it_takes():
    scenario = _duskwatch_board()
    alice = scenario.player("alice")
    looked = scenario.top_of_library(3)
    bears = looked[0]
    stamps = {state.id: state.zone_change_stamp for state in looked}
    epoch = alice.library_epoch

    _activate_recruiter(scenario, [bears.id])

    records = [r for r in scenario.game.reveals if r.source == "Duskwatch Recruiter"]
    looks = [r for r in records if r.viewers == ["alice"]]
    reveals = [r for r in records if r.viewers is None]
    assert {r.card_id for r in looks} == {state.id for state in looked}
    for look in looks:
        assert look.zone is Zone.LIBRARY
        assert look.library_epoch == epoch
        assert look.zone_change_stamp == stamps[look.card_id]
    assert [r.card_id for r in reveals] == [bears.id]
    assert reveals[0].zone is Zone.LIBRARY
    assert reveals[0].zone_change_stamp == stamps[bears.id]

    assert bears.zone is Zone.HAND
    assert known(scenario.game, "bob") == [("Grizzly Bears", Zone.HAND, None, True)]
    assert known(scenario.game, "alice") == [("Grizzly Bears", Zone.HAND, None, True)]


def test_duskwatch_declining_reveals_nothing_and_the_bottomed_looks_end():
    scenario = _duskwatch_board()
    looked = scenario.top_of_library(3)

    _activate_recruiter(scenario, [])

    records = [r for r in scenario.game.reveals if r.source == "Duskwatch Recruiter"]
    assert {r.card_id for r in records} == {state.id for state in looked}
    assert all(r.viewers == ["alice"] for r in records), "nothing was revealed"
    assert known(scenario.game, "alice") == []
    assert known(scenario.game, "bob") == []


# -- the existing reveal recorders fill every field ------------------------------


def test_goblin_guides_reveal_fills_every_field():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Guide"])
        .player("bob", library=["Lightning Bolt", "Forest"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bob = scenario.player("bob")
    bolt = bob.library[0]
    scenario.attack_with(scenario.creature("Goblin Guide", "alice"))
    scenario.resolve_top()

    (reveal,) = scenario.game.reveals
    assert reveal.card_id == bolt.id
    assert reveal.viewers is None
    assert reveal.zone is Zone.LIBRARY
    assert reveal.revealed_by == "bob"
    assert reveal.source == "Goblin Guide"
    assert reveal.zone_change_stamp == bolt.zone_change_stamp
    assert reveal.library_epoch == bob.library_epoch
    assert reveal.turn == scenario.game.turn.turns_taken
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.LIBRARY, 0, False)]


def test_explores_reveal_fills_every_field():
    scenario = amalia_board("Forest", "Llanowar Elves").build()
    alice = scenario.player("alice")
    forest = alice.library[0]
    stamp = forest.zone_change_stamp
    epoch = alice.library_epoch

    _explore(scenario)

    (reveal,) = scenario.game.reveals
    assert reveal.card_id == forest.id
    assert reveal.viewers is None
    assert reveal.zone is Zone.LIBRARY
    assert reveal.revealed_by == "alice"
    assert reveal.source == "Amalia Benavides Aguirre"
    assert reveal.zone_change_stamp == stamp
    assert reveal.library_epoch == epoch
    assert reveal.turn == scenario.game.turn.turns_taken
