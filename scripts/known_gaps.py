"""Print the known-gap list that playtest player agents must not report.

The playtest loop hands each player agent a "do not report these" list. Curating
that list by hand went stale three times in one session - each miss cost a whole
game, because a player spent its only report on a mechanic already documented as
missing (Utopia Sprawl's colour choice, Ocelot Pride's ascend, Mobilize's
tokens).

The list has a single source of truth already: the "Not modelled" table in
`docs/engine-coverage.md`. This script reads it, so the brief cannot drift from
the doc. Keep the doc current and the players stay current.

    uv run python scripts/known_gaps.py            # one line per gap
    uv run python scripts/known_gaps.py --detail   # include the note column
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "docs" / "engine-coverage.md"

_HEADING = re.compile(r"^##\s+(?P<title>.+?)\s*$")
_SEPARATOR = re.compile(r"^\|[\s:|-]+\|$")


def not_modelled_rows(text: str) -> list[tuple[str, str, str]]:
    """Every row of the "Not modelled" table, as (area, rules, note)."""
    rows: list[tuple[str, str, str]] = []
    in_section = False
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            # Any following "##" heading ends the section.
            in_section = heading.group("title").strip().lower() == "not modelled"
            continue
        if not in_section or not line.startswith("|"):
            continue
        if _SEPARATOR.match(line):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower() == "area":
            continue
        rows.append((cells[0], cells[1], cells[2]))
    return rows


def _plain(markdown: str) -> str:
    """Strip the markdown a terminal brief does not need."""
    text = re.sub(r"`([^`]*)`", r"\1", markdown)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    return re.sub(r"\*([^*]*)\*", r"\1", text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--detail",
        action="store_true",
        help="include each gap's note, not just its name",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="also list the cards sweep_pool.py already knows resolve to nothing",
    )
    args = parser.parse_args()

    rows = not_modelled_rows(DOC.read_text())
    if not rows:
        raise SystemExit(f"no 'Not modelled' table found in {DOC}")

    print("Known gaps - do NOT report these. Source: docs/engine-coverage.md")
    print()
    for area, rules, note in rows:
        print(f"- {_plain(area)} ({_plain(rules)})")
        if args.detail:
            print(f"    {_plain(note)}")
    print()
    print(f"{len(rows)} known gaps.")

    if args.silent:
        print()
        print(silent_card_section())


def silent_card_section() -> str:
    """The sweeper's silent list, which players also must not re-report.

    A card that resolves to nothing is already enumerated by
    `scripts/sweep_pool.py` and sits on the work queue. A player rediscovering
    one spends its single report on something already counted. What a game
    uniquely finds - and the sweeper never can - is a card that does the
    *wrong* thing rather than nothing at all.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sweep_pool import (  # type: ignore[import-not-found]
        SILENT,
        card,
        classify_card,
        has_rules_text,
        pool,
    )

    names = sorted(
        name
        for name in pool()
        if has_rules_text(printing := card(name)) and classify_card(printing)[0] == SILENT
    )
    header = (
        "Cards with at least one clause that does nothing - do NOT report\n"
        "those clauses; they are on the work queue already.\n"
        "Source: scripts/sweep_pool.py.\n"
        "\n"
        "Read that first line exactly: since `classify_card` began reporting\n"
        "the WORST clause per card rather than the best, a card is listed here\n"
        "if ANY of its clauses is silent. Most of these cards mostly work. If\n"
        "one of them did the wrong thing, or a different clause of it did\n"
        "nothing, that is a real finding and this list does not cover it.\n"
        "A card that does the WRONG thing is always reportable.\n"
    )
    return (
        header + "\n" + "\n".join(f"- {name}" for name in names) + f"\n\n{len(names)} silent cards."
    )


if __name__ == "__main__":
    main()
