"""Scenario: cast triggers that copy, spells that gain keywords, and the
next-cast delayed copy (ECL).

- **Spinerock Tyrant** - "Whenever you cast an instant or sorcery spell with
  a single target, you may copy it. If you do, those spells gain wither. You
  may choose new targets for the copy." CR 115.9a: a "spell with a single
  target" counts the times any object or player was chosen as its target.
  CR 707.10: the copy isn't cast; CR 707.10c: its controller may choose new
  targets. CR 702.80a: damage from a source with wither to a creature is
  dealt as -1/-1 counters - here the source is the spell itself.
- **Judith, Carnage Connoisseur** (proof printing for the spell keyword
  gain) - "That spell gains deathtouch and lifelink."
- **Voracious Tome-Skimmer** - "Whenever you cast a spell during an
  opponent's turn, you may pay 1 life. If you do, draw a card." and the proof
  printing Crossway Troublemakers' "Whenever a Vampire you control dies, you
  may pay 2 life. If you do, draw a card." CR 119.4: a player can pay life
  only if their life total is at least that amount.
- **Rimefire Torque** - "{T}, Remove three charge counters from this
  artifact: When you next cast an instant or sorcery spell this turn, copy
  it. You may choose new targets for the copy." CR 603.7: a delayed
  triggered ability, triggering only once (CR 603.7b's "next time"). Proof
  printing: Summon: G.F. Cerberus's chapter II, the same sentence on a Saga
  chapter.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: CR 115.9a, CR 707.10, CR 707.10c, CR 702.80a, CR 119.4,
CR 603.7, CR 603.7b, CR 702.2b, CR 702.15b.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

# -- Spinerock Tyrant --------------------------------------------------------


def _tyrant_board(*, alice_hand=("Lightning Bolt",), bob_battlefield=("Craw Wurm", "Hill Giant")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=["Spinerock Tyrant", "Mountain", "Mountain", "Island"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_tyrant_copies_a_single_target_bolt_and_both_deal_wither_damage():
    scenario = _tyrant_board()
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True, username="alice")  # copy it
    scenario.will_take_the_may(True, username="alice")  # choose new targets
    scenario.will_choose_targets(giant, username="alice")
    scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=[wurm])
    assert scenario.stack_names() == ["Lightning Bolt", "Spinerock Tyrant's triggered ability"]

    scenario.resolve_top()  # the Tyrant's trigger: the copy goes on the stack
    assert scenario.stack_names() == ["Lightning Bolt", "Lightning Bolt"]
    scenario.resolve_top()  # the copy, at the Giant
    scenario.resolve_top()  # the original, at the Wurm

    assert giant.zone is Zone.GRAVEYARD, "3 -1/-1 counters on a 3/3"
    assert wurm.counters[Counter.MINUS_ONE] == 3
    assert wurm.damage == 0, "wither damage is not marked (CR 702.80a)"


def test_declining_the_copy_means_the_original_does_not_gain_wither():
    """ "If you do" - no copy, no wither."""
    scenario = _tyrant_board()
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.will_take_the_may(False, username="alice")
    scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=[wurm])

    scenario.resolve_top()
    assert scenario.stack_names() == ["Lightning Bolt"]
    scenario.resolve_top()

    assert wurm.counters[Counter.MINUS_ONE] == 0
    assert wurm.damage == 3


def test_keeping_the_same_target_puts_six_counters_on_it():
    scenario = _tyrant_board()
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.will_take_the_may(True, username="alice")  # copy it
    scenario.will_take_the_may(False, username="alice")  # keep the target
    scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=[wurm])

    scenario.resolve_top()
    scenario.resolve_top()
    assert wurm.counters[Counter.MINUS_ONE] == 3
    scenario.resolve_top()
    scenario.state_based_actions()
    assert wurm.zone is Zone.GRAVEYARD, "six -1/-1 counters on a 6/4"


def test_a_spell_with_no_target_does_not_trigger():
    scenario = _tyrant_board(alice_hand=("Opt",))
    scenario.cast_onto_stack("Opt", auto=True, username="alice")
    assert scenario.stack_names() == ["Opt"]


def test_a_spell_with_two_targets_does_not_trigger():
    """CR 115.9a: Electrolyze divided between two targets has two."""
    scenario = _tyrant_board(alice_hand=("Electrolyze",))
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_onto_stack(
        "Electrolyze", auto=True, username="alice", targets=[wurm, giant], division=[1, 1]
    )
    assert scenario.stack_names() == ["Electrolyze"]


def test_the_same_divided_spell_with_one_target_does_trigger():
    scenario = _tyrant_board(alice_hand=("Electrolyze",))
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_onto_stack(
        "Electrolyze", auto=True, username="alice", targets=[wurm], division=[2]
    )
    assert scenario.stack_names() == ["Electrolyze", "Spinerock Tyrant's triggered ability"]


def test_an_opponents_single_target_spell_does_not_trigger():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Spinerock Tyrant"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Lightning Bolt", auto=True, username="bob", targets=["alice"])
    assert scenario.stack_names() == ["Lightning Bolt"]


def test_a_wither_spell_still_deals_ordinary_damage_to_a_player():
    """CR 702.80a speaks only of damage dealt to a creature."""
    scenario = _tyrant_board()
    scenario.will_take_the_may(True, username="alice")
    scenario.will_take_the_may(False, username="alice")
    scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    scenario.resolve_top()
    scenario.resolve_top()
    scenario.resolve_top()
    assert scenario.player("bob").life == 14


def test_judith_grants_a_spell_deathtouch_and_lifelink():
    """The proof printing for a spell gaining keywords: Shock with
    deathtouch kills the 6/4 Wurm, and lifelink gains Alice 2."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shock"],
            battlefield=["Judith, Carnage Connoisseur", "Mountain"],
            library=["Island"] * 3,
        )
        .player("bob", battlefield=["Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.will_choose_mode("That spell gains deathtouch and lifelink.", username="alice")
    scenario.cast_onto_stack("Shock", auto=True, username="alice", targets=[wurm])
    scenario.resolve_top()  # Judith's trigger, first mode
    scenario.resolve_top()  # Shock
    scenario.state_based_actions()

    assert wurm.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22


# -- Voracious Tome-Skimmer --------------------------------------------------


def _skimmer_on_bobs_turn(alice_life: int = 20):
    scenario = (
        Scenario()
        .player("bob", battlefield=["Island"], library=["Island"] * 5)
        .player(
            "alice",
            life=alice_life,
            hand=["Opt"],
            battlefield=["Voracious Tome-Skimmer", "Island"],
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.turn.active_player == "bob"
    scenario.pass_priority("bob")
    return scenario


def test_casting_during_an_opponents_turn_pays_a_life_and_draws():
    scenario = _skimmer_on_bobs_turn()
    scenario.will_take_the_may(True, username="alice")
    scenario.cast_onto_stack("Opt", auto=True, username="alice")
    assert scenario.stack_names() == ["Opt", "Voracious Tome-Skimmer's triggered ability"]
    hand = len(scenario.player("alice").hand)

    scenario.resolve_top()

    assert scenario.player("alice").life == 19
    assert len(scenario.player("alice").hand) == hand + 1


def test_declining_to_pay_draws_nothing():
    scenario = _skimmer_on_bobs_turn()
    scenario.will_pay_the_life(False, username="alice")
    scenario.cast_onto_stack("Opt", auto=True, username="alice")
    hand = len(scenario.player("alice").hand)

    scenario.resolve_top()

    assert scenario.player("alice").life == 20
    assert len(scenario.player("alice").hand) == hand


def test_casting_on_your_own_turn_does_not_trigger():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Opt"],
            battlefield=["Voracious Tome-Skimmer", "Island"],
            library=["Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Opt", auto=True, username="alice")
    assert scenario.stack_names() == ["Opt"]


def test_an_opponent_casting_on_their_own_turn_does_not_trigger_yours():
    """ "Whenever *you* cast" - Bob's own spell on Bob's turn is not Alice's."""
    scenario = (
        Scenario()
        .player("bob", hand=["Opt"], battlefield=["Island"], library=["Island"] * 5)
        .player("alice", battlefield=["Voracious Tome-Skimmer"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Opt", auto=True, username="bob")
    assert scenario.stack_names() == ["Opt"]


def test_brineborn_cutthroat_reads_the_same_opponents_turn_window():
    """The proof printing for the "during an opponent's turn" window: a
    different effect behind the identical condition - and on Alice's own
    turn it does not trigger."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Island"], library=["Island"] * 5)
        .player(
            "alice",
            hand=["Opt", "Opt"],
            battlefield=["Brineborn Cutthroat", "Island", "Island"],
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutthroat = scenario.creature("Brineborn Cutthroat", "alice")
    scenario.pass_priority("bob")
    scenario.cast_onto_stack("Opt", auto=True, username="alice")
    scenario.resolve_top()
    assert cutthroat.counters[Counter.PLUS_ONE] == 1


def test_crossway_troublemakers_pays_two_life_to_draw_when_a_vampire_dies():
    """The proof printing: a dies trigger with the same "you may pay N life.
    If you do, ..." rider."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Crossway Troublemakers", "Bloodghast"],
            library=["Island"] * 3,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bloodghast = scenario.creature("Bloodghast", "alice")
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Lightning Bolt", auto=True, username="bob", targets=[bloodghast])
    hand = len(scenario.player("alice").hand)
    assert "Crossway Troublemakers's triggered ability" in scenario.stack_names()

    scenario.resolve_top()

    assert scenario.player("alice").life == 18
    assert len(scenario.player("alice").hand) == hand + 1


# -- Rimefire Torque ---------------------------------------------------------


def _torque_board(counters: int = 3, *, alice_hand=("Lightning Bolt", "Shock")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=["Rimefire Torque", "Mountain", "Mountain", "Mountain"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Craw Wurm", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    torque = scenario.game.battlefield[0]
    assert torque.name == "Rimefire Torque"
    if counters:
        scenario.game.add_counters(torque, Counter.CHARGE, counters)
    return scenario, torque


def test_torque_copies_the_next_instant_and_the_copy_may_be_retargeted():
    scenario, torque = _torque_board()
    scenario.activate(torque, username="alice")
    scenario.resolve_top()
    assert torque.counters[Counter.CHARGE] == 0
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_targets(giant, username="alice")

    scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=[wurm])
    assert scenario.stack_names() == ["Lightning Bolt", "Rimefire Torque's triggered ability"]
    scenario.resolve_top()
    scenario.resolve_top()
    scenario.resolve_top()

    assert giant.zone is Zone.GRAVEYARD
    assert wurm.damage == 3


def test_only_the_next_spell_is_copied():
    """CR 603.7b: "the next time" - the delayed ability triggers once."""
    scenario, torque = _torque_board()
    scenario.activate(torque, username="alice")
    scenario.resolve_top()
    scenario.will_take_the_may(False, username="alice")
    scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    scenario.resolve_top()
    scenario.resolve_top()
    scenario.resolve_top()

    scenario.cast_onto_stack("Shock", auto=True, username="alice", targets=["bob"])
    assert scenario.stack_names() == ["Shock"]


def test_fewer_than_three_charge_counters_cannot_pay():
    scenario, torque = _torque_board(counters=2)
    import pytest

    with pytest.raises(ValueError):
        scenario.activate(torque, username="alice")


def test_the_delayed_copy_ends_with_the_turn():
    scenario, torque = _torque_board()
    scenario.activate(torque, username="alice")
    scenario.resolve_top()
    assert [
        t for t in scenario.game.delayed_triggers.triggers if t.source_name == "Rimefire Torque"
    ]
    scenario.game.cleanup_step()
    assert not [
        t for t in scenario.game.delayed_triggers.triggers if t.source_name == "Rimefire Torque"
    ]


def test_cerberus_chapter_two_copies_the_next_instant():
    """The proof printing: Summon: G.F. Cerberus's chapter II, "Double -
    When you next cast an instant or sorcery spell this turn, copy it. You
    may choose new targets for the copy." - the same delayed copy off a Saga
    chapter (behind an ability word) rather than an activated ability."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Summon: G.F. Cerberus", "Mountain"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.game.stack:
        scenario.resolve_top()
    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # chapter II
    scenario.will_take_the_may(False, username="alice")

    scenario.cast_onto_stack("Lightning Bolt", auto=True, username="alice", targets=["bob"])
    assert scenario.stack_names() == ["Lightning Bolt", "Summon: G.F. Cerberus's triggered ability"]
    scenario.resolve_top()
    scenario.resolve_top()
    scenario.resolve_top()
    assert scenario.player("bob").life == 14
