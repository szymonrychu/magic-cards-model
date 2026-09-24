"""Smoke tests for `scripts/condition_inventory.py` over the scenario pool.

The script measures how many printed conditions - intervening "if" clauses
(CR 603.4) and activation instructions (CR 602.1b) - the engine cannot read,
using the same probes the support classifier asks
(`triggers.intervening_if_readable`, `Game.unread_activation_restrictions`).
"""

from pathlib import Path

from scripts.condition_inventory import (
    ACTIVATION,
    INTERVENING_IF,
    Probed,
    cluster_report,
    load_printings,
    main,
    probe,
)

from tests.cards import card


def test_the_pool_is_probed_and_counts_are_printed(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "in-format printings probed:" in out
    assert "intervening-if:" in out
    assert "activation:" in out


def test_only_in_format_printings_are_probed():
    names = {printing.name for printing in load_printings(None)}
    assert "Sundial of the Infinite" in names
    assert len(names) == len(load_printings(None))


def test_a_read_timing_instruction_probes_read():
    rows = probe(card("Sundial of the Infinite"))
    assert rows == [
        Probed(ACTIVATION, "Sundial of the Infinite", "Activate only during your turn.", True)
    ]


def test_a_who_may_activate_instruction_is_not_left_in_the_effect():
    assert [row.read for row in probe(card("Knight of the Holy Nimbus"))] == [True]


def test_a_read_intervening_if_probes_read():
    assert probe(card("Scytheclaw Raptor")) == [
        Probed(INTERVENING_IF, "Scytheclaw Raptor", "it's not their turn", True)
    ]


def test_cluster_rows_are_matched_to_the_current_clauses(tmp_path: Path, capsys):
    (tmp_path / "X1.tsv").write_text(
        "intervening-if\tScytheclaw Raptor\tit's not their turn\n"
        "activation-instruction\tSundial of the Infinite\tActivate only during your turn\n"
        "intervening-if\tNo Such Card Anywhere\tit's your turn\n"
    )
    assert main(["--clusters", "X1", "--cluster-dir", str(tmp_path), "--unread"]) == 0
    out = capsys.readouterr().out
    assert "cluster X1: 3 clauses, 1 unread" in out
    assert "missing\tintervening-if\tNo Such Card Anywhere" in out


def test_a_recut_clause_is_judged_by_the_cards_unlisted_clauses():
    """A parse-boundary fix changes the clause text; the listed row is then
    judged by the card's current clauses that no cluster lists."""
    probed = {
        "Some Card": [Probed(INTERVENING_IF, "Some Card", "the new, whole clause", True)],
    }
    report = cluster_report(
        {"P": [("intervening-if", "Some Card", "the old cut")]},
        probed,
        {"Some Card": {"the old cut"}},
    )
    assert report == {"P": [("intervening-if", "Some Card", "the old cut", "read")]}
    unread = {"Some Card": [Probed(INTERVENING_IF, "Some Card", "the new, whole clause", False)]}
    report = cluster_report(
        {"P": [("intervening-if", "Some Card", "the old cut")]},
        unread,
        {"Some Card": {"the old cut"}},
    )
    assert report["P"][0][3] == "unread"
