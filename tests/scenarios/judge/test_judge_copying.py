"""Judge scenarios: copying a spell and copying a permanent (CR 707).

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#951** - Frontline Heroism + Psychotic Fury (a triggered ability that
  creates a token and then copies the spell that triggered it, retargeting the
  copy onto that token)
- **DDR#986** - Superior Spider-Man + Bringer of the Last Gift (entering the
  battlefield *as a copy* of a card in a graveyard, and the linked "exile that
  card" losing track of a card that has since changed zones)
- **DDR#980** - Jolrael, Voice of Zhalfir + Aggressive Biomancy (a token copy
  of an animated land copies none of the animation, but does get the copy
  effect's own added ETB fight ability)
- **DDR#32** - Clone vs. Purelace and Forerunner of Slaughter (a copy effect
  in layer 1, then two colour-changing effects in layer 5, one of them a
  characteristic-defining ability)
- **DDR#977** - Drafna, Founder of Lat-Nam vs. Flamehold Grappler (a *targeted*
  copy ability whose target spell is countered in response, against an
  untargeted one that copies off last known information)

CR 707.10 is what "copy a spell" means: "put a copy of it onto the stack; a
copy of a spell isn't cast". CR 707.2 is where the copy's values come from: "the
copy acquires the copiable values of the original object's characteristics
and, for an object on the stack, choices made when casting or activating it
(mode, targets, ...)".

Copying is **partly** built, and each test below says which part it is
standing on. DDR#951's own clause parses and runs for real
(`machines/effects._parse_create_token_then_copy_spell_retargeted_clause`), so
its Soldier token and its retargeted copy both happen; what it fails on is one
rules question about the copy's target, recorded in that test's own xfail
reason. The permanent-copying half is the one that is genuinely absent:
`machines/effects._parse_token_clause` refuses outright the moment it sees
"copy of" in a clause (`return None  # CR 707.2 copying needs copiable values
this wave does not read`), and there is no `replacements_of` row for an "enter
as a copy" clause - both confirmed directly below rather than assumed from the
absence of a grep hit. Every CR number here was looked up with
`knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.effects import (
    create_continuous_effect,
    effect_for,
    trigger_effect_for,
)
from magic_cards_model.machines.replacement import replacements_of
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.models.token import TokenState, is_token
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_frontline_heroisms_copy_clause_is_read_off_the_effect_half_of_the_line():
    """DDR#951, the provable half: the copy clause *is* parsed - off the right text.

    Frontline Heroism's second ability is "Whenever you cast a spell that
    targets only a single creature you control, create a 1/1 red Soldier
    creature token with haste, then copy that spell. The copy targets that
    token." `_parse_create_token_then_copy_spell_retargeted_clause` in
    `machines/effects.py` is written for exactly that clause and returns a
    live effect for it.

    What it is given matters: `trigger_effect_for` is a fail-closed,
    whole-clause dispatcher, so handing it the *whole printed line* - the
    "Whenever you cast a spell that targets ..." condition included - reads as
    one unrecognised clause and comes back None. That is not the text the
    engine passes at resolution; `Game` strips the condition and passes the
    effect half, which parses. Both halves are asserted here because an
    earlier version of this file read the None from the whole line as proof
    that spell copying was absent from the engine entirely, which it is not.
    """
    heroism = card("Frontline Heroism")
    lines = heroism.oracle_text.split("\n")
    trigger_text = lines[1]
    assert trigger_text.startswith("Whenever you cast a spell")

    condition, _, effect_text = trigger_text.partition("control, ")
    assert condition.startswith("Whenever you cast a spell that targets")
    assert effect_text.startswith("create a 1/1 red Soldier creature token")

    assert trigger_effect_for("Frontline Heroism", TriggerEvent.CAST_SPELL, trigger_text) is None
    assert trigger_effect_for("Frontline Heroism", TriggerEvent.CAST_SPELL, effect_text) is not None


@pytest.mark.xfail(
    strict=True,
    reason="The trigger fires, the Soldier token is created, and a real second Psychotic Fury "
    "(is_copy, retargeted at the token) does reach the stack - that much works. The copy is "
    "then removed from the stack by CR 608.2b's on-resolution target check ('If the spell or "
    "ability specifies targets, it checks whether the targets are still legal'), because a 1/1 "
    "red Soldier is not the 'target multicolored creature' Psychotic Fury requires, so nothing "
    "ever gains double strike. "
    "Whether that is correct turns on the disposition clause of CR 707.10e ('Some effects copy "
    "a spell or ability and specify a new target for the copy'), whose text this session could "
    "not retrieve past its second sentence - knowledge_search truncates the excerpt before the "
    "clause that says what happens when the specified object is an illegal target for the copy. "
    "Exempting an effect-specified copy target from the CR 608.2b check would be a change to "
    "src/machines, which this test does not own.",
)
def test_frontline_heroism_should_copy_psychotic_fury_onto_a_fresh_token():
    """DDR#951: the copy should hand double strike to a token Kitchen Finks never asked for.

    Psychotic Fury reads "Target multicolored creature gains double strike
    until end of turn. Draw a card." (verified with `resolve_cards`) - a legal
    single-creature target, so Frontline Heroism's trigger fires (CR 603.2),
    making a 1/1 Soldier token and copying Psychotic Fury with the copy
    retargeted onto that token. CR 707.10e is the rule for a copy whose target
    the *effect* names: "Some effects copy a spell or ability and specify a new
    target for the copy. If the spell or ability has more than one target, each
    of the copy's targets must be that player or object." Frontline Heroism is
    that shape - "The copy targets that token" - rather than CR 707.10c's "may
    choose new targets".

    The token receiving double strike despite not being multicolored is
    exactly what tells this apart from Psychotic Fury resolving once, plainly.
    Two mana and a library are not decoration: Psychotic Fury costs {1}{R}, and
    its second sentence is "Draw a card", which on an empty library would lose
    alice the game to CR 704.5b's state-based action and take her whole
    battlefield - the Soldier included - with her.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Psychotic Fury"],
            library=["Forest", "Forest"],
            battlefield=["Frontline Heroism", "Kitchen Finks", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks", "alice")

    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Psychotic Fury", *sources, username="alice", targets=[finks])

    # The trigger resolved first (it went on the stack above the spell that
    # caused it), so the original Psychotic Fury is still waiting underneath
    # the copy Frontline Heroism just made - CR 112.1a: "A copy of a spell is
    # also a spell, even if it has no card associated with it."
    original, copy = scenario.game.stack
    assert (original.name, original.is_copy) == ("Psychotic Fury", False)
    assert (copy.name, copy.is_copy) == ("Psychotic Fury", True)

    soldiers = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if isinstance(state, TokenState)
    ]
    assert len(soldiers) == 1, "the trigger should have made a 1/1 Soldier token"
    (token,) = soldiers
    # CR 707.10e's specified target: the copy points at the token, not at Finks.
    assert copy.targets[0].card_id == token.id

    while scenario.game.stack:
        scenario.resolve_top()

    abilities = scenario.game.characteristics_of(token).abilities
    assert "Double strike" in abilities, "the copy should have targeted the token"


# --------------------------------------------------------------------------
# DDR#986 - Superior Spider-Man + Bringer of the Last Gift
# --------------------------------------------------------------------------


def test_superior_spider_mans_enter_as_a_copy_clause_has_no_replacement_row():
    """DDR#986, the provable half: "enter as a copy" is a replacement effect
    (CR 614.1c) this engine has no row for.

    Superior Spider-Man (verified with `resolve_cards`): "Mind Swap - You may
    have Superior Spider-Man enter as a copy of any creature card in a
    graveyard, except his name is Superior Spider-Man and he's a 4/4 Spider
    Human Hero in addition to his other types. When you do, exile that card."

    CR 614.1c: "Effects that read '[This permanent] enters with . . . ,' 'As
    [this permanent] enters . . . ,' or '[This permanent] enters as . . . '
    are replacement effects." CR 614.12a puts the choice - which graveyard
    card to copy - before the permanent enters, which is exactly why the
    episode's second half works: every Superior Spider-Man entering at once
    picks what to copy before any of them has exiled anything. None of that is
    reachable here: `replacements_of` is empty for this card, so
    `apply_replacements` never sees the clause at all.
    """
    spidey = card("Superior Spider-Man")
    assert "enter as a copy of any creature card in a graveyard" in spidey.oracle_text
    assert replacements_of(spidey) == []


def test_superior_spider_man_enters_as_plain_superior_spider_man():
    """The consequence, played out: no copy, no linked trigger, nothing exiled.

    Without the CR 614.1c replacement, Superior Spider-Man resolves as its own
    printed 4/4 and Bringer of the Last Gift sits untouched in the graveyard.
    Both of the episode's triggers - Bringer's own "when this creature enters"
    and Mind Swap's linked "when you do, exile that card" - are simply absent
    from the stack, which is what the xfail below is measured against.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Superior Spider-Man"],
            graveyard=["Bringer of the Last Gift"],
            battlefield=["Island", "Island", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Swamp", "Swamp", username="alice")
    spidey = scenario.cast_and_resolve("Superior Spider-Man", *sources, username="alice")

    assert spidey.zone is Zone.BATTLEFIELD
    assert (spidey.power, spidey.toughness) == (4, 4)
    assert scenario.stack_names() == []
    assert scenario.pending_triggers == []
    assert [state.name for state in scenario.player("alice").graveyard] == [
        "Bringer of the Last Gift"
    ]


@pytest.mark.xfail(
    strict=True,
    reason="replacements_of('Superior Spider-Man') is empty (proven above), so the CR 614.1c "
    "'enter as a copy' choice is never offered and no copy effect is created - Bringer of the "
    "Last Gift's own enters trigger is never acquired, never goes on the stack, and never "
    "returns the original Bringer from the graveyard.",
)
def test_a_spider_bringer_and_a_real_bringer_can_both_end_up_on_the_battlefield():
    """DDR#986: stack the two triggers so the reanimation beats the exile.

    Superior Spider-Man enters as a copy of the Bringer in alice's graveyard,
    so it is a 4/4 carrying Bringer's own "when this creature enters" ability.
    Two of alice's triggers are then waiting - that one and Mind Swap's linked
    "when you do, exile that card" - and CR 603.3b lets their controller order
    them: "each player, in APNAP order, puts each triggered ability they
    control on the stack in any order they choose." Put the exile one on first
    (lowest, resolving last) and the reanimation resolves while the Bringer
    card is still in the graveyard.

    By the time the exile instruction resolves, that card has changed zones,
    and CR 400.7 - "an object that moves from one zone to another becomes a
    new object with no memory of, or relation to, its previous existence" -
    means "that card" no longer refers to anything. The exile finds nothing,
    and alice keeps both: a 4/4 Spider-Bringer and the real 6/6.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Superior Spider-Man"],
            graveyard=["Bringer of the Last Gift"],
            battlefield=["Island", "Island", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Swamp", "Swamp", username="alice")
    scenario.cast_and_resolve("Superior Spider-Man", *sources, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()

    on_battlefield = {
        (state.name, state.power, state.toughness)
        for state in scenario.game.battlefield
        if state.controller == "alice" and Type.CREATURE in state.card.types
    }
    assert on_battlefield == {("Superior Spider-Man", 4, 4), ("Bringer of the Last Gift", 6, 6)}


# --------------------------------------------------------------------------
# DDR#980 - Jolrael, Voice of Zhalfir + Aggressive Biomancy
# --------------------------------------------------------------------------


def test_neither_jolraels_animation_nor_aggressive_biomancy_has_a_scripted_effect():
    """DDR#980, the provable half: both ends of the interaction are unbuilt.

    Jolrael, Voice of Zhalfir (verified with `resolve_cards`): "At the
    beginning of combat on your turn, up to one target land you control
    becomes an X/X green and blue Bird creature with flying and haste until
    end of turn, where X is the number of cards in your hand. It's still a
    land." Aggressive Biomancy: "Create X tokens that are copies of target
    creature you control, except they have 'When this token enters, it fights
    up to one target creature you don't control.'"

    `effect_for` returns `None` for both, and `_parse_token_clause` refuses
    the moment it reads "copies of" - the same refusal DDR#951 above already
    documents. So there is nothing to animate a land with, and nothing to copy
    it with.
    """
    assert effect_for("Aggressive Biomancy", card("Aggressive Biomancy").oracle_text) is None
    jolrael = card("Jolrael, Voice of Zhalfir")
    assert effect_for(jolrael.name, jolrael.oracle_text) is None


@pytest.mark.xfail(
    strict=True,
    reason="effect_for is None for both Jolrael and Aggressive Biomancy (proven above), so no "
    "land is animated and no token copies are created at all - CR 707.2 copiable values and the "
    "CR 707.9a 'except they have ...' added ability are both unimplemented, and machines/"
    "casting.py never threads a non-modal spell's announced X into its effect either.",
)
def test_token_copies_of_an_animated_land_are_plain_forests_with_a_fight_trigger():
    """DDR#980: the copy copies the land, not the animation.

    CR 707.2: "the copy acquires the copiable values of the original object's
    characteristics" - and an until-end-of-turn animation is a continuous
    effect acting on the Forest, not part of its copiable values, so the
    tokens are ordinary Forests: not blue, not green, no flying, no haste, not
    even creatures.

    The one thing they *do* get is the copy effect's own modification. CR
    707.9a: "Some copy effects cause the copy to gain an ability as part of
    the copying process. This ability becomes part of the copiable values for
    the copy" - so each token has "When this token enters, it fights up to one
    target creature you don't control", and the episode's point is that this
    triggers perfectly normally even on a noncreature token, because "this
    creature" in a trigger condition still identifies the object the ability
    is on. It just does nothing on resolution: CR 701.14b, "if one or both
    creatures instructed to fight are no longer on the battlefield or are no
    longer creatures, neither of them fights or deals damage."
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Aggressive Biomancy"],
            battlefield=["Jolrael, Voice of Zhalfir", "Forest", "Forest", "Island", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Island", "Island", username="alice")
    scenario.cast_and_resolve("Aggressive Biomancy", *sources, username="alice")

    tokens = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and isinstance(state, TokenState)
    ]
    assert len(tokens) == 2
    assert all(Type.CREATURE not in token.card.types for token in tokens)
    assert all(token.name == "Forest" for token in tokens)
    assert scenario.creature("Grizzly Bears", "bob").damage == 0


# --------------------------------------------------------------------------
# DDR#32 - Clone vs. Purelace and Forerunner of Slaughter
# --------------------------------------------------------------------------


def test_purelace_targets_a_spell_on_the_stack_and_is_a_layer_five_effect():
    """DDR#32, the provable half: the target is legal and the effect is real.

    Purelace (verified with `resolve_cards`): "Target spell or permanent
    becomes white." `machines/targeting.py` reads that phrase into a real
    requirement, so a spell already on the stack is a legal target and the
    cast goes through - which is the whole premise of the episode, Nick lacing
    the Clone *spell* rather than the permanent.

    The colour change itself is a continuous effect, so `effect_for` routes
    the card to `create_continuous_effect` rather than to a one-shot: layer 5
    (CR 613.1e, "Layer 5: Color-changing effects are applied"), read off the
    printed sentence by `machines/layers._BECOMES_COLOR_RE`. This test asserts
    the routing; the test below asserts what it does.

    (Noted, and not this episode's point: that requirement's `zones` is
    `{Zone.STACK}` alone, so the same parse would refuse the "or permanent"
    half of the printed phrase. Recorded in the wave ledger rather than
    tested here.)
    """
    assert effect_for("Purelace", card("Purelace").oracle_text) is create_continuous_effect

    scenario = (
        Scenario()
        .player("alice", hand=["Clone"], battlefield=["Island", "Island", "Island", "Island"])
        .player("bob", hand=["Purelace"], battlefield=["Plains", "Forerunner of Slaughter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")
    clone = scenario.cast_onto_stack("Clone", *sources, username="alice")
    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    purelace = scenario.cast_onto_stack("Purelace", plains, username="bob", targets=[clone])

    assert scenario.stack_names() == ["Clone", "Purelace"]
    scenario.resolve_top()
    assert purelace.zone is Zone.GRAVEYARD


def test_a_laced_clone_of_a_devoid_creature_ends_up_white():
    """DDR#32: a colour-changing effect beats a colour-defining ability here.

    The order the episode walks through is the order CR 613 gives:

    - CR 613.1a, layer 1: the copy effect applies, so Clone has Forerunner of
      Slaughter's copiable values, mana cost {B}{R} included.
    - CR 613.1e, layer 5: colour-changing effects. Two of them want this
      permanent - devoid, which CR 702.114a calls a characteristic-defining
      ability meaning "this object is colorless", and Purelace's "becomes
      white".
    - CR 613.3 breaks the tie, and *not* by timestamp: "Within layers 2-6,
      apply effects from characteristic-defining abilities first, then all
      other effects in timestamp order." Devoid goes first even though
      Purelace has the earlier timestamp, so white lands on top.

    Purelace was aimed at the Clone while it was still a spell; the effect
    keeps applying to the permanent that spell becomes, which is why the
    permanent is affected at all.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Clone"], battlefield=["Island", "Island", "Island", "Island"])
        .player("bob", hand=["Purelace"], battlefield=["Plains", "Forerunner of Slaughter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")
    clone = scenario.cast_onto_stack("Clone", *sources, username="alice")
    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_onto_stack("Purelace", plains, username="bob", targets=[clone])
    scenario.resolve_top()  # Purelace
    scenario.resolve_top()  # Clone, entering as a copy

    # The permanent is looked up by the identity the spell had on the stack,
    # not by name: CR 400.7's "new object" carve-out list includes CR 400.7a,
    # so this is the same `CardState`, and `scenario.creature(...)` searches
    # printed names, which layer 1 never rewrites.
    assert clone.zone is Zone.BATTLEFIELD
    assert clone.card.name == "Clone"
    assert scenario.game.characteristics_of(clone).name == "Forerunner of Slaughter"
    # `Characteristics.colors` is an ordered `tuple`, not a `frozenset`, and
    # `Game.characteristics_of` is the read that includes the effects created
    # by resolution (CR 611.2) - `compute_board(battlefield, static_effects(...))`
    # deliberately builds only the *static* ones (CR 611.3), so Purelace's
    # would be invisible to it.
    assert scenario.game.characteristics_of(clone).colors == (Color.WHITE,)


# --------------------------------------------------------------------------
# DDR#977 - Drafna, Founder of Lat-Nam vs. Flamehold Grappler
# --------------------------------------------------------------------------


def test_countering_the_spell_drafnas_ability_targets_removes_that_ability():
    """DDR#977's actual ruling, and the engine already gets it right.

    Drafna, Founder of Lat-Nam (verified with `resolve_cards`): "{3}, {T}:
    Copy target artifact spell you control." Nick counters the Sol Ring in
    response, which moves it off the stack, and CR 608.2b then refuses the
    ability outright: "If the spell or ability specifies targets, it checks
    whether the targets are still legal. A target that's no longer in the zone
    it was in when it was targeted is illegal." CR 608.3b applies that same
    check to a resolving ability. Amy gets neither a Sol Ring nor a token.

    `Game.fizzled` is the engine's record of exactly that removal, and it
    carries the *ability's* own id - the object this episode is about, not the
    countered spell's.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sol Ring"],
            battlefield=["Drafna, Founder of Lat-Nam", "Island", "Island", "Island", "Island"],
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (one,) = scenario.untapped_sources("Island", username="alice")
    sol_ring = scenario.cast_onto_stack("Sol Ring", one, username="alice")
    drafna = scenario.creature("Drafna, Founder of Lat-Nam", "alice")
    mana = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    ability = scenario.activate(drafna, *mana, index=1, username="alice", targets=[sol_ring])

    scenario.pass_priority("alice")
    counters = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *counters, username="bob", targets=[sol_ring])
    scenario.resolve_top()  # Counterspell
    assert sol_ring.zone is Zone.GRAVEYARD

    scenario.resolve_top()  # Drafna's ability, with nothing left to target
    assert ability.id in scenario.game.fizzled
    assert scenario.stack_names() == []
    assert [
        state.name
        for state in scenario.game.battlefield
        if state.controller == "alice" and is_token(state)
    ] == []


@pytest.mark.xfail(
    strict=True,
    reason="ONE clause is left, and it belongs in machines/effects.py. The old "
    "reason here was stale about everything except the parser: Game.copy_spell "
    "implements CR 707.10, offer_new_targets_for_copy implements CR 707.10c, and "
    "a copy of a permanent spell already becomes a token as it resolves "
    "(CR 707.10f, CR 608.3f). machines/delayed.py is complete too - "
    "DelayedTrigger takes a parsed `callback`, watches TriggerEvent.CAST_SPELL, "
    "and DelayedTriggers.create is CR 603.7a's 'the ability exists from now'. "
    "What is missing is that "
    "trigger_effect_for('Flamehold Grappler', ENTERS_THE_BATTLEFIELD, 'When "
    "this creature enters, copy the next spell you cast this turn when you cast "
    "it.') returns None: no clause parser in machines/effects.py reads 'copy the "
    "next spell you cast this turn when you cast it', so nothing calls "
    "DelayedTriggers.create and CR 707.10's second stack object is never built. "
    "It needs an effects.py clause that, on the ETB resolving, creates a "
    "DelayedTrigger with event=TriggerEvent.CAST_SPELL, remaining=1, "
    "controller=the Grappler's controller, and a callback that calls "
    "game.copy_spell(spell, controller) then "
    "game.offer_new_targets_for_copy(copy, controller, "
    "source_name='Flamehold Grappler') - CR 603.7d puts the source and "
    "controller on the creating ability, and CR 603.7b's 'the next' is the "
    "remaining=1. Not machines/casting.py: casting.py already emits the "
    "CAST_SPELL event this waits for, and a cast-time hook there would be a "
    "second, card-specific copy of the delayed-trigger machinery delayed.py "
    "already has.",
)
def test_flamehold_grapplers_untargeted_copy_still_copies_a_countered_spell():
    """DDR#977's contrast case: no target, so nothing to make illegal.

    Flamehold Grappler (verified with `resolve_cards`): "When this creature
    enters, copy the next spell you cast this turn when you cast it." CR
    608.2b only refuses an object that "specifies targets", and this copy
    specifies none - so when Nick counters the Sol Ring in response, the copy
    still happens, built from the spell's characteristics as they last existed
    on the stack. CR 707.10f then turns that copy of a permanent spell into a
    token as it resolves: "As that copy resolves, it ceases being a copy of a
    spell and becomes a token permanent."

    Amy ends with a Sol Ring token even though the Sol Ring card itself is in
    the graveyard.

    The Grappler is **cast** here rather than placed on the battlefield: its
    ability is "When this creature enters", so a board that starts with it in
    play never triggers it at all and the delayed ability (CR 603.7a: it "won't
    trigger until it has actually been created") would never exist. The token
    is counted with `models.token.is_token` rather than
    `isinstance(state, TokenState)`, because CR 707.10f's token is the
    resolving copy itself - a plain `CardState` with `token=True`, which no
    `TokenState` check can ever match.
    """
    grappler_card = card("Flamehold Grappler")
    trigger_line = grappler_card.oracle_text.split("\n")[1]
    assert trigger_line.startswith("When this creature enters, copy the next spell")

    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flamehold Grappler", "Sol Ring"],
            battlefield=["Island", "Mountain", "Plains", "Island"],
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Island", "Mountain", "Plains", username="alice")
    scenario.cast_and_resolve("Flamehold Grappler", *lands, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()  # the enters trigger, creating the delayed one

    (one,) = scenario.untapped_sources("Island", username="alice")
    sol_ring = scenario.cast_onto_stack("Sol Ring", one, username="alice")
    scenario.pass_priority("alice")
    counters = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *counters, username="bob", targets=[sol_ring])
    while scenario.game.stack:
        scenario.resolve_top()

    assert sol_ring.zone is Zone.GRAVEYARD
    tokens = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and is_token(state)
    ]
    assert [token.name for token in tokens] == ["Sol Ring"]
