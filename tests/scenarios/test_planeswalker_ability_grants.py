"""Planeswalkers you control have "`<quoted ability>`." - a group quoted
ability grant (CR 113.10a, CR 611.3, CR 613.1f).

Every CR number here was looked up with `mise run rules:find <number>`
against the checksum-verified 2026-09-25 Comprehensive Rules release in the
session that wrote this file.

- **CR 113.10a** - "An effect that adds an activated ability may include
  activation instructions for that ability. These instructions become part of
  the ability that's added to the object." The quoted line - loyalty symbol,
  colon and all - is not decoration; it is what the object gains.
- **CR 611.3** / **CR 611.3b** - a static ability's continuous effect "applies
  at all times that the permanent generating it is on the battlefield", which
  is why the grant is live only while the granting permanent is, and why it
  is judged off the *computed* board (CR 613.5) rather than the printed card.
- **CR 613.1f** - "Layer 6: Ability-adding effects ... are applied", the layer
  this grant lands in, same as any other "has/have `<ability>`" sentence.

**The mechanism under test, not the cards.** Every card below is a real,
differently-shaped printing of the identical sentence -
`"Planeswalkers you control have \"<ability>\"."` - read by
`machines/layers._GROUP_QUOTED_ABILITY_GRANT_RE` and
`_group_quoted_ability_grant_builder`: a static restriction with no cost at
all (Tomik), a positive-loyalty damage-and-lifegain ability (Sanctum Lurker),
a double-digit negative-loyalty counter ability (Avatar of Burgeoning
Echoes), and six "Way of the `<name>`" enchantments whose granted lines are
six unrelated shapes - a delayed spell copy, an optional sacrifice-for-token,
a token-plus-surveil, a mana ability, a two-target damage split, and a plain
token creation. Proving the grant lands and is activatable on this spread is
what proves the mechanism is general, not merely that six cards happen to
work.

Every scenario stages the granting permanent alongside Jace, Reality
Sculptor - a real planeswalker with its own three printed loyalty abilities
that none of these grants touch - on the same controller's battlefield, so
the assertion is about what the *grant* adds, not about a walker built for
one card.

**A confirmed and since-fixed engine gap, found while writing this file.**
CR 107.7 prints a loyalty symbol in brackets - `[+N]`, `[0]`, `[-N]` - and
that is exactly how every one of these cards' *quoted* granted lines is
templated (Sanctum Lurker's own oracle text reads `"[+2]: This planeswalker
deals 1 damage..."`, brackets included). A planeswalker's own *printed*
card never carries the brackets (Jace, Reality Sculptor's `+1:`, `−3:`,
`0:` have none), so `machines/abilities._LOYALTY_SYMBOL` - the regex
`_classify_cost` matches a cost piece against to recognise a loyalty
ability at all (CR 606.2) - was only ever written to match the bracket-free
shape, which classified a granted line's own bracketed symbol as
`CostKind.OTHER` and made `Game.activation_cost` refuse it outright. Fixed
by making the brackets optional in `_LOYALTY_SYMBOL` itself, so every
granted loyalty ability in the pool - not only the ones below - now
activates the ordinary way. Also found and fixed alongside it: Way of the
Warlord's own two-target damage split ("deals 2 damage to up to one target
creature or planeswalker **and** 2 damage to target player") needed a new
merge (`_merge_split_damage_clauses`, `machines/effects.py`) for the
"and"-joined pair `_CLAUSE_SEPARATOR` cuts the shared subject off of -
proven off-set on Lunge's identically-shaped "Lunge deals 2 damage to
target creature and 2 damage to target player or planeswalker."

Every scenario below - including Warlord's own two-target damage split -
is now a plain, passing test; none of this file's tests are `xfail`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import CardState, Counter
from magic_cards_model.models.token import PREDEFINED, TokenState, create_tokens
from tests.scenarios.harness import Scenario

JACE = "Jace, Reality Sculptor"


def _board(granter: str, *, opponent_battlefield: list[str] | None = None) -> Scenario:
    """`granter` and Jace, Reality Sculptor on alice's battlefield; an
    opponent with whatever `opponent_battlefield` names, empty by default."""
    scenario = Scenario().player("alice", battlefield=[granter, JACE])
    scenario.player("bob", battlefield=list(opponent_battlefield or []))
    return scenario


def _jace(scenario: Scenario) -> CardState:
    return scenario.find(JACE, Zone.BATTLEFIELD, "alice")


# --------------------------------------------------------------------------
# Tomik, Orzhov Lawmage - a static restriction, no cost at all
# --------------------------------------------------------------------------

TOMIK_ABILITY = "No more than one creature can attack this planeswalker each combat."


def test_tomik_grants_the_restriction_to_a_planeswalker_it_does_not_print_it_on():
    """Tomik's own line never mentions Jace by name - CR 611.3's own
    "applies ... to whatever its text indicates" group subject is what
    reaches him."""
    scenario = _board("Tomik, Orzhov Lawmage").build()
    jace = _jace(scenario)

    board = scenario.game.computed_board()
    assert board.of(jace).has_ability(TOMIK_ABILITY)
    assert jace.granted_ability_texts == (TOMIK_ABILITY,)


def test_tomiks_restriction_is_not_an_activated_ability():
    """It carries no cost (CR 602.1 needs one), so it never reaches
    `Game.activated_abilities` - only the three printed loyalty abilities do.
    """
    scenario = _board("Tomik, Orzhov Lawmage").build()
    jace = _jace(scenario)
    scenario.game.computed_board()

    abilities = scenario.game.activated_abilities(jace)
    assert [a.effect for a in abilities] == [
        "Empower Jace X, where X is the number of Islands you control.",
        "Until your next turn, whenever a creature attacks you or a planeswalker "
        "you control, it gets -5/-0 until end of turn.",
        "Exile all but the bottom card of each opponent's library.",
    ]


# --------------------------------------------------------------------------
# Sanctum Lurker - a positive-loyalty damage-and-lifegain ability
# --------------------------------------------------------------------------

SANCTUM_LURKER_ABILITY = (
    "[+2]: This planeswalker deals 1 damage to each opponent and you gain 1 life."
)


def test_sanctum_lurker_grants_its_quoted_ability_to_the_planeswalker():
    scenario = _board("Sanctum Lurker").build()
    jace = _jace(scenario)

    board = scenario.game.computed_board()
    assert board.of(jace).has_ability(SANCTUM_LURKER_ABILITY)
    assert jace.granted_ability_texts == (SANCTUM_LURKER_ABILITY,)

    (granted,) = [
        a for a in scenario.game.activated_abilities(jace) if a.raw == SANCTUM_LURKER_ABILITY
    ]
    assert granted.cost == "[+2]"
    assert (
        granted.effect == "This planeswalker deals 1 damage to each opponent and you gain 1 life."
    )


def test_activating_sanctum_lurkers_granted_ability_damages_bob_and_gains_alice_life():
    scenario = _board("Sanctum Lurker").build()
    jace = _jace(scenario)

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.computed_board()

    index = next(
        i
        for i, a in enumerate(scenario.game.activated_abilities(jace))
        if a.raw == SANCTUM_LURKER_ABILITY
    )
    ability = scenario.activate(jace, index=index)
    assert ability is not None
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21


# --------------------------------------------------------------------------
# Avatar of Burgeoning Echoes - a double-digit negative-loyalty counter ability
# --------------------------------------------------------------------------

AVATAR_ABILITY = "[−10]: Put a +1/+1 counter on target creature for each land you control."


def test_avatar_of_burgeoning_echoes_grants_its_quoted_ability_to_the_planeswalker():
    scenario = _board("Avatar of Burgeoning Echoes").build()
    jace = _jace(scenario)

    board = scenario.game.computed_board()
    assert board.of(jace).has_ability(AVATAR_ABILITY)
    assert jace.granted_ability_texts == (AVATAR_ABILITY,)

    (granted,) = [a for a in scenario.game.activated_abilities(jace) if a.raw == AVATAR_ABILITY]
    assert granted.cost == "[−10]"
    assert granted.effect == "Put a +1/+1 counter on target creature for each land you control."


def test_activating_avatars_granted_ability_counters_a_target_creature_per_land():
    scenario = _board("Avatar of Burgeoning Echoes", opponent_battlefield=["Grizzly Bears"]).build()
    jace = _jace(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.computed_board()
    jace.add_counters(Counter.LOYALTY, 5)  # 5 printed + 5 = 10, enough for CR 606.6

    index = next(
        i for i, a in enumerate(scenario.game.activated_abilities(jace)) if a.raw == AVATAR_ABILITY
    )
    scenario.activate(jace, index=index, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.counter_count(Counter.PLUS_ONE) == 0, "alice controls no lands in this scenario"


# --------------------------------------------------------------------------
# Way of the `<name>` - six differently-shaped granted loyalty abilities
# --------------------------------------------------------------------------

WAY_OF_THE_CRYOMANCER_ABILITY = (
    "[−3]: When you next cast an instant or sorcery spell this turn, copy that spell. "
    "You may choose new targets for the copy."
)
WAY_OF_THE_DEATHBRINGER_ABILITY = (
    "[−2]: You may sacrifice a creature. If you do, create a 4/4 green Beast creature "
    "token with trample."
)
WAY_OF_THE_HEALER_ABILITY = (
    "[−2]: Create a 2/2 colorless Wizard Soldier creature token named Cadet. Surveil 1."
)
WAY_OF_THE_PYROMANCER_ABILITY = "[+1]: Add {R}."
WAY_OF_THE_WARLORD_ABILITY = (
    "[−4]: This planeswalker deals 2 damage to up to one target creature or planeswalker "
    "and 2 damage to target player."
)
WAY_OF_THE_WILDSPEAKER_ABILITY = "[−4]: Create a 4/4 green Beast creature token with trample."


@pytest.mark.parametrize(
    "card_name,ability_text",
    [
        ("Way of the Cryomancer", WAY_OF_THE_CRYOMANCER_ABILITY),
        ("Way of the Deathbringer", WAY_OF_THE_DEATHBRINGER_ABILITY),
        ("Way of the Healer", WAY_OF_THE_HEALER_ABILITY),
        ("Way of the Pyromancer", WAY_OF_THE_PYROMANCER_ABILITY),
        ("Way of the Warlord", WAY_OF_THE_WARLORD_ABILITY),
        ("Way of the Wildspeaker", WAY_OF_THE_WILDSPEAKER_ABILITY),
    ],
)
def test_each_way_of_the_name_grants_its_own_quoted_ability_to_the_planeswalker(
    card_name: str, ability_text: str
):
    """Six unrelated ability bodies - a delayed spell copy, an optional
    sacrifice-for-token, a token-plus-surveil, a mana ability, a two-target
    damage split, and a plain token creation - reach `Game.activated_abilities`
    off the identical grant sentence, which is the generality claim this
    mechanism makes (`docs/CLAUDE.md`'s "target the mechanic, never the
    card")."""
    scenario = _board(card_name).build()
    jace = _jace(scenario)

    board = scenario.game.computed_board()
    assert board.of(jace).has_ability(ability_text)
    assert jace.granted_ability_texts == (ability_text,)

    (granted,) = [a for a in scenario.game.activated_abilities(jace) if a.raw == ability_text]
    assert granted.raw == ability_text


def test_activating_way_of_the_pyromancers_granted_ability_adds_red_mana():
    """`[+1]: Add {R}.` - CR 605.1a's third criterion, "it's not a loyalty
    ability", is false of this one (CR 606.2), so unlike a plain mana ability
    it goes on the stack and the mana arrives only once it resolves - the same
    shape `test_loyalty_abilities.py`'s Ugin `0: Add {C}{C}{C}` test already
    proves for a *printed* loyalty ability."""
    scenario = _board("Way of the Pyromancer").build()
    jace = _jace(scenario)

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.computed_board()

    index = next(
        i
        for i, a in enumerate(scenario.game.activated_abilities(jace))
        if a.raw == WAY_OF_THE_PYROMANCER_ABILITY
    )
    ability = scenario.activate(jace, index=index)
    assert ability is not None
    scenario.pass_until_resolved()

    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}


def test_activating_way_of_the_wildspeakers_granted_ability_creates_a_beast_token():
    """`[−4]: Create a 4/4 green Beast creature token with trample.` - CR
    111.4's own unstated-name rule makes the token "Beast Token"."""
    scenario = _board("Way of the Wildspeaker").build()
    jace = _jace(scenario)

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.computed_board()

    index = next(
        i
        for i, a in enumerate(scenario.game.activated_abilities(jace))
        if a.raw == WAY_OF_THE_WILDSPEAKER_ABILITY
    )
    ability = scenario.activate(jace, index=index)
    assert ability is not None
    scenario.pass_until_resolved()

    beasts = [state for state in scenario.game.battlefield if state.name == "Beast Token"]
    assert len(beasts) == 1
    beast = beasts[0]
    assert (beast.power, beast.toughness) == (4, 4)
    assert beast.card.colors == [Color.GREEN]
    assert has_keyword(beast, Keyword.TRAMPLE, scenario.game)


def test_activating_way_of_the_warlords_granted_ability_splits_damage_between_creature_and_player():
    """`[−4]: This planeswalker deals 2 damage to up to one target
    creature or planeswalker and 2 damage to target player.` - two targets of
    two different kinds from one ability, off the same granted-line reader as
    Sanctum Lurker's single-target one above.

    Ancient Silverback (6/5), not Grizzly Bears (2/2): CR 704.5g would put a
    2/2 into the graveyard the moment 2 damage marks it, which proves
    lethal damage, not that this specific clause marked exactly 2 -
    Ancient Silverback's own 5 toughness survives with the mark still
    readable."""
    scenario = _board("Way of the Warlord", opponent_battlefield=["Ancient Silverback"]).build()
    jace = _jace(scenario)
    silverback = scenario.creature("Ancient Silverback", "bob")

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.computed_board()

    index = next(
        i
        for i, a in enumerate(scenario.game.activated_abilities(jace))
        if a.raw == WAY_OF_THE_WARLORD_ABILITY
    )
    ability = scenario.activate(jace, index=index, targets=[silverback, "bob"])
    assert ability is not None
    scenario.pass_until_resolved()

    assert silverback.damage == 2
    assert scenario.player("bob").life == 18


# --------------------------------------------------------------------------
# Round 293-fra T3: every listed card's own empower trigger, and the grant's
# own CR 606 rules - all on the real refreshed printings.
#
# CR numbers looked up this session with `mise run rules:find`:
# - CR 701.71a - "To empower Jace N means 'If you don't control a Jace
#   planeswalker token, create a blue Jace planeswalker token with 0 loyalty,
#   [-1]: Surveil 1, and [-3]: Draw a card. Choose a Jace planeswalker token
#   you control. Put N loyalty counters on it.'"
# - CR 606.3 - a loyalty ability is activated only with an empty stack in a
#   main phase of your turn, and "only if no player has previously activated
#   a loyalty ability of that permanent that turn" - one limit, shared by
#   printed and granted loyalty abilities alike.
# - CR 606.4 - the cost is the loyalty counters the symbol shows.
# - CR 606.6 - a negative cost needs at least that many loyalty counters.
# - CR 605.1a - "it's not a loyalty ability" is one of a mana ability's own
#   criteria, so `[+1]: Add {R}.` is a loyalty ability, not a mana ability.
# - CR 704.5i - a planeswalker with loyalty 0 goes to its owner's graveyard.
# --------------------------------------------------------------------------


def _drain_stack(scenario) -> None:
    for _ in range(20):
        scenario.pass_until_resolved()
        if not scenario.game.stack and not scenario.pending_triggers:
            return
    raise AssertionError("stack never emptied")


def _jace_tokens(scenario, username: str = "alice") -> list[CardState]:
    return [
        permanent
        for permanent in scenario.game.battlefield
        if permanent.name == "Jace" and permanent.controller == username
    ]


def _advance_to_main(scenario, username: str, *, turns_from_now: int) -> None:
    """Advance to `username`'s precombat main phase, `turns_from_now` turn
    changes ahead."""
    seen = 0
    previous_active = scenario.game.active_player.username
    for _ in range(80):
        scenario.advance()
        active = scenario.game.active_player.username
        if active != previous_active:
            seen += 1
            previous_active = active
        if seen >= turns_from_now and active == username and scenario.step is Step.PRECOMBAT_MAIN:
            return
    raise AssertionError(f"never reached {username}'s main phase")


def _granted_index(scenario, walker: CardState, ability_text: str) -> int:
    scenario.game.computed_board()
    return next(
        i for i, a in enumerate(scenario.game.activated_abilities(walker)) if a.raw == ability_text
    )


@pytest.mark.parametrize(
    "card_name,amount,ability_text",
    [
        ("Way of the Cryomancer", 5, WAY_OF_THE_CRYOMANCER_ABILITY),
        ("Way of the Deathbringer", 5, WAY_OF_THE_DEATHBRINGER_ABILITY),
        ("Way of the Healer", 5, WAY_OF_THE_HEALER_ABILITY),
        ("Way of the Pyromancer", 2, WAY_OF_THE_PYROMANCER_ABILITY),
        ("Way of the Warlord", 5, WAY_OF_THE_WARLORD_ABILITY),
        ("Way of the Wildspeaker", 7, WAY_OF_THE_WILDSPEAKER_ABILITY),
        ("Sanctum Lurker", 1, SANCTUM_LURKER_ABILITY),
    ],
)
def test_each_cards_etb_empower_creates_the_jace_token_which_carries_the_grant(
    card_name: str, amount: int, ability_text: str
):
    """No Jace token controlled: CR 701.71a creates a blue 0-loyalty "Jace"
    token and puts N counters on it (CR 306.5c: its loyalty is those
    counters). The token is a planeswalker alice controls, so the very
    permanent that empowered it grants it its own quoted ability too."""
    scenario = Scenario().player("alice", hand=[card_name]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield(card_name)
    _drain_stack(scenario)

    (token,) = _jace_tokens(scenario)
    assert isinstance(token, TokenState)
    assert token.loyalty == amount
    assert token.counter_count(Counter.LOYALTY) == amount
    assert token.card.colors == [Color.BLUE]
    board = scenario.game.computed_board()
    assert board.of(token).has_ability(ability_text)
    raws = [a.raw for a in scenario.game.activated_abilities(token)]
    assert ability_text in raws
    assert len(raws) == 3, "the token's own [-1] and [-3] plus the grant"


def test_avatar_landfall_empowers_two_and_a_second_landfall_reuses_the_token():
    """Avatar of Burgeoning Echoes: "Whenever a land you control enters,
    empower Jace 2." The first landfall creates the token; the second finds
    it already controlled and only adds counters - no second token."""
    scenario = (
        Scenario()
        .player("alice", hand=["Forest", "Island"], battlefield=["Avatar of Burgeoning Echoes"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.play_land("Forest")
    _drain_stack(scenario)
    (token,) = _jace_tokens(scenario)
    assert token.loyalty == 2

    scenario.put_onto_battlefield("Island")
    _drain_stack(scenario)
    assert _jace_tokens(scenario) == [token]
    assert token.loyalty == 4


def test_a_non_token_jace_does_not_stop_empower_from_creating_the_token():
    """CR 701.71a asks for a Jace planeswalker *token*: Jace, Reality
    Sculptor is a Jace planeswalker but not a token, so landfall still
    creates the token and leaves the Sculptor's loyalty alone."""
    scenario = (
        Scenario()
        .player("alice", hand=["Forest"], battlefield=["Avatar of Burgeoning Echoes", JACE])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sculptor = _jace(scenario)

    scenario.play_land("Forest")
    _drain_stack(scenario)

    (token,) = _jace_tokens(scenario)
    assert token.loyalty == 2
    assert sculptor.loyalty == 5


def test_with_two_jace_tokens_sanctum_lurkers_empower_goes_on_the_chosen_one():
    """CR 701.71a's "Choose a Jace planeswalker token you control" - two
    tokens, the controller picks; the other is untouched."""
    scenario = Scenario().player("alice", hand=["Sanctum Lurker"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = create_tokens(scenario.game, PREDEFINED["Jace"], "alice", count=2)
    scenario.game.add_counters(first, Counter.LOYALTY, 3)
    scenario.game.add_counters(second, Counter.LOYALTY, 4)

    scenario.will_choose_cards(second, source="Sanctum Lurker")
    scenario.put_onto_battlefield("Sanctum Lurker")
    _drain_stack(scenario)

    assert first.loyalty == 3
    assert second.loyalty == 5
    assert len(_jace_tokens(scenario)) == 2


def test_the_jace_tokens_own_minus_one_surveils_and_minus_three_draws():
    """The token's own two loyalty abilities (CR 701.71a) activate the
    ordinary way: [-1] surveils 1 (CR 701.25a), and the next turn [-3]
    draws a card."""
    scenario = (
        Scenario()
        .player("alice", hand=["Way of the Wildspeaker"], library=["Forest"] * 6)
        .player("bob", library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Way of the Wildspeaker")
    _drain_stack(scenario)
    (token,) = _jace_tokens(scenario)
    assert token.loyalty == 7

    top = scenario.top_of_library(1, "alice")[0]
    scenario.surveil_to_graveyard(top)
    scenario.activate(token, index=0)  # "[-1]: Surveil 1."
    _drain_stack(scenario)
    assert token.loyalty == 6
    assert top.zone is Zone.GRAVEYARD

    assert scenario.why_cannot_activate(token, 1) is not None, "CR 606.3: once per turn"

    _advance_to_main(scenario, "alice", turns_from_now=1)
    hand_before = len(scenario.player("alice").hand)
    scenario.activate(token, index=1)  # "[-3]: Draw a card."
    _drain_stack(scenario)
    assert token.loyalty == 3
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_a_jace_token_that_pays_its_last_counters_goes_to_the_graveyard():
    """CR 704.5i: Way of the Pyromancer's empower 2 makes a 2-loyalty token,
    which pays both counters to Way of the Healer's granted [-2]; with no
    Sanctum Lurker around it is put into the graveyard at the next check,
    while the ability itself still resolves (CR 113.7a)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Way of the Pyromancer"], battlefield=["Way of the Healer"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Way of the Pyromancer")
    _drain_stack(scenario)
    (token,) = _jace_tokens(scenario)
    assert token.loyalty == 2

    scenario.surveil_keeping_everything_on_top()
    scenario.activate(token, index=_granted_index(scenario, token, WAY_OF_THE_HEALER_ABILITY))
    assert token.loyalty == 0
    _drain_stack(scenario)

    assert _jace_tokens(scenario) == []
    assert [s.name for s in scenario.game.battlefield if s.name == "Cadet"] == ["Cadet"]


# -- the grant's own CR 606 rules ------------------------------------------


def test_a_granted_loyalty_ability_shares_the_once_per_turn_limit():
    """CR 606.3: activating Sanctum Lurker's granted [+2] uses up Jace's one
    loyalty activation this turn, so his printed +1 is refused after it."""
    scenario = _board("Sanctum Lurker").build()
    jace = _jace(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    index = _granted_index(scenario, jace, SANCTUM_LURKER_ABILITY)
    scenario.activate(jace, index=index)
    _drain_stack(scenario)
    assert jace.loyalty == 7

    assert scenario.why_cannot_activate(jace, 0) is not None
    assert scenario.why_cannot_activate(jace, index) is not None


def test_a_printed_loyalty_activation_blocks_the_granted_one_the_same_turn():
    scenario = _board("Sanctum Lurker").build()
    jace = _jace(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.activate(jace, index=0)  # Jace's printed +1
    _drain_stack(scenario)

    index = _granted_index(scenario, jace, SANCTUM_LURKER_ABILITY)
    assert scenario.why_cannot_activate(jace, index) is not None


def test_a_granted_negative_cost_needs_that_many_loyalty_counters():
    """CR 606.6: Avatar's [-10] on a 5-loyalty Jace is refused."""
    scenario = _board("Avatar of Burgeoning Echoes").build()
    jace = _jace(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    index = _granted_index(scenario, jace, AVATAR_ABILITY)
    assert jace.loyalty == 5
    assert scenario.why_cannot_activate(jace, index) is not None


def test_avatars_granted_ability_counts_lands_at_resolution():
    """ "for each land you control" is counted as the ability resolves: a
    land entering while it waits on the stack is counted too (and its own
    landfall empower resolves first, above it)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Forest"],
            battlefield=["Avatar of Burgeoning Echoes", JACE, "Forest", "Forest"],
        )
        .player("bob", battlefield=["Ancient Silverback"])
        .build()
    )
    jace = _jace(scenario)
    silverback = scenario.creature("Ancient Silverback", "bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace.add_counters(Counter.LOYALTY, 5)

    index = _granted_index(scenario, jace, AVATAR_ABILITY)
    scenario.activate(jace, index=index, targets=[silverback])
    scenario.put_onto_battlefield("Forest")
    _drain_stack(scenario)

    assert silverback.counter_count(Counter.PLUS_ONE) == 3


def test_the_grant_reaches_a_planeswalker_that_enters_later():
    scenario = (
        Scenario()
        .player("alice", hand=[JACE], battlefield=["Way of the Wildspeaker"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sculptor = scenario.put_onto_battlefield(JACE)
    _drain_stack(scenario)

    board = scenario.game.computed_board()
    assert board.of(sculptor).has_ability(WAY_OF_THE_WILDSPEAKER_ABILITY)


def test_the_grant_disappears_when_the_granting_permanent_leaves():
    scenario = _board("Way of the Wildspeaker").build()
    jace = _jace(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    way = scenario.find("Way of the Wildspeaker", Zone.BATTLEFIELD, "alice")

    assert scenario.game.computed_board().of(jace).has_ability(WAY_OF_THE_WILDSPEAKER_ABILITY)
    scenario.game.destroy(way)

    board = scenario.game.computed_board()
    assert not board.of(jace).has_ability(WAY_OF_THE_WILDSPEAKER_ABILITY)
    assert WAY_OF_THE_WILDSPEAKER_ABILITY not in [
        a.raw for a in scenario.game.activated_abilities(jace)
    ]


def test_the_grant_does_not_reach_an_opponents_planeswalker():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Way of the Wildspeaker"])
        .player("bob", battlefield=[JACE])
        .build()
    )
    bobs = scenario.find(JACE, Zone.BATTLEFIELD, "bob")
    board = scenario.game.computed_board()
    assert not board.of(bobs).has_ability(WAY_OF_THE_WILDSPEAKER_ABILITY)


# -- each remaining granted ability, activated ----------------------------


def test_way_of_the_pyromancers_granted_mana_ability_keeps_loyalty_timing():
    """CR 605.1a + CR 606.3: `[+1]: Add {R}.` is a loyalty ability, so it is
    not activatable with a spell on the stack, nor on the opponent's turn."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Way of the Pyromancer", JACE])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain", JACE])
        .build()
    )
    jace = _jace(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    index = _granted_index(scenario, jace, WAY_OF_THE_PYROMANCER_ABILITY)
    assert scenario.why_cannot_activate(jace, index) is None

    # Anything on the stack: alice activates Jace's printed +1, keeps priority.
    scenario.activate(jace, index=0)
    assert scenario.game.stack
    assert scenario.why_cannot_activate(jace, index) is not None


def test_way_of_the_pyromancers_granted_ability_is_refused_on_the_opponents_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Way of the Pyromancer", JACE], library=["Forest"] * 5)
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    jace = _jace(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    index = _granted_index(scenario, jace, WAY_OF_THE_PYROMANCER_ABILITY)
    assert scenario.why_cannot_activate(jace, index) is None
    for _ in range(60):
        if scenario.game.active_player.username == "bob" and scenario.step is Step.PRECOMBAT_MAIN:
            break
        scenario.advance()
    assert scenario.game.active_player.username == "bob"
    assert scenario.why_cannot_activate(jace, index, "alice") is not None


def test_way_of_the_healers_granted_ability_makes_a_cadet_and_surveils():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Way of the Healer", JACE], library=["Forest"] * 3)
        .player("bob")
        .build()
    )
    jace = _jace(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top = scenario.top_of_library(1, "alice")[0]
    scenario.surveil_to_graveyard(top)

    index = _granted_index(scenario, jace, WAY_OF_THE_HEALER_ABILITY)
    scenario.activate(jace, index=index)
    _drain_stack(scenario)

    assert jace.loyalty == 3
    (cadet,) = [s for s in scenario.game.battlefield if s.name == "Cadet"]
    assert (cadet.power, cadet.toughness) == (2, 2)
    assert cadet.card.colors == []
    assert {"Wizard", "Soldier"} <= set(cadet.subtypes)
    assert top.zone is Zone.GRAVEYARD


@pytest.mark.parametrize("sacrifice", [True, False])
def test_way_of_the_deathbringers_granted_ability_is_an_optional_sacrifice(sacrifice: bool):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Way of the Deathbringer", JACE, "Grizzly Bears"])
        .player("bob")
        .build()
    )
    jace = _jace(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(sacrifice)
    if sacrifice:
        scenario.will_choose_cards(bears)

    index = _granted_index(scenario, jace, WAY_OF_THE_DEATHBRINGER_ABILITY)
    scenario.activate(jace, index=index)
    _drain_stack(scenario)

    beasts = [s for s in scenario.game.battlefield if s.name == "Beast Token"]
    assert jace.loyalty == 3
    if sacrifice:
        assert bears.zone is Zone.GRAVEYARD
        (beast,) = beasts
        assert (beast.power, beast.toughness) == (4, 4)
        assert has_keyword(beast, Keyword.TRAMPLE, scenario.game)
    else:
        assert bears.zone is Zone.BATTLEFIELD
        assert beasts == []


def test_way_of_the_cryomancers_granted_ability_copies_only_the_next_instant_or_sorcery():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Way of the Cryomancer", JACE, "Mountain", "Mountain"],
            hand=["Lightning Bolt", "Lightning Bolt"],
        )
        .player("bob", life=20)
        .build()
    )
    jace = _jace(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    index = _granted_index(scenario, jace, WAY_OF_THE_CRYOMANCER_ABILITY)
    scenario.activate(jace, index=index)
    _drain_stack(scenario)
    assert jace.loyalty == 2

    first, second = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Lightning Bolt", first, targets=["bob"])
    _drain_stack(scenario)
    assert scenario.player("bob").life == 14, "the bolt and its copy"

    scenario.cast_and_resolve("Lightning Bolt", second, targets=["bob"])
    _drain_stack(scenario)
    assert scenario.player("bob").life == 11, "the delayed trigger fires once"
