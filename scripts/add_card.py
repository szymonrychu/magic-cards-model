#!/usr/bin/env python
"""Add a card to the scenario test pool.

    uv run python scripts/add_card.py "Birds of Paradise" "Llanowar Elves"

Fetches the exact printing from Scryfall and writes it to
src/magic_cards_model/data/printings.
"""

import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

import magic_cards_model

POOL = pathlib.Path(magic_cards_model.__file__).parent / "data" / "printings"
#: Scryfall fields that are not needed by the engine and carry third-party
#: content (artist credit, flavor text) or marketplace data; never stored.
DROPPED_KEYS = ("flavor_text", "prices", "purchase_uris", "artist")
HEADERS = {"User-Agent": "magic-cards-model/0.1", "Accept": "*/*"}


def slugify(name: str) -> str:
    front = name.split("//")[0].strip().lower()
    return "".join(c if c.isalnum() else "_" for c in front).strip("_")


def strip_dropped(value):
    """Remove DROPPED_KEYS from a card record, including inside card_faces."""
    if isinstance(value, dict):
        for key in DROPPED_KEYS:
            value.pop(key, None)
        for child in value.values():
            strip_dropped(child)
    elif isinstance(value, list):
        for child in value:
            strip_dropped(child)
    return value


def fetch(name: str) -> dict:
    url = "https://api.scryfall.com/cards/named?exact=" + urllib.parse.quote(name)
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request) as response:
        return strip_dropped(json.load(response))


def main(names: list[str]) -> int:
    if not names:
        print(__doc__)
        return 1

    POOL.mkdir(parents=True, exist_ok=True)
    for name in names:
        try:
            card = fetch(name)
        except urllib.error.HTTPError as error:
            print(f"{name}: {error.code} - check the exact card name")
            return 1

        path = POOL / f"{slugify(card['name'])}.json"
        path.write_text(json.dumps(card, indent=2) + "\n")
        print(f"{card['name']} -> {path.relative_to(POOL.parent.parent.parent.parent)}")
        time.sleep(0.12)  # Scryfall asks for 100ms between requests
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
