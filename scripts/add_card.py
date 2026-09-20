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
HEADERS = {"User-Agent": "magic-cards-model/0.1", "Accept": "*/*"}

#: Seconds any single Scryfall call may block for. `urlopen` with no timeout
#: waits forever on a socket that connects and then stops sending, and
#: `tests/test_survey_cards.py` reaches Scryfall on purpose - so an unbounded
#: read hangs `mise run test` itself rather than just this script.
FETCH_TIMEOUT = 20.0


def slugify(name: str) -> str:
    front = name.split("//")[0].strip().lower()
    return "".join(c if c.isalnum() else "_" for c in front).strip("_")


def fetch(name: str, timeout: float = FETCH_TIMEOUT) -> dict:
    url = "https://api.scryfall.com/cards/named?exact=" + urllib.parse.quote(name)
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


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
