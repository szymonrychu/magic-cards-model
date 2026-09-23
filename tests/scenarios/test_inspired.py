"""Scenario: Inspired (CR 207.2c ability word - "Inspired — Whenever this
creature becomes untapped, [effect]", no rules meaning of its own beyond
tying together cards that share the trigger).

Two things are proven separately:

- **The trigger itself** ("becomes untapped" firing Inspired) already had a
  regression test (`test_ordering_objects_onto_the_stack.py`'s untap/upkeep
  ordering), so this file's own untap scenario is new coverage for the
  *effect*, not a first proof that the event fires.
- **A general "`<target>` gets -N/-0" reader** (`machines/layers.py`'s
  `_PUMP_RE`, widened here to accept "an opponent controls" alongside the
  existing "you control"): Deepwater Hypnotist's own Inspired clause,
  "target creature an opponent controls gets -3/-0 until end of turn.", and
  Burrog Befuddler's differently-worded, differently-signed ETB, "target
  creature an opponent controls gets -1/-0 until end of turn." - not an
  ability word at all, proof that the reader is general across *any*
  trigger, not fitted to Inspired's own wording. Pain Seer's own Inspired
  trigger is a *third*, entirely different effect ("reveal the top card of
  your library and put that card into your hand. You lose life equal to
  that card's mana value.") - proof that the ability word itself is read
  independently of which effect happens to follow it.

Oracle text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def test_deepwater_hypnotist_shrinks_a_target_on_becoming_untapped():
    """Deepwater Hypnotist tapped on bob's turn, so CR 502.3's untap step on
    alice's own turn is the event that fires Inspired - the identical setup
    `test_ordering_objects_onto_the_stack.py` already uses for the trigger
    half, reused here for the effect."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Deepwater Hypnotist"], library=["Forest"] * 10)
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.creature("Deepwater Hypnotist", "alice").tap()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Deepwater Hypnotist", [bears])

    scenario.start_at(Step.END_STEP)
    while not (scenario.step is Step.UNTAP and scenario.turn.active_player == "alice"):
        scenario.advance()
    assert [item.source_name for item in scenario.pending_triggers] == ["Deepwater Hypnotist"]
    scenario.advance()  # upkeep: the held trigger goes on the stack
    scenario.pass_until_resolved()

    chars = scenario.game.characteristics_of(bears)
    assert chars.power == -1  # printed 2, -3/-0 - nothing floors power at 0
    assert chars.toughness == 2  # unchanged


def test_off_pool_burrog_befuddler_shrinks_a_target_by_one_on_etb():
    """A differently-worded, differently-signed proof of the same "`<target>`
    gets -N/-0" reader - an ETB, not Inspired at all, and -1/-0 rather than
    -3/-0."""
    scenario = (
        Scenario()
        .player("alice", hand=["Burrog Befuddler"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Burrog Befuddler", [bears])

    scenario.put_onto_battlefield("Burrog Befuddler")
    scenario.pass_until_resolved()

    chars = scenario.game.characteristics_of(bears)
    assert chars.power == 1  # printed 2, -1/-0
    assert chars.toughness == 2  # unchanged


def test_off_pool_pain_seer_inspired_is_a_different_effect_entirely():
    """Pain Seer's own Inspired trigger is not a -N/-0 pump at all: "reveal
    the top card of your library and put that card into your hand. You lose
    life equal to that card's mana value." Proof that Inspired's own trigger
    (`test_ordering_objects_onto_the_stack.py`'s untap/upkeep machinery,
    reused verbatim here) is read independently of whichever effect follows
    the ability word."""
    scenario = (
        Scenario().player("alice", battlefield=["Pain Seer"], library=["Lightning Bolt"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.creature("Pain Seer", "alice").tap()
    life_before = scenario.player("alice").life

    scenario.start_at(Step.END_STEP)
    while not (scenario.step is Step.UNTAP and scenario.turn.active_player == "alice"):
        scenario.advance()
    assert [item.source_name for item in scenario.pending_triggers] == ["Pain Seer"]
    scenario.advance()  # upkeep
    scenario.pass_until_resolved()

    hand = scenario.player("alice").hand
    assert [card.name for card in hand] == ["Lightning Bolt"]
    assert scenario.player("alice").life == life_before - 1  # Lightning Bolt costs {R}, mv 1


def test_off_pool_pain_seer_does_not_trigger_while_already_untapped():
    """Pain Seer starts untapped (the default) and simply advancing through
    an untap step - its own, with nothing to untap - fires nothing: CR 502.3
    only untaps a permanent that was tapped, and "becomes untapped" (CR
    603.2, an event) never happens for one that already was."""
    scenario = Scenario().player("alice", battlefield=["Pain Seer"]).build()
    scenario.start_at(Step.END_STEP)
    while not (scenario.step is Step.UNTAP and scenario.turn.active_player == "alice"):
        scenario.advance()

    assert scenario.pending_triggers == []
    scenario.advance()  # upkeep
    assert scenario.game.stack_is_empty


def test_deepwater_hypnotist_target_must_be_an_opponents_creature():
    """CR 601.2c/602.2b: "target creature an opponent controls" cannot name
    alice's own creature - the targeting half `profile_for_text` already
    enforced before this file's own effect reader existed."""
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Deepwater Hypnotist", "Grizzly Bears"], library=["Forest"] * 10
        )
        .player("bob", library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    own_bears = scenario.creature("Grizzly Bears", "alice")
    scenario.creature("Deepwater Hypnotist", "alice").tap()

    scenario.start_at(Step.END_STEP)
    while not (scenario.step is Step.UNTAP and scenario.turn.active_player == "alice"):
        scenario.advance()
    scenario.advance()  # upkeep

    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Deepwater Hypnotist", [own_bears])
    assert own_bears.zone is Zone.BATTLEFIELD
