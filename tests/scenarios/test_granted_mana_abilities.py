"""Scenario: "`<permanents>` you control have "`<mana ability>`"." - a static
ability that grants a quoted mana ability to a group of permanents
(`machines/layers._GROUP_QUOTED_ABILITY_GRANT_RE`).

Resonating Lute is the reported card: "Lands you control have "{T}: Add two
mana of any one color. Spend this mana only to cast instant and sorcery
spells."" Cryptolith Rite is the second printing that proves the reader is
the template, not Lute's sentence: a different group (creatures, not lands),
a different mana ability ("one mana of any color") and no spend restriction.
Both legal in Modern and Pioneer (Scryfall legalities, 2026-09-26); Cryptolith
Rite is in no deck under `magic-cards-model-api/decks/`.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 113.10** - an effect that adds an ability says the object "has" it.
- **CR 613.1f** - layer 6: ability-adding effects.
- **CR 611.3a** - a static ability's effect is not locked in; it applies at
  any moment to whatever its text indicates.
- **CR 604.2** - a static ability's effect lasts as long as its permanent
  remains on the battlefield.
- **CR 106.6** - mana produced with a restriction on how it may be spent.
- **CR 302.6** - a creature's {T} ability can't be activated unless it has
  been under its controller's control since their most recent turn began.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

LUTE = (
    "{T}: Add two mana of any one color. Spend this mana only to cast instant and sorcery spells."
)
RITE = "{T}: Add one mana of any color."


def _mine(scenario, name: str, username: str = "alice"):
    (state,) = [s for s in scenario.game.battlefield if s.name == name and s.controller == username]
    return state


def _lute_board(*, hand=(), bob=("Forest",)):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=["Resonating Lute", "Island"])
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _granted_index(scenario, permanent, text: str) -> int:
    """The activation index of the granted line: `Game.activated_abilities`
    lists the printed/intrinsic abilities first and the granted one after."""
    assert text in scenario.game.characteristics_of(permanent).abilities
    (index,) = [
        i
        for i, ability in enumerate(scenario.game.activated_abilities(permanent))
        if f"{ability.cost}: {ability.effect}" == text
    ]
    return index


def test_both_cards_static_lines_are_handled() -> None:
    for name in ("Resonating Lute", "Cryptolith Rite"):
        clauses = [c for c in classify_clauses(card(name)) if c.text]
        assert {c.category for c in clauses} == {HANDLED}, name


def test_a_land_you_control_has_the_quoted_ability() -> None:
    scenario = _lute_board()

    chars = scenario.game.characteristics_of(_mine(scenario, "Island"))

    assert LUTE in chars.abilities


def test_the_granted_ability_makes_two_mana_of_one_chosen_color() -> None:
    scenario = _lute_board()
    island = _mine(scenario, "Island")

    index = _granted_index(scenario, island, LUTE)
    assert index == 1

    options = scenario.game.mana_color_options(island, index, "alice")
    scenario.activate(island, index=index, color=Color.RED)

    assert set(options) == {Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN}
    assert island.tapped
    assert scenario.player().mana_pool.floating == {Color.RED: 2}


def test_the_mana_pays_for_an_instant() -> None:
    scenario = _lute_board(hand=["Lightning Bolt"])
    island = _mine(scenario, "Island")
    scenario.game.activate_ability(island, 1, "alice", color=Color.RED)

    casting = scenario.cast("Lightning Bolt", "alice", targets=["bob"])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.game.player("bob").life == 17


def test_the_mana_pays_for_a_sorcery() -> None:
    scenario = _lute_board(hand=["Lava Spike"])
    island = _mine(scenario, "Island")
    scenario.game.activate_ability(island, 1, "alice", color=Color.RED)

    casting = scenario.cast("Lava Spike", "alice", targets=["bob"])
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.game.player("bob").life == 17


def test_the_mana_refuses_a_creature_spell() -> None:
    """CR 106.6: the restriction rides on the mana the granted ability made."""
    scenario = _lute_board(hand=["Goblin Guide"])
    island = _mine(scenario, "Island")
    scenario.game.activate_ability(island, 1, "alice", color=Color.RED)
    (restricted,) = scenario.player().mana_pool.restricted
    assert restricted.restriction.understood is True

    casting = scenario.cast("Goblin Guide", "alice")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="Spend this mana only to cast instant and sorcery"):
        payment.pay()
    casting.cancel()
    assert scenario.find("Goblin Guide", Zone.HAND).zone is Zone.HAND


def test_the_land_keeps_its_own_unrestricted_ability() -> None:
    """The grant is additional (CR 113.10): the Island still taps for {U}."""
    scenario = _lute_board()
    island = _mine(scenario, "Island")

    scenario.game.activate_ability(island, 0, "alice")

    assert scenario.player().mana_pool.floating == {Color.BLUE: 1}
    assert scenario.player().mana_pool.restricted == []


def test_an_opponents_land_does_not_have_it() -> None:
    scenario = _lute_board()

    chars = scenario.game.characteristics_of(_mine(scenario, "Forest", "bob"))

    assert LUTE not in chars.abilities


def test_a_land_that_enters_later_has_it_too() -> None:
    """CR 611.3a: not locked in to the lands there when the Lute entered."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mountain"], battlefield=["Resonating Lute"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    mountain = scenario.put_onto_battlefield("Mountain", "alice")

    assert LUTE in scenario.game.characteristics_of(mountain).abilities


def test_the_grant_ends_when_the_lute_leaves() -> None:
    """CR 604.2."""
    scenario = _lute_board()
    scenario.game.put_into_graveyard(_mine(scenario, "Resonating Lute"))

    chars = scenario.game.characteristics_of(_mine(scenario, "Island"))

    assert LUTE not in chars.abilities


def test_a_nonland_permanent_you_control_does_not_have_it() -> None:
    scenario = _lute_board()

    chars = scenario.game.characteristics_of(_mine(scenario, "Resonating Lute"))

    assert LUTE not in chars.abilities


# -- Cryptolith Rite: a creature group, a different mana ability ------------


def _rite_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cryptolith Rite", "Grizzly Bears", "Forest"])
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_cryptolith_rite_lets_a_settled_creature_tap_for_any_color() -> None:
    scenario = _rite_board()
    bears = _mine(scenario, "Grizzly Bears")
    bears.summoning_sick = False
    index = _granted_index(scenario, bears, RITE)

    scenario.activate(bears, index=index, color=Color.BLACK)

    assert bears.tapped
    assert scenario.player().mana_pool.floating == {Color.BLACK: 1}
    assert scenario.player().mana_pool.restricted == []


def test_cryptolith_rite_a_summoning_sick_creature_cannot_use_it() -> None:
    """CR 302.6: the granted {T} ability is still a creature's {T} ability."""
    scenario = _rite_board()
    bears = _mine(scenario, "Grizzly Bears")
    bears.summoning_sick = True
    index = _granted_index(scenario, bears, RITE)

    reason = scenario.why_cannot_activate(bears, index)

    assert reason is not None and "since their most recent turn began" in reason
    with pytest.raises(ValueError):
        scenario.activate(bears, index=index, color=Color.BLACK)
    assert not bears.tapped


def test_cryptolith_rite_does_not_reach_lands_or_opponents_creatures() -> None:
    scenario = _rite_board()

    assert RITE not in scenario.game.characteristics_of(_mine(scenario, "Forest")).abilities
    elves = _mine(scenario, "Llanowar Elves", "bob")
    assert RITE not in scenario.game.characteristics_of(elves).abilities
