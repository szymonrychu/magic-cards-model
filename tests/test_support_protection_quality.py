"""A Protection keyword is credited only when the engine can read every
quality it names (CR 702.16a: "protection from [quality]"). A quality no
protection reader understands (`models/game.protection_quality_readable`) is
never enforced, so the keyword clause is a notice naming it - not `handled`
on the word's presence alone.

Every printing is chosen from the pool by its own Protection keyword, never
by name.
"""

from magic_cards_model.models.game import protection_qualities, protection_quality_readable
from magic_cards_model.support import card_support
from tests.cards import pool


def _protection_printings():
    seen = {}
    for printing in pool().values():
        if "Protection" in printing.keywords:
            seen.setdefault(printing.name, printing)
    return [seen[name] for name in sorted(seen)]


def _protection_clause(printing):
    (clause,) = [
        c for c in card_support(printing).clauses if c.kind == "keyword" and c.text == "Protection"
    ]
    return clause


def test_a_protection_keyword_is_handled_exactly_when_every_quality_reads():
    handled, notice = [], []
    for printing in _protection_printings():
        qualities = protection_qualities(printing)
        readable = bool(qualities) and all(protection_quality_readable(q) for q in qualities)
        clause = _protection_clause(printing)
        if readable:
            assert clause.outcome == "handled", (printing.name, qualities)
            handled.append(printing.name)
        else:
            assert clause.outcome == "notice", (printing.name, qualities)
            unread = [q for q in qualities if not protection_quality_readable(q)]
            assert all(q in clause.reason for q in unread), (printing.name, clause.reason)
            notice.append(printing.name)
    assert len(handled) >= 5, handled


def test_colour_count_qualities_read():
    """CR 105.2a/105.2b's "monocolored"/"multicolored" are read qualities -
    `tests/scenarios/test_protection_color_count_qualities.py` plays them."""
    assert protection_quality_readable("multicolored")
    assert protection_quality_readable("monocolored")
    assert not protection_quality_readable("everything")
