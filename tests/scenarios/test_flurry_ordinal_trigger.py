"""Cori-Steel Cutter's *Flurry*: "Whenever you cast your second spell each
turn, create a 1/1 white Monk creature token with prowess. You may attach
this Equipment to it."

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 207.2c** - an ability word ("Flurry") "ha[s] no special rules meaning"
  of its own; the mechanic is the sentence after it.
- **CR 603.2** - what a printed trigger condition is matched against.
- **CR 603.3** - a triggered ability waits in `pending_triggers` until the
  next time a player would receive priority, then goes on the stack.
- **CR 701.3a** - "to attach ... means to take it from where it currently is
  and put it onto that object" - the general action, not only CR 702.6a's
  own Equip ability.
- **CR 608.2d** - "the player announces these while applying the effect ...
  The player can't choose an option that's illegal or impossible" - the
  "you may attach" half.

`test_tokens.py::test_cori_steel_cutter_makes_a_monk_on_the_second_spell_only`
already covers the plain happy path (one spell makes no Monk, the second
does) alongside the rest of that file's token-creation coverage. This file is
the ordinal-count trigger and the optional-attach effect on their own -
`machines/triggers._ordinal_spell_this_turn_matches` (CAST_SPELL's own
position in `Game.spells_cast_this_turn`, not an intervening *if* - the
ordinal sits in the trigger *condition* itself, checked once, never
rechecked at resolution the way CR 603.4's clause would be) and
`machines/effects._parse_create_token_then_may_attach_clause`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _two_spells_in_hand(*extra: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Cori-Steel Cutter", "Mountain", "Mountain", "Mountain", *extra],
        )
        .player("bob")
    )


def test_the_third_spell_makes_no_second_monk():
    """CR 603.2's condition names an exact ordinal - "your second spell" -
    not "your second spell or later". A third spell in the same turn is
    alice's third, not her second, so Flurry stays quiet a second time."""
    scenario = _two_spells_in_hand().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True)

    first, second, third = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Lightning Bolt", first, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()
    scenario.cast_and_resolve("Lightning Bolt", second, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()
    assert scenario.battlefield_names().count("Monk Token") == 1, "the second spell made one"

    scenario.cast_and_resolve("Lightning Bolt", third, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.battlefield_names().count("Monk Token") == 1, "the third spell makes no more"


def test_a_new_turn_resets_the_count():
    """`Game.spells_cast_this_turn` is cleared at the turn boundary (CR
    500.4's "as a new turn begins", the same reset Alania, Divergent Storm's
    own "first spell ... this turn" clause already depends on) - so a spell
    that would be alice's *third* spell of the game is her *first* spell of
    a fresh turn, and Flurry does not fire off it either."""
    scenario = _two_spells_in_hand().manual_turn_based_actions().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True)

    first, second, third = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Lightning Bolt", first, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()
    scenario.cast_and_resolve("Lightning Bolt", second, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()
    assert scenario.battlefield_names().count("Monk Token") == 1

    scenario.game.begin_turn_for("alice")  # CR 500.4: a fresh spells_cast_this_turn
    scenario.cast_and_resolve("Lightning Bolt", third, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.battlefield_names().count("Monk Token") == 1, "her first spell of a new turn"


def test_declining_the_attach_leaves_the_equipment_free():
    """CR 608.2d: the attach is a "you may", separate from the token's own
    unconditional creation (CR 603.12's "instruct" half has no decision at
    all - the token always appears). Declining leaves Cori-Steel Cutter on
    the battlefield unattached and the Monk unbuffed."""
    scenario = _two_spells_in_hand().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False)

    first, second, _ = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Lightning Bolt", first, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()
    scenario.cast_and_resolve("Lightning Bolt", second, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    monk = scenario.find("Monk Token", Zone.BATTLEFIELD)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD)
    assert cutter.attached_to is None
    characteristics = scenario.game.characteristics_of(monk)
    assert (characteristics.power, characteristics.toughness) == (1, 1)


def test_accepting_the_attach_actually_equips_the_monk():
    """CR 701.3a's attach really moves the Equipment onto the fresh token -
    `CardState.attached_to` points at it, the same fact `equipped_creature`
    (`machines/keywords.py`) reads for an ordinary Equip activation. What
    the attachment then *does* - Cori-Steel Cutter's own "Equipped creature
    gets +1/+1 and has trample and haste" - is a layer 6/7c continuous
    effect nothing generates yet for any Equipment's static bonus text; see
    `tests/scenarios/test_equip.py`'s own module docstring and
    `docs/engine-coverage.md`. This test is the attach half only.
    """
    scenario = _two_spells_in_hand().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True)

    first, second, _ = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Lightning Bolt", first, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()
    scenario.cast_and_resolve("Lightning Bolt", second, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    monk = scenario.find("Monk Token", Zone.BATTLEFIELD)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD)
    assert cutter.attached_to == monk.id
    assert cutter.is_attached


def test_an_illegal_attach_answer_still_leaves_the_monk_created_and_completes_resolution():
    """CR 603.12's token-creation half of Flurry's paragraph is unconditional
    - "instruct", not "you may" - and already complete by the time the
    attach half of the same one ability (CR 113.3) asks its own `MAY`
    question. If that question can't be legally answered - `Game.ask`'s own
    `MAY` branch refusing a non-bool answer - CR 733.1's reversal has nothing
    to reverse: the token is real, the same way `Game.ask`'s docstring
    already treats a shockland forced to "no" as a fact, not an undo.

    What has to hold regardless is CR 608.2n: the ability comes off the stack
    and CR 704.3's state-based actions run before anything else, whether or
    not the effect that put it there finished cleanly. `Game._resolve_ability`
    did not guarantee that before this fix - the same "ceases to exist"
    bookkeeping `Game.resolve_top` already guarantees a resolving spell's own
    final zone placement, just never extended to an ability's own resolution.

    Impact Tremors is the instrument that makes the gap observable rather
    than merely plausible: its own "whenever a creature you control enters"
    trigger (`test_triggered_abilities.py::test_a_card_with_no_registry_row_
    gets_the_each_opponent_damage_shape_too`) fires the instant the Monk
    token enters and is recorded straight into `Game.pending_triggers` (CR
    603.3) - independently of whether Flurry's own resolution later succeeds
    or raises. CR 603.3's "the next time a player would receive priority"
    is `Game._before_priority`'s job, via `put_triggers_on_stack`. Skip that
    call - which is exactly what happened before this fix, on any exception -
    and Impact Tremors' trigger is stuck in `pending_triggers` forever,
    never reaching the stack at all, rather than merely resolving late.
    """
    scenario = _two_spells_in_hand("Impact Tremors").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_life_before = scenario.player("bob").life

    first, second, _ = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Lightning Bolt", first, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    # The second cast puts Flurry's trigger on the stack above the spell
    # (CR 601.2i) - drive it by hand instead of `cast_and_resolve`, whose own
    # single `resolve_top()` call would otherwise be the one that hits the
    # illegal answer.
    scenario.cast_onto_stack("Lightning Bolt", second, targets=["bob"])
    assert "Cori-Steel Cutter" in scenario.stack_names()[-1]
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.MAY,
            value="yes",  # not a bool: Game.ask's own MAY branch refuses this
            player="alice",
            source="Cori-Steel Cutter",
        )
    )

    with pytest.raises(ValueError, match="a yes-or-no question needs a bool answer"):
        scenario.resolve_top()

    # The token is real - CR 603.12's unconditional first clause already
    # completed, and nothing reverses a legally-completed action.
    monk = scenario.find("Monk Token", Zone.BATTLEFIELD)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD)
    # The attach question never got an answer, so the attach itself never
    # happened.
    assert cutter.attached_to is None
    # CR 608.2n: the ability is off the stack either way, and CR 603.3 has
    # already moved Impact Tremors' own trigger from `pending_triggers` onto
    # the stack above the second Lightning Bolt, which never got a chance to
    # resolve.
    assert scenario.pending_triggers == []
    assert scenario.stack_names() == ["Lightning Bolt", "Impact Tremors's triggered ability"]
    scenario.assert_in_exactly_one_zone(*scenario.all_card_states())
    # Draining the rest of the stack still works - the game was not left in
    # a broken state by the refusal, and Impact Tremors' trigger still
    # resolves rather than having been dropped.
    while scenario.game.stack:
        scenario.resolve_top()
    assert monk.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == bob_life_before - 6 - 1, "two Bolts and Impact Tremors"
