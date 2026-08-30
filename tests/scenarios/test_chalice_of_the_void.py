"""Scenario: Chalice of the Void - "This artifact enters with X charge
counters on it. Whenever a player casts a spell with mana value equal to the
number of charge counters on this artifact, counter that spell."

Every CR number below was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.

Two gaps kept this card silent before this file:

1. **The trigger condition was reading the wrong number.**
   `machines/triggers.condition_matches` already had a regex
   (`_MANA_VALUE_EQUALS_COUNTERS`) for this shape, but it compared the
   charge-counter count against `event.subject_card.cmc` - the spell's
   *printed* mana value. **CR 202.3e**: "When calculating the mana value of
   an object with an {X} in its mana cost, X is treated as 0 while the
   object is not on the stack, and X is treated as the number chosen for it
   while the object is on the stack." A printed `Card.cmc` is always the
   off-stack, X-as-0 reading (**CR 107.3g**), so an `{X}` spell's real
   on-stack mana value was never seen: a Chalice on 3 would not catch a
   Walking Ballista cast for X=3 (real mana value 6 for its `{X}{X}` cost,
   printed cmc 0), and would instead wrongly catch a Walking Ballista cast
   for X=0 if 0 happened to equal its own count some other way. `Game.
   put_on_stack` now computes the spell's real on-stack mana value - printed
   cmc plus `x_value` once per `{X}` in the cost (**CR 107.3i**: "Normally,
   all instances of X on an object have the same value at any given time",
   which is why a `{X}{X}` cost is `2 * x_value`, not `x_value` - Walking
   Ballista cast for X=1 has mana value 2, not 1) - and carries it on the
   emitted `GameEvent.amount`, which the condition now reads in preference to
   the printed `subject_card.cmc`.
2. **There was no effect at all.** `_parse_counter_that_spell_clause` in
   `machines/effects.py` is the fix: a generic clause parser, reached through
   `trigger_effect_for`'s ordinary `parse_mixed_effect` fallback rather than a
   `TRIGGER_EFFECTS` row keyed to Chalice's own name - a name row cannot
   generalise to a future card printing the same clause, which is the whole
   point of parsing by shape. "Counter that spell." is **CR 607.1** linked-
   ability anaphora back to the trigger's own event subject, not something
   CR 601.2c ever asked anyone to target, so it is read off
   `ability.event.subject_id` rather than through `Game.resolve_targets` -
   the same shape Vexing Bauble's identical clause needed, so
   `vexing_bauble_counter`'s old hand-written `TRIGGER_EFFECTS` row is gone
   too (`tests/scenarios/test_mana_spent_intervening_if.py`'s Vexing Bauble
   test now runs off this same parser). **CR 701.6a**: "A countered spell is
   put into its owner's graveyard" - by way of `Game.counter`, which also
   honours a rebound or flashback spell's own replaced destination rather
   than always the graveyard.

The trigger fires on *casting* (**CR 601.2a**, **CR 603.2**), and CR 603.3
puts the ability on the stack above the spell that caused it, so the spell is
still there, unresolved, when the ability resolves and counters it - proven
directly by `test_chalice_counters_a_spell_with_exactly_matching_mana_value`
reading `scenario.stack_names()` before resolving anything.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_chalice_counters_a_spell_with_exactly_matching_mana_value():
    """The plain case: Chalice on 1 charge counter, an opponent casts a
    mana-value-1 spell. The ability goes on the stack *above* the spell
    (CR 603.3), and resolving it counters the spell before it ever resolves.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Chalice of the Void"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    chalice = scenario.creature("Chalice of the Void", "alice")
    scenario.game.add_counters(chalice, Counter.CHARGE, 1)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", mountain, username="bob", targets=[scenario.player("alice")]
    )

    assert scenario.stack_names() == ["Lightning Bolt", "Chalice of the Void's triggered ability"]
    scenario.resolve_top()  # Chalice's triggered ability resolves first (CR 608)

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []


def test_chalice_does_not_counter_a_higher_mana_value_spell():
    """Near miss upward: Chalice on 1 must not catch a mana-value-2 spell.
    Grizzly Bears ({1}{G}, mana value 2) resolves onto the battlefield as
    normal, and nothing goes on the stack above it.
    """
    scenario = (
        Scenario()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("alice", battlefield=["Chalice of the Void"])
        .build()
    )
    chalice = scenario.creature("Chalice of the Void", "alice")
    scenario.game.add_counters(chalice, Counter.CHARGE, 1)
    scenario.start_at(Step.PRECOMBAT_MAIN)  # bob is active: sorcery speed for his own spell

    forests = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *forests, username="bob")

    assert scenario.stack_names() == ["Grizzly Bears"]
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD


def test_chalice_does_not_counter_a_lower_mana_value_spell():
    """Near miss downward: Chalice on 1 must not catch a mana-value-0 spell.
    Memnite ({0}, mana value 0) resolves onto the battlefield as normal.
    """
    scenario = (
        Scenario()
        .player("bob", hand=["Memnite"])
        .player("alice", battlefield=["Chalice of the Void"])
        .build()
    )
    chalice = scenario.creature("Chalice of the Void", "alice")
    scenario.game.add_counters(chalice, Counter.CHARGE, 1)
    scenario.start_at(Step.PRECOMBAT_MAIN)  # bob is active: sorcery speed for his own spell

    memnite = scenario.cast_onto_stack("Memnite", username="bob")

    assert scenario.stack_names() == ["Memnite"]
    scenario.resolve_top()

    assert memnite.zone is Zone.BATTLEFIELD


def test_chalice_on_zero_counters_a_zero_mana_value_spell():
    """The other half of the same pair: Chalice with *no* charge counters
    (X=0 as cast, or simply never given any) catches a mana-value-0 spell -
    the exact-match case is not special-cased away just because the number
    happens to be zero.
    """
    scenario = (
        Scenario()
        .player("bob", hand=["Memnite"])
        .player("alice", battlefield=["Chalice of the Void"])
        .build()
    )
    scenario.creature("Chalice of the Void", "alice")  # 0 charge counters, untouched
    scenario.start_at(Step.PRECOMBAT_MAIN)  # bob is active: sorcery speed for his own spell

    memnite = scenario.cast_onto_stack("Memnite", username="bob")

    assert scenario.stack_names() == ["Memnite", "Chalice of the Void's triggered ability"]
    scenario.resolve_top()

    assert memnite.zone is Zone.GRAVEYARD


def test_chalice_counters_an_x_spell_by_its_real_on_stack_mana_value():
    """Walking Ballista's `{X}{X}` cast for X=1 has mana value 2 (CR 107.3i:
    both X's share the one chosen value), not 1 and not its printed cmc of 0.
    Chalice on 2 catches it; this is the case a fix that read
    `subject_card.cmc` (always 0 for this printing) or added `x_value` only
    once (giving 1, not 2) would get wrong in either direction.
    """
    scenario = (
        Scenario()
        .player("bob", hand=["Walking Ballista"], battlefield=["Forest", "Forest"])
        .player("alice", battlefield=["Chalice of the Void"])
        .build()
    )
    chalice = scenario.creature("Chalice of the Void", "alice")
    scenario.game.add_counters(chalice, Counter.CHARGE, 2)
    scenario.start_at(Step.PRECOMBAT_MAIN)  # bob is active: sorcery speed for his own spell

    sources = scenario.untapped_sources("Forest", "Forest", username="bob")
    casting = scenario.cast("Walking Ballista", username="bob")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    ballista = scenario.put_on_stack(casting)

    assert scenario.stack_names() == [
        "Walking Ballista",
        "Chalice of the Void's triggered ability",
    ]
    scenario.resolve_top()

    assert ballista.zone is Zone.GRAVEYARD


def test_chalice_does_not_counter_the_same_x_spell_at_a_non_matching_count():
    """The near miss for the X case: Chalice on 1 does not catch the same
    Walking Ballista cast for X=1 (real mana value 2, not 1) - proof the
    doubling in the test above is not a coincidence that happens to match
    whatever the fix does, but an actual discriminator.
    """
    scenario = (
        Scenario()
        .player("bob", hand=["Walking Ballista"], battlefield=["Forest", "Forest"])
        .player("alice", battlefield=["Chalice of the Void"])
        .build()
    )
    chalice = scenario.creature("Chalice of the Void", "alice")
    scenario.game.add_counters(chalice, Counter.CHARGE, 1)
    scenario.start_at(Step.PRECOMBAT_MAIN)  # bob is active: sorcery speed for his own spell

    sources = scenario.untapped_sources("Forest", "Forest", username="bob")
    casting = scenario.cast("Walking Ballista", username="bob")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    ballista = scenario.put_on_stack(casting)

    assert scenario.stack_names() == ["Walking Ballista"]
    scenario.resolve_top()

    assert ballista.zone is Zone.BATTLEFIELD


def test_chalice_on_zero_counters_an_x_spell_cast_for_x_equals_zero():
    """CR 107.3g/202.3e together mean an `{X}` spell cast for X=0 has real
    mana value 0, on the stack exactly as much as off it - Chalice on 0 must
    catch it precisely because 0 is not a special case either direction.
    """
    scenario = (
        Scenario()
        .player("bob", hand=["Walking Ballista"])
        .player("alice", battlefield=["Chalice of the Void"])
        .build()
    )
    scenario.creature("Chalice of the Void", "alice")  # 0 charge counters
    scenario.start_at(Step.PRECOMBAT_MAIN)  # bob is active: sorcery speed for his own spell

    casting = scenario.cast("Walking Ballista", username="bob")
    casting.determine_cost(x_value=0)
    payment = casting.begin_paying()
    scenario.pay_with(payment)
    ballista = scenario.put_on_stack(casting)

    assert scenario.stack_names() == [
        "Walking Ballista",
        "Chalice of the Void's triggered ability",
    ]
    scenario.resolve_top()

    assert ballista.zone is Zone.GRAVEYARD


def test_chalice_counters_its_own_controllers_spell_too():
    """CR 603.2 gives the trigger no exception for the caster being Chalice's
    own controller - "Whenever a player casts a spell" is any player,
    including this one. A test exercising only an opponent's cast would pass
    while a controller-only bug (`_controller_clause_holds` misapplied, say)
    stayed invisible.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Chalice of the Void", "Mountain"])
        .player("bob")
        .build()
    )
    chalice = scenario.creature("Chalice of the Void", "alice")
    scenario.game.add_counters(chalice, Counter.CHARGE, 1)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", mountain, username="alice", targets=[scenario.player("bob")]
    )

    assert scenario.stack_names() == ["Lightning Bolt", "Chalice of the Void's triggered ability"]
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD


def test_two_chalices_at_different_counts_only_the_matching_one_triggers():
    """Two Chalices, one on 1 and one on 2. A mana-value-1 spell triggers only
    the first - each is judged against its *own* charge-counter count at the
    moment the spell is cast (CR 603.2, 603.4), not some shared or merged
    total. If the second one triggered too, `stack_names()` would have three
    entries instead of two: the spell and one ability each.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Chalice of the Void", "Chalice of the Void"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    low, high = scenario.creatures("Chalice of the Void", "Chalice of the Void", username="alice")
    scenario.game.add_counters(low, Counter.CHARGE, 1)
    scenario.game.add_counters(high, Counter.CHARGE, 2)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", mountain, username="bob", targets=[scenario.player("alice")]
    )

    assert scenario.stack_names() == ["Lightning Bolt", "Chalice of the Void's triggered ability"]
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD


def test_chalice_still_counters_after_its_charge_counters_are_removed_in_response():
    """CR 603.4's intervening condition is checked once, when the spell is
    cast - Chalice's ability carries no intervening *if* (CR 603.4's own
    "if" construction), so CR 608.2a's resolution recheck does not apply to
    it at all. Once the trigger has fired and gone on the stack, removing the
    charge counters that made it fire does not call it back: the ability
    still counters the spell on resolution, judged by the count that held
    when the spell was cast, not the count that holds now.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Chalice of the Void"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    chalice = scenario.creature("Chalice of the Void", "alice")
    scenario.game.add_counters(chalice, Counter.CHARGE, 1)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", mountain, username="bob", targets=[scenario.player("alice")]
    )
    assert scenario.stack_names() == ["Lightning Bolt", "Chalice of the Void's triggered ability"]

    # In response, before the trigger resolves, the charge counter comes off.
    chalice.remove_counters(Counter.CHARGE, 1)
    assert chalice.counters[Counter.CHARGE] == 0

    scenario.resolve_top()  # Chalice's ability, still holding its old target

    assert bolt.zone is Zone.GRAVEYARD
