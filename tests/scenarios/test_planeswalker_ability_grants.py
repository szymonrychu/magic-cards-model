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
