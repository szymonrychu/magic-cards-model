"""Restless Cottage, Restless Reef and Firdoch Core: lands and an artifact that
animate themselves until end of turn.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 613.1d / 613.4b** - the animation's types go to layer 4 and its P/T to
  layer 7b; CR 205.1b - "It's still a land" keeps every prior type.
- **CR 514.2** - "until end of turn" effects end in the cleanup step.
- **CR 302.6** - a creature cannot attack, or use a `{T}` ability, until its
  controller has controlled it continuously since their turn began.
- **CR 508.3a** - "Whenever [a creature] attacks" triggers only when that
  creature is declared as an attacker: an unanimated land never attacks, and
  another creature attacking does not trigger it.
- **CR 702.2b / 702.2c** - deathtouch.
- **CR 701.17a** - milling puts that many cards from the top of the library
  into the graveyard.
- **CR 702.73a** - changeling is "every creature type", even on a
  non-creature Kindred artifact.
- **CR 205.3d** - no subtype that does not correspond to one of the types.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import Scenario

# -- helpers ------------------------------------------------------------------


def _ready(scenario, name: str, username: str = "alice"):
    permanent = scenario.find(name, Zone.BATTLEFIELD, username)
    permanent.summoning_sick = False
    return permanent


def _cottage_board(*, bob_graveyard: list[str] | None = None, alice_graveyard=None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Restless Cottage", "Swamp", "Forest", "Swamp", "Forest"],
            graveyard=alice_graveyard or [],
            library=["Forest"] * 5,
        )
        .player("bob", graveyard=bob_graveyard or [], library=["Forest"] * 8)
    )


def _reef_board(*, bob_battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Restless Reef", "Island", "Swamp", "Island", "Swamp"],
            library=["Forest"] * 8,
        )
        .player("bob", battlefield=bob_battlefield or [], library=["Forest"] * 8)
    )


def _animate(scenario, name: str, *sources: str, index: int = 1):
    land = _ready(scenario, name)
    paying = scenario.untapped_sources(*sources)
    scenario.activate(land, *paying, index=index)
    scenario.pass_until_resolved()
    return land


def _to_declare_attackers(scenario) -> None:
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers


# -- Restless Cottage ---------------------------------------------------------


def test_cottage_enters_tapped():
    scenario = (
        Scenario()
        .player("alice", hand=["Restless Cottage"], library=["Forest"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    cottage = scenario.play_land("Restless Cottage")

    assert cottage.tapped


@pytest.mark.parametrize("colour", [Color.BLACK, Color.GREEN])
def test_cottage_taps_for_black_or_green(colour):
    scenario = _cottage_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cottage = _ready(scenario, "Restless Cottage")

    scenario.activate(cottage, index=0, color=colour)

    assert scenario.player("alice").mana_pool.floating == {colour: 1}


def test_cottage_is_just_a_land_until_animated():
    scenario = _cottage_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cottage = _ready(scenario, "Restless Cottage")

    computed = scenario.game.computed_board().of(cottage)
    assert not computed.is_creature
    assert computed.colors == ()
    _to_declare_attackers(scenario)
    assert not scenario.can_attack(cottage)


def test_cottage_becomes_a_four_four_black_and_green_horror_that_is_still_a_land():
    scenario = _cottage_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    cottage = _animate(scenario, "Restless Cottage", "Swamp", "Forest", "Swamp", "Forest")

    computed = scenario.game.computed_board().of(cottage)
    assert computed.is_creature
    assert computed.is_land, "CR 205.1b: 'It's still a land.'"
    assert (computed.power, computed.toughness) == (4, 4)
    assert set(computed.colors) == {Color.BLACK, Color.GREEN}
    assert "Horror" in computed.subtypes


def test_cottage_animation_ends_in_the_cleanup_step():
    scenario = _cottage_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cottage = _animate(scenario, "Restless Cottage", "Swamp", "Forest", "Swamp", "Forest")

    while scenario.game.turn.active_player == "alice":
        scenario.advance()

    computed = scenario.game.computed_board().of(cottage)
    assert not computed.is_creature
    assert computed.is_land
    assert computed.colors == ()
    assert "Horror" not in computed.subtypes


def test_cottage_animation_cannot_be_paid_without_both_colours():
    scenario = _cottage_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cottage = _ready(scenario, "Restless Cottage")
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Forest")

    with pytest.raises(ValueError):
        scenario.activate(cottage, *swamps, index=1)  # three mana and no {G}... {2}{B}{G} needs 4


def test_cottage_attack_makes_a_food_and_exiles_the_chosen_graveyard_card():
    scenario = _cottage_board(bob_graveyard=["Memnite"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cottage = _animate(scenario, "Restless Cottage", "Swamp", "Forest", "Swamp", "Forest")
    _to_declare_attackers(scenario)
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "bob")

    scenario.choose_trigger_targets("Restless Cottage", [memnite])
    scenario.attack_with(cottage)
    assert scenario.stack_names() == ["Restless Cottage's triggered ability"]
    scenario.pass_until_resolved()

    assert memnite.zone is Zone.EXILE
    foods = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.card.name == "Food Token"
        or "Food" in scenario.game.computed_board().of(state).subtypes
    ]
    assert len(foods) == 1
    assert is_token(foods[0])


def test_cottage_may_target_its_own_controllers_graveyard():
    scenario = _cottage_board(alice_graveyard=["Memnite"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cottage = _animate(scenario, "Restless Cottage", "Swamp", "Forest", "Swamp", "Forest")
    _to_declare_attackers(scenario)
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "alice")

    scenario.choose_trigger_targets("Restless Cottage", [memnite])
    scenario.attack_with(cottage)
    scenario.pass_until_resolved()

    assert memnite.zone is Zone.EXILE


def test_cottage_with_no_graveyard_card_still_makes_the_food():
    """'Up to one target': zero targets is legal and the Food is still created."""
    scenario = _cottage_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cottage = _animate(scenario, "Restless Cottage", "Swamp", "Forest", "Swamp", "Forest")
    _to_declare_attackers(scenario)

    scenario.choose_trigger_targets("Restless Cottage", [])
    scenario.attack_with(cottage)
    scenario.pass_until_resolved()

    names = [state.card.name for state in scenario.game.permanents_controlled_by("alice")]
    assert names.count("Food Token") == 1


def test_cottage_trigger_does_not_fire_when_another_creature_attacks():
    """CR 508.3a: only when *this* land is declared as an attacker."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Restless Cottage", "Grizzly Bears"],
            library=["Forest"] * 3,
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = _ready(scenario, "Grizzly Bears")
    _to_declare_attackers(scenario)

    scenario.attack_with(bears)

    assert scenario.stack_names() == []
    assert not any(
        state.card.name == "Food Token" for state in scenario.game.permanents_controlled_by("alice")
    )


def test_a_cottage_played_this_turn_can_be_animated_but_cannot_attack():
    """CR 302.6: the animation grants no haste."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Restless Cottage"],
            battlefield=["Swamp", "Forest", "Swamp", "Forest"],
            library=["Forest"] * 3,
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cottage = scenario.play_land("Restless Cottage")
    paying = scenario.untapped_sources("Swamp", "Forest", "Swamp", "Forest")
    scenario.activate(cottage, *paying, index=1)
    scenario.pass_until_resolved()
    assert scenario.game.computed_board().of(cottage).is_creature

    _to_declare_attackers(scenario)
    assert not scenario.can_attack(cottage)


# -- Restless Reef ------------------------------------------------------------


def _animate_reef(scenario):
    return _animate(scenario, "Restless Reef", "Island", "Swamp", "Island", "Swamp")


def test_reef_enters_tapped():
    scenario = (
        Scenario()
        .player("alice", hand=["Restless Reef"], library=["Forest"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.play_land("Restless Reef").tapped


@pytest.mark.parametrize("colour", [Color.BLUE, Color.BLACK])
def test_reef_taps_for_blue_or_black(colour):
    scenario = _reef_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reef = _ready(scenario, "Restless Reef")

    scenario.activate(reef, index=0, color=colour)

    assert scenario.player("alice").mana_pool.floating == {colour: 1}


def test_reef_becomes_a_four_four_blue_and_black_shark_with_deathtouch():
    scenario = _reef_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    reef = _animate_reef(scenario)

    computed = scenario.game.computed_board().of(reef)
    assert computed.is_creature and computed.is_land
    assert (computed.power, computed.toughness) == (4, 4)
    assert set(computed.colors) == {Color.BLUE, Color.BLACK}
    assert "Shark" in computed.subtypes
    assert computed.has_ability("Deathtouch")


def test_reef_loses_creature_status_and_deathtouch_at_cleanup():
    scenario = _reef_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reef = _animate_reef(scenario)

    while scenario.game.turn.active_player == "alice":
        scenario.advance()

    computed = scenario.game.computed_board().of(reef)
    assert not computed.is_creature
    assert not computed.has_ability("Deathtouch")


def test_reef_attack_mills_the_target_player_four():
    scenario = _reef_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reef = _animate_reef(scenario)
    _to_declare_attackers(scenario)

    scenario.choose_trigger_targets("Restless Reef", ["bob"])
    scenario.attack_with(reef)
    scenario.pass_until_resolved()

    assert len(scenario.player("bob").library) == 4
    assert len(scenario.player("bob").graveyard) == 4
    assert len(scenario.player("alice").library) == 8


def test_reef_may_mill_its_own_controller():
    scenario = _reef_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reef = _animate_reef(scenario)
    _to_declare_attackers(scenario)

    scenario.choose_trigger_targets("Restless Reef", ["alice"])
    scenario.attack_with(reef)
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").graveyard) == 4
    assert len(scenario.player("bob").graveyard) == 0


def test_reef_mills_only_what_a_short_library_has():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Restless Reef", "Island", "Swamp", "Island", "Swamp"],
            library=["Forest"] * 3,
        )
        .player("bob", library=["Forest"] * 2)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reef = _animate_reef(scenario)
    _to_declare_attackers(scenario)

    scenario.choose_trigger_targets("Restless Reef", ["bob"])
    scenario.attack_with(reef)
    scenario.pass_until_resolved()

    assert len(scenario.player("bob").library) == 0
    assert len(scenario.player("bob").graveyard) == 2


def test_reef_does_not_trigger_unanimated():
    scenario = _reef_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reef = _ready(scenario, "Restless Reef")
    _to_declare_attackers(scenario)

    assert not scenario.can_attack(reef)
    assert scenario.stack_names() == []
    assert len(scenario.player("bob").library) == 8


def test_reefs_deathtouch_kills_a_bigger_blocker():
    scenario = _reef_board(bob_battlefield=["Colossal Dreadmaw"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reef = _animate_reef(scenario)
    _to_declare_attackers(scenario)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.choose_trigger_targets("Restless Reef", ["bob"])
    scenario.attack_with(reef)
    scenario.pass_until_resolved()
    scenario.block(reef, dreadmaw)
    scenario.combat_damage()

    assert dreadmaw.zone is Zone.GRAVEYARD, "CR 702.2b: four deathtouch damage kills a 6/6"


# -- Firdoch Core -------------------------------------------------------------


def _core_board(*, hand: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=hand or [],
            battlefield=["Firdoch Core", *["Forest"] * 4],
            library=["Forest"] * 3,
        )
        .player("bob", library=["Forest"] * 3)
    )


def test_firdoch_core_is_a_kindred_artifact_with_every_creature_type():
    scenario = _core_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    core = _ready(scenario, "Firdoch Core")

    computed = scenario.game.computed_board().of(core)
    assert not computed.is_creature
    assert Type.ARTIFACT in computed.types and Type.KINDRED in computed.types
    assert {"Goblin", "Elf", "Dragon", "Shapeshifter"} <= set(computed.subtypes)
    assert "Equipment" not in computed.subtypes, "CR 205.3d: creature types only"


@pytest.mark.parametrize("colour", [Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN])
def test_firdoch_core_taps_for_one_mana_of_any_colour(colour):
    scenario = _core_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    core = _ready(scenario, "Firdoch Core")

    scenario.activate(core, index=0, color=colour)

    assert scenario.player("alice").mana_pool.floating == {colour: 1}


def test_firdoch_core_becomes_a_four_four_artifact_creature_until_end_of_turn():
    scenario = _core_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    core = _ready(scenario, "Firdoch Core")

    scenario.activate(core, *scenario.untapped_sources(*["Forest"] * 4), index=1)
    scenario.pass_until_resolved()

    computed = scenario.game.computed_board().of(core)
    assert computed.is_creature
    assert Type.ARTIFACT in computed.types
    assert (computed.power, computed.toughness) == (4, 4)
    assert computed.colors == (), "no colour is printed in the animation"
    assert {"Goblin", "Shapeshifter"} <= set(computed.subtypes)


def test_firdoch_core_stops_being_a_creature_in_the_cleanup_step():
    scenario = _core_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    core = _ready(scenario, "Firdoch Core")
    scenario.activate(core, *scenario.untapped_sources(*["Forest"] * 4), index=1)
    scenario.pass_until_resolved()

    while scenario.game.turn.active_player == "alice":
        scenario.advance()

    computed = scenario.game.computed_board().of(core)
    assert not computed.is_creature
    assert Type.ARTIFACT in computed.types
    assert (computed.power, computed.toughness) == (None, None)


def test_animated_firdoch_core_that_was_controlled_all_turn_can_attack():
    scenario = _core_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    core = _ready(scenario, "Firdoch Core")
    scenario.activate(core, *scenario.untapped_sources(*["Forest"] * 4), index=1)
    scenario.pass_until_resolved()
    _to_declare_attackers(scenario)

    assert scenario.can_attack(core)


def test_a_firdoch_core_cast_this_turn_cannot_attack_once_animated():
    """CR 302.6: it became a creature, so summoning sickness applies to it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Firdoch Core"],
            battlefield=["Forest"] * 7,
            library=["Forest"] * 3,
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Firdoch Core", *scenario.untapped_sources(*["Forest"] * 3))
    core = scenario.find("Firdoch Core", Zone.BATTLEFIELD, "alice")
    scenario.activate(core, *scenario.untapped_sources(*["Forest"] * 4), index=1)
    scenario.pass_until_resolved()
    _to_declare_attackers(scenario)

    assert scenario.game.computed_board().of(core).is_creature
    assert not scenario.can_attack(core)


# -- The reader fixed here, on a second printing -------------------------------


def test_alloy_animist_animating_a_kindred_artifact_keeps_its_creature_type():
    """CR 205.1a: only an effect that sets a creature type replaces the old
    ones. "Becomes a 4/4 artifact creature" sets none, so Obsidian Battle-Axe
    stays a Warrior (the same reader as Firdoch Core's {4} ability, reached
    through a target instead of "this artifact")."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Alloy Animist", "Obsidian Battle-Axe", "Forest", "Forest", "Forest"],
            library=["Forest"] * 3,
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    animist = _ready(scenario, "Alloy Animist")
    axe = scenario.find("Obsidian Battle-Axe", Zone.BATTLEFIELD, "alice")
    scenario.activate(animist, *scenario.untapped_sources(*["Forest"] * 3), index=0, targets=[axe])
    scenario.pass_until_resolved()

    computed = scenario.game.computed_board().of(axe)
    assert computed.is_creature and Type.ARTIFACT in computed.types
    assert (computed.power, computed.toughness) == (4, 4)
    assert "Warrior" in computed.subtypes
