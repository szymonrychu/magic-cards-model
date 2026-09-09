"""The engine's own read access to its bundled Scryfall printings.

`tests/cards.py` already loads every `data/printings/*.json` file into a
name-indexed pool for tests to resolve card names against; this is the
identical loader, moved somewhere `src/` itself can reach, because at least
one real mechanic needs a card the game state has no other way to find.

Meld is that mechanic (CR 701.42, CR 712.8g): a melded permanent's
characteristics come from a *third* printing - the combined back face
(Hanweir, the Writhing Township, say) - that is never anyone's deck card and
so is never already loaded into a `Game`. Unlike `Deck.problems`, which takes
a `CardResolver` from its caller because deck legality is checked outside any
live game, `machines/meld.py`'s clause parser runs deep inside `Game.
resolve_top`, with no caller in a position to hand one in. The data this
needs already ships with the package (`data/printings/`, real Scryfall
responses, the same files every scenario test resolves against) - this is a
second reader of it, not a second copy.

No mocks, no hand-written data: every printing here is the genuine file
`scripts/add_card.py` wrote, verified against Scryfall at the moment it was
added, same as the test pool's own copies (because they are the same files).
"""

import json
from functools import cache
from pathlib import Path

from .. import __file__ as _package_file
from ..models.card import Card

PRINTINGS_DIR = Path(_package_file).parent / "data" / "printings"


@cache
def printing_pool() -> dict[str, Card]:
    """Every bundled printing, indexed by name (and by a multifaced card's
    own front-face name, the same alias `tests.cards.pool` provides)."""
    cards: dict[str, Card] = {}
    for path in sorted(PRINTINGS_DIR.glob("*.json")):
        card = Card.model_validate(json.loads(path.read_text()))
        cards[card.name] = card
        cards.setdefault(card.name.split("//")[0].strip(), card)
    return cards


def resolve_printing(name: str) -> Card | None:
    """The bundled `Card` named `name`, or `None` if this engine has never
    seen a printing by that name (`scripts/add_card.py` has not added it)."""
    return printing_pool().get(name)
