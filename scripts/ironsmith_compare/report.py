"""The comparison rendered as `report.json` (schema-versioned), `report.md` and
`worklist.csv`. Every file lands in the gitignored out dir; none carries ironsmith's
compiled text (the reader never selects it)."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict

from scripts.ironsmith_compare.compare import RANKING, CardRow, Comparison

SCHEMA_VERSION = 1
CSV_FIELDS = (
    "rank",
    "name",
    "oracle_id",
    "formats",
    "mcm_status",
    "iron_status",
    "metagame_weight",
    "cluster_size",
    "cluster_label",
    "mcm_clause",
    "mcm_reason",
    "iron_reason",
)
#: How many worklist cards `report.md` lists (the csv and json carry all of them).
MD_WORKLIST_LIMIT = 300


def _card(row: CardRow) -> dict:
    return asdict(row)


def render_json(comparison: Comparison, meta: dict) -> str:
    report = {
        "schema_version": SCHEMA_VERSION,
        "meta": {**meta, "ranking": RANKING},
        "quadrants": comparison.quadrants,
        "unjoined_iron": comparison.unjoined_iron,
        "cards": [_card(row) for row in comparison.rows],
        "worklist": [_card(row) for row in comparison.worklist],
    }
    return json.dumps(report, indent=1, ensure_ascii=False) + "\n"


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_md(comparison: Comparison, meta: dict) -> str:
    lines = [
        f"# MCM vs ironsmith ({meta['format']})",
        "",
        f"- date: {meta['date']}",
        f"- ironsmith: {meta['iron_sha'][:12]} (pin {meta['pin'][:12]},"
        f" licence elected: {meta['licence']})",
        f"- magic-cards-model: {meta['mcm_sha'][:12]}",
        f"- worklist statuses: {', '.join(meta['statuses'])}",
        f"- ranking: {RANKING}",
        "",
        "ironsmith 'supported' is its own compile acceptance, not proof of correct play.",
        "",
        "## Coverage quadrants",
        "",
        "| quadrant | cards |",
        "|---|---|",
        *(f"| {name} | {count} |" for name, count in comparison.quadrants.items()),
        "",
        f"ironsmith rows not joined to the pool: {len(comparison.unjoined_iron)}",
        "",
        f"## Worklist ({len(comparison.worklist)} cards, top {MD_WORKLIST_LIMIT} by cluster)",
        "",
    ]
    shown = comparison.worklist[:MD_WORKLIST_LIMIT]
    clusters: dict[str, list[CardRow]] = {}
    for row in shown:
        clusters.setdefault(row.cluster, []).append(row)
    for rows in clusters.values():
        head = rows[0]
        lines += [
            f"### {_cell(head.cluster_label) or head.name} ({head.cluster_size} cards)",
            "",
            "| rank | card | metagame | ironsmith | MCM reason |",
            "|---|---|---|---|---|",
            *(
                f"| {r.rank} | {_cell(r.name)} | {r.metagame_weight:g} | {r.iron_status}"
                f" | {_cell(r.mcm_reason)} |"
                for r in rows
            ),
            "",
        ]
    return "\n".join(lines)


def render_csv(worklist: list[CardRow]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in worklist:
        data = asdict(row)
        data["formats"] = " ".join(row.formats)
        writer.writerow({field: data[field] for field in CSV_FIELDS})
    return buffer.getvalue()
