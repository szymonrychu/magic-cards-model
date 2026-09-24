"""Copying an activated or triggered ability on the stack (CR 707.10: "To
copy a spell, activated ability, or triggered ability means to put a copy of
it onto the stack ... a copy of an activated ability isn't activated";
CR 707.10b: the copy has the same source; CR 707.10c: new targets may be
chosen).

- Echo, Perceptive Prodigy: "{1}, {T}: Copy target activated or triggered
  ability you control from a creature source. You may choose new targets for
  the copy."
- Scientist Supreme of A.I.M.: "Pay 2 life: Copy target activated or
  triggered ability you control from an artifact source. You may choose new
  targets for the copy. Activate only during your turn and only once each
  turn."

"From a creature source": the ability's source (CR 113.7) as it is now, or
as it last existed once it has left (CR 113.7a) - Mogg Fanatic's ability is
still from a creature source after the Fanatic was sacrificed to activate it.

Off-set proof (legal, in no deck list):

- Peter Parker's Camera: "{2}, {T}, Remove a film counter from this artifact:
  Copy target activated or triggered ability you control. You may choose new
  targets for the copy." - no source restriction, a counter-removal cost.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import Zone

from .harness import Scenario

ECHO = "Echo, Perceptive Prodigy"
SUPREME = "Scientist Supreme of A.I.M."
CAMERA = "Peter Parker's Camera"


def _abilities_on_stack(scenario):
    return [item for item in scenario.game.stack if isinstance(item, AbilityOnStack)]


def _resolve_everything(scenario):
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()


def _board(alice_battlefield, *, alice_hand=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=list(alice_battlefield),
            library=["Island"] * 8,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for permanent in scenario.game.battlefield:
        permanent.summoning_sick = False
    return scenario


def _wall_enters(scenario):
    """Wall of Omens' enters trigger ("draw a card"), waiting on the stack."""
    wall = scenario.put_onto_battlefield("Wall of Omens", "alice")
    scenario.game.put_triggers_on_stack()
    (trigger,) = _abilities_on_stack(scenario)
    return wall, trigger


# -- Echo, Perceptive Prodigy ----------------------------------------------------------


def test_echo_copies_a_creatures_triggered_ability():
    scenario = _board([ECHO, "Island", "Island"], alice_hand=["Wall of Omens"])
    echo = scenario.creature(ECHO, "alice")
    _, trigger = _wall_enters(scenario)
    hand = len(scenario.player("alice").hand)

    scenario.activate(echo, *scenario.untapped_sources("Island"), targets=[trigger])
    assert len(_abilities_on_stack(scenario)) == 2  # Echo's own ability
    _resolve_everything(scenario)

    assert len(scenario.player("alice").hand) == hand + 2


def test_echo_copies_an_activated_ability_whose_creature_is_gone_and_retargets_it():
    """Mogg Fanatic was sacrificed to activate its ability; the ability is
    still from a creature source (CR 113.7a). The copy is pointed at Grizzly
    Bears instead of bob."""
    scenario = _board([ECHO, "Mogg Fanatic", "Island", "Island"], bob_battlefield=["Grizzly Bears"])
    echo = scenario.creature(ECHO, "alice")
    fanatic = scenario.creature("Mogg Fanatic", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    fanatic_ability = scenario.activate(fanatic, sacrificing=[fanatic], targets=["bob"])
    assert fanatic.zone is Zone.GRAVEYARD

    scenario.will_take_the_may(True)
    scenario.will_choose_targets(bears)
    scenario.activate(echo, *scenario.untapped_sources("Island"), targets=[fanatic_ability])
    _resolve_everything(scenario)

    assert scenario.player("bob").life == 19
    assert bears.damage == 1


def test_echo_keeps_the_original_targets_when_new_ones_are_declined():
    scenario = _board([ECHO, "Mogg Fanatic", "Island", "Island"])
    echo = scenario.creature(ECHO, "alice")
    fanatic = scenario.creature("Mogg Fanatic", "alice")
    fanatic_ability = scenario.activate(fanatic, sacrificing=[fanatic], targets=["bob"])

    scenario.will_take_the_may(False)
    scenario.activate(echo, *scenario.untapped_sources("Island"), targets=[fanatic_ability])
    _resolve_everything(scenario)

    assert scenario.player("bob").life == 18


def test_echo_cannot_target_an_artifacts_ability():
    scenario = _board([ECHO, "Mind Stone", "Island", "Island"])
    echo = scenario.creature(ECHO, "alice")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    draw = scenario.activate(
        stone, *scenario.untapped_sources("Island"), index=1, sacrificing=[stone]
    )

    with pytest.raises(ValueError, match="creature source"):
        scenario.activate(echo, *scenario.untapped_sources("Island"), targets=[draw])


def test_echo_cannot_target_an_opponents_ability():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Mogg Fanatic"], library=["Forest"] * 5)
        .player("alice", battlefield=[ECHO, "Island"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for permanent in scenario.game.battlefield:
        permanent.summoning_sick = False
    fanatic = scenario.creature("Mogg Fanatic", "bob")
    echo = scenario.creature(ECHO, "alice")
    ability = scenario.activate(fanatic, sacrificing=[fanatic], targets=["alice"], username="bob")
    scenario.pass_priority("bob")

    with pytest.raises(ValueError):
        scenario.activate(
            echo, *scenario.untapped_sources("Island", username="alice"), targets=[ability]
        )


# -- Scientist Supreme of A.I.M. -----------------------------------------------------------


def _stone_draw(scenario):
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    return scenario.activate(
        stone, *scenario.untapped_sources("Island"), index=1, sacrificing=[stone]
    )


def test_scientist_supreme_copies_an_artifacts_ability_for_two_life():
    scenario = _board([SUPREME, "Mind Stone", "Island"])
    supreme = scenario.creature(SUPREME, "alice")
    draw = _stone_draw(scenario)
    hand = len(scenario.player("alice").hand)

    scenario.activate(supreme, targets=[draw])
    _resolve_everything(scenario)

    assert scenario.player("alice").life == 18
    assert len(scenario.player("alice").hand) == hand + 2


def test_scientist_supreme_only_once_each_turn():
    scenario = _board([SUPREME, "Mind Stone", "Mind Stone", "Island", "Island"])
    supreme = scenario.creature(SUPREME, "alice")
    first, second = [card for card in scenario.game.battlefield if card.name == "Mind Stone"]
    draw = scenario.activate(
        first, *scenario.untapped_sources("Island"), index=1, sacrificing=[first]
    )
    scenario.activate(supreme, targets=[draw])
    _resolve_everything(scenario)

    assert scenario.why_cannot_activate(supreme) is not None


def test_scientist_supreme_only_during_your_turn():
    scenario = (
        Scenario()
        .player("bob", library=["Forest"] * 5)
        .player("alice", battlefield=[SUPREME, "Mind Stone", "Island"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    supreme = scenario.creature(SUPREME, "alice")

    assert scenario.why_cannot_activate(supreme, username="alice") is not None


def test_scientist_supreme_cannot_target_a_creatures_ability():
    scenario = _board([SUPREME, "Mogg Fanatic"])
    supreme = scenario.creature(SUPREME, "alice")
    fanatic = scenario.creature("Mogg Fanatic", "alice")
    ability = scenario.activate(fanatic, sacrificing=[fanatic], targets=["bob"])

    with pytest.raises(ValueError, match="artifact source"):
        scenario.activate(supreme, targets=[ability])


# -- Peter Parker's Camera (off-set proof) ----------------------------------------------------


def test_peter_parkers_camera_copies_any_ability_you_control():
    scenario = _board(["Island", "Island"], alice_hand=["Wall of Omens", CAMERA])
    camera = scenario.put_onto_battlefield(CAMERA, "alice")
    assert camera.counters["film"] == 3
    _, trigger = _wall_enters(scenario)
    hand = len(scenario.player("alice").hand)

    scenario.activate(camera, *scenario.untapped_sources("Island", "Island"), targets=[trigger])
    _resolve_everything(scenario)

    assert len(scenario.player("alice").hand) == hand + 2
    assert camera.counters["film"] == 2
