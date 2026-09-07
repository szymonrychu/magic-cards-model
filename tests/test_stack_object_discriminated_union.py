"""T3: `StackObject` becomes a discriminated union on `state_class`.

`Game.shared_zones: dict[Zone, list[StackObject]]` (`models/game.py`) is the
only field in the suite typed with the untagged `StackObject = CardState |
AbilityOnStack` union, and it is the sole source of every pydantic serializer
warning the suite emits: pydantic tries a `TokenState` against both untagged
arms, matches neither exactly, and warns once per arm per object every time
`Game.model_dump` reaches `shared_zones`. `Player.zones` (`models/player.py`)
never warns because it is typed plain `CardState`, not the union - `TokenState`
there is not the union's problem to solve, and this file does not touch it
(see `tests/scenarios/test_tokens.py`'s own `Player.zones` round-trip test).

`AbilityOnStack` (`machines/triggers.py`) had no `state_class` discriminator
at all before this task, so a real discriminated union could not dispatch on
it. This file is the union's own regression test: a token sitting in a shared
zone must dump with no pydantic warning at all, and must still decode back as
a `TokenState`, not merely a "warning-free but wrong class" pass.
"""

import warnings

from magic_cards_model.machines import Step
from magic_cards_model.models.game import Game
from magic_cards_model.models.token import TokenDefinition, TokenState, create_tokens
from tests.scenarios.harness import Scenario


def test_a_token_on_the_battlefield_dumps_with_no_serializer_warnings():
    """The 462-warning defect, directly: before this task, dumping a `Game`
    with a `TokenState` in `shared_zones` (here, the battlefield) emits a
    `UserWarning: Pydantic serializer warnings` because `StackObject` is an
    untagged `CardState | AbilityOnStack` union that a `TokenState` matches
    neither arm of exactly."""
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spirit = TokenDefinition(subtypes=("Spirit",), colors=(), power=1, toughness=1)
    create_tokens(scenario.game, spirit, "alice")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        scenario.game.model_dump(mode="json")

    serializer_warnings = [
        item
        for item in caught
        if issubclass(item.category, UserWarning) and "serializer" in str(item.message).lower()
    ]
    assert serializer_warnings == [], (
        f"dumping a token on the battlefield must not warn, got: {serializer_warnings}"
    )


def test_a_token_on_the_battlefield_still_decodes_as_a_tokenstate():
    """The discriminator must not merely silence the warning - the decoded
    object still has to be the real `TokenState`, with CR 111.8's `move_to`
    override intact, not some class the union happened to pick quietly."""
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spirit = TokenDefinition(subtypes=("Spirit",), colors=(), power=1, toughness=1)
    (token,) = create_tokens(scenario.game, spirit, "alice")

    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))
    decoded_token = next(item for item in decoded.battlefield if item.id == token.id)

    assert isinstance(decoded_token, TokenState)
    assert decoded_token.token is True
