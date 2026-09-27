"""Self-removal triggers keyed on "while this creature has a -1/-1 counter on
it" (CR 603.4's intervening *if*, CR 603.2's "while" event qualifier), read
by shape and never by card:

- **"Whenever another creature you control enters while this creature has a
  -1/-1 counter on it, remove a -1/-1 counter from this creature."** -
  Bristlebane Battler, Reluctant Dounguard.
- **"Whenever this creature becomes tapped while it has a -1/-1 counter on
  it, remove a -1/-1 counter from it."** - Encumbered Reejerey.
- **"Whenever one or more permanent cards are put into your graveyard from
  anywhere while this creature has a -1/-1 counter on it, remove a -1/-1
  counter from this creature."** - Moonshadow.
- **"At the beginning of your end step, if there is an Elf card in your
  graveyard and this creature has a -1/-1 counter on it, remove a -1/-1
  counter from this creature."** - Creakwood Safewright (an ordinary
  intervening *if*, not an event qualifier - the trigger condition itself
  has no event to qualify).
- **"Whenever another creature you control dies, surveil 1, then remove a
  -1/-1 counter from this creature."** - Heirloom Auntie, no "while it has a
  counter" gate at all: the removal always runs, and CR 122.5 says removing
  what is not there simply removes nothing.

The "while `<this>` has a `<kind>` counter on it" qualifier itself is not new
- `machines/conditions/objects._has_counters` already reads any "`<subject>`
has/had `<quantity>` `<kind>` counter(s) on it" clause generically, both as
an intervening *if* (`machines/triggers.intervening_if_answer`) and as an
event qualifier (`machines/triggers.event_qualifier_holds`), so every trigger
condition above already worked before this file - what was missing on every
one of them was the *removal* itself, `machines/minus_counters._parse_
remove_a_counter_from_self_clause` and its "surveil, then remove" sibling.

Belligerent Hatchling (Modern-legal, not a listed card and not in any
`code/magic-cards-model-api/decks/*.txt` deck) proves the removal reader is
not fitted to any one trigger condition: its own "Whenever you cast a red
spell, remove a -1/-1 counter from this creature." carries no "while it has
a counter" gate at all, a cast trigger rather than an ETB/tap/graveyard one.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import GameEvent, TriggerEvent
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_bristlebane_battler_removes_a_counter_when_another_creature_enters():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bristlebane Battler"],
            hand=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battler = scenario.creature("Bristlebane Battler")
    battler.add_counters(Counter.MINUS_ONE, 2)

    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert battler.counter_count(Counter.MINUS_ONE) == 1


def test_bristlebane_battler_does_not_trigger_with_no_counter_on_it():
    """CR 603.4: the intervening *if* is false the moment the event occurs,
    so there is nothing on the stack to resolve at all - not a no-op
    resolution."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bristlebane Battler"], hand=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battler = scenario.creature("Bristlebane Battler")
    assert battler.counter_count(Counter.MINUS_ONE) == 0

    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_reluctant_dounguard_carries_the_identical_template():
    """A second printing of the exact same shape - proves the reader is the
    mechanic's, not Bristlebane Battler's own."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Reluctant Dounguard"], hand=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dounguard = scenario.creature("Reluctant Dounguard")
    dounguard.add_counters(Counter.MINUS_ONE, 1)

    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert dounguard.counter_count(Counter.MINUS_ONE) == 0


def test_encumbered_reejerey_removes_a_counter_when_it_becomes_tapped():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Encumbered Reejerey", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reejerey = scenario.creature("Encumbered Reejerey")
    reejerey.add_counters(Counter.MINUS_ONE, 2)

    scenario.attack_with(reejerey)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert reejerey.counter_count(Counter.MINUS_ONE) == 1


def test_moonshadow_removes_a_counter_when_a_permanent_card_reaches_its_graveyard():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Moonshadow", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    moonshadow = scenario.creature("Moonshadow")
    moonshadow.add_counters(Counter.MINUS_ONE, 3)
    bears = scenario.creature("Grizzly Bears")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert moonshadow.counter_count(Counter.MINUS_ONE) == 2


def test_creakwood_safewright_end_step_with_elf_in_graveyard_and_a_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Creakwood Safewright"],
            graveyard=["Llanowar Elves"],
        )
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    safewright = scenario.creature("Creakwood Safewright")
    safewright.add_counters(Counter.MINUS_ONE, 1)

    scenario.start_at(Step.END_STEP)
    scenario.game.emit(
        GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=Step.END_STEP, player="alice")
    )
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert safewright.counter_count(Counter.MINUS_ONE) == 0


def test_creakwood_safewright_does_not_remove_without_an_elf_card_in_the_graveyard():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Creakwood Safewright"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    safewright = scenario.creature("Creakwood Safewright")
    safewright.add_counters(Counter.MINUS_ONE, 1)

    scenario.start_at(Step.END_STEP)
    scenario.game.emit(
        GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=Step.END_STEP, player="alice")
    )
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert safewright.counter_count(Counter.MINUS_ONE) == 1


def test_heirloom_auntie_surveils_then_removes_a_counter_when_another_creature_dies():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Heirloom Auntie", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    auntie = scenario.creature("Heirloom Auntie")
    auntie.add_counters(Counter.MINUS_ONE, 2)
    bears = scenario.creature("Grizzly Bears")

    scenario.surveil_keeping_everything_on_top(username="alice")
    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert auntie.counter_count(Counter.MINUS_ONE) == 1


def test_heirloom_auntie_removing_nothing_when_it_has_no_counter_is_a_no_op():
    """CR 122.5: removing what is not there removes nothing - the surveil
    still happens, but the missing counter is not an error."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Heirloom Auntie", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    auntie = scenario.creature("Heirloom Auntie")
    bears = scenario.creature("Grizzly Bears")

    scenario.surveil_keeping_everything_on_top(username="alice")
    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert auntie.counter_count(Counter.MINUS_ONE) == 0


def test_belligerent_hatchling_removes_a_counter_on_a_cast_trigger_with_no_while_gate():
    """Belligerent Hatchling (Modern-legal, off-pool): the identical bare
    removal reader, on a trigger condition with no "while it has a counter"
    qualifier at all - proof the removal is read independently of the
    trigger condition it happens to sit behind."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Belligerent Hatchling", "Mountain"], hand=["Lightning Bolt"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hatchling = scenario.creature("Belligerent Hatchling")
    hatchling.add_counters(Counter.MINUS_ONE, 4)
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert hatchling.counter_count(Counter.MINUS_ONE) == 3
    assert hatchling.zone is Zone.BATTLEFIELD
