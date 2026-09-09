"""`CardState.is_planeswalker` reads the *computed* board on the battlefield,
not the printed type line (CR 613.5, CR 613.1d) - the same shape
`CardState.is_saga` already uses (`is_saga`'s own docstring, `models/
card_state.py:2049`).

No real, already-implemented card in this pool grants or strips the
planeswalker type through a generic text parser - `machines/layers.py`'s
`_BECOMES_TYPE_IN_ADDITION_RE` (Liquimetal Coating's "Target permanent becomes
an artifact in addition to its other types until end of turn.") *can* name
"planeswalker" as the extra type (`_OTHER_PERMANENT_TYPE_WORDS` lists it
alongside artifact/enchantment/land/battle), but no printed card in Magic
targets that exact shape at the planeswalker type, so there is no real card
to add to the pool for it.

This file exercises the same real production machinery that shape's builder
would call - `add_type`, `Layer.TYPE`, `only_this_incarnation`, all from
`machines/layers.py` - through `ContinuousEffects.add`, which is documented
as the entry point "for a caller that is not going through the registry".
That is exactly this file's situation: a real Scryfall permanent (Grizzly
Bears) with a hand-built continuous effect, the same pattern `tests/
test_layers.py` already uses throughout to exercise the layer engine without
needing a specific card's text parsed. Nothing here is a mock - `Grizzly
Bears` is a real printing and `ContinuousEffect`/`add_type` are the engine's
own production types, not stand-ins for them.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import (
    ContinuousEffect,
    Layer,
    add_type,
    only_this_incarnation,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type

from .harness import Scenario


def test_is_planeswalker_is_false_for_an_ordinary_creature_on_the_battlefield():
    """The inverse this file's positive case needs: a permanent nothing has
    touched must not read as a planeswalker either way."""
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    assert bears.is_planeswalker is False


def test_is_planeswalker_reads_the_computed_board_on_the_battlefield():
    """CR 613.1d puts a type-changing effect in layer 4, and CR 613.5 says the
    layer system's answer is applied "continually and automatically" - so
    once a layer-4 effect has added the planeswalker type, `is_planeswalker`
    must say so even though Grizzly Bears' own printed type line never
    changes.
    """
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert Type.PLANESWALKER not in bears.types, "the printed type line is just Creature"

    store = scenario.game.continuous_effects
    # `ContinuousEffect.id` is minted by `new_id()`, which is only
    # deterministic - and so only replay-safe - inside the game's own
    # `_id_allocator_scope()` (see `tests/test_state_based_actions.py`'s
    # identical need for a hand-built call with no allocator scope of its
    # own to open).
    with scenario.game._id_allocator_scope():  # noqa: SLF001
        store.add(
            ContinuousEffect(
                description="test: Grizzly Bears becomes a planeswalker",
                layer=Layer.TYPE,
                timestamp=store.tick(),
                selector=only_this_incarnation(bears, bears.zone_change_stamp),
                modification=add_type(Type.PLANESWALKER),
            )
        )

    computed = scenario.game.characteristics_of(bears)
    assert Type.PLANESWALKER in computed.types, "the layer-4 effect landed on the computed board"
    assert bears.is_planeswalker is True, "CR 613.5: the computed answer, not the printed one"
    assert Type.PLANESWALKER not in bears.types, "the printed type line never changes underneath it"


def test_is_planeswalker_reads_the_printing_off_the_battlefield():
    """No `game` reaches a card in hand (CR 613.5's layer system applies to
    permanents on the battlefield only), so the printed answer is the only
    one there is - and for an ordinary creature, that answer is False.
    """
    scenario = Scenario().player("alice", hand=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND)

    assert bears.is_planeswalker is False
