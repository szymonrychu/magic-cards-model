#!/usr/bin/env python
"""Survey any card - not just `src/magic_cards_model/data/printings` - for what
this engine would actually do with it, using the exact same classifier
`scripts/sweep_pool.py` runs over the fixture pool.

    uv run python scripts/survey_cards.py "Lightning Bolt" "Fiend Artisan"
    uv run python scripts/survey_cards.py --file names.txt
    uv run python scripts/survey_cards.py --deck path/to/deck.txt
    uv run python scripts/survey_cards.py --deck path/to/deck.txt --csv > out.csv
    uv run python scripts/survey_cards.py --deck path/to/deck.txt --json > out.json

Where a card comes from, in order:

1. `src/magic_cards_model/data/printings/` - read-only. If the printing is
   already in the scenario-test pool, it is loaded from there and Scryfall is
   never touched.
2. `--cache-dir` (default `.survey-cache/cards/` at the repo root) - a survey's
   own cache, separate from the fixture pool. A card fetched here is written
   *only* to this directory, never to `src/magic_cards_model/data/printings/`,
   so running this script never changes what the scenario-test suite sees.
3. Scryfall's `/cards/named?exact=` endpoint (the same call `scripts/add_card.py`
   makes), rate-limited the same way (~120ms between live fetches). The result
   is written to the cache directory above and reused on the next run.

A name Scryfall does not recognise is reported as `not_found` rather than
raising - it never reaches the classifier.

Classification reuses `scripts/sweep_pool.py`'s own production-dispatcher path
verbatim (`classify_card`, `has_rules_text`, `ignored_keywords`,
`targeting_gaps`): a card is **handled** (a registry row or a parser produced a
real effect), fails closed with a **notice** (the engine recognised the shape
and refused rather than guessing), is **silent** (nothing happened and nothing
was recorded - the only category that is a bug), or has **no rules text** at
all (a vanilla creature or a bare land - nothing to classify). Every result also
carries the same two side reports the sweeper prints: keywords with no
execution path, and targeting text `machines/targeting.py` could not read.
"""

import argparse
import csv
import json
import sys
import time
import urllib.error
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.add_card import fetch, slugify  # noqa: E402
from scripts.sweep_pool import (  # noqa: E402
    HANDLED,
    NOTICE,
    SILENT,
    STATIC_UNAUDITED,
    classify_card,
    has_rules_text,
    ignored_keywords,
    targeting_gaps,
)

import magic_cards_model  # noqa: E402
from magic_cards_model.models import Card  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = Path(magic_cards_model.__file__).parent / "data" / "printings"
DEFAULT_CACHE_DIR = REPO_ROOT / ".survey-cache" / "cards"

NOT_FOUND = "not_found"
NO_RULES_TEXT = "no_rules_text"


class CardNotFound(Exception):
    """Scryfall does not know this name."""


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def fetch_printing(name: str, cache_dir: Path, rate_limit: float = 0.12) -> Card:
    """The exact printing for `name`, preferring the fixture pool, then the
    survey cache, and only hitting Scryfall - via `scripts/add_card.fetch`,
    the same call `add_card.py` itself makes - as a last resort. A live fetch
    is written to `cache_dir` only; `src/magic_cards_model/data/printings/` is
    never touched.
    """
    slug = slugify(name)

    fixture_path = FIXTURES_DIR / f"{slug}.json"
    if fixture_path.exists():
        return Card.model_validate(_load_json(fixture_path))

    cache_path = cache_dir / f"{slug}.json"
    if cache_path.exists():
        return Card.model_validate(_load_json(cache_path))

    # Only an answer from Scryfall is a CardNotFound. A timeout or a reset
    # connection is no answer at all, and folding it in here filed a real card
    # as `not_found` - so a transport failure propagates as the OSError it is
    # and `main` fails the whole survey closed rather than mislabelling it.
    try:
        data = fetch(name)
    except urllib.error.HTTPError as error:
        raise CardNotFound(f"{error.code} {error.reason}") from error

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, indent=2) + "\n")
    time.sleep(rate_limit)
    return Card.model_validate(data)


@dataclass
class SurveyResult:
    """The verdict on one card: the same three-way split
    `scripts/sweep_pool.classify_card` produces, plus its two side reports."""

    name: str
    found: bool
    category: str
    detail: str = ""
    ignored_keywords: list[str] = field(default_factory=list)
    targeting_gaps: list[str] = field(default_factory=list)
    error: str = ""

    def as_row(self) -> dict:
        row = asdict(self)
        row["ignored_keywords"] = ";".join(self.ignored_keywords)
        row["targeting_gaps"] = ";".join(self.targeting_gaps)
        return row


def survey_one(name: str, cache_dir: Path) -> SurveyResult:
    try:
        printing = fetch_printing(name, cache_dir)
    except CardNotFound as error:
        return SurveyResult(name=name, found=False, category=NOT_FOUND, error=str(error))

    gaps = [f"[{kind}] {text}" for kind, text in targeting_gaps(printing)]
    keywords = ignored_keywords(printing)

    if not has_rules_text(printing):
        return SurveyResult(
            name=printing.name,
            found=True,
            category=NO_RULES_TEXT,
            ignored_keywords=keywords,
            targeting_gaps=gaps,
        )

    category, detail = classify_card(printing)
    return SurveyResult(
        name=printing.name,
        found=True,
        category=category,
        detail=detail,
        ignored_keywords=keywords,
        targeting_gaps=gaps,
    )


def survey(names: list[str], cache_dir: Path) -> list[SurveyResult]:
    seen: dict[str, SurveyResult] = {}
    for name in names:
        if name in seen:
            continue
        seen[name] = survey_one(name, cache_dir)
    return list(seen.values())


def parse_name_file(path: Path) -> list[str]:
    names = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        names.append(line)
    return names


def parse_decklist(path: Path) -> list[str]:
    """Names in a `magic-cards-model-api/decks/*.txt` decklist: a `# ...`
    header, `N Card Name` lines for the mainboard, a `Sideboard` separator,
    then more `N Card Name` lines for the sideboard. Both sections are
    surveyed - the separator line and the count are dropped, everything else
    that looks like `<digits> <name>` is kept, in file order, deduplicated.
    """
    names: list[str] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.lower() == "sideboard":
            continue
        count, _, rest = line.partition(" ")
        if not count.isdigit() or not rest.strip():
            continue
        names.append(rest.strip())
    # Deduplicate while preserving first-seen order.
    return list(dict.fromkeys(names))


def print_table(results: list[SurveyResult]) -> None:
    for result in sorted(results, key=lambda r: r.name):
        if not result.found:
            print(f"  {result.name:<40} {NOT_FOUND:<14} {result.error}")
            continue
        line = f"  {result.name:<40} {result.category:<14} {result.detail[:60]}"
        print(line)
        if result.ignored_keywords:
            print(f"    ignored keywords: {', '.join(result.ignored_keywords)}")
        for gap in result.targeting_gaps:
            print(f"    unreadable targeting: {gap[:70]}")


def print_summary(results: list[SurveyResult]) -> None:
    counts = Counter(r.category for r in results)
    total = len(results)
    print("-" * 62)
    print(f"  {total} card(s) surveyed")
    # STATIC_UNAUDITED belongs here or the summary silently undercounts:
    # a card whose static line the classifier will not judge lands in that
    # bucket, and leaving it out of this tuple meant it appeared in the table
    # and the CSV but in no total, so three cards surveyed could report two.
    # It is an explicit unknown, never coverage - see sweep_pool.
    for category in (HANDLED, NOTICE, SILENT, STATIC_UNAUDITED, NO_RULES_TEXT, NOT_FOUND):
        if counts[category]:
            print(f"    {category:<17} {counts[category]}")
    ignored_total = sum(len(r.ignored_keywords) for r in results)
    gaps_total = sum(len(r.targeting_gaps) for r in results)
    print(f"  {ignored_total} ignored-keyword occurrence(s)")
    print(f"  {gaps_total} unreadable targeting phrase(s)")


def write_csv(results: list[SurveyResult], stream) -> None:
    fieldnames = [
        "name",
        "found",
        "category",
        "detail",
        "ignored_keywords",
        "targeting_gaps",
        "error",
    ]
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    for result in sorted(results, key=lambda r: r.name):
        writer.writerow(result.as_row())


def write_json(results: list[SurveyResult], stream) -> None:
    payload = {
        "cards": [asdict(r) for r in sorted(results, key=lambda r: r.name)],
        "summary": dict(Counter(r.category for r in results)),
    }
    json.dump(payload, stream, indent=2)
    stream.write("\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("names", nargs="*", help="card names to survey")
    parser.add_argument("--file", type=Path, help="a file of card names, one per line")
    parser.add_argument(
        "--deck",
        type=Path,
        help="a decklist (magic-cards-model-api/decks/*.txt shape): "
        "'# ...' header, 'N Card Name' lines, a 'Sideboard' separator",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help=f"where a live Scryfall fetch is cached (default: {DEFAULT_CACHE_DIR}). "
        "src/magic_cards_model/data/printings/ is read but never written.",
    )
    parser.add_argument("--csv", action="store_true", help="write CSV to stdout instead of a table")
    parser.add_argument(
        "--json", action="store_true", help="write JSON to stdout instead of a table"
    )
    args = parser.parse_args(argv)

    names: list[str] = list(args.names)
    if args.file:
        names.extend(parse_name_file(args.file))
    if args.deck:
        names.extend(parse_decklist(args.deck))

    if not names:
        parser.print_help()
        return 1

    if args.csv and args.json:
        print("--csv and --json are mutually exclusive", file=sys.stderr)
        return 1

    try:
        results = survey(names, args.cache_dir)
    except OSError as error:
        print(f"could not reach Scryfall: {error}", file=sys.stderr)
        return 1

    if args.csv:
        write_csv(results, sys.stdout)
    elif args.json:
        write_json(results, sys.stdout)
    else:
        print_table(results)
        print_summary(results)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
