"""Tokens: CR 111, and the create keyword action of CR 701.7.

Every rule cited here was looked up with `knowledge_search(type="rules")` and
then read in full out of the 2026-08-19 Comprehensive Rules, because CR 111's
excerpts truncate before the clause that decides the case.

The happy path is one test. The rest of the file is what a token is *not*: not a
card (CR 111.6), not something that survives leaving the battlefield (CR 111.7,
CR 704.5d), not something that can come back (CR 111.8), and not something
anything else on the battlefield treats differently (CR 110.1).

Roles are a token too, and they have a file of their own -
`test_role_tokens.py` - because CR 111.10k and CR 303.7 are their own mechanic.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color, Type
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import (
    TokenDefinition,
    create_predefined_tokens,
    create_tokens,
    is_token,
    token_copy_of,
    tokens_that_cease_to_exist,
)
from tests.scenarios.harness import Scenario


def _spectral_procession() -> Scenario:
    """Six Plains and the sorcery that turns them into three Spirits.

    Spectral Procession costs `{2/W}{2/W}{2/W}`, so six generic mana pays for it
    without a white source in sight - which is why the board is six Plains rather
    than three.
    """
    return (
        Scenario()
        .player("alice", hand=["Spectral Procession"], battlefield=["Plains"] * 6)
        .player("bob")
    )


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_a_spell_that_creates_tokens_puts_them_onto_the_battlefield():
    """CR 701.7a: "To create one or more tokens with certain characteristics, put
    the specified number of tokens with the specified characteristics onto the
    battlefield."

    Spectral Procession reads "Create three 1/1 white Spirit creature tokens with
    flying", and CR 111.3 makes each of those stated values as real as a printed
    one: "The characteristic values defined this way are functionally equivalent
    to the characteristic values that are printed on a card."

    CR 111.4 supplies the name nobody stated: "If the spell or ability doesn't
    specify the name of the token, its name is the same as its subtype(s) plus
    the word 'Token.'"
    """
    scenario = _spectral_procession().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources(*["Plains"] * 6, username="alice")
    scenario.cast_and_resolve("Spectral Procession", *sources, username="alice")

    spirits = [state for state in scenario.game.battlefield if state.name == "Spirit Token"]
    assert len(spirits) == 3

    spirit = spirits[0]
    assert spirit.power == 1 and spirit.toughness == 1
    assert spirit.card.colors == [Color.WHITE]
    assert spirit.card.types == [Type.CREATURE]
    assert spirit.card.subtypes == ["Spirit"]
    assert has_keyword(spirit, Keyword.FLYING)


def test_a_token_is_a_permanent_but_is_not_a_card():
    """CR 110.1: "A permanent is a card **or token** on the battlefield."

    CR 111.6 draws the other half of the line: "A token is subject to anything
    that affects permanents in general or that affects the token's card type or
    subtype. A token isn't a card." CR 108.2b says the same from the card's side,
    and CR 205.2c is why the type line still works: "Tokens have card types even
    though they aren't cards."

    CR 202.3a settles the mana value: "The mana value of an object with no mana
    cost is 0."
    """
    scenario = _spectral_procession().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Plains"] * 6, username="alice")
    scenario.cast_and_resolve("Spectral Procession", *sources, username="alice")

    spirit = scenario.find("Spirit Token", Zone.BATTLEFIELD)
    plains = scenario.find("Plains", Zone.BATTLEFIELD)

    assert is_token(spirit)
    assert not is_token(plains), "a real printing is a card, not a token"
    assert spirit.is_permanent and spirit.is_creature
    assert spirit.card.mana_cost is None
    assert spirit.card.cmc == 0.0


def test_the_creating_player_controls_the_token():
    """CR 111.2: "The player who creates a token is its owner. The token enters
    the battlefield under that player's control."

    So a spell one player casts never hands tokens to anybody else, and
    `Game.permanents_controlled_by` counts them for their creator.
    """
    scenario = _spectral_procession().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Plains"] * 6, username="alice")
    scenario.cast_and_resolve("Spectral Procession", *sources, username="alice")

    mine = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Spirit Token"
    ]
    assert len(mine) == 3
    assert not [
        state
        for state in scenario.game.permanents_controlled_by("bob")
        if state.name == "Spirit Token"
    ]


# --------------------------------------------------------------------------
# Entering: a token enters the battlefield like anything else
# --------------------------------------------------------------------------


def test_a_token_entering_fires_another_permanents_enters_trigger():
    """CR 603.6a's enters-the-battlefield trigger does not care what entered.

    Soul Warden reads "Whenever another creature enters, you gain 1 life", and
    CR 110.1 makes a token a permanent as it enters exactly as a card is one.
    Three Spirits entering is three separate events, so the trigger fires three
    times and alice gains three life.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spectral Procession"],
            battlefield=["Plains"] * 6 + ["Soul Warden"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = scenario.player("alice").life

    sources = scenario.untapped_sources(*["Plains"] * 6, username="alice")
    scenario.cast_and_resolve("Spectral Procession", *sources, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("alice").life == before + 3


def test_a_token_creature_is_summoning_sick_the_turn_it_is_created():
    """CR 302.6: "A creature can't attack unless it has been under its
    controller's control continuously since their most recent turn began."

    Nothing about a token exempts it. CR 111.3 says a token has no
    characteristics the creating effect did not give it, and Spectral Procession
    gives its Spirits flying and nothing else - so no haste (CR 702.10b).
    """
    scenario = _spectral_procession().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Plains"] * 6, username="alice")
    scenario.cast_and_resolve("Spectral Procession", *sources, username="alice")

    spirit = scenario.find("Spirit Token", Zone.BATTLEFIELD)
    assert spirit.summoning_sick
    assert not scenario.can_attack(spirit, defending="bob")


def test_a_token_created_tapped_and_attacking_never_attacked():
    """CR 508.4, read past the truncation: "If a creature is put onto the
    battlefield attacking, its controller chooses which defending player ... it's
    attacking as it enters the battlefield (unless the effect that put it onto
    the battlefield specifies what it's attacking). ... **Such creatures are
    'attacking' but, for the purposes of trigger events and effects, they never
    'attacked.'** They remain attacking creatures until they're removed from
    combat or the combat phase ends."

    That last clause is the whole reason Dalkovan Encampment's Warriors do not
    fire another Dalkovan Encampment - and it is entirely inside the tail
    `knowledge_search` cuts off.

    CR 508.4c is why summoning sickness does not stop them: "A creature that's
    put onto the battlefield attacking ... isn't affected by requirements or
    restrictions that apply to the declaration of attackers."
    """
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    warrior = TokenDefinition(subtypes=("Warrior",), colors=(Color.RED,), power=1, toughness=1)
    (token,) = create_tokens(scenario.game, warrior, "alice", tapped=True, attacking="bob")

    assert token.tapped
    assert token.summoning_sick, "it still has not been here since the turn began"
    assert scenario.game.is_attacking(token)
    assert not scenario.game.pending_triggers, "it never 'attacked' (CR 508.4)"


def test_a_token_put_onto_the_battlefield_attacking_a_player_who_left_is_not_attacking():
    """CR 506.3c and CR 508.4a: "If a creature would be put onto the battlefield
    attacking either a player not in the game ... that creature does enter the
    battlefield, but it's never considered to be an attacking creature."

    It enters. It just is not in combat.
    """
    scenario = Scenario().player("alice").player("bob").player("carol").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.game.concede("carol")

    warrior = TokenDefinition(subtypes=("Warrior",), colors=(Color.RED,), power=1, toughness=1)
    (token,) = create_tokens(scenario.game, warrior, "alice", attacking="carol")

    assert token.zone is Zone.BATTLEFIELD
    assert not scenario.game.is_attacking(token)


def test_a_token_can_be_created_with_counters_on_it():
    """CR 122.1 counters go on a token like any other permanent, and CR 122.1a
    makes them change its power and toughness.

    CR 122.6 is why they are put on *after* the token has arrived - they are
    counters being put on an object, an event of their own inside the token's
    creation, which is what Doubling Season's second ability watches for.
    """
    scenario = Scenario().player("alice").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spawn = TokenDefinition(subtypes=("Eldrazi", "Spawn"), power=0, toughness=1)
    (token,) = create_tokens(scenario.game, spawn, "alice", counters={Counter.PLUS_ONE: 2})

    assert token.counters[Counter.PLUS_ONE] == 2
    assert (token.power, token.toughness) == (2, 3)


# --------------------------------------------------------------------------
# Leaving: CR 111.7, CR 111.8, CR 704.5d
# --------------------------------------------------------------------------


def test_a_token_that_dies_reaches_the_graveyard_first():
    """CR 111.7's parenthesis, which is the part that gets truncated away: "A
    token that's in a zone other than the battlefield ceases to exist. This is a
    state-based action; see rule 704. **(Note that if a token changes zones,
    applicable triggered abilities will trigger before the token ceases to
    exist.)**"

    So a dying token really is put into a graveyard (CR 700.4: "dies" means "is
    put into a graveyard from the battlefield"), and only afterwards does
    CR 704.5d remove it. This test is the first half of that sequence.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spirit = TokenDefinition(subtypes=("Spirit",), colors=(Color.WHITE,), power=1, toughness=1)
    (token,) = create_tokens(scenario.game, spirit, "alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[token])

    assert token.zone is Zone.GRAVEYARD, "it died before it ceased to exist"


def test_a_token_that_dies_fires_its_own_dies_trigger():
    """The consequence of CR 111.7's parenthesis, with a trigger to prove it.

    A token copy of Wurmcoil Engine carries Wurmcoil's printed text (CR 707.2),
    which includes "When this creature dies, create a 3/3 colorless Phyrexian
    Wurm artifact creature token with deathtouch and a 3/3 colorless Phyrexian
    Wurm artifact creature token with lifelink." CR 603.10a lets the trigger look
    back in time at the permanent that has just left, and CR 111.7 guarantees the
    token is still there to be looked at.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Swords to Plowshares"],
            battlefield=["Plains", "Wurmcoil Engine"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    original = scenario.creature("Wurmcoil Engine", "alice")
    (copy,) = token_copy_of(scenario.game, original, "alice")
    assert is_token(copy)

    scenario.game.destroy(copy)
    scenario.game.put_triggers_on_stack()  # CR 603.3
    while scenario.game.stack:
        scenario.resolve_top()

    wurms = [state for state in scenario.game.battlefield if state.name == "Phyrexian Wurm Token"]
    assert len(wurms) == 2, "the dying token's own trigger resolved"
    assert has_keyword(wurms[0], Keyword.DEATHTOUCH)
    assert has_keyword(wurms[1], Keyword.LIFELINK)


def test_a_token_in_a_graveyard_ceases_to_exist():
    """CR 704.5d: "If a token is in a zone other than the battlefield, it ceases
    to exist." CR 111.7 states the same rule from the token's side.

    Ceasing to exist is not going anywhere - the token is simply gone, so the
    graveyard it was in for a moment ends up empty of it.
    """
    scenario = Scenario().player("alice").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spirit = TokenDefinition(subtypes=("Spirit",), colors=(Color.WHITE,), power=1, toughness=1)
    (token,) = create_tokens(scenario.game, spirit, "alice")
    scenario.game.destroy(token)
    assert token in scenario.player("alice").graveyard

    gone = tokens_that_cease_to_exist(scenario.game)

    assert gone == [token]
    assert token not in scenario.player("alice").graveyard
    assert scenario.player("alice").graveyard == []


def test_the_game_makes_a_dead_token_cease_to_exist_by_itself():
    """CR 704.3 with CR 704.5d: the game checks state-based actions "whenever a
    player would get priority", and CR 704.5d is on the list it checks.

    Nobody should have to call `tokens_that_cease_to_exist` by hand. A token that
    died a moment ago is gone by the time anyone next holds priority, which is
    also what keeps a dead token out of every count of cards in a graveyard -
    delirium's card types (CR 205.2a), a Tarmogoyf's power, threshold.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spirit = TokenDefinition(subtypes=("Spirit",), colors=(Color.WHITE,), power=1, toughness=1)
    (token,) = create_tokens(scenario.game, spirit, "alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[token])
    scenario.state_based_actions()

    graveyard = [state.name for state in scenario.player("alice").graveyard]
    assert graveyard == ["Lightning Bolt"], "the Spirit ceased to exist; only the Bolt is left"


def test_a_token_that_left_the_battlefield_cannot_come_back():
    """CR 111.8: "A token that has left the battlefield can't move to another zone
    or come back onto the battlefield. If such a token would change zones, it
    remains in its current zone instead. It ceases to exist the next time
    state-based actions are checked."

    The point of the rule is a token that a Raise Dead or a flicker effect would
    otherwise recur. Once it has been to a graveyard it is finished; the effect
    that would move it does nothing at all.
    """
    scenario = Scenario().player("alice").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spirit = TokenDefinition(subtypes=("Spirit",), colors=(Color.WHITE,), power=1, toughness=1)
    (token,) = create_tokens(scenario.game, spirit, "alice")
    scenario.game.destroy(token)

    scenario.game.return_to_hand(token)

    assert token.zone is Zone.GRAVEYARD, "it remains in its current zone instead"
    assert token not in scenario.player("alice").hand
    assert token in scenario.player("alice").graveyard, "and it is still listed there"


def test_a_token_that_left_the_battlefield_cannot_be_exiled_out_of_the_graveyard():
    """CR 111.8 says "can't move to another zone", not "can't come back".

    A graveyard-hate effect that would exile the dead token does nothing at all -
    the token stays in the graveyard and ceases to exist there. This is the half
    of the rule that is easy to miss, because the memorable case is the flicker.
    """
    scenario = Scenario().player("alice").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spirit = TokenDefinition(subtypes=("Spirit",), colors=(Color.WHITE,), power=1, toughness=1)
    (token,) = create_tokens(scenario.game, spirit, "alice")
    scenario.game.destroy(token)

    scenario.game.exile_permanent(token)

    assert token.zone is Zone.GRAVEYARD
    assert token not in scenario.game.exile
    assert token in scenario.player("alice").graveyard


def test_a_token_that_left_the_battlefield_cannot_be_put_back_onto_it():
    """CR 111.8's "or come back onto the battlefield", which is the reanimation
    case.

    `Game.put_onto_battlefield` is the route every effect that puts a permanent
    onto the battlefield without casting it takes (CR 110.2a), and it refuses.
    Nothing enters, so no enters-the-battlefield ability triggers either
    (CR 603.6a) - CR 614.6's "if an event is replaced, it never happens" is the
    shape of it, even though CR 111.8 is a rule rather than a replacement effect.
    """
    scenario = Scenario().player("alice", battlefield=["Soul Warden"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spirit = TokenDefinition(subtypes=("Spirit",), colors=(Color.WHITE,), power=1, toughness=1)
    (token,) = create_tokens(scenario.game, spirit, "alice")
    scenario.game.destroy(token)
    while scenario.game.stack:
        scenario.resolve_top()
    life = scenario.player("alice").life

    scenario.game.put_onto_battlefield(token, "alice")

    assert token.zone is Zone.GRAVEYARD
    assert token not in scenario.game.battlefield
    assert scenario.player("alice").life == life, "nothing entered, so nothing triggered"


def test_a_token_that_ceased_to_exist_is_in_no_zone_at_all():
    """CR 704.5d removes the token; it does not move it.

    Ceasing to exist is not a zone change (CR 400.6 is about moving between
    zones and this is not a move), so there is no destination to look in. The
    token object is still in the caller's hands - Python does not forget it - and
    every zone list in the game has stopped mentioning it.
    """
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spirit = TokenDefinition(subtypes=("Spirit",), colors=(Color.WHITE,), power=1, toughness=1)
    (token,) = create_tokens(scenario.game, spirit, "alice")
    scenario.game.destroy(token)
    scenario.state_based_actions()

    every_zone = [
        cards for player in scenario.game.players for cards in player.zones.values()
    ] + list(scenario.game.shared_zones.values())
    assert all(token not in cards for cards in every_zone)
    assert scenario.game.find_by_id(token.id) is None


# --------------------------------------------------------------------------
# Copies (CR 707.2), and predefined tokens (CR 111.10)
# --------------------------------------------------------------------------


def test_a_token_copy_of_a_permanent_gets_its_printed_values_and_none_of_its_state():
    """CR 707.2: "the copy acquires the copiable values of the original object's
    characteristics ... The copiable values are the values derived from the text
    printed on the object ... **Other effects (including type-changing and
    text-changing effects), status, counters, and stickers are not copied.**"

    The tail there is the whole test: the original is tapped, damaged and covered
    in +1/+1 counters, and the copy is none of those things. CR 111.4's last
    example gives the naming: a token copy of Doomed Dissenter is named Doomed
    Dissenter, not "Human Token" - so this copy is named Hangarback Walker.

    No card in the pool prints "create a token that's a copy of ..." in a form
    this engine can cast yet - Caretaker's Talent needs Class levels and Ocelot
    Pride needs the city's blessing - so the copy is made through the same call
    those cards' effects would make.
    """
    scenario = Scenario().player("alice", battlefield=["Hangarback Walker"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    original = scenario.creature("Hangarback Walker", "alice")
    original.add_counters(Counter.PLUS_ONE, 3)
    original.tap()
    original.mark_damage(1)

    (copy,) = token_copy_of(scenario.game, original, "alice")

    assert copy.name == "Hangarback Walker"
    assert is_token(copy) and not is_token(original)
    assert copy.counters[Counter.PLUS_ONE] == 0, "counters are not copied"
    assert copy.untapped and copy.damage == 0, "status is not copied"
    assert (copy.power, copy.toughness) == (0, 0), "the printed 0/0 is what is copied"


def test_a_token_copy_of_a_token_copies_the_stated_characteristics():
    """CR 111.3: the characteristics a creating effect states "define the token's
    copiable values", so a token can be copied like anything else.

    CR 707.2b then fixes it in place: "Once an object has been copied, changing
    the copiable values of the original object won't cause the copy to change."
    """
    scenario = Scenario().player("alice").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    definition = TokenDefinition(subtypes=("Cat",), colors=(Color.WHITE,), power=1, toughness=1)
    (original,) = create_tokens(scenario.game, definition, "alice")
    (copy,) = token_copy_of(scenario.game, original, "alice")

    assert is_token(copy)
    assert copy.name == "Cat Token"
    assert (copy.power, copy.toughness) == (1, 1)
    assert copy.card.colors == [Color.WHITE]
    assert copy.id != original.id, "two objects, one set of copiable values"


def test_a_predefined_token_gets_the_characteristics_the_rules_give_it():
    """CR 111.10: "Some effects instruct a player to create a predefined token.
    These effects use the definition below to determine the characteristics the
    token is created with."

    CR 111.10a is the one the pool needs: "A Treasure token is a colorless
    Treasure artifact token with '{T}, Sacrifice this token: Add one mana of any
    color.'" Colorless, so `colors` is empty (CR 105.2), and an artifact rather
    than a creature.
    """
    scenario = Scenario().player("alice").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (treasure,) = create_predefined_tokens(scenario.game, "Treasure", "alice")

    assert treasure.card.types == [Type.ARTIFACT]
    assert treasure.card.subtypes == ["Treasure"]
    assert treasure.card.colors == []
    assert treasure.card.oracle_text == "{T}, Sacrifice this token: Add one mana of any color."
    assert not treasure.is_creature

    # CR 111.11 sends an unknown name to the Oracle card reference, which nothing
    # here can consult at runtime, so it refuses rather than inventing a token.
    with pytest.raises(ValueError, match="CR 111.10"):
        create_predefined_tokens(scenario.game, "Clue", "alice")


# --------------------------------------------------------------------------
# The metagame cards
# --------------------------------------------------------------------------


def test_ajanis_enters_trigger_creates_a_cat_warrior():
    """Ajani, Nacatl Pariah: "When Ajani enters, create a 2/1 white Cat Warrior
    creature token." CR 603.6a, then CR 701.7a.

    CR 111.4 names it Cat Warrior Token, from both of its subtypes.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Ajani, Nacatl Pariah"], battlefield=["Plains", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.cast_and_resolve("Ajani, Nacatl Pariah", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger

    cat = scenario.find("Cat Warrior Token", Zone.BATTLEFIELD)
    assert (cat.power, cat.toughness) == (2, 1)
    assert cat.card.subtypes == ["Cat", "Warrior"]


@pytest.mark.xfail(
    strict=True,
    reason="The trigger itself now fires: `condition_matches` reads a non-self DIES "
    "condition narrowed by subtype ('one or more other Cats you control die'), so a Cat "
    "token dying puts Ajani's second ability on the stack - see "
    "test_dies_trigger_scope.py::test_another_cat_dying_triggers_ajanis_transform_ability "
    "for that half. What is still missing is the *effect*: `machines/effects.py` has no "
    "entry for Ajani's DIES trigger, so it resolves and does nothing - exiling and "
    "returning him transformed needs a way to turn a creature into its planeswalker face, "
    "which does not exist yet.",
)
def test_a_cat_token_dying_flips_ajani():
    """Ajani, Nacatl Pariah: "Whenever one or more other Cats you control die, you
    may exile Ajani, then return him to the battlefield transformed under his
    owner's control."

    A Cat token dying is a Cat you control dying: CR 700.4's "dies" and CR 111.7's
    parenthesis together mean the token really did go to a graveyard and really
    is visible to a dies trigger. This is the interaction that makes Ajani a
    metagame card, and it is the transform half that is still missing.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Ajani, Nacatl Pariah"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.creature("Ajani, Nacatl Pariah", "alice")

    cat = TokenDefinition(subtypes=("Cat", "Warrior"), colors=(Color.WHITE,), power=2, toughness=1)
    (token,) = create_tokens(scenario.game, cat, "alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[token])
    scenario.game.put_triggers_on_stack()  # CR 603.3
    while scenario.game.stack:
        scenario.resolve_top()

    assert ajani.transformed


def test_seasoned_pyromancer_makes_an_elemental_for_each_nonland_discarded():
    """Seasoned Pyromancer: "When this creature enters, discard two cards, then
    draw two cards. For each nonland card discarded this way, create a 1/1 red
    Elemental creature token."

    "Discarded this way" is a count over exactly what this discard put into the
    graveyard, not over the graveyard afterwards. One land and one spell in hand
    means one Elemental.

    Which two cards are discarded is a decision nobody is here to make, so the
    first two in hand go - which is what the hand order below is choosing.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest", "Island"],
            hand=["Seasoned Pyromancer", "Mountain", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Seasoned Pyromancer", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger

    elementals = [state for state in scenario.game.battlefield if state.name == "Elemental Token"]
    assert len(elementals) == 1, "one of the two discards was a land"
    assert (elementals[0].power, elementals[0].toughness) == (1, 1)
    assert [state.name for state in scenario.player("alice").hand] == ["Forest", "Island"]


def test_malevolent_rumble_creates_an_eldrazi_spawn():
    """Malevolent Rumble: "Reveal the top four cards of your library. You may put
    a permanent card from among them into your hand. Put the rest into your
    graveyard. Create a 0/1 colorless Eldrazi Spawn creature token with 'Sacrifice
    this token: Add {C}.'"

    In printed order (CR 608.2c), so the token is last. CR 111.3 gives it the
    quoted ability as its rules text.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Grizzly Bears", "Forest", "Counterspell"],
            hand=["Malevolent Rumble"],
            battlefield=["Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.cast_and_resolve("Malevolent Rumble", *sources, username="alice")

    spawn = scenario.find("Eldrazi Spawn Token", Zone.BATTLEFIELD)
    assert (spawn.power, spawn.toughness) == (0, 1)
    assert spawn.card.colors == []
    assert spawn.card.oracle_text == "Sacrifice this token: Add {C}."
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]
    assert scenario.player("alice").library == []


def test_ocelot_pride_creates_a_cat_at_the_end_step():
    """Ocelot Pride: "At the beginning of your end step, if you gained life this
    turn, create a 1/1 white Cat creature token."

    CR 500.6 puts a beginning-of-step trigger on the stack the first time a player
    would receive priority in that step. CR 603.4's intervening *if* is judged
    for real: `Game.gain_life` now records who gained life this turn (CR 119.9),
    which is what makes the clause true here - not an unconditional pass.
    `Game.gain_life` is called directly rather than through a life-gain source,
    because `machines/effects.py`'s generic "you gain N life" fallback calls
    `Player.gain_life` straight, bypassing `Game.gain_life` (and so CR 614.1a's
    replacement effects) entirely - a separate, pre-existing gap outside this
    fix's scope. The second sentence - the city's blessing copying every token
    that entered this turn (CR 702.131b) - is a genuine no-op here because
    alice never reaches ten permanents; see `tests/scenarios/test_ascend.py`
    for that half of the ability end to end.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ocelot Pride"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 1)
    assert "alice" in scenario.game.life_gained_this_turn

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins

    while scenario.game.stack:
        scenario.resolve_top()

    cat = scenario.find("Cat Token", Zone.BATTLEFIELD)
    assert (cat.power, cat.toughness) == (1, 1)
    assert cat.card.colors == [Color.WHITE]


def test_ocelot_pride_does_not_trigger_without_a_life_gain_this_turn():
    """CR 603.4: the intervening *if* stops the ability from triggering at all
    when nothing gained alice any life this turn - a plain absence, not a
    fizzle, so nothing goes on the stack.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ocelot Pride"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # the end step begins

    assert scenario.game.stack_is_empty
    assert scenario.pending_triggers == []


def test_hangarback_walker_makes_a_thopter_for_each_counter_it_had():
    """Hangarback Walker: "When this creature dies, create a 1/1 colorless Thopter
    artifact creature token with flying for each +1/+1 counter on this creature."

    CR 122.2 destroys the counters as it changes zones - "the counters are not
    'removed'; they simply cease to exist" - and CR 603.10a lets the dies trigger
    look back in time at the permanent as it last existed. So the count is the
    counters it *had*, not the none it has now.
    """
    scenario = Scenario().player("alice", battlefield=["Hangarback Walker"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    walker = scenario.creature("Hangarback Walker", "alice")
    walker.add_counters(Counter.PLUS_ONE, 3)

    scenario.game.destroy(walker)
    scenario.game.put_triggers_on_stack()  # CR 603.3
    while scenario.game.stack:
        scenario.resolve_top()

    thopters = [state for state in scenario.game.battlefield if state.name == "Thopter Token"]
    assert len(thopters) == 3
    assert has_keyword(thopters[0], Keyword.FLYING)
    assert walker.counters[Counter.PLUS_ONE] == 0, "CR 122.2 took them"


# --------------------------------------------------------------------------
# Metagame cards the token machinery is not enough for
# --------------------------------------------------------------------------


def test_doubling_season_doubles_the_tokens_created():
    """Doubling Season: "If an effect would create one or more tokens under your
    control, it creates twice that many of those tokens instead."

    CR 701.7b is the ordering rule that makes this a *creation* replacement
    rather than an *entering* one: "If a replacement effect applies to a token
    being created, that effect applies before considering any continuous effects
    that will modify the characteristics of that token."
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spectral Procession"],
            battlefield=["Plains"] * 6 + ["Doubling Season"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources(*["Plains"] * 6, username="alice")
    scenario.cast_and_resolve("Spectral Procession", *sources, username="alice")

    spirits = [state for state in scenario.game.battlefield if state.name == "Spirit Token"]
    assert len(spirits) == 6


@pytest.mark.xfail(
    strict=True,
    reason="Ragavan's trigger is 'Whenever Ragavan deals combat damage to a player', and "
    "machines/abilities.TriggerEvent has no member for damage being dealt - the six it "
    "recognises are enters, dies, attacks, blocks, beginning of step and cast. The trigger "
    "is parsed with `event=None` and never fires, so the Treasure is never created. The "
    "hook is a DEALS_COMBAT_DAMAGE event in machines/abilities.py and machines/triggers.py, "
    "emitted from machines/combat.py.",
)
def test_ragavan_creates_a_treasure_on_combat_damage():
    """Ragavan, Nimble Pilferer: "Whenever Ragavan deals combat damage to a
    player, create a Treasure token and exile the top card of that player's
    library."

    The Treasure is CR 111.10a's predefined token and this engine can create it.
    What it cannot do is notice the trigger event.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ragavan, Nimble Pilferer"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")
    ragavan.summoning_sick = False

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ragavan, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.find("Treasure Token", Zone.BATTLEFIELD)


@pytest.mark.xfail(
    strict=True,
    reason="Cori-Steel Cutter triggers on 'whenever you cast your second spell each turn'. "
    "machines/triggers.py reads a CAST_SPELL condition as 'whoever cast it, and what type "
    "of spell' and nothing counts spells cast this turn, so the trigger would fire on the "
    "first spell as well as the second. It is deliberately left out of TRIGGER_EFFECTS "
    "rather than registered wrong. The hook is a per-turn cast count on models/game.py "
    "plus an ordinal clause in machines/triggers.condition_matches.",
)
def test_cori_steel_cutter_makes_a_monk_on_the_second_spell_only():
    """Cori-Steel Cutter: "Flurry - Whenever you cast your second spell each turn,
    create a 1/1 white Monk creature token with prowess."

    *Flurry* is an ability word (CR 207.2c) with no rules meaning, so the whole
    mechanic is the sentence after it. One spell should make no Monk; the second
    should make one.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Cori-Steel Cutter", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    first, second = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", first, username="alice", targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()
    assert "Monk Token" not in scenario.battlefield_names(), "not on the first spell"

    scenario.cast_and_resolve("Lightning Bolt", second, username="alice", targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()

    assert "Monk Token" in scenario.battlefield_names()


@pytest.mark.xfail(
    strict=True,
    reason="Kozilek's Command is modal with an X in its cost. machines/modes.py parses and "
    "validates the modes but CardState records no chosen mode and EFFECTS is keyed by card "
    "name alone (CR 700.2a), and nothing exposes the value chosen for {X} (CR 601.2b) to a "
    "resolving effect. Both hooks are on models/card_state.py and models/game.py.",
)
def test_kozileks_command_creates_x_eldrazi_spawn():
    """Kozilek's Command, first mode: "Target player creates X 0/1 colorless
    Eldrazi Spawn creature tokens with 'Sacrifice this token: Add {C}.'"

    Note whose tokens they are: CR 111.2 says "the player who creates a token is
    its owner", and this mode makes the *targeted* player the creator, so the
    Spawn are theirs and not the caster's.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kozilek's Command"],
            battlefield=["Eldrazi Temple", "Eldrazi Temple", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Kozilek's Command", username="alice")
    casting.choose_modes([1, 2])
    casting.choose_targets(["alice", "alice"])
    payment = casting.begin_paying()
    scenario.pay_with(
        payment,
        *scenario.untapped_sources(
            "Eldrazi Temple", "Eldrazi Temple", "Forest", "Forest", username="alice"
        ),
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    spawn = [state for state in scenario.game.battlefield if state.name == "Eldrazi Spawn Token"]
    assert len(spawn) == 2


def test_dalkovan_encampment_creates_warriors_tapped_and_attacking():
    """Dalkovan Encampment: "{2}{W}, {T}: Whenever you attack this turn, create two
    1/1 red Warrior creature tokens that are tapped and attacking. Sacrifice them
    at the beginning of the next end step."

    The token half of this - CR 508.4's "put onto the battlefield attacking",
    tapped - is modelled and tested above. What is missing is the ability that
    reaches it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Dalkovan Encampment",
                "Plains",
                "Plains",
                "Plains",
                "Grizzly Bears",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False

    encampment = scenario.find("Dalkovan Encampment", Zone.BATTLEFIELD)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", username="alice")
    scenario.activate(encampment, *sources, index=1, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()  # CR 603.3
    while scenario.game.stack:
        scenario.resolve_top()

    warriors = [state for state in scenario.game.battlefield if state.name == "Warrior Token"]
    assert len(warriors) == 2
    assert all(state.tapped and scenario.game.is_attacking(state) for state in warriors)


def _dalkovan_board():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Dalkovan Encampment",
                "Plains",
                "Plains",
                "Plains",
                "Grizzly Bears",
            ],
        )
        .player("bob")
        .build()
    )


def _activate_dalkovan(scenario: "Scenario"):
    encampment = scenario.find("Dalkovan Encampment", Zone.BATTLEFIELD)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", username="alice")
    scenario.activate(encampment, *sources, index=1, username="alice")
    while scenario.game.stack:
        scenario.resolve_top()


def test_dalkovan_encampment_warriors_are_sacrificed_at_the_next_end_step():
    """The second half: "Sacrifice them at the beginning of the next end
    step" - CR 603.7, one one-shot delayed trigger per token (each reusing
    `machines/delayed.py`'s existing `"sacrifice"` entry), not a single
    trigger that only manages to sacrifice one of the two.
    """
    scenario = _dalkovan_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    _activate_dalkovan(scenario)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    warriors = [state for state in scenario.game.battlefield if state.name == "Warrior Token"]
    assert len(warriors) == 2

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    while scenario.game.stack:
        scenario.resolve_top()

    assert all(state.zone is Zone.GRAVEYARD for state in warriors)


def test_dalkovan_encampment_fires_again_on_a_second_attack_the_same_turn():
    """CR 603.7b's own "unless it has a stated duration, such as 'this
    turn'": the delayed trigger is not spent after its first firing, so a
    second attack declaration later in the same turn creates two *more*
    tokens on top of the first two. A second real combat phase needs extra-
    combat machinery this engine does not model, so the second declaration
    is reached the same way `Game.declare_attackers` itself would emit it -
    the identical subjectless `ATTACKS` event, by hand.
    """
    from magic_cards_model.machines.abilities import TriggerEvent
    from magic_cards_model.machines.triggers import GameEvent

    scenario = _dalkovan_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    _activate_dalkovan(scenario)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    assert len([s for s in scenario.game.battlefield if s.name == "Warrior Token"]) == 2

    scenario.game.emit(GameEvent(event=TriggerEvent.ATTACKS, player="alice"))
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert len([s for s in scenario.game.battlefield if s.name == "Warrior Token"]) == 4


def test_dalkovan_encampment_does_not_fire_after_cleanup_expires_it():
    """CR 514.2 ends every "this turn" effect in the cleanup step - so once
    `DelayedTriggers.expire_this_turn` has run, a later attack (a new turn's
    own combat, reached here the same subjectless-`ATTACKS`-event way
    `test_dalkovan_encampment_fires_again_on_a_second_attack_the_same_turn`
    reaches its second attack, since neither test wants the turn machinery's
    own untap/draw bookkeeping to be what is under test) creates no tokens
    and queues no reflexive-style trigger at all.
    """
    from magic_cards_model.machines.abilities import TriggerEvent
    from magic_cards_model.machines.triggers import GameEvent

    scenario = _dalkovan_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    _activate_dalkovan(scenario)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="bob")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    assert len([s for s in scenario.game.battlefield if s.name == "Warrior Token"]) == 2

    while scenario.step is not Step.CLEANUP:
        scenario.advance()
        while scenario.game.stack:
            scenario.resolve_top()  # the per-token sacrifice at the end step (CR 603.7)
    scenario.turn_based_actions()  # CR 514.2: expires the delayed trigger

    scenario.game.emit(GameEvent(event=TriggerEvent.ATTACKS, player="alice"))
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert not any(
        s.name == "Warrior Token" and s.zone is Zone.BATTLEFIELD for s in scenario.game.battlefield
    )
