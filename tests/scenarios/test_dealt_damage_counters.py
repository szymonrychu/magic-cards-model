""" "Whenever <this> is dealt damage, put that many +1/+1 counters on it."
(CR 120.3e's marked damage, CR 607.1's "that many" anaphora onto the very
event that triggered the ability).

Venus, Torn Between Worlds prints this with the object-position self-pronoun
"her" (CR 201.5c, a legendary permanent's own convention), rewritten to the
impersonal "it" by `machines/abilities.legendary_self_pronoun_normalized`
before `machines/counter_payoffs._put_that_many_counters_on_it` ever sees it.
Hungering Hydra is the off-pool generality proof: a non-legendary printing of
the identical template that spells the self-reference as the bare word "it"
directly, with no pronoun to normalise at all - proving the reader itself,
not the normalisation Venus happens to need on top of it.

The corner case is the reminder text both cards print almost word for word:
"It/She must survive the damage to get the counters." CR 400.7/603.10a mean
a lethal hit destroys the creature (CR 704.5g) before the triggered ability -
already queued off the very same event - ever resolves, so the ability finds
nothing left to put counters on.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 120.3e** - damage dealt to a creature by a source with neither wither
  nor infect causes that much damage to be marked on that creature.
- **CR 607.1** - a resolution clause's "that many"/"that much" refers back to
  a count an earlier part of the same ability established.
- **CR 603.2, 603.3** - a triggered ability's condition is checked at the
  event, and the ability itself waits for the next time a player would
  receive priority before going on the stack - after state-based actions
  (CR 704.3) have already run.
- **CR 704.5g** - a creature with damage marked on it at least equal to its
  toughness is destroyed as a state-based action.
- **CR 400.7** - an object that changes zones is a new object with no memory
  of its previous existence - so a triggered ability's own record of "what
  it triggered on" no longer finds that object in the zone it expects it.

Venus's *second* ability - "Whenever a creature you control with a counter
on it deals combat damage to a player, you may pay {U}. If you do, draw a
card." - belongs in this file too: it is the same card's own counter-gated
trigger, just on the *giving* side of damage rather than the receiving side
above. `machines/triggers.condition_matches`'s `DEALS_DAMAGE` branch read the
"a creature you control" subject clause but had no reader at all for the
trailing "with a counter on it" qualifier (CR 122.1's counter-presence
question), so the ability fired for any attacker regardless of whether it
carried a counter. `_SUBJECT_HAS_COUNTER_RE` is that reader, general enough to
also read a *named* counter kind ("with a +1/+1 counter on it") and not only
the bare "a counter" Venus prints, though nothing in the pool proves the
named-kind half of it yet.

Yathan Tombguard is the off-pool generality proof: a different card, a
different (unconditional, no "may pay") consequence, and a board where the
creature carrying the ability (Yathan) is never the one dealing the damage,
which is what actually proves this reads a general subject clause rather
than a self-reference - Venus's own tests above happen to have her both
carry the ability and deal the damage herself.

- **CR 122.1** - a counter's own open set of kinds, looked up again for this
  addition in the same session.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_venus_gets_a_counter_for_each_point_of_damage_dealt_to_her():
    scenario = (
        Scenario().player("alice", battlefield=["Venus, Torn Between Worlds"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    venus = scenario.creature("Venus, Torn Between Worlds", "alice")
    assert scenario.game.power_of(venus) == 5

    scenario.game.deal_damage(venus, 3, source=None)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Venus, Torn Between Worlds's triggered ability"]
    scenario.resolve_top()

    assert venus.zone is Zone.BATTLEFIELD
    assert venus.counter_count(Counter.PLUS_ONE) == 3
    assert scenario.game.power_of(venus) == 8
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_venus_does_not_survive_lethal_damage_and_gets_no_counters():
    """CR 704.5g destroys her before the triggered ability - already queued
    off the very same damage event - ever gets to resolve (CR 603.3)."""
    scenario = (
        Scenario().player("alice", battlefield=["Venus, Torn Between Worlds"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    venus = scenario.creature("Venus, Torn Between Worlds", "alice")

    scenario.game.deal_damage(venus, 5, source=None)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()

    assert venus.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Venus, Torn Between Worlds's triggered ability"]
    scenario.resolve_top()

    assert venus.counter_count(Counter.PLUS_ONE) == 0
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_hungering_hydra_off_pool_proof_reads_the_bare_word_it_directly():
    """Hungering Hydra's own printed template never needs the legendary
    pronoun rewrite at all - "Whenever this creature is dealt damage, put
    that many +1/+1 counters on it." already says "it" - so this proves
    `machines/counter_payoffs._put_that_many_counters_on_it` on its own,
    independent of Venus's own pronoun normalisation.

    Staged directly at 2 +1/+1 counters (as CR 614.1c's own "enters with X
    +1/+1 counters on it" would have left it for X=2) rather than cast for a
    real X, since that static ability is proven working on its own already
    (`scripts/sweep_pool.py --card "Hungering Hydra"`) and is not this file's
    own mechanic.
    """
    scenario = Scenario().player("alice", battlefield=["Hungering Hydra"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.creature("Hungering Hydra", "alice")
    scenario.game.add_counters(hydra, Counter.PLUS_ONE, 2)
    assert scenario.game.power_of(hydra) == 2

    scenario.game.deal_damage(hydra, 1, source=None)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Hungering Hydra's triggered ability"]
    scenario.resolve_top()

    assert hydra.counter_count(Counter.PLUS_ONE) == 3
    assert scenario.game.power_of(hydra) == 3


def test_hungering_hydra_off_pool_proof_dies_before_counters_land():
    scenario = Scenario().player("alice", battlefield=["Hungering Hydra"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.creature("Hungering Hydra", "alice")
    scenario.game.add_counters(hydra, Counter.PLUS_ONE, 1)
    assert scenario.game.power_of(hydra) == 1

    scenario.game.deal_damage(hydra, 5, source=None)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()

    assert hydra.zone is Zone.GRAVEYARD
    scenario.resolve_top()

    assert hydra.counter_count(Counter.PLUS_ONE) == 0


def test_venus_second_ability_does_not_fire_for_a_creature_with_no_counter():
    """Venus, Torn Between Worlds' own second ability: "Whenever a creature
    you control with a counter on it deals combat damage to a player, you may
    pay {U}. If you do, draw a card." A creature with no counter on it dealing
    combat damage to a player must not trigger this ability at all (CR
    122.1's counter-presence qualifier on the trigger's own subject)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Venus, Torn Between Worlds", "Island"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    venus = scenario.creature("Venus, Torn Between Worlds", "alice")
    assert venus.counter_count(Counter.PLUS_ONE) == 0

    scenario.game._dealing_combat_damage = True
    try:
        scenario.game.deal_damage(scenario.player("bob"), 5, source=venus)
    finally:
        scenario.game._dealing_combat_damage = False
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_venus_second_ability_fires_once_she_carries_a_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Venus, Torn Between Worlds", "Island"],
            library=["Mountain"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    venus = scenario.creature("Venus, Torn Between Worlds", "alice")
    scenario.game.add_counters(venus, Counter.PLUS_ONE, 1)
    scenario.will_pay_the_mana_cost(True, source="Venus, Torn Between Worlds")
    hand_before = len(scenario.player("alice").hand)

    scenario.game._dealing_combat_damage = True
    try:
        scenario.game.deal_damage(scenario.player("bob"), 5, source=venus)
    finally:
        scenario.game._dealing_combat_damage = False
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Venus, Torn Between Worlds's triggered ability"]
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == hand_before + 1
    assert scenario.game.unmodeled_trigger_effect_notices == []


def test_yathan_tombguard_off_pool_proof_reads_a_non_self_referential_subject():
    """Off-pool generality proof: Yathan Tombguard's own "Whenever a creature
    you control with a counter on it deals combat damage to a player, you draw
    a card and you lose 1 life." - a different card, a different (unconditional)
    consequence, and a board where the creature carrying the ability is never
    the one dealing the damage, which is what actually proves the reader
    reads a general subject clause rather than a self-reference on the source
    of the event."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Yathan Tombguard", "Memnite"],
            library=["Mountain"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "alice")
    hand_before = len(scenario.player("alice").hand)
    life_before = scenario.player("alice").life

    scenario.game._dealing_combat_damage = True
    try:
        scenario.game.deal_damage(scenario.player("bob"), 1, source=memnite)
    finally:
        scenario.game._dealing_combat_damage = False
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [], "Memnite carries no counter yet"

    scenario.game.add_counters(memnite, Counter.PLUS_ONE, 1)
    scenario.game._dealing_combat_damage = True
    try:
        scenario.game.deal_damage(scenario.player("bob"), 1, source=memnite)
    finally:
        scenario.game._dealing_combat_damage = False
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Yathan Tombguard's triggered ability"]
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == hand_before + 1
    assert scenario.player("alice").life == life_before - 1
    assert scenario.game.unmodeled_trigger_effect_notices == []
