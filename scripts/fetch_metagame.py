#!/usr/bin/env python
"""Fetch a 30-day competitive-metagame snapshot from the spellslinger MCP
server and write `docs/card_coverage/metagame.json` - the Round 0 input for
the card-coverage campaign (`scripts/card_coverage.py`).

    mise run metagame:fetch
    uv run python scripts/fetch_metagame.py --as-of 2026-09-27

For each of modern/pioneer/standard: every archetype whose merged deck
count (summed across every id sharing its `canonical_name` -
`statistics_archetypes` can list the same name under several ids) over the
last 30 days is at least `--min-decks` (default 20) has every one of its
decks enumerated - day-sliced primary calls by `archetype_name` (which
resolves only to the highest-count id) plus a secondary harvest of every
other id, read off a day-sliced whole-format listing and then fetched
individually - deduplicated by `(pilot, tournament_date)` across both
sources. Every card whose MAINBOARD inclusion rate across those decks is at
least `--min-rate` (default 0.20) is kept.

Ported from a throwaway probe script (`archetype_rates.py`, written against
the real server while exploring the tools' shape) into typed, tested
tooling; `scripts/spellslinger_client.py` is the other half of that port.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts import card_coverage  # noqa: E402
from scripts.spellslinger_client import (  # noqa: E402
    DEFAULT_URL,
    MCPCallError,
    MCPTransport,
    SpellslingerClient,
    Transport,
)

__all__ = [
    "DEFAULT_URL",
    "MCPCallError",
    "MCPTransport",
    "SpellslingerClient",
    "Transport",
]

#: The three formats this campaign covers (owner instruction, "Target
#: formats" memory note): every other format is out of scope.
FORMATS: tuple[str, ...] = ("modern", "pioneer", "standard")

WINDOW_DAYS = 30
DEFAULT_MIN_DECKS = 20
DEFAULT_MIN_RATE = 0.20
DEFAULT_OUT_PATH = Path("docs/card_coverage/metagame.json")
DEFAULT_CACHE_DIR = Path(".scryfall-cache")

_DECK_LINE_RE = re.compile(r"^\s*\d+\s+(.+?)\s*$")


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------


def window_days(as_of: date, *, days: int = WINDOW_DAYS) -> list[str]:
    """Every ISO date in the `days`-day window ending on (and including)
    `as_of`, inclusive of both ends - `days + 1` dates in total."""
    start = as_of - timedelta(days=days)
    return [(start + timedelta(days=i)).isoformat() for i in range(days + 1)]


# ---------------------------------------------------------------------------
# Merging archetypes by canonical_name
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArchetypeMerge:
    """One `canonical_name`'s merged view across every id
    `statistics_archetypes` lists it under: `deck_count` summed, and
    `top_id` - the id `archetype_name=` resolves to on `statistics_decks` -
    the highest deck-count id (ties broken by id for determinism)."""

    canonical_name: str
    ids: tuple[str, ...]
    deck_count: int
    top_id: str


def merge_archetypes(archetypes: Sequence[Mapping[str, Any]]) -> list[ArchetypeMerge]:
    by_name: dict[str, list[Mapping[str, Any]]] = {}
    for entry in archetypes:
        by_name.setdefault(entry["canonical_name"], []).append(entry)
    merges: list[ArchetypeMerge] = []
    for name, group in by_name.items():
        top = max(group, key=lambda e: (e["deck_count"], e["id"]))
        merges.append(
            ArchetypeMerge(
                canonical_name=name,
                ids=tuple(sorted(e["id"] for e in group)),
                deck_count=sum(e["deck_count"] for e in group),
                top_id=top["id"],
            )
        )
    return merges


def qualifying_archetypes(
    merges: Iterable[ArchetypeMerge], *, min_decks: int
) -> list[ArchetypeMerge]:
    return sorted((m for m in merges if m.deck_count >= min_decks), key=lambda m: m.canonical_name)


# ---------------------------------------------------------------------------
# Deck enumeration
# ---------------------------------------------------------------------------


class TruncationError(RuntimeError):
    """A `statistics_decks` response came back truncated (over the
    server's ~32KB response cap) on a call this tool relies on to be
    complete - raised rather than silently undercounting."""

    def __init__(
        self, *, format: str, archetype: str, date: str, count: int, original_count: int | None
    ) -> None:
        super().__init__(
            f"{format}/{archetype} on {date}: response truncated "
            f"({count} of {original_count} items) - day-slicing is supposed to keep this "
            f"under the cap; narrow the window or investigate before trusting this snapshot"
        )


def response_items(response: Any) -> tuple[list[dict[str, Any]], bool, int | None]:
    """`(items, truncated, original_count)` out of a `statistics_decks`
    response: a plain list when the payload fit under the server's ~32KB
    cap, or `{"items", "_truncated", "_original_count"}` when it didn't."""
    if isinstance(response, dict):
        return (
            list(response.get("items", [])),
            bool(response.get("_truncated")),
            response.get("_original_count"),
        )
    return list(response), False, len(response)


def _deck_key(item: Mapping[str, Any]) -> tuple[str, str]:
    return (item["pilot"], item["tournament_date"])


def fetch_whole_format_listing_by_day(
    client: SpellslingerClient, *, format: str, days: Sequence[str]
) -> dict[str, list[dict[str, Any]]]:
    """One `statistics_decks(include_cards="none")` call per day - the
    listing depends only on `(format, day)`, never on which archetype is
    asking, so `fetch_format` calls this once and shares it across every
    qualifying archetype's secondary harvest instead of each archetype
    re-fetching the same day's listing for itself. A truncated day is
    warned about here, once, rather than once per archetype that happens to
    need it."""
    by_day: dict[str, list[dict[str, Any]]] = {}
    for day in days:
        response = client.statistics_decks(
            format=format, date_from=day, date_to=day, limit=5000, include_cards="none"
        )
        items, truncated, original_count = response_items(response)
        if truncated:
            print(
                f"WARNING: {format} whole-format listing for {day} truncated "
                f"({len(items)} of {original_count}); secondary-harvest decks that fell in "
                "the truncated tail are missed this run",
                file=sys.stderr,
            )
        by_day[day] = items
    return by_day


def enumerate_archetype_decks(
    client: SpellslingerClient,
    *,
    format: str,
    merge: ArchetypeMerge,
    days: Sequence[str],
    whole_format_by_day: Mapping[str, list[dict[str, Any]]] | None = None,
) -> dict[tuple[str, str], list[str]]:
    """Every deck of `merge`'s whole merged canonical name, keyed by
    `(pilot, tournament_date)` so the same physical deck reached through two
    different sources (or two different ids) is counted once.

    Primary source: day-sliced `statistics_decks(archetype_name=...)` -
    `archetype_name` resolves only to `merge.top_id`, and day-slicing is
    what keeps each call's response under the truncation cap
    ("Slicing by single day keeps per-archetype responses under the cap").
    A truncated primary response is a real anomaly (day-slicing should have
    prevented it) and raises `TruncationError` immediately.

    Secondary source (only when `merge.ids` has more than one id):
    `merge.top_id` is the only id `archetype_name=` ever resolves to, so
    every other id's decks are only reachable by day-slicing the *whole
    format's* listing (`include_cards="none"`, cheap) and keeping the
    entries whose own `archetype_id` is one of them, then fetching each
    kept deck's mainboard individually by id. Unlike the primary source,
    this whole-format listing routinely exceeds the cap on a busy day
    (dozens of archetypes' decks land on the same date, not just this one),
    so a truncated day here is a real, expected exposure rather than a bug -
    it is reported on stderr (never silent) and the secondary harvest
    continues with what that day did return, rather than aborting the run
    over a busy day this source's own volume, not this archetype's, caused.
    `whole_format_by_day`, when given (`fetch_format` passes its own
    `fetch_whole_format_listing_by_day` result), is used instead of fetching
    that listing again for this archetype - the listing never depends on
    which archetype is asking."""
    decks: dict[tuple[str, str], list[str]] = {}

    for day in days:
        response = client.statistics_decks(
            format=format,
            archetype_name=merge.canonical_name,
            date_from=day,
            date_to=day,
            limit=5000,
            include_cards="names_only",
        )
        items, truncated, original_count = response_items(response)
        if truncated:
            raise TruncationError(
                format=format,
                archetype=merge.canonical_name,
                date=day,
                count=len(items),
                original_count=original_count,
            )
        for item in items:
            decks[_deck_key(item)] = item.get("mainboard") or []

    secondary_ids = set(merge.ids) - {merge.top_id}
    if secondary_ids:
        by_day = whole_format_by_day
        if by_day is None:
            by_day = fetch_whole_format_listing_by_day(client, format=format, days=days)
        wanted: list[dict[str, Any]] = [
            item
            for day in days
            for item in by_day.get(day, [])
            if item.get("archetype_id") in secondary_ids
        ]
        for item in wanted:
            key = _deck_key(item)
            if key in decks:
                continue
            full = client.statistics_decks(format=format, id=item["id"])
            decks[key] = [f"{e['count']} {e['name']}" for e in full.get("main_json") or []]

    return decks


# ---------------------------------------------------------------------------
# Inclusion rates
# ---------------------------------------------------------------------------


def _card_name(line: str) -> str:
    match = _DECK_LINE_RE.match(line)
    return match.group(1) if match else line.strip()


def resolve_deck_mainboard(
    mainboard: list[str], resolve_name: Callable[[str], str | None]
) -> list[str]:
    """`mainboard` (raw "N Name" lines) rewritten so every card is named by
    its canonical engine name where one resolves, deduplicated per deck -
    the same physical card must never be counted twice because it showed
    up under two different raw spellings in the same deck (front-face-only
    from one source, the full "A // B" name from another - both real,
    seen live). A name that does not resolve is kept under its own raw
    spelling rather than dropped, so it still counts towards something and
    `fetch_format`'s own resolve-and-report step downstream still sees it.

    This must run *before* `card_inclusion_rates`, not after: resolving
    only the names that already cleared a per-spelling rate threshold
    cannot recover a card whose rate was split across two spellings and
    never cleared the threshold under either one alone - each deck has to
    be canonicalized first so every deck contributes to one shared count.
    Rewritten as synthetic "1 <name>" lines since `card_inclusion_rates`
    only cares about presence per deck, never copy count."""
    names: set[str] = set()
    for line in mainboard:
        raw_name = _card_name(line)
        names.add(resolve_name(raw_name) or raw_name)
    return [f"1 {name}" for name in names]


def card_inclusion_rates(
    decks: Mapping[tuple[str, str], list[str]], *, min_rate: float
) -> dict[str, float]:
    """name -> rate (rounded to 3dp) for every card whose MAINBOARD
    inclusion rate across `decks` is at least `min_rate`. A deck counts a
    card once regardless of copy count - the question is presence in the
    deck, not how many copies."""
    total = len(decks)
    if total == 0:
        return {}
    counts: collections.Counter[str] = collections.Counter()
    for mainboard in decks.values():
        counts.update({_card_name(line) for line in mainboard})
    return {
        name: round(count / total, 3) for name, count in counts.items() if count / total >= min_rate
    }


# ---------------------------------------------------------------------------
# Name resolution against the engine's card data
# ---------------------------------------------------------------------------


#: Both separators a two-faced card's name can show up under - the engine's
#: own `" // "` and a single `" / "` some sources (spellslinger's own
#: rendering of a Room card, observed live: "Unholy Annex / Ritual Chamber")
#: use instead.
_SLASH_SEPARATORS = (" // ", " / ")


def _split_front_face(name: str) -> str:
    """`name` up to (not including) its first `" // "` or `" / "`
    separator - the front face of a two-faced card's name - or `name`
    unchanged when it carries neither separator at all."""
    for separator in _SLASH_SEPARATORS:
        if separator in name:
            return name.split(separator, 1)[0].strip()
    return name


def _normalize_slash_separator(name: str) -> str:
    """A single `" / "` separator normalized to the engine's own `" // "`.
    Never touches a name that already has `" // "`, and is a no-op on a
    name with no separator at all."""
    if " // " in name or " / " not in name:
        return name
    return name.replace(" / ", " // ")


def build_name_resolver(oracle_cards: Iterable[Mapping[str, Any]]) -> Callable[[str], str | None]:
    """A `name -> engine name | None` resolver built the same way
    `scripts/card_coverage.py` matches card names: a split/MDFC/adventure
    card's full engine name is `"A // B"`, but spellslinger's decklists
    (like this project's own tested-index lookups) carry only the front
    face, `front_name(name)`. Any full engine name resolves to itself; any
    front face resolves to the full `"A // B"` name it belongs to.

    Two further, real cases seen live: a Room card whose name came back
    with a single `" / "` separator instead of `" // "`
    (`_normalize_slash_separator`), and a name whose front face is right
    but whose back face is wrong or duplicated (a spellslinger data
    oddity) - falls back to resolving by front face alone
    (`_split_front_face`) rather than leaving either unresolved.

    Ineligible rows (`card_coverage.is_eligible_printing` - tokens,
    emblems, art_series-set-type, digital-only) or never-legal-anywhere-
    in-scope rows (`card_coverage._in_target_formats`) are skipped
    entirely: a real bug found live is oracle-cards also carrying a
    `memorabilia`/`layout="art_series"` gallery object literally named
    "Twinmaw Stormbrood // Twinmaw Stormbrood" (never legal in any format -
    `is_eligible_printing` alone does not catch it, since its `set_type` is
    `"memorabilia"`, not `"art_series"`) alongside the real adventure card
    "Twinmaw Stormbrood // Charring Bite" - left unfiltered, the bogus
    row's exact name shadowed the front-face fallback that would otherwise
    have found the real card. Gating on legality is also exactly what
    keeps this resolver's index matching `card_coverage.py`'s own
    classification pool, which every Round 0 name is checked against next."""
    by_full_name: set[str] = set()
    by_front_name: dict[str, str] = {}
    for raw in oracle_cards:
        if not card_coverage.is_eligible_printing(raw) or not card_coverage._in_target_formats(raw):
            continue
        name = raw.get("name")
        if not name:
            continue
        by_full_name.add(name)
        front = card_coverage.front_name(name)
        if front != name:
            by_front_name.setdefault(front, name)

    def resolve(name: str) -> str | None:
        for candidate in (name, _normalize_slash_separator(name)):
            if candidate in by_full_name:
                return candidate
            if candidate in by_front_name:
                return by_front_name[candidate]
        front = _split_front_face(name)
        if front != name:
            return by_front_name.get(front)
        return None

    return resolve


# ---------------------------------------------------------------------------
# Per-format fetch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArchetypeSnapshot:
    deck_count_reported: int
    decks_enumerated: int
    cards: dict[str, float] = field(default_factory=dict)


def fetch_format(
    client: SpellslingerClient,
    *,
    format: str,
    as_of: date,
    min_decks: int,
    min_rate: float,
    resolve_name: Callable[[str], str | None],
    unresolved: set[str],
) -> dict[str, ArchetypeSnapshot]:
    """Every qualifying archetype's snapshot for one format. Any card whose
    inclusion rate clears `min_rate` but whose name does not resolve against
    the engine's card data is added to `unresolved` (for the caller to
    report, never dropped silently) and left out of that archetype's own
    `cards`."""
    days = window_days(as_of)
    archetypes = client.statistics_archetypes(format=format, limit=5000)
    qualifying = qualifying_archetypes(merge_archetypes(archetypes), min_decks=min_decks)

    # The whole-format day listing is shared across every archetype's
    # secondary harvest below (it depends only on (format, day)) - fetched
    # once here rather than once per archetype that happens to need it.
    whole_format_by_day = None
    if any(set(m.ids) - {m.top_id} for m in qualifying):
        whole_format_by_day = fetch_whole_format_listing_by_day(client, format=format, days=days)

    result: dict[str, ArchetypeSnapshot] = {}
    for merge in qualifying:
        decks = enumerate_archetype_decks(
            client, format=format, merge=merge, days=days, whole_format_by_day=whole_format_by_day
        )
        resolved_decks = {
            key: resolve_deck_mainboard(mainboard, resolve_name) for key, mainboard in decks.items()
        }
        raw_rates = card_inclusion_rates(resolved_decks, min_rate=min_rate)
        resolved_cards: dict[str, float] = {}
        for name, rate in raw_rates.items():
            resolved = resolve_name(name)
            if resolved is None:
                unresolved.add(name)
                continue
            resolved_cards[resolved] = max(rate, resolved_cards.get(resolved, 0.0))
        result[merge.canonical_name] = ArchetypeSnapshot(
            deck_count_reported=merge.deck_count,
            decks_enumerated=len(decks),
            cards=resolved_cards,
        )
    return result


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def build_output(
    *,
    as_of: date,
    min_decks: int,
    min_rate: float,
    formats: Mapping[str, Mapping[str, ArchetypeSnapshot]],
    unresolved: Iterable[str],
) -> dict[str, Any]:
    """The full `metagame.json` payload - deterministic: sorted keys and
    lists throughout, and rates already rounded to 3dp by
    `card_inclusion_rates`, so two runs against the same snapshot always
    serialize byte-identically."""
    out_formats: dict[str, dict[str, dict[str, Any]]] = {}
    for fmt, archetypes in formats.items():
        out_formats[fmt] = {
            name: {
                "deck_count_reported": snapshot.deck_count_reported,
                "decks_enumerated": snapshot.decks_enumerated,
                "cards": dict(sorted(snapshot.cards.items())),
            }
            for name, snapshot in sorted(archetypes.items())
        }
    return {
        "as_of": as_of.isoformat(),
        "window_days": WINDOW_DAYS,
        "min_decks": min_decks,
        "min_rate": min_rate,
        "source": "spellslinger statistics_decks",
        "formats": out_formats,
        "unresolved": sorted(set(unresolved)),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--as-of", type=date.fromisoformat, default=None, help="ISO date, default: today"
    )
    parser.add_argument("--min-decks", type=int, default=DEFAULT_MIN_DECKS)
    parser.add_argument("--min-rate", type=float, default=DEFAULT_MIN_RATE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--url", default=DEFAULT_URL)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    as_of = args.as_of or date.today()

    bulk_path = card_coverage.download_bulk("oracle-cards", cache_dir=args.cache_dir)
    resolve_name = build_name_resolver(card_coverage.load_bulk_json(bulk_path))

    client = SpellslingerClient(MCPTransport(args.url))

    unresolved: set[str] = set()
    formats: dict[str, dict[str, ArchetypeSnapshot]] = {}
    for fmt in FORMATS:
        formats[fmt] = fetch_format(
            client,
            format=fmt,
            as_of=as_of,
            min_decks=args.min_decks,
            min_rate=args.min_rate,
            resolve_name=resolve_name,
            unresolved=unresolved,
        )

    output = build_output(
        as_of=as_of,
        min_decks=args.min_decks,
        min_rate=args.min_rate,
        formats=formats,
        unresolved=unresolved,
    )

    for name in output["unresolved"]:
        print(
            f"WARNING: could not resolve {name!r} against the engine's card data", file=sys.stderr
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")

    for fmt, archetypes in output["formats"].items():
        distinct_cards = {name for a in archetypes.values() for name in a["cards"]}
        enumerated = sum(a["decks_enumerated"] for a in archetypes.values())
        reported = sum(a["deck_count_reported"] for a in archetypes.values())
        print(
            f"{fmt}: {len(archetypes)} qualifying archetypes, {enumerated} decks enumerated "
            f"({reported} reported), {len(distinct_cards)} distinct cards"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
