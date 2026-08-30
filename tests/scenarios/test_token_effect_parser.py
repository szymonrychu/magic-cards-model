"""Scenario: token creation (CR 111, CR 701.7a), read off a card's own printed
text instead of a per-card `TokenDefinition` in `machines/effects.py` (W4).

`_parse_token_clause` is a new shape in the same per-clause dispatcher W1-W3
built for damage, search, and player clauses: `_parse_mixed_clause` tries it
between the targeted parser and the search parser, so a card whose whole text
is "create ... token(s)" - or that mixes a token clause with a targeted or
player one - reaches the board with no table row.

W4 deleted four rows this parser now subsumes: Spectral Procession (`EFFECTS`),
and Ajani, Nacatl Pariah's enters trigger, Drowner of Truth's cast trigger, and
Wurmcoil Engine's dies trigger (all three `TRIGGER_EFFECTS`). Existing tests in
`test_tokens.py` already exercise Spectral Procession, Ajani's enters trigger,
and a Wurmcoil dies trigger (through a token copy) end to end without a row -
they were not rewritten for this wave because they did not need to be, and
their still passing is itself proof the fallback replaced the row without
changing what the card does. This file is what those did not already cover:
Drowner of Truth's quoted rules text, a predefined token reached by a card that
never had a row at all (Generous Ent's Food), a token entering firing another
permanent's own enters trigger with no help from a hand-written case, and the
two fail-closed guarantees the task asked to be proven rather than assumed:
Ocelot Pride and Hangarback Walker's full printed text refusing to parse at
all, copy clause and variable count included, so neither can ever be
half-executed if their table rows were ever removed.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 701.7a** - "To create one or more tokens with certain characteristics,
  put the specified number of tokens with the specified characteristics onto
  the battlefield."
- **CR 111.3** - a token's stated characteristics "are functionally
  equivalent to the characteristic values that are printed on a card."
- **CR 111.10** - "Some effects instruct a player to create a predefined
  token." CR 111.10b: "A Food token is a colorless Food artifact token with
  '{2}, {T}, Sacrifice this token: You gain 3 life.'"
- **CR 707.2** - a copy "acquires the copiable values of the original
  object's characteristics" - what "create a token that's a copy of ..."
  needs and this parser does not read, so it fails closed rather than
  creating a blank token.
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - one unreadable clause among several
  takes the whole effect down with it.
- **CR 603.6a** - the enters-the-battlefield trigger event, which does not
  care whether what entered was a card or a token (CR 110.1).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent, parse_abilities
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.effects import (
    EFFECTS,
    TRIGGER_EFFECTS,
    parse_mixed_effect,
    parse_mixed_effect_for_spell,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.cards import card
from tests.scenarios.harness import Scenario


def _triggered_effect_text(card_name: str, event: TriggerEvent) -> str:
    """The real `TriggeredAbility.effect` text for one card's trigger on
    `event`, read off its own printed text the way `test_registry_is_minimal`
    does - not hand-typed, so a test can never quietly drift from the fixture.
    """
    (ability,) = [
        a for a in parse_abilities(card(card_name)) if hasattr(a, "event") and a.event is event
    ]
    return ability.effect


# --------------------------------------------------------------------------
# The four deleted rows stay gone
# --------------------------------------------------------------------------


def test_the_four_token_rows_this_wave_removed_are_gone():
    """A row this parser subsumes is dead weight (see `test_registry_is_minimal.py`
    for the general guard); this pins the four W4 specifically removed so a
    later change cannot silently reintroduce one without this file noticing.
    """
    assert "Spectral Procession" not in EFFECTS
    assert ("Ajani, Nacatl Pariah", TriggerEvent.ENTERS_THE_BATTLEFIELD, "") not in TRIGGER_EFFECTS
    assert ("Drowner of Truth", TriggerEvent.CAST_SPELL, "") not in TRIGGER_EFFECTS
    assert ("Wurmcoil Engine", TriggerEvent.DIES, "") not in TRIGGER_EFFECTS
    # Ocelot Pride and Hangarback Walker keep theirs - their second clause
    # needs a copy or a variable count this wave's parser cannot read.
    assert ("Ocelot Pride", TriggerEvent.BEGINNING_OF_STEP, "") in TRIGGER_EFFECTS
    assert ("Hangarback Walker", TriggerEvent.DIES, "") in TRIGGER_EFFECTS


# --------------------------------------------------------------------------
# Drowner of Truth: quoted rules text on the token
# --------------------------------------------------------------------------


def test_drowner_of_truth_quoted_rules_text_parses_into_two_working_spawn():
    """Drowner of Truth: "create two 0/1 colorless Eldrazi Spawn creature
    tokens with 'Sacrifice this token: Add {C}.'" The quoted sentence is
    CR 111.3's token "text" - copied onto the token's `rules_text` exactly as
    printed, not a hand-written ability - so the token's own sacrifice-for-mana
    ability works once it is on the battlefield.

    This is a direct check of the parsed function rather than a full game:
    `Drowner of Truth`'s trigger never actually reaches the stack in this
    engine, because its intervening *if* - "if {C} was spent to cast it" -
    needs spent-mana tracking `intervening_if_holds` does not have, and CR
    603.4 fails an unreadable condition closed rather than open (see
    `docs/engine-coverage.md`). That gap predates this wave and is not this
    parser's to fix; what this test proves is that *if* the trigger ever did
    fire, the token half is read correctly off the card's own text.
    """
    text = _triggered_effect_text("Drowner of Truth", TriggerEvent.CAST_SPELL)
    effect = parse_mixed_effect(text)
    assert effect is not None

    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack

    triggered_ability = next(
        a
        for a in parse_abilities(card("Drowner of Truth"))
        if hasattr(a, "event") and a.event is TriggerEvent.CAST_SPELL
    )
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=triggered_ability,
        source_name="Drowner of Truth",
        controller="alice",
    )
    effect(scenario.game, ability)

    spawn = [state for state in scenario.game.battlefield if state.name == "Eldrazi Spawn Token"]
    assert len(spawn) == 2
    token = spawn[0]
    assert (token.power, token.toughness) == (0, 1)
    assert token.card.colors == []
    assert token.card.oracle_text == "Sacrifice this token: Add {C}."


# --------------------------------------------------------------------------
# A predefined token, reached by a card that never had a row
# --------------------------------------------------------------------------


def test_generous_ent_creates_a_food_token_off_its_own_text():
    """Generous Ent: "When this creature enters, create a Food token." Never
    had a `machines/effects.py` entry before this wave - tokens were not
    modelled at all when Generous Ent was added to the pool - so this is new
    coverage, not a deleted row. CR 111.10b's predefined Food is now in
    `models/token.py`'s `PREDEFINED` table, reached the same way Treasure and
    the Monster Role already are.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Generous Ent"], battlefield=["Forest"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 6, username="alice")
    scenario.cast_and_resolve("Generous Ent", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger

    food = scenario.find("Food Token", Zone.BATTLEFIELD)
    assert food.card.types == [Type.ARTIFACT]
    assert food.card.subtypes == ["Food"]
    assert food.card.colors == []
    assert food.card.oracle_text == "{2}, {T}, Sacrifice this token: You gain 3 life."


# --------------------------------------------------------------------------
# A token entering is a creature entering (CR 110.1, CR 603.6a)
# --------------------------------------------------------------------------


def test_a_created_token_fires_another_permanents_enters_trigger():
    """Guide of Souls: "Whenever another creature you control enters, you gain
    1 life and get {E}." A token is a permanent exactly as a card is one
    (CR 110.1), so three Spirits from Spectral Procession fire it three times -
    the interaction the task flagged as most likely to be missed if token
    creation and the "enters" trigger were wired up independently.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spectral Procession"],
            battlefield=["Plains"] * 6 + ["Guide of Souls"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    life_before = alice.life

    sources = scenario.untapped_sources(*["Plains"] * 6, username="alice")
    scenario.cast_and_resolve("Spectral Procession", *sources, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()

    spirits = [state for state in scenario.game.battlefield if state.name == "Spirit Token"]
    assert len(spirits) == 3
    assert alice.life == life_before + 3


# --------------------------------------------------------------------------
# Fail closed: a copy clause or a variable count takes the whole effect down
# --------------------------------------------------------------------------


def test_ocelot_prides_full_text_fails_closed_because_of_its_copy_clause():
    """Ocelot Pride: "create a 1/1 white Cat creature token. Then if you have
    the city's blessing, for each token you control that entered this turn,
    create a token that's a copy of it." Its first sentence alone is exactly
    `_parse_token_clause`'s shape; its second needs a token *copy* (CR 707.2)
    and a variable count this wave does not read.

    CR 608.2c has no notion of running half an effect, so `parse_mixed_effect`
    on the *whole* printed text must come back `None` - not the first
    sentence's tokens with the second silently dropped. This is a direct check
    of the parser, independent of `ocelot_pride_end_step`'s hand-written row,
    which is what actually runs in a real game and is untouched by this wave
    (see `test_tokens.py::test_ocelot_pride_creates_a_cat_at_the_end_step`).
    The row exists *because* this is what the fallback would do if it did not:
    nothing, cleanly, rather than half of the card's text.
    """
    text = _triggered_effect_text("Ocelot Pride", TriggerEvent.BEGINNING_OF_STEP)
    assert "copy of it" in text.lower()
    assert parse_mixed_effect(text) is None


def test_hangarback_walkers_full_text_fails_closed_because_of_its_count():
    """Hangarback Walker: "create a 1/1 colorless Thopter artifact creature
    token with flying for each +1/+1 counter on this creature." The count is
    not a `_COUNT` word this parser reads - it depends on the permanent's own
    counters, read at resolution by `hangarback_dies` - so the whole clause,
    tail included, must fail rather than create exactly one Thopter and drop
    the "for each" silently.
    """
    text = _triggered_effect_text("Hangarback Walker", TriggerEvent.DIES)
    assert "for each" in text.lower()
    assert parse_mixed_effect(text) is None


def test_repudiates_copy_clause_fails_closed():
    """Repudiate // Replicate: "Create a token that's a copy of target
    creature you control." The whole spell is this one sentence, and it names
    a copy (CR 707.2) this parser explicitly refuses before even trying the
    noun-phrase regex - not because "target" fails to match (the targeted
    clause parser is tried first and also does not cover "create"), but
    because `_parse_token_clause` bails out on "copy of" by name.
    """
    assert parse_mixed_effect_for_spell(card("Repudiate").oracle_text or "") is None


# --------------------------------------------------------------------------
# Multi-token and keyword-halves regressions, still exercised by name
# --------------------------------------------------------------------------


def test_wurmcoil_engines_own_dies_trigger_creates_both_wurms_with_their_own_keyword():
    """Wurmcoil Engine, on the real permanent this time (not a token copy, which
    `test_tokens.py` already covers) - "create a 3/3 ... token with deathtouch
    and a 3/3 ... token with lifelink." CR 608.2c's clause split cuts the
    sentence at "and" into two noun phrases, and `_parse_token_clause` reads
    each on its own - proof the split does not need "create" repeated on the
    second half to work.
    """
    scenario = Scenario().player("alice", battlefield=["Wurmcoil Engine"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurmcoil = scenario.creature("Wurmcoil Engine", "alice")

    scenario.game.destroy(wurmcoil)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    wurms = [state for state in scenario.game.battlefield if state.name == "Phyrexian Wurm Token"]
    assert len(wurms) == 2
    assert all((w.power, w.toughness) == (3, 3) for w in wurms)
    assert all(w.card.types == [Type.ARTIFACT, Type.CREATURE] for w in wurms)
    assert all(w.card.colors == [] for w in wurms)
    keyworded = {Keyword.DEATHTOUCH: 0, Keyword.LIFELINK: 0}
    for wurm in wurms:
        for keyword in keyworded:
            if has_keyword(wurm, keyword):
                keyworded[keyword] += 1
    assert keyworded == {Keyword.DEATHTOUCH: 1, Keyword.LIFELINK: 1}
