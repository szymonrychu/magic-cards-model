"""Persist (CR 702.79a) granted rather than printed, two shapes:

- **Temporary, targeted**: Rhys, the Evermore's own "When Rhys enters,
  another target creature you control gains persist until end of turn." -
  `machines/effects._TARGET_GAINS_KEYWORDS_RE`'s own pre-existing "target
  `<phrase>` gains `<keyword(s)>` until end of turn" shape, which already
  read every other keyword in `_KNOWN_KEYWORDS` before this task - what was
  missing was persist itself in that whitelist
  (`machines/layers._GRANTABLE_TRIGGERED_KEYWORDS`, widened by this task to
  `{"prowess", "persist"}`).
- **Static, group**: Eirdu, Carrier of Dawn // Isilu, Carrier of Twilight's
  back face, "Each other nontoken creature you control has persist." - a new
  reader, `machines/layers._EACH_INDEFINITE_KEYWORD_GRANT_RE`, the singular-
  noun ("each ... creature ... has") twin of the pre-existing plural
  `_INDEFINITE_KEYWORD_GRANT_RE` ("creatures you control have"), reusing its
  identical `_indefinite_keyword_grant_builder` rather than a second copy of
  the selector logic.

Either shape only actually *works* once granted, rather than raising, thanks
to `machines/keywords.persist_return`'s own `keyword_confirmed` parameter:
`has_persist(card.card)` reads only a card's own **printed** Scryfall
keywords, never a layer 6 grant computed on the board, so a granted-persist
creature dying used to hit persist_return's "has no persist ability" guard
the instant its own trigger resolved. `_persist_effect` now passes
`keyword_confirmed=True` - it already knows, from dispatch, that the
resolving ability *is* a persist ability, printed or granted.

Antler Skulkin (Modern-legal, off pool) - "{2}: Target white creature gains
persist until end of turn." - proves the temporary-grant widening on a
second printing: the identical `_TARGET_GAINS_KEYWORDS_RE`/`_GRANTABLE_
TRIGGERED_KEYWORDS` path, from an activated ability rather than an ETB
trigger.

No second Modern/Pioneer/Standard-legal printing carries Eirdu's own exact
singular "each other `<qualifier>` creature you control has `<bare
keyword>`" template (a Scryfall full-text search for several common bare
keywords in that exact shape came back empty - dated MEMORY.md line records
the search); every real printing sharing this general *shape* pairs it with
a qualified keyword such as "hexproof from each of its colors" (Tam,
Mindful First-Year), which is a different, already-existing grant shape
`_EACH_INDEFINITE_KEYWORD_GRANT_RE` does not touch. The builder this reader
calls (`_indefinite_keyword_grant_builder`) is the identical, already-proven
one the plural shape uses elsewhere in the suite, so this file's own
Eirdu-specific scenarios (a second creature getting persist, Eirdu itself
not getting it, the grant ending when Eirdu transforms back) are what prove
the new regex reaches that shared builder correctly.

Eirdu's own **front** face also grants a keyword this task closes off:
"Creature spells you cast have convoke." (CR 702.51a). `machines/spell_
grants.py`'s own module docstring says outright that convoke is "not a
grant it reads at all" - a deliberate exclusion, since nothing there
*executes* a granted convoke - so `machines/objects_as_costs.has_convoke_now`
is a new function reading the identical "`<quality>` spells you cast have
`<keyword>`" shape read-only (no change to `spell_grants.SPELL_GRANT_
KEYWORDS` or any function in that module), consulted by `objects_as_costs.
convoke` in place of the printed-only `has_convoke`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_rhys_grants_persist_to_another_target_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grizzly Bears", "Plains", "Plains"],
            hand=["Rhys, the Evermore"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    # CR 603.3d: a triggered ability's own targets are chosen as it goes on
    # the stack, after the spell that caused it has already resolved - Rhys
    # itself takes no targets at all (its ETB trigger does), so this is
    # registered ahead of time the same way `test_activated_ability_effects.
    # py`'s own reflexive-trigger target already is.
    scenario.choose_trigger_targets("Rhys, the Evermore", [bears])
    scenario.cast_and_resolve("Rhys, the Evermore", auto=True, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    rhys = scenario.creature("Rhys, the Evermore", "alice")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counter_count(Counter.MINUS_ONE) == 1

    # Rhys itself was never the target, so it keeps no persist of its own.
    scenario.game.destroy(rhys)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert rhys.zone is Zone.GRAVEYARD


def test_rhys_activated_ability_removes_every_counter_from_target_creature():
    """CR 122.5's "any number" - CR 608.2d would let the controller choose
    fewer, but no `DecisionKind` exists yet for that open-ended amount, so
    (the same scoped simplification `machines/effects._parse_remove_up_to_n_
    counters_from_target_clause` already records for its own sibling) this
    always takes the maximum: every counter of every kind comes off."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Rhys, the Evermore", "Grizzly Bears", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rhys = scenario.creature("Rhys, the Evermore")
    bears = scenario.creature("Grizzly Bears")
    bears.add_counters(Counter.MINUS_ONE, 1)
    bears.add_counters(Counter.PLUS_ONE, 2)
    (plains,) = scenario.untapped_sources("Plains")

    scenario.activate(rhys, plains, targets=[bears])
    scenario.resolve_top()

    assert bears.counter_count(Counter.MINUS_ONE) == 0
    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_eirdu_transformed_into_isilu_grants_persist_to_other_creatures():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Eirdu, Carrier of Dawn // Isilu, Carrier of Twilight", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    eirdu = scenario.creature("Eirdu, Carrier of Dawn")
    bears = scenario.creature("Grizzly Bears")
    eirdu.transform()
    assert eirdu.transformed

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counter_count(Counter.MINUS_ONE) == 1


def test_isilu_does_not_grant_persist_to_herself():
    """ "Each *other* nontoken creature" - CR 400.7b's own group grant never
    includes the source."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Eirdu, Carrier of Dawn // Isilu, Carrier of Twilight"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    eirdu = scenario.creature("Eirdu, Carrier of Dawn")
    eirdu.transform()

    scenario.game.destroy(eirdu)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert eirdu.zone is Zone.GRAVEYARD


def test_eirdu_front_face_grants_no_persist_at_all():
    """Convoke, not persist, is Eirdu's own front-face static - the grant
    only exists on Isilu's back face."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Eirdu, Carrier of Dawn // Isilu, Carrier of Twilight", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")

    scenario.game.destroy(bears)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert bears.zone is Zone.GRAVEYARD


def test_antler_skulkin_off_pool_proves_the_temporary_grant_is_not_rhys_specific():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Antler Skulkin", "Serra Angel", "Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skulkin = scenario.creature("Antler Skulkin")
    angel = scenario.creature("Serra Angel")
    sources = scenario.untapped_sources("Plains", "Plains")

    scenario.activate(skulkin, *sources, targets=[angel])
    scenario.resolve_top()

    scenario.game.destroy(angel)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert angel.zone is Zone.BATTLEFIELD
    assert angel.counter_count(Counter.MINUS_ONE) == 1


def test_eirdu_front_face_grants_convoke_to_creature_spells():
    """CR 702.51a/CR 702.51b: a creature Eirdu's controller taps pays for one
    symbol of the total cost of a creature spell they cast, exactly as if
    the spell itself printed convoke."""
    from magic_cards_model.machines.objects_as_costs import convoke
    from magic_cards_model.models.card import Color

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Eirdu, Carrier of Dawn // Isilu, Carrier of Twilight",
                "Grizzly Bears",
                "Forest",
            ],
            hand=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    eirdu = scenario.creature("Eirdu, Carrier of Dawn")
    assert not eirdu.transformed
    tapper = scenario.creature("Grizzly Bears")
    (forest,) = scenario.untapped_sources("Forest")

    casting = scenario.cast("Grizzly Bears", username="alice")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, tapper, Color.GREEN)
    scenario.pay_with(payment, forest)
    scenario.put_on_stack(casting)

    assert tapper.tapped, "CR 702.51a: the tapped creature paid for a symbol"
    assert eirdu.tapped is False


def test_a_spell_with_no_convoke_grant_cannot_convoke():
    from magic_cards_model.machines.objects_as_costs import convoke

    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"], hand=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tapper = scenario.creature("Grizzly Bears")
    casting = scenario.cast("Grizzly Bears", username="alice")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="does not have convoke"):
        convoke(payment, casting.spell, tapper)
