"""A plain "target player draws N cards" clause (CR 121.1), aimed at a chosen
player rather than the caster - `_parse_target_player_draws_clause` in
`machines/effects.py`, the draw-side twin of
`test_target_player_discards.py`'s "target player discards N cards"
(`_parse_target_player_discards_clause`).

Ancestral Vision is the vehicle: "Suspend 4-{U} ... Target player draws three
cards." Its own `Suspend 4-{U} (...)` line used to poison the clause split of
the sentence after it (the same class of bug `_FLASHBACK_LINE_RE`/
`_KICKER_LINE_RE` fix for their own keywords; `_SUSPEND_LINE_RE` already
existed for this one), and once past that, nothing in `machines/effects.py`
read "target player draws N cards" at all - only "you draw"/implicit-"you"
shapes reached a resolving *target* rather than the caster.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 121.1** - "A player draws a card by putting the top card of their
  library into their hand."
- **CR 121.2** - "Cards may only be drawn one at a time. If a player is
  instructed to draw multiple cards, that player performs that many
  individual card draws."
- **CR 601.2c** - a target is announced when the spell is cast, and rechecked
  on resolution (CR 608.2b) - a player who has left the game by then is an
  illegal target and draws nothing, the ordinary way any other target does.
- **CR 702.62a/702.62b/702.62d** - suspend: two triggered abilities and a
  static one, none of which is the spell's own CR 608.2c resolution
  instruction, which is why its own printed line has to be stripped before
  "Target player draws three cards." is read as the whole effect.

Ancestral Vision's `mana_cost` is the empty string - it has **no printed mana
cost** (verified with `resolve_cards`), the same shape as Living End
(`tests/scenarios/test_suspend.py`), and CR 118.6 makes that an unpayable
cost. The two tests below used to hardcast it "plainly" through the ordinary
`Casting` path anyway - the same defect `test_suspend.py`'s own reported-bug
test now refuses - so they are staged with `Game.put_on_stack` instead, the
same cost-free primitive `test_living_end.py` already uses to test a
suspend-only card's *resolution* without re-proving its cast legality here.
This file is about the "target player draws N" clause, not suspend or CR
118.6 - both already have their own coverage.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import TargetRef
from tests.scenarios.harness import Scenario


def test_ancestral_vision_lets_its_target_draw_three():
    """Resolution only - Ancestral Vision has no mana cost (CR 118.6) and its
    only real route onto the stack is its own suspend ability
    (`test_suspend.py`); this file is about the clause after it resolves."""
    scenario = (
        Scenario()
        .player("alice", hand=["Ancestral Vision"])
        .player("bob", library=["Forest", "Mountain", "Swamp", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    vision = scenario.find("Ancestral Vision", Zone.HAND)
    scenario.game.put_on_stack(vision, "alice")
    vision.targets = [TargetRef.to_player("bob")]

    scenario.resolve_top()

    assert len(bob.hand) == 3
    assert len(bob.library) == 1


def test_the_caster_can_target_themselves():
    """CR 115.1's "target player" names any player, the caster included - no
    special-casing required for pointing it at yourself."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ancestral Vision"],
            library=["Forest", "Mountain", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    vision = scenario.find("Ancestral Vision", Zone.HAND)
    scenario.game.put_on_stack(vision, "alice")
    vision.targets = [TargetRef.to_player("alice")]

    scenario.resolve_top()

    assert len(alice.hand) == 3
    assert len(alice.library) == 0
