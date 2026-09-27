"""Scenario: three "this turn" history facts `machines/conditions/history.py`
did not yet read, or read only in a narrower shape than the card printed.

- **Haliya, Guided by Light**: "At the beginning of your end step, draw a
  card if you've gained 3 or more life this turn." `_life_this_turn`'s own
  reader already answered "you gained 3 or more life this turn" (no
  contraction); the printed "you've" - the shape every other reader in this
  family already accepts (`_drew`, `_discarded`, `_cast_a_spell`) - was
  simply never added to this one reader's pattern, so the whole clause
  (reached the same way through `Game.condition_holds` a resolution "if"
  always is) never matched at all.
- **Proft's Eidetic Memory**: "At the beginning of combat on your turn, if
  you've drawn more than one card this turn, put X +1/+1 counters on target
  creature you control, where X is the number of cards you've drawn this
  turn minus one." A genuine CR 603.4 intervening if (the "if" immediately
  follows the trigger event) - `_drew`'s reader only read "`<N>` or more
  cards", never "more than `<N>`", so the ability never triggered at all
  and its otherwise-already-generic X ("the number of cards you've drawn
  this turn", `machines/effects._COUNT_CARDS_DRAWN_THIS_TURN_RE`, "minus
  one" read by the already-generic `amount_expression`) never ran either.
- **Obsessive Pursuit**: "Whenever you attack, put X +1/+1 counters on
  target attacking creature, where X is the number of permanents you've
  sacrificed this turn. If X is three or more, that creature gains lifelink
  until end of turn." The attack trigger and the counter-placement effect
  were already generic; "the number of permanents you've sacrificed this
  turn" had no `count_expression` reader of its own at all.

No Modern/Pioneer/Standard-legal second printing was found for "you've
gained `<N>` or more life this turn" (the contraction specifically), "you've
drawn more than one card this turn", or "the number of permanents you've
sacrificed this turn" - recorded in `MEMORY.md` rather than asserted. Every
reader here is the same shared, already-generic family (`machines/
conditions/history.py`'s `READERS`, `machines/effects.count_expression`)
every other card in the pool already reaches through `Game.condition_holds`/
`amount_expression` - none of it is gated on these three cards' names.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

HALIYA = "Haliya, Guided by Light"
PROFT = "Proft's Eidetic Memory"
OBSESSIVE_PURSUIT = "Obsessive Pursuit"


# ---------------------------------------------------------------------------
# Haliya, Guided by Light
# ---------------------------------------------------------------------------


def _advance_to_end_step(scenario: Scenario) -> None:
    """`Scenario.start_at` only moves the raw step pointer (`Turn.advance_to`)
    - it never runs a step's own turn-based actions or fires its "beginning
    of" trigger, so reaching the end step through it leaves Haliya's own
    trigger never raised at all. `Scenario.advance()` (`Game.advance`) is the
    real door, the same way `_to_bobs` in `test_any_turn_loyalty.py` already
    drives it."""
    while scenario.step is not Step.END_STEP:
        scenario.advance()


def test_haliya_draws_a_card_at_end_step_after_gaining_three_or_more_life():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Helix"],
            library=["Forest"],
            battlefield=[HALIYA, "Mountain", "Plains"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)
    (mountain, plains) = scenario.untapped_sources("Mountain", "Plains")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Lightning Helix", mountain, plains, targets=[bears])
    assert scenario.player("alice").life == 23, "Lightning Helix gains 3 life"

    _advance_to_end_step(scenario)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{HALIYA}'s triggered ability"]
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == hand_before - 1 + 1, "Helix spent, then drawn"


def test_haliya_does_not_draw_below_three_life_gained():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=[HALIYA])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)
    _advance_to_end_step(scenario)
    scenario.game.put_triggers_on_stack()
    # The ability itself is unconditional (CR 603.4: the "if" here is inside
    # the effect text, not right after the trigger event) - only the draw at
    # resolution is gated.
    assert scenario.stack_names() == [f"{HALIYA}'s triggered ability"]
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == hand_before


# ---------------------------------------------------------------------------
# Proft's Eidetic Memory
# ---------------------------------------------------------------------------


def test_profts_eidetic_memory_counters_target_creature_by_extra_cards_drawn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[PROFT],
            library=["Mountain", "Forest", "Island"],
            battlefield=["Island", "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (island, mountain) = scenario.untapped_sources("Island", "Mountain")
    scenario.cast_and_resolve(PROFT, island, mountain)
    scenario.game.put_triggers_on_stack()  # Proft's own ETB draw
    scenario.resolve_top()  # 1 card drawn so far
    scenario.game.draw_cards("alice", 1)  # a second card, no intervening if to clear

    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{PROFT}'s triggered ability"]
    scenario.choose_trigger_targets(PROFT, [bears])
    scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 1, "2 cards drawn this turn, minus one"


def test_profts_eidetic_memory_does_not_trigger_on_exactly_one_card_drawn():
    scenario = (
        Scenario()
        .player("alice", hand=[PROFT], library=["Forest"], battlefield=["Island", "Mountain"])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island, mountain) = scenario.untapped_sources("Island", "Mountain")
    scenario.cast_and_resolve(PROFT, island, mountain)
    scenario.game.put_triggers_on_stack()  # the ETB draw: exactly one card this turn
    scenario.resolve_top()

    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


# ---------------------------------------------------------------------------
# Obsessive Pursuit
# ---------------------------------------------------------------------------


def test_obsessive_pursuit_counters_by_permanents_sacrificed_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[OBSESSIVE_PURSUIT, "Grizzly Bears", "Hill Giant", "Mountain"],
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    giant = scenario.creature("Hill Giant", "alice")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    scenario.game.sacrifice(giant)
    scenario.game.sacrifice(mountain)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{OBSESSIVE_PURSUIT}'s triggered ability"]
    scenario.choose_trigger_targets(OBSESSIVE_PURSUIT, [bears])
    scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 2, "two permanents sacrificed this turn"


def test_obsessive_pursuit_grants_lifelink_only_at_three_or_more_sacrificed():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                OBSESSIVE_PURSUIT,
                "Grizzly Bears",
                "Hill Giant",
                "Mountain",
                "Forest",
            ],
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    for name in ("Hill Giant", "Mountain", "Forest"):
        scenario.game.sacrifice(scenario.find(name, Zone.BATTLEFIELD, "alice"))

    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()
    scenario.choose_trigger_targets(OBSESSIVE_PURSUIT, [bears])
    scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 3
    from magic_cards_model.machines.combat import has_keyword

    assert has_keyword(bears, "lifelink", scenario.game)
