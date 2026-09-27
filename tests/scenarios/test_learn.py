"""Learn: CR 701.48a, a bare CR 701 keyword action.

"Learn" means "You may discard a card. If you do, draw a card. If you
didn't discard a card, you may reveal a Lesson card you own from outside
the game and put it into your hand." Read generically off the printed word
in `machines/effects.py`'s `_parse_learn_clause`, not by card name, on two
differently-shaped cards: Divide by Zero's capitalised, sentence-final
"Learn." on a spell, and Eyetwitch's lowercase, mid-sentence "learn" inside
a dies trigger.

The Lesson-reveal half is performed too: CR 400.11a puts a sideboard outside
the game, CR 205.3k makes Lesson a spell type, and the card revealed there and
put into the hand is recorded publicly (CR 701.20a, 701.20b) and carried into
the hand like every other "reveal ... from outside the game and put it into
your hand" template (`test_reveal_from_outside_the_game_stays_known_in_hand.
py`). Igneous Inspiration is the off-pool proof: it is listed in neither
`~/Documents/mtg-decks/decks/*/decklist.txt` nor `magic-cards-model-api/decks/
*.txt`.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario


def _cast_divide_by_zero_at_a_spell(scenario):
    """Alice's own Shock, still on the stack, bounced by her own Divide by
    Zero in response - sidesteps `machines/targeting.py`'s unrelated "target
    spell or permanent" gap (that phrase's battlefield half is not read at
    all), which is not this mechanic's business to fix."""
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    shock = scenario.cast_onto_stack("Shock", mountain, username="alice", targets=["bob"])
    sources = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    dbz = scenario.cast_onto_stack("Divide by Zero", *sources, username="alice", targets=[shock])
    return dbz


def test_divide_by_zero_lets_its_caster_discard_to_draw():
    """Divide by Zero: "Return target spell or permanent with mana value 1 or
    greater to its owner's hand. Learn."
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Divide by Zero", "Lightning Bolt", "Shock"],
            library=["Forest"],
            battlefield=["Island", "Island", "Island", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.will_take_the_may(True, source="Divide by Zero")
    scenario.will_discard(bolt, username="alice")
    _cast_divide_by_zero_at_a_spell(scenario)
    scenario.pass_until_resolved()

    assert bolt.zone.value == "graveyard"
    assert len(scenario.player("alice").hand) == hand_before - 1


def test_declining_learn_discards_nothing_and_draws_nothing():
    """CR 608.2d: a "may" left unanswered/declined performs neither half."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Divide by Zero", "Lightning Bolt", "Shock"],
            library=["Forest"],
            battlefield=["Island", "Island", "Island", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)

    scenario.will_take_the_may(False, source="Divide by Zero")
    _cast_divide_by_zero_at_a_spell(scenario)
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == hand_before - 1


def test_eyetwitch_learns_lowercase_and_mid_sentence_when_it_dies():
    """Eyetwitch: "When this creature dies, learn." - a triggered ability's
    own effect text, not a spell's trailing sentence, and the lowercase word
    Divide by Zero's regex has to match too.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], library=["Forest"], battlefield=["Eyetwitch"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    eyetwitch = scenario.creature("Eyetwitch", "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.game.destroy(eyetwitch)
    scenario.state_based_actions()
    scenario.will_take_the_may(True, source="Eyetwitch")
    scenario.will_discard(bolt, username="alice")
    scenario.pass_until_resolved()

    assert bolt.zone.value == "graveyard"
    assert len(scenario.player("alice").hand) == hand_before


# -- the Lesson-reveal half ----------------------------------------------------


def known(game: Game, viewer: str) -> list[tuple[str, Zone, int | None, bool]]:
    return [
        (entry.card_name, entry.zone, entry.index_from_top, entry.carried)
        for entry in game.known_to(viewer)
    ]


def _divide_by_zero_board(hand: list[str], sideboard: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Divide by Zero", "Shock", *hand],
            library=["Forest"],
            battlefield=["Island", "Island", "Island", "Mountain"],
            sideboard=sideboard,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_declining_the_discard_reveals_a_lesson_from_outside_the_game_known_to_all():
    """CR 701.48a: "If you didn't discard a card, you may reveal a Lesson card
    you own from outside the game and put it into your hand." """
    scenario = _divide_by_zero_board(["Lightning Bolt"], ["Environmental Sciences", "Preordain"])
    alice = scenario.player("alice")
    (lesson,) = [
        state for state in alice.outside_the_game if state.name == "Environmental Sciences"
    ]
    scenario.will_take_the_may(False, username="alice", source="Divide by Zero")
    scenario.will_take_the_may(True, username="alice", source="Divide by Zero")
    scenario.will_choose_cards(lesson, username="alice", source="Divide by Zero")

    _cast_divide_by_zero_at_a_spell(scenario)
    scenario.pass_until_resolved()

    assert lesson.zone is Zone.HAND
    assert [state.name for state in alice.outside_the_game] == ["Preordain"]
    (reveal,) = scenario.game.reveals
    assert reveal.card_id == lesson.id
    assert reveal.zone is Zone.SIDEBOARD, "CR 701.20b: shown where it sat"
    assert reveal.viewers is None
    # The Lesson is carried from its outside-the-game reveal; the Shock that
    # Divide by Zero bounced off the stack is known too, because the stack is
    # a public zone (CR 400.2) - see `test_public_card_to_hand_known.py`.
    assert sorted(known(scenario.game, "bob")) == [
        ("Environmental Sciences", Zone.HAND, None, True),
        ("Shock", Zone.HAND, None, True),
    ]


def test_discarding_to_draw_offers_no_lesson():
    """CR 701.48a's "If you didn't discard a card": the two halves are exclusive."""
    scenario = _divide_by_zero_board(["Lightning Bolt"], ["Environmental Sciences"])
    alice = scenario.player("alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_take_the_may(True, username="alice", source="Divide by Zero")
    scenario.will_discard(bolt, username="alice")

    _cast_divide_by_zero_at_a_spell(scenario)
    scenario.pass_until_resolved()

    assert [state.name for state in alice.outside_the_game] == ["Environmental Sciences"]
    assert scenario.game.reveals == []


def test_a_non_lesson_card_outside_the_game_is_not_offered():
    scenario = _divide_by_zero_board([], ["Preordain", "Lightning Bolt"])
    alice = scenario.player("alice")
    # The bounced Shock is back in hand by now, so the discard is offered first.
    scenario.will_take_the_may(False, username="alice", source="Divide by Zero")

    _cast_divide_by_zero_at_a_spell(scenario)
    scenario.pass_until_resolved()

    assert len(alice.outside_the_game) == 2
    assert scenario.game.reveals == []
    assert not any("Lesson" in d.prompt for d in scenario.game.decisions.asked)


def test_declining_the_lesson_reveal_leaves_it_outside_the_game():
    scenario = _divide_by_zero_board([], ["Environmental Sciences"])
    alice = scenario.player("alice")
    scenario.will_take_the_may(False, username="alice", source="Divide by Zero")
    scenario.will_take_the_may(False, username="alice", source="Divide by Zero")

    _cast_divide_by_zero_at_a_spell(scenario)
    scenario.pass_until_resolved()

    assert [state.name for state in alice.outside_the_game] == ["Environmental Sciences"]
    assert scenario.game.reveals == []


def test_eyetwitch_with_an_empty_hand_still_reveals_a_lesson():
    """No card to discard means no discard, so the Lesson half is still open."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Eyetwitch"], sideboard=["Environmental Sciences"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (lesson,) = list(alice.outside_the_game)
    scenario.will_take_the_may(True, username="alice", source="Eyetwitch")
    scenario.will_choose_cards(lesson, username="alice", source="Eyetwitch")

    scenario.game.destroy(scenario.creature("Eyetwitch", "alice"))
    scenario.state_based_actions()
    scenario.pass_until_resolved()

    assert lesson.zone is Zone.HAND
    assert known(scenario.game, "bob") == [("Environmental Sciences", Zone.HAND, None, True)]


def test_igneous_inspiration_learns_a_lesson_off_pool():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Igneous Inspiration"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            sideboard=["Environmental Sciences"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (lesson,) = list(alice.outside_the_game)
    scenario.will_take_the_may(True, username="alice", source="Igneous Inspiration")
    scenario.will_choose_cards(lesson, username="alice", source="Igneous Inspiration")

    scenario.cast_and_resolve(
        "Igneous Inspiration",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=["bob"],
    )

    assert scenario.player("bob").life == 17
    assert lesson.zone is Zone.HAND
    assert known(scenario.game, "bob") == [("Environmental Sciences", Zone.HAND, None, True)]


# --------------------------------------------------------------------------
# R0a-T7: Academic Dispute - "Target creature blocks this turn if able. You
# may have it gain reach until end of turn.\nLearn." - a general CR 509.1c
# block requirement (no named attacker) beside the optional reach grant and
# an unrelated Learn already read above.
# --------------------------------------------------------------------------


def test_academic_dispute_forces_the_targeted_creature_to_block_if_able():
    """CR 509.1c: with no requirement, a defending player may simply not
    block; once Academic Dispute grants "This creature blocks each combat if
    able," declining to block at all is illegal, and the requirement is
    satisfied by blocking the (only) attacker, with no attacker named on the
    granted line at all."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant", "Forest", "Forest"], library=["Forest"] * 10)
        .player(
            "bob",
            hand=["Academic Dispute"],
            battlefield=["Grizzly Bears", "Mountain"],
            library=["Forest"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")
    giant.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(giant)
    scenario.pass_priority("alice")
    scenario.will_take_the_may(False, username="bob", source="Academic Dispute")

    scenario.cast_and_resolve(
        "Academic Dispute",
        *scenario.untapped_sources("Mountain", username="bob"),
        targets=[bears],
        username="bob",
    )

    assert scenario.game.characteristics_of(bears).abilities == (
        "This creature blocks each combat if able.",
    )
    assert scenario.game.mode_notices == []

    with pytest.raises(ValueError, match=r"CR 509\.1c"):
        scenario.no_blocks()

    scenario.block(giant, bears)
    assert scenario.blockers() == [bears]


def test_academic_dispute_may_grant_reach_and_still_learns():
    """The optional "You may have it gain reach until end of turn." (CR
    608.2d) and "Learn." (CR 701.48a, already read by `machines/keywords.py`)
    - a flying attacker the targeted creature could not otherwise block."""
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Aether Swooper", "Forest", "Forest"], library=["Forest"] * 10
        )
        .player(
            "bob",
            hand=["Academic Dispute", "Opt"],
            battlefield=["Grizzly Bears", "Mountain"],
            library=["Forest"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    spirit = scenario.creature("Aether Swooper", "alice")
    spirit.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(spirit)
    scenario.pass_priority("alice")
    scenario.will_take_the_may(True, username="bob", source="Academic Dispute")
    scenario.will_take_the_may(True, username="bob", source="Academic Dispute")
    scenario.will_choose_cards(
        scenario.find("Opt", Zone.HAND, "bob"), username="bob", source="Academic Dispute"
    )

    scenario.cast_and_resolve(
        "Academic Dispute",
        *scenario.untapped_sources("Mountain", username="bob"),
        targets=[bears],
        username="bob",
    )

    assert set(scenario.game.characteristics_of(bears).abilities) == {
        "This creature blocks each combat if able.",
        "Reach",
    }
    assert bears.zone is Zone.GRAVEYARD or bears.zone is Zone.BATTLEFIELD
    assert scenario.game.mode_notices == []

    scenario.block(spirit, bears)
    assert scenario.blockers() == [bears]
