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
fail-closed guarantee the task asked to be proven rather than assumed:
Hangarback Walker's full printed text refusing to parse at all, variable count
included, so it can never be half-executed if its table row were ever removed.

A later wave built *ascend* and the city's blessing (CR 702.131) end to end -
`Player.has_citys_blessing`, `CardState.turn_entered`, and `token_copy_of` - so
Ocelot Pride's second sentence, "Then if you have the city's blessing, for
each token you control that entered this turn, create a token that's a copy
of it.", is readable too now (`_parse_city_blessing_token_copy_clause`) and no
longer fails closed; its row is gone. See `tests/scenarios/test_ascend.py` for
that mechanic end to end, and
`test_ocelot_prides_full_text_now_parses_as_one_ability` below for the parser
check this file used to run the other way.

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
  needs. `_parse_token_clause` still refuses this shape outright (it fails
  closed rather than creating a blank token); `_parse_city_blessing_token_copy_clause`
  reads Ocelot Pride's specific "copy of it" shape through `token_copy_of`.
- **CR 702.131b, CR 702.131c** - *ascend*'s "any time you control ten or more
  permanents ... you get the city's blessing for the rest of the game", and
  the city's blessing as a designation nothing ever takes away.
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - one unreadable clause among several
  takes the whole effect down with it.
- **CR 603.6a** - the enters-the-battlefield trigger event, which does not
  care whether what entered was a card or a token (CR 110.1).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent, parse_abilities, parse_mana_abilities
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.effects import (
    EFFECTS,
    TRIGGER_EFFECTS,
    parse_mixed_effect,
    parse_mixed_effect_for_spell,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Supertype, Type
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
    # Ocelot Pride's row is gone too, now that ascend and the city's blessing
    # are built (see test_ascend.py): both of its sentences are readable off
    # its own printed text with no row. Hangarback Walker's row went with EP-01
    # R3 T8: the token "for each counter on it/this creature" reader counts
    # the permanent's own last-known counters at resolution, so its printed
    # text reads with no row (test_registry_is_minimal.py's dead-weight rule).
    assert ("Ocelot Pride", TriggerEvent.BEGINNING_OF_STEP, "") not in TRIGGER_EFFECTS
    assert ("Hangarback Walker", TriggerEvent.DIES, "") not in TRIGGER_EFFECTS


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
    it builds the `AbilityOnStack` by hand instead of casting the card and
    letting its intervening *if* - "if {C} was spent to cast it" - decide
    whether the trigger reaches the stack at all (`machines/triggers.
    intervening_if_holds` now reads that off `Game.cast_record`; see
    `tests/scenarios/test_intervening_if.py` for the full-game version, both
    branches). What this test proves is narrower and still useful on its own:
    the token half is read correctly off the card's own text, independent of
    whether the trigger fires.
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


def test_ocelot_prides_full_text_now_parses_as_one_ability():
    """Ocelot Pride: "create a 1/1 white Cat creature token. Then if you have
    the city's blessing, for each token you control that entered this turn,
    create a token that's a copy of it." Its first sentence is
    `_parse_token_clause`'s ordinary shape; its second is
    `_parse_city_blessing_token_copy_clause`'s (CR 702.131, CR 707.2), now
    that *ascend*, the city's blessing, and "entered this turn" are all built.

    Both clauses read, so `parse_mixed_effect` on the *whole* printed text
    comes back a real effect, not `None` - this is what makes it safe for the
    card to have no `TRIGGER_EFFECTS` row at all: `trigger_effect_for`'s
    fallback reaches the whole paragraph, not half of it (CR 608.2c). See
    `tests/scenarios/test_ascend.py` for the effect run end to end through a
    real game.
    """
    text = _triggered_effect_text("Ocelot Pride", TriggerEvent.BEGINNING_OF_STEP)
    assert "copy of it" in text.lower()
    assert parse_mixed_effect(text) is not None


def test_hangarback_walkers_full_text_reads_its_count_off_its_own_counters():
    """Hangarback Walker: "create a 1/1 colorless Thopter artifact creature
    token with flying for each +1/+1 counter on this creature." The count
    depends on the permanent's own counters (last known, CR 603.10a), which the
    token "for each ... counter on it/this creature" reader now counts at
    resolution - so the clause reads whole, "for each" included, rather than
    failing closed (the earlier version of this test, which asserted the
    fail-closed state, stood in for the reader that did not exist yet; the
    counts are proven in test_ep01_r3_amounts_and_riders.py).
    """
    text = _triggered_effect_text("Hangarback Walker", TriggerEvent.DIES)
    assert "for each" in text.lower()
    assert parse_mixed_effect(text) is not None


def test_repudiates_copy_clause_fails_closed():
    """`card("Repudiate")` resolves to the *combined* "Repudiate // Replicate"
    printing (`tests/cards.pool`'s own front-face alias), whose top-level
    `oracle_text` is blank for a split card (CR 709.3b: only the chosen
    half's characteristics exist) - `.oracle_text or ""` is `""`, so this is
    really asserting that empty text parses to nothing, not anything specific
    about copying. See `test_replicate_creates_a_token_copy_of_the_target`
    below for the real per-face text, which now reads
    (`_parse_create_token_copy_of_target_clause`) - `_parse_token_clause`
    still bails out on any "copy of" phrase by name, unchanged; the new
    parser is a different function entirely, tried alongside it.
    """
    assert parse_mixed_effect_for_spell(card("Repudiate").oracle_text or "") is None


def test_replicate_creates_a_token_copy_of_the_target():
    """Replicate (the sorcery half): "Create a token that's a copy of target
    creature you control." CR 707.2: the copy shares the original's copiable
    values - same name, same power and toughness - but is a fresh object with
    none of the original's counters or damage.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Repudiate // Replicate"],
            battlefield=["Grizzly Bears", "Forest", "Forest", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Repudiate")
    casting.cast_as_split_half("Replicate")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest", "Island"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    copies = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Grizzly Bears" and state is not bears
    ]
    assert len(copies) == 1
    assert copies[0].token
    assert copies[0].power == 2
    assert copies[0].toughness == 2


def test_astral_dragon_creates_two_type_and_pt_overridden_copies():
    """Astral Dragon (pool card): "Project Image — When this creature enters,
    create two tokens that are copies of target noncreature permanent,
    except they're 3/3 Dragon creatures in addition to their other types,
    and they have flying."

    This is the family `_CREATE_TOKEN_COPIES_EXCEPT_RE` used to refuse
    outright: its count was digits/a/an only (a word like "two" was
    rejected), its phrase was pinned to "target creature you control" (Sol
    Ring, targeted here, is neither a creature nor "you control" qualified -
    "target noncreature permanent" is a different restriction), and its
    "except" tail only read a *quoted* granted ability, never an unquoted
    type/power/toughness override. `_read_token_copy_except`'s `_TOKEN_COPY_
    EXCEPT_TYPE_PT_RE` half is what reads this one - CR 707.9b's "some copy
    effects modify a characteristic as part of the copying process", and
    CR 205.1b's "in addition to its other types" is why the copy is still an
    artifact too, not only a Dragon creature.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Astral Dragon"],
            battlefield=["Sol Ring"] + ["Island"] * 8,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources(*["Island"] * 8)

    scenario.choose_trigger_targets("Astral Dragon", [sol_ring])
    scenario.cast_and_resolve("Astral Dragon", *sources)
    scenario.pass_until_resolved()

    copies = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Sol Ring" and state is not sol_ring
    ]
    assert len(copies) == 2
    for copy in copies:
        assert copy.token
        assert copy.power == 3
        assert copy.toughness == 3
        characteristics = scenario.game.characteristics_of(copy)
        assert Type.ARTIFACT in characteristics.types  # CR 205.1b: kept
        assert Type.CREATURE in characteristics.types  # CR 707.9b: added
        assert "Dragon" in characteristics.subtypes
        assert has_keyword(copy, Keyword.FLYING, scenario.game)
        # The original's own ability line is still part of the copiable
        # values (CR 707.2), sitting alongside the added "Flying" line.
        assert "{T}: Add {C}{C}." in copy.card.oracle_text
    # Sol Ring itself is untouched (CR 707.2b: the copy is a snapshot).
    assert sol_ring.power is None
    assert not scenario.game.characteristics_of(sol_ring).is_creature


def test_rebuild_the_city_copies_the_land_it_chose_not_a_second_target():
    """Rebuild the City (off-pool, added with `scripts/add_card.py`, verified
    against its own printed text): "Choose target land. Create three tokens
    that are copies of it, except they're 3/3 creatures in addition to their
    other types and they have vigilance and menace."

    Proves the other half of the same family: `_parse_choose_target_then_
    create_token_copies_pair`'s "it" reads back the ability's own sole
    target (CR 607.1 anaphora), read off the *first* sentence - "Choose
    target land." - rather than a second "target" word the second sentence
    never prints; and the "except" tail's type/P-T override with no named
    subtype at all ("3/3 creatures", not "3/3 `<subtype>` creatures") still
    reads through `_TOKEN_COPY_EXCEPT_TYPE_PT_RE`'s optional subtype group.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rebuild the City"],
            battlefield=["Forest", "Swamp", "Mountain", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Forest", "Swamp", "Mountain", "Island", "Island", "Island")

    scenario.cast_and_resolve("Rebuild the City", *sources, targets=[forest])

    copies = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Forest" and state is not forest
    ]
    assert len(copies) == 3
    for copy in copies:
        assert copy.token
        assert copy.power == 3
        assert copy.toughness == 3
        characteristics = scenario.game.characteristics_of(copy)
        assert Type.LAND in characteristics.types  # CR 205.1b: kept
        assert Type.CREATURE in characteristics.types  # CR 707.9b: added
        assert characteristics.subtypes == ("Forest",)  # no added subtype
        assert has_keyword(copy, Keyword.VIGILANCE, scenario.game)
        assert has_keyword(copy, Keyword.MENACE, scenario.game)
    # The original land itself is untouched and still just a land.
    assert not scenario.game.characteristics_of(forest).is_creature


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


# --------------------------------------------------------------------------
# Heartwood: a new CR 111.10 predefined token (CR 111.10x, Reality Fracture)
# --------------------------------------------------------------------------


def test_hungering_puppetbeast_creates_a_heartwood_token_off_its_own_text():
    """Hungering Puppetbeast: "When this creature enters, create a Heartwood
    token." CR 111.10x: "A Heartwood token is a red and green Heartwood
    artifact token with '{T}: Add {R} or {G}.'" - a new row in `PREDEFINED`,
    reached through the same `predefined_name in PREDEFINED` branch of
    `_parse_token_clause` that Treasure and Food already use, so no new
    parser code is needed to read it.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Hungering Puppetbeast"], battlefield=["Forest"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 5, username="alice")
    scenario.cast_and_resolve("Hungering Puppetbeast", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger

    heartwood = scenario.find("Heartwood Token", Zone.BATTLEFIELD)
    assert heartwood.card.types == [Type.ARTIFACT]
    assert heartwood.card.subtypes == ["Heartwood"]
    assert set(heartwood.card.colors) == {Color.RED, Color.GREEN}
    assert heartwood.card.oracle_text == "{T}: Add {R} or {G}."
    assert not heartwood.tapped


def test_tenured_tethermage_creates_two_tapped_heartwood_tokens():
    """Tenured Tethermage: "When this creature enters, you may sacrifice a
    land. If you do, create two tapped Heartwood tokens." Differently worded
    from Hungering Puppetbeast's own trigger (a reflexive "if you do", a
    count of two, and "tapped") - proof the predefined-token row is read
    generically and not fitted to one card's exact sentence, composed here
    with `_parse_conditional_sacrifice_clause`'s existing CR 118.12 machinery.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Tenured Tethermage"], battlefield=["Mountain", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Forest", "Forest", username="alice")
    scenario.will_take_the_may(True)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, username="alice")
    scenario.will_choose_cards(forest)
    scenario.cast_and_resolve("Tenured Tethermage", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger, with its reflexive sacrifice

    heartwoods = [state for state in scenario.game.battlefield if state.name == "Heartwood Token"]
    assert len(heartwoods) == 2
    assert all(token.tapped for token in heartwoods)
    assert forest.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# "Land creature" tokens (CR 205.1a's two-type shape) - not a new mechanic,
# but a two-type combination `_parse_generic_token_descriptor` never read:
# the artifact/creature branch had no land-creature twin.
# --------------------------------------------------------------------------


def test_awaken_the_woods_creates_x_land_creature_tokens():
    """Awaken the Woods (off-set, not in the fra pool): "Create X 1/1 green
    Forest Dryad land creature tokens." X here is CR 107.3a's announced X -
    already substituted by `effect_for` before this clause is ever read - so
    this exercises only the "land creature" shape itself: two card types
    read off one noun phrase the same way "artifact creature" already is,
    and CR 305.6's basic-land mana ability granted intrinsically by the
    "Forest" subtype rather than a quoted ability on the token.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Awaken the Woods"], battlefield=["Forest"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 4, username="alice")
    casting = scenario.cast("Awaken the Woods")
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    dryads = [state for state in scenario.game.battlefield if state.name == "Forest Dryad Token"]
    assert len(dryads) == 2
    dryad = dryads[0]
    assert dryad.card.types == [Type.CREATURE, Type.LAND]
    assert dryad.card.subtypes == ["Forest", "Dryad"]
    assert (dryad.power, dryad.toughness) == (1, 1)
    assert set(dryad.card.colors) == {Color.GREEN}
    # CR 305.6: the basic land type Forest carries its mana ability
    # intrinsically - nothing was printed on the token for it.
    assert dryad.card.oracle_text is None
    mana_abilities = parse_mana_abilities(dryad.card)
    assert len(mana_abilities) == 1
    assert mana_abilities[0].options == [[Color.GREEN]]


def test_verdant_krakens_upkeep_trigger_creates_a_forest_tentacle_land_creature_token():
    """Verdant Kraken (on-set): "At the beginning of each player's upkeep, you
    create a 3/3 green Forest Tentacle land creature token." Differently
    worded from Awaken the Woods (a leading "you", a fixed count instead of
    X, a different subtype pair) - proof the same "land creature" reader
    handles both without being fitted to either card's own sentence.
    """
    text = _triggered_effect_text("Verdant Kraken", TriggerEvent.BEGINNING_OF_STEP)
    effect = parse_mixed_effect(text)
    assert effect is not None

    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack

    triggered_ability = next(
        a
        for a in parse_abilities(card("Verdant Kraken"))
        if hasattr(a, "event") and a.event is TriggerEvent.BEGINNING_OF_STEP
    )
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=triggered_ability,
        source_name="Verdant Kraken",
        controller="alice",
    )
    effect(scenario.game, ability)

    tentacle = scenario.find("Forest Tentacle Token", Zone.BATTLEFIELD)
    assert tentacle.card.types == [Type.CREATURE, Type.LAND]
    assert tentacle.card.subtypes == ["Forest", "Tentacle"]
    assert (tentacle.power, tentacle.toughness) == (3, 3)
    assert set(tentacle.card.colors) == {Color.GREEN}
    mana_abilities = parse_mana_abilities(tentacle.card)
    assert len(mana_abilities) == 1
    assert mana_abilities[0].options == [[Color.GREEN]]


# --------------------------------------------------------------------------
# CR 111.9's named appositive: "create <Name>, a <descriptor> token."
# --------------------------------------------------------------------------


def test_drizzt_do_urdens_appositive_names_and_tokens_guenhwyvar():
    """Drizzt Do'Urden (off-set, not in the fra pool): "When Drizzt enters,
    create Guenhwyvar, a legendary 4/1 green Cat creature token with
    trample." CR 111.9's own example shape - the token's name leads the
    sentence as its own noun, not `_TOKEN_CLAUSE_RE`'s trailing "named
    <Name>" - which `_TOKEN_CLAUSE_RE` itself explicitly does not read.
    """
    text = _triggered_effect_text("Drizzt Do'Urden", TriggerEvent.ENTERS_THE_BATTLEFIELD)
    effect = parse_mixed_effect(text)
    assert effect is not None

    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack

    triggered_ability = next(
        a
        for a in parse_abilities(card("Drizzt Do'Urden"))
        if hasattr(a, "event") and a.event is TriggerEvent.ENTERS_THE_BATTLEFIELD
    )
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=triggered_ability,
        source_name="Drizzt Do'Urden",
        controller="alice",
    )
    effect(scenario.game, ability)

    guenhwyvar = scenario.find("Guenhwyvar", Zone.BATTLEFIELD)
    assert guenhwyvar.card.name == "Guenhwyvar"
    assert Supertype.LEGENDARY in guenhwyvar.card.supertypes
    assert guenhwyvar.card.subtypes == ["Cat"]
    assert (guenhwyvar.power, guenhwyvar.toughness) == (4, 1)
    assert set(guenhwyvar.card.colors) == {Color.GREEN}
    assert has_keyword(guenhwyvar, Keyword.TRAMPLE)


def test_jiang_yanggu_never_alones_appositive_names_and_tokens_mowu():
    """Jiang Yanggu, Never Alone (on-set): "When Jiang Yanggu enters, create
    Mowu, a legendary 3/3 green Dog creature token." Differently worded from
    Drizzt's own trigger (no tail keyword at all, a different name, P/T,
    color, and subtype) - proof the appositive reader is not fitted to
    either card's own sentence.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Jiang Yanggu, Never Alone"], battlefield=["Forest"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 4, username="alice")
    scenario.cast_and_resolve("Jiang Yanggu, Never Alone", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger

    mowu = scenario.find("Mowu", Zone.BATTLEFIELD)
    assert mowu.card.name == "Mowu"
    assert Supertype.LEGENDARY in mowu.card.supertypes
    assert mowu.card.subtypes == ["Dog"]
    assert (mowu.power, mowu.toughness) == (3, 3)
    assert set(mowu.card.colors) == {Color.GREEN}


# --------------------------------------------------------------------------
# A named artifact token with a quoted mana ability - already generic
# --------------------------------------------------------------------------


def test_goblin_kaboomists_named_artifact_token_reads_its_quoted_ability():
    """Off-set: Goblin Kaboomist's upkeep trigger opens "create a colorless
    artifact token named Land Mine with '{R}, Sacrifice this token: ...'." -
    the same "named `<Name>` with `<quoted ability>`" shape Kwia Vigorbloom's
    own Lotus token uses below, read here off only the real card's first
    printed sentence (the coin flip after it is a separate, unmodelled
    mechanic - out of scope here, and irrelevant to whether the token itself
    reads).
    """
    triggered_ability = next(
        a
        for a in parse_abilities(card("Goblin Kaboomist"))
        if hasattr(a, "event") and a.event is TriggerEvent.BEGINNING_OF_STEP
    )
    # The token clause only - the coin flip after it is a separate,
    # unmodelled mechanic (out of scope here), split off at the closing
    # quote so the quoted ability's own internal "." is not mistaken for the
    # sentence boundary.
    first_sentence = triggered_ability.effect.split('." ', 1)[0] + '."'
    assert "Land Mine" in first_sentence
    effect = parse_mixed_effect(first_sentence)
    assert effect is not None

    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack

    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=triggered_ability,
        source_name="Goblin Kaboomist",
        controller="alice",
    )
    effect(scenario.game, ability)

    land_mine = scenario.find("Land Mine", Zone.BATTLEFIELD)
    assert land_mine.card.types == [Type.ARTIFACT]
    assert land_mine.card.subtypes == []
    assert land_mine.card.colors == []
    assert land_mine.card.oracle_text == (
        "{R}, Sacrifice this token: This token deals 2 damage to target "
        "attacking creature without flying."
    )


def test_kwia_vigorblooms_lotus_token_reads_its_quoted_ability():
    """Kwia Vigorbloom (on-set): "Whenever you gain life, create a colorless
    artifact token named Lotus with '{T}, Sacrifice this token: Add three
    mana of any one color.' This ability triggers only once each turn."
    Differently worded from Goblin Kaboomist's own token (no "tapped", a
    different quoted ability, a "gains life" trigger rather than an upkeep
    one, and the once-per-turn restriction `abilities.py` already strips into
    its own field) - proof the same reader handles both.
    """
    scenario = Scenario().player("alice", battlefield=["Kwia Vigorbloom"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("alice", 3)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    lotus = scenario.find("Lotus", Zone.BATTLEFIELD)
    assert lotus.card.name == "Lotus"
    assert lotus.card.types == [Type.ARTIFACT]
    assert lotus.card.subtypes == []
    assert lotus.card.colors == []
    assert lotus.card.oracle_text == "{T}, Sacrifice this token: Add three mana of any one color."


# --------------------------------------------------------------------------
# "If it isn't a token, create N tokens that are copies of it" (CR 707.2)
# --------------------------------------------------------------------------


def test_gruff_triplets_enters_trigger_copies_itself_when_its_not_already_a_token():
    """Off-set: Gruff Triplets: "When this creature enters, if it isn't a
    token, create two tokens that are copies of it." `intervening_if_holds`'s
    new "it isn't a token" clause and `_parse_self_copy_token_clause`'s "N
    tokens that are copies of it", proven together end to end.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Gruff Triplets"], battlefield=["Forest"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 6, username="alice")
    scenario.cast_and_resolve("Gruff Triplets", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger

    triplets = [state for state in scenario.game.battlefield if state.name == "Gruff Triplets"]
    assert len(triplets) == 3
    assert sum(1 for t in triplets if t.token) == 2
    assert sum(1 for t in triplets if not t.token) == 1


def test_gruff_triplets_token_copy_does_not_copy_itself_again():
    """The copies Gruff Triplets makes are themselves tokens, so their own
    "if it isn't a token" intervening *if* is false and neither one makes two
    more - `intervening_if_holds`'s "it isn't a token" reads `CardState.token`
    directly rather than checking only the original printing's own name.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Gruff Triplets"], battlefield=["Forest"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 6, username="alice")
    scenario.cast_and_resolve("Gruff Triplets", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger fires only for the nontoken original

    assert not scenario.game.stack
    triplets = [state for state in scenario.game.battlefield if state.name == "Gruff Triplets"]
    assert len(triplets) == 3


def test_sphinx_of_false_conclusions_dies_trigger_copies_itself_when_its_not_already_a_token():
    """On-set: Sphinx of False Conclusions: "When this creature dies, if it
    isn't a token, create a token that's a copy of it." Differently worded
    from Gruff Triplets (a dies trigger instead of an enters one, a count of
    one instead of two, "a copy" instead of "copies") - proof the reader is
    not fitted to either card's own sentence. The dies trigger's own "it"
    needs CR 113.7a/608.2h's look-back, which the ETB version above never
    exercises.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sphinx of False Conclusions"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sphinx = scenario.creature("Sphinx of False Conclusions", "alice")

    scenario.game.destroy(sphinx)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    copy = next(
        state for state in scenario.game.battlefield if state.name == "Sphinx of False Conclusions"
    )
    assert copy.token
    assert copy is not sphinx
    assert (copy.power, copy.toughness) == (sphinx.power, sphinx.toughness)


# --------------------------------------------------------------------------
# "For each creature target player controls, create a token copy of it"
# --------------------------------------------------------------------------


def test_clone_legion_copies_every_creature_target_player_controls():
    """Off-set: Clone Legion: "For each creature target player controls,
    create a token that's a copy of that creature." No "except" tail at all -
    the plain shape, targeting an opponent's whole board.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Clone Legion"], battlefield=["Island"] * 9)
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Island"] * 9, username="alice")
    scenario.cast_and_resolve("Clone Legion", *sources, username="alice", targets=["bob"])

    alice_creatures = scenario.game.permanents_controlled_by("alice")
    bears_copy = next(state for state in alice_creatures if state.name == "Grizzly Bears")
    giant_copy = next(state for state in alice_creatures if state.name == "Hill Giant")
    assert bears_copy.token and giant_copy.token
    assert (bears_copy.power, bears_copy.toughness) == (2, 2)
    assert (giant_copy.power, giant_copy.toughness) == (3, 3)


def test_face_yourself_copies_with_haste_and_a_granted_sacrifice_trigger():
    """On-set: Face Yourself: "For each creature target player controls,
    create a token that's a copy of that creature, except it has haste and
    'At the beginning of the end step, if you don't control a planeswalker,
    sacrifice this creature.'" Differently worded from Clone Legion (a mixed
    keyword-then-quoted-ability tail neither existing copy-tail reader
    handles alone) - proof `_parse_copy_added_ability_lines` reads both
    halves of the mix.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Face Yourself"], battlefield=["Mountain"] * 7)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Mountain"] * 7, username="alice")
    scenario.cast_and_resolve("Face Yourself", *sources, username="alice", targets=["bob"])

    copy = next(
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Grizzly Bears"
    )
    assert copy.token
    assert has_keyword(copy, Keyword.HASTE, scenario.game)
    assert (
        "At the beginning of the end step, if you don't control a planeswalker, "
        "sacrifice this creature." in (copy.card.oracle_text or "")
    )


# --------------------------------------------------------------------------
# CR 107.3f's own X: "Create X ... tokens ..., where X is <expr>."
# --------------------------------------------------------------------------


def test_charisma_bobbleheads_activated_ability_creates_x_tokens_by_bobbleheads_controlled():
    """Off-set: Charisma Bobblehead's own second ability: "{4}, {T}: Create X
    1/1 white Soldier creature tokens, where X is the number of Bobbleheads
    you control." No `{X}` in the card's own cost - this is CR 107.3f's *own-
    text* X, read through the already-shared `count_expression`, not CR
    107.3a's announced one.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Charisma Bobblehead"] + ["Plains"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Plains"] * 4, username="alice")
    bobblehead = scenario.find("Charisma Bobblehead", Zone.BATTLEFIELD, username="alice")
    scenario.activate(bobblehead, *sources, index=1, username="alice")
    scenario.resolve_top()

    soldiers = [state for state in scenario.game.battlefield if state.name == "Soldier Token"]
    assert len(soldiers) == 1
    assert (soldiers[0].power, soldiers[0].toughness) == (1, 1)


def test_germinate_recruits_creates_x_cadets_by_life_gained_this_turn():
    """On-set: Germinate Recruits: "Create X 2/2 colorless Wizard Soldier
    creature tokens named Cadet, where X is the amount of life you gained
    this turn." Differently worded from Charisma Bobblehead (a named token, a
    spell rather than an activated ability, and CR 107.3f's own new
    "amount of life you gained this turn" magnitude rather than an already-
    supported "number of ... you control") - proof the "where X is ..." token
    reader composes with a brand new `count_expression` shape too.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Germinate Recruits"], battlefield=["Plains"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 5)
    sources = scenario.untapped_sources(*["Plains"] * 3, username="alice")
    scenario.cast_and_resolve("Germinate Recruits", *sources, username="alice")

    cadets = [state for state in scenario.game.battlefield if state.name == "Cadet"]
    assert len(cadets) == 5
    assert all((c.power, c.toughness) == (2, 2) for c in cadets)
    assert all(c.card.subtypes == ["Wizard", "Soldier"] for c in cadets)


def test_germinate_recruits_creates_no_tokens_with_no_life_gained():
    """No life gained this turn is X = 0 (CR 107.2's own "0 instead" for an
    amount that can't be determined otherwise) - CR 111.5/701.7a both make
    "create zero tokens" a legal no-op, not an error."""
    scenario = (
        Scenario()
        .player("alice", hand=["Germinate Recruits"], battlefield=["Plains"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Plains"] * 3, username="alice")
    scenario.cast_and_resolve("Germinate Recruits", *sources, username="alice")

    assert not any(state.name == "Cadet" for state in scenario.game.battlefield)


# --------------------------------------------------------------------------
# "If this spell was cast from a graveyard, put counters on {that token|each
# of them}" - CR 601.2, CR 702.34a's flashback
# --------------------------------------------------------------------------


def test_retrieve_the_esper_puts_two_counters_only_when_cast_from_the_graveyard():
    """Off-set: Retrieve the Esper: "Create a 3/3 blue Robot Warrior artifact
    creature token. Then if this spell was cast from a graveyard, put two
    +1/+1 counters on that token." A literal flat count, no divisor tail -
    the plain shape, and read whole ahead of the ordinary per-clause split
    (the sentence boundary is a period `_CLAUSE_SEPARATOR` would cut on too).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Retrieve the Esper"], battlefield=["Island"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Island"] * 4, username="alice")
    scenario.cast_and_resolve("Retrieve the Esper", *sources, username="alice")

    robot = scenario.find("Robot Warrior Token", Zone.BATTLEFIELD)
    assert robot.counter_count("+1/+1") == 0  # cast from hand: no bonus


def test_retrieve_the_esper_from_the_graveyard_gets_its_two_counters():
    """The same card, cast via flashback out of the graveyard this time -
    `Game.cast_record(spell).origin_zone` is `Zone.GRAVEYARD`, so the second
    sentence's condition is true and the token gets its two counters."""
    scenario = (
        Scenario()
        .player("alice", graveyard=["Retrieve the Esper"], battlefield=["Island"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Island"] * 6, username="alice")
    casting = scenario.cast("Retrieve the Esper", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    robot = scenario.find("Robot Warrior Token", Zone.BATTLEFIELD)
    assert robot.counter_count("+1/+1") == 2


def test_recursive_recruitment_puts_counters_by_graveyard_size_when_flashed_back():
    """On-set: Recursive Recruitment: "Create two 2/2 colorless Wizard
    Soldier creature tokens named Cadet. If this spell was cast from a
    graveyard, put a +1/+1 counter on each of them for every three cards in
    your graveyard." Differently worded from Retrieve the Esper (plural
    "each of them" instead of "that token", no "Then", a "for every three
    cards" divisor instead of a flat count, two tokens instead of one) -
    proof the reader is not fitted to either card's own sentence.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Recursive Recruitment"] + ["Plains"] * 6,
            battlefield=["Island", "Swamp"] + ["Plains"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Swamp", *["Plains"] * 6, username="alice")
    casting = scenario.cast("Recursive Recruitment", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    cadets = [state for state in scenario.game.battlefield if state.name == "Cadet"]
    assert len(cadets) == 2
    # Six Plains left in the graveyard once the spell itself moved to the
    # stack: 6 // 3 = 2 counters on each token.
    assert len(scenario.player("alice").graveyard) == 6
    assert all(cadet.counter_count("+1/+1") == 2 for cadet in cadets)


def test_recursive_recruitment_from_hand_puts_no_counters():
    """Cast for its ordinary mana cost, from the hand - the "cast from a
    graveyard" condition is false, so the Cadets arrive with no counters."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Recursive Recruitment"],
            battlefield=["Island", "Swamp", "Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Swamp", "Plains", "Plains", username="alice")
    scenario.cast_and_resolve("Recursive Recruitment", *sources, username="alice")

    cadets = [state for state in scenario.game.battlefield if state.name == "Cadet"]
    assert len(cadets) == 2
    assert all(cadet.counter_count("+1/+1") == 0 for cadet in cadets)


# --------------------------------------------------------------------------
# "Create ... token, then put counters on each other <subtype> you control"
# --------------------------------------------------------------------------


def test_good_king_mogs_chapter_iv_counters_each_other_moogle_not_itself():
    """Off-set: Summon: Good King Mog XII's own Saga chapter IV: "Put two
    +1/+1 counters on each other Moogle you control." `_parse_put_counters_
    on_group_clause`'s own "other" now excludes the *ability's* source
    (itself, a Moogle) from the group - the different "other" Command the
    Stage's combined parser below needs, which excludes the tokens *this
    same instruction* just created instead.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Summon: Good King Mog XII"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mog = scenario.creature("Summon: Good King Mog XII", "alice")

    chapters = [
        a for a in parse_abilities(card("Summon: Good King Mog XII")) if getattr(a, "chapter", None)
    ]
    chapter_one = next(a for a in chapters if a.chapter == 1)
    chapter_four = next(a for a in chapters if a.chapter == 4)

    from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack

    effect_one = parse_mixed_effect(chapter_one.effect)
    assert effect_one is not None
    ability_one = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=chapter_one,
        source_id=mog.id,
        source_name=mog.name,
        controller="alice",
    )
    effect_one(scenario.game, ability_one)

    moogle_tokens = [state for state in scenario.game.battlefield if state.name == "Moogle Token"]
    assert len(moogle_tokens) == 2

    effect_four = parse_mixed_effect(chapter_four.effect)
    assert effect_four is not None
    ability_four = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=chapter_four,
        source_id=mog.id,
        source_name=mog.name,
        controller="alice",
    )
    effect_four(scenario.game, ability_four)

    assert mog.counter_count("+1/+1") == 0
    assert all(token.counter_count("+1/+1") == 2 for token in moogle_tokens)


def test_command_the_stage_counters_other_wizard_tokens_not_the_one_just_made():
    """On-set: Command the Stage: "Create a 2/2 colorless Wizard Soldier
    creature token named Cadet, then put a +1/+1 counter on each other
    Wizard token you control." A different "other" from Good King Mog's
    (excludes the token(s) this same spell just created, not an ability's
    own source), and the sentence composes with a *second*, unrelated
    triggered ability printed below it on the same card -
    `_strip_trailing_standalone_triggered_ability` keeps that second
    ability's own unread text from poisoning the first paragraph's own
    resolution (CR 608.2c; CR 112.6c, an ability that functions from the
    graveyard - not built here, S5's own scope).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Command the Stage"],
            battlefield=["Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Command the Stage", *sources, username="alice")

    cadet = scenario.find("Cadet", Zone.BATTLEFIELD, username="alice")
    assert cadet.counter_count("+1/+1") == 0


def test_command_the_stage_boosts_a_pre_existing_wizard_token():
    """A Wizard token already on the battlefield before Command the Stage
    resolves is an *other* Wizard token and gets the counter; the new Cadet
    (also a Wizard) does not, proving the exclusion is by the newly created
    tokens' own identity and not by name or subtype alone.
    """
    from magic_cards_model.machines.effects import (
        _parse_generic_token_descriptor,
        create_tokens,
    )

    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Command the Stage"],
            battlefield=["Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    definition = _parse_generic_token_descriptor(
        ["2/2", "colorless", "Wizard", "Soldier", "creature"], None
    )
    assert definition is not None
    (pre_existing_cadet,) = create_tokens(scenario.game, definition, "alice")

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Command the Stage", *sources, username="alice")

    cadets = [
        state for state in scenario.game.battlefield if state.card.subtypes == ["Wizard", "Soldier"]
    ]
    assert len(cadets) == 2
    new_cadet = next(c for c in cadets if c.id != pre_existing_cadet.id)
    assert pre_existing_cadet.counter_count("+1/+1") == 1
    assert new_cadet.counter_count("+1/+1") == 0
