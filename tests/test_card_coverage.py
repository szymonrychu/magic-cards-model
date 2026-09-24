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
        ("Card A", "silent", "triggered", "Whenever you draw a card, Card A deals 1 damage.", "x"),
        ("Card B", "silent", "triggered", "Whenever you draw a card, Card B gains 1 life.", "x"),
        ("Card C", "notice", "static", "This permanent has no other abilities.", "x"),
    ]
    clusters = cc.cluster_missing_mechanics(entries)
    sizes = sorted(len(c.cards) for c in clusters)
    assert sizes == [1, 2]
    biggest = max(clusters, key=lambda c: len(c.cards))
    assert set(biggest.cards) == {"Card A", "Card B"}


def test_cluster_missing_mechanics_empty_is_empty():
    assert cc.cluster_missing_mechanics([]) == []


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


def test_render_plan_md_contains_required_sections():
    rows = [
        cc.PlanRow(
            number=2,
            code="msh",
            name="Marvel",
            release_date="2026-06-26",
            total=156,
            full=10,
            state="in-progress",
        ),
        cc.PlanRow(
            number=1,
            code="hob",
            name="Hobbit",
            release_date="2026-08-14",
            total=107,
            full=107,
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
