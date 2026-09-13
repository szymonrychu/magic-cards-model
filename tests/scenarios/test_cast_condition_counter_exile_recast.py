"""Transcendent Dragon's own ETB trigger: "When this creature enters, if you
cast it, counter target spell. If that spell is countered this way, exile it
instead of putting it into its owner's graveyard, then you may cast it
without paying its mana cost." - two things this file exercises together:

- The intervening *if* "you cast it" (CR 603.4/608.2a), read by
  `machines/triggers.intervening_if_holds` off `Game.cast_record`, the same
  primitive Wistfulness's "if [mana] was spent to cast it" already reads -
  see that clause's own coverage in `test_cast_triggers.py` for the mana-spent
  half of the same primitive.
- `_parse_counter_exile_then_cast_free_clauses` in `machines/effects.py`: the
  ability-side counterpart of Force of Negation's own counter-then-exile pair
  (`test_counterspells.py` covers that spell-side shape), extended with the
  "you may cast it without paying its mana cost" permission Force of
  Negation does not print at all.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 603.4** - "When the trigger event occurs, the ability checks whether
  the stated condition is true. The ability triggers only if it's true."
- **CR 608.2a** - the intervening *if* is checked again as the ability
  resolves.
- **CR 601.2 / CR 701.5a** - "to cast a spell is to take it from the zone
  it's in ... put it on the stack, and pay its costs" - the defined action
  "if you cast it" asks about, as opposed to any other way a permanent
  reaches the battlefield.
- **CR 701.6a** - to counter a spell moves it to its owner's graveyard by
  default; Transcendent Dragon's own second sentence overrides that
  destination.
- **CR 608.2g** - "then you may cast it without paying its mana cost" is
  carried out while the trigger resolves, through `Game.
  may_cast_during_resolution`, not held as a permission.
- **CR 118.9** - "without paying its mana cost" is CR 107.3b's alternative
  cost of nothing.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_casting_the_dragon_counters_and_exiles_the_target_spell():
    """The ordinary path: cast for real, condition holds, the target spell is
    countered and moved to exile rather than its owner's graveyard."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Transcendent Dragon"],
            battlefield=["Island"] * 6,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])

    islands = scenario.untapped_sources(*["Island"] * 6)
    scenario.pass_priority("bob")
    scenario.choose_trigger_targets("Transcendent Dragon", [bolt])
    scenario.will_take_the_may(False, source="Transcendent Dragon")
    dragon = scenario.cast_and_resolve("Transcendent Dragon", *islands)
    scenario.pass_until_resolved()

    assert dragon.zone is Zone.BATTLEFIELD
    assert bolt.zone is Zone.EXILE
    assert bolt not in scenario.game.stack


def test_the_exiled_spell_may_be_cast_again_for_free_by_the_dragons_controller():
    """The cast half: "you may cast it" is Transcendent Dragon's own
    controller (alice), not bolt's owner (bob) - CR 108.3 keeps ownership and
    control separate - and it is cast while the trigger resolves (CR 608.2g),
    not held as a permission for later."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Transcendent Dragon"],
            battlefield=["Island"] * 6,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])

    islands = scenario.untapped_sources(*["Island"] * 6)
    scenario.pass_priority("bob")
    scenario.choose_trigger_targets("Transcendent Dragon", [bolt])
    scenario.will_take_the_may(True, source="Transcendent Dragon")
    scenario.will_choose_targets("bob", source="Lightning Bolt")
    scenario.cast_and_resolve("Transcendent Dragon", *islands)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # the enters trigger: counter, exile, cast it

    assert bolt.zone is Zone.STACK
    assert scenario.game.controller_of(bolt).username == "alice"
    assert scenario.game.play_permissions == []
    scenario.resolve_top()
    assert scenario.player("bob").life == 17


def test_reanimating_the_dragon_never_triggers_the_counter_at_all():
    """CR 601.2's cast is a defined action: putting the dragon onto the
    battlefield some other way (here, straight from hand as a stand-in for a
    reanimation effect this pool has no dedicated spell for) means there was
    never a `CastRecord` for it, so "if you cast it" reads false and the
    ability does not trigger - no counter, no target asked, nothing exiled."""
    scenario = (
        Scenario()
        .player("alice", hand=["Transcendent Dragon"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])

    dragon = scenario.put_onto_battlefield("Transcendent Dragon", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Lightning Bolt"]
    assert dragon.zone is Zone.BATTLEFIELD
    assert bolt in scenario.game.stack
