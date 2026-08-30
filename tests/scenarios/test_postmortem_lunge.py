"""Scenario: Postmortem Lunge - "({B/P} can be paid with either {B} or 2
life.) Return target creature card with mana value X from your graveyard to
the battlefield. It gains haste. Exile it at the beginning of the next end
step."

Three clauses read as one CR 608.2c instruction: a reanimation whose target
comparison is CR 107.3a's ordinary X (this card's mana cost is `{X}{B/P}`, so
`effect_for`'s own X substitution applies), an indefinite haste grant scoped
to the one incarnation that just entered (CR 611.2a: no duration stated,
lasts indefinitely - it just does not live long, since the third clause
exiles it), and a delayed triggered ability (CR 603.7) built fresh rather
than looked up in a name-keyed table.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 107.4f** - Phyrexian mana: "{B/P} can be paid with either B or 2 life."
- **CR 107.3a** - X is announced once, before targets, and fixed for the
  whole spell.
- **CR 603.7** - a delayed triggered ability, created during resolution.
- **CR 603.7c** - it still affects a referenced object even if its
  characteristics change, but not if the object has left the expected zone.
- **CR 701.13a** - "To exile an object, move it to the exile zone from
  wherever it is."
- **CR 702.10e** (haste) - not needed as a numbered citation here; haste is
  granted through the generic layer-6 ability-grant machinery already used
  elsewhere in this file's engine, not reimplemented for this card.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_main(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


def _walk_to(scenario, step: Step) -> None:
    """Advance turn-by-turn - never jump - until `step`, resolving anything
    that fires along the way. `start_at` moves the turn machine directly and
    fires no "a step began" event (CR 500.6), which is what a delayed trigger
    waiting for a step needs - the same helper `test_delayed_trigger_clause_
    parsing.py` uses for Phelia's own delayed return.
    """
    while scenario.step is not step:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def test_postmortem_lunge_reanimates_with_haste_then_exiles_at_end_step():
    """The whole three-clause instruction, worked all the way through: a
    mana value 1 creature comes back, can attack the turn it returns (haste),
    and is exiled again once the end step arrives.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Postmortem Lunge"],
            graveyard=["Elvish Mystic"],
            battlefield=["Swamp"],
        )
        .build()
    )
    _to_main(scenario)

    casting = scenario.cast("Postmortem Lunge")
    casting.game = scenario.game
    mystic = scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice")
    casting.choose_modes([], x_value=1)
    casting.choose_targets([mystic])
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert mystic.zone is Zone.BATTLEFIELD
    assert "Haste" in scenario.game.characteristics_of(mystic).abilities
    assert mystic.summoning_sick, "a freshly reanimated creature is a new object (CR 302.6)"

    _walk_to(scenario, Step.END_STEP)

    assert mystic.zone is Zone.EXILE, "the delayed trigger exiles it at the next end step"


def test_postmortem_lunge_can_pay_the_phyrexian_symbol_with_life():
    """CR 107.4f: {B/P} may be paid with 2 life instead of black mana."""
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Postmortem Lunge"],
            graveyard=["Elvish Mystic"],
            battlefield=["Forest"],
        )
        .build()
    )
    _to_main(scenario)

    casting = scenario.cast("Postmortem Lunge")
    casting.game = scenario.game
    mystic = scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice")
    casting.choose_modes([], x_value=1)
    casting.choose_targets([mystic])
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    # The Forest pays the {1} generic; no black source at all, so the {B/P}
    # can only be paid with 2 life (CR 107.4f).
    scenario.pay_with(payment, *scenario.untapped_sources("Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("alice").life == 18
    assert mystic.zone is Zone.BATTLEFIELD


def test_postmortem_lunge_cannot_target_a_creature_of_the_wrong_mana_value():
    """The target names mana value X specifically - a mana value 3 creature
    is not a legal target when X is announced as 1.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Postmortem Lunge"],
            graveyard=["Wood Elves"],
            battlefield=["Swamp"],
        )
        .build()
    )
    _to_main(scenario)

    casting = scenario.cast("Postmortem Lunge")
    casting.game = scenario.game
    elves = scenario.find("Wood Elves", Zone.GRAVEYARD, "alice")
    casting.choose_modes([], x_value=1)

    with pytest.raises(ValueError):
        casting.choose_targets([elves])


def test_postmortem_lunges_exile_does_not_reach_a_creature_that_left_early():
    """CR 603.7c: if the reanimated creature is destroyed before the delayed
    trigger fires, the trigger resolves and affects nothing - it does not
    reach into whatever *other* zone the creature ended up in.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Postmortem Lunge"],
            graveyard=["Elvish Mystic"],
            battlefield=["Swamp"],
        )
        .build()
    )
    _to_main(scenario)

    casting = scenario.cast("Postmortem Lunge")
    casting.game = scenario.game
    mystic = scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice")
    casting.choose_modes([], x_value=1)
    casting.choose_targets([mystic])
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert mystic.zone is Zone.BATTLEFIELD

    scenario.game.destroy(mystic)
    assert mystic.zone is Zone.GRAVEYARD

    _walk_to(scenario, Step.END_STEP)

    assert mystic.zone is Zone.GRAVEYARD, "already gone; the delayed exile has nothing to affect"
