"""The per-card join of MCM's support verdicts with ironsmith's compile status, the
coverage quadrants, and the ranked worklist of the cards MCM does not support yet.

Pure data: the inputs are a Scryfall card pool, MCM verdicts and our own normalised
ironsmith rows (`coverage.read_status_db`). Ranking, highest first: metagame weight,
then whether ironsmith supports the card (evidence the text is machine-readable), then the
size of the oracle-template cluster it shares with other worklist cards, then name.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from scripts.card_coverage import cards_from_metagame, clause_signature
from scripts.ironsmith_compare.coverage import join_name

FORMATS = ("modern", "pioneer", "standard")
RANKING = (
    "metagame weight (highest inclusion rate over modern/pioneer/standard archetypes) desc,"
    " ironsmith supported first, cluster size desc, name"
)


@dataclass
class CardRow:
    name: str
    oracle_id: str
    formats: list[str]
    mcm_status: str
    mcm_clause: str
    mcm_reason: str
    iron_status: str
    iron_reason: str
    metagame_weight: float = 0.0
    cluster: str = ""
    cluster_label: str = ""
    cluster_size: int = 0
    rank: int = 0


@dataclass
class Comparison:
    rows: list[CardRow]
    quadrants: dict[str, int]
    unjoined_iron: list[str]
    worklist: list[CardRow] = field(default_factory=list)


def legal_formats(raw: dict) -> list[str]:
    legalities = raw.get("legalities") or {}
    return [fmt for fmt in FORMATS if legalities.get(fmt, "not_legal") != "not_legal"]


def _weights(metagame: dict) -> dict[str, float]:
    weights: dict[str, float] = {}
    for name, pulls in cards_from_metagame(metagame).items():
        key = join_name(name)
        weights[key] = max([weights.get(key, 0.0), *(rate for _f, _a, rate in pulls)])
    return weights


def _quadrant(row: CardRow) -> str:
    mcm = row.mcm_status == "handled"
    iron = row.iron_status == "supported"
    return {(True, True): "both", (True, False): "mcm_only", (False, True): "iron_only"}.get(
        (mcm, iron), "neither"
    )


def build_rows(
    pool: Iterable[dict],
    mcm: dict[str, dict],
    iron: list[dict],
    metagame: dict,
    *,
    fmt: str,
    statuses: set[str],
) -> Comparison:
    """`pool` cards legal in `fmt`, each joined with its MCM verdict (`mcm`, keyed by
    oracle id: `status`, `clause`, `reason`) and its ironsmith row (by `join_name`);
    the worklist holds the rows whose MCM status is in `statuses`."""
    iron_by_join = {row["join"]: row for row in iron}
    weights = _weights(metagame)
    rows: list[CardRow] = []
    joined: set[str] = set()
    for raw in pool:
        formats = legal_formats(raw)
        if fmt not in formats:
            continue
        key = join_name(raw["name"])
        verdict = mcm.get(raw.get("oracle_id") or raw["name"]) or {}
        iron_row = iron_by_join.get(key)
        if iron_row:
            joined.add(key)
        rows.append(
            CardRow(
                name=raw["name"],
                oracle_id=raw.get("oracle_id") or "",
                formats=formats,
                mcm_status=verdict.get("status", "unknown"),
                mcm_clause=verdict.get("clause", ""),
                mcm_reason=verdict.get("reason", ""),
                iron_status=iron_row["status"] if iron_row else "unknown",
                iron_reason=iron_row["reason"] if iron_row else "",
                metagame_weight=weights.get(key, 0.0),
            )
        )
    rows.sort(key=lambda r: (r.name, r.oracle_id))
    quadrants = Counter({"both": 0, "mcm_only": 0, "iron_only": 0, "neither": 0})
    quadrants.update(_quadrant(row) for row in rows)
    unjoined = sorted(row["name"] for row in iron if row["join"] not in joined)
    worklist = [row for row in rows if row.mcm_status in statuses]
    for row in worklist:
        row.cluster, row.cluster_label = clause_signature(row.name, row.mcm_clause)
    sizes = Counter(row.cluster for row in worklist)
    for row in worklist:
        row.cluster_size = sizes[row.cluster]
    worklist.sort(
        key=lambda r: (-r.metagame_weight, r.iron_status != "supported", -r.cluster_size, r.name)
    )
    for rank, row in enumerate(worklist, start=1):
        row.rank = rank
    return Comparison(rows, dict(quadrants), unjoined, worklist)
