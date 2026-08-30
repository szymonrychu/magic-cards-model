"""Guard: nothing in `REPLACEMENTS` should be reachable through the parser
fallback `replacements_of` (`machines/replacement.py`) uses on a registry miss.

`REPLACEMENTS` keeps a card only when no compiled shape reads its wording - the
same principle `tests/scenarios/test_registry_is_minimal.py` enforces for
`machines/effects.py` and `tests/scenarios/test_layer_effects_registry_is_minimal.py`
enforces for `machines/layers.py`. A row here for a shape `parsed_card_replacements`
already covers is dead weight at best (this wave deleted eight such rows - Rest
in Peace, Leyline of the Void, Necrodominance, Sanctifier en-Vec, Containment
Priest, Alhammarret's Archive's two lines, Doubling Season's two lines, and Fog
Bank - once this test proved each reachable without its row) and a silent trap
at worst: `replacements_of` checks `REPLACEMENTS` first, so a re-added row
always *shadows* the parser rather than merely duplicating it.

For every row this test reads the card's own oracle text and asserts
`parsed_card_replacements` comes back empty. A row that fails this test is
telling you which compiled shape already understands it; delete the row.
"""

import pytest

from magic_cards_model.machines.replacement import REPLACEMENTS, parsed_card_replacements
from tests.cards import card


@pytest.mark.parametrize("card_name", sorted(REPLACEMENTS))
def test_replacements_row_is_not_reachable_through_the_generic_compilers(card_name: str) -> None:
    compiled = parsed_card_replacements(card(card_name))
    assert compiled == [], (
        f"REPLACEMENTS[{card_name!r}] is dead weight: the generic compilers already "
        f"read {card_name!r}'s oracle text into working replacement(s) ({compiled!r}). "
        f"Delete the row - see this file's docstring."
    )


def test_a_readded_redundant_row_fails_the_guard() -> None:
    """Proof the guard above actually catches a regrowing registry.

    Rest in Peace's "If a card or token would be put into a graveyard from
    anywhere, exile it instead." is exactly the shape this wave generalised and
    deleted the row for. Re-adding it would make `parsed_card_replacements`
    return something for its text, which is precisely what the parametrized
    test above asserts never happens for any row still in the table - so
    simulating the re-add here must fail that same assertion.
    """
    compiled = parsed_card_replacements(card("Rest in Peace"))
    assert compiled != [], (
        "the guard cannot be proven to catch anything if the shape it is "
        "supposed to catch stopped parsing"
    )
    with pytest.raises(AssertionError):
        assert compiled == [], (
            f"REPLACEMENTS['Rest in Peace'] would be dead weight: "
            f"parsed_card_replacements already reads it ({compiled!r})."
        )
