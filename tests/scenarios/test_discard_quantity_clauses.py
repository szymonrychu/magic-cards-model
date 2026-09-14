"""G1-3/G1-4: discard quantity ("discard up to N cards"/"any number of
cards" in place of a bare "a card"/"N cards") and the "you may discard
`<quantity>` cards. If you do, `<consequence>`." merge
(`_merge_may_discard_if_you_do_clauses` in `machines/effects.py`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 107.1c** - "any positive number or zero" - CR 118.12's "you may
  discard up to N cards" is this quantifier over a discard.
- **CR 701.9a/701.9b** - discarding, and the discarding player's own choice
  of which.
- **CR 118.12** - "[A player] may [do something]. If [that player] does,
  [effect]." - the optional-cost shape `_merge_may_discard_if_you_do_clauses`
  reads.
- **CR 608.2d** - declining an optional cost is always legal.
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - the discard already ran by the time
  Fable of the Mirror-Breaker II's own "draw that many cards" is found to be
  a count this file cannot yet read (Group 0b's own channel), so the
  ability still triggers and the discard still happens; only the unreadable
  remainder is recorded rather than silently dropped.
- **CR 714.2/714.3a/107.15a** - a Saga's chapter abilities and its own
  intrinsic first lore counter, which is what makes one `saga_lore_step()`
  call below enough to reach Fable's own chapter II.

Fable of the Mirror-Breaker is the pool card a "discard up to N" clause left
silent - its own "draw that many cards" still has no reader until Group 0b's
channel lands, recorded as a notice instead of running unread. Thrilling
Discovery is a real Modern printing of the same "you may discard N. If you
do, `<consequence>`" shape with a fully readable (non-"that many")
consequence, so the whole spell runs end to end.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_thrilling_discovery_discards_two_then_draws_three():
    """Thrilling Discovery (off-pool, an exact count rather than Fable's own
    "up to"): "You gain 2 life. Then you may discard two cards. If you do,
    draw three cards." A fully readable consequence - no Group 0b channel
    needed - so the whole spell runs end to end."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Thrilling Discovery", "Grizzly Bears", "Lightning Bolt"],
            battlefield=["Mountain", "Plains"],
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Mountain", "Plains")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    life_before = alice.life

    scenario.will_take_the_may(True, source="Thrilling Discovery")
    scenario.will_choose_cards(bears, bolt, username="alice")

    scenario.cast_and_resolve("Thrilling Discovery", *sources)

    assert alice.life == life_before + 2
    assert bears.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.GRAVEYARD
    assert len(alice.hand) == 3


def test_thrilling_discovery_declining_the_discard_draws_nothing():
    """CR 608.2d: declining is always legal, and the draw never runs
    without the discard that gates it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Thrilling Discovery", "Grizzly Bears"],
            battlefield=["Mountain", "Plains"],
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Mountain", "Plains")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    life_before = alice.life

    scenario.will_take_the_may(False, source="Thrilling Discovery")

    scenario.cast_and_resolve("Thrilling Discovery", *sources)

    assert alice.life == life_before + 2
    assert bears.zone is Zone.HAND
    assert alice.hand == [bears]


def test_fable_ii_discards_up_to_two_then_records_a_notice_for_the_unread_draw():
    """Fable of the Mirror-Breaker's chapter II: "You may discard up to two
    cards. If you do, draw that many cards." The discard itself now reads
    (CR 107.1c's "up to two" is a non-exact `_discard_cards` choice); the
    "draw that many cards" consequence still has no reader until Group 0b's
    channel lands, so it is recorded as an `UnmodeledTriggerEffectNotice`
    (CR 608.2c: the discard already ran, in order) instead of the whole
    chapter silently doing nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Lightning Bolt"],
            battlefield=["Fable of the Mirror-Breaker"],
            library=["Forest"] * 3,
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    # Clear out chapter I's own trigger (a token, no decisions) so only
    # chapter II's own trigger is on the stack below.
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 1

    scenario.will_take_the_may(True, source="Fable of the Mirror-Breaker")
    scenario.will_choose_cards(bears, bolt, username="alice")

    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.GRAVEYARD
    assert alice.hand == []
    notices = scenario.game.unmodeled_trigger_effect_notices
    assert len(notices) == 1
    assert "draw that many cards" in notices[0].text


def test_fable_ii_declining_the_discard_records_no_notice():
    """CR 608.2d again: declining the discard never reaches the unreadable
    consequence at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Fable of the Mirror-Breaker"],
            library=["Forest"] * 3,
        )
        .player("bob")
        .build()
    )
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()

    scenario.will_take_the_may(False, source="Fable of the Mirror-Breaker")

    scenario.resolve_top()

    assert bears.zone is Zone.HAND
    assert scenario.player("alice").hand == [bears]
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_a_saga_placed_on_the_battlefield_already_carries_chapter_ones_lore_counter():
    """CR 714.3a's intrinsic lore counter - the same one
    `tests/scenarios/test_sagas.py` confirms for History of Benalia - is
    what makes one `saga_lore_step()` call above enough to reach chapter II."""
    scenario = Scenario().player("alice", battlefield=["Fable of the Mirror-Breaker"]).build()
    saga = scenario.find("Fable of the Mirror-Breaker", Zone.BATTLEFIELD)
    assert saga.counters[Counter.LORE] == 1
