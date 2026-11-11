"""`scripts/ironsmith_compare/coverage.py`: reading ironsmith's card-status SQLite as data.

Each test writes its own tiny database in `tmp_path`: only the columns the reader asks
for, rows we invented. Column names are an interface fact of ironsmith's documented
status schema; nothing here comes from an ironsmith database or source file.
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from scripts.ironsmith_compare.coverage import (
    SchemaError,
    iron_status,
    join_name,
    read_jsonl,
    read_status_db,
    write_cards_json,
    write_jsonl,
)

_COLUMNS = (
    "card_name",
    "parse_status",
    "parse_error",
    "has_unimplemented",
    "parse_lossy",
    "parse_loss_reasons",
    "semantic_mismatch",
    "compiled_text",
)


def _db(tmp_path, rows, version=11):
    path = tmp_path / "status.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE compilation ({', '.join(_COLUMNS)})")
    conn.execute("CREATE VIEW latest_card_compilation AS SELECT * FROM compilation")
    for row in rows:
        values = {
            "parse_error": None,
            "has_unimplemented": 0,
            "parse_lossy": 0,
            "parse_loss_reasons": "",
            "semantic_mismatch": 0,
            "compiled_text": "SECRET COMPILED TEXT",
            **row,
        }
        conn.execute(
            f"INSERT INTO compilation VALUES ({', '.join('?' * len(_COLUMNS))})",
            [values[c] for c in _COLUMNS],
        )
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()
    return path


def test_status_mapping():
    base = {"has_unimplemented": 0, "parse_lossy": 0, "semantic_mismatch": 0}
    assert iron_status({**base, "parse_status": "strict_compiled"}) == "supported"
    assert iron_status({**base, "parse_status": "strict_compiled", "parse_lossy": 1}) == "partial"
    assert (
        iron_status({**base, "parse_status": "strict_compiled", "has_unimplemented": 1})
        == "partial"
    )
    assert (
        iron_status({**base, "parse_status": "strict_compiled", "semantic_mismatch": 1})
        == "partial"
    )
    assert iron_status({**base, "parse_status": "compiled_with_allow_unsupported"}) == (
        "unsupported"
    )
    assert iron_status({**base, "parse_status": "parse_failed"}) == "unsupported"


def test_join_name_is_the_casefolded_front_face():
    assert join_name("Fire // Ice") == "fire"
    assert join_name("Lightning Bolt") == join_name("LIGHTNING BOLT")


def test_rows_are_normalised_and_never_carry_compiled_text(tmp_path):
    db = _db(
        tmp_path,
        [
            {"card_name": "Lightning Bolt", "parse_status": "strict_compiled"},
            {
                "card_name": "Made Up Card",
                "parse_status": "parse_failed",
                "parse_error": "unknown clause",
            },
            {
                "card_name": "Other Card",
                "parse_status": "strict_compiled",
                "parse_lossy": 1,
                "parse_loss_reasons": "dropped rider",
            },
        ],
    )
    rows = read_status_db(db)
    assert rows == [
        {
            "name": "Lightning Bolt",
            "join": "lightning bolt",
            "status": "supported",
            "parse_status": "strict_compiled",
            "reason": "",
        },
        {
            "name": "Made Up Card",
            "join": "made up card",
            "status": "unsupported",
            "parse_status": "parse_failed",
            "reason": "unknown clause",
        },
        {
            "name": "Other Card",
            "join": "other card",
            "status": "partial",
            "parse_status": "strict_compiled",
            "reason": "dropped rider",
        },
    ]
    assert "COMPILED" not in json.dumps(rows)


@pytest.mark.parametrize("version", [11, 12])
def test_known_schema_versions_are_read(tmp_path, version):
    db = _db(tmp_path, [{"card_name": "X", "parse_status": "parse_failed"}], version)
    assert len(read_status_db(db)) == 1


def test_an_unknown_schema_version_is_refused(tmp_path):
    db = _db(tmp_path, [], version=13)
    with pytest.raises(SchemaError, match="13"):
        read_status_db(db)


def test_the_database_is_opened_read_only(tmp_path):
    db = _db(tmp_path, [{"card_name": "X", "parse_status": "parse_failed"}])
    before = db.read_bytes()
    read_status_db(db)
    assert db.read_bytes() == before


def test_jsonl_round_trip(tmp_path):
    rows = [{"name": "A", "n": 1}, {"name": "B", "n": 2}]
    path = tmp_path / "out" / "rows.jsonl"
    write_jsonl(rows, path)
    assert read_jsonl(path) == rows


def test_cards_json_is_a_plain_array_of_the_pool(tmp_path):
    pool = [{"name": "A", "oracle_id": "1"}, {"name": "B", "oracle_id": "2"}]
    path = tmp_path / "cards.json"
    write_cards_json(pool, path)
    assert json.loads(path.read_text()) == pool
