"""Scenario: a general "create a token that's a copy of target `<permanent
description>` you control" reader (`_parse_create_token_copy_of_target_
clause`, `_CREATE_TOKEN_COPY_OF_TARGET_RE`, CR 707.2, `token_copy_of`).

Three Steps Ahead's own second Spree mode - "Create a token that's a copy of
target artifact or creature you control." - names a two-word target
description ("artifact or creature") the reader's old `phrase` group only
ever matched literally as the single fixed string "target creature you
control" (Replicate's own printing, the only card that shape was ever read
from). Widening the noun-phrase capture to "target `<word>`[ or `<word>`]
you control" costs nothing beyond recognising the shape - `machines/
targeting.py` is what actually resolves either description, and this
function only asks whether that module understood it
(`_targets_understood`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 707.2** - "To create a token, the game puts one or more tokens onto
  the battlefield." Not CR 111.13's spell-copy exemption - a genuine new
  object.
- **CR 111.13** - "A copy of a permanent spell becomes a token as it
  resolves"; this shape never puts a spell on the stack at all, it creates
  the token directly.
- **CR 700.2a** - a modal spell's chosen modes each resolve.
- **CR 702.172a** - Spree: "Choose one or more modes. As an additional cost
  to cast this spell, pay the costs associated with those modes."

Cackling Counterpart (off-pool, confirmed with `scripts/add_card.py`,
Modern-legal) is the proof this reads generally: its own printed phrase,
"target creature you control", is the *narrower*, single-word shape the
reader already read before this wave - proving the widened regex did not
stop matching the shape it already had.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_three_steps_ahead_mode_two_alone_copies_a_creature_you_control():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Three Steps Ahead"],
            battlefield=["Island"] * 4 + ["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources(*(["Island"] * 4))

    casting = scenario.cast("Three Steps Ahead")
    casting.choose_modes([2])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    tokens = [
        state
        for state in scenario.game.battlefield
        if state.token and state.name == "Grizzly Bears"
    ]
    assert len(tokens) == 1
    assert tokens[0].id != bears.id, "a new object (CR 707.2), not the original"
    assert (tokens[0].power, tokens[0].toughness) == (2, 2)


def test_three_steps_ahead_modes_two_and_three_together_copies_an_artifact_and_loots():
    """Modes 2 and 3 chosen together (CR 700.2a): mode 2's own token copy,
    targeting Mind Stone - a plain artifact, not a creature, proving "target
    artifact or creature" reaches the artifact half too - and mode 3's own
    "draw two cards, then discard a card"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Three Steps Ahead", "Mountain"],
            battlefield=["Island"] * 6 + ["Mind Stone"],
            library=["Plains", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    mountain = scenario.find("Mountain", Zone.HAND, "alice")
    sources = scenario.untapped_sources(*(["Island"] * 6))
    scenario.will_choose_cards(mountain, username="alice", source="Three Steps Ahead")

    casting = scenario.cast("Three Steps Ahead")
    casting.choose_modes([2, 3])
    casting.choose_targets([stone])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    tokens = [
        state for state in scenario.game.battlefield if state.token and state.name == "Mind Stone"
    ]
    assert len(tokens) == 1
    assert tokens[0].id != stone.id

    alice = scenario.player("alice")
    assert {state.name for state in alice.hand} == {"Plains", "Swamp"}, (
        "drew two (CR 121.1), then discarded the chosen Mountain (CR 701.9a)"
    )


def test_cackling_counterpart_copies_a_creature_you_control():
    """Off-pool proof: Cackling Counterpart's own printed phrase is the
    narrower, single-word "target creature you control" the reader already
    matched before this wave widened the noun-phrase capture for Three Steps
    Ahead's own two-word description."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cackling Counterpart"],
            battlefield=["Island"] * 3 + ["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources(*(["Island"] * 3))

    casting = scenario.cast("Cackling Counterpart")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    tokens = [
        state
        for state in scenario.game.battlefield
        if state.token and state.name == "Grizzly Bears"
    ]
    assert len(tokens) == 1
    assert tokens[0].id != bears.id
