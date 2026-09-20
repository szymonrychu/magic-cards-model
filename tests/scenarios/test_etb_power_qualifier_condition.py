"""Scenario: an ENTERS_THE_BATTLEFIELD condition's own "with power N or
greater" qualifier (CR 208.1).

Garruk, Curse Breaker: "Whenever a creature you control with power 4 or
greater enters, draw a card." Before this fix,
`machines/triggers.condition_matches`'s ENTERS_THE_BATTLEFIELD branch read a
condition's controller clause, card type, and subtype (CR 205.3i) but never
its power/toughness qualifier - Garruk's own "with power 4 or greater" was
silently dropped, so the trigger fired for *any* creature entering, a 1/1
included.

The fix reuses `machines/triggers._power_or_toughness_qualifier_holds` -
already wired into the `BLOCKS` branch for Tetsuko Umezawa, Pursuer's own
"with power or toughness 1 or less blocks" - in the `ENTERS_THE_BATTLEFIELD`
and `DIES` branches too: nothing about the qualifier's grammar is specific to
blocking, and CR 208.1's power/toughness comparison means the same thing
wherever a trigger condition names it.

Kronch Wrangler - not in this fix's own design pool - proves it generalises:
"Whenever a creature you control with power 4 or greater enters, put a
+1/+1 counter on this creature." reads the identical qualifier on a
creature source rather than a planeswalker.

Card text verified with `resolve_cards`. CR numbers looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 603.6a** - enters-the-battlefield abilities trigger when a permanent
  enters the battlefield.
- **CR 208.1** - a creature's power is printed in the lower right corner of
  its rules text box.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_garruk_draws_when_a_power_4_creature_enters():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bayou Groff"],
            library=["Opt"],
            battlefield=["Garruk, Curse Breaker"],
        )
        .player("bob")
        .build()
    )

    scenario.put_onto_battlefield("Bayou Groff")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Garruk, Curse Breaker's triggered ability"]


def test_garruk_does_not_draw_for_a_weaker_creature():
    """Grizzly Bears is a 2/2 - short of Garruk's own "power 4 or greater"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            library=["Opt"],
            battlefield=["Garruk, Curse Breaker"],
        )
        .player("bob")
        .build()
    )

    scenario.put_onto_battlefield("Grizzly Bears")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_kronch_wrangler_off_set_proof_power_4_creature_entering():
    """The off-set proof: a creature source, not a planeswalker, reading the
    identical qualifier."""
    scenario = (
        Scenario()
        .player("alice", hand=["Bayou Groff"], battlefield=["Kronch Wrangler"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wrangler = scenario.creature("Kronch Wrangler", "alice")

    scenario.put_onto_battlefield("Bayou Groff")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert wrangler.counters["+1/+1"] == 1


def test_kronch_wrangler_off_set_proof_does_not_fire_for_a_weaker_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Kronch Wrangler"])
        .player("bob")
        .build()
    )
    wrangler = scenario.creature("Kronch Wrangler", "alice")

    scenario.put_onto_battlefield("Grizzly Bears")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert wrangler.counters["+1/+1"] == 0
