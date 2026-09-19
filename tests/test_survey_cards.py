"""Regression tests for `scripts/survey_cards.py`.

The survey tool exists so a card outside `tests/fixtures/cards` can still be
run through the exact production classifier `scripts/sweep_pool.classify_card`
uses - these tests pin the three promises the tool makes: it never writes to
the fixture pool, it reuses the fixture pool (not a fresh Scryfall fetch) for a
card already there, and it reports a name Scryfall does not know as
`not_found` instead of raising. No card data is hand-written anywhere below -
everything comes from `tests/fixtures/cards` (already real Scryfall printings)
or, for the not-found and live-fetch cases, a real call to Scryfall itself.
"""

import csv
import io
import json

import pytest
from scripts.survey_cards import (
    FIXTURES_DIR,
    HANDLED,
    NO_RULES_TEXT,
    NOT_FOUND,
    SILENT,
    fetch_printing,
    parse_decklist,
    parse_name_file,
    survey,
    survey_one,
    write_csv,
    write_json,
)

from magic_cards_model.models import Card


def test_a_card_that_works_classifies_as_handled(tmp_path):
    result = survey_one("Lightning Bolt", tmp_path)
    assert result.found
    assert result.category == HANDLED
    assert result.name == "Lightning Bolt"


def test_a_genuinely_dead_card_classifies_as_silent(tmp_path):
    """Keen-Eyed Curator is `test_sweep_pool.py`'s own control for a still-open
    gap: "As long as there are four or more card types among cards exiled with
    this creature, it gets +4/+4 and has trample." is a condition
    `machines/layers.py` does not read - `LayerContext` carries graveyards, not
    the cards exiled with a particular permanent - so the bonus happens nowhere.

    Rancor stood here until "Enchanted creature ..." joined "Equipped creature
    ..." in `machines/layers._ATTACHED_CREATURE_STATIC_RE`; it is `handled`
    today, and `tests/scenarios/test_attached_creature_statics.py` is what pins
    that. This test needs a card that is genuinely dead, so it names one.

    This test used to name Grand Arbiter Augustin IV and assert
    `no_rules_text`, on the reading that a permanent's static line was not
    something the classifier judged at all. That is the defect
    `scripts/sweep_pool.has_rules_text` no longer has: a permanent's static
    ability (CR 604.2) is now judged, and lands in `silent`,
    `static_unaudited`, `notice` or `handled` like anything else. Grand
    Arbiter itself is `handled` today (`machines/cost.py` reads all three of
    its lines, including the opponent-scoped tax `CostModifierKind.
    OPPONENT_TYPE_INCREASE` closed for the S10 survey, 2026-09-19), which is
    why it is no longer the dead-card control anywhere.
    """
    result = survey_one("Keen-Eyed Curator", tmp_path)
    assert result.found
    assert result.category == SILENT


def test_a_vanilla_creature_has_no_rules_text(tmp_path):
    result = survey_one("Craw Wurm", tmp_path)
    assert result.found
    assert result.category == NO_RULES_TEXT
    assert result.detail == ""


def test_split_card_both_halves_are_read(tmp_path):
    """Wear // Tear must classify as HANDLED, not SILENT - the same
    split-card regression `test_sweep_pool.py` already pins on
    `classify_card` directly, exercised here through the survey wrapper."""
    result = survey_one("Wear // Tear", tmp_path)
    assert result.found
    assert result.category == HANDLED


def test_unknown_card_name_is_not_found_not_a_crash(tmp_path):
    """A name Scryfall does not know reports `not_found` rather than raising.

    This one genuinely needs the network - the whole point is a name that is
    not in the fixture pool - so a transport failure is not the behaviour
    under test and must not be reported as one. Skipping on `OSError` (which
    covers the `ConnectionResetError` Scryfall throttling produced during a
    parallel run) keeps the assertion honest: it only ever passes or fails on
    what the tool did with a real answer.
    """
    try:
        result = survey_one("Zzzznot A Real Magic Card Toobsche", tmp_path)
    except OSError as exc:
        pytest.skip(f"Scryfall unreachable, so the not-found path is untestable here: {exc}")
    assert not result.found
    assert result.category == NOT_FOUND
    assert result.error


def test_a_fixture_pool_card_is_read_from_the_pool_not_fetched(tmp_path):
    """A card already in `tests/fixtures/cards` must be served from there -
    the survey cache directory must stay empty, proving Scryfall was never
    hit for it."""
    printing = fetch_printing("Lightning Bolt", tmp_path)
    assert printing.name == "Lightning Bolt"
    assert list(tmp_path.iterdir()) == []


def test_a_card_not_in_the_fixture_pool_is_cached_but_the_pool_is_untouched(tmp_path):
    """A live Scryfall fetch is written only to the survey's own cache
    directory, never to `tests/fixtures/cards` - running a survey must never
    change what the scenario-test suite sees."""
    name = "Krosan Tusker"
    fixture_path = FIXTURES_DIR / "krosan_tusker.json"
    assert not fixture_path.exists(), (
        "test picked a card that is already a fixture; pick a different one"
    )

    printing = fetch_printing(name, tmp_path)
    assert printing.name == name

    cached = list(tmp_path.glob("*.json"))
    assert len(cached) == 1
    assert not fixture_path.exists()

    # The cache is reused on a second call without re-fetching: reading the
    # cached json directly must round-trip to an identical Card.
    reloaded = Card.model_validate(json.loads(cached[0].read_text()))
    assert reloaded.name == name


def test_survey_deduplicates_repeated_names(tmp_path):
    results = survey(["Lightning Bolt", "Lightning Bolt", "Craw Wurm"], tmp_path)
    assert len(results) == 2


# -- Decklist and name-file parsing ------------------------------------------


def test_parse_decklist_reads_mainboard_and_sideboard(tmp_path):
    deck = tmp_path / "deck.txt"
    deck.write_text(
        "# Test deck - pilot Nobody, 2026-01-01, source test\n"
        "# mainboard 3, sideboard 2\n"
        "2 Lightning Bolt\n"
        "1 Craw Wurm\n"
        "\n"
        "Sideboard\n"
        "2 Wear // Tear\n"
    )
    names = parse_decklist(deck)
    assert names == ["Lightning Bolt", "Craw Wurm", "Wear // Tear"]


def test_parse_decklist_deduplicates_a_name_split_across_sections(tmp_path):
    deck = tmp_path / "deck.txt"
    deck.write_text("# header\n1 Lightning Bolt\n\nSideboard\n1 Lightning Bolt\n")
    assert parse_decklist(deck) == ["Lightning Bolt"]


def test_parse_name_file_skips_blank_lines_and_comments(tmp_path):
    names_file = tmp_path / "names.txt"
    names_file.write_text("Lightning Bolt\n\n# a comment\nCraw Wurm\n")
    assert parse_name_file(names_file) == ["Lightning Bolt", "Craw Wurm"]


# -- Output formats -----------------------------------------------------------


def test_write_csv_round_trips_every_row(tmp_path):
    results = survey(["Lightning Bolt", "Craw Wurm"], tmp_path)
    stream = io.StringIO()
    write_csv(results, stream)
    stream.seek(0)
    rows = list(csv.DictReader(stream))
    assert {row["name"] for row in rows} == {"Lightning Bolt", "Craw Wurm"}
    bolt_row = next(row for row in rows if row["name"] == "Lightning Bolt")
    assert bolt_row["category"] == HANDLED


def test_write_json_includes_a_summary(tmp_path):
    results = survey(["Lightning Bolt", "Craw Wurm"], tmp_path)
    stream = io.StringIO()
    write_json(results, stream)
    payload = json.loads(stream.getvalue())
    assert len(payload["cards"]) == 2
    assert payload["summary"][HANDLED] == 1
    assert payload["summary"][NO_RULES_TEXT] == 1


def test_silent_category_is_reachable_through_the_survey_wrapper(tmp_path):
    """Sanity check that SILENT is still a real, importable category name and
    not dead code left over from a refactor - `sweep_pool`'s own SILENT is
    re-exported by `survey_cards` for callers that want to filter on it."""
    assert SILENT == "silent"


def test_a_permanents_unaudited_static_reaches_the_survey_as_its_own_category(tmp_path):
    """`scripts/sweep_pool.py` grew a fourth bucket - `static_unaudited`, a
    permanent's own static ability (CR 604.2) that no part of the sweep
    audits - so that a card nobody looked at can never be counted as a card
    with nothing to look at. It flows through the survey wrapper untouched:
    Grafdigger's Cage used to report `no_rules_text` here.

    `scripts/survey_cards.print_summary` still iterates a fixed tuple of
    categories that does not include this one, so the *table* and the CSV/JSON
    rows carry it but the human summary does not count it. That is a companion
    change owed to `survey_cards.py`, which this task does not own.
    """
    result = survey_one("Grafdigger's Cage", tmp_path)
    assert result.found
    assert result.category == "static_unaudited"
    assert result.category != NO_RULES_TEXT
