"""ironsmith's per-card compile status, read as data from the SQLite its own
`sync_card_status_db` binary writes, normalised into our `.jsonl` rows.

Only the status columns are read. Compiled text and card definitions are never selected,
so no ironsmith output that could carry its program text reaches our reports.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

IronStatus = Literal["supported", "partial", "unsupported"]

#: `PRAGMA user_version` values whose `latest_card_compilation` view this reader knows.
KNOWN_SCHEMA_VERSIONS = frozenset({11, 12})

_QUERY = (
    "SELECT card_name, parse_status, parse_error, has_unimplemented, parse_lossy,"
    " parse_loss_reasons, semantic_mismatch FROM latest_card_compilation ORDER BY card_name"
)


class SchemaError(RuntimeError):
    """The status database is at a schema version this reader was not written for."""


def join_name(name: str) -> str:
    """The key both sides are joined on: the front face, casefolded."""
    return name.split("//")[0].strip().casefold()


def iron_status(row: dict) -> IronStatus:
    if row["parse_status"] != "strict_compiled":
        return "unsupported"
    flagged = row["has_unimplemented"] or row["parse_lossy"] or row["semantic_mismatch"]
    return "partial" if flagged else "supported"


def read_status_db(db: Path) -> list[dict]:
    """One normalised row per card in the database, opened read-only."""
    conn = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in KNOWN_SCHEMA_VERSIONS:
            known = sorted(KNOWN_SCHEMA_VERSIONS)
            raise SchemaError(
                f"{db}: status schema version {version} is not one of {known};"
                " the ironsmith pin moved without this reader"
            )
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(_QUERY)]
    finally:
        conn.close()
    return [
        {
            "name": row["card_name"],
            "join": join_name(row["card_name"]),
            "status": iron_status(row),
            "parse_status": row["parse_status"],
            "reason": row["parse_error"] or row["parse_loss_reasons"] or "",
        }
        for row in rows
    ]


def write_jsonl(rows: Iterable[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_cards_json(pool: list[dict], path: Path) -> None:
    """The card pool as the plain JSON array of Scryfall card objects that ironsmith's
    `--cards` flag reads, so both engines read the identical oracle text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pool, ensure_ascii=False))
