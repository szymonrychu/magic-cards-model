"""Defect 1: two different tokens minting the same `Card.id` poisons the
process-global ability caches.

T1 (`ids.py`) made object ids deterministic: `uuid5` of `game_uid` and the
`objects_created` counter, installed for the span of one `Game` mutating
method via `Game._id_allocator_scope()` (see `tests/test_game_determinism.py`
for the replay-identity guarantee that buys). T8a added process-global memo
caches keyed on `Card.id` - `machines/abilities.py`'s `_ability_cache` and
`machines/triggers.py`'s `_activated_abilities_cache` - on the documented
strength of `Card` being immutable, so "two different printings ... can never
collide" (`machines/abilities.py:1418-1424`).

Synthesized token `Card`s break that strength assumption:
`TokenDefinition.to_card()` (`models/token.py`) mints its `Card.id` with
`ids.new_id()`, which resolves to the *same* deterministic allocator inside a
`Game._id_allocator_scope()`. Two decodes of one snapshot share the same
`game_uid` and the same starting `objects_created` counter, so if each decode
creates its *first* token at the same point in its own call sequence, both
mint the identical `uuid5(game_uid, n)` for their token's `Card` - even though
the two tokens are genuinely different printings (CR 111.3: a token's stated
characteristics are its copiable values, exactly the way a printed card's
text is). The cache then serves the first token's abilities back for the
second token's card, silently.

Real cards, not hand-written token data: Seasoned Pyromancer's `ELEMENTAL`
(1/1 red Elemental, no abilities at all) and Malevolent Rumble/Kozilek's
Command/Drowner of Truth's `ELDRAZI_SPAWN` (0/1 colorless Eldrazi Spawn with
the printed activated ability "Sacrifice this token: Add {C}.") are the two
`TokenDefinition` constants `machines/effects.py` already wires to those
cards - see `tests/scenarios/test_token_effect_parser.py` for the same
constants exercised through real spell resolution.
"""

from magic_cards_model.machines.abilities import ActivatedAbility, parse_abilities
from magic_cards_model.machines.effects import ELDRAZI_SPAWN, ELEMENTAL
from magic_cards_model.machines.triggers import activated_abilities_of
from magic_cards_model.models.game import Game
from magic_cards_model.models.token import create_tokens
from tests.scenarios.harness import Scenario


def test_two_decoded_branches_creating_different_tokens_get_independent_abilities():
    """Reproduces the reviewer's repro and then the consequence it implies but
    does not itself demonstrate: not just "same `Card.id`", but "the second
    token reads the first token's abilities back".
    """
    scenario = Scenario().player("alice", battlefield=["Forest"]).build()
    snapshot = scenario.game.model_dump(mode="json")

    # Two independent decodes of the *same* snapshot - same `game_uid`, same
    # `objects_created` counter - each then takes a *different* first action.
    branch_elemental = Game.model_validate(snapshot)
    branch_spawn = Game.model_validate(snapshot)

    (elemental_token,) = create_tokens(branch_elemental, ELEMENTAL, "alice")
    (spawn_token,) = create_tokens(branch_spawn, ELDRAZI_SPAWN, "alice")

    # They are different printings (CR 111.3: a token's stated characteristics
    # are its copiable values), so a correct engine must mint different ids -
    # the reviewer's repro showed the deterministic per-game allocator minting
    # the *same* id for both, since both branches share `game_uid` and the
    # same starting `objects_created` and each token is the first thing its
    # own branch creates.
    assert elemental_token.card.oracle_text != spawn_token.card.oracle_text
    assert elemental_token.card.id != spawn_token.card.id, (
        "two decoded branches of one snapshot, each creating a different "
        "first token, minted the same Card.id - the T1/T8a collision this "
        "test is named for"
    )

    # Populate the process-global cache with the Elemental's abilities first.
    assert parse_abilities(elemental_token.card) == []

    # The consequence: asking the *same question* about the Eldrazi Spawn's
    # card - a card with a real printed activated ability - must not read
    # back the Elemental's cached (empty) answer.
    spawn_abilities = parse_abilities(spawn_token.card)
    assert spawn_abilities != [], (
        "Eldrazi Spawn Token's 'Sacrifice this token: Add {C}.' ability was "
        "read back as the Elemental Token's empty ability list - the "
        "process-global _ability_cache is keyed on the colliding Card.id"
    )
    assert any(isinstance(ability, ActivatedAbility) for ability in spawn_abilities)

    # Same consequence through the other memo, `activated_abilities_of`.
    spawn_activated = activated_abilities_of(spawn_token.card)
    assert spawn_activated != [], (
        "Eldrazi Spawn Token's activated ability was read back as the "
        "Elemental Token's empty list - _activated_abilities_cache is keyed "
        "on the colliding Card.id too"
    )
