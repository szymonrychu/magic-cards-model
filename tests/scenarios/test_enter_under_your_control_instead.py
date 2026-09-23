"""Control-changing entry replacements a resolving spell or ability leaves
for the turn: "If a creature would enter the battlefield under an opponent's
control this turn, it enters under your control instead." (Gather
Specimens) and "each token that would be created under an opponent's control
this turn is created under your control instead." (Crafty Cutpurse's
enters trigger).

CR 614.1a: an "instead" effect is a replacement effect. CR 616.1b: "If any
of the replacement and/or prevention effects would modify under whose
control an object would enter the battlefield, one of them must be chosen" -
before a copy effect (616.1c) or anything else (616.1e). CR 614.5: each
effect gets one opportunity per event. CR 111.2: the player who creates a
token is its owner - Crafty Cutpurse changes only who controls it. CR 701.7b:
a replacement for a token *being created* applies before the one for it
*entering* - which is why Cutpurse sees a token creation and Gather Specimens
sees the entry. CR 514.2 ends both in the cleanup step.

Listed card: Gather Specimens. Proof printing: Crafty Cutpurse (legal in
Modern and Pioneer, not in any api deck) - the only other printing of this
template: the token-creation event instead of the entering one, created by a
creature's enters trigger rather than an instant.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.game import Game
from magic_cards_model.models.token import create_predefined_tokens
from tests.scenarios.harness import Scenario

GATHER = "Gather Specimens"


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _to_next_turn(scenario) -> None:
    active = scenario.turn.active_player
    while scenario.turn.active_player == active:
        scenario.advance()


def _board(
    *, alice_hand=(GATHER,), bob_hand=("Spectral Procession",), bob_battlefield=()
) -> Scenario:
    """bob is the active player; alice holds up six Islands for an instant."""
    return (
        Scenario()
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=["Forest", "Forest", "Plains", "Plains", "Plains", *bob_battlefield],
            library=["Forest"] * 5,
        )
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=["Island"] * 6,
            library=["Island"] * 5,
        )
    )


def _alice_casts(scenario, name: str = GATHER) -> None:
    scenario.pass_priority()  # bob passes; alice now holds priority
    scenario.cast_and_resolve(name, username="alice", auto=True)
    _resolve_everything(scenario)


def test_an_opponents_creature_spell_enters_under_your_control():
    """Ruling 2008-10-01: it resolves, and enters under your control."""
    scenario = _board(bob_hand=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alice_casts(scenario)

    bears = scenario.cast_and_resolve("Grizzly Bears", username="bob", auto=True)

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    assert bears.owner == "bob"


def test_its_enters_trigger_is_yours():
    """Ruling 2008-10-01: "enters" abilities trigger after it is under your
    control - Wall of Omens draws alice the card."""
    scenario = _board(bob_hand=("Wall of Omens",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alice_casts(scenario)

    scenario.put_onto_battlefield("Wall of Omens", "bob")
    _resolve_everything(scenario)

    assert [state.name for state in scenario.player("alice").hand] == ["Island"]
    assert scenario.player("bob").hand == []


def test_an_opponents_token_enters_under_your_control_but_stays_theirs_to_own():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alice_casts(scenario)

    (treasure,) = create_predefined_tokens(scenario.game, "Treasure", "bob")
    assert treasure.controller == "bob", 'a noncreature token is not "a creature"'

    scenario.cast_and_resolve("Spectral Procession", username="bob", auto=True)
    spirits = [p for p in scenario.game.battlefield if p.name == "Spirit Token"]
    assert len(spirits) == 3
    assert {p.controller for p in spirits} == {"alice"}
    assert {p.owner for p in spirits} == {"bob"}


def test_your_own_creature_is_unaffected():
    scenario = _board(alice_hand=(GATHER, "Grizzly Bears")).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alice_casts(scenario)

    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert bears.controller == "alice"


def test_it_does_not_take_a_creature_that_already_entered():
    """Ruling 2008-10-01: not retroactive."""
    scenario = _board(bob_battlefield=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alice_casts(scenario)

    assert scenario.creature("Grizzly Bears", "bob").controller == "bob"


def test_it_ends_with_the_turn():
    scenario = _board(bob_hand=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alice_casts(scenario)
    _to_next_turn(scenario)
    assert scenario.game.created_replacements == []

    bears = scenario.put_onto_battlefield("Grizzly Bears", "bob")
    assert bears.controller == "bob"


def test_two_gather_specimens_hand_it_back():
    """Ruling 2008-10-01: with both players' effects active, alice's takes
    bob's creature, then bob's takes it back, and each has had its one
    chance (CR 614.5) - it enters under bob's control."""
    scenario = _board(bob_hand=(GATHER, "Grizzly Bears"), bob_battlefield=("Island",) * 6).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(GATHER, username="bob", auto=True)
    _alice_casts(scenario)

    bears = scenario.put_onto_battlefield("Grizzly Bears", "bob")

    assert bears.controller == "bob"


def test_it_applies_before_doubling_season_at_entry_but_not_at_creation():
    """CR 701.7b: bob's Doubling Season doubles the tokens bob *creates*
    (the creation event); each of the six then *enters* - and Gather
    Specimens takes each one."""
    scenario = _board(bob_battlefield=("Doubling Season",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alice_casts(scenario)

    scenario.cast_and_resolve("Spectral Procession", username="bob", auto=True)

    spirits = [p for p in scenario.game.battlefield if p.name == "Spirit Token"]
    assert len(spirits) == 6
    assert {p.controller for p in spirits} == {"alice"}


def test_the_record_round_trips():
    scenario = _board(bob_hand=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alice_casts(scenario)

    dumped = scenario.game.model_dump(mode="json")
    (record,) = dumped["created_replacements"]
    assert record["spec"]["kind"] == "enter_under_your_control"

    decoded = Game.model_validate(dumped)
    bears = next(s for s in decoded.player("bob").hand if s.name == "Grizzly Bears")
    decoded.put_onto_battlefield(bears, "bob")
    assert bears.controller == "alice"


# --------------------------------------------------------------------------
# Crafty Cutpurse (proof printing) - "Flash. When this creature enters, each
# token that would be created under an opponent's control this turn is
# created under your control instead."
# --------------------------------------------------------------------------


def _cutpurse_board(*bob_battlefield: str) -> Scenario:
    return _board(
        alice_hand=("Crafty Cutpurse",),
        bob_hand=("Grizzly Bears", "Spectral Procession"),
        bob_battlefield=bob_battlefield,
    )


def test_cutpurse_takes_an_opponents_tokens_as_they_are_created():
    scenario = _cutpurse_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alice_casts(scenario, "Crafty Cutpurse")

    scenario.cast_and_resolve("Spectral Procession", username="bob", auto=True)

    spirits = [p for p in scenario.game.battlefield if p.name == "Spirit Token"]
    assert len(spirits) == 3
    assert {p.controller for p in spirits} == {"alice"}
    assert {p.owner for p in spirits} == {"bob"}, "CR 111.2: bob created them"


def test_cutpurse_applies_before_the_opponents_doubler():
    """Ruling 2018-01-19: applied before any other replacement effect that
    would modify how the token enters - bob's Doubling Season no longer sees
    tokens created under bob's control, so alice gets three, not six."""
    scenario = _cutpurse_board("Doubling Season").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alice_casts(scenario, "Crafty Cutpurse")

    scenario.cast_and_resolve("Spectral Procession", username="bob", auto=True)

    spirits = [p for p in scenario.game.battlefield if p.name == "Spirit Token"]
    assert len(spirits) == 3
    assert {p.controller for p in spirits} == {"alice"}


def test_cutpurse_leaves_a_nontoken_creature_alone():
    scenario = _cutpurse_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alice_casts(scenario, "Crafty Cutpurse")

    bears = scenario.cast_and_resolve("Grizzly Bears", username="bob", auto=True)

    assert bears.controller == "bob"


def test_cutpurse_ends_with_the_turn():
    scenario = _cutpurse_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _alice_casts(scenario, "Crafty Cutpurse")
    _to_next_turn(scenario)

    assert scenario.game.created_replacements == []
