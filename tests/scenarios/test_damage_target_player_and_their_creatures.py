"""One damage instruction to a targeted player and to every creature that
player controls.

- **Urabrask // The Great Work**, chapter I: "This Saga deals 3 damage to
  target opponent and each creature they control."
- **Flame Wave** (the second printing - Modern legal on Scryfall, not a listed
  card, in no deck list): "Flame Wave deals 4 damage to target player or
  planeswalker and each creature that player or that planeswalker's controller
  controls." A spell rather than a chapter ability, "player" rather than
  "opponent", a planeswalker alternative, and "that player ... controls"
  rather than "they control".

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 120.2b** - "Damage may be dealt as an effect of a spell or ability. The
  spell or ability will specify which object deals that damage."
- **CR 120.3a / 120.3c / 120.3e** - damage to a player is life loss, to a
  planeswalker removes loyalty counters, to a creature is marked on it.
- **CR 115.2** - a player can be a target only when the spell or ability says
  so; "target opponent" never reaches its own controller.
- **CR 608.2b** - the target is checked again as the effect resolves.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _great_work(target_username: str = "bob"):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Urabrask"],
            battlefield=["Grizzly Bears"],
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Colossal Dreadmaw"],
            library=["Mountain"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    urabrask = scenario.find("Urabrask", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(urabrask, "alice", transformed=True)
    scenario.choose_trigger_targets("The Great Work", [scenario.player(target_username)])
    return scenario, urabrask


def test_chapter_one_hits_the_opponent_and_each_creature_they_control():
    scenario, saga = _great_work()
    _resolve_everything(scenario)

    assert saga.name == "The Great Work"
    assert saga.counters[Counter.LORE] == 1
    assert scenario.player("bob").life == 17
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert scenario.creature("Colossal Dreadmaw", "bob").damage == 3


def test_chapter_one_leaves_its_controllers_side_alone():
    scenario, _saga = _great_work()
    _resolve_everything(scenario)

    assert scenario.player("alice").life == 20
    assert scenario.creature("Grizzly Bears", "alice").damage == 0


def test_chapter_one_cannot_target_its_own_controller():
    """CR 115.2: "target opponent" is never the Saga's controller."""
    with pytest.raises(ValueError, match="opponent"):
        _great_work(target_username="alice")


def _flame_wave(*, bob_battlefield=("Grizzly Bears", "Colossal Dreadmaw")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flame Wave"],
            battlefield=["Grizzly Bears"] + ["Mountain"] * 7,
        )
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_flame_wave_hits_the_targeted_player_and_their_creatures():
    scenario = _flame_wave()
    scenario.cast_and_resolve("Flame Wave", auto=True, targets=[scenario.player("bob")])

    assert scenario.player("bob").life == 16
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert scenario.creature("Colossal Dreadmaw", "bob").damage == 4
    assert scenario.creature("Grizzly Bears", "alice").damage == 0
    assert scenario.player("alice").life == 20


def test_flame_wave_aimed_at_its_caster_burns_the_casters_own_side():
    """ "Target player" includes the caster, and "each creature that player
    controls" follows the target, not the caster's opponents."""
    scenario = _flame_wave()
    scenario.cast_and_resolve("Flame Wave", auto=True, targets=[scenario.player("alice")])

    assert scenario.player("alice").life == 16
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice") is not None
    assert scenario.player("bob").life == 20
    assert scenario.creature("Grizzly Bears", "bob").damage == 0


def test_flame_wave_at_a_planeswalker_hits_it_and_its_controllers_creatures():
    """The planeswalker takes the damage (CR 120.3c), not its controller, and
    the creatures are "that planeswalker's controller['s]"."""
    scenario = _flame_wave(bob_battlefield=("Grizzly Bears", "Chandra, Torch of Defiance"))
    chandra = scenario.find("Chandra, Torch of Defiance", Zone.BATTLEFIELD, "bob")
    chandra.add_counters(Counter.LOYALTY, 6 - chandra.counters[Counter.LOYALTY])
    scenario.cast_and_resolve("Flame Wave", auto=True, targets=[chandra])

    assert chandra.counters[Counter.LOYALTY] == 2
    assert scenario.player("bob").life == 20
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert scenario.creature("Grizzly Bears", "alice").damage == 0
