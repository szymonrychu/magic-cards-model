"""Counters removed off a target, and a modal spell that reaches for that
plus a hand-exile:

- **Rhys, the Evermore**'s activated ability, "{W}, {T}: Remove any number of
  counters from target creature you control." (CR 122.5). CR 608.2d would
  let the controller choose fewer than every counter present, but no
  `DecisionKind` exists yet for an open-ended amount unconnected to a cost -
  the same scoped simplification `machines/effects._parse_remove_up_to_n_
  counters_from_target_clause` already records for "remove up to N", so this
  always takes the maximum: every counter of every kind comes off. No second
  Modern/Pioneer/Standard-legal printing of this exact phrase turned up on a
  Scryfall full-text search - only Rhys itself and Eventide's Shadow, which
  is legal nowhere (dated MEMORY.md line records the search).
- **Perfect Intimidation**'s own "Choose one or both — • Target opponent
  exiles two cards from their hand. • Remove all counters from target
  creature." CR 700.2's "Choose one or both" was already fully generic in
  `machines/modes.py` before this task (`_OR_MORE`'s own "or both"
  alternation), and "Remove all counters from target creature." was already
  `machines/effects._parse_remove_all_counters_from_target_clause`'s shape -
  the only missing piece was "Target opponent exiles two cards from their
  hand.", `machines/minus_counters._parse_target_opponent_exiles_from_hand_
  clause`, CR 701.9b's default-chooser shape (the same one `machines/
  effects._parse_target_player_discards_clause` already gives its own
  discard sibling) read for CR 406's exile instead.

Aim for the Head (Pioneer/Modern-legal, off pool) - "Choose one — • Exile
target Zombie. • Target opponent exiles two cards from their hand." - proves
the exile-from-hand reader on a second printing, in a "Choose one" (not
"one or both") modal spell with an entirely different first mode.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_rhys_removes_every_counter_of_every_kind_from_target_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rhys, the Evermore", "Grizzly Bears", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rhys = scenario.creature("Rhys, the Evermore")
    bears = scenario.creature("Grizzly Bears")
    bears.add_counters(Counter.PLUS_ONE, 3)
    bears.add_counters(Counter.MINUS_ONE, 1)
    (plains,) = scenario.untapped_sources("Plains")

    scenario.activate(rhys, plains, targets=[bears])
    scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 0
    assert bears.counter_count(Counter.MINUS_ONE) == 0


def test_rhys_removing_counters_from_a_creature_with_none_is_a_no_op():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rhys, the Evermore", "Grizzly Bears", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rhys = scenario.creature("Rhys, the Evermore")
    bears = scenario.creature("Grizzly Bears")
    (plains,) = scenario.untapped_sources("Plains")

    scenario.activate(rhys, plains, targets=[bears])
    scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_perfect_intimidation_choosing_both_modes():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
            hand=["Perfect Intimidation"],
        )
        .player("bob", hand=["Grizzly Bears", "Lightning Bolt"], battlefield=["Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "bob")
    wurm.add_counters(Counter.PLUS_ONE, 2)
    bob_hand_size = len(scenario.player("bob").hand)

    casting = scenario.cast("Perfect Intimidation", username="alice")
    casting.choose_modes([1, 2])
    casting.choose_targets(["bob", wurm])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    scenario.will_choose_cards(*scenario.player("bob").hand, username="bob")
    scenario.resolve_top()

    assert len(scenario.player("bob").hand) == bob_hand_size - 2
    assert wurm.counter_count(Counter.PLUS_ONE) == 0


def test_perfect_intimidation_choosing_only_the_exile_mode():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Swamp", "Swamp", "Swamp", "Swamp"], hand=["Perfect Intimidation"]
        )
        .player("bob", hand=["Grizzly Bears", "Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_hand_size = len(scenario.player("bob").hand)

    casting = scenario.cast("Perfect Intimidation", username="alice")
    casting.choose_modes([1])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    scenario.will_choose_cards(*scenario.player("bob").hand, username="bob")
    scenario.resolve_top()

    assert len(scenario.player("bob").hand) == bob_hand_size - 2
    for card_state in scenario.game.exile:
        assert card_state.zone is Zone.EXILE


def test_aim_for_the_head_off_pool_proves_the_exile_reader_is_not_perfect_intimidations():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Swamp", "Swamp", "Swamp"], hand=["Aim for the Head"])
        .player("bob", hand=["Grizzly Bears", "Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_hand_size = len(scenario.player("bob").hand)

    casting = scenario.cast("Aim for the Head", username="alice")
    casting.choose_modes([2])
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    scenario.will_choose_cards(*scenario.player("bob").hand, username="bob")
    scenario.resolve_top()

    assert len(scenario.player("bob").hand) == bob_hand_size - 2
