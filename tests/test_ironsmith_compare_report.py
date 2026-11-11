"""`scripts/ironsmith_compare/report.py` and the CLI (`python -m scripts.ironsmith_compare`).

The CLI runs end to end over fixtures we write into `tmp_path`: a tiny `oracle-cards`
array, MCM verdicts and our own normalised ironsmith rows. No ironsmith tool is run: the
one `collect` test stops at the pin check, before anything would start.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess

from scripts.ironsmith_compare.__main__ import latest_collected, main
from scripts.ironsmith_compare.compare import build_rows
from scripts.ironsmith_compare.coverage import write_jsonl
from scripts.ironsmith_compare.report import (
    behaviour_summary,
    render_csv,
    render_json,
    render_md,
)

_LEGAL = {"modern": "legal", "pioneer": "not_legal", "standard": "not_legal"}
_META = {
    "date": "2026-11-11",
    "iron_sha": "a" * 40,
    "mcm_sha": "b" * 40,
    "pin": "a59720c3966b02437c50807b8ed664496862810b",
    "licence": "AGPL-3.0-or-later",
    "format": "modern",
    "statuses": ["silent"],
}


def _pool():
    return [
        {"name": "Alpha", "oracle_id": "1", "legalities": _LEGAL},
        {"name": "Beta", "oracle_id": "2", "legalities": _LEGAL},
        {"name": "Gamma", "oracle_id": "3", "legalities": _LEGAL},
    ]


def _comparison():
    mcm = {
        "1": {"status": "handled", "clause": "", "reason": ""},
        "2": {"status": "silent", "clause": "Draw 2 cards.", "reason": "no reader"},
        "3": {"status": "silent", "clause": "Draw 3 cards.", "reason": "no reader"},
    }
    iron = [
        {
            "name": "Alpha",
            "join": "alpha",
            "status": "supported",
            "parse_status": "s",
            "reason": "",
        },
        {
            "name": "Gamma",
            "join": "gamma",
            "status": "supported",
            "parse_status": "s",
            "reason": "",
        },
    ]
    return build_rows(_pool(), mcm, iron, {"formats": {}}, fmt="modern", statuses={"silent"})


_BEHAVIOUR = [
    {"id": "alpha/activated-0", "card": "Alpha", "verdict": "agree", "message": ""},
    {
        "id": "alpha/triggered-0",
        "card": "Alpha",
        "verdict": "disagree",
        "message": "expected 2 Alpha permanents, got 1",
    },
    {
        "id": "beta/triggered-0",
        "card": "Beta",
        "verdict": "untranslated",
        "message": "decision may (answers are not recorded)",
    },
]


def test_behaviour_summary_counts_verdicts_and_reasons():
    summary = behaviour_summary(_BEHAVIOUR)
    assert summary["counts"] == {"agree": 1, "disagree": 1, "ironsmith-error": 0, "untranslated": 1}
    assert summary["untranslated_reasons"] == {"decision may (answers are not recorded)": 1}
    assert summary["by_card"]["Alpha"] == {"agree": 1, "disagree": 1}


def test_report_json_is_versioned_and_never_carries_compiled_text():
    report = json.loads(render_json(_comparison(), _BEHAVIOUR, _META))
    assert report["schema_version"] == 1
    assert report["meta"]["iron_sha"] == "a" * 40
    assert report["quadrants"] == {"both": 1, "mcm_only": 0, "iron_only": 1, "neither": 1}
    keys = set(report["cards"][0])
    assert not any("compiled" in key for key in keys)
    assert {
        "name",
        "oracle_id",
        "formats",
        "mcm_status",
        "mcm_reason",
        "iron_status",
        "iron_reason",
        "cluster",
        "metagame_weight",
        "rank",
        "behaviour",
    } <= keys
    alpha = next(card for card in report["cards"] if card["name"] == "Alpha")
    assert alpha["behaviour"] == {"agree": 1, "disagree": 1}
    assert [w["name"] for w in report["worklist"]] == ["Gamma", "Beta"]


def test_report_md_header_tables_and_disagreements():
    md = render_md(_comparison(), _BEHAVIOUR, _META)
    assert md.startswith("# MCM vs ironsmith (modern)\n")
    for text in (
        "a" * 12,
        "b" * 12,
        "a59720c39",
        "AGPL-3.0-or-later",
        "2026-11-11",
        "| both | 1 |",
        "Gamma",
        "expected 2 Alpha permanents, got 1",
        "decision may (answers are not recorded)",
    ):
        assert text in md
    assert chr(0x2014) not in md
    assert md.index("Gamma") < md.index("Beta")


def test_worklist_csv_columns_and_order():
    rows = list(csv.DictReader(io.StringIO(render_csv(_comparison().worklist))))
    assert [r["name"] for r in rows] == ["Gamma", "Beta"]
    assert rows[0]["rank"] == "1"
    assert rows[0]["iron_status"] == "supported"
    assert rows[0]["mcm_clause"] == "Draw 3 cards."


def test_compare_end_to_end_writes_the_three_reports(tmp_path, monkeypatch):
    bulk = tmp_path / "oracle-cards.json"
    bulk.write_text(
        json.dumps(
            [
                {
                    "name": "Lightning Bolt",
                    "oracle_id": "b0",
                    "legalities": _LEGAL,
                    "layout": "normal",
                    "set_type": "core",
                    "games": ["paper"],
                    "oracle_text": "x",
                },
            ]
        )
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            [
                {
                    "oracle_id": "b0",
                    "name": "Lightning Bolt",
                    "status": "handled",
                    "text_hash": "x",
                },
            ]
        )
    )
    out = tmp_path / "out"
    write_jsonl(
        [
            {
                "name": "Lightning Bolt",
                "join": "lightning bolt",
                "status": "supported",
                "parse_status": "strict_compiled",
                "reason": "",
            }
        ],
        out / "ironsmith-coverage.jsonl",
    )
    code = main(
        [
            "compare",
            "--out",
            str(out),
            "--bulk",
            str(bulk),
            "--baseline",
            str(baseline),
            "--ironsmith",
            str(tmp_path / "absent"),
        ]
    )
    assert code == 0
    report = json.loads((out / "report.json").read_text())
    assert report["quadrants"]["both"] == 1
    assert (out / "report.md").read_text().startswith("# MCM vs ironsmith")
    assert (out / "worklist.csv").read_text().startswith("rank,")


def test_collect_refuses_an_unpinned_checkout_before_running_anything(tmp_path, capsys):
    repo = tmp_path / "ironsmith"
    repo.mkdir()
    for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(
            ["git", "-c", "user.email=t@e.invalid", "-c", "user.name=t", *args],
            cwd=repo,
            check=True,
        )
    out = tmp_path / "out"
    code = main(["collect", "coverage", "--ironsmith", str(repo), "--out", str(out)])
    assert code == 2
    assert "HEAD" in capsys.readouterr().err
    assert not out.exists()


def test_doctor_reports_a_missing_checkout(tmp_path, capsys):
    assert main(["doctor", "--ironsmith", str(tmp_path / "absent")]) == 1
    printed = capsys.readouterr()
    assert "does not exist" in printed.err
    assert "git clone" in printed.out


def test_compare_finds_data_collected_before_an_mcm_commit(tmp_path):
    collected = tmp_path / ("c" * 12 + "-" + "1" * 12)
    write_jsonl([], collected / "ironsmith-coverage.jsonl")
    (tmp_path / ("c" * 12 + "-" + "2" * 12)).mkdir()  # after an MCM commit, nothing collected
    write_jsonl([], tmp_path / ("e" * 12 + "-" + "1" * 12) / "ironsmith-coverage.jsonl")
    assert latest_collected(tmp_path, "c" * 40) == collected
    assert latest_collected(tmp_path, "f" * 40) is None
