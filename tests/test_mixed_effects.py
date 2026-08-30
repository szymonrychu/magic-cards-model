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
# The anaphoric "<verb> target X. Its/that X's controller ..." pair
# (Solitude's defect) - see `tests/scenarios/test_anaphoric_referent_clauses.py`
# for the end-to-end scenario coverage; this is the text-level parser check.
# --------------------------------------------------------------------------


def test_solitude_now_parses_as_a_mixed_effect():
    """Solitude's trigger text, exactly as `TriggeredAbility.effect` holds it
    (the "When this creature enters," prefix already stripped): "exile up to
    one other target creature. That creature's controller gains life equal
    to its power." used to have no parser for its second sentence at all.
    """
    from magic_cards_model.machines.effects import parse_mixed_effect

    text = (
        "exile up to one other target creature. "
        "That creature's controller gains life equal to its power."
    )
    assert parse_mixed_effect(text) is not None


def test_swords_to_plowshares_now_parses_as_a_mixed_effect_with_no_row():
    assert "Swords to Plowshares" not in EFFECTS
    assert parse_mixed_effect_for_spell(card("Swords to Plowshares").oracle_text) is not None


def test_unreadable_anaphoric_clause_finds_the_second_sentence_of_a_synthetic_pair():
    """`_unreadable_anaphoric_clause` is what feeds `AnaphoricClauseNotice` -
    it has to find the second sentence of a structurally-matching pair whose
    tail this wave genuinely cannot read (no real card in the fixture pool
    has this exact gap any more; a synthetic string, the same discipline
    `test_a_variable_energy_amount_does_not_parse` uses for a shape with no
    real-card example).
    """
    from magic_cards_model.machines.effects import _unreadable_anaphoric_clause

    text = "exile target creature. That creature's controller draws a card equal to its power."
    unread = _unreadable_anaphoric_clause(text, for_spell=True)
    assert unread == "That creature's controller draws a card equal to its power"


def test_boseijus_channel_search_clause_now_parses():
    """Boseiju, Who Endures' Channel ability used to fail to parse as a whole,
    for two separate reasons layered on top of each other - both now fixed:

    - its search sentence says "a land card with a basic land type" rather
      than the "a basic land card" phrasing `_REFERENT_SEARCH_RE` used to
      read alone; `_SEARCH_AND_PUT_RE`/`_REFERENT_SEARCH_RE` now carry a
      `basic_land_type` group read by `_search_and_place_for` as CR 305.6's
      own subtype question (not the "basic" *supertype* "a basic land card"
      is - a shockland has a basic land type without being a basic land,
      CR 305.8), so it is not folded into `_quality_matcher`'s narrower
      "basic land" branch.
    - its destroy clause used to be followed by a third sentence ("This
      ability costs {1} less ...") no clause parser read; that sentence is
      no longer part of this text at all by the time it gets here -
      `machines/abilities._split_off_trailing_cost_reduction` reads it as
      its own static ability (CR 604.1, CR 702.41a's Affinity is the CR's own
      precedent for this "costs [N] less" shape) before `ActivatedAbility.
      effect` is ever built, so the text below is exactly what a real
      activation resolves - no cost-reduction tail to strip here by hand.

    What matters here is that `_unreadable_anaphoric_clause` correctly
    checks by actually trying to build the pair
    (`_parse_anaphoric_clause_pair`), not just matching the two shapes' own
    regexes - both fixes are exercised together, since the search clause is
    the second half of the anaphoric pair the destroy clause opens.
    """
    from magic_cards_model.machines.effects import _unreadable_anaphoric_clause

    text = (
        "Destroy target artifact, enchantment, or nonbasic land an opponent controls. "
        "That player may search their library for a land card with a basic land type, "
        "put it onto the battlefield, then shuffle."
    )
    unread = _unreadable_anaphoric_clause(text, for_spell=False)
    assert unread is None


# --------------------------------------------------------------------------
# "Imprint" (CR 207.2c) - "you may exile a `<quality>` card ... from your
# hand", and giving the linked card back. See
# `tests/scenarios/test_imprint.py` for the end-to-end game-state coverage;
# this is the text-level parser check, on Ugin's Labyrinth's real printed
# text (the only card in the fixture pool carrying this shape).
# --------------------------------------------------------------------------


def test_ugins_labyrinths_imprint_trigger_now_parses_with_no_registry_row():
    """ "Imprint — When this land enters, you may exile a colorless card with
    mana value 7 or greater from your hand." - `TriggeredAbility.effect` holds
    the text after the ability word and the trigger condition are stripped.
    """
    from magic_cards_model.machines import AbilityKind, abilities_of_kind
    from magic_cards_model.machines.abilities import TriggerEvent
    from magic_cards_model.machines.effects import TRIGGER_EFFECTS, trigger_effect_for

    assert not any(key[0] == "Ugin's Labyrinth" for key in TRIGGER_EFFECTS)
    (trigger,) = abilities_of_kind(card("Ugin's Labyrinth"), AbilityKind.TRIGGERED)
    effect = trigger_effect_for(
        "Ugin's Labyrinth", TriggerEvent.ENTERS_THE_BATTLEFIELD, trigger.effect
    )
    assert effect is not None


def test_ugins_labyrinths_return_ability_now_parses_with_no_registry_row():
    """ "{T}: Return the exiled card to its owner's hand." - the land's third
    ability, index 1 among its activated abilities (index 0 is the mana
    ability).
    """
    from magic_cards_model.machines.abilities import ActivatedAbility, parse_abilities
    from magic_cards_model.machines.effects import ACTIVATED_EFFECTS, activated_effect_for

    assert not any(key[0] == "Ugin's Labyrinth" for key in ACTIVATED_EFFECTS)
    activated = [
        ability
        for ability in parse_abilities(card("Ugin's Labyrinth"))
        if isinstance(ability, ActivatedAbility)
    ]
    assert len(activated) == 2
    effect = activated_effect_for("Ugin's Labyrinth", 1, activated[1].effect)
    assert effect is not None


def test_ugins_labyrinths_mana_ability_carries_the_imprinted_condition():
    """ "{T}: Add {C}. If a card is exiled with this land, add {C}{C}
    instead." reads as a `ManaCondition` with `imprinted=True`, the same
    conditional-mana shape as Urza's Tower's land-type check and Gemstone
    Caverns' counter check, just a third kind of thing to check.
    """
    from magic_cards_model.machines.abilities import parse_mana_abilities

    (ability,) = parse_mana_abilities(card("Ugin's Labyrinth"))
    assert len(ability.conditional) == 1
    assert ability.conditional[0].imprinted is True


def test_an_unrecognised_imprint_quality_is_still_recognised_as_the_shape():
    """`_unreadable_imprint_quality` is what feeds `ImprintNotice` - it has to
    find the clause of a structurally-matching "you may exile a `<quality>`
    card ... from your hand" sentence whose quality this wave cannot read (no
    real card in the fixture pool has this gap - Ugin's Labyrinth's own
    "colorless" and every "with mana value N or greater/less" bound both
    parse fine - so this is a synthetic string, the same discipline
    `test_unreadable_anaphoric_clause_finds_the_second_sentence_of_a_synthetic_pair`
    uses above).
    """
    from magic_cards_model.machines.effects import _unreadable_imprint_quality

    text = "you may exile an artifact or creature card from your hand"
    assert _unreadable_imprint_quality(text) == text


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
