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
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_ancestral_vision_lets_its_target_draw_three():
    """Cast plainly (not suspended) for its own alternative purposes here -
    this file is about the resolution clause, not the suspend mechanic."""
    scenario = (
        Scenario()
        .player("alice", hand=["Ancestral Vision"], battlefield=["Island"])
        .player("bob", library=["Forest", "Mountain", "Swamp", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Island")

    scenario.cast_and_resolve("Ancestral Vision", *sources, targets=["bob"])

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
            battlefield=["Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Island")

    scenario.cast_and_resolve("Ancestral Vision", *sources, targets=["alice"])

    assert len(alice.hand) == 3
    assert len(alice.library) == 0
