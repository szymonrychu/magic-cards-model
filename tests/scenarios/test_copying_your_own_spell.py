"""A cast trigger that copies the spell it is printed on (CR 707.10).

Sage of the Skies: "When you cast this spell, if you've cast another spell
this turn, copy this spell. (The copy becomes a token.)"

CR 707.10: "To copy a spell, activated ability, or triggered ability means to
put a copy of it onto the stack; a copy of a spell isn't cast and a copy of an
activated ability isn't activated."

The parenthesis is CR 707.10f - "Some effects copy a permanent spell. As that
copy resolves, it ceases being a copy of a spell and becomes a token
permanent" - which CR 111.13 states from the token side: "A copy of a permanent
spell becomes a token as it resolves. The token has the characteristics of the
spell that became that token. The token is not 'created' for the purposes of
any replacement effect". CR 608.3f is the resolution step itself.

The intervening *if* is CR 608.2a: "If a triggered ability has an intervening
'if' clause, it checks whether the clause's condition is true. If it isn't, the
ability is removed from the stack and does nothing."

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import Scenario


def sage_board(bob_hand: list[str] | None = None) -> Scenario:
    """Alice holding the Sage and a Bolt, with the mana for both."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Sage of the Skies", "Lightning Bolt"],
            battlefield=["Plains", "Plains", "Plains", "Mountain"],
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            hand=list(bob_hand or []),
            battlefield=["Island", "Island"],
            library=["Mountain"] * 5,
        )
    )


def sages(scenario) -> list:
    return [state for state in scenario.game.battlefield if state.name == "Sage of the Skies"]


def cast_a_bolt(scenario) -> None:
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_a_second_spell_this_turn_makes_the_sage_copy_itself():
    """CR 707.10 puts the copy on the stack above the ability that made it, so
    it resolves first and both Sages end up on the battlefield."""
    scenario = sage_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_a_bolt(scenario)

    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_onto_stack("Sage of the Skies", *plains)
    assert scenario.stack_names() == [
        "Sage of the Skies",
        "Sage of the Skies's triggered ability",
    ]

    while scenario.game.stack:
        scenario.pass_until_resolved()

    assert len(sages(scenario)) == 2


# --------------------------------------------------------------------------
# Corner cases
# --------------------------------------------------------------------------


def test_the_copy_becomes_a_token_and_the_original_stays_a_real_card():
    """CR 707.10f and CR 111.13: the copy "ceases being a copy of a spell and
    becomes a token permanent", while the card that was actually cast is an
    ordinary nontoken permanent."""
    scenario = sage_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_a_bolt(scenario)

    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    original = scenario.cast_onto_stack("Sage of the Skies", *plains)
    while scenario.game.stack:
        scenario.pass_until_resolved()

    both = sages(scenario)
    assert len(both) == 2
    assert not is_token(original)
    assert original.zone is Zone.BATTLEFIELD
    copies = [state for state in both if state.id != original.id]
    assert len(copies) == 1
    assert is_token(copies[0])


def test_no_other_spell_this_turn_means_the_intervening_if_stops_it():
    """CR 608.2a: the clause is false, the ability is removed from the stack
    and does nothing. One Sage, no copy - and no `InterveningIfNotice`, which
    is what tells "the condition was false" apart from "the condition could
    not be read"."""
    scenario = sage_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_onto_stack("Sage of the Skies", *plains)
    while scenario.game.stack:
        scenario.pass_until_resolved()

    assert len(sages(scenario)) == 1
    assert scenario.game.intervening_if_notices == [], "the clause was read, not failed closed"


def test_the_copy_is_not_cast_so_it_does_not_trigger_the_ability_again():
    """CR 707.10: "a copy of a spell isn't cast". The trigger's condition is
    "When you cast this spell", so the copy going on the stack is not a cast
    event and fires nothing - exactly two Sages, never a runaway loop."""
    scenario = sage_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_a_bolt(scenario)

    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_onto_stack("Sage of the Skies", *plains)
    while scenario.game.stack:
        scenario.pass_until_resolved()

    assert len(sages(scenario)) == 2
    assert scenario.pending_triggers == []
    assert scenario.stack_names() == []


def test_countering_the_original_leaves_nothing_to_copy():
    """The trigger is on the stack above the spell it copies, so it resolves
    first - but a Counterspell cast in response resolves above *both*. Once
    the Sage is in a graveyard there is no spell to copy and the ability does
    nothing, which CR 707.10 leaves as simply having nothing to put a copy
    of onto the stack."""
    scenario = sage_board(bob_hand=["Counterspell"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_a_bolt(scenario)

    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    sage = scenario.cast_onto_stack("Sage of the Skies", *plains)
    scenario.pass_priority("alice")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *islands, targets=[sage], username="bob")

    while scenario.game.stack:
        scenario.pass_until_resolved()

    assert sage.zone is Zone.GRAVEYARD
    assert sages(scenario) == []


def test_a_land_played_this_turn_is_not_another_spell():
    """CR 305.1: "A player may play one land ... this action doesn't use the
    stack" - playing a land is a special action, not casting a spell, so it
    does not satisfy "you've cast another spell this turn"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sage of the Skies", "Mountain"],
            battlefield=["Plains", "Plains", "Plains"],
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Mountain")

    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_onto_stack("Sage of the Skies", *plains)
    while scenario.game.stack:
        scenario.pass_until_resolved()

    assert len(sages(scenario)) == 1
    assert scenario.game.intervening_if_notices == []


def test_an_opponents_spell_does_not_count_as_one_you_cast():
    """ "**You've** cast another spell this turn" - bob's Lightning Bolt is
    bob's, and does nothing for alice's clause."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sage of the Skies"],
            battlefield=["Plains", "Plains", "Plains"],
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            battlefield=["Mountain"],
            library=["Mountain"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["alice"], username="bob")

    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_onto_stack("Sage of the Skies", *plains)
    while scenario.game.stack:
        scenario.pass_until_resolved()

    assert len(sages(scenario)) == 1
