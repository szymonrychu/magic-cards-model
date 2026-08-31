"""Scenario: Goryo's Vengeance - "Return target legendary creature card from
your graveyard to the battlefield. That creature gains haste. Exile it at the
beginning of the next end step."

The same three-clause instruction Postmortem Lunge prints, with two differences
that between them killed the whole card: the target is qualified ("legendary
creature card", not "creature card"), and the haste clause names its antecedent
demonstratively ("That creature gains haste", not "It gains haste"). An ability
resolves whole or fails closed in this engine, so either miss took the
reanimation in sentence one down with it.

The third clause is now built through `machines/delayed.py`'s anaphoric
primitive rather than a bespoke `verb == "exile it"` comparison, which is why
"Exile it" and "Exile that creature" are the same shape here.

Every CR number in this file was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it:

- **CR 603.7a** - delayed triggered abilities are created during the resolution
  of spells or abilities.
- **CR 603.7c** - the delayed ability affects the object even if its
  characteristics changed, but does nothing if that object has left the zone
  the ability expects it in.
- **CR 205.4a** - "The supertypes are basic, legendary, ongoing, snow, and
  world", so "legendary creature card" is a supertype restriction on the
  target, not a subtype or a type.
- **CR 302.6** - a creature that entered this turn is summoning sick, which is
  what the haste grant exists to answer.
- **CR 701.13a** - "To exile an object, move it to the exile zone from wherever
  it is."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _walk_to(scenario, step: Step) -> None:
    """Advance step by step until `step`, resolving whatever fires on the way.

    `start_at` moves the turn machine without emitting a "step began" event
    (CR 500.6), which is exactly what a delayed trigger waiting for a step
    would never see - so the walk has to be a real one.
    """
    while scenario.step is not step:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def _cast_vengeance(scenario, target):
    casting = scenario.cast("Goryo's Vengeance")
    casting.game = scenario.game
    casting.choose_targets([target])
    casting.determine_cost()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return casting


def test_goryos_vengeance_reanimates_a_legendary_creature_with_haste():
    """The archetype's whole engine, played through: a legendary creature card
    leaves the graveyard, enters with haste, and is exiled at the next end
    step."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Goryo's Vengeance"],
            graveyard=["Isamaru, Hound of Konda"],
            battlefield=["Swamp", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    isamaru = scenario.find("Isamaru, Hound of Konda", Zone.GRAVEYARD, "alice")
    _cast_vengeance(scenario, isamaru)

    assert isamaru.zone is Zone.BATTLEFIELD
    assert "Haste" in scenario.game.characteristics_of(isamaru).abilities
    assert isamaru.summoning_sick, "a reanimated creature is a new object (CR 302.6)"

    _walk_to(scenario, Step.END_STEP)

    assert isamaru.zone is Zone.EXILE, "the delayed trigger exiles it (CR 701.13a)"


def test_goryos_vengeance_is_not_a_notice_any_more():
    """The measurement the deck-gap doc kept: `effect_for` must build a real
    effect rather than record that it could not read the delayed clause."""
    from magic_cards_model.machines.effects import effect_for

    vengeance = card("Goryo's Vengeance")
    effect = effect_for(vengeance.name, vengeance.oracle_text or "")

    assert effect is not None
    assert getattr(effect, "__name__", "") != "delayed_notice_only"


def test_goryos_vengeance_cannot_target_a_nonlegendary_creature_card():
    """CR 205.4a: the supertype is part of the target's restriction, so an
    ordinary creature card in the graveyard is not a legal target."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Goryo's Vengeance"],
            graveyard=["Elvish Mystic"],
            battlefield=["Swamp", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    mystic = scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice")
    casting = scenario.cast("Goryo's Vengeance")
    casting.game = scenario.game

    with pytest.raises(ValueError):
        casting.choose_targets([mystic])


def test_goryos_delayed_exile_does_not_reach_a_creature_that_already_left():
    """CR 603.7c: once the reanimated creature has left the battlefield the
    delayed ability still resolves, and does nothing - it does not dig the
    card back out of the graveyard."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Goryo's Vengeance"],
            graveyard=["Isamaru, Hound of Konda"],
            battlefield=["Swamp", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    isamaru = scenario.find("Isamaru, Hound of Konda", Zone.GRAVEYARD, "alice")
    _cast_vengeance(scenario, isamaru)
    assert isamaru.zone is Zone.BATTLEFIELD

    scenario.game.destroy(isamaru)
    assert isamaru.zone is Zone.GRAVEYARD

    _walk_to(scenario, Step.END_STEP)

    assert isamaru.zone is Zone.GRAVEYARD
