"""R0b proofs: sacrifice-for-value artifacts and the sacrifice outlet creature.

Candy Trail (a Food Clue artifact), Giant's Boulder and Curious Farm Animals'
sacrifice ability are already handled; each ability is proven through the
engine. Rules, read with `mise run rules:find`:

- **CR 701.22a** - scry N on enter.
- **CR 602.2** / **CR 118.12** - the sacrifice and tap are costs, paid before
  the ability exists; an ability whose source is gone still resolves.
- **CR 115.1d** - "up to one target" may have zero targets.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario


def _resolve(scenario) -> None:
    """Stack the pending triggers (CR 603.3b), then resolve until quiet."""
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# -- Candy Trail -------------------------------------------------------------


def _cast_candy_trail(library):
    scenario = (
        Scenario()
        .player("alice", hand=["Candy Trail"], battlefield=["Island"] * 4, library=library)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_candy_trail_enters_and_scries_two_bottoming_one():
    scenario = _cast_candy_trail(["Island", "Forest", "Plains", "Swamp"])
    island, forest, plains, _swamp = scenario.top_of_library(4)
    scenario.scry_bottoming(island)
    (payer,) = scenario.untapped_sources("Island", username="alice")[:1]

    scenario.cast_and_resolve("Candy Trail", payer, username="alice")
    _resolve(scenario)

    assert scenario.top_of_library(3) == [forest, plains, _swamp]
    assert scenario.player("alice").library[-1] == island


def test_candy_trail_scry_two_can_keep_both_on_top():
    scenario = _cast_candy_trail(["Island", "Forest", "Plains"])
    top = scenario.top_of_library(3)
    scenario.scry_keeping_everything_on_top()
    (payer,) = scenario.untapped_sources("Island", username="alice")[:1]

    scenario.cast_and_resolve("Candy Trail", payer, username="alice")
    _resolve(scenario)

    assert scenario.top_of_library(3) == top


def test_candy_trail_is_both_food_and_clue():
    scenario = _cast_candy_trail(["Island"] * 3)
    scenario.scry_keeping_everything_on_top()
    (payer,) = scenario.untapped_sources("Island", username="alice")[:1]
    trail = scenario.cast_and_resolve("Candy Trail", payer, username="alice")
    assert {"Food", "Clue"} <= set(trail.card.type_line.replace("—", " ").split())


def test_candy_trail_sacrifice_gains_three_and_draws():
    scenario = _cast_candy_trail(["Island", "Forest", "Plains", "Swamp"])
    scenario.scry_keeping_everything_on_top()
    (payer,) = scenario.untapped_sources("Island", username="alice")[:1]
    trail = scenario.cast_and_resolve("Candy Trail", payer, username="alice")
    _resolve(scenario)
    trail.summoning_sick = False
    top = scenario.top_of_library(1)[0]
    hand = len(scenario.player("alice").hand)
    sources = scenario.untapped_sources("Island", "Island", username="alice")

    scenario.activate(trail, *sources, sacrificing=[trail])
    assert trail.zone is Zone.GRAVEYARD, "sacrificed as a cost, before resolving"
    _resolve(scenario)

    assert scenario.player("alice").life == 23
    assert len(scenario.player("alice").hand) == hand + 1
    assert top.zone is Zone.HAND
    assert scenario.player("bob").life == 20


def test_candy_trail_cannot_be_activated_without_the_two_mana():
    scenario = _cast_candy_trail(["Island"] * 3)
    scenario.scry_keeping_everything_on_top()
    (payer,) = scenario.untapped_sources("Island", username="alice")[:1]
    trail = scenario.cast_and_resolve("Candy Trail", payer, username="alice")
    _resolve(scenario)
    trail.summoning_sick = False
    (one,) = scenario.untapped_sources("Island", username="alice")[:1]

    try:
        scenario.activate(trail, one, sacrificing=[trail])
    except (ValueError, RuntimeError):
        pass
    else:
        raise AssertionError("activated with one mana")
    assert scenario.player("alice").life == 20


# -- Giant's Boulder ---------------------------------------------------------


def _boulder_board(**extra):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Giant's Boulder", *["Island"] * 8],
            library=["Island", "Forest", "Plains", "Swamp"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Forest"], **extra)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    boulder = scenario.find("Giant's Boulder", Zone.BATTLEFIELD, "alice")
    boulder.summoning_sick = False
    return scenario, boulder


def test_boulder_enters_and_scries_two():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant's Boulder"],
            battlefield=["Island"],
            library=["Island", "Forest", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island, forest, plains = scenario.top_of_library(3)
    scenario.scry_bottoming(island, forest, top_order=None)
    (payer,) = scenario.untapped_sources("Island", username="alice")

    scenario.cast_and_resolve("Giant's Boulder", payer, username="alice")
    _resolve(scenario)

    assert scenario.top_of_library(1) == [plains]


def test_boulder_taps_for_one_mana_of_any_colour_with_one_generic():
    scenario, boulder = _boulder_board()
    (island,) = scenario.untapped_sources("Island", username="alice")[:1]

    scenario.activate(boulder, island, index=0, color=Color.GREEN)

    assert boulder.tapped
    assert scenario.player("alice").mana_pool.floating.get(Color.GREEN) == 1


def test_boulder_seven_tap_sacrifice_destroys_target_permanent():
    scenario, boulder = _boulder_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*["Island"] * 7, username="alice")

    scenario.activate(boulder, *sources, index=1, sacrificing=[boulder], targets=[bears])
    assert boulder.zone is Zone.GRAVEYARD, "sacrificed as a cost"
    _resolve(scenario)

    assert bears.zone is Zone.GRAVEYARD


def test_boulder_destroys_a_land_too_any_permanent():
    scenario, boulder = _boulder_board()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    sources = scenario.untapped_sources(*["Island"] * 7, username="alice")

    scenario.activate(boulder, *sources, index=1, sacrificing=[boulder], targets=[forest])
    _resolve(scenario)

    assert forest.zone is Zone.GRAVEYARD


def test_boulder_destroy_needs_seven_mana():
    scenario, boulder = _boulder_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*["Island"] * 6, username="alice")

    try:
        scenario.activate(boulder, *sources, index=1, sacrificing=[boulder], targets=[bears])
    except (ValueError, RuntimeError):
        pass
    else:
        raise AssertionError("activated the destroy ability with six mana")
    assert bears.zone is Zone.BATTLEFIELD


# -- Curious Farm Animals' sacrifice ability ---------------------------------


def _animals_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Curious Farm Animals", "Plains", "Plains"])
        .player("bob", battlefield=["Mind Stone", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    animals = scenario.creature("Curious Farm Animals", "alice")
    animals.summoning_sick = False
    return scenario, animals


def test_farm_animals_sacrifice_destroys_an_artifact():
    scenario, animals = _animals_board()
    mind_stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    plains = scenario.untapped_sources("Plains", "Plains", username="alice")

    scenario.activate(animals, *plains, index=0, sacrificing=[animals], targets=[mind_stone])
    _resolve(scenario)

    assert animals.zone is Zone.GRAVEYARD
    assert mind_stone.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 23, "its dies trigger too"


def test_farm_animals_sacrifice_destroys_an_enchantment():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Curious Farm Animals", "Plains", "Plains"])
        .player("bob", battlefield=["Pacifism"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    animals = scenario.creature("Curious Farm Animals", "alice")
    animals.summoning_sick = False
    pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "bob")
    plains = scenario.untapped_sources("Plains", "Plains", username="alice")

    scenario.activate(animals, *plains, sacrificing=[animals], targets=[pacifism])
    _resolve(scenario)

    assert pacifism.zone is Zone.GRAVEYARD


def test_farm_animals_sacrifice_with_zero_targets_is_legal():
    """CR 115.1d: "up to one" - choosing no target still activates, and the
    creature is still sacrificed (and its dies trigger gains 3)."""
    scenario, animals = _animals_board()
    plains = scenario.untapped_sources("Plains", "Plains", username="alice")

    scenario.activate(animals, *plains, sacrificing=[animals], targets=[])
    _resolve(scenario)

    assert animals.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 23
    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD


def test_farm_animals_cannot_target_a_nonartifact_nonenchantment():
    scenario, animals = _animals_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    plains = scenario.untapped_sources("Plains", "Plains", username="alice")

    try:
        scenario.activate(animals, *plains, sacrificing=[animals], targets=[bears])
    except (ValueError, RuntimeError):
        pass
    else:
        raise AssertionError("targeted a plain creature")
    assert bears.zone is Zone.BATTLEFIELD
