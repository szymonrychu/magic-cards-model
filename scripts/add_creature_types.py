#!/usr/bin/env python
"""Refresh the bundled creature-type list from the Comprehensive Rules text.

    mise run rules:pull
    uv run python scripts/add_creature_types.py

Writes src/magic_cards_model/data/creature_types.json - CR 205.3m's own list,
read out of `.rules/MagicCompRules.txt`, never typed by hand. The rules file is
gitignored, so the list is bundled for the engine to read at runtime;
`tests/scenarios/test_choose_a_creature_type.py` compares the two whenever the
rules file is on disk, so a stale bundle fails a test instead of refusing a new
creature type.
"""

import json
import re
import sys

from magic_cards_model.data.creature_types import (
    CREATURE_TYPES_FILE,
    RULES_FILE,
    rules_creature_types,
)


def main() -> int:
    if not RULES_FILE.exists():
        print(f"{RULES_FILE} is missing - run `mise run rules:pull` first")
        return 1
    text = RULES_FILE.read_text()
    types = rules_creature_types(text)
    effective = re.search(r"These rules are effective as of ([^.]+)\.", text)
    CREATURE_TYPES_FILE.write_text(
        json.dumps(
            {
                "rule": "205.3m",
                "effective": effective.group(1) if effective else None,
                "types": list(types),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"{len(types)} creature types -> {CREATURE_TYPES_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
