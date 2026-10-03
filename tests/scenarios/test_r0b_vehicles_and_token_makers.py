"""Scenario: Vehicles with enters/attack triggers, and token makers.

Esika's Chariot (two Cat tokens on entering, crew 4, an attack trigger
copying a token you control), Thundering Broodwagon (reach, menace, crew 3,
an enters destroy and cycling), Warleader's Call (an anthem plus a ping per
creature entering) and Hop to It (three Rabbits), each played through the
engine.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 702.122a** - Crew N: "Tap any number of other untapped creatures you
  control with total power N or greater: This permanent becomes an artifact
  creature until end of turn."
- **CR 707.2** - a token copy acquires the copiable values of the original.
- **CR 603.6a** - an enters ability triggers for each permanent entering,
  newcomers included.
- **CR 608.2b** - a target gone by resolution is illegal.
- **CR 702.111b** - menace: can't be blocked except by two or more creatures.
- **CR 702.17a** - reach is a static ability.
- **CR 702.29a** - cycling: "[Cost], Discard this card: Draw a card."
- **CR 613.4c** - layer 7c: effects that modify power and toughness.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario

CHARIOT = "Esika's Chariot"
BROODWAGON = "Thundering Broodwagon"
CALL = "Warleader's Call"


def _resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _tokens(scenario, name, username="alice"):
    return [
        p
        for p in scenario.game.battlefield
        if p.token
        and p.name == f"{name} Token"
        and scenario.game.controller_of(p).username == username
    ]


def _crew(scenario, vehicle, *creatures):
    activation = crew_activation(scenario.game, vehicle, list(creatures), "alice")
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()


def _board(alice=(), bob=(), *, hand=(), bob_hand=()):
    return (
        Scenario()
        .player("alice", battlefield=list(alice), hand=list(hand), library=["Island"] * 5)
        .player("bob", battlefield=list(bob), hand=list(bob_hand), library=["Island"] * 5)
        .build()
    )


# -- Esika's Chariot ----------------------------------------------------------


def _chariot_in_play(alice=(), bob=()):
    scenario = _board(alice, bob, hand=[CHARIOT])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chariot = scenario.put_onto_battlefield(CHARIOT, "alice")
    _resolve_everything(scenario)
    return scenario, chariot


def test_esikas_chariot_entering_makes_two_green_cats():
    scenario, chariot = _chariot_in_play()

    cats = _tokens(scenario, "Cat")
    assert len(cats) == 2
    for cat in cats:
        chars = _chars(scenario, cat)
        assert (chars.power, chars.toughness) == (2, 2)
        assert Type.CREATURE in chars.types
        assert "Cat" in chars.subtypes
    assert Type.CREATURE not in _chars(scenario, chariot).types


def test_esikas_chariot_crewed_by_its_two_cats_is_a_four_four_creature():
    """CR 702.122a: two 2/2 Cats are exactly the crew 4."""
    scenario, chariot = _chariot_in_play()
    cats = _tokens(scenario, "Cat")

    _crew(scenario, chariot, *cats)

    chars = _chars(scenario, chariot)
    assert Type.CREATURE in chars.types and Type.ARTIFACT in chars.types
    assert (chars.power, chars.toughness) == (4, 4)
    assert all(cat.tapped for cat in cats)


def test_esikas_chariot_one_cat_is_not_enough_crew():
    scenario, chariot = _chariot_in_play()
    cat = _tokens(scenario, "Cat")[0]

    with pytest.raises(ValueError):
        _crew(scenario, chariot, cat)
    assert Type.CREATURE not in _chars(scenario, chariot).types


def _chariot_with_rabbits():
    """The Chariot has been Alice's since the turn began; Hop to It makes
    three Rabbit tokens to copy, and two Bears crew it."""
    scenario = _board(
        [CHARIOT, "Grizzly Bears", "Grizzly Bears", "Plains", "Plains", "Plains"],
        hand=["Hop to It"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Hop to It", *scenario.untapped_sources("Plains", "Plains", "Plains"))
    _resolve_everything(scenario)
    chariot = scenario.find(CHARIOT, Zone.BATTLEFIELD, "alice")
    _crew(
        scenario, chariot, *scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario, chariot


def test_esikas_chariot_attacking_copies_a_target_token_you_control():
    scenario, chariot = _chariot_with_rabbits()
    rabbit = _tokens(scenario, "Rabbit")[0]
    scenario.will_choose_targets(rabbit, username="alice")

    scenario.attack_with(chariot)
    _resolve_everything(scenario)

    rabbits = _tokens(scenario, "Rabbit")
    assert len(rabbits) == 4
    for token in rabbits:
        assert (_chars(scenario, token).power, _chars(scenario, token).toughness) == (1, 1)


def test_esikas_chariot_cannot_copy_a_nontoken_creature():
    """ "target token you control": the nontoken Bears are no legal target."""
    scenario, chariot = _chariot_with_rabbits()
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")[0]
    scenario.will_choose_targets(bears, username="alice")

    with pytest.raises(ValueError, match="not a legal target"):
        scenario.attack_with(chariot)
        _resolve_everything(scenario)
    assert len(_tokens(scenario, "Rabbit")) == 3


def test_esikas_chariot_token_target_gone_makes_no_copy():
    """CR 608.2b: the Rabbit is destroyed in response; nothing is copied."""
    scenario, chariot = _chariot_with_rabbits()
    rabbit = _tokens(scenario, "Rabbit")[0]
    scenario.will_choose_targets(rabbit, username="alice")
    scenario.attack_with(chariot)
    scenario.game.put_triggers_on_stack()

    scenario.game.destroy(rabbit)
    _resolve_everything(scenario)

    assert len(_tokens(scenario, "Rabbit")) == 2


def test_an_uncrewed_esikas_chariot_cannot_attack():
    scenario = _board([CHARIOT])
    chariot = scenario.find(CHARIOT, Zone.BATTLEFIELD, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert not scenario.can_attack(chariot)


# -- Thundering Broodwagon ----------------------------------------------------


def test_broodwagon_entering_destroys_an_opponents_permanent_of_mv_four():
    """Hill Giant is mana value 4 - "4 or less" includes it."""
    scenario = _board(bob=["Hill Giant"], hand=[BROODWAGON])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_choose_targets(giant, username="alice")

    scenario.put_onto_battlefield(BROODWAGON, "alice")
    _resolve_everything(scenario)

    assert giant.zone is Zone.GRAVEYARD


def test_broodwagon_destroys_a_noncreature_permanent_too():
    scenario = _board(bob=["Mind Stone"], hand=[BROODWAGON])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_targets(stone, username="alice")

    scenario.put_onto_battlefield(BROODWAGON, "alice")
    _resolve_everything(scenario)

    assert stone.zone is Zone.GRAVEYARD


@pytest.mark.parametrize(
    ("owner", "name"),
    [("bob", "Wurmcoil Engine"), ("bob", "Mountain"), ("alice", "Grizzly Bears")],
    ids=["mana-value-six", "a-land", "your-own-permanent"],
)
def test_broodwagon_cannot_target_outside_its_description(owner, name):
    """With a legal Hill Giant also on Bob's side, naming the other
    permanent is refused at targeting."""
    alice = ["Grizzly Bears"] if owner == "alice" else []
    bob = ["Hill Giant", *([name] if owner == "bob" else [])]
    scenario = _board(alice, bob, hand=[BROODWAGON])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    illegal = scenario.find(name, Zone.BATTLEFIELD, owner)
    scenario.will_choose_targets(illegal, username="alice")

    scenario.put_onto_battlefield(BROODWAGON, "alice")
    with pytest.raises(ValueError, match="not a legal target"):
        _resolve_everything(scenario)
    assert illegal.zone is Zone.BATTLEFIELD


def test_broodwagon_with_no_legal_target_does_nothing():
    """CR 603.3d: only a mana-value-6 Wurmcoil and a land on Bob's side - the
    trigger has no legal target and is removed from the stack."""
    scenario = _board(bob=["Wurmcoil Engine", "Mountain"], hand=[BROODWAGON])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield(BROODWAGON, "alice")
    _resolve_everything(scenario)

    assert scenario.find("Wurmcoil Engine", Zone.BATTLEFIELD, "bob").zone is Zone.BATTLEFIELD
    assert scenario.find("Mountain", Zone.BATTLEFIELD, "bob").zone is Zone.BATTLEFIELD


def test_broodwagon_crew_three_makes_a_six_five_with_reach_and_menace():
    scenario = _board([BROODWAGON, "Grizzly Bears", "Llanowar Elves"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wagon = scenario.find(BROODWAGON, Zone.BATTLEFIELD, "alice")

    _crew(
        scenario,
        wagon,
        scenario.creature("Grizzly Bears", "alice"),
        scenario.creature("Llanowar Elves", "alice"),
    )

    chars = _chars(scenario, wagon)
    assert Type.CREATURE in chars.types
    assert (chars.power, chars.toughness) == (6, 5)
    assert has_keyword(wagon, "Reach", scenario.game)
    assert has_keyword(wagon, "Menace", scenario.game)


def test_broodwagon_crew_needs_total_power_three():
    scenario = _board([BROODWAGON, "Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wagon = scenario.find(BROODWAGON, Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError):
        _crew(scenario, wagon, scenario.creature("Grizzly Bears", "alice"))


def _crewed_broodwagon_attacking(bob):
    scenario = _board([BROODWAGON, "Hill Giant"], bob)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wagon = scenario.find(BROODWAGON, Zone.BATTLEFIELD, "alice")
    _crew(scenario, wagon, scenario.creature("Hill Giant", "alice"))
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(wagon)
    return scenario, wagon


def test_broodwagon_menace_refuses_a_lone_blocker():
    """CR 702.111b."""
    scenario, wagon = _crewed_broodwagon_attacking(["Grizzly Bears", "Savannah Lions"])
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError):
        scenario.block(wagon, bears)


def test_broodwagon_menace_allows_two_blockers():
    scenario, wagon = _crewed_broodwagon_attacking(["Grizzly Bears", "Savannah Lions"])
    bears = scenario.creature("Grizzly Bears", "bob")
    lions = scenario.creature("Savannah Lions", "bob")

    scenario.block(wagon, bears, lions)

    assert {b.id for b in scenario.blockers()} == {bears.id, lions.id}


def test_broodwagon_cycling_draws_a_card():
    """CR 702.29a: {2}, discard it: draw."""
    scenario = _board(["Mountain", "Mountain"], hand=[BROODWAGON])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wagon = scenario.find(BROODWAGON, Zone.HAND, "alice")

    scenario.cycle(wagon, *scenario.untapped_sources("Mountain", "Mountain"))
    _resolve_everything(scenario)

    alice = scenario.player("alice")
    assert wagon.zone is Zone.GRAVEYARD
    assert [c.name for c in alice.hand] == ["Island"]


# -- Warleader's Call ---------------------------------------------------------


def test_warleaders_call_pumps_only_your_creatures():
    scenario = _board([CALL, "Grizzly Bears"], ["Watchwolf"])
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "bob")

    assert (_chars(scenario, bears).power, _chars(scenario, bears).toughness) == (3, 3)
    assert (_chars(scenario, wolf).power, _chars(scenario, wolf).toughness) == (3, 3)


def test_warleaders_call_pings_each_opponent_when_a_creature_enters():
    scenario = _board([CALL], hand=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    _resolve_everything(scenario)

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 20


def test_warleaders_call_pings_once_per_creature_entering_together():
    """CR 603.6a: three Rabbits entering at once are three triggers."""
    scenario = _board([CALL, "Plains", "Plains", "Plains"], hand=["Hop to It"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Hop to It", *scenario.untapped_sources("Plains", "Plains", "Plains"))
    _resolve_everything(scenario)

    assert scenario.player("bob").life == 17
    for rabbit in _tokens(scenario, "Rabbit"):
        assert (_chars(scenario, rabbit).power, _chars(scenario, rabbit).toughness) == (2, 2)


def test_warleaders_call_ignores_an_opponents_creature_entering():
    scenario = _board([CALL], bob_hand=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Grizzly Bears", "bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []
    assert scenario.player("bob").life == 20


def test_warleaders_call_ignores_a_noncreature_entering():
    scenario = _board([CALL], hand=["Mind Stone"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Mind Stone", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []


# -- Hop to It ----------------------------------------------------------------


def test_hop_to_it_makes_three_white_rabbits():
    scenario = _board(["Plains", "Plains", "Plains"], hand=["Hop to It"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spell = scenario.cast_and_resolve(
        "Hop to It", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )

    rabbits = _tokens(scenario, "Rabbit")
    assert len(rabbits) == 3
    for rabbit in rabbits:
        chars = _chars(scenario, rabbit)
        assert (chars.power, chars.toughness) == (1, 1)
        assert "Rabbit" in chars.subtypes
        assert [c.value for c in chars.colors] == ["W"]
    assert spell.zone is Zone.GRAVEYARD


def test_broodwagon_reach_lets_it_block_a_flyer():
    """CR 702.17b/702.9b: crewed on Bob's turn, it blocks his Ornithopter; an
    uncrewed one is no creature and blocks nothing."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Ornithopter"], library=["Island"] * 5)
        .player("alice", battlefield=[BROODWAGON, "Hill Giant"], library=["Island"] * 5)
        .build()
    )
    thopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "bob")
    wagon = scenario.find(BROODWAGON, Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(thopter)
    assert not scenario.game.can_block(giant, thopter), "no reach, no flying"

    _crew(scenario, wagon, giant)

    assert scenario.game.can_block(wagon, thopter)
