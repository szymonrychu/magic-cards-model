"""Scenario: "`<creatures>` you control have `<keyword(s)>` and "`<ability>`"."
- a static ability granting a group both a keyword and a quoted activated
ability in one sentence (`machines/layers._INDEFINITE_KEYWORD_AND_QUOTED_GRANT_RE`).

Inga and Esika is the reported card: "Creatures you control have vigilance and
"{T}: Add one mana of any color. Spend this mana only to cast a creature
spell."" - the quoted ability is a mana ability carrying a spend restriction.
Two second printings prove the reader is the template, not Inga's sentence:

- Esika, God of the Tree: "Other legendary creatures you control have
  vigilance and "{T}: Add one mana of any color."" - a qualified subject
  ("other legendary") and an unrestricted mana ability.
- Tocasia, Dig Site Mentor: "Creatures you control have vigilance and "{T}:
  Surveil 1."" - the quoted ability is not a mana ability at all.

All three legal in Modern and Pioneer (Scryfall legalities, 2026-10-03).

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 113.10** - an effect that adds an ability says the object "has" it.
- **CR 613.1f** - layer 6: ability-adding effects.
- **CR 611.3a** - a static ability's effect is not locked in; it applies at
  any moment to whatever its text indicates.
- **CR 604.2** - a static ability's effect lasts as long as its permanent
  remains on the battlefield.
- **CR 106.6** - mana produced with a restriction on how it may be spent.
- **CR 106.3** - the source of mana produced by an ability is that ability's
  source (here: the creature the ability was granted to).
- **CR 603.4** - the intervening "if" clause.
- **CR 702.20b** - attacking doesn't cause creatures with vigilance to tap.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

INGA = "{T}: Add one mana of any color. Spend this mana only to cast a creature spell."
ESIKA = "{T}: Add one mana of any color."
TOCASIA = "{T}: Surveil 1."


def _mine(scenario, name: str, username: str = "alice"):
    (state,) = [s for s in scenario.game.battlefield if s.name == name and s.controller == username]
    return state


def _all_mine(scenario, name: str, username: str = "alice"):
    return [s for s in scenario.game.battlefield if s.name == name and s.controller == username]


def _granted_index(scenario, permanent, text: str) -> int:
    assert text in scenario.game.characteristics_of(permanent).abilities
    (index,) = [
        i
        for i, ability in enumerate(scenario.game.activated_abilities(permanent))
        if f"{ability.cost}: {ability.effect}" == text
    ]
    return index


def _board(alice, *, hand=(), bob=("Llanowar Elves",), library=("Forest",) * 6):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), hand=list(hand), library=list(library))
        .player("bob", battlefield=list(bob), library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for permanent in scenario.game.battlefield:
        permanent.summoning_sick = False
    return scenario


def test_every_cards_static_line_is_handled() -> None:
    for name in ("Inga and Esika", "Esika, God of the Tree", "Tocasia, Dig Site Mentor"):
        clauses = [c for c in classify_clauses(card(name)) if c.text]
        assert {c.category for c in clauses} == {HANDLED}, (name, clauses)


# -- Inga and Esika ------------------------------------------------------------


def test_inga_grants_vigilance_and_the_mana_ability_to_each_creature_you_control() -> None:
    scenario = _board(["Inga and Esika", "Grizzly Bears"])

    for name in ("Inga and Esika", "Grizzly Bears"):
        abilities = scenario.game.characteristics_of(_mine(scenario, name)).abilities
        assert "Vigilance" in abilities or "vigilance" in [a.lower() for a in abilities], name
        assert INGA in abilities, name


def test_inga_does_not_reach_an_opponents_creature() -> None:
    scenario = _board(["Inga and Esika"])

    abilities = scenario.game.characteristics_of(_mine(scenario, "Llanowar Elves", "bob")).abilities

    assert INGA not in abilities
    assert "vigilance" not in [a.lower() for a in abilities]


def test_a_creature_attacking_under_inga_does_not_tap() -> None:
    """CR 702.20b, on the granted keyword."""
    scenario = _board(["Inga and Esika", "Grizzly Bears"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = _mine(scenario, "Grizzly Bears")

    scenario.attack_with(bears)

    assert scenario.game.is_attacking(bears)
    assert bears.untapped


def test_the_granted_mana_ability_makes_restricted_mana() -> None:
    scenario = _board(["Inga and Esika", "Grizzly Bears"])
    bears = _mine(scenario, "Grizzly Bears")

    scenario.activate(bears, index=_granted_index(scenario, bears, INGA), color=Color.RED)

    assert bears.tapped
    (restricted,) = scenario.player().mana_pool.restricted
    assert restricted.restriction.understood is True


def test_the_granted_mana_pays_for_a_creature_spell() -> None:
    scenario = _board(["Inga and Esika", "Llanowar Elves", "Elvish Mystic"], hand=["Grizzly Bears"])
    for name in ("Llanowar Elves", "Elvish Mystic"):
        source = _mine(scenario, name)
        scenario.activate(source, index=_granted_index(scenario, source, INGA), color=Color.GREEN)

    casting = scenario.cast("Grizzly Bears", "alice")
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert _mine(scenario, "Grizzly Bears").zone is Zone.BATTLEFIELD


def test_the_granted_mana_refuses_a_noncreature_spell() -> None:
    """CR 106.6: the restriction rides on the mana the granted ability made."""
    scenario = _board(["Inga and Esika", "Grizzly Bears"], hand=["Giant Growth"])
    bears = _mine(scenario, "Grizzly Bears")
    scenario.activate(bears, index=_granted_index(scenario, bears, INGA), color=Color.GREEN)

    casting = scenario.cast("Giant Growth", "alice", targets=[bears])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="Spend this mana only to cast a creature spell"):
        payment.pay()
    casting.cancel()
    assert scenario.find("Giant Growth", Zone.HAND).zone is Zone.HAND


def test_a_creature_keeps_its_own_unrestricted_mana_ability() -> None:
    """The grant is additional (CR 113.10): Llanowar Elves still taps for {G}."""
    scenario = _board(["Inga and Esika", "Llanowar Elves"])
    elves = _mine(scenario, "Llanowar Elves")

    scenario.game.activate_ability(elves, 0, "alice")

    assert scenario.player().mana_pool.floating == {Color.GREEN: 1}
    assert scenario.player().mana_pool.restricted == []


def test_a_creature_that_enters_later_gets_the_grant() -> None:
    """CR 611.3a: not locked in to the creatures there when Inga entered."""
    scenario = _board(["Inga and Esika"], hand=["Grizzly Bears"])

    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")

    abilities = scenario.game.characteristics_of(bears).abilities
    assert INGA in abilities
    assert "vigilance" in [a.lower() for a in abilities]


def test_the_grant_ends_when_inga_leaves() -> None:
    """CR 604.2."""
    scenario = _board(["Inga and Esika", "Grizzly Bears"])
    scenario.game.put_into_graveyard(_mine(scenario, "Inga and Esika"))

    bears = _mine(scenario, "Grizzly Bears")
    abilities = scenario.game.characteristics_of(bears).abilities

    assert INGA not in abilities
    assert "vigilance" not in [a.lower() for a in abilities]
    assert len(scenario.game.activated_abilities(bears)) == 0


def test_three_granted_creature_mana_draws_a_card() -> None:
    """Inga's second ability, fed by its first: mana from the granted ability
    is mana from a creature (CR 106.3), so three of it spent on a creature
    spell satisfies the intervening "if" (CR 603.4)."""
    scenario = _board(
        ["Inga and Esika", "Grizzly Bears", "Grizzly Bears", "Grizzly Bears"] + ["Forest"] * 3,
        hand=["Colossal Dreadmaw"],
    )
    for bears in _all_mine(scenario, "Grizzly Bears"):
        scenario.activate(bears, index=_granted_index(scenario, bears, INGA), color=Color.GREEN)
    hand_before = len(scenario.player().hand)

    casting = scenario.cast("Colossal Dreadmaw", "alice")
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    scenario.put_on_stack(casting)
    scenario.game.put_triggers_on_stack()

    assert "Inga and Esika's triggered ability" in scenario.stack_names()
    scenario.resolve_top()
    # Dreadmaw left hand (-1), the trigger drew one (+1).
    assert len(scenario.player().hand) == hand_before


def test_two_granted_creature_mana_does_not_draw() -> None:
    scenario = _board(
        ["Inga and Esika", "Grizzly Bears", "Grizzly Bears"] + ["Forest"] * 4,
        hand=["Colossal Dreadmaw"],
    )
    for bears in _all_mine(scenario, "Grizzly Bears"):
        scenario.activate(bears, index=_granted_index(scenario, bears, INGA), color=Color.GREEN)

    casting = scenario.cast("Colossal Dreadmaw", "alice")
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    )
    scenario.put_on_stack(casting)
    scenario.game.put_triggers_on_stack()

    assert "Inga and Esika's triggered ability" not in scenario.stack_names()
    assert scenario.game.intervening_if_notices == []


# -- Esika, God of the Tree: "other legendary", no restriction ----------------


def test_esika_grants_other_legendary_creatures_only() -> None:
    scenario = _board(["Esika, God of the Tree", "Thalia, Guardian of Thraben", "Grizzly Bears"])

    thalia = scenario.game.characteristics_of(_mine(scenario, "Thalia, Guardian of Thraben"))
    bears = scenario.game.characteristics_of(_mine(scenario, "Grizzly Bears"))

    assert ESIKA in thalia.abilities
    assert "vigilance" in [a.lower() for a in thalia.abilities]
    assert ESIKA not in bears.abilities
    assert "vigilance" not in [a.lower() for a in bears.abilities]


def test_esika_does_not_grant_itself_a_second_copy() -> None:
    """ "Other": Esika keeps only its printed mana ability."""
    scenario = _board(["Esika, God of the Tree"])
    esika = _mine(scenario, "Esika, God of the Tree")

    abilities = scenario.game.characteristics_of(esika).abilities

    assert abilities.count(ESIKA) == 1


def test_esikas_granted_mana_is_unrestricted() -> None:
    scenario = _board(["Esika, God of the Tree", "Thalia, Guardian of Thraben"])
    thalia = _mine(scenario, "Thalia, Guardian of Thraben")

    scenario.activate(thalia, index=_granted_index(scenario, thalia, ESIKA), color=Color.BLUE)

    assert thalia.tapped
    assert scenario.player().mana_pool.floating == {Color.BLUE: 1}
    assert scenario.player().mana_pool.restricted == []


# -- Tocasia, Dig Site Mentor: a non-mana quoted ability ----------------------


def test_tocasia_grants_a_tap_surveil_ability_that_resolves() -> None:
    scenario = _board(["Tocasia, Dig Site Mentor", "Grizzly Bears"])
    bears = _mine(scenario, "Grizzly Bears")
    (top,) = scenario.top_of_library(1)
    scenario.surveil_to_graveyard(top)

    ability = scenario.activate(bears, index=_granted_index(scenario, bears, TOCASIA))
    assert ability is not None
    scenario.resolve_top()

    assert bears.tapped
    assert top.zone is Zone.GRAVEYARD


def test_tocasia_grant_ends_when_it_leaves() -> None:
    scenario = _board(["Tocasia, Dig Site Mentor", "Grizzly Bears"])
    scenario.game.put_into_graveyard(_mine(scenario, "Tocasia, Dig Site Mentor"))

    abilities = scenario.game.characteristics_of(_mine(scenario, "Grizzly Bears")).abilities

    assert TOCASIA not in abilities
