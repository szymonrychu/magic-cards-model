"""`models/token.py::_put_onto_the_battlefield_attacking` (CR 508.4) reads the
*computed* board, not a token's printed types, to decide whether CR 506.3a's
refusal applies.

CR 506.3a: an effect that puts a noncreature permanent onto the battlefield
already attacking does not make it an attacking creature - "that permanent
does enter the battlefield, but it's never considered to be an attacking
creature." The token is already on the battlefield by the time this check
runs: `game.put_onto_battlefield` has already moved it there, and every
caller of `_put_onto_the_battlefield_attacking` verifies `zone is Zone.
BATTLEFIELD` first (`models/token.py:553`'s own `if token.zone is not Zone.
BATTLEFIELD: ... continue` and `machines/effects.py`'s identical guard before
its own call) - which is exactly what CR 613.5's "computed on the
battlefield, printed everywhere else" guard needs to be safe here.

No printed card creates a noncreature token already attacking that some other
permanent's static ability also turns into a creature, so this file builds
the shape directly with the engine's own real primitives - `create_tokens`
(CR 701.7a) and a hand-built `ContinuousEffect` added through `ContinuousEffects.
add`, documented as the entry point "for a caller that is not going through
the registry" (the same pattern `test_layer_computed_planeswalker.py` uses)
- rather than a fake test double: a plain Artifact token, and an anthem
shaped like "Artifacts you control are creatures in addition to their other
types" would produce.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import (
    ContinuousEffect,
    Layer,
    add_type,
    all_permanents_controlled_by,
)
from magic_cards_model.models.card import Type
from magic_cards_model.models.token import TokenDefinition, create_tokens

from .harness import Scenario


def _anthem_makes_alices_permanents_creatures(scenario) -> None:
    store = scenario.game.continuous_effects
    with scenario.game._id_allocator_scope():  # noqa: SLF001
        store.add(
            ContinuousEffect(
                description="test: alice's permanents are creatures",
                layer=Layer.TYPE,
                timestamp=store.tick(),
                selector=all_permanents_controlled_by("alice"),
                modification=add_type(Type.CREATURE),
            )
        )


def test_a_noncreature_token_the_computed_board_makes_a_creature_can_attack():
    """The positive case: printed says Artifact only, computed says creature
    too, and CR 508.4 has to agree with the computed answer.
    """
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _anthem_makes_alices_permanents_creatures(scenario)

    definition = TokenDefinition(types=(Type.ARTIFACT,), name="Test Clue")
    (token,) = create_tokens(scenario.game, definition, "alice", attacking="bob")

    assert Type.CREATURE not in token.types, "the printed token definition is Artifact only"
    assert scenario.game.characteristics_of(token).is_creature, "the anthem made it one"
    assert scenario.game.is_attacking(token), "CR 508.4: the computed board says creature"


def test_a_noncreature_token_with_no_anthem_never_attacks():
    """The inverse: without anything making it a creature, CR 506.3a's
    refusal still holds exactly as it did before this fix - a plain
    noncreature token put onto the battlefield attacking is never considered
    attacking.
    """
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    definition = TokenDefinition(types=(Type.ARTIFACT,), name="Test Clue")
    (token,) = create_tokens(scenario.game, definition, "alice", attacking="bob")

    assert not scenario.game.characteristics_of(token).is_creature
    assert not scenario.game.is_attacking(token)
