"""Tests for `scripts/fetch_metagame.py`, the spellslinger metagame-snapshot
fetcher that backs `docs/card_coverage/metagame.json` (Round 0 of the
card-coverage campaign).

This is tooling, not the engine's own card-rules code, so the no-mocks rule
(`CLAUDE.md`) does not apply: the MCP transport is faked with small,
trimmed real responses recorded under `tests/fixtures/metagame/` rather than
hitting the network.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from scripts import fetch_metagame as fm

FIXTURES = Path(__file__).parent / "fixtures" / "metagame"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# Fake transport
# ---------------------------------------------------------------------------


class FakeTransport:
    """A `fm.Transport` whose `call` looks up a canned response by
    `(tool, sorted(arguments))` - deterministic and easy to script per test,
    unlike a queue that depends on call order."""

    def __init__(self, responses: dict[tuple[str, tuple[tuple[str, Any], ...]], Any]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call(self, tool: str, **arguments: Any) -> Any:
        self.calls.append((tool, arguments))
        key = (tool, tuple(sorted(arguments.items())))
        if key not in self._responses:
            raise AssertionError(f"unscripted call: {tool}({arguments!r})")
        return self._responses[key]


def _key(tool: str, **kwargs: Any) -> tuple[str, tuple[tuple[str, Any], ...]]:
    return (tool, tuple(sorted(kwargs.items())))


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------


def test_window_days_is_inclusive_of_both_ends():
    days = fm.window_days(date(2026, 9, 27), days=30)
    assert len(days) == 31
    assert days[0] == "2026-08-28"
    assert days[-1] == "2026-09-27"


# ---------------------------------------------------------------------------
# Merging by canonical_name
# ---------------------------------------------------------------------------


def test_merge_archetypes_sums_deck_count_across_ids_sharing_a_name():
    archetypes = _load("statistics_archetypes_modern.json")
    merges = fm.merge_archetypes(archetypes)
    by_name = {m.canonical_name: m for m in merges}
    assert by_name["broodscale bloodchief"].deck_count == 260 + 110
    assert set(by_name["broodscale bloodchief"].ids) == {
        "71762286-6941-4b81-94cc-c1df4b742066",
        "b535c0d2-d346-458f-8c83-ec4ca6f20580",
    }
    assert by_name["esper blink"].deck_count == 124


def test_merge_archetypes_top_id_is_the_highest_deck_count():
    archetypes = _load("statistics_archetypes_modern.json")
    merges = fm.merge_archetypes(archetypes)
    (merge,) = [m for m in merges if m.canonical_name == "broodscale bloodchief"]
    assert merge.top_id == "71762286-6941-4b81-94cc-c1df4b742066"


def test_qualifying_archetypes_filters_by_min_decks():
    archetypes = _load("statistics_archetypes_modern.json")
    merges = fm.merge_archetypes(archetypes)
    qualifying = fm.qualifying_archetypes(merges, min_decks=200)
    assert [m.canonical_name for m in qualifying] == ["broodscale bloodchief"]
    qualifying_low_bar = fm.qualifying_archetypes(merges, min_decks=20)
    assert {m.canonical_name for m in qualifying_low_bar} == {
        "broodscale bloodchief",
        "esper blink",
    }


# ---------------------------------------------------------------------------
# Deck enumeration: primary + secondary, dedup, truncation
# ---------------------------------------------------------------------------


def _broodscale_merge() -> fm.ArchetypeMerge:
    archetypes = _load("statistics_archetypes_modern.json")
    (merge,) = [
        m for m in fm.merge_archetypes(archetypes) if m.canonical_name == "broodscale bloodchief"
    ]
    return merge


def test_enumerate_archetype_decks_primary_only_dedupes_by_pilot_and_date():
    merge = _broodscale_merge()
    decks_page = _load("statistics_decks_broodscale_bloodchief.json")
    responses = {
        _key(
            "statistics_decks",
            format="modern",
            archetype_name="broodscale bloodchief",
            date_from="2026-09-22",
            date_to="2026-09-22",
            limit=5000,
            include_cards="names_only",
        ): decks_page,
    }
    # Every other day in the window: no decks that day.
    for day in fm.window_days(date(2026, 9, 22), days=30):
        if day == "2026-09-22":
            continue
        responses[
            _key(
                "statistics_decks",
                format="modern",
                archetype_name="broodscale bloodchief",
                date_from=day,
                date_to=day,
                limit=5000,
                include_cards="names_only",
            )
        ] = []
    transport = FakeTransport(responses)
    client = fm.SpellslingerClient(transport)
    decks = fm.enumerate_archetype_decks(
        client,
        format="modern",
        merge=fm.ArchetypeMerge(
            canonical_name="broodscale bloodchief",
            ids=(merge.top_id,),
            deck_count=2,
            top_id=merge.top_id,
        ),
        days=fm.window_days(date(2026, 9, 22), days=30),
    )
    assert len(decks) == 2
    assert ("danro", "2026-09-22T00:00:00Z") in decks
    assert ("someoneelse", "2026-09-22T00:00:00Z") in decks


def test_enumerate_archetype_decks_secondary_reaches_other_ids_and_dedupes():
    merge = _broodscale_merge()
    primary_page = _load("statistics_decks_broodscale_bloodchief.json")
    whole_format_page = _load("statistics_decks_whole_format_day.json")
    by_id_deck = _load("statistics_decks_by_id.json")
    days = fm.window_days(date(2026, 9, 22), days=30)

    responses: dict[Any, Any] = {}
    for day in days:
        responses[
            _key(
                "statistics_decks",
                format="modern",
                archetype_name="broodscale bloodchief",
                date_from=day,
                date_to=day,
                limit=5000,
                include_cards="names_only",
            )
        ] = primary_page if day == "2026-09-22" else []
        responses[
            _key(
                "statistics_decks",
                format="modern",
                date_from=day,
                date_to=day,
                limit=5000,
                include_cards="none",
            )
        ] = whole_format_page if day == "2026-09-22" else []
    responses[
        _key("statistics_decks", format="modern", id="3677f30b-f064-42bf-b500-3cb5a624af68")
    ] = by_id_deck

    transport = FakeTransport(responses)
    client = fm.SpellslingerClient(transport)
    decks = fm.enumerate_archetype_decks(client, format="modern", merge=merge, days=days)

    # 2 primary decks (danro, someoneelse) + 1 secondary deck (chiyou, via
    # the other id b535c0d2...) - "someoneelse" appears in the whole-format
    # listing too (under a different archetype) but must not be pulled in.
    assert len(decks) == 3
    assert ("chiyou", "2026-09-22T00:00:00Z") in decks
    assert decks[("chiyou", "2026-09-22T00:00:00Z")] == [
        "4 Basking Broodscale",
        "4 Kozilek's Command",
        "1 Cavern of Souls",
    ]


def test_fetch_whole_format_listing_by_day_is_shared_not_refetched_per_archetype():
    """`fetch_format` fetches the whole-format day listing once per day and
    shares it across every qualifying archetype's secondary harvest,
    instead of each archetype re-fetching the same day's listing for
    itself - the listing depends only on (format, day)."""
    archetypes = [
        {"canonical_name": "archetype a", "id": "id-a1", "deck_count": 15, "format": "modern"},
        {"canonical_name": "archetype a", "id": "id-a2", "deck_count": 10, "format": "modern"},
        {"canonical_name": "archetype b", "id": "id-b1", "deck_count": 15, "format": "modern"},
        {"canonical_name": "archetype b", "id": "id-b2", "deck_count": 10, "format": "modern"},
    ]
    days = fm.window_days(date(2026, 9, 22), days=30)
    responses: dict[Any, Any] = {
        _key("statistics_archetypes", format="modern", limit=5000): archetypes
    }
    for day in days:
        for name in ("archetype a", "archetype b"):
            responses[
                _key(
                    "statistics_decks",
                    format="modern",
                    archetype_name=name,
                    date_from=day,
                    date_to=day,
                    limit=5000,
                    include_cards="names_only",
                )
            ] = []
        responses[
            _key(
                "statistics_decks",
                format="modern",
                date_from=day,
                date_to=day,
                limit=5000,
                include_cards="none",
            )
        ] = []
    transport = FakeTransport(responses)
    client = fm.SpellslingerClient(transport)
    fm.fetch_format(
        client,
        format="modern",
        as_of=date(2026, 9, 22),
        min_decks=20,
        min_rate=0.2,
        resolve_name=lambda name: name,
        unresolved=set(),
    )
    whole_format_calls = [
        args
        for tool, args in transport.calls
        if tool == "statistics_decks" and "id" not in args and "archetype_name" not in args
    ]
    # One call per day, not one per (day, archetype) - both archetypes need
    # secondary harvest, so a naive implementation would call this twice
    # per day (62 calls) instead of once (31 calls).
    assert len(whole_format_calls) == len(days)


def test_enumerate_archetype_decks_primary_truncation_raises():
    merge = fm.ArchetypeMerge(
        canonical_name="broodscale bloodchief", ids=("only-id",), deck_count=999, top_id="only-id"
    )
    days = ["2026-09-22"]
    responses = {
        _key(
            "statistics_decks",
            format="modern",
            archetype_name="broodscale bloodchief",
            date_from="2026-09-22",
            date_to="2026-09-22",
            limit=5000,
            include_cards="names_only",
        ): {
            "items": [{"pilot": "a", "tournament_date": "x", "mainboard": []}],
            "_truncated": True,
            "_original_count": 500,
        },
    }
    transport = FakeTransport(responses)
    client = fm.SpellslingerClient(transport)
    with pytest.raises(fm.TruncationError) as exc_info:
        fm.enumerate_archetype_decks(client, format="modern", merge=merge, days=days)
    message = str(exc_info.value)
    assert "broodscale bloodchief" in message
    assert "2026-09-22" in message


# ---------------------------------------------------------------------------
# Inclusion rates
# ---------------------------------------------------------------------------


def test_card_inclusion_rates_keeps_only_cards_at_or_above_threshold():
    decks = {
        ("a", "d1"): ["4 Lightning Bolt", "4 Mountain"],
        ("b", "d2"): ["4 Lightning Bolt", "2 Island"],
        ("c", "d3"): ["1 Lightning Bolt"],
        ("d", "d4"): ["2 Island"],
    }
    rates = fm.card_inclusion_rates(decks, min_rate=0.5)
    # >= 0.5, not > 0.5: Island is included at exactly 0.5, Mountain (0.25)
    # is not - "keep cards with rate >= min_rate" per the campaign spec.
    assert rates == {"Lightning Bolt": 0.75, "Island": 0.5}


def test_card_inclusion_rates_counts_presence_not_copies():
    decks = {
        ("a", "d1"): ["4 Lightning Bolt"],
        ("b", "d2"): ["1 Lightning Bolt"],
    }
    rates = fm.card_inclusion_rates(decks, min_rate=0.2)
    assert rates["Lightning Bolt"] == 1.0


def test_card_inclusion_rates_rounds_to_three_decimal_places():
    decks = {(str(i), str(i)): ["1 Sol Ring"] for i in range(3)}
    rates = fm.card_inclusion_rates(decks, min_rate=0.2)
    assert rates == {"Sol Ring": 1.0}
    decks2 = {(str(i), str(i)): (["1 Sol Ring"] if i < 2 else []) for i in range(3)}
    rates2 = fm.card_inclusion_rates(decks2, min_rate=0.2)
    assert rates2 == {"Sol Ring": 0.667}


def test_card_inclusion_rates_empty_decks_is_empty():
    assert fm.card_inclusion_rates({}, min_rate=0.2) == {}


# ---------------------------------------------------------------------------
# Name resolution against the engine's card data
# ---------------------------------------------------------------------------


def test_build_name_resolver_resolves_plain_name():
    resolve = fm.build_name_resolver([{"name": "Lightning Bolt"}])
    assert resolve("Lightning Bolt") == "Lightning Bolt"


def test_build_name_resolver_resolves_front_face_of_an_mdfc():
    resolve = fm.build_name_resolver(
        [{"name": "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"}]
    )
    assert resolve("Fable of the Mirror-Breaker") == (
        "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"
    )


def test_build_name_resolver_returns_none_for_unknown_card():
    resolve = fm.build_name_resolver([{"name": "Lightning Bolt"}])
    assert resolve("Not A Real Card") is None


def test_build_name_resolver_resolves_full_mdfc_name_unchanged():
    """A fixture-level check that the ordinary path (a full `"A // B"` name
    already matching the engine's own spelling) still resolves to itself,
    unaffected by the single-slash normalization and front-face fallback
    added below."""
    full_name = "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki"
    resolve = fm.build_name_resolver([{"name": full_name}])
    assert resolve(full_name) == full_name


def test_build_name_resolver_normalizes_a_single_slash_room_name():
    """A Room card's spellslinger name came back as a single `" / "`
    separator ("Unholy Annex / Ritual Chamber") rather than the engine's
    `" // "` - normalized before lookup rather than left unresolved."""
    full_name = "Unholy Annex // Ritual Chamber"
    resolve = fm.build_name_resolver([{"name": full_name}])
    assert resolve("Unholy Annex / Ritual Chamber") == full_name


def test_build_name_resolver_falls_back_to_front_face_on_a_bad_back_face():
    """A spellslinger data oddity: the full name it gave has the right
    front face but a wrong/duplicated back face
    ("Twinmaw Stormbrood // Twinmaw Stormbrood" instead of the real back
    face). The exact string never matches, so this falls back to the front
    face (before the first separator) and resolves via the engine's own
    front-face index, emitting the canonical engine name - not left
    unresolved."""
    full_name = "Twinmaw Stormbrood // Twinmaw Stormbrood, Reborn"
    resolve = fm.build_name_resolver([{"name": full_name}])
    assert resolve("Twinmaw Stormbrood // Twinmaw Stormbrood") == full_name


def test_build_name_resolver_front_face_fallback_also_covers_single_slash():
    full_name = "Some Front // Some Back"
    resolve = fm.build_name_resolver([{"name": full_name}])
    # Wrong back face AND a single-slash separator at once.
    assert resolve("Some Front / Not The Real Back") == full_name


def test_build_name_resolver_ignores_a_never_legal_memorabilia_duplicate_of_the_bad_name():
    """Real bug found live: oracle-cards also carries a `memorabilia`
    (`layout="art_series"`) gallery object literally named
    "Twinmaw Stormbrood // Twinmaw Stormbrood" - never legal in any format
    - alongside the real adventure card "Twinmaw Stormbrood // Charring
    Bite". `is_eligible_printing` alone does not exclude it
    (`_EXCLUDED_SET_TYPES` only checks `set_type == "art_series"`, and this
    row's own `set_type` is `"memorabilia"`); without also gating on
    `_in_target_formats` (never-legal), the bogus row's exact name shadowed
    the front-face fallback and the resolver returned the fake name
    unchanged instead of the real card."""
    real_card = "Twinmaw Stormbrood // Charring Bite"
    resolve = fm.build_name_resolver(
        [
            {
                "name": real_card,
                "layout": "adventure",
                "set_type": "expansion",
                "legalities": {"standard": "not_legal", "pioneer": "not_legal", "modern": "legal"},
            },
            {
                "name": "Twinmaw Stormbrood // Twinmaw Stormbrood",
                "layout": "art_series",
                "set_type": "memorabilia",
                "legalities": {
                    "standard": "not_legal",
                    "pioneer": "not_legal",
                    "modern": "not_legal",
                },
            },
        ]
    )
    assert resolve("Twinmaw Stormbrood // Twinmaw Stormbrood") == real_card


# ---------------------------------------------------------------------------
# Per-format fetch: unresolved reporting, deterministic snapshot shape
# ---------------------------------------------------------------------------


def test_fetch_format_reports_unresolved_names_without_dropping_them_silently():
    archetypes = [
        {
            "canonical_name": "solo archetype",
            "id": "id-1",
            "deck_count": 1,
            "format": "modern",
            "share": 1.0,
        }
    ]
    days = fm.window_days(date(2026, 9, 22), days=30)
    decks_page = [
        {"pilot": "p", "tournament_date": "2026-09-22T00:00:00Z", "mainboard": ["1 Mystery Card"]}
    ]
    responses: dict[Any, Any] = {}
    for day in days:
        responses[
            _key(
                "statistics_decks",
                format="modern",
                archetype_name="solo archetype",
                date_from=day,
                date_to=day,
                limit=5000,
                include_cards="names_only",
            )
        ] = decks_page if day == "2026-09-22" else []
    responses[_key("statistics_archetypes", format="modern", limit=5000)] = archetypes
    transport = FakeTransport(responses)
    client = fm.SpellslingerClient(transport)

    unresolved: set[str] = set()
    resolve_name = fm.build_name_resolver([{"name": "Something Else"}])
    result = fm.fetch_format(
        client,
        format="modern",
        as_of=date(2026, 9, 22),
        min_decks=1,
        min_rate=0.2,
        resolve_name=resolve_name,
        unresolved=unresolved,
    )
    assert unresolved == {"Mystery Card"}
    assert result["solo archetype"].cards == {}
    assert result["solo archetype"].decks_enumerated == 1
    assert result["solo archetype"].deck_count_reported == 1


# ---------------------------------------------------------------------------
# Output: deterministic, sorted, stable rounding
# ---------------------------------------------------------------------------


def test_build_output_is_deterministic_and_sorted():
    formats = {
        "modern": {
            "zeta archetype": fm.ArchetypeSnapshot(
                deck_count_reported=30,
                decks_enumerated=30,
                cards={"Zeta Card": 0.5, "Alpha Card": 0.9},
            ),
            "alpha archetype": fm.ArchetypeSnapshot(
                deck_count_reported=25, decks_enumerated=25, cards={"Beta Card": 0.25}
            ),
        },
        "pioneer": {},
        "standard": {},
    }
    out1 = fm.build_output(
        as_of=date(2026, 9, 27),
        min_decks=20,
        min_rate=0.2,
        formats=formats,
        unresolved={"Z Card", "A Card"},
    )
    out2 = fm.build_output(
        as_of=date(2026, 9, 27),
        min_decks=20,
        min_rate=0.2,
        formats=formats,
        unresolved={"Z Card", "A Card"},
    )
    text1 = json.dumps(out1, sort_keys=True)
    text2 = json.dumps(out2, sort_keys=True)
    assert text1 == text2
    assert out1["unresolved"] == ["A Card", "Z Card"]
    assert list(out1["formats"]["modern"].keys()) == ["alpha archetype", "zeta archetype"]
    assert list(out1["formats"]["modern"]["zeta archetype"]["cards"].keys()) == [
        "Alpha Card",
        "Zeta Card",
    ]
    assert out1["as_of"] == "2026-09-27"
    assert out1["window_days"] == 30
    assert out1["min_decks"] == 20
    assert out1["min_rate"] == 0.2
    assert out1["source"] == "spellslinger statistics_decks"
