"""Spells cast this game: a per-player count kept for the whole game, and
"if this spell is the first spell you've cast this game".

First Contact (trk): "Mill four cards. You may put a permanent card from
among them into your hand. If this spell is the first spell you've cast this
game, you gain 2 life." `Game.spells_cast_this_turn` is emptied every turn,
so the question needs its own ledger: `Game.spells_cast_this_game` counts
each player's casts and stamps the running number onto the spell's
`CastRecord` as it becomes cast.

No other legal printing asks about the spells cast this game (Scryfall
checked in the writing session: Once Upon a Time asks the same question but
is banned in Modern and asks it while casting, not resolving), so the board
varies inside the one card: earlier turns, the opponent's spells, a spell
cast in response, a second copy of the card, and a copy of the spell.

CR rules looked up with `mise run rules:find` in the writing session:

- CR 601.2i: "... then the spell becomes cast." - the moment a cast is
  counted, and so the moment a spell's place in the count is fixed.
- CR 707.10: "a copy of a spell isn't cast".
- CR 117.1a: "A player may cast an instant spell any time they have
  priority."
- CR 701.17a: milling; CR 110.4a: "permanent card".
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _names(cards) -> list[str]:
    return [card.name for card in cards]


def _board(*, hand: list[str], battlefield: list[str], library: list[str] | None = None):
    return (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=battlefield,
            library=library if library is not None else ["Grizzly Bears", "Opt", "Shock", "Opt"],
        )
        .player("bob", hand=["Opt"], battlefield=["Island"], library=["Plains"] * 3)
        .build()
    )


def _cast_first_contact(scenario, username: str = "alice") -> None:
    scenario.cast_onto_stack(
        "First Contact",
        *scenario.untapped_sources("Forest", "Forest", username=username),
        username=username,
    )


def test_first_contact_as_the_first_spell_of_the_game_gains_2_life() -> None:
    """The happy path: mill four, take the permanent card, and - this being
    alice's first cast of the game - gain 2 life."""
    scenario = _board(hand=["First Contact"], battlefield=["Forest", "Forest"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.player("alice").library[0]
    scenario.will_take_the_may(True, source="First Contact")
    scenario.will_choose_cards(bears, source="First Contact")
    _cast_first_contact(scenario)
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert alice.life == 22
    assert _names(alice.hand) == ["Grizzly Bears"]
    assert sorted(_names(alice.graveyard)) == ["First Contact", "Opt", "Opt", "Shock"]
    assert scenario.game.spells_cast_this_game == {"alice": 1}


def test_first_contact_counts_a_spell_cast_on_an_earlier_turn() -> None:
    """Alice cast Opt last turn: nothing of it is left in this turn's ledger,
    but it was still her first spell this game, so First Contact gains no
    life."""
    scenario = _board(
        hand=["Opt", "First Contact"],
        battlefield=["Island", "Forest", "Forest"],
        library=["Grizzly Bears", "Opt", "Shock", "Opt", "Island", "Island"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Opt", *scenario.untapped_sources("Island"))
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # bob's turn begins
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.turn.active_player == "bob"
    assert scenario.game.spells_cast_this_turn.get("alice", []) == []
    scenario.will_take_the_may(False, source="First Contact")
    scenario.pass_priority("bob")
    _cast_first_contact(scenario)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 20
    assert scenario.game.spells_cast_this_game == {"alice": 2}


def test_an_opponents_spell_does_not_count_as_yours() -> None:
    """Bob cast a spell first; "you've cast" is alice's own count, so her
    First Contact is still her first and gains the life."""
    scenario = _board(hand=["First Contact"], battlefield=["Forest", "Forest"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="First Contact")
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Opt", *scenario.untapped_sources("Island", username="bob"), username="bob"
    )
    scenario.pass_until_resolved()
    _cast_first_contact(scenario)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 22
    assert scenario.game.spells_cast_this_game == {"bob": 1, "alice": 1}


def test_a_spell_cast_in_response_does_not_take_the_first_place() -> None:
    """Alice casts First Contact, then Opt in response (CR 117.1a). Opt
    resolves first, but First Contact became cast first (CR 601.2i), so it is
    still the first spell she cast this game."""
    scenario = _board(
        hand=["First Contact", "Opt"],
        battlefield=["Forest", "Forest", "Island"],
        library=["Grizzly Bears", "Opt", "Shock", "Opt", "Island"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="First Contact")
    _cast_first_contact(scenario)
    scenario.cast_onto_stack("Opt", *scenario.untapped_sources("Island"))
    scenario.pass_until_resolved()  # Opt
    assert scenario.player("alice").life == 20
    scenario.pass_until_resolved()  # First Contact

    assert scenario.player("alice").life == 22
    assert scenario.game.spells_cast_this_game == {"alice": 2}


def test_the_second_first_contact_gains_no_life() -> None:
    """Two copies of the card: only the one cast first gains life."""
    scenario = _board(
        hand=["First Contact", "First Contact"],
        battlefield=["Forest"] * 4,
        library=["Opt"] * 8,
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="First Contact", times=None)
    _cast_first_contact(scenario)
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 22
    _cast_first_contact(scenario)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 22
    assert scenario.find("First Contact", Zone.GRAVEYARD, "alice")
    assert scenario.game.spells_cast_this_game == {"alice": 2}


def test_a_copy_of_the_first_spell_was_never_cast_and_gains_no_life() -> None:
    """Reverberate copies First Contact. The copy mills and may take a card,
    but a copy isn't cast (CR 707.10), so it is no spell "you've cast" at all;
    the original, alice's first cast, still gains the 2 life."""
    scenario = _board(
        hand=["First Contact", "Reverberate"],
        battlefield=["Forest", "Forest", "Mountain", "Mountain"],
        library=["Opt"] * 8,
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="First Contact", times=None)
    _cast_first_contact(scenario)
    original = scenario.game.stack[-1]
    scenario.cast_onto_stack(
        "Reverberate", *scenario.untapped_sources("Mountain", "Mountain"), targets=[original]
    )
    scenario.pass_until_resolved()  # Reverberate: the copy goes on the stack
    assert len(scenario.game.stack) == 2
    scenario.pass_until_resolved()  # the copy
    assert scenario.player("alice").life == 20
    assert len(scenario.player("alice").library) == 4, "the copy milled four"
    scenario.pass_until_resolved()  # the original

    assert scenario.player("alice").life == 22
    assert scenario.player("alice").library == []
    assert scenario.game.spells_cast_this_game == {"alice": 2}


def test_the_count_and_the_stamp_survive_a_game_dump_and_reload() -> None:
    """The ledger is persisted game state: a game dumped while First Contact
    is on the stack and decoded again keeps both alice's count and the
    spell's own place in it."""
    from magic_cards_model.models.game import Game

    scenario = _board(hand=["First Contact"], battlefield=["Forest", "Forest"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_first_contact(scenario)
    spell = scenario.game.stack[-1]

    reloaded = Game.model_validate_json(scenario.game.model_dump_json())

    assert reloaded.spells_cast_this_game == {"alice": 1}
    record = reloaded.cast_record_of(reloaded.stack[-1])
    assert record is not None
    assert reloaded.stack[-1].id == spell.id
    assert (record.caster, record.cast_number_this_game) == ("alice", 1)
