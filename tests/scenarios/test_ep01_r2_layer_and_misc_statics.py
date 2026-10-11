"""Layer-affecting and miscellaneous statics left over from the EP-01 round 2
grab-bag (T8).

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 613.1b** - layer 2: control-changing effects; **CR 611.3a** - a static
  ability's effect applies while its source is on the battlefield.
- **CR 205.4a** - supertypes (legendary); **CR 111.1** - tokens.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Supertype
from magic_cards_model.models.token import TokenState
from tests.scenarios.harness import Scenario


def _board(alice=(), *, bob=(), hand=(), bob_hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", battlefield=list(alice), hand=list(hand), library=["Plains"] * 8
        )
        .player("bob", battlefield=list(bob), hand=list(bob_hand), library=["Plains"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# ---- "You control enchanted artifact creature." (Domineer) -----------------------


def test_domineer_gives_me_control_of_the_enchanted_artifact_creature():
    scenario = _board(["Domineer"], bob=["Wurmcoil Engine"])
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.find("Domineer", Zone.BATTLEFIELD, "alice").attach_to(wurm)
    assert wurm.controller == "alice"
    assert wurm.owner == "bob"


def test_control_returns_when_domineer_leaves_the_battlefield():
    scenario = _board(["Domineer", "Forest", "Forest"], bob=["Wurmcoil Engine"], hand=["Nature's Claim"])
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    domineer = scenario.find("Domineer", Zone.BATTLEFIELD, "alice")
    domineer.attach_to(wurm)
    assert wurm.controller == "alice"
    scenario.cast_and_resolve(
        "Nature's Claim", *scenario.untapped_sources("Forest"), targets=[domineer]
    )
    assert domineer.zone is Zone.GRAVEYARD
    assert wurm.controller == "bob"


def test_domineer_cannot_be_cast_on_a_creature_that_is_not_an_artifact():
    scenario = _board(hand=["Domineer"], bob=["Grizzly Bears"])
    with pytest.raises(ValueError):
        scenario.cast_onto_stack(
            "Domineer",
            username="alice",
            targets=[scenario.creature("Grizzly Bears", "bob")],
        )


# ---- "~ isn't legendary if it's a token." (Aeve, Progenitor Ooze) ---------------


def _aeve_with_a_storm_copy():
    scenario = _board(
        ["Forest"] * 6 + ["Grizzly Bears"], hand=["Giant Growth", "Aeve, Progenitor Ooze"]
    )
    scenario.cast_and_resolve(
        "Giant Growth",
        *scenario.untapped_sources("Forest"),
        targets=[scenario.creature("Grizzly Bears", "alice")],
    )
    scenario.cast_onto_stack("Aeve, Progenitor Ooze", *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest"))
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
    aeves = [
        permanent
        for permanent in scenario.game.permanents_controlled_by("alice")
        if permanent.name == "Aeve, Progenitor Ooze"
    ]
    return scenario, aeves


def test_the_token_copy_of_aeve_is_not_legendary_and_the_cast_aeve_is():
    scenario, aeves = _aeve_with_a_storm_copy()
    assert len(aeves) == 2  # CR 704.5j would have put one away were both legendary
    (token,) = [aeve for aeve in aeves if isinstance(aeve, TokenState)]
    (card,) = [aeve for aeve in aeves if not isinstance(aeve, TokenState)]
    assert Supertype.LEGENDARY not in scenario.game.characteristics_of(token).supertypes
    assert Supertype.LEGENDARY in scenario.game.characteristics_of(card).supertypes


# ---- "Damage isn't removed from this creature during cleanup steps." --------------


def _cleanup_board(alice, *, bob):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice), library=["Plains"] * 8)
        .player("bob", battlefield=list(bob), library=["Plains"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _run_the_cleanup_step(scenario):
    scenario.game.cleanup_step()  # CR 514.2


def test_ancient_adamantoise_keeps_its_damage_through_the_cleanup_step():
    scenario = _cleanup_board(["Ancient Adamantoise", "Grizzly Bears"], bob=["Goblin Guide"])
    adamantoise = scenario.creature("Ancient Adamantoise", "alice")
    guide = scenario.creature("Goblin Guide", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.deal_damage(adamantoise, 2, source=guide)
    scenario.game.deal_damage(guide, 1, source=bears)
    assert guide.damage == 1
    _run_the_cleanup_step(scenario)
    assert adamantoise.damage == 2  # CR 514.2's removal skips it
    assert guide.damage == 0  # every other permanent is wiped as usual
    assert adamantoise.zone is Zone.BATTLEFIELD


def test_the_damage_stays_marked_across_turns_and_is_lethal_when_it_adds_up():
    scenario = _cleanup_board(["Ancient Adamantoise"], bob=["Goblin Guide"])
    adamantoise = scenario.creature("Ancient Adamantoise", "alice")
    guide = scenario.creature("Goblin Guide", "bob")
    toughness = scenario.game.toughness_of(adamantoise)
    scenario.game.deal_damage(adamantoise, toughness - 1, source=guide)
    _run_the_cleanup_step(scenario)
    _run_the_cleanup_step(scenario)
    assert adamantoise.damage == toughness - 1
    scenario.game.deal_damage(adamantoise, 1, source=guide)
    scenario.game.check_state_based_actions()
    assert adamantoise.zone is Zone.GRAVEYARD


# ---- "Non-Human Werewolves you control can't transform." (Immerwolf) --------------
# Proof printing: Villagers of Estwald // Howlpack of Estwald (Human Werewolf
# front, non-Human Werewolf back).


def _villagers(*, mine=("Immerwolf",), theirs=()):
    scenario = _board(["Villagers of Estwald", *mine], bob=list(theirs))
    return scenario, scenario.creature("Villagers of Estwald", "alice")


def test_a_human_werewolf_front_face_can_still_transform_under_immerwolf():
    scenario, villagers = _villagers()
    villagers.transform()
    assert villagers.transformed
    assert scenario.game.characteristics_of(villagers).name == "Howlpack of Estwald"


def test_a_non_human_werewolf_cannot_transform_back_while_immerwolf_is_in_play():
    scenario, villagers = _villagers()
    villagers.transform()
    villagers.transform()
    assert villagers.transformed
    assert villagers.times_transformed == 1


def test_it_transforms_back_without_immerwolf():
    scenario, villagers = _villagers(mine=())
    villagers.transform()
    villagers.transform()
    assert not villagers.transformed


def test_an_opponents_immerwolf_does_not_stop_my_werewolf_transforming():
    scenario, villagers = _villagers(mine=(), theirs=("Immerwolf",))
    villagers.transform()
    villagers.transform()
    assert not villagers.transformed


def test_immerwolf_does_not_stop_a_non_werewolf_transforming():
    scenario = _board(["Immerwolf", "Delver of Secrets"])
    delver = scenario.creature("Delver of Secrets", "alice")
    delver.transform()
    assert delver.transformed
