#!/usr/bin/env python
"""Refresh the bundled subtype vocabulary from Scryfall's own catalogs.

    uv run python scripts/add_subtypes.py

Writes src/magic_cards_model/data/subtypes.json - every subtype WOTC has
printed, grouped by the card type whose subtypes they are (CR 205.3). Same
contract as `scripts/add_card.py`: real data fetched from Scryfall, never
hand-written, re-runnable when a set adds a type.
"""

import json
import pathlib
import sys
import time
import urllib.request

import magic_cards_model

DESTINATION = pathlib.Path(magic_cards_model.__file__).parent / "data" / "subtypes.json"
HEADERS = {"User-Agent": "magic-cards-model/0.1", "Accept": "*/*"}
#: CR 205.3: every card type that has subtypes of its own, by the Scryfall
#: catalog that lists them.
CATALOGS = {
    "artifact": "artifact-types",
    "battle": "battle-types",
    "creature": "creature-types",
    "enchantment": "enchantment-types",
    "land": "land-types",
    "planeswalker": "planeswalker-types",
    "spell": "spell-types",
}


def fetch(catalog: str) -> list[str]:
    request = urllib.request.Request(f"https://api.scryfall.com/catalog/{catalog}", headers=HEADERS)
    with urllib.request.urlopen(request) as response:
        return sorted(json.load(response)["data"])


def main() -> int:
    vocabulary = {}
    for kind, catalog in CATALOGS.items():
        vocabulary[kind] = fetch(catalog)
        print(f"{catalog}: {len(vocabulary[kind])}")
        time.sleep(0.12)  # Scryfall asks for 100ms between requests
    DESTINATION.write_text(json.dumps(vocabulary, indent=2, ensure_ascii=False) + "\n")
    print(f"-> {DESTINATION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
