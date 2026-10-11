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
