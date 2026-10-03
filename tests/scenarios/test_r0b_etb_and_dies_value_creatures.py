"""R0b proofs: small creatures whose value is an enters or dies trigger.

Dream Beavers, Greedy Freebooter, Callous Inspector, Curious Farm Animals
and Vinereap Mentor are already handled; each ability is proven through the
engine. Rules, read with `mise run rules:find`:

- **CR 701.22a** - scry N: look at the top N, bottom any number, rest on top.
- **CR 603.10a** - a dies trigger looks back in time: it uses the creature as
  it last existed on the battlefield (the Inspector is the damage source).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario


def _resolve(scenario) -> None:
    """Stack the pending triggers (CR 603.3b), then resolve until quiet."""
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _dies(scenario, name: str, username: str = "alice"):
    creature = scenario.creature(name, username)
    scenario.game.destroy(creature)
    scenario.game.check_state_based_actions()
    assert creature.zone is Zone.GRAVEYARD
    return creature


def _tokens(scenario, name: str, username: str = "alice"):
    return [
        s
        for s in scenario.game.battlefield
        if s.token and s.name == name and s.controller == username
    ]


# -- Dream Beavers -----------------------------------------------------------


def _beavers_cast(library):
    scenario = (
        Scenario()
        .player("alice", hand=["Dream Beavers"], battlefield=["Swamp"], library=library)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")
    return scenario, swamp


def test_dream_beavers_drains_one_and_scries_keeping_the_top():
    scenario, swamp = _beavers_cast(["Island", "Forest", "Plains"])
    top = scenario.top_of_library(1)
    scenario.scry_keeping_everything_on_top()

    scenario.cast_and_resolve("Dream Beavers", swamp, username="alice")
    _resolve(scenario)

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21
    assert scenario.top_of_library(1) == top


def test_dream_beavers_scry_can_bottom_the_top_card():
    scenario, swamp = _beavers_cast(["Island", "Forest", "Plains"])
    island, forest, plains = scenario.top_of_library(3)
    scenario.scry_bottoming(island)

    scenario.cast_and_resolve("Dream Beavers", swamp, username="alice")
    _resolve(scenario)

    assert scenario.top_of_library(3) == [forest, plains, island]
    assert scenario.player("bob").life == 19


def test_dream_beavers_has_flying_and_only_the_enter_trigger_drains():
    scenario, swamp = _beavers_cast(["Island"] * 3)
    scenario.scry_keeping_everything_on_top()
    scenario.cast_and_resolve("Dream Beavers", swamp, username="alice")
    _resolve(scenario)
    beavers = scenario.creature("Dream Beavers", "alice")
    assert has_keyword(beavers, Keyword.FLYING, scenario.game)

    _dies(scenario, "Dream Beavers")
    _resolve(scenario)
    assert scenario.player("bob").life == 19, "no dies trigger"


# -- Greedy Freebooter -------------------------------------------------------


def test_freebooter_dies_scries_and_makes_a_treasure():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Greedy Freebooter"], library=["Island", "Forest", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island, forest, plains = scenario.top_of_library(3)
    scenario.scry_bottoming(island)

    _dies(scenario, "Greedy Freebooter")
    _resolve(scenario)

    (treasure,) = _tokens(scenario, "Treasure Token")
    assert treasure.zone is Zone.BATTLEFIELD
    assert scenario.top_of_library(3) == [forest, plains, island]


def test_freebooter_treasure_taps_and_sacrifices_for_mana():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Greedy Freebooter"], library=["Island"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.scry_keeping_everything_on_top()
    _dies(scenario, "Greedy Freebooter")
    _resolve(scenario)
    (treasure,) = _tokens(scenario, "Treasure Token")

    scenario.activate(treasure, color=Color.RED)
    assert treasure.zone is not Zone.BATTLEFIELD, "the Treasure is sacrificed for its mana"
    assert scenario.player("alice").mana_pool.floating.get(Color.RED) == 1


def test_freebooter_entering_makes_no_treasure():
    scenario = (
        Scenario()
        .player("alice", hand=["Greedy Freebooter"], battlefield=["Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (swamp,) = scenario.untapped_sources("Swamp", username="alice")
    scenario.cast_and_resolve("Greedy Freebooter", swamp, username="alice")
    _resolve(scenario)
    assert _tokens(scenario, "Treasure Token") == []


# -- Callous Inspector -------------------------------------------------------


def test_inspector_dies_hurts_its_controller_for_one_and_makes_a_clue():
    scenario = Scenario().player("alice", battlefield=["Callous Inspector"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    inspector = _dies(scenario, "Callous Inspector")
    _resolve(scenario)

    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 20
    assert len(_tokens(scenario, "Clue Token")) == 1
    (damage,) = scenario.game.damage_dealt_this_turn
    assert damage.source_id == inspector.id, "CR 603.10a: the Inspector is the source"
    assert damage.recipient_player == "alice"
    assert damage.amount == 1


def test_inspector_has_menace():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Callous Inspector"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    inspector = scenario.creature("Callous Inspector", "alice")
    inspector.summoning_sick = False
    scenario.attack_with(inspector)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    try:
        scenario.block(inspector, scenario.creature("Grizzly Bears", "bob"))
    except ValueError as error:
        assert "menace" in str(error).lower() or "two" in str(error).lower()
    else:
        raise AssertionError("a lone blocker blocked a menace creature")


# -- Curious Farm Animals ----------------------------------------------------


def test_farm_animals_dies_gains_three():
    scenario = (
        Scenario().player("alice", battlefield=["Curious Farm Animals"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _dies(scenario, "Curious Farm Animals")
    _resolve(scenario)
    assert scenario.player("alice").life == 23
    assert scenario.player("bob").life == 20


def test_farm_animals_sacrificed_also_gains_three():
    """Sacrifice is dying (CR 700.4): the dies trigger sees the sacrifice."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Curious Farm Animals", "Plains", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    animals = scenario.creature("Curious Farm Animals", "alice")
    plains = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.activate(animals, *plains, sacrificing=[animals], targets=[])
    _resolve(scenario)
    assert animals.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 23


# -- Vinereap Mentor ---------------------------------------------------------


def test_mentor_enters_and_dies_each_make_a_food():
    scenario = (
        Scenario()
        .player("alice", hand=["Vinereap Mentor"], battlefield=["Forest", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Swamp", username="alice")
    scenario.cast_and_resolve("Vinereap Mentor", *sources, username="alice")
    _resolve(scenario)
    assert len(_tokens(scenario, "Food Token")) == 1

    _dies(scenario, "Vinereap Mentor")
    _resolve(scenario)
    assert len(_tokens(scenario, "Food Token")) == 2


def test_mentor_food_gains_three_for_two_tap_and_sacrifice():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vinereap Mentor", "Forest", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _dies(scenario, "Vinereap Mentor")
    _resolve(scenario)
    (food,) = _tokens(scenario, "Food Token")
    sources = scenario.untapped_sources("Forest", "Swamp", username="alice")

    scenario.activate(food, *sources)
    _resolve(scenario)

    assert scenario.player("alice").life == 23
    assert _tokens(scenario, "Food Token") == []


def test_mentor_makes_food_for_its_controller_only():
    scenario = Scenario().player("alice", battlefield=["Vinereap Mentor"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _dies(scenario, "Vinereap Mentor")
    _resolve(scenario)
    assert _tokens(scenario, "Food Token", "bob") == []
