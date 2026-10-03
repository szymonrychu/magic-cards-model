"""CR 201.4's Oracle card names: the legal answers to "choose a card name".

CR 201.4: "If an effect instructs a player to choose a card name, the player
must choose the name of a card in the Oracle card reference." Bundled in
`card_names.json` from Scryfall's own card-name catalog by
`scripts/add_card_names.py` - every card ever printed, not only the printings
this engine's pool bundles.
"""

import json
from functools import cache
from pathlib import Path

from .. import __file__ as _package_file

CARD_NAMES_FILE = Path(_package_file).parent / "data" / "card_names.json"


@cache
def oracle_card_names() -> frozenset[str]:
    """Every card name in the Oracle card reference (CR 201.4)."""
    return frozenset(json.loads(CARD_NAMES_FILE.read_text()))


def is_card_name(name: str) -> bool:
    """Whether `name` is a card in the Oracle card reference - a multi-faced
    card's whole name or either face's own name."""
    names = oracle_card_names()
    if name in names:
        return True
    return any(name in whole.split(" // ") for whole in names if " // " in whole)
