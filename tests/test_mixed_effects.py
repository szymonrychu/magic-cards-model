"""The mixed targeted/player clause dispatcher - `machines/effects.py`'s
`parse_mixed_effect_for_spell` and the shared clause preparation
(`_prepare_effect_clauses`) it uses with `_parse_targeted_clauses` and
`_parse_player_clauses`.

This is a unit-test file: it checks what the parser returns (`None` or a
callable) against real printed text, the same discipline `test_effects.py`
and `test_targeted_effects.py` use for their own parsers. Whether the callable
actually changes a real game state is `tests/scenarios/test_mixed_effect_parser.py`'s
job.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - why one bad clause takes the whole
  effect down rather than the half that would have worked being run alone.
- **CR 700.2** - "A spell or ability is modal if it has two or more options in
  a bulleted list preceded by instructions for a player to choose a number of
  those options" - why a modal card is refused outright rather than read as
  one linear list of clauses.
- **CR 118.8a** - an additional cost is paid on the way to the stack, not part
  of resolving the spell, which is why it is stripped before clauses are read.
"""

from magic_cards_model.machines.effects import (
    EFFECTS,
    effect_for,
    parse_mixed_effect_for_spell,
    parse_player_effect_for_spell,
)
from tests.cards import card


def test_lightning_helix_parses_as_a_mixed_effect():
    """The worked case: a targeted damage clause and a plain player life-gain
    clause, joined by "and" - neither whole-effect parser alone reads this.
    """
    assert parse_mixed_effect_for_spell(card("Lightning Helix").oracle_text) is not None


def test_vraskas_contempt_parses_as_a_mixed_effect():
    """The same mixed shape on a different real card, split on a period
    instead of "and": "Exile target creature or planeswalker. You gain 2
    life."
    """
    assert parse_mixed_effect_for_spell(card("Vraska's Contempt").oracle_text) is not None


def test_fatal_push_still_does_not_parse_as_a_mixed_effect():
    """Fatal Push's mana-value comparison is refused by `_targets_understood`
    regardless of which parser tries the clause, so the mixed dispatcher does
    not change this - still `None`.
    """
    assert parse_mixed_effect_for_spell(card("Fatal Push").oracle_text) is None


def test_assassins_trophy_now_parses_as_a_mixed_effect():
    """Assassin's Trophy: "Destroy target permanent an opponent controls. Its
    controller may search their library for a basic land card, put it onto
    the battlefield, then shuffle."

    `test_targeted_effects.py` still proves the *targeted-only* parser refuses
    this card - its second clause is not a targeted shape at all. Before W3
    that second clause was a "you may" search neither whole-effect parser
    read, so the mixed dispatcher came back `None` too. W3 folded a search
    into the mixed dispatcher as its own clause shape - `_parse_search_clause`
    reads "Its controller may search ..." the same way it reads Ghost
    Quarter's identical compensation - so this card, unlike Fatal Push's
    mana-value comparison, now parses in full with no registry row.
    """
    assert parse_mixed_effect_for_spell(card("Assassin's Trophy").oracle_text) is not None


def test_a_modal_card_does_not_parse_as_a_mixed_effect():
    """Abrade: modal (CR 700.2), refused outright rather than read as two
    linear clauses.
    """
    assert parse_mixed_effect_for_spell(card("Abrade").oracle_text) is None


def test_lightning_helix_has_no_registry_row_any_more():
    assert "Lightning Helix" not in EFFECTS
    assert effect_for("Lightning Helix", card("Lightning Helix").oracle_text) is not None


# --------------------------------------------------------------------------
# The shared preamble strip + modal bail (`_prepare_effect_clauses`)
# --------------------------------------------------------------------------


def test_cathartic_reunions_additional_cost_line_is_stripped_before_splitting():
    """Cathartic Reunion: "As an additional cost to cast this spell, discard
    two cards. Draw three cards." Before `_prepare_effect_clauses` was shared
    between the targeted and player clause parsers, only the targeted side
    stripped this preamble (CR 118.8a) - the player-only parser read the cost
    line as an unparseable effect clause and threw the whole card away, so
    "Draw three cards" never ran even though it is exactly `parse_clause_effect`'s
    shape. This is the visible loss the inventory named.
    """
    text = card("Cathartic Reunion").oracle_text
    assert parse_player_effect_for_spell(text) is not None
    assert parse_mixed_effect_for_spell(text) is not None


def test_a_modal_card_whose_every_mode_is_player_parseable_does_not_run_them_all():
    """The fails-open shape the inventory warned about: before the modal bail
    was shared with the player-clause parser, only `_parse_targeted_clauses`
    checked for "Choose ..." (CR 700.2) ahead of splitting into clauses.
    `_parse_player_clauses` had no such check, so a modal card whose every
    mode happens to be a plain player clause would have `split_effect_clauses`
    cut straight across the bullet points and this parser would have read the
    whole list as one linear effect and run every mode, not just the one a
    player actually chose.

    No card in the fixture pool has this exact shape - a real "Choose one —"
    line is itself unparseable by every clause regex today (it contains
    "choose", which none of them recognise), so it already failed closed on
    its own before this fix, for a different reason. This is a synthetic
    string, the same way `test_a_variable_energy_amount_does_not_parse` and
    friends in `test_effects.py` use literal effect text to pin the parser's
    own behaviour rather than a card's - the fixture-pool proof lives in the
    real-card tests above and in `test_targeted_effects.py`'s Abrade case.
    """
    modal_text = "Choose one —\nYou gain 3 life.\nDraw a card."
    assert parse_player_effect_for_spell(modal_text) is None
    assert parse_mixed_effect_for_spell(modal_text) is None
