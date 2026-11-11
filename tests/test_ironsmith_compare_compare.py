"""`scripts/ironsmith_compare/compare.py`: the per-card join, the quadrants and the ranked,
cluster-grouped worklist of the cards MCM does not support. Inputs are hand-built: card
dicts in Scryfall's shape, MCM verdicts, our own normalised ironsmith rows."""

from __future__ import annotations

from scripts.card_coverage import clause_signature
from scripts.ironsmith_compare.compare import build_rows

_LEGAL = {"modern": "legal", "pioneer": "not_legal", "standard": "not_legal"}


def _card(name, oracle_id, legalities=None):
    return {"name": name, "oracle_id": oracle_id, "legalities": legalities or _LEGAL}


def _iron(name, status):
    return {
        "name": name,
        "join": name.split("//")[0].strip().casefold(),
        "status": status,
        "parse_status": "x",
        "reason": "",
    }


def _mcm(status, clause="", reason=""):
    return {"status": status, "clause": clause, "reason": reason}


def _meta(**rates):
    return {"formats": {"modern": {"Deck": {"cards": rates}}}}


def test_quadrants_and_unjoined_names():
    pool = [
        _card("Both", "1"),
        _card("Mcm Only", "2"),
        _card("Iron Only", "3"),
        _card("Neither", "4"),
        _card("Fire // Ice", "5"),
    ]
    mcm = {
        "1": _mcm("handled"),
        "2": _mcm("handled"),
        "3": _mcm("silent", "Do a thing."),
        "4": _mcm("silent", "Do another thing."),
        "5": _mcm("handled"),
    }
    iron = [
        _iron("Both", "supported"),
        _iron("Mcm Only", "unsupported"),
        _iron("Iron Only", "supported"),
        _iron("Fire // Ice", "partial"),
        _iron("Not In Pool", "supported"),
    ]
    result = build_rows(pool, mcm, iron, {"formats": {}}, fmt="modern", statuses={"silent"})
    assert result.quadrants == {"both": 1, "mcm_only": 2, "iron_only": 1, "neither": 1}
    assert result.unjoined_iron == ["Not In Pool"]
    by_name = {row.name: row for row in result.rows}
    assert by_name["Neither"].iron_status == "unknown"
    assert by_name["Fire // Ice"].iron_status == "partial"


def test_quadrants_count_partial_and_unknown_as_not_supported():
    pool = [_card("A", "1"), _card("B", "2")]
    mcm = {"1": _mcm("silent", "x."), "2": _mcm("notice", "y.")}
    result = build_rows(
        pool, mcm, [_iron("A", "partial")], {"formats": {}}, fmt="modern", statuses={"silent"}
    )
    assert result.quadrants == {"both": 0, "mcm_only": 0, "iron_only": 0, "neither": 2}


def test_the_worklist_ranks_by_weight_then_ironsmith_support_then_cluster_size():
    pool = [
        _card(n, str(i))
        for i, n in enumerate(
            ["Heavy", "Light Iron", "Light Big Cluster A", "Light Big Cluster B", "Light Alone"]
        )
    ]
    mcm = {
        "0": _mcm("silent", "Unique heavy text."),
        "1": _mcm("silent", "Iron text."),
        "2": _mcm("silent", "Draw 2 cards, then mill 3."),
        "3": _mcm("silent", "Draw 4 cards, then mill 1."),
        "4": _mcm("silent", "Lonely text."),
    }
    iron = [_iron("Light Iron", "supported")]
    result = build_rows(pool, mcm, iron, _meta(Heavy=0.9), fmt="modern", statuses={"silent"})
    assert [row.name for row in result.worklist] == [
        "Heavy",
        "Light Iron",
        "Light Big Cluster A",
        "Light Big Cluster B",
        "Light Alone",
    ]
    assert [row.rank for row in result.worklist] == [1, 2, 3, 4, 5]
    assert result.worklist[0].metagame_weight == 0.9
    cluster_a, cluster_b = result.worklist[2], result.worklist[3]
    assert cluster_a.cluster == cluster_b.cluster
    assert cluster_a.cluster_size == 2
    assert (
        cluster_a.cluster
        == clause_signature("Light Big Cluster A", "Draw 2 cards, then mill 3.")[0]
    )


def test_the_worklist_follows_the_format_and_status_filters():
    pool = [
        _card("Modern Silent", "1"),
        _card(
            "Pioneer Silent",
            "2",
            {"modern": "not_legal", "pioneer": "legal", "standard": "not_legal"},
        ),
        _card("Modern Notice", "3"),
        _card("Modern Handled", "4"),
    ]
    mcm = {
        "1": _mcm("silent", "a."),
        "2": _mcm("silent", "b."),
        "3": _mcm("notice", "c."),
        "4": _mcm("handled"),
    }
    silent = build_rows(pool, mcm, [], {"formats": {}}, fmt="modern", statuses={"silent"})
    assert [r.name for r in silent.worklist] == ["Modern Silent"]
    assert {r.name for r in silent.rows} == {"Modern Silent", "Modern Notice", "Modern Handled"}
    both = build_rows(pool, mcm, [], {"formats": {}}, fmt="modern", statuses={"silent", "notice"})
    assert {r.name for r in both.worklist} == {"Modern Silent", "Modern Notice"}
    pioneer = build_rows(pool, mcm, [], {"formats": {}}, fmt="pioneer", statuses={"silent"})
    assert [r.name for r in pioneer.worklist] == ["Pioneer Silent"]
    assert pioneer.worklist[0].formats == ["pioneer"]


def test_metagame_weight_is_the_highest_rate_over_formats_and_archetypes():
    pool = [_card("Card", "1")]
    metagame = {
        "formats": {
            "modern": {"A": {"cards": {"Card": 0.2}}, "B": {"cards": {"Card": 0.5}}},
            "pioneer": {"C": {"cards": {"Card": 0.4}}},
        }
    }
    result = build_rows(
        pool, {"1": _mcm("silent", "x.")}, [], metagame, fmt="modern", statuses={"silent"}
    )
    assert result.worklist[0].metagame_weight == 0.5
