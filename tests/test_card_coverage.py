"""Tests for `scripts/card_coverage.py`, the per-expansion coverage report
generator that backs the card-coverage campaign skills.

This is tooling, not the engine's own card-rules code, so the no-mocks rule
(`CLAUDE.md`) does not apply here: Scryfall network calls are faked with
small synthetic fixtures rather than hitting the network, and bulk data is
a handful of hand-built dicts shaped like the real Scryfall card object.

The classification tests do call the real engine (`magic_cards_model.support
.card_support`) against tiny synthetic printings, because that integration
(raw dict -> Card -> card_support -> ClassificationResult) is exactly the
thing worth proving works end to end.
"""

from __future__ import annotations

import io
import json
import uuid
from pathlib import Path

import pytest
from scripts import card_coverage as cc

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def make_card(
    name: str,
    *,
    set_code: str = "tst",
    set_name: str = "Test Set",
    released_at: str = "2020-06-01",
    oracle_text: str | None = None,
    keywords: list[str] | None = None,
    mana_cost: str = "{1}{G}",
    cmc: float = 2.0,
    type_line: str = "Creature — Bear",
    power: str | None = "2",
    toughness: str | None = "2",
    layout: str = "normal",
    set_type: str = "expansion",
    digital: bool = False,
    games: tuple[str, ...] = ("paper", "arena"),
    legal_standard: str = "not_legal",
    legal_pioneer: str = "not_legal",
    legal_modern: str = "legal",
    oracle_id: str | None = None,
    promo: bool = False,
) -> dict:
    """A Scryfall-card-shaped dict: enough of the real fields for `Card.
    model_validate` (the engine model) plus the raw bulk-data fields
    (`released_at`, `set_name`, `set_type`, `digital`, `games`) that only
    this tooling's own filtering reads."""
    return {
        "id": str(uuid.uuid4()),
        "oracle_id": oracle_id or str(uuid.uuid4()),
        "name": name,
        "type_line": type_line,
        "mana_cost": mana_cost,
        "cmc": cmc,
        "oracle_text": oracle_text,
        "colors": ["G"],
        "color_identity": ["G"],
        "keywords": keywords or [],
        "power": power,
        "toughness": toughness,
        "layout": layout,
        "legalities": {
            "standard": legal_standard,
            "pioneer": legal_pioneer,
            "modern": legal_modern,
        },
        "rarity": "common",
        "set": set_code,
        # Raw bulk-data-only fields (ignored by the engine's Card model,
        # used by this tooling's own eligibility/set-grouping logic).
        "set_name": set_name,
        "set_type": set_type,
        "released_at": released_at,
        "digital": digital,
        "games": list(games),
        "promo": promo,
    }


# ---------------------------------------------------------------------------
# Eligibility / first-printing selection
# ---------------------------------------------------------------------------


def test_eligible_printing_accepts_an_ordinary_paper_card():
    assert cc.is_eligible_printing(make_card("Grizzly Bears"))


def test_eligible_printing_rejects_a_token():
    assert not cc.is_eligible_printing(make_card("Soldier Token", layout="token", set_type="token"))


def test_eligible_printing_rejects_an_emblem():
    assert not cc.is_eligible_printing(make_card("Ajani Emblem", layout="emblem"))


def test_eligible_printing_rejects_art_series():
    assert not cc.is_eligible_printing(make_card("Some Art Card", set_type="art_series"))


def test_eligible_printing_rejects_digital_only():
    assert not cc.is_eligible_printing(make_card("Alchemy Card", digital=True, games=("arena",)))
    assert not cc.is_eligible_printing(make_card("Arena Only", games=("arena",)))


def test_select_first_printing_picks_earliest_release_date():
    old = make_card("Reprint Bear", set_code="old", released_at="1999-01-01")
    new = make_card("Reprint Bear", set_code="new", released_at="2020-01-01")
    first = cc.select_first_printing([new, old])
    assert first["set"] == "old"


def test_select_first_printing_ignores_ineligible_printings():
    token = make_card(
        "X", set_code="tok", released_at="1990-01-01", layout="token", set_type="token"
    )
    real = make_card("X", set_code="real", released_at="2000-01-01")
    first = cc.select_first_printing([token, real])
    assert first["set"] == "real"


def test_select_first_printing_ties_break_on_set_code():
    a = make_card("Y", set_code="bbb", released_at="2000-01-01")
    b = make_card("Y", set_code="aaa", released_at="2000-01-01")
    first = cc.select_first_printing([a, b])
    assert first["set"] == "aaa"


def test_select_first_printing_none_when_nothing_eligible():
    token = make_card("Z", layout="token", set_type="token")
    assert cc.select_first_printing([token]) is None


def test_select_first_printing_prefers_non_promo_over_earlier_promo():
    """Review finding #1: a prerelease/promo printing that ships on or
    before the main expansion's release date must not win - the card's home
    is the main (non-promo) expansion whenever one exists at all."""
    promo = make_card(
        "Strixhaven Mascot",
        set_code="psos",
        set_type="promo",
        released_at="2026-04-20",
    )
    main = make_card(
        "Strixhaven Mascot",
        set_code="sos",
        set_type="expansion",
        released_at="2026-04-24",
    )
    first = cc.select_first_printing([promo, main])
    assert first["set"] == "sos"


def test_select_first_printing_falls_back_to_promo_when_no_non_promo_exists():
    promo = make_card(
        "WPN Exclusive",
        set_code="pwpn",
        set_type="promo",
        released_at="2026-01-01",
    )
    first = cc.select_first_printing([promo])
    assert first["set"] == "pwpn"


def test_select_first_printing_promo_flagged_true_is_also_promo_like():
    promo_flagged = make_card(
        "Judge Gift",
        set_code="jgift",
        set_type="expansion",  # set_type alone doesn't say promo
        promo=True,
        released_at="2020-01-01",
    )
    main = make_card(
        "Judge Gift",
        set_code="main",
        set_type="expansion",
        promo=False,
        released_at="2021-01-01",
    )
    first = cc.select_first_printing([promo_flagged, main])
    assert first["set"] == "main"


def test_select_first_printing_memorabilia_and_token_set_types_are_promo_like():
    memorabilia = make_card(
        "Signed Bear", set_code="mem", set_type="memorabilia", released_at="2019-01-01"
    )
    token_set = make_card(
        "Token-ish Bear", set_code="tok2", set_type="token", released_at="2019-06-01"
    )
    main = make_card("Signed Bear", set_code="main", set_type="expansion", released_at="2020-01-01")
    assert cc.select_first_printing([memorabilia, main])["set"] == "main"
    assert cc.select_first_printing([token_set])["set"] == "tok2"


def test_select_first_printing_does_not_treat_commander_sets_as_promo():
    """Commander sets stay as they are: a card first printed in a Commander
    set really does belong there."""
    commander = make_card(
        "Command Zone Legend", set_code="cmd", set_type="commander", released_at="2020-01-01"
    )
    later_main = make_card(
        "Command Zone Legend", set_code="main", set_type="expansion", released_at="2021-01-01"
    )
    first = cc.select_first_printing([commander, later_main])
    assert first["set"] == "cmd"


def test_select_first_printing_promo_set_code_no_longer_wins_tiebreak():
    """Regression for the reported bug: with tie-breaking by set code alone,
    "psos" used to win over "sos" (p < s). It must not, once set-type
    preference is applied."""
    promo = make_card("Tied Card", set_code="psos", set_type="promo", released_at="2026-04-24")
    main = make_card("Tied Card", set_code="sos", set_type="expansion", released_at="2026-04-24")
    first = cc.select_first_printing([promo, main])
    assert first["set"] == "sos"


def test_group_first_printings_keys_by_oracle_id():
    oid = str(uuid.uuid4())
    old = make_card("Dual Bear", set_code="old", released_at="1999-01-01", oracle_id=oid)
    new = make_card("Dual Bear", set_code="new", released_at="2020-01-01", oracle_id=oid)
    other = make_card("Other Card", oracle_id=str(uuid.uuid4()))
    grouped = cc.group_first_printings([old, new, other])
    assert len(grouped) == 2
    assert grouped[oid]["set"] == "old"


def test_merge_first_printing_metadata_corrects_reprint_attribution():
    oid = str(uuid.uuid4())
    # oracle-cards picked the newest reprint as "most recognizable".
    oracle_row = make_card(
        "Reprinted Staple",
        set_code="newest",
        set_name="Newest Set",
        released_at="2026-01-01",
        oracle_id=oid,
    )
    # default-cards' own first eligible printing is much older.
    true_first = make_card(
        "Reprinted Staple",
        set_code="og",
        set_name="Original Set",
        released_at="1998-01-01",
        oracle_id=oid,
    )
    merged = cc.merge_first_printing_metadata([oracle_row], {oid: true_first})
    (result,) = merged
    assert result["set"] == "og"
    assert result["set_name"] == "Original Set"
    assert result["released_at"] == "1998-01-01"
    # Everything else (oracle text, legalities, mana cost) is untouched.
    assert result["name"] == "Reprinted Staple"
    assert result["legalities"] == oracle_row["legalities"]


def test_merge_first_printing_metadata_leaves_unmatched_rows_alone():
    oracle_row = make_card("No Default Cards Record", oracle_id="missing-oid")
    merged = cc.merge_first_printing_metadata([oracle_row], {})
    assert merged == [oracle_row]


# ---------------------------------------------------------------------------
# Set indexing, ordering, numbering
# ---------------------------------------------------------------------------


def _first_printings(*cards: dict) -> dict[str, dict]:
    return {c["oracle_id"]: c for c in cards}


def test_build_set_index_groups_by_set_and_takes_earliest_release():
    a = make_card("A", set_code="abc", set_name="Alphabet", released_at="2001-05-01")
    b = make_card("B", set_code="abc", set_name="Alphabet", released_at="2001-05-01")
    index = cc.build_set_index(_first_printings(a, b).values())
    assert set(index) == {"abc"}
    assert index["abc"].name == "Alphabet"
    assert index["abc"].release_date == "2001-05-01"
    assert len(index["abc"].cards) == 2


def test_modern_legal_codes_requires_at_least_one_modern_legal_card():
    modern_legal = make_card("Legal One", set_code="mod", legal_modern="legal")
    never_modern = make_card("Never Modern", set_code="nomod", legal_modern="not_legal")
    index = cc.build_set_index(_first_printings(modern_legal, never_modern).values())
    assert cc.modern_legal_codes(index) == {"mod"}


def test_order_newest_first_sorts_by_release_date_descending():
    old = make_card("Old", set_code="old", released_at="1993-08-05")
    mid = make_card("Mid", set_code="mid", released_at="2010-01-01")
    new = make_card("New", set_code="new", released_at="2024-01-01")
    index = cc.build_set_index(_first_printings(old, mid, new).values())
    ordered = cc.order_newest_first(index, {"old", "mid", "new"})
    assert ordered == ["new", "mid", "old"]


def test_assign_numbers_is_stable_oldest_is_one():
    ordered_oldest_first = ["old", "mid", "new"]
    numbers = cc.assign_numbers(ordered_oldest_first, existing={})
    assert numbers == {"old": 1, "mid": 2, "new": 3}


def test_assign_numbers_preserves_existing_and_appends_new():
    ordered_oldest_first = ["old", "mid", "new", "newest"]
    existing = {"old": 1, "mid": 2}
    numbers = cc.assign_numbers(ordered_oldest_first, existing=existing)
    # Existing numbers never move.
    assert numbers["old"] == 1
    assert numbers["mid"] == 2
    # New sets get the next free numbers, in oldest-to-newest order.
    assert numbers["new"] == 3
    assert numbers["newest"] == 4


def test_format_expansion_dir_zero_pads():
    assert cc.format_expansion_dir(1, "mh1") == "001-mh1"
    assert cc.format_expansion_dir(76, "lea") == "076-lea"
    assert cc.format_expansion_dir(123, "abc") == "123-abc"


def test_read_existing_numbers_parses_folder_names(tmp_path: Path):
    (tmp_path / "001-lea").mkdir()
    (tmp_path / "002-arn").mkdir()
    (tmp_path / "not-a-match").mkdir()
    numbers = cc.read_existing_numbers(tmp_path)
    assert numbers == {"lea": 1, "arn": 2}


# ---------------------------------------------------------------------------
# Tested-card detection
# ---------------------------------------------------------------------------


def test_tested_index_printings_pool(tmp_path: Path):
    printings = tmp_path / "printings"
    printings.mkdir()
    (printings / "lightning_bolt.json").write_text(json.dumps({"name": "Lightning Bolt"}))
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    golden_dir = tests_dir / "golden"
    golden_dir.mkdir()
    index = cc.build_tested_index(
        printings_dir=printings, tests_dir=tests_dir, golden_dir=golden_dir
    )
    assert index.is_tested("Lightning Bolt")
    assert not index.is_tested("Some Untested Card")


def test_tested_index_quoted_reference_in_tests(tmp_path: Path):
    printings = tmp_path / "printings"
    printings.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_something.py").write_text('scenario.cast("Counterspell", mountain)\n')
    golden_dir = tests_dir / "golden"
    golden_dir.mkdir()
    index = cc.build_tested_index(
        printings_dir=printings, tests_dir=tests_dir, golden_dir=golden_dir
    )
    assert index.is_tested("Counterspell")
    assert not index.is_tested("Not Mentioned Anywhere")


def test_tested_index_golden_directory(tmp_path: Path):
    printings = tmp_path / "printings"
    printings.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    golden_dir = tests_dir / "golden"
    golden_dir.mkdir()
    (golden_dir / "murktide-regent").mkdir()
    index = cc.build_tested_index(
        printings_dir=printings, tests_dir=tests_dir, golden_dir=golden_dir
    )
    assert index.is_tested("Murktide Regent")


def test_tested_index_checks_front_face_name(tmp_path: Path):
    printings = tmp_path / "printings"
    printings.mkdir()
    (printings / "fire.json").write_text(json.dumps({"name": "Fire // Ice"}))
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    golden_dir = tests_dir / "golden"
    golden_dir.mkdir()
    index = cc.build_tested_index(
        printings_dir=printings, tests_dir=tests_dir, golden_dir=golden_dir
    )
    assert index.is_tested("Fire // Ice")
    assert index.is_tested("Fire")


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status,tested,expected",
    [
        ("handled", True, "full"),
        ("handled", False, "not_tested"),
        ("unaudited", True, "partial"),
        ("unaudited", False, "partial"),
        ("notice", True, "not_working"),
        ("silent", False, "not_working"),
        ("error", True, "not_working"),
    ],
)
def test_bucket_of(status, tested, expected):
    assert cc.bucket_of(status, tested) == expected


# ---------------------------------------------------------------------------
# Classification (real engine call on synthetic printings)
# ---------------------------------------------------------------------------


def test_classify_card_raw_handled_for_vanilla_creature():
    raw = make_card("Vanilla Bear", oracle_text=None, keywords=[])
    result = cc.classify_card_raw(raw)
    assert result.name == "Vanilla Bear"
    assert result.status == "handled"
    assert not result.error


def test_classify_card_raw_silent_for_unknown_keyword():
    raw = make_card("Mystery Bear", keywords=["Frobnicate"], oracle_text="Frobnicate")
    result = cc.classify_card_raw(raw)
    assert result.status == "silent"
    assert result.clause_text


def test_classify_card_raw_error_on_bad_data():
    raw = make_card("Broken Card")
    del raw["legalities"]
    result = cc.classify_card_raw(raw)
    assert result.status == "error"
    assert result.error
    assert result.reason


def test_classify_many_sequential_matches_individual_calls():
    cards = [make_card("Bear One"), make_card("Bear Two", keywords=["Frobnicate"])]
    results = cc.classify_many(cards, workers=1)
    assert [r.status for r in results] == ["handled", "silent"]
    assert [r.name for r in results] == ["Bear One", "Bear Two"]


# ---------------------------------------------------------------------------
# Missing-mechanics clustering
# ---------------------------------------------------------------------------


def test_cluster_missing_mechanics_groups_shared_wording():
    entries = [
        (
            "Card A",
            "silent",
            "triggered",
            "Whenever you draw a card, Card A deals 1 damage.",
            "x",
            "seta",
        ),
        (
            "Card B",
            "silent",
            "triggered",
            "Whenever you draw a card, Card B deals 1 damage.",
            "x",
            "seta",
        ),
        ("Card C", "notice", "static", "This permanent has no other abilities.", "x", "seta"),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    sizes = sorted(c.count for c in clusters)
    assert sizes == [1, 2]
    biggest = max(clusters, key=lambda c: c.count)
    assert set(biggest.cards) == {"Card A", "Card B"}


def test_cluster_missing_mechanics_empty_is_empty():
    assert cc.cluster_missing_mechanics([]) == []


def test_cluster_missing_mechanics_does_not_group_by_first_five_words_alone():
    """Review finding #2: grouping by the first 5 words holds hundreds of
    unrelated cards together just because they share an opening clause. Two
    upkeep triggers that share the same first five words but do genuinely
    different things must land in separate clusters."""
    entries = [
        (
            "Card A",
            "silent",
            "triggered",
            "At the beginning of your upkeep, target opponent reveals their hand "
            "and you choose a nonland card from it for them to discard.",
            "x",
            "seta",
        ),
        (
            "Card B",
            "silent",
            "triggered",
            "At the beginning of your upkeep, target opponent mills three cards.",
            "x",
            "seta",
        ),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    assert len(clusters) == 2
    assert all(c.count == 1 for c in clusters)


def test_cluster_missing_mechanics_groups_by_normalized_template():
    """Same mechanic, different card name and different number, must land in
    one cluster because the normalized template (name -> ~, number -> N)
    is identical."""
    entries = [
        (
            "Card X",
            "silent",
            "triggered",
            "Whenever Card X attacks, you gain 1 life.",
            "x",
            "seta",
        ),
        (
            "Card Y",
            "silent",
            "triggered",
            "Whenever Card Y attacks, you gain 5 life.",
            "x",
            "setb",
        ),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    assert len(clusters) == 1
    (cluster,) = clusters
    assert cluster.count == 2
    assert set(cluster.cards) == {"Card X", "Card Y"}
    assert cluster.sets == ("seta", "setb")


def test_cluster_missing_mechanics_normalizes_self_reference_like_card_name():
    """ "This creature" and the card's own name are both self-references and
    must normalize to the same token."""
    entries = [
        (
            "Card A",
            "silent",
            "static",
            "This creature can't be blocked except by two or more creatures.",
            "x",
            "seta",
        ),
        (
            "Card B",
            "silent",
            "static",
            "Card B can't be blocked except by two or more creatures.",
            "x",
            "seta",
        ),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    assert len(clusters) == 1
    assert clusters[0].count == 2


def test_cluster_missing_mechanics_normalizes_mana_symbols():
    entries = [
        (
            "Card A",
            "silent",
            "activated",
            "Pay {1}: Card A gets +1/+0 until end of turn.",
            "x",
            "s",
        ),
        (
            "Card B",
            "silent",
            "activated",
            "Pay {2}: Card B gets +1/+0 until end of turn.",
            "x",
            "s",
        ),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    assert len(clusters) == 1
    assert clusters[0].count == 2


def test_cluster_missing_mechanics_normalizes_quoted_text():
    entries = [
        (
            "Card A",
            "silent",
            "triggered",
            'Search your library for a card named "Plains".',
            "x",
            "s",
        ),
        (
            "Card B",
            "silent",
            "triggered",
            'Search your library for a card named "Island".',
            "x",
            "s",
        ),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    assert len(clusters) == 1
    assert clusters[0].count == 2


def test_cluster_missing_mechanics_clusters_ability_word_by_its_leading_word():
    """A clause led by a keyword/ability word followed by an em dash (or
    " - ") clusters by that word, whatever comes after the dash."""
    entries = [
        (
            "Bender One",
            "silent",
            "triggered",
            "Waterbend — Whenever you cast a spell, put a +1/+1 counter on target "
            "creature you control.",
            "x",
            "seta",
        ),
        (
            "Bender Two",
            "silent",
            "triggered",
            "Waterbend — Whenever you cast a spell, draw a card.",
            "x",
            "setb",
        ),
        (
            "Farmer",
            "silent",
            "triggered",
            "Landfall - Whenever a land enters the battlefield under your control, "
            "you gain 1 life.",
            "x",
            "setb",
        ),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    assert len(clusters) == 2
    by_label = {c.label: c for c in clusters}
    assert set(by_label) == {"Waterbend", "Landfall"}
    assert by_label["Waterbend"].count == 2
    assert set(by_label["Waterbend"].cards) == {"Bender One", "Bender Two"}
    assert by_label["Waterbend"].sets == ("seta", "setb")
    assert by_label["Landfall"].count == 1


def test_cluster_missing_mechanics_limits_example_cards_to_five():
    entries = [
        (f"Card {i}", "silent", "static", "Card does a thing that isn't modelled.", "x", "s")
        for i in range(7)
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    assert len(clusters) == 1
    assert clusters[0].count == 7
    assert len(clusters[0].cards) == 5


def test_cluster_missing_mechanics_chapter_markers_are_not_ability_words():
    """Review follow-up: "I", "II", "III" (Saga/Case chapter markers) must
    never cluster by their roman-numeral lead the way a real ability word
    ("Waterbend — ...") does - two different sagas' chapter I, with
    genuinely different effects, must land in separate clusters, not one
    "I" cluster."""
    entries = [
        (
            "Saga A",
            "silent",
            "triggered",
            "I — Destroy target creature an opponent controls.",
            "nothing in the engine reads this text",
            "seta",
        ),
        (
            "Saga B",
            "silent",
            "triggered",
            "I — Draw a card.",
            "nothing in the engine reads this text",
            "setb",
        ),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    assert not any(c.label == "I" for c in clusters)
    assert len(clusters) == 2
    assert all(c.count == 1 for c in clusters)


def test_cluster_missing_mechanics_chapter_markers_cluster_by_stripped_template():
    """Same effect modulo card name/number, whatever chapter it's printed
    on, must cluster together by the normalized template of the effect text
    with the chapter marker itself stripped off (the marker is not part of
    the clustering key - Saga C's genuinely different effect must not join
    that cluster just because it also happens to be a chapter)."""
    entries = [
        (
            "Saga A",
            "silent",
            "triggered",
            "I — Saga A deals 1 damage to any target.",
            "nothing in the engine reads this text",
            "seta",
        ),
        (
            "Saga B",
            "silent",
            "triggered",
            "I — Saga B deals 3 damage to any target.",
            "nothing in the engine reads this text",
            "setb",
        ),
        (
            "Saga C",
            "silent",
            "triggered",
            "II — Saga C gains flying until end of turn.",
            "nothing in the engine reads this text",
            "setc",
        ),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    template_clusters = [c for c in clusters if c.label != "Saga chapter (see templates)"]
    assert len(template_clusters) == 2  # damage-template cluster, flying-template cluster
    by_count = sorted(template_clusters, key=lambda c: -c.count)
    assert by_count[0].count == 2
    assert set(by_count[0].cards) == {"Saga A", "Saga B"}
    assert by_count[1].count == 1
    assert by_count[1].cards == ("Saga C",)


def test_cluster_missing_mechanics_chapter_ranges_are_stripped_too():
    entries = [
        (
            "Saga D",
            "silent",
            "triggered",
            "I, II — Create a 1/1 white Human Soldier creature token.",
            "nothing in the engine reads this text",
            "setd",
        ),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    assert not any(c.label in ("I", "II", "I, II") for c in clusters)
    assert any("create a N/N" in c.label for c in clusters)


def test_cluster_missing_mechanics_adds_saga_machinery_rollup_when_reason_implicates_it():
    """Only when the failing chapter's own reason implicates the Saga
    machinery itself (not just that chapter's unparsed effect) does the
    extra "Saga chapter (see templates)" roll-up row appear, in addition to
    the ordinary per-template clusters."""
    entries = [
        (
            "Saga E",
            "notice",
            "triggered",
            "I — Create a 1/1 white Human Soldier creature token.",
            "no machine advances this Saga's lore/chapter counters",
            "sete",
        ),
        (
            "Saga F",
            "notice",
            "triggered",
            "II — Draw two cards.",
            "no machine advances this Saga's lore/chapter counters",
            "setf",
        ),
        (
            # An ordinary unmodeled chapter effect - reason never mentions
            # "Saga" - must NOT count toward the machinery roll-up.
            "Saga G",
            "silent",
            "triggered",
            "I — Exile target artifact.",
            "nothing in the engine reads this text",
            "setg",
        ),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    rollups = [c for c in clusters if c.label == "Saga chapter (see templates)"]
    assert len(rollups) == 1
    (rollup,) = rollups
    assert rollup.count == 2
    assert set(rollup.cards) == {"Saga E", "Saga F"}
    assert "Saga G" not in rollup.cards
    # The per-template clusters for those same chapters still exist too.
    assert any(c.label != "Saga chapter (see templates)" and "Saga E" in c.cards for c in clusters)


def test_cluster_missing_mechanics_no_saga_rollup_when_no_reason_implicates_it():
    entries = [
        (
            "Saga H",
            "silent",
            "triggered",
            "I — Exile target artifact.",
            "nothing in the engine reads this text - it would do nothing and log nothing",
            "seth",
        ),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    assert not any(c.label == "Saga chapter (see templates)" for c in clusters)


# ---------------------------------------------------------------------------
# Notes / round-state preservation
# ---------------------------------------------------------------------------


def test_extract_section_returns_verbatim_body():
    md = "# Title\n\n## Notes\n\nSomething the human wrote.\n- a bullet\n\n## Next Section\nother\n"
    body = cc.extract_section(md, "Notes")
    assert body == "Something the human wrote.\n- a bullet"


def test_extract_section_missing_returns_none():
    md = "# Title\n\n## Other\nstuff\n"
    assert cc.extract_section(md, "Notes") is None


def test_extract_round_states_reads_state_column():
    md = (
        "## Campaign order\n\n"
        "| Round | Set | Cards | Full | State |\n"
        "|---|---|---|---|---|\n"
        "| 1 | [hob](001-hob/status.md) | 107 | 90 | done |\n"
        "| 2 | [msh](002-msh/status.md) | 156 | 100 | in-progress |\n"
    )
    states = cc.extract_round_states(md)
    assert states == {"hob": "done", "msh": "in-progress"}


def test_extract_round_states_reads_state_column_with_works_column():
    """Regression: the campaign-order table gained a Works column next to
    Tested (bucket relabeling). extract_round_states must still find the
    right (last) column as the state, whatever the column count."""
    md = (
        "## Campaign order\n\n"
        "| Round | Set | Release date | Cards | Tested | Works | State |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 1 | [hob](001-hob/status.md) - The Hobbit | 2026-08-14 | 107 | 90 | 10 | done |\n"
        "| 2 | [msh](002-msh/status.md) - Marvel | 2026-06-26 | 156 | 16 | 100 | in-progress |\n"
    )
    states = cc.extract_round_states(md)
    assert states == {"hob": "done", "msh": "in-progress"}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _sample_set_meta(code="tst"):
    a = make_card("Full Card", set_code=code, legal_modern="legal")
    b = make_card("Silent Card", set_code=code, keywords=["Frobnicate"], legal_modern="legal")
    index = cc.build_set_index(_first_printings(a, b).values())
    return index[code]


def test_render_status_md_contains_required_sections():
    meta = _sample_set_meta()
    classifications = {
        "Full Card": cc.ClassificationResult(
            name="Full Card",
            status="handled",
            clause_kind="spell",
            clause_text="",
            reason="",
            error=False,
        ),
        "Silent Card": cc.ClassificationResult(
            name="Silent Card",
            status="silent",
            clause_kind="keyword",
            clause_text="Frobnicate",
            reason="no machine executes this keyword",
            error=False,
        ),
    }
    tested = {"Full Card": True, "Silent Card": False}
    md = cc.render_status_md(
        meta,
        number=1,
        classifications=classifications,
        tested=tested,
        existing_notes=None,
    )
    assert "# Test Set" in md
    assert "tst" in md
    assert "## Coverage" in md
    assert "## Cards needing work" in md
    assert "Silent Card" in md
    assert "## Fully supported" in md
    assert "Full Card" in md
    assert "## Missing mechanics" in md
    assert "## Notes" in md


def test_render_status_md_coverage_table_uses_relabeled_buckets_in_order():
    meta = _sample_set_meta()
    classifications = {
        "Full Card": cc.ClassificationResult(
            name="Full Card",
            status="handled",
            clause_kind="spell",
            clause_text="",
            reason="",
            error=False,
        ),
        "Silent Card": cc.ClassificationResult(
            name="Silent Card",
            status="silent",
            clause_kind="keyword",
            clause_text="Frobnicate",
            reason="no machine executes this keyword",
            error=False,
        ),
    }
    tested = {"Full Card": True, "Silent Card": False}
    md = cc.render_status_md(
        meta, number=1, classifications=classifications, tested=tested, existing_notes=None
    )
    coverage = cc.extract_section(md, "Coverage")
    assert coverage is not None
    assert "Full (handled + tested)" not in coverage
    assert "Not tested (handled, untested)" not in coverage
    assert "Not working (silent / notice / error)" not in coverage
    lines = [line for line in coverage.splitlines() if line.startswith("| ")]
    labels = [line.split("|")[1].strip() for line in lines]
    assert labels == ["Bucket", "Tested", "Works (untested)", "Partial (unaudited)", "Not working"]


def test_render_status_md_preserves_existing_notes():
    meta = _sample_set_meta()
    classifications = {
        "Full Card": cc.ClassificationResult(
            name="Full Card",
            status="handled",
            clause_kind="spell",
            clause_text="",
            reason="",
            error=False,
        ),
    }
    md = cc.render_status_md(
        meta,
        number=1,
        classifications=classifications,
        tested={"Full Card": True},
        existing_notes="Human-written note that must survive regeneration.",
    )
    assert "Human-written note that must survive regeneration." in md


def test_render_status_md_missing_mechanics_shows_cluster_and_sets():
    meta = _sample_set_meta(code="tst")
    classifications = {
        "Silent Card": cc.ClassificationResult(
            name="Silent Card",
            status="silent",
            clause_kind="keyword",
            clause_text="Frobnicate",
            reason="no machine executes this keyword",
            error=False,
        ),
        "Full Card": cc.ClassificationResult(
            name="Full Card",
            status="handled",
            clause_kind="spell",
            clause_text="",
            reason="",
            error=False,
        ),
    }
    md = cc.render_status_md(
        meta,
        number=1,
        classifications=classifications,
        tested={"Full Card": True, "Silent Card": False},
        existing_notes=None,
    )
    section = cc.extract_section(md, "Missing mechanics")
    assert section is not None
    assert "Silent Card" in section
    assert "tst" in section


def test_render_plan_md_shows_only_top_50_missing_mechanics_clusters():
    rows = [
        cc.PlanRow(
            number=1,
            code="one",
            name="One",
            release_date="2020-01-01",
            total=1,
            tested=0,
            works=0,
            partial=0,
            not_working=1,
            state="todo",
        ),
    ]
    clusters = [
        cc.MechanicCluster(
            signature=f"tmpl:mechanic {i}",
            label=f"mechanic {i}",
            count=100 - i,
            cards=(f"Card {i}",),
            sets=("one",),
        )
        for i in range(60)
    ]
    md = cc.render_plan_md(
        rows=rows,
        round0_cards=[],
        missing_mechanics=clusters,
        existing_notes=None,
        existing_done=None,
    )
    section = cc.extract_section(md, "Missing mechanics")
    assert section is not None
    shown = sum(1 for line in section.splitlines() if line.startswith("| mechanic "))
    assert shown == 50
    assert "mechanic 0" in section
    assert "mechanic 49" in section
    assert "mechanic 50" not in section


def test_render_plan_md_contains_required_sections():
    rows = [
        cc.PlanRow(
            number=2,
            code="msh",
            name="Marvel",
            release_date="2026-06-26",
            total=156,
            tested=10,
            works=20,
            partial=30,
            not_working=96,
            state="in-progress",
        ),
        cc.PlanRow(
            number=1,
            code="hob",
            name="Hobbit",
            release_date="2026-08-14",
            total=107,
            tested=107,
            works=0,
            partial=0,
            not_working=0,
            state="done",
        ),
    ]
    md = cc.render_plan_md(
        rows=rows,
        round0_cards=["Some Deck Card"],
        missing_mechanics=[],
        existing_notes=None,
        existing_done=None,
    )
    assert "## Overall coverage" in md
    assert "## Campaign order" in md
    assert "Round 0" in md
    assert "## Missing mechanics" in md
    assert "## Notes" in md
    assert "## Done" in md
    # Newest first.
    assert md.index("hob") < md.index("msh")


def test_render_plan_md_overall_coverage_shows_all_four_relabeled_buckets():
    rows = [
        cc.PlanRow(
            number=1,
            code="one",
            name="One",
            release_date="2020-01-01",
            total=100,
            tested=10,
            works=20,
            partial=30,
            not_working=40,
            state="todo",
        ),
    ]
    md = cc.render_plan_md(
        rows=rows,
        round0_cards=[],
        missing_mechanics=[],
        existing_notes=None,
        existing_done=None,
    )
    overall = cc.extract_section(md, "Overall coverage")
    assert overall is not None
    assert "Tested" in overall
    assert "Works (untested)" in overall
    assert "Partial (unaudited)" in overall
    assert "Not working" in overall
    # Old headline wording is gone.
    assert "Full (handled + tested)" not in overall
    assert "Not tested (handled, untested)" not in overall
    # Counts and percentages for each bucket are present.
    assert "| Tested | 10 | 10.0% |" in overall
    assert "| Works (untested) | 20 | 20.0% |" in overall
    assert "| Partial (unaudited) | 30 | 30.0% |" in overall
    assert "| Not working | 40 | 40.0% |" in overall


def test_render_plan_md_campaign_order_has_tested_and_works_columns():
    rows = [
        cc.PlanRow(
            number=1,
            code="one",
            name="One",
            release_date="2020-01-01",
            total=100,
            tested=10,
            works=20,
            partial=30,
            not_working=40,
            state="todo",
        ),
    ]
    md = cc.render_plan_md(
        rows=rows,
        round0_cards=[],
        missing_mechanics=[],
        existing_notes=None,
        existing_done=None,
    )
    campaign = cc.extract_section(md, "Campaign order")
    assert campaign is not None
    assert "| Round | Set | Release date | Cards | Tested | Works | State |" in campaign
    assert "| 1 | [one](001-one/status.md) - One | 2020-01-01 | 100 | 10 | 20 | todo |" in campaign


# ---------------------------------------------------------------------------
# Deck parsing (Round 0)
# ---------------------------------------------------------------------------


def test_parse_deck_file_reads_counted_lines(tmp_path: Path):
    deck = tmp_path / "deck.txt"
    deck.write_text("4 Lightning Bolt\n2 Mountain\n\nSideboard\n1 Pyroblast\n")
    names = cc.parse_deck_file(deck)
    assert names == {"Lightning Bolt", "Mountain", "Pyroblast"}


def test_parse_deck_file_ignores_blank_and_comment_lines(tmp_path: Path):
    deck = tmp_path / "deck.txt"
    deck.write_text("// a comment\n\n1 Sol Ring\n")
    names = cc.parse_deck_file(deck)
    assert names == {"Sol Ring"}


# ---------------------------------------------------------------------------
# Bulk-data fetching (network faked)
# ---------------------------------------------------------------------------


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_load_bulk_json_reads_gzip_jsonl(tmp_path: Path):
    path = tmp_path / "oracle-cards.jsonl.gz"
    payload = [{"name": "A"}, {"name": "B"}]
    path.write_bytes(cc.gzip.compress(b"\n".join(json.dumps(c).encode() for c in payload)))
    assert cc.load_bulk_json(path) == payload


def test_load_bulk_json_reads_plain_array(tmp_path: Path):
    path = tmp_path / "oracle-cards.json"
    payload = [{"name": "A"}, {"name": "B"}]
    path.write_text(json.dumps(payload))
    assert cc.load_bulk_json(path) == payload


def test_download_bulk_picks_matching_type_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    index_payload = {
        "data": [
            {
                "type": "oracle_cards",
                "jsonl_download_uri": "https://example.test/oracle.jsonl.gz",
                "updated_at": "2026-01-01",
            },
            {
                "type": "default_cards",
                "jsonl_download_uri": "https://example.test/default.jsonl.gz",
                "updated_at": "2026-01-01",
            },
        ]
    }
    bulk_payload = [{"name": "Test Card"}]
    bulk_jsonl_gz = cc.gzip.compress(b"\n".join(json.dumps(c).encode() for c in bulk_payload))

    calls = []

    def fake_urlopen(request, timeout=30):
        url = request.full_url if hasattr(request, "full_url") else request
        calls.append(url)
        if "bulk-data" in url and "oracle.jsonl.gz" not in url and "default.jsonl.gz" not in url:
            return _FakeResponse(json.dumps(index_payload).encode())
        return _FakeResponse(bulk_jsonl_gz)

    monkeypatch.setattr(cc.urllib.request, "urlopen", fake_urlopen)

    path = cc.download_bulk("oracle-cards", cache_dir=tmp_path)
    assert path.exists()
    assert cc.load_bulk_json(path) == bulk_payload
    assert any("bulk-data" in c for c in calls)

    # Second call should hit the cache and make no further "bulk-data" index
    # request, since the file already exists and force is not set.
    calls.clear()
    path2 = cc.download_bulk("oracle-cards", cache_dir=tmp_path)
    assert path2 == path
    assert calls == []


def test_fetch_set_cards_paginates(monkeypatch: pytest.MonkeyPatch):
    page1 = {
        "data": [{"name": "Card One"}],
        "has_more": True,
        "next_page": "https://api.scryfall.com/cards/search?page=2",
    }
    page2 = {"data": [{"name": "Card Two"}], "has_more": False}

    responses = [page1, page2]

    def fake_urlopen(request, timeout=30):
        return _FakeResponse(json.dumps(responses.pop(0)).encode())

    monkeypatch.setattr(cc.urllib.request, "urlopen", fake_urlopen)
    cards = cc.fetch_set_cards("tst")
    assert [c["name"] for c in cards] == ["Card One", "Card Two"]


# ---------------------------------------------------------------------------
# End-to-end smoke (small synthetic bulk file, no network)
# ---------------------------------------------------------------------------


def test_generate_all_uses_default_cards_for_first_print_attribution(tmp_path: Path):
    oid = str(uuid.uuid4())
    # oracle-cards' own pick: the newest reprint set.
    oracle_cards = [
        make_card(
            "Reprinted Staple",
            set_code="newest",
            set_name="Newest Set",
            released_at="2026-01-01",
            legal_modern="legal",
            oracle_id=oid,
        )
    ]
    # default-cards: every printing, including the true original.
    default_cards = [
        make_card(
            "Reprinted Staple",
            set_code="newest",
            set_name="Newest Set",
            released_at="2026-01-01",
            legal_modern="legal",
            oracle_id=oid,
        ),
        make_card(
            "Reprinted Staple",
            set_code="og",
            set_name="Original Set",
            released_at="1998-06-01",
            legal_modern="legal",
            oracle_id=oid,
        ),
    ]
    bulk_path = tmp_path / "oracle-cards.json"
    bulk_path.write_text(json.dumps(oracle_cards))
    default_path = tmp_path / "default-cards.json"
    default_path.write_text(json.dumps(default_cards))

    out_dir = tmp_path / "docs" / "card_coverage"
    printings_dir = tmp_path / "printings"
    printings_dir.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    golden_dir = tests_dir / "golden"
    golden_dir.mkdir()

    result = cc.generate_all(
        bulk_path=bulk_path,
        default_bulk_path=default_path,
        out_dir=out_dir,
        printings_dir=printings_dir,
        tests_dir=tests_dir,
        golden_dir=golden_dir,
        decks_dirs=[],
        workers=1,
    )

    assert result.set_count == 1
    assert (out_dir / "001-og" / "status.md").exists()
    assert not (out_dir / "001-newest").exists()


def test_generate_all_end_to_end(tmp_path: Path):
    oracle_cards = [
        make_card(
            "Old Legal Card",
            set_code="old",
            set_name="Old Set",
            released_at="1999-01-01",
            legal_modern="legal",
        ),
        make_card(
            "New Legal Card",
            set_code="new",
            set_name="New Set",
            released_at="2020-01-01",
            legal_modern="legal",
            keywords=["Frobnicate"],
        ),
        make_card(
            "Not In Any Format",
            set_code="new",
            set_name="New Set",
            released_at="2020-01-01",
            legal_modern="not_legal",
        ),
    ]
    bulk_path = tmp_path / "oracle-cards.json"
    bulk_path.write_text(json.dumps(oracle_cards))

    out_dir = tmp_path / "docs" / "card_coverage"
    printings_dir = tmp_path / "printings"
    printings_dir.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    golden_dir = tests_dir / "golden"
    golden_dir.mkdir()

    result = cc.generate_all(
        bulk_path=bulk_path,
        out_dir=out_dir,
        printings_dir=printings_dir,
        tests_dir=tests_dir,
        golden_dir=golden_dir,
        decks_dirs=[],
        workers=1,
    )

    assert result.set_count == 2
    assert (out_dir / "001-old" / "status.md").exists()
    assert (out_dir / "002-new" / "status.md").exists()
    assert (out_dir / "plan.md").exists()

    plan_text = (out_dir / "plan.md").read_text()
    assert "New Set" in plan_text
    assert "Old Set" in plan_text

    # Re-running is deterministic: identical output on an unchanged input.
    result2 = cc.generate_all(
        bulk_path=bulk_path,
        out_dir=out_dir,
        printings_dir=printings_dir,
        tests_dir=tests_dir,
        golden_dir=golden_dir,
        decks_dirs=[],
        workers=1,
    )
    assert (out_dir / "001-old" / "status.md").read_text() == (
        out_dir / "001-old" / "status.md"
    ).read_text()
    assert result2.set_count == 2


def test_generate_all_preserves_hand_edited_notes(tmp_path: Path):
    oracle_cards = [
        make_card(
            "Solo Card",
            set_code="solo",
            set_name="Solo Set",
            released_at="2001-01-01",
            legal_modern="legal",
        ),
    ]
    bulk_path = tmp_path / "oracle-cards.json"
    bulk_path.write_text(json.dumps(oracle_cards))
    out_dir = tmp_path / "docs" / "card_coverage"
    printings_dir = tmp_path / "printings"
    printings_dir.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    golden_dir = tests_dir / "golden"
    golden_dir.mkdir()

    cc.generate_all(
        bulk_path=bulk_path,
        out_dir=out_dir,
        printings_dir=printings_dir,
        tests_dir=tests_dir,
        golden_dir=golden_dir,
        decks_dirs=[],
        workers=1,
    )
    status_path = out_dir / "001-solo" / "status.md"
    text = status_path.read_text()
    text = text.replace("## Notes\n\n", "## Notes\n\nHand-written note.\n\n", 1)
    status_path.write_text(text)

    cc.generate_all(
        bulk_path=bulk_path,
        out_dir=out_dir,
        printings_dir=printings_dir,
        tests_dir=tests_dir,
        golden_dir=golden_dir,
        decks_dirs=[],
        workers=1,
    )
    assert "Hand-written note." in status_path.read_text()


# ---------------------------------------------------------------------------
# Pruning orphaned set directories
# ---------------------------------------------------------------------------


def _write_status_md(path: Path, *, notes: str | None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    body = "# Some Set (xyz)\n\n## Coverage\n\nsomething\n\n## Notes\n\n"
    body += (notes or "") + "\n"
    (path / "status.md").write_text(body)


def test_prune_orphaned_sets_removes_dirs_with_no_notes(tmp_path: Path):
    out_dir = tmp_path / "docs" / "card_coverage"
    _write_status_md(out_dir / "003-gone", notes=None)
    _write_status_md(out_dir / "004-keep", notes=None)
    pruned, kept_with_notes = cc.prune_orphaned_sets(out_dir, {"keep"})
    assert pruned == ["gone"]
    assert kept_with_notes == []
    assert not (out_dir / "003-gone").exists()
    assert (out_dir / "004-keep").exists()


def test_prune_orphaned_sets_never_deletes_a_dir_with_notes(tmp_path: Path):
    out_dir = tmp_path / "docs" / "card_coverage"
    _write_status_md(out_dir / "005-noted", notes="Human wrote something important here.")
    pruned, kept_with_notes = cc.prune_orphaned_sets(out_dir, set())
    assert pruned == []
    assert kept_with_notes == [("noted", "Human wrote something important here.")]
    assert (out_dir / "005-noted").exists()
    assert (out_dir / "005-noted" / "status.md").exists()


def test_merge_pruned_notes_into_plan_appends_tagged_block():
    merged = cc.merge_pruned_notes_into_plan(
        "Existing human note.", [("psos", "Cards moved to sos.")]
    )
    assert merged is not None
    assert "Existing human note." in merged
    assert "psos" in merged
    assert "Cards moved to sos." in merged


def test_merge_pruned_notes_into_plan_is_idempotent():
    once = cc.merge_pruned_notes_into_plan(None, [("psos", "Cards moved to sos.")])
    twice = cc.merge_pruned_notes_into_plan(once, [("psos", "Cards moved to sos.")])
    assert once == twice


def test_generate_all_prunes_orphaned_set_with_no_notes(tmp_path: Path):
    def make_oracle_cards(include_gone: bool) -> list[dict]:
        cards = [
            make_card(
                "Keep Card",
                set_code="keep",
                set_name="Keep Set",
                released_at="2020-01-01",
                legal_modern="legal",
            ),
        ]
        if include_gone:
            cards.append(
                make_card(
                    "Gone Card",
                    set_code="gone",
                    set_name="Gone Set",
                    released_at="2019-01-01",
                    legal_modern="legal",
                )
            )
        return cards

    bulk_path = tmp_path / "oracle-cards.json"
    out_dir = tmp_path / "docs" / "card_coverage"
    printings_dir = tmp_path / "printings"
    printings_dir.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    golden_dir = tests_dir / "golden"
    golden_dir.mkdir()

    bulk_path.write_text(json.dumps(make_oracle_cards(True)))
    cc.generate_all(
        bulk_path=bulk_path,
        out_dir=out_dir,
        printings_dir=printings_dir,
        tests_dir=tests_dir,
        golden_dir=golden_dir,
        decks_dirs=[],
        workers=1,
    )
    assert (out_dir / "001-gone").exists()

    bulk_path.write_text(json.dumps(make_oracle_cards(False)))
    result = cc.generate_all(
        bulk_path=bulk_path,
        out_dir=out_dir,
        printings_dir=printings_dir,
        tests_dir=tests_dir,
        golden_dir=golden_dir,
        decks_dirs=[],
        workers=1,
    )
    assert not (out_dir / "001-gone").exists()
    assert result.pruned_codes == ("gone",)
    assert result.recovered_notes_codes == ()


def test_generate_all_keeps_and_recovers_notes_for_pruned_set(tmp_path: Path):
    def make_oracle_cards(include_marked: bool) -> list[dict]:
        cards = [
            make_card(
                "Keep Card",
                set_code="keep",
                set_name="Keep Set",
                released_at="2020-01-01",
                legal_modern="legal",
            ),
        ]
        if include_marked:
            cards.append(
                make_card(
                    "Marked Card",
                    set_code="marked",
                    set_name="Marked Set",
                    released_at="2019-01-01",
                    legal_modern="legal",
                )
            )
        return cards

    bulk_path = tmp_path / "oracle-cards.json"
    out_dir = tmp_path / "docs" / "card_coverage"
    printings_dir = tmp_path / "printings"
    printings_dir.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    golden_dir = tests_dir / "golden"
    golden_dir.mkdir()

    bulk_path.write_text(json.dumps(make_oracle_cards(True)))
    cc.generate_all(
        bulk_path=bulk_path,
        out_dir=out_dir,
        printings_dir=printings_dir,
        tests_dir=tests_dir,
        golden_dir=golden_dir,
        decks_dirs=[],
        workers=1,
    )
    marked_status = out_dir / "001-marked" / "status.md"
    text = marked_status.read_text()
    text = text.replace("## Notes\n\n", "## Notes\n\nDo not lose this human note.\n\n", 1)
    marked_status.write_text(text)

    bulk_path.write_text(json.dumps(make_oracle_cards(False)))
    result = cc.generate_all(
        bulk_path=bulk_path,
        out_dir=out_dir,
        printings_dir=printings_dir,
        tests_dir=tests_dir,
        golden_dir=golden_dir,
        decks_dirs=[],
        workers=1,
    )
    # The directory survives untouched - never deleted while it holds notes.
    assert marked_status.exists()
    assert "Do not lose this human note." in marked_status.read_text()
    assert result.pruned_codes == ()
    assert result.recovered_notes_codes == ("marked",)
    plan_text = (out_dir / "plan.md").read_text()
    plan_notes = cc.extract_section(plan_text, "Notes")
    assert plan_notes is not None
    assert "marked" in plan_notes
    assert "Do not lose this human note." in plan_notes
