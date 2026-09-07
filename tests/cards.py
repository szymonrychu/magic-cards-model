"""The test card pool: real Scryfall printings, loaded by name.

Every card in src/magic_cards_model/data/printings is a genuine Scryfall
response. To use a card the pool does not have, add its json there rather than
hand-writing card data - tests are only worth anything here if they run
against the real shape.

    uv run python - <<'EOF'
    import json, pathlib, urllib.parse, urllib.request
    import magic_cards_model
    name = "Birds of Paradise"
    url = "https://api.scryfall.com/cards/named?exact=" + urllib.parse.quote(name)
    req = urllib.request.Request(url, headers={"User-Agent": "magic-cards-model/0.1",
                                               "Accept": "*/*"})
    data = json.load(urllib.request.urlopen(req))
    slug = "".join(c if c.isalnum() else "_" for c in data["name"].split("//")[0].strip().lower())
    pool = pathlib.Path(magic_cards_model.__file__).parent / "data" / "printings"
    (pool / f"{slug.strip('_')}.json").write_text(json.dumps(data, indent=2) + "\n")
    EOF
"""

import json
from functools import cache
from pathlib import Path

import magic_cards_model
from magic_cards_model.models import Card, CardState, Zone

CARD_POOL = Path(magic_cards_model.__file__).parent / "data" / "printings"


@cache
def pool() -> dict[str, Card]:
    """Every card in the pool, indexed by name."""
    cards: dict[str, Card] = {}
    for path in sorted(CARD_POOL.glob("*.json")):
        card_data = Card.model_validate(json.loads(path.read_text()))
        cards[card_data.name] = card_data
        # Multifaced cards are also reachable by their front face's name.
        cards.setdefault(card_data.name.split("//")[0].strip(), card_data)
    return cards


def card(name: str) -> Card:
    """Look up a printing by name. Raises listing the pool if it is missing."""
    try:
        return pool()[name]
    except KeyError:
        raise KeyError(
            f"{name!r} is not in src/magic_cards_model/data/printings. "
            f"Available: {', '.join(sorted(pool()))}. "
            f"Add its Scryfall json to the pool to use it."
        ) from None


def card_state(name: str, zone: Zone = Zone.LIBRARY, **kwargs) -> CardState:
    """One physical copy of a card, in a zone."""
    return CardState(card=card(name), zone=zone, **kwargs)
