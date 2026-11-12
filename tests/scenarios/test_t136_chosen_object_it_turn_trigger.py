"""A turn-scoped delayed triggered ability about one chosen object, written
with the bare pronoun: "Whenever it <event> this turn, <effect>".

`test_nw01_chosen_creature_delayed_triggers.py` covers the "Whenever that
creature ..." wording (Hunter's Insight, Arcbond, Niko Aris). This file is
the same ability written "Whenever it ...":

- **The Inner Light**, chapter II (a Saga's triggered ability) - "Choose
  target creature. Whenever it deals combat damage to a player this turn,
  you draw that many cards."
- **Fire Giant's Fury** (proof printing, a different set and wording) -
  "Target Giant you control gets +2/+2 and gains trample until end of
  turn. Whenever it deals combat damage to a player this turn, exile that
  many cards from the top of your library. Until the end of your next turn,
  you may play those cards." A spell, no "Choose" opener: "it" is the
  pumped target, and the delayed ability's body is two sentences.

Rules, each looked up with `mise run rules:find` in the session that wrote
this file:

- **CR 107.15a** - a chapter symbol is a triggered ability ("When one or
  more lore counters are put onto this Saga ...").
- **CR 603.7a** - resolving the chapter ability (or the spell) creates the
  delayed triggered ability.
- **CR 603.7b** - "this turn" is a stated duration: it triggers on every
  matching event that turn, and not after.
- **CR 603.7c** - it refers to that particular object; another creature, or
  the same card after it left and came back (CR 400.7), is not it.
- **CR 603.7e** - an ability's delayed ability has that ability's source
  and controller, so "you draw" is the Saga controller's draw.
- **CR 120.2a** - combat damage is dealt by attacking and blocking creatures
  in the combat damage step; other damage is not combat damage.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# The Inner Light, chapter II
# --------------------------------------------------------------------------


def _inner_light_board(*, bob_battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "The Inner Light",
                "Hill Giant",
                "Grizzly Bears",
                "Fencing Ace",
                "Raging Goblin",
            ],
            library=["Island"] * 8,
        )
        .player("bob", battlefield=bob_battlefield or [], life=20)
    )


def _chapter_two(scenario, target) -> None:
    """Advance the Saga to chapter II with `target` chosen and resolve it."""
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("The Inner Light", [target])
    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def _combat(scenario, attacker, *, blocker=None) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    if blocker is None:
        scenario.no_blocks()
    else:
        scenario.block(attacker, blocker)
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()


def test_chapter_two_draws_as_many_cards_as_the_chosen_creature_deals_to_a_player():
    scenario = _inner_light_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    _chapter_two(scenario, giant)
    hand_before = len(scenario.player("alice").hand)

    _combat(scenario, giant)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17
    assert len(scenario.player("alice").hand) == hand_before + 3


def test_chapter_two_creates_one_delayed_trigger_that_lasts_the_turn():
    """CR 603.7a/b: resolving the chapter creates the ability, and "this turn"
    is its stated duration (`expires_end_of_turn`, any number of times)."""
    scenario = _inner_light_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    _chapter_two(scenario, giant)

    (trigger,) = scenario.game.delayed_triggers.triggers
    assert trigger.expires_end_of_turn
    assert trigger.remaining is None
    assert trigger.controller == "alice"
    scenario.game.delayed_triggers.expire_this_turn()
    assert scenario.game.delayed_triggers.triggers == []


def test_chapter_two_ignores_combat_damage_from_another_creature():
    """CR 603.7c: "it" is the chosen creature; Grizzly Bears connecting draws
    nothing."""
    scenario = _inner_light_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _chapter_two(scenario, giant)
    hand_before = len(scenario.player("alice").hand)

    _combat(scenario, bears)

    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 18
    assert len(scenario.player("alice").hand) == hand_before


def test_chapter_two_ignores_combat_damage_to_a_blocker():
    """ "to a player": damage the chosen creature deals to a blocking
    creature is not it."""
    scenario = _inner_light_board(bob_battlefield=["Savannah Lions"]).build()
    giant = scenario.creature("Hill Giant", "alice")
    lions = scenario.creature("Savannah Lions", "bob")
    _chapter_two(scenario, giant)
    hand_before = len(scenario.player("alice").hand)

    _combat(scenario, giant, blocker=lions)

    assert scenario.stack_names() == []
    assert lions.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before


def test_chapter_two_ignores_noncombat_damage_from_the_chosen_creature():
    """CR 120.2a: only combat damage counts."""
    scenario = _inner_light_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    _chapter_two(scenario, giant)
    hand_before = len(scenario.player("alice").hand)

    scenario.game.deal_damage(scenario.player("bob"), 3, source=giant)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert len(scenario.player("alice").hand) == hand_before


def test_chapter_two_triggers_on_each_combat_damage_step_of_a_double_striker():
    """CR 603.7b: a stated duration ("this turn") makes the ability trigger
    every time its event occurs, not once - a double striker deals combat
    damage in both combat damage steps and draws for each."""
    scenario = _inner_light_board().build()
    ace = scenario.creature("Fencing Ace", "alice")
    _chapter_two(scenario, ace)
    hand_before = len(scenario.player("alice").hand)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ace)
    scenario.no_blocks()
    for _ in range(2):  # CR 510.4: the first-strike step, then the regular one
        scenario.game.combat_damage_step()
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()

    assert scenario.player("bob").life == 18
    assert len(scenario.player("alice").hand) == hand_before + 2


def test_chapter_two_forgets_a_chosen_creature_that_left_and_came_back():
    """CR 603.7c / CR 400.7: a creature that left the battlefield and
    returned is a new object the ability never named. Raging Goblin has
    haste, so the returned one can still attack and connect this turn."""
    scenario = _inner_light_board().build()
    goblin = scenario.creature("Raging Goblin", "alice")
    _chapter_two(scenario, goblin)

    scenario.game.return_to_hand(goblin)
    returned = scenario.find("Raging Goblin", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(returned, "alice")
    hand_before = len(scenario.player("alice").hand)
    _combat(scenario, returned)

    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 19
    assert len(scenario.player("alice").hand) == hand_before


def test_chapter_two_is_no_longer_silent():
    """The chapter reads as a real effect, not a silent no-op."""
    from magic_cards_model.support import classify_clauses
    from tests.cards import card

    outcomes = classify_clauses(card("The Inner Light"))
    assert [outcome.category for outcome in outcomes] == ["handled", "handled", "handled"]


# --------------------------------------------------------------------------
# Fire Giant's Fury (proof printing)
# --------------------------------------------------------------------------


def _fury_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Fire Giant's Fury"],
            battlefield=["Mountain", "Mountain", "Hill Giant", "Grizzly Bears"],
            library=["Lightning Bolt", "Mountain", "Shock", "Island", "Forest"],
        )
        .player("bob", life=20)
    )


def test_fury_exiles_as_many_cards_as_the_giant_deals_and_lets_alice_play_them():
    scenario = _fury_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Fire Giant's Fury", auto=True, targets=[giant])

    assert scenario.game.power_of(giant) == 5

    _combat(scenario, giant)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 15
    exiled = [state.name for state in scenario.game.exile]
    assert exiled == ["Lightning Bolt", "Mountain", "Shock", "Island", "Forest"]
    bolt = scenario.find("Lightning Bolt", Zone.EXILE, "alice")
    assert scenario.game.play_permission_for(bolt, "alice") is not None


def test_fury_does_not_fire_for_a_creature_it_did_not_target():
    scenario = _fury_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Fire Giant's Fury", auto=True, targets=[giant])

    _combat(scenario, bears)

    assert scenario.stack_names() == []
    assert scenario.game.exile == []


# --------------------------------------------------------------------------
# Long River Lurker (the "that creature" wording after a targeted head, with
# a two-sentence body; a notice before the head-then-trigger reader)
# --------------------------------------------------------------------------


def _lurker_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Long River Lurker"],
            battlefield=["Hill Giant", "Grizzly Bears"],
            library=["Island"] * 3,
        )
        .player("bob", battlefield=["Savannah Lions"], life=20)
    )


def _lurker_enters_targeting(scenario, target) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Long River Lurker", [target])
    scenario.put_onto_battlefield("Long River Lurker", "alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def test_lurker_makes_the_target_unblockable_and_blinks_it_after_it_connects():
    """The head ("can't be blocked this turn") applies to the target, and the
    created trigger exiles and returns that creature once it deals combat
    damage (CR 603.7c: that one creature)."""
    scenario = _lurker_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    lions = scenario.creature("Savannah Lions", "bob")
    _lurker_enters_targeting(scenario, giant)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant)
    with pytest.raises(ValueError):
        scenario.block(giant, lions)  # the target can't be blocked this turn
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(True)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17
    returned = scenario.creature("Hill Giant", "alice")
    assert returned.zone is Zone.BATTLEFIELD
    assert returned not in scenario.attackers(), "a new object, removed from combat (CR 400.7)"


def test_lurker_trigger_ignores_another_creatures_combat_damage():
    scenario = _lurker_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _lurker_enters_targeting(scenario, giant)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_lurker_declining_the_may_leaves_the_creature_in_combat():
    """ "If you do": declining the exile returns nothing and moves nothing."""
    scenario = _lurker_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    _lurker_enters_targeting(scenario, giant)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(False)
    scenario.pass_until_resolved()

    assert giant.zone is Zone.BATTLEFIELD
    assert giant in scenario.attackers()
    assert scenario.game.exile == []
