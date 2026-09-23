"""A land becoming a 0/0 creature for the rest of the game, grown by counters.

"Put three +1/+1 counters on up to one target noncreature land you control.
Untap it. It becomes a 0/0 Elemental creature with vigilance and haste that's
still a land." - Nissa, Who Shakes the World's +1. The animation names no
duration, so it lasts for the rest of the game; the counters are what give
the 0/0 its size. The same template reads on the proof printings:

- Wall of Resurgence: "you may put three +1/+1 counters on target land you
  control. If you do, that land becomes a 0/0 Elemental creature with haste
  that's still a land." - an ETB trigger, an optional put, an anaphoric
  "that land";
- Stalking Stones: "{6}: This land becomes a 3/3 Elemental artifact creature
  that's still a land." - the land animating itself, indefinitely.

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 611.2a** - "If no duration is stated, it lasts until the end of the
  game."
- **CR 205.1b** - "that's still a land" retains every prior card type and
  subtype: an animated Forest is still a Forest.
- **CR 613.4b / 613.4c / 122.1a** - the 0/0 is set in layer 7b and the
  +1/+1 counters are applied in layer 7c on top of it.
- **CR 115.6** - "up to one" may choose zero targets, and then the ability
  does nothing but its cost is still paid (**CR 606.4**).
- **CR 608.2b** - a target gone by resolution is illegal, and nothing is done
  to it.
- **CR 702.10b** - haste lets a land that entered this turn attack.
- **CR 702.20b** - attacking does not tap a creature with vigilance.
- **CR 106.12a** - Nissa's "Whenever you tap a Forest for mana" triggers off
  an animated Forest too, because it is still a Forest.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _nissa_board(*, alice_hand: list[str] | None = None, bob: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=alice_hand or [],
            battlefield=["Nissa, Who Shakes the World", "Forest", "Island"],
            library=["Island"] * 5,
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            battlefield=bob if bob is not None else ["Mountain", "Forest"],
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _nissa(scenario):
    return scenario.find("Nissa, Who Shakes the World", Zone.BATTLEFIELD, "alice")


def _plus_one(scenario, target):
    nissa = _nissa(scenario)
    scenario.activate(nissa, index=0, targets=[target] if target is not None else [])
    scenario.pass_until_resolved()
    return nissa


def test_plus_one_makes_a_tapped_forest_an_untapped_three_three_elemental_land():
    scenario = _nissa_board()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    forest.tapped = True

    nissa = _plus_one(scenario, forest)

    assert nissa.loyalty == 6, "CR 606.4: the +1 is its cost"
    assert not forest.tapped, "Untap it."
    assert forest.counters[Counter.PLUS_ONE] == 3
    computed = scenario.game.computed_board().of(forest)
    assert computed.is_creature
    assert computed.is_land, "CR 205.1b: that's still a land"
    assert (computed.power, computed.toughness) == (3, 3), "0/0 set, three counters on top"
    assert "Elemental" in computed.subtypes
    assert "Forest" in computed.subtypes, "CR 205.1b retains its land type too"
    assert computed.has_ability("Vigilance")
    assert computed.has_ability("Haste")
    assert computed.colors == ()


def test_the_animation_lasts_past_the_end_of_the_turn():
    """CR 611.2a: no duration stated means the rest of the game."""
    scenario = _nissa_board()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    _plus_one(scenario, forest)

    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    while scenario.game.turn.active_player == "bob":
        scenario.advance()

    computed = scenario.game.computed_board().of(forest)
    assert computed.is_creature
    assert (computed.power, computed.toughness) == (3, 3)
    assert computed.has_ability("Haste")


def test_an_island_animates_just_the_same_the_template_names_no_land_type():
    scenario = _nissa_board()
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    _plus_one(scenario, island)
    computed = scenario.game.computed_board().of(island)
    assert computed.is_creature and "Island" in computed.subtypes
    assert (computed.power, computed.toughness) == (3, 3)


def test_a_land_played_this_turn_can_attack_at_once_thanks_to_haste():
    """CR 702.10b."""
    scenario = _nissa_board(alice_hand=["Forest"])
    fresh = scenario.play_land("Forest")
    _plus_one(scenario, fresh)
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    assert scenario.can_attack(fresh)


def test_the_animated_land_attacks_without_tapping():
    """CR 702.20b: vigilance."""
    scenario = _nissa_board()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    _plus_one(scenario, forest)
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(forest)
    assert not forest.tapped


def test_choosing_no_target_changes_nothing_but_still_adds_loyalty():
    """CR 115.6 + CR 606.4."""
    scenario = _nissa_board()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    nissa = _plus_one(scenario, None)
    assert nissa.loyalty == 6
    assert forest.counters[Counter.PLUS_ONE] == 0
    assert not scenario.game.computed_board().of(forest).is_creature
    assert not scenario.game.computed_board().of(nissa).is_creature, "never the source"


def test_an_opponents_land_is_not_a_legal_target():
    """ "target noncreature land *you control*"."""
    scenario = _nissa_board()
    bobs_forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    with pytest.raises(ValueError):
        scenario.activate(_nissa(scenario), index=0, targets=[bobs_forest])


def test_a_land_that_is_already_a_creature_is_not_a_legal_target():
    """ "target *noncreature* land": a land Nissa already animated is a
    creature, so a second +1 next turn cannot pick it again."""
    scenario = _nissa_board()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    _plus_one(scenario, forest)
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    while scenario.game.turn.active_player == "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    with pytest.raises(ValueError):
        scenario.activate(_nissa(scenario), index=0, targets=[forest])


def test_a_target_that_left_before_resolution_gets_nothing():
    """CR 608.2b: the land is gone, so there is no counter, no untap and no
    animation - and nothing else is animated in its place."""
    scenario = _nissa_board()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    nissa = _nissa(scenario)
    scenario.activate(nissa, index=0, targets=[forest])
    scenario.game.destroy(forest)
    scenario.pass_until_resolved()

    assert forest.zone is Zone.GRAVEYARD
    assert not scenario.game.computed_board().of(nissa).is_creature
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    assert not scenario.game.computed_board().of(island).is_creature


def test_nissa_leaving_in_response_does_not_stop_the_ability():
    """CR 113.7a: once activated, the ability exists independently of Nissa."""
    scenario = _nissa_board()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    nissa = _nissa(scenario)
    scenario.activate(nissa, index=0, targets=[forest])
    scenario.game.destroy(nissa)
    scenario.pass_until_resolved()

    assert nissa.zone is Zone.GRAVEYARD
    assert forest.counters[Counter.PLUS_ONE] == 3
    computed = scenario.game.computed_board().of(forest)
    assert computed.is_creature and (computed.power, computed.toughness) == (3, 3)


def test_the_animated_forest_still_makes_nissas_extra_green():
    """Nissa's static trigger reads "a Forest" (CR 106.12a); CR 205.1b kept
    the animated land a Forest, so tapping it for mana still adds {G}{G}."""
    scenario = _nissa_board()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    _plus_one(scenario, forest)

    scenario.game.activate_ability(forest, 0, "alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("alice").mana_pool.total == 2


def test_three_damage_kills_the_three_three_land_it_is_a_creature_now():
    """The animated land is a creature for CR 704.5g like any other."""
    scenario = _nissa_board()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    _plus_one(scenario, forest)
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[forest],
    )
    assert forest.zone is Zone.GRAVEYARD


# -- Wall of Resurgence: an ETB trigger, "you may ... If you do, that land" --


def _wall_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wall of Resurgence"],
            battlefield=["Plains", "Plains", "Plains"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_wall(scenario, target, *, take: bool):
    scenario.will_take_the_may(take, source="Wall of Resurgence")
    scenario.put_onto_battlefield("Wall of Resurgence", "alice")
    scenario.choose_trigger_targets("Wall of Resurgence", [target])
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def test_wall_of_resurgence_makes_a_land_a_three_three_elemental_with_haste():
    scenario = _wall_board()
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "alice")
    _enter_wall(scenario, plains, take=True)

    assert plains.counters[Counter.PLUS_ONE] == 3
    computed = scenario.game.computed_board().of(plains)
    assert computed.is_creature and computed.is_land
    assert (computed.power, computed.toughness) == (3, 3)
    assert "Elemental" in computed.subtypes and "Plains" in computed.subtypes
    assert computed.has_ability("Haste")
    assert not computed.has_ability("Vigilance")


def test_wall_of_resurgence_declined_puts_nothing_and_animates_nothing():
    """ "If you do" (CR 608.2c): no counters put, so no animation either."""
    scenario = _wall_board()
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "alice")
    _enter_wall(scenario, plains, take=False)

    assert plains.counters[Counter.PLUS_ONE] == 0
    assert not scenario.game.computed_board().of(plains).is_creature
    wall = scenario.find("Wall of Resurgence", Zone.BATTLEFIELD, "alice")
    assert (scenario.game.computed_board().of(wall).power) == 0, "the Wall is untouched"


def test_wall_of_resurgence_leaving_in_response_still_animates_the_land():
    """CR 113.7a: the trigger exists independently of the Wall."""
    scenario = _wall_board()
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, source="Wall of Resurgence")
    wall = scenario.put_onto_battlefield("Wall of Resurgence", "alice")
    scenario.choose_trigger_targets("Wall of Resurgence", [plains])
    scenario.game.put_triggers_on_stack()
    scenario.game.destroy(wall)
    while scenario.game.stack:
        scenario.resolve_top()

    assert wall.zone is Zone.GRAVEYARD
    computed = scenario.game.computed_board().of(plains)
    assert computed.is_creature and (computed.power, computed.toughness) == (3, 3)


def test_wall_of_resurgences_target_gone_animates_nothing_else():
    """CR 608.2b: no legal target, nothing done - never the Wall itself."""
    scenario = _wall_board()
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, source="Wall of Resurgence")
    wall = scenario.put_onto_battlefield("Wall of Resurgence", "alice")
    scenario.choose_trigger_targets("Wall of Resurgence", [plains])
    scenario.game.put_triggers_on_stack()
    scenario.game.destroy(plains)
    while scenario.game.stack:
        scenario.resolve_top()

    computed = scenario.game.computed_board().of(wall)
    assert Type.LAND not in computed.types
    assert (computed.power, computed.toughness) == (0, 6)
    assert wall.counters[Counter.PLUS_ONE] == 0


def test_wall_of_resurgences_land_stays_a_creature_next_turn():
    scenario = _wall_board()
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "alice")
    _enter_wall(scenario, plains, take=True)
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    assert scenario.game.computed_board().of(plains).is_creature


# -- Stalking Stones: itself, for the rest of the game ------------------------


def _stones_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Stalking Stones", *["Wastes"] * 6],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stones = scenario.find("Stalking Stones", Zone.BATTLEFIELD, "alice")
    scenario.activate(stones, *scenario.untapped_sources(*["Wastes"] * 6), index=1)
    scenario.pass_until_resolved()
    return scenario, stones


def test_stalking_stones_becomes_a_three_three_elemental_artifact_creature_land():
    scenario, stones = _stones_board()
    computed = scenario.game.computed_board().of(stones)
    assert set(computed.types) == {Type.ARTIFACT, Type.CREATURE, Type.LAND}
    assert (computed.power, computed.toughness) == (3, 3)
    assert "Elemental" in computed.subtypes


def test_stalking_stones_stays_animated_after_the_turn_ends():
    """CR 611.2a: its reminder text says it too - "This effect lasts
    indefinitely."."""
    scenario, stones = _stones_board()
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    computed = scenario.game.computed_board().of(stones)
    assert computed.is_creature and computed.is_land
    assert (computed.power, computed.toughness) == (3, 3)
