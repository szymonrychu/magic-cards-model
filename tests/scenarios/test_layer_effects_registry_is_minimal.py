"""Guard: nothing in `LAYER_EFFECTS` should be reachable through
`parsed_layer_effects`, the parser fallback `effects_for` (`machines/layers.py`)
uses on a registry miss.

`LAYER_EFFECTS` keeps a card only when no parser reads its shape - the same
principle `tests/scenarios/test_registry_is_minimal.py` already enforces for
`machines/effects.py`'s `EFFECTS`/`TRIGGER_EFFECTS`/`ACTIVATED_EFFECTS`. A row
here for a shape `parsed_layer_effects` already covers is dead weight at best
(W5 deleted eight such rows - Glorious Anthem, Giant Growth, Elesh Norn,
Dismember, Basking Rootwalla, Mutagenic Growth, Assault Strobe, and Monstrous
Rage's pump - once this test proved each reachable without its row) and a
silent trap at worst: `effects_for` checks `LAYER_EFFECTS` first, so a
re-added row always *shadows* the parser rather than merely duplicating it.

For every row this test reads the exact oracle text `effects_for` would have
handed the parser - `Card.oracle_text` for a real card, `MONSTER_ROLE.rules_text`
for the one entry keyed on a token's name rather than a card in the pool - and
asserts `parsed_layer_effects` comes back `None`. A row that fails this test is
telling you which shape the parser already understands; delete the row.

T10's round-trip/replay invariant does not apply here: this file never builds
a `Game`, only reads a static registry against parser output, so `tests/
scenarios/conftest.py`'s hook has nothing to checkpoint.
"""

import pytest

from magic_cards_model.machines.layers import LAYER_EFFECTS, parsed_layer_effects
from magic_cards_model.models.token import MONSTER_ROLE
from tests.cards import card


def _oracle_text(card_name: str) -> str:
    """The text `effects_for` reads for one `LAYER_EFFECTS` key.

    "Monster" is not a Scryfall printing in the pool - it is CR 111.10k's
    predefined Role token, whose characteristics come from `MONSTER_ROLE`
    (`models/token.py`) rather than a fixture, exactly as
    `_monster_role`'s own docstring in `machines/layers.py` documents.
    """
    if card_name == "Monster":
        return MONSTER_ROLE.rules_text
    return card(card_name).oracle_text or ""


@pytest.mark.parametrize("card_name", sorted(LAYER_EFFECTS.keys()))
def test_layer_effects_row_is_not_reachable_through_the_parser(card_name: str) -> None:
    text = _oracle_text(card_name)
    result = parsed_layer_effects(text)
    assert result is None, (
        f"LAYER_EFFECTS[{card_name!r}] is dead weight: parsed_layer_effects "
        f"already reads {card_name!r}'s oracle text into a working effect "
        f"({text!r}). Delete the row - see this file's docstring."
    )


def test_a_readded_redundant_row_fails_the_guard() -> None:
    """Proof the guard above actually catches a regrowing registry.

    Glorious Anthem's "Creatures you control get +1/+1." is exactly the
    static-anthem shape W5 generalised and deleted the row for. Re-adding it
    would make `parsed_layer_effects` return something for its text, which is
    precisely what the parametrized test above asserts never happens for any
    row still in the table - so simulating the re-add here must fail that same
    assertion.
    """
    text = card("Glorious Anthem").oracle_text or ""
    assert parsed_layer_effects(text) is not None, (
        "the guard cannot be proven to catch anything if the shape it is "
        "supposed to catch stopped parsing"
    )
    with pytest.raises(AssertionError):
        assert parsed_layer_effects(text) is None, (
            f"LAYER_EFFECTS['Glorious Anthem'] would be dead weight: "
            f"parsed_layer_effects already reads it ({text!r})."
        )
