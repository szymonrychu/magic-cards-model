"""Number-sweep G12-1: "that many" on a triggered self-counter.

Marauding Mako's "Whenever you discard one or more cards, put that many
+1/+1 counters on this creature." `_COUNTER_ON_SELF_RE` only ever matched a
plain fixed count before this wave - "that many" did not match at all, so
this trigger silently placed nothing no matter how many cards were
discarded.

"That many" is CR 607.1's anaphora back to the ability's own triggering
event, read off `GameEvent.amount` by the number sweep's shared count
channel reader (`machines/effects.that_many`). Proven here against Mind
Rot's real two-card discard rather than a hardcoded one.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 122.1, 122.1a** - counters, and how a +1/+1 counter changes power and
  toughness.
- **CR 607.1** - linked abilities: a resolution clause that refers back to
  what an earlier clause on the same object did or watched.
- **CR 701.9a** - discarding a card.
- **CR 603.2c** - one trigger event, however many cards a single instruction
  discards.
- **CR 603.2g** - "An ability triggers only if its trigger event actually
  occurs."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_abilities
from magic_cards_model.machines.effects import _parse_put_counters_on_self_clause
from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack
from magic_cards_model.models.card_state import Counter
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_marauding_makos_counters_equal_the_real_discard_count():
    """Mind Rot: "Target player discards two cards." - a single CR 701.9a
    instruction discarding two, which `Game.discard_cards` reports as one
    `DISCARDS_A_CARD` event with `amount=2` (CR 603.2c: one event, however
    many cards). Marauding Mako's own "that many" reads that count, not a
    hardcoded one."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mind Rot", "Grizzly Bears", "Grizzly Bears"],
            battlefield=["Marauding Mako", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mako = scenario.creature("Marauding Mako", "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    scenario.cast_and_resolve("Mind Rot", *sources, targets=["alice"])
    assert scenario.stack_names() == ["Marauding Mako's triggered ability"]
    scenario.resolve_top()

    assert mako.counter_count(Counter.PLUS_ONE) == 2
    assert scenario.game.unmodeled_trigger_effect_notices == []
    assert len(scenario.player("alice").hand) == 0


def test_marauding_makos_that_many_fails_closed_with_no_triggering_event():
    """No silent skip, and no guessed "1": an ability whose event carries no
    count records an `UnmodeledTriggerEffectNotice` instead - the same
    fail-closed shape every other notice list in this module already keeps.
    Reached directly (the parser, not a live trigger with no event, which
    this engine has no way to construct): `_parse_put_counters_on_self_
    clause` is what `_COUNTER_ON_SELF_RE`'s "that many" wires up to, and this
    is its own unit-level proof that a missing count fails closed rather than
    silently doing nothing untraced.
    """
    effect = _parse_put_counters_on_self_clause("put that many +1/+1 counters on this creature.")
    assert effect is not None

    scenario = Scenario().player("alice", battlefield=["Marauding Mako"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mako = scenario.creature("Marauding Mako", "alice")
    stand_in_ability = parse_abilities(card("Marauding Mako"))[0]
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=stand_in_ability,
        source_id=mako.id,
        source_name="Marauding Mako",
        controller="alice",
        event=None,
    )

    effect(scenario.game, ability)

    assert mako.counter_count(Counter.PLUS_ONE) == 0
    (notice,) = scenario.game.unmodeled_trigger_effect_notices
    assert notice.source_name == "Marauding Mako"
