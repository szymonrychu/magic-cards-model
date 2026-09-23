"""`magic_cards_model.support.card_support` - the sweep's own per-card verdict
(`scripts/sweep_pool.py`), as a library call a consumer can ask about any
`Card` built from a Scryfall printing.

Every card below is a real printing from the package's own printings pool, and
each is the pool's example of one outcome: a card that works, a card with a
dead clause, a card that only fails closed with a notice, a card resting on a
static ability nothing audits, a card whose clauses disagree (the worst one
wins), a multi-face card, and cards whose only rules are keywords.
"""

import json
import time
import uuid

import pytest
from pydantic import ValidationError

import magic_cards_model
from magic_cards_model.ids import install_id_allocator, reset_id_allocator
from magic_cards_model.models import Card
from magic_cards_model.support import (
    ENGINE_VERSION,
    CardSupport,
    SupportClause,
    card_support,
    classify_card,
    clear_card_support_cache,
    has_rules_text,
    ignored_keywords,
)
from tests.cards import CARD_POOL, card, gap_example, pool


def _kinds(support: CardSupport) -> set[str]:
    return {clause.kind for clause in support.clauses}


def test_a_card_that_works_is_handled():
    support = card_support(card("Lightning Bolt"))
    assert support.name == "Lightning Bolt"
    assert support.status == "handled"
    assert support.engine_version == ENGINE_VERSION
    (clause,) = support.clauses
    assert clause.kind == "spell"
    assert clause.outcome == "handled"
    assert clause.status == "handled"
    assert "3 damage" in clause.text
    assert clause.reason


def test_a_nonlegendary_activated_ability_is_judged_as_the_engine_reads_it():
    """Treasure Map is not legendary, so the engine never reads "Treasure" in
    its "create three Treasure tokens" as a short self-name
    (`self_normalized_effect_text`'s legendary-only first-word form) - the
    sweep must ask `activated_effect_for` the same way `Game` does, or it
    judges a working ability a notice."""
    support = card_support(card("Treasure Map"))
    assert support.status == "handled"


def test_a_card_with_a_dead_clause_is_silent_and_names_the_clause():
    """A still-silent printing, chosen by `gap_example` (Keen-Eyed Curator
    stood here until S09 read its linked-exile threshold static): the card is
    silent and names the dead clause."""
    printing = gap_example("silent", lambda p: card_support(p).status == "silent")
    support = card_support(printing)
    silent = [clause for clause in support.clauses if clause.status == "silent"]
    assert silent
    assert all(clause.text and clause.reason for clause in silent)


def test_a_card_that_only_fails_closed_is_notice():
    """A printing whose worst clause fails closed with a notice, chosen by
    `gap_example` (Final Showdown stood here until S21 read its last two
    Spree modes): nothing on it is silent or unaudited."""
    printing = gap_example("a notice", lambda p: card_support(p).status == "notice")
    support = card_support(printing)
    assert {clause.status for clause in support.clauses} <= {"handled", "notice"}
    assert any(clause.status == "notice" for clause in support.clauses)


def _unaudited_static_only(printing) -> bool:
    support = card_support(printing)
    return support.status == "unaudited" and all(
        c.kind == "static" and c.outcome == "static_unaudited"
        for c in support.clauses
        if c.status == "unaudited"
    )


def test_a_static_ability_nothing_audits_is_unaudited():
    """A static line no support check audits (Alhammarret's Archive's
    life-doubling replacement stood here) is an explicit unknown, never a
    claim either way. The printing is chosen by `gap_example`."""
    printing = gap_example("unaudited on a static line", _unaudited_static_only)
    support = card_support(printing)
    assert support.status == "unaudited"
    unaudited = [c for c in support.clauses if c.status == "unaudited"]
    assert unaudited
    assert all(c.kind == "static" and c.outcome == "static_unaudited" for c in unaudited)


def test_the_worst_clause_decides_the_card():
    """A printing carrying a handled clause, a fail-closed clause and an
    unaudited one (Bloodghast stood here), chosen by `gap_example`: the card
    is only as good as its worst clause (silent < unaudited < notice <
    handled)."""
    printing = gap_example(
        "handled, notice and unaudited at once",
        lambda p: (
            {clause.status for clause in card_support(p).clauses}
            == {"handled", "notice", "unaudited"}
        ),
    )
    assert card_support(printing).status == "unaudited"


def test_a_multi_face_card_judges_each_castable_face():
    """Beck // Call is a split card: a player chooses which half to cast
    (CR 709.3, verified 2026-09-23 with `mise run rules:find 709.3`), so each
    half is judged as its own spell - two clauses, each carrying its own
    half's text. (Beck's half used to be the dead one; its "this turn"
    trigger is read now, so both are handled.)"""
    printing = card("Beck // Call")
    support = card_support(printing)
    assert support.name == "Beck // Call"
    spells = [c for c in support.clauses if c.kind == "spell"]
    assert len(spells) == 2
    assert spells[0].text.startswith("Whenever a creature enters this turn")
    assert spells[1].text.startswith("Create four 1/1 white Bird")
    assert {c.status for c in spells} == {"handled"}
    assert support.status == "handled"


def test_a_keyword_only_card_is_handled_through_its_keywords():
    """Colossal Dreadmaw's only rule is trample, read by combat."""
    printing = card("Colossal Dreadmaw")
    assert not has_rules_text(printing)
    support = card_support(printing)
    assert support.status == "handled"
    assert _kinds(support) == {"keyword"}
    (clause,) = support.clauses
    assert clause.text == "Trample"
    assert "combat" in clause.reason


def test_a_keyword_no_machine_executes_is_a_silent_keyword_clause():
    """Hammers of Moradin's Myriad has no execution path anywhere (the sweep's
    `--keywords --all-formats` report)."""
    printing = card("Hammers of Moradin")
    assert "Myriad" in ignored_keywords(printing)
    support = card_support(printing)
    myriad = [c for c in support.clauses if c.kind == "keyword" and c.text == "Myriad"]
    assert len(myriad) == 1
    assert myriad[0].status == "silent"
    assert support.status == "silent"


def test_a_card_built_straight_from_a_printing_is_classified_without_the_pool():
    """`card_support` never looks a card up by name: a `Card` validated
    straight from the Scryfall json, not fetched through `tests.cards.pool`,
    gets the same answer."""
    raw = json.loads((CARD_POOL / "lightning_bolt.json").read_text())
    fresh = Card.model_validate(raw)
    assert fresh is not card("Lightning Bolt")
    assert card_support(fresh) == card_support(card("Lightning Bolt"))


def test_the_result_is_frozen():
    support = card_support(card("Lightning Bolt"))
    with pytest.raises(ValidationError):
        support.status = "silent"
    with pytest.raises(ValidationError):
        support.clauses[0].status = "silent"
    assert isinstance(support.clauses, tuple)
    assert isinstance(support.clauses[0], SupportClause)


def test_the_support_models_announce_mutation_like_every_engine_model():
    """The package-wide invariant (`test_models_announce_mutation`) holds for
    the support oracle's own models too."""
    from magic_cards_model.snapshot import EngineModel

    assert issubclass(CardSupport, EngineModel)
    assert issubclass(SupportClause, EngineModel)


def test_the_verdict_matches_the_sweep_for_every_pool_card():
    """Single source of truth: the per-card rules-text verdict is exactly
    `classify_card`'s, for every card with rules text."""
    for printing in {id(c): c for c in pool().values()}.values():
        support = card_support(printing)
        if has_rules_text(printing):
            assert (support.effect_outcome, support.effect_detail) == classify_card(printing)
        else:
            assert support.effect_outcome is None


def test_the_answer_does_not_depend_on_call_order_or_the_cache():
    names = ["Bloodghast", "Beck // Call", "Keen-Eyed Curator", "Lightning Bolt"]
    forward = [card_support(card(name)) for name in names]
    clear_card_support_cache()
    backward = [card_support(card(name)) for name in reversed(names)]
    assert forward == list(reversed(backward))


def test_classification_never_consumes_a_games_id_allocator():
    """Side-effect free: classifying a card whose trigger condition the
    sweep probes on a throwaway board (Bloodghast's landfall) must not mint
    ids out of an allocator a live game installed, or that game's ids - and
    its replay - would shift."""
    clear_card_support_cache()
    minted: list[int] = []

    def allocator():
        minted.append(1)
        return uuid.uuid4()

    token = install_id_allocator(allocator)
    try:
        card_support(card("Bloodghast"))
        card_support(card("Steam Vents"))
    finally:
        reset_id_allocator(token)
    assert minted == []


def test_the_full_pool_classifies_within_budget():
    """The whole printings pool (one Card per printing) classifies from a
    cold cache in well under five seconds, and a warm cache is near free."""
    printings = list({id(c): c for c in pool().values()}.values())
    clear_card_support_cache()
    start = time.perf_counter()
    for printing in printings:
        card_support(printing)
    cold = time.perf_counter() - start
    start = time.perf_counter()
    for printing in printings:
        card_support(printing)
    warm = time.perf_counter() - start
    assert cold < 5.0, f"cold pool classification took {cold:.2f}s"
    assert warm < cold


def test_engine_version_names_the_package_and_schema():
    from magic_cards_model.models import Game

    assert magic_cards_model.__version__ in ENGINE_VERSION
    assert str(Game.CURRENT_SCHEMA_VERSION) in ENGINE_VERSION
