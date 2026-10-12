"""Embalm, eternalize, cloak and disguise's self-reducing cost (EP-01 round 3, T4).

Rules read with `mise run rules:find` in the session that wrote this:

- **CR 702.128a** - embalm: "[Cost], Exile this card from your graveyard: Create
  a token that's a copy of this card, except it's white, it has no mana cost,
  and it's a Zombie in addition to its other types. Activate only as a sorcery."
- **CR 702.129a** - eternalize: the same, black and 4/4.
- **CR 707.9b** - a copy effect that modifies a characteristic as part of copying.
- **CR 701.58a** - cloak: a 2/2 face-down creature card with ward {2}.
- **CR 701.58b** - a cloaked creature card turns face up for its mana cost.
- **CR 701.58g** - a cloaked instant or sorcery card is revealed and left face down.
- **CR 702.168d** - turning a disguised permanent face up pays its disguise cost.
- **CR 708.8** - turning face up: no enters abilities.
- **CR 608.2g** - casting a spell during resolution.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import (
    off_zone_abilities,
    off_zone_activation,
    turn_face_up_cost,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import Scenario, mana_from


def _board(*, alice=None, bob=None, step=Step.PRECOMBAT_MAIN, manual=True):
    builder = Scenario().manual_turn_based_actions() if manual else Scenario()
    scenario = builder.player("alice", **(alice or {})).player("bob", **(bob or {})).build()
    scenario.start_at(step)
    return scenario


def _activate_off_zone(scenario, card, *sources, index=0):
    activation = off_zone_activation(scenario.game, card, "alice", index)
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    return activation


# ---- embalm / eternalize ---------------------------------------------------


def test_embalm_is_a_graveyard_ability_with_the_rule_s_cost():
    scenario = _board(alice={"graveyard": ["Trueheart Duelist"]})
    duelist = scenario.find("Trueheart Duelist", Zone.GRAVEYARD, "alice")
    (entry,) = off_zone_abilities(duelist.card, state=duelist, game=scenario.game)
    assert entry.family == "token_copy"
    assert entry.keyword == "Embalm"
    assert entry.zone is Zone.GRAVEYARD


def test_embalm_exiles_the_card_and_makes_a_white_zombie_copy_with_no_mana_cost():
    scenario = _board(
        alice={"graveyard": ["Trueheart Duelist"], "battlefield": ["Plains"] * 3},
    )
    duelist = scenario.find("Trueheart Duelist", Zone.GRAVEYARD, "alice")
    activation = _activate_off_zone(scenario, duelist, *scenario.untapped_sources(*["Plains"] * 3))
    assert duelist.zone is Zone.EXILE  # the exile is a cost (CR 702.128a)
    activation.resolve()
    (token,) = [
        p for p in scenario.game.battlefield if p.name == "Trueheart Duelist" and is_token(p)
    ]
    chars = scenario.game.characteristics_of(token)
    assert set(chars.colors) == {Color.WHITE}
    assert "Zombie" in chars.subtypes and "Human" in chars.subtypes
    assert chars.mana_value == 0
    assert (chars.power, chars.toughness) == (2, 2)
    # The copy keeps the printed static: it can block an additional creature.
    assert any("additional creature" in line for line in chars.abilities)


def test_embalm_on_a_second_printing_keeps_its_enters_trigger():
    scenario = _board(
        alice={"graveyard": ["Angel of Sanctions"], "battlefield": ["Plains"] * 6},
        bob={"battlefield": ["Grizzly Bears"]},
    )
    angel = scenario.find("Angel of Sanctions", Zone.GRAVEYARD, "alice")
    activation = _activate_off_zone(scenario, angel, *scenario.untapped_sources(*["Plains"] * 6))
    activation.resolve()
    (token,) = [p for p in scenario.game.battlefield if p.name == "Angel of Sanctions"]
    chars = scenario.game.characteristics_of(token)
    assert is_token(token) and set(chars.colors) == {Color.WHITE}
    assert "Zombie" in chars.subtypes and "Angel" in chars.subtypes
    assert (chars.power, chars.toughness) == (3, 4)
    scenario.game.put_triggers_on_stack()
    assert any("Angel of Sanctions" in name for name in scenario.stack_names())


def test_embalm_is_sorcery_speed_only():
    scenario = _board(
        alice={"graveyard": ["Trueheart Duelist"], "battlefield": ["Plains"] * 3},
        step=Step.UPKEEP,
    )
    duelist = scenario.find("Trueheart Duelist", Zone.GRAVEYARD, "alice")
    activation = off_zone_activation(scenario.game, duelist, "alice", 0)
    reason = activation.why_not()
    assert reason is not None and "sorcery" in reason.lower()


def test_embalm_cannot_be_activated_from_the_hand():
    scenario = _board(alice={"hand": ["Trueheart Duelist"], "battlefield": ["Plains"] * 3})
    duelist = scenario.find("Trueheart Duelist", Zone.HAND, "alice")
    activation = off_zone_activation(scenario.game, duelist, "alice", 0)
    reason = activation.why_not()
    assert reason is not None and "graveyard" in reason


def test_eternalize_makes_a_black_four_four():
    scenario = _board(
        alice={"graveyard": ["Fanatic of Rhonas"], "battlefield": ["Forest"] * 4},
    )
    fanatic = scenario.find("Fanatic of Rhonas", Zone.GRAVEYARD, "alice")
    entries = off_zone_abilities(fanatic.card, state=fanatic, game=scenario.game)
    index = next(i for i, e in enumerate(entries) if e.keyword == "Eternalize")
    activation = _activate_off_zone(
        scenario, fanatic, *scenario.untapped_sources(*["Forest"] * 4), index=index
    )
    activation.resolve()
    (token,) = [p for p in scenario.game.battlefield if p.name == "Fanatic of Rhonas"]
    chars = scenario.game.characteristics_of(token)
    assert set(chars.colors) == {Color.BLACK}
    assert (chars.power, chars.toughness) == (4, 4)
    assert "Zombie" in chars.subtypes and chars.mana_value == 0


# ---- disguise's self-reducing cost -------------------------------------------


def _cast_disguised(scenario, name):
    casting = scenario.cast(name)
    casting.use_keyword("Disguise")
    assert str(casting.total_cost.mana) == "{3}"
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * 3))
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_disguise_with_a_reduction_sentence_is_still_a_disguise_cast():
    scenario = _board(alice={"hand": ["Fugitive Codebreaker"], "battlefield": ["Mountain"] * 3})
    permanent = _cast_disguised(scenario, "Fugitive Codebreaker")
    assert permanent.face_down
    chars = scenario.game.characteristics_of(permanent)
    assert (chars.power, chars.toughness) == (2, 2)
    assert "Ward" in " ".join(chars.abilities)


@pytest.mark.parametrize(
    ("graveyard", "expected"),
    [
        ([], "{5}{R}"),
        (["Lightning Bolt"], "{4}{R}"),
        (["Lightning Bolt", "Divination", "Grizzly Bears"], "{3}{R}"),
        (["Lightning Bolt"] * 7, "{R}"),
    ],
)
def test_the_turn_up_cost_counts_instants_and_sorceries_in_the_graveyard(graveyard, expected):
    scenario = _board(
        alice={
            "hand": ["Fugitive Codebreaker"],
            "battlefield": ["Mountain"] * 3,
            "graveyard": graveyard,
        }
    )
    permanent = _cast_disguised(scenario, "Fugitive Codebreaker")
    cost = turn_face_up_cost(permanent, "alice", game=scenario.game)
    assert cost is not None and str(cost.mana) == expected
    # Without the game, nothing is counted: the printed cost.
    assert str(turn_face_up_cost(permanent, "alice").mana) == "{5}{R}"


def test_turning_codebreaker_up_for_the_reduced_cost_fires_its_trigger():
    scenario = _board(
        alice={
            "hand": ["Fugitive Codebreaker", "Island"],
            "battlefield": ["Mountain"] * 5,
            "graveyard": ["Lightning Bolt", "Divination", "Shock", "Opt"],
            "library": ["Plains"] * 5,
        }
    )
    permanent = _cast_disguised(scenario, "Fugitive Codebreaker")
    scenario.turn_face_up(permanent, *scenario.untapped_sources("Mountain", "Mountain"))
    assert permanent.face_up
    scenario.resolve_top()
    hand = [c.name for c in scenario.player("alice").hand]
    assert "Island" not in hand and len(hand) == 3


def test_a_plain_disguise_card_is_unchanged():
    scenario = _board(alice={"hand": ["Bubble Smuggler"], "battlefield": ["Island"] * 3})
    casting = scenario.cast("Bubble Smuggler")
    casting.use_keyword("Disguise")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Island"] * 3))
    scenario.put_on_stack(casting)
    permanent = scenario.resolve_top()
    cost = turn_face_up_cost(permanent, "alice", game=scenario.game)
    assert cost is not None and str(cost.mana) == "{5}{U}"


# ---- cloak -------------------------------------------------------------------


def _combat_damage_with(scenario, *attackers):
    scenario.attack_with(*attackers)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()


def test_etrata_cloaks_the_damaged_player_s_top_card_under_its_controller():
    scenario = _board(
        alice={"battlefield": ["Etrata, Deadly Fugitive"]},
        bob={"library": ["Grizzly Bears", "Forest"]},
        step=Step.DECLARE_ATTACKERS,
        manual=False,
    )
    etrata = scenario.find("Etrata, Deadly Fugitive", Zone.BATTLEFIELD, "alice")
    _combat_damage_with(scenario, etrata)
    scenario.resolve_top()
    (cloaked,) = [p for p in scenario.game.battlefield if p.face_down]
    assert cloaked.card.name == "Grizzly Bears"
    assert cloaked.controller == "alice" and cloaked.owner == "bob"
    chars = scenario.game.characteristics_of(cloaked)
    assert (chars.power, chars.toughness) == (2, 2)
    assert "Ward" in " ".join(chars.abilities)
    assert [c.name for c in scenario.player("bob").library] == ["Forest"]


def test_a_cloaked_creature_turns_up_for_its_mana_cost():
    scenario = _board(
        alice={"battlefield": ["Etrata, Deadly Fugitive", "Forest", "Forest"]},
        bob={"library": ["Grizzly Bears"]},
        step=Step.DECLARE_ATTACKERS,
        manual=False,
    )
    etrata = scenario.find("Etrata, Deadly Fugitive", Zone.BATTLEFIELD, "alice")
    _combat_damage_with(scenario, etrata)
    scenario.resolve_top()
    (cloaked,) = [p for p in scenario.game.battlefield if p.face_down]
    cost = turn_face_up_cost(cloaked, "alice", game=scenario.game)
    assert cost is not None and str(cost.mana) == "{1}{G}"
    scenario.turn_face_up(cloaked, *scenario.untapped_sources("Forest", "Forest"))
    assert cloaked.face_up and scenario.game.characteristics_of(cloaked).power == 2


def test_an_empty_library_cloaks_nothing():
    scenario = _board(
        alice={"battlefield": ["Etrata, Deadly Fugitive"]},
        step=Step.DECLARE_ATTACKERS,
        manual=False,
    )
    etrata = scenario.find("Etrata, Deadly Fugitive", Zone.BATTLEFIELD, "alice")
    scenario.player("bob").zones[Zone.LIBRARY].clear()
    _combat_damage_with(scenario, etrata)
    scenario.resolve_top()
    assert not [p for p in scenario.game.battlefield if p.face_down]


def test_vannifar_cloaks_a_card_from_its_controller_s_hand():
    scenario = _board(
        alice={"battlefield": ["Vannifar, Evolved Enigma"], "hand": ["Grizzly Bears"]},
        manual=False,
    )
    scenario.will_choose_mode("Cloak a card from your hand.")
    scenario.advance()
    scenario.pass_until_resolved()
    (cloaked,) = [p for p in scenario.game.battlefield if p.face_down]
    assert cloaked.card.name == "Grizzly Bears" and cloaked.controller == "alice"
    assert not scenario.player("alice").hand


# ---- Etrata's granted turn-up-or-exile ability ---------------------------------


def _cloaked_under_etrata(scenario):
    etrata = scenario.find("Etrata, Deadly Fugitive", Zone.BATTLEFIELD, "alice")
    _combat_damage_with(scenario, etrata)
    scenario.resolve_top()
    (cloaked,) = [p for p in scenario.game.battlefield if p.face_down]
    return cloaked


def test_face_down_creatures_gain_the_turn_up_ability():
    scenario = _board(
        alice={"battlefield": ["Etrata, Deadly Fugitive", "Island", "Island", "Swamp", "Swamp"]},
        bob={"library": ["Grizzly Bears"]},
        step=Step.DECLARE_ATTACKERS,
        manual=False,
    )
    cloaked = _cloaked_under_etrata(scenario)
    ability = scenario.activate(
        cloaked, *scenario.untapped_sources("Island", "Island", "Swamp", "Swamp")
    )
    assert ability is not None
    scenario.resolve_top()
    assert cloaked.face_up and cloaked.zone is Zone.BATTLEFIELD
    assert not scenario.player("bob").graveyard


def test_a_cloaked_sorcery_is_exiled_and_may_be_cast_free():
    scenario = _board(
        alice={
            "battlefield": ["Etrata, Deadly Fugitive", "Island", "Island", "Swamp", "Swamp"],
        },
        bob={"library": ["Divination", "Forest", "Forest", "Forest"]},
        step=Step.DECLARE_ATTACKERS,
        manual=False,
    )
    cloaked = _cloaked_under_etrata(scenario)
    scenario.will_take_the_may()
    scenario.activate(cloaked, *scenario.untapped_sources("Island", "Island", "Swamp", "Swamp"))
    scenario.resolve_top()
    assert cloaked.zone is not Zone.BATTLEFIELD
    assert "Divination" in scenario.stack_names() or scenario.player("bob").graveyard


def test_the_grant_reaches_only_face_down_creatures():
    scenario = _board(
        alice={"battlefield": ["Etrata, Deadly Fugitive", "Grizzly Bears"]},
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    lines = scenario.game.characteristics_of(bears).abilities
    assert not any("Turn this creature face up" in line for line in lines)
