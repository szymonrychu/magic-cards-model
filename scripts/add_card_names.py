#!/usr/bin/env python
"""Refresh the bundled Oracle card-name list from Scryfall's own catalog.

    uv run python scripts/add_card_names.py

Writes src/magic_cards_model/data/card_names.json - the name of every card in
the Oracle card reference (CR 201.4: a named card "must be the name of a card
in the Oracle card reference"). Same contract as `scripts/add_subtypes.py`:
real data fetched from Scryfall, never hand-written, re-runnable when a set
adds cards.
"""

import json
import pathlib
import sys
import urllib.request

import magic_cards_model

DESTINATION = pathlib.Path(magic_cards_model.__file__).parent / "data" / "card_names.json"
HEADERS = {"User-Agent": "magic-cards-model/0.1", "Accept": "*/*"}


def main() -> int:
    request = urllib.request.Request("https://api.scryfall.com/catalog/card-names", headers=HEADERS)
    with urllib.request.urlopen(request) as response:
        names = sorted(json.load(response)["data"])
    DESTINATION.write_text(json.dumps(names, ensure_ascii=False, indent=0) + "\n")
    print(f"{len(names)} names -> {DESTINATION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
