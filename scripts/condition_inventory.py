"""Inventory the printed conditions this engine cannot read.

    uv run python scripts/condition_inventory.py                    # the pool
    uv run python scripts/condition_inventory.py --oracle cards.jsonl
    uv run python scripts/condition_inventory.py --oracle cards.jsonl --clusters P0,T1 --unread

Two kinds of printed condition gate what a card does, and both used to fail
without anybody measuring how often:

- a triggered ability's intervening "if" (CR 603.4) - probed with
  `machines/triggers.intervening_if_readable`, the same probe the support
  classifier asks: only a clause no reader claims is unread;
- an activated ability's CR 602.1b activation instructions - probed with
  `Game.unread_activation_restrictions` on a throwaway game, plus any
  instruction the parser left inside the effect text, which nothing reads.

Every in-format printing (Modern, Pioneer or Standard, banned included -
`support.in_target_formats`) is probed. `--oracle` reads a Scryfall
oracle-cards JSON-lines dump instead of the scenario pool
(`src/magic_cards_model/data/printings`).

A trigger condition's own "while <doing something>" qualifier (CR 603.2:
part of the trigger event, not an intervening "if") is probed alongside the
intervening "if" clauses, since the cluster files list it as one: read when
a registered reader claims it and its bare trigger event is one the engine
raises (`triggers.event_qualifier_readable`).

`--clusters` reads the named cluster files (`<ID>.tsv`, tab-separated kind,
card, clause) from `--cluster-dir` and reports, per cluster, how many of its
listed clauses are still unread; `--unread` lists them. A listed clause the
parser now cuts differently (a parse-boundary fix) is matched to the card's
current clauses of the same kind that no cluster file lists - and is unread
when there are none left. The exit status is always 0: this measures, it
does not gate.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import magic_cards_model
from magic_cards_model.machines.abilities import (
    ActivatedAbility,
    TriggeredAbility,
    parse_abilities,
)
from magic_cards_model.machines.triggers import (
    event_qualifier_readable,
    intervening_if_readable,
    triggered_abilities_of,
)
from magic_cards_model.models import CardState, Game, Player, Zone
from magic_cards_model.models.card import Card
from magic_cards_model.support import in_target_formats

POOL = Path(magic_cards_model.__file__).parent / "data" / "printings"
CLUSTER_DIR = Path(
    "/private/tmp/claude-501/-Users-szymonri-Documents-magic-trainer/"
    "64bce749-539c-4011-a6f3-c056d683e096/scratchpad/ec-clusters"
)

INTERVENING_IF = "intervening-if"
ACTIVATION = "activation"
#: The cluster files' own kind column, folded onto the two probes above.
_KIND_FAMILY = {
    "intervening-if": INTERVENING_IF,
    "activate-only-if": ACTIVATION,
    "activation-instruction": ACTIVATION,
}
_LEFT_IN_EFFECT = " (left in effect text)"
#: An activation instruction's own opening words (CR 602.1b), found where the
#: parser should never leave one: inside the effect text.
_STRANDED = re.compile(
    r"(?:^|(?<=[.\"'”’]\s))((?:Activate|Any player may activate|Only your opponents may"
    r" activate)\b[^.]*\.)"
)
_SKIPPED_LAYOUTS = {"token", "emblem", "art_series", "double_faced_token"}


@dataclass(frozen=True)
class Probed:
    """One printed condition and whether the engine reads it."""

    kind: str
    card: str
    clause: str
    read: bool


def load_printings(oracle: Path | None) -> list[Card]:
    """Every in-format printing, one per name, from `oracle` or the pool."""
    raws: list[dict] = []
    if oracle is None:
        raws = [json.loads(path.read_text()) for path in sorted(POOL.glob("*.json"))]
    else:
        with oracle.open() as handle:
            raws = [json.loads(line) for line in handle if line.strip()]
    seen: set[str] = set()
    printings: list[Card] = []
    for raw in raws:
        if raw.get("layout") in _SKIPPED_LAYOUTS:
            continue
        try:
            printing = Card.model_validate(raw)
        except Exception:  # noqa: BLE001 - a printing the model refuses is skipped
            continue
        if printing.name in seen or not in_target_formats(printing):
            continue
        seen.add(printing.name)
        printings.append(printing)
    return printings


def _throwaway_source(printing: Card) -> tuple[Game, CardState]:
    game = Game(
        players=[Player(username="you"), Player(username="opponent")],
        schema_version=Game.CURRENT_SCHEMA_VERSION,
    )
    source = CardState(card=printing, zone=Zone.BATTLEFIELD, controller="you", owner="you")
    source.bind_to_game(game)
    game.battlefield.append(source)
    return game, source


def probe(printing: Card) -> list[Probed]:
    """Every intervening "if" and activation instruction `printing` prints,
    each with whether the engine reads it."""
    try:
        abilities = list(parse_abilities(printing))
    except Exception:  # noqa: BLE001 - an unparseable card has nothing to probe
        return []
    with contextlib.suppress(Exception):
        abilities += triggered_abilities_of(printing)
    found: list[Probed] = []
    seen: set[tuple[str, str]] = set()
    game_and_source: tuple[Game, CardState] | None = None
    for ability in abilities:
        if isinstance(ability, TriggeredAbility) and ability.event_qualifier:
            key = (ability.text, ability.event_qualifier)
            if key not in seen:
                seen.add(key)
                found.append(
                    Probed(
                        INTERVENING_IF,
                        printing.name,
                        ability.event_qualifier,
                        event_qualifier_readable(ability),
                    )
                )
        if isinstance(ability, TriggeredAbility) and ability.intervening_if:
            key = (ability.text, ability.intervening_if)
            if key in seen:
                continue
            seen.add(key)
            found.append(
                Probed(
                    INTERVENING_IF,
                    printing.name,
                    ability.intervening_if,
                    intervening_if_readable(printing, ability),
                )
            )
        elif isinstance(ability, ActivatedAbility):
            key = (ability.text, ability.instructions or "")
            if key in seen:
                continue
            seen.add(key)
            for stranded in _STRANDED.finditer(ability.effect or ""):
                found.append(
                    Probed(
                        ACTIVATION,
                        printing.name,
                        stranded.group(1) + _LEFT_IN_EFFECT,
                        False,
                    )
                )
            if not ability.instructions:
                continue
            if game_and_source is None:
                try:
                    game_and_source = _throwaway_source(printing)
                except Exception:  # noqa: BLE001
                    found.append(Probed(ACTIVATION, printing.name, ability.instructions, False))
                    continue
            game, source = game_and_source
            unread = game.unread_activation_restrictions(ability, source)
            if not unread:
                found.append(Probed(ACTIVATION, printing.name, ability.instructions, True))
            for text in unread:
                found.append(Probed(ACTIVATION, printing.name, text, False))
    return found


def _matching_key(kind: str, clause: str) -> str:
    """A clause as the cluster files and this probe both spell it."""
    del kind  # the probe and every cluster file spell each kind the same way
    text = clause.strip().removesuffix(_LEFT_IN_EFFECT).strip().rstrip(".").strip().lower()
    return text.removeprefix("activate only if ")


def read_clusters(cluster_dir: Path, ids: list[str]) -> dict[str, list[tuple[str, str, str]]]:
    """`{cluster id: [(kind, card, clause), ...]}` for each named cluster file."""
    clusters: dict[str, list[tuple[str, str, str]]] = {}
    for cluster_id in ids:
        path = cluster_dir / f"{cluster_id}.tsv"
        rows = []
        for line in path.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                rows.append((parts[0], parts[1], parts[2]))
        clusters[cluster_id] = rows
    return clusters


def cluster_report(
    clusters: dict[str, list[tuple[str, str, str]]],
    probed: dict[str, list[Probed]],
    listed_elsewhere: dict[str, set[str]],
) -> dict[str, list[tuple[str, str, str, str]]]:
    """Per cluster, every listed clause with its verdict: `read`, `unread` or
    `missing` (no in-format printing of that name was probed)."""
    report: dict[str, list[tuple[str, str, str, str]]] = {}
    for cluster_id, rows in clusters.items():
        verdicts = []
        for kind, name, clause in rows:
            family = _KIND_FAMILY.get(kind, ACTIVATION)
            if name not in probed:
                verdicts.append((kind, name, clause, "missing"))
                continue
            current = [row for row in probed[name] if row.kind == family]
            wanted = _matching_key(kind, clause)
            exact = [row for row in current if _matching_key(kind, row.clause) == wanted]
            if exact:
                read = all(row.read for row in exact)
            else:
                # The parser cuts this clause differently now: judge the
                # card's clauses of this kind that no cluster lists. With
                # none left the clause was dropped, not read.
                unlisted = [
                    row
                    for row in current
                    if _matching_key(kind, row.clause) not in listed_elsewhere[name]
                ]
                read = bool(unlisted) and all(row.read for row in unlisted)
            verdicts.append((kind, name, clause, "read" if read else "unread"))
        report[cluster_id] = verdicts
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--oracle", type=Path, default=None, help="Scryfall oracle-cards JSONL")
    parser.add_argument("--clusters", default=None, help="comma-separated cluster ids")
    parser.add_argument("--cluster-dir", type=Path, default=CLUSTER_DIR)
    parser.add_argument("--unread", action="store_true", help="list every unread clause")
    args = parser.parse_args(argv)

    printings = load_printings(args.oracle)
    probed: dict[str, list[Probed]] = {}
    for printing in printings:
        rows = probe(printing)
        if rows:
            probed[printing.name] = rows
    for printing in printings:
        probed.setdefault(printing.name, [])

    every = [row for rows in probed.values() for row in rows]
    print(f"in-format printings probed: {len(printings)}")
    for label, family in (("intervening-if", INTERVENING_IF), ("activation", ACTIVATION)):
        of_kind = [row for row in every if row.kind == family]
        unread = [row for row in of_kind if not row.read]
        print(
            f"{label}: {len(of_kind)} clauses, {len(unread)} unread "
            f"on {len({row.card for row in unread})} cards"
        )

    if args.clusters:
        ids = [part.strip() for part in args.clusters.split(",") if part.strip()]
        every_id = sorted(path.stem for path in args.cluster_dir.glob("*.tsv"))
        listed_elsewhere: dict[str, set[str]] = defaultdict(set)
        for rows in read_clusters(args.cluster_dir, every_id).values():
            for kind, name, clause in rows:
                listed_elsewhere[name].add(_matching_key(kind, clause))
        report = cluster_report(read_clusters(args.cluster_dir, ids), probed, listed_elsewhere)
        for cluster_id, verdicts in report.items():
            unread = [row for row in verdicts if row[3] != "read"]
            print(f"cluster {cluster_id}: {len(verdicts)} clauses, {len(unread)} unread")
            if args.unread:
                for kind, name, clause, verdict in unread:
                    print(f"  {verdict}\t{kind}\t{name}\t{clause}")
    elif args.unread:
        for row in every:
            if not row.read:
                print(f"  unread\t{row.kind}\t{row.card}\t{row.clause}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
