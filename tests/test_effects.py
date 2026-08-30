"""Single-clause player effects, parsed off real oracle text rather than a
per-card table row - see `machines/effects.py`'s `parse_clause_effect`,
`split_effect_clauses`, `parse_player_effect` and `parse_player_effect_for_spell`.

This is a unit-test file: it checks what the parser returns (`None` or a
callable) against real printed text, the same discipline
`test_abilities.py` uses for the ability parser itself. Whether the callable
actually changes a real game state is `tests/scenarios/test_player_effect_parser.py`'s
job - a scenario test with a real board, since that is where the primitives
(`Player.gain_life`, `Player.add_counters`, `Game.draw_cards`, `Game.surveil`,
`Game.scry`, `Game.put_into_graveyard`) actually run.

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote this file:

- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - the reason a multi-clause effect is
  split and run clause by clause, in order.
- **CR 119.3** - "If an effect causes a player to gain life or lose life, that
  player's life total is adjusted accordingly."
- **CR 107.14** - "The energy symbol is {E}. It represents one energy
  counter."
- **CR 121.1/121.2** - drawing a card, one at a time.
- **CR 701.17a** - "For a player to mill a number of cards, that player puts
  that many cards from the top of their library into their graveyard."
- **CR 701.22a** - scry.
- **CR 701.25a** - surveil.
"""

from magic_cards_model.machines import AbilityKind, TriggerEvent, abilities_of_kind
from magic_cards_model.machines.effects import (
    ACTIVATED_EFFECTS,
    EFFECTS,
    TRIGGER_EFFECTS,
    activated_effect_for,
    effect_for,
    parse_clause_effect,
    parse_player_effect,
    parse_player_effect_for_spell,
    split_effect_clauses,
    trigger_effect_for,
)
from tests.cards import card


def _triggered_effect_text(name: str, event: TriggerEvent | None = None) -> str:
    """The `effect` field of one of a card's triggered abilities, reminder
    text and trigger condition already stripped by `machines/abilities.py` -
    the exact string `trigger_effect_for` is called with in a real game.

    `event` picks one out for a card with more than one trigger (Guide of
    Souls has two); left `None`, the card must have exactly one.
    """
    triggers = abilities_of_kind(card(name), AbilityKind.TRIGGERED)
    if event is not None:
        (ability,) = [ability for ability in triggers if ability.event is event]
        return ability.effect
    (ability,) = triggers
    return ability.effect


def _activated_effect_text(name: str, index: int = 0) -> str:
    ability = abilities_of_kind(card(name), AbilityKind.ACTIVATED)[index]
    return ability.effect


# --------------------------------------------------------------------------
# split_effect_clauses - CR 608.2c, "in the order written"
# --------------------------------------------------------------------------


def test_guide_of_souls_splits_into_the_gain_and_the_energy():
    """The exact reported bug: one sentence, two clauses, joined by "and"."""
    assert split_effect_clauses(
        _triggered_effect_text("Guide of Souls", TriggerEvent.ENTERS_THE_BATTLEFIELD)
    ) == [
        "you gain 1 life",
        "get {E}",
    ]


def test_vampiric_rites_splits_on_and():
    assert split_effect_clauses(_activated_effect_text("Vampiric Rites")) == [
        "You gain 1 life",
        "draw a card",
    ]


def test_preordain_splits_on_a_sentence_and_a_then():
    """Preordain has a registry row and never reaches this parser in a real
    game, but its shape - "Scry 2, then draw a card." - is exactly the
    "then" join this wave was asked to handle, off real printed text.
    """
    assert split_effect_clauses(card("Preordain").oracle_text) == ["Scry 2", "draw a card"]


def test_a_single_clause_effect_splits_into_one_clause():
    assert split_effect_clauses(_triggered_effect_text("Soul Warden")) == ["you gain 1 life"]


# --------------------------------------------------------------------------
# parse_clause_effect - one clause, matched only when the whole clause is this
# --------------------------------------------------------------------------


def test_gain_life_clause_parses():
    assert parse_clause_effect("you gain 1 life") is not None


def test_lose_life_clause_parses_off_thoughtseizes_own_text():
    """Thoughtseize: "...That player discards that card. You lose 2 life." -
    the last clause, taken on its own, is exactly the "You lose N life." shape.
    """
    clauses = split_effect_clauses(card("Thoughtseize").oracle_text)
    assert clauses[-1] == "You lose 2 life"
    assert parse_clause_effect(clauses[-1]) is not None


def test_energy_clause_parses_off_static_prisons_own_text():
    """Static Prison: "...You get {E}{E} (two energy counters)." - the reminder
    parenthetical is real printed text too, and must not stop the match.
    """
    clauses = split_effect_clauses(
        _triggered_effect_text("Static Prison", TriggerEvent.ENTERS_THE_BATTLEFIELD)
    )
    energy_clause = clauses[-1]
    assert "{E}{E}" in energy_clause
    assert parse_clause_effect(energy_clause) is not None


def test_draw_a_card_clause_parses():
    assert parse_clause_effect("Draw a card.") is not None


def test_draw_seven_cards_spelled_out_parses():
    """Griselbrand: "Pay 7 life: Draw seven cards." - a spelled-out number,
    not a digit.
    """
    assert parse_clause_effect(_activated_effect_text("Griselbrand")) is not None


def test_mill_a_card_clause_parses():
    assert parse_clause_effect(_triggered_effect_text("Icetill Explorer")) is not None


def test_surveil_clause_parses():
    assert parse_clause_effect(_triggered_effect_text("Commercial District")) is not None


def test_scry_clause_parses():
    assert parse_clause_effect(_triggered_effect_text("Archive Dragon")) is not None


def test_a_targeted_clause_does_not_parse():
    """ "Choose target creature or planeswalker" - Galvanic Discharge's first
    clause. Targeting is the next wave's job, not this one's.
    """
    assert parse_clause_effect("Choose target creature or planeswalker") is None


def test_a_target_player_clause_does_not_parse():
    """Blood Artist: "target player loses 1 life and you gain 1 life." - the
    first half names a target, so it is not the same shape as "you lose".
    """
    clauses = split_effect_clauses(_triggered_effect_text("Blood Artist"))
    assert clauses[0] == "target player loses 1 life"
    assert parse_clause_effect(clauses[0]) is None


def test_a_may_clause_does_not_parse():
    """Solemn Simulacrum's death trigger is "you may draw a card" - a choice,
    which this wave explicitly does not resolve (nobody to ask).
    """
    assert (
        parse_clause_effect(_triggered_effect_text("Solemn Simulacrum", TriggerEvent.DIES)) is None
    )


def test_a_variable_energy_amount_does_not_parse():
    """Wrath of the Skies: "You get X {E}" - X is a choice made on casting,
    not a fixed number of {E} symbols this parser reads off the text.
    """
    clauses = split_effect_clauses(card("Wrath of the Skies").oracle_text)
    assert parse_clause_effect(clauses[0]) is None


# --------------------------------------------------------------------------
# parse_player_effect / parse_player_effect_for_spell - fail-closed
# --------------------------------------------------------------------------


def test_guide_of_souls_parses_as_one_effect_with_two_clauses():
    assert (
        parse_player_effect(
            _triggered_effect_text("Guide of Souls", TriggerEvent.ENTERS_THE_BATTLEFIELD)
        )
        is not None
    )


def test_one_bad_clause_fails_the_whole_effect_closed():
    """The most important test in this wave: Blood Artist's dies trigger has
    one parseable clause ("you gain 1 life") and one that is not ("target
    player loses 1 life"). CR 608.2c has no notion of running half of an
    effect, so the whole thing must come back `None` - not a life *gain* with
    the life *loss* silently dropped, which would be a wrong game state that
    looks like a right one.
    """
    assert parse_player_effect(_triggered_effect_text("Blood Artist")) is None


def test_a_wholly_targeted_spell_does_not_parse_as_a_player_effect():
    """Galvanic Discharge - three clauses, the first and third both targeted.
    None of it should run.
    """
    assert parse_player_effect_for_spell(card("Galvanic Discharge").oracle_text) is None


def test_thoughtseize_does_not_parse_despite_its_last_clause_being_plain():
    assert parse_player_effect(card("Thoughtseize").oracle_text) is None


def test_static_prisons_enters_trigger_does_not_parse_as_a_whole():
    """The energy clause alone parses (see above), but the trigger's first
    clause exiles a target - so the whole ability still returns `None`, and
    Static Prison's energy grant is not something this wave turns on.
    """
    assert (
        parse_player_effect(
            _triggered_effect_text("Static Prison", TriggerEvent.ENTERS_THE_BATTLEFIELD)
        )
        is None
    )


# --------------------------------------------------------------------------
# Wired into all three resolution paths, and an explicit row always wins
# --------------------------------------------------------------------------


def test_trigger_effect_for_falls_back_to_the_player_effect_parser():
    assert ("Kitchen Finks", TriggerEvent.ENTERS_THE_BATTLEFIELD, "") not in TRIGGER_EFFECTS
    assert (
        trigger_effect_for("Kitchen Finks", TriggerEvent.ENTERS_THE_BATTLEFIELD, "you gain 2 life")
        is not None
    )


def test_activated_effect_for_falls_back_to_the_player_effect_parser():
    assert ("Vexing Bauble", 0) not in ACTIVATED_EFFECTS
    assert activated_effect_for("Vexing Bauble", 0, "Draw a card.") is not None


def test_effect_for_falls_back_to_the_player_effect_parser_for_a_spell():
    """The spell path had no fallback at all before this wave - `effect_for`
    took only a card name and could not read a spell's own text.
    """
    assert "Test Plain Life Gain Spell" not in EFFECTS
    assert effect_for("Test Plain Life Gain Spell", "You gain 3 life.") is not None


def test_an_explicit_trigger_row_wins_over_the_parser(monkeypatch):
    """Same guarantee `test_fetching_a_land.py` proves for
    `parse_search_and_put_effect`: an explicit registry row is checked first,
    so nothing already scripted changes behaviour just because its text also
    happens to be parseable.
    """
    sentinel = object()
    key = ("Kitchen Finks", TriggerEvent.ENTERS_THE_BATTLEFIELD, "")
    monkeypatch.setitem(TRIGGER_EFFECTS, key, sentinel)

    assert (
        trigger_effect_for("Kitchen Finks", TriggerEvent.ENTERS_THE_BATTLEFIELD, "you gain 2 life")
        is sentinel
    )


def test_an_explicit_activated_row_wins_over_the_parser(monkeypatch):
    sentinel = object()
    monkeypatch.setitem(ACTIVATED_EFFECTS, ("Vexing Bauble", 0), sentinel)

    assert activated_effect_for("Vexing Bauble", 0, "Draw a card.") is sentinel


def test_an_explicit_spell_row_wins_over_the_parser(monkeypatch):
    sentinel = object()
    monkeypatch.setitem(EFFECTS, "Vexing Bauble", sentinel)

    assert effect_for("Vexing Bauble", "Draw a card.") is sentinel


def test_no_card_has_a_registry_entry_that_would_shadow_the_player_effect_parser():
    """The equivalent of `test_fetching_a_land.py`'s
    `test_no_fetchland_has_a_registry_entry_that_would_shadow_the_parser`, for
    every card this wave newly unlocks. Re-adding a per-card row for any of
    them would silently take over from the parser again.
    """
    newly_unlocked_triggers = [
        ("Kitchen Finks", TriggerEvent.ENTERS_THE_BATTLEFIELD),
        ("Soul Warden", TriggerEvent.ENTERS_THE_BATTLEFIELD),
        ("Guide of Souls", TriggerEvent.ENTERS_THE_BATTLEFIELD),
        ("Icetill Explorer", TriggerEvent.ENTERS_THE_BATTLEFIELD),
        ("Archive Dragon", TriggerEvent.ENTERS_THE_BATTLEFIELD),
        ("Commercial District", TriggerEvent.ENTERS_THE_BATTLEFIELD),
        ("Elegant Parlor", TriggerEvent.ENTERS_THE_BATTLEFIELD),
        ("Thundering Falls", TriggerEvent.ENTERS_THE_BATTLEFIELD),
        ("Dragon's Rage Channeler", TriggerEvent.CAST_SPELL),
    ]
    for name, event in newly_unlocked_triggers:
        for row_name, row_event, _marker in TRIGGER_EFFECTS:
            assert not (row_name == name and row_event is event), (name, event)

    newly_unlocked_activated = [
        ("Vexing Bauble", 0),
        ("Griselbrand", 0),
        ("Mind Stone", 1),
        ("Nurturing Peatland", 1),
        ("Fiery Islet", 1),
        ("Sunbaked Canyon", 1),
    ]
    for key in newly_unlocked_activated:
        assert key not in ACTIVATED_EFFECTS
