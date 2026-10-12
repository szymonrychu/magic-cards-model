"""Scenario: die-roll results tables, random and named-choice rows, and the
opponent attack/payment restrictions (EP-01 round 3, task T1).

Every rule cited here was looked up with `mise run rules:find` in the session
that wrote this file:

- CR 706.2 - the natural result of a die roll, and modifiers that add to or
  subtract from it; the result is the number after every modifier.
- CR 706.3a - a results table: each row means "If the result was in this
  range, [effect]", and a result no row names does nothing.
- CR 706.3b - the roll, its modifiers, the instructions based on the result
  and the table are all one ability.
"""

from random import Random

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.machines.effects.continuous import transform_permanent
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def board(
    alice: list[str] | None = None,
    bob: list[str] | None = None,
    *,
    step: Step = Step.PRECOMBAT_MAIN,
    alice_zones: dict | None = None,
    bob_zones: dict | None = None,
):
    scenario = (
        Scenario()
        .player("alice", battlefield=alice or [], **(alice_zones or {}))
        .player("bob", battlefield=bob or [], **(bob_zones or {}))
        .build()
    )
    scenario.start_at(step)
    return scenario


def rig_dice(scenario: Scenario, rolls: list[int], sides: int = 20) -> None:
    """Pick a `shuffle_seed` under which the next dice `Game.roll_dice` rolls
    come out as `rolls` - the engine still rolls (CR 706.1a), this only picks
    the seed its randomness is drawn from."""
    game = scenario.game
    start = game.coin_flips_performed
    for seed in range(400000):
        if all(
            Random(f"{seed}:{start + index}:die").randint(1, sides) == roll  # noqa: S311
            for index, roll in enumerate(rolls)
        ):
            game.shuffle_seed = seed
            return
    raise AssertionError(f"no seed found for {rolls}")


def on_battlefield(scenario: Scenario, name: str, username: str):
    return [
        state
        for state in scenario.game.battlefield
        if state.name in (name, f"{name} Token") and (state.controller or state.owner) == username
    ]


def names(cards) -> list[str]:
    return sorted(card.name for card in cards)


def enter_and_resolve(scenario: Scenario, name: str, username: str = "alice"):
    permanent = scenario.put_onto_battlefield(name, username)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    return permanent


# --------------------------------------------------------------------------
# d20 results tables (CR 706.3a)
# --------------------------------------------------------------------------


def test_swarming_goblins_low_roll_makes_one_goblin():
    scenario = board(alice_zones={"hand": ["Swarming Goblins"]})
    rig_dice(scenario, [4])
    enter_and_resolve(scenario, "Swarming Goblins")
    assert len(on_battlefield(scenario, "Goblin", "alice")) == 1


def test_swarming_goblins_middle_roll_makes_two_of_those_tokens():
    scenario = board(alice_zones={"hand": ["Swarming Goblins"]})
    rig_dice(scenario, [10])
    enter_and_resolve(scenario, "Swarming Goblins")
    goblins = on_battlefield(scenario, "Goblin", "alice")
    assert len(goblins) == 2
    for goblin in goblins:
        stats = scenario.game.characteristics_of(goblin)
        assert (stats.power, stats.toughness) == (1, 1)


def test_swarming_goblins_natural_twenty_makes_three():
    scenario = board(alice_zones={"hand": ["Swarming Goblins"]})
    rig_dice(scenario, [20])
    enter_and_resolve(scenario, "Swarming Goblins")
    assert len(on_battlefield(scenario, "Goblin", "alice")) == 3


def test_scion_of_stygia_low_roll_only_taps():
    scenario = board(bob=["Grizzly Bears"], alice_zones={"hand": ["Scion of Stygia"]})
    bears = scenario.creature("Grizzly Bears", "bob")
    rig_dice(scenario, [9])
    scenario.will_choose_targets(bears)
    enter_and_resolve(scenario, "Scion of Stygia")
    assert bears.tapped
    assert not bears.exerted  # it untaps as usual in bob's next untap step


def test_scion_of_stygia_high_roll_taps_and_holds_it_down():
    scenario = board(bob=["Grizzly Bears"], alice_zones={"hand": ["Scion of Stygia"]})
    bears = scenario.creature("Grizzly Bears", "bob")
    rig_dice(scenario, [10])
    scenario.will_choose_targets(bears)
    enter_and_resolve(scenario, "Scion of Stygia")
    assert bears.tapped
    assert bears.exerted  # CR 701.43b's flag: skips its controller's next untap step
    scion = scenario.creature("Scion of Stygia", "alice")
    assert not scion.tapped  # "that creature" is the target, never the trigger's source


def test_aberrant_mind_sorcerer_high_roll_returns_the_target_to_hand():
    scenario = board(
        alice_zones={"hand": ["Aberrant Mind Sorcerer"], "graveyard": ["Lightning Bolt"]}
    )
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    rig_dice(scenario, [10])
    scenario.will_choose_targets(bolt)
    enter_and_resolve(scenario, "Aberrant Mind Sorcerer")
    assert bolt.zone is Zone.HAND


def test_aberrant_mind_sorcerer_low_roll_may_put_it_on_top():
    scenario = board(
        alice_zones={
            "hand": ["Aberrant Mind Sorcerer"],
            "graveyard": ["Lightning Bolt"],
            "library": ["Forest", "Island"],
        }
    )
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    rig_dice(scenario, [3])
    scenario.will_choose_targets(bolt)
    scenario.will_take_the_may(True)
    enter_and_resolve(scenario, "Aberrant Mind Sorcerer")
    assert scenario.player("alice").library[0] is bolt


def test_aberrant_mind_sorcerer_low_roll_declined_leaves_it():
    scenario = board(
        alice_zones={"hand": ["Aberrant Mind Sorcerer"], "graveyard": ["Lightning Bolt"]}
    )
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    rig_dice(scenario, [3])
    scenario.will_choose_targets(bolt)
    scenario.will_take_the_may(False)
    enter_and_resolve(scenario, "Aberrant Mind Sorcerer")
    assert bolt.zone is Zone.GRAVEYARD


def _pit_trap(roll: int):
    scenario = board(["Spiked Pit Trap", *["Wastes"] * 5], ["Colossal Dreadmaw"])
    trap = scenario.creature("Spiked Pit Trap", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    rig_dice(scenario, [roll])
    scenario.activate(
        trap, *scenario.untapped_sources(*["Wastes"] * 5), sacrificing=[trap], targets=[dreadmaw]
    )
    scenario.pass_until_resolved()
    return scenario, dreadmaw


def test_spiked_pit_trap_low_roll_deals_five():
    scenario, dreadmaw = _pit_trap(9)
    assert dreadmaw.damage == 5
    assert on_battlefield(scenario, "Treasure", "alice") == []


def test_spiked_pit_trap_high_roll_also_makes_a_treasure():
    scenario, dreadmaw = _pit_trap(12)
    assert dreadmaw.damage == 5
    assert len(on_battlefield(scenario, "Treasure", "alice")) == 1


def _troll(roll: int):
    scenario = board(
        ["Forest", "Forest", "Forest", "Forest"],
        alice_zones={"graveyard": ["Loathsome Troll"], "library": ["Island"]},
    )
    troll = scenario.find("Loathsome Troll", Zone.GRAVEYARD, "alice")
    rig_dice(scenario, [roll])
    scenario.activate(troll, *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest"))
    scenario.pass_until_resolved()
    return scenario, troll


def test_loathsome_troll_low_roll_goes_on_top_of_the_library():
    scenario, troll = _troll(1)
    assert scenario.player("alice").library[0] is troll


def test_loathsome_troll_middle_roll_returns_to_hand():
    scenario, troll = _troll(19)
    assert troll.zone is Zone.HAND


def test_loathsome_troll_twenty_returns_to_the_battlefield_tapped():
    scenario, troll = _troll(20)
    assert troll.zone is Zone.BATTLEFIELD
    assert troll.tapped


def test_loathsome_troll_cannot_be_activated_from_the_battlefield():
    scenario = board(["Loathsome Troll", "Forest", "Forest", "Forest", "Forest"])
    troll = scenario.creature("Loathsome Troll", "alice")
    assert scenario.why_cannot_activate(troll) is not None


def _chest(roll: int, library: list[str] | None = None):
    scenario = board(
        ["Treasure Chest", "Wastes", "Wastes", "Wastes", "Wastes"],
        alice_zones={"library": library or ["Island", "Forest", "Plains", "Swamp"]},
    )
    chest = scenario.creature("Treasure Chest", "alice")
    rig_dice(scenario, [roll])
    scenario.activate(
        chest,
        *scenario.untapped_sources("Wastes", "Wastes", "Wastes", "Wastes"),
        sacrificing=[chest],
    )
    scenario.pass_until_resolved()
    return scenario


def test_treasure_chest_natural_one_is_trapped():
    scenario = _chest(1)
    assert scenario.player("alice").life == 17


def test_treasure_chest_low_roll_makes_five_treasures():
    scenario = _chest(2)
    assert len(on_battlefield(scenario, "Treasure", "alice")) == 5


def test_treasure_chest_middle_roll_gains_and_draws():
    scenario = _chest(19)
    assert scenario.player("alice").life == 23
    assert len(scenario.player("alice").hand) == 3


def test_treasure_chest_twenty_puts_an_artifact_onto_the_battlefield():
    scenario = board(
        ["Treasure Chest", "Wastes", "Wastes", "Wastes", "Wastes"],
        alice_zones={"library": ["Island", "Ornithopter"]},
    )
    chest = scenario.creature("Treasure Chest", "alice")
    rig_dice(scenario, [20])
    ornithopter = scenario.find("Ornithopter", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(ornithopter)
    scenario.will_take_the_may(True)
    scenario.activate(
        chest,
        *scenario.untapped_sources("Wastes", "Wastes", "Wastes", "Wastes"),
        sacrificing=[chest],
    )
    scenario.pass_until_resolved()
    assert ornithopter.zone is Zone.BATTLEFIELD


def test_treasure_chest_twenty_puts_a_nonartifact_into_the_hand():
    scenario = board(
        ["Treasure Chest", "Wastes", "Wastes", "Wastes", "Wastes"],
        alice_zones={"library": ["Island", "Ornithopter"]},
    )
    chest = scenario.creature("Treasure Chest", "alice")
    rig_dice(scenario, [20])
    island = scenario.find("Island", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(island)
    scenario.activate(
        chest,
        *scenario.untapped_sources("Wastes", "Wastes", "Wastes", "Wastes"),
        sacrificing=[chest],
    )
    scenario.pass_until_resolved()
    assert island.zone is Zone.HAND


def _deck(
    roll: int, hand: list[str], graveyard: list[str] | None = None, bob_yard=None, prepare=None
):
    scenario = board(
        ["The Deck of Many Things", "Wastes", "Wastes"],
        alice_zones={
            "hand": hand,
            "graveyard": graveyard or [],
            "library": ["Island", "Forest", "Plains"],
        },
        bob_zones={"graveyard": bob_yard or []},
    )
    deck = scenario.creature("The Deck of Many Things", "alice")
    rig_dice(scenario, [roll])
    if prepare is not None:
        prepare(scenario)
    scenario.activate(deck, *scenario.untapped_sources("Wastes", "Wastes"))
    scenario.pass_until_resolved()
    return scenario


def test_deck_of_many_things_subtracts_hand_size_and_discards_at_zero():
    # natural 3, three cards in hand: the result is 0 (CR 706.2).
    scenario = _deck(3, ["Island", "Forest", "Plains"], ["Lightning Bolt"])
    alice = scenario.player("alice")
    assert alice.hand == []
    assert "Lightning Bolt" in names(alice.graveyard)  # no row for 0 (CR 706.3a)


def test_deck_of_many_things_modified_low_result_returns_a_random_card():
    # natural 12, three cards in hand: result 9.
    scenario = _deck(12, ["Island", "Forest", "Plains"], ["Lightning Bolt"])
    alice = scenario.player("alice")
    assert "Lightning Bolt" in names(alice.hand)
    assert len(alice.hand) == 4


def test_deck_of_many_things_middle_result_draws_two():
    scenario = _deck(15, [])
    assert len(scenario.player("alice").hand) == 2


def test_deck_of_many_things_twenty_reanimates_and_dooms_its_owner():
    chosen = {}

    def prepare(scenario):
        chosen["card"] = scenario.find("Colossal Dreadmaw", Zone.GRAVEYARD, "bob")
        scenario.will_choose_cards(chosen["card"])

    scenario = _deck(20, [], ["Grizzly Bears"], bob_yard=["Colossal Dreadmaw"], prepare=prepare)
    dreadmaw = chosen["card"]
    assert dreadmaw.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(dreadmaw).username == "alice"
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert not scenario.game.is_over
    scenario.game.destroy(dreadmaw)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    scenario.state_based_actions()
    # its owner (bob), not the player who controlled it, loses (CR 104.3e)
    assert not scenario.game.is_in_game("bob")
    assert scenario.game.is_in_game("alice")


def test_deck_of_many_things_twenty_with_no_creature_card_anywhere_does_nothing():
    scenario = _deck(20, [], ["Lightning Bolt"])
    assert names(scenario.player("alice").graveyard) == ["Lightning Bolt"]
    assert not scenario.game.is_over


def test_haunted_fengraf_returns_a_creature_card_at_random_to_hand():
    # Second printing for the widened "at random from your graveyard to your
    # hand" reader: a creature card, never the land in the same graveyard.
    scenario = board(
        ["Haunted Fengraf", "Wastes", "Wastes", "Wastes"],
        alice_zones={"graveyard": ["Grizzly Bears", "Forest"]},
    )
    fengraf = scenario.creature("Haunted Fengraf", "alice")
    scenario.activate(
        fengraf,
        *scenario.untapped_sources("Wastes", "Wastes", "Wastes"),
        index=1,
        sacrificing=[fengraf],
    )
    scenario.pass_until_resolved()
    alice = scenario.player("alice")
    assert names(alice.hand) == ["Grizzly Bears"]
    assert "Forest" in names(alice.graveyard)


def test_haunted_fengraf_with_no_creature_card_returns_nothing():
    scenario = board(
        ["Haunted Fengraf", "Wastes", "Wastes", "Wastes"],
        alice_zones={"graveyard": ["Forest"]},
    )
    fengraf = scenario.creature("Haunted Fengraf", "alice")
    scenario.activate(
        fengraf,
        *scenario.untapped_sources("Wastes", "Wastes", "Wastes"),
        index=1,
        sacrificing=[fengraf],
    )
    scenario.pass_until_resolved()
    assert scenario.player("alice").hand == []


# --------------------------------------------------------------------------
# Modes printed as token characteristics (CR 700.2): "choose one that hasn't
# been chosen this turn" (Genku) and "choose one at random" (Outlaws'
# Merriment, whose ruling picks the mode as the ability goes on the stack,
# CR 700.2b's moment)
# --------------------------------------------------------------------------

_FOX = "Create a 2/2 white Fox creature token with vigilance."
_MOONFOLK = "Create a 1/2 blue Moonfolk creature token with flying."


def _genku_board():
    scenario = board(["Genku, Future Shaper", "Ornithopter", "Memnite", "Wastes"])
    return scenario


def _leave(scenario: Scenario, name: str) -> None:
    scenario.game.sacrifice(scenario.creature(name, "alice"))
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def test_genku_makes_the_chosen_token():
    scenario = _genku_board()
    scenario.will_choose_mode(_FOX)
    _leave(scenario, "Ornithopter")
    (fox,) = on_battlefield(scenario, "Fox", "alice")
    stats = scenario.game.characteristics_of(fox)
    assert (stats.power, stats.toughness) == (2, 2)
    assert has_keyword(fox, "vigilance", scenario.game)


def test_genku_will_not_repeat_a_mode_in_the_same_turn():
    import pytest

    scenario = _genku_board()
    scenario.will_choose_mode(_FOX)
    _leave(scenario, "Ornithopter")
    scenario.will_choose_mode(_FOX)
    with pytest.raises(ValueError):
        _leave(scenario, "Memnite")


def test_genku_offers_a_used_mode_again_next_turn():
    scenario = _genku_board()
    scenario.will_choose_mode(_FOX)
    _leave(scenario, "Ornithopter")
    scenario.game.cleanup_step()  # CR 514.2: "this turn" ends
    scenario.will_choose_mode(_FOX)
    _leave(scenario, "Memnite")
    assert len(on_battlefield(scenario, "Fox", "alice")) == 2


def test_genku_a_second_leave_makes_a_different_token():
    scenario = _genku_board()
    scenario.will_choose_mode(_FOX)
    _leave(scenario, "Ornithopter")
    scenario.will_choose_mode(_MOONFOLK)
    _leave(scenario, "Memnite")
    assert len(on_battlefield(scenario, "Moonfolk", "alice")) == 1


def test_genku_ignores_a_token_leaving():
    scenario = _genku_board()
    scenario.will_choose_mode(_FOX)
    _leave(scenario, "Ornithopter")
    (fox,) = on_battlefield(scenario, "Fox", "alice")
    scenario.game.sacrifice(fox)
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack == []


def _merriment_upkeep(seed: int):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Outlaws' Merriment"], library=["Wastes"] * 3)
        .player("bob", battlefield=["Grizzly Bears"], library=["Wastes"] * 3)
        .build()
    )
    scenario.start_at(Step.UNTAP)
    scenario.game.shuffle_seed = seed
    scenario.advance()  # untap -> upkeep: the mode is picked as it goes on the stack
    scenario.will_choose_targets(scenario.creature("Grizzly Bears", "bob"))
    scenario.pass_until_resolved()
    tokens = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and state.name.startswith("Human")
    ]
    return scenario, tokens


def test_outlaws_merriment_makes_one_red_and_white_token_without_asking():
    from magic_cards_model.machines.decisions import DecisionKind

    scenario, tokens = _merriment_upkeep(1)
    assert len(tokens) == 1
    stats = scenario.game.characteristics_of(tokens[0])
    assert {color.value for color in stats.colors} == {"R", "W"}
    assert (stats.power, stats.toughness) in {(3, 1), (2, 1), (1, 2)}
    assert all(q.kind is not DecisionKind.CHOOSE_A_MODE for q in scenario.questions_asked())


def test_outlaws_merriment_picks_every_mode_across_seeds():
    seen = set()
    for seed in range(40):
        scenario, (token,) = _merriment_upkeep(seed)
        stats = scenario.game.characteristics_of(token)
        seen.add((stats.power, stats.toughness))
        if len(seen) == 3:
            break
    assert seen == {(3, 1), (2, 1), (1, 2)}


# --------------------------------------------------------------------------
# A modal activation whose instruction line carries "Activate only once each
# turn" (Skinshifter; CR 700.2a picks the mode on activation, CR 602.5b)
# --------------------------------------------------------------------------

_RHINO = (
    "Until end of turn, this creature becomes a Rhino with base power and toughness 4/4 "
    "and gains trample."
)
_PLANT = "Until end of turn, this creature becomes a Plant with base power and toughness 0/8."


def test_skinshifter_becomes_a_rhino():
    scenario = board(["Skinshifter", "Forest", "Forest"])
    shifter = scenario.creature("Skinshifter", "alice")
    scenario.will_choose_mode(_RHINO)
    scenario.activate(shifter, scenario.untapped_sources("Forest")[0])
    scenario.pass_until_resolved()
    stats = scenario.game.characteristics_of(shifter)
    assert (stats.power, stats.toughness) == (4, 4)
    assert set(stats.subtypes) == {"Rhino"}
    assert has_keyword(shifter, "trample", scenario.game)


def test_skinshifter_becomes_a_plant_and_reverts_at_end_of_turn():
    scenario = board(["Skinshifter", "Forest", "Forest"])
    shifter = scenario.creature("Skinshifter", "alice")
    scenario.will_choose_mode(_PLANT)
    scenario.activate(shifter, scenario.untapped_sources("Forest")[0])
    scenario.pass_until_resolved()
    stats = scenario.game.characteristics_of(shifter)
    assert (stats.power, stats.toughness) == (0, 8)
    scenario.game.cleanup_step()
    stats = scenario.game.characteristics_of(shifter)
    assert (stats.power, stats.toughness) == (1, 1)


def test_skinshifter_activates_only_once_each_turn():
    scenario = board(["Skinshifter", "Forest", "Forest"])
    shifter = scenario.creature("Skinshifter", "alice")
    scenario.will_choose_mode(_PLANT)
    scenario.activate(shifter, scenario.untapped_sources("Forest")[0])
    scenario.pass_until_resolved()
    assert scenario.why_cannot_activate(shifter) is not None


# --------------------------------------------------------------------------
# Payment and opponent-caused restrictions (CR 101.2): Yasharn's "can't pay
# life or sacrifice nonland permanents to cast spells or activate abilities",
# Tamiyo's "can't cause you to discard cards or sacrifice permanents"
# --------------------------------------------------------------------------


def test_yasharn_finds_a_basic_forest_and_a_basic_plains():
    scenario = board(
        alice_zones={
            "hand": ["Yasharn, Implacable Earth"],
            "library": ["Island", "Forest", "Swamp", "Plains", "Mountain"],
        }
    )
    enter_and_resolve(scenario, "Yasharn, Implacable Earth")
    assert names(scenario.player("alice").hand) == ["Forest", "Plains"]
    assert len(scenario.player("alice").library) == 3


def test_yasharn_finds_only_the_forest_when_there_is_no_plains():
    scenario = board(
        alice_zones={"hand": ["Yasharn, Implacable Earth"], "library": ["Island", "Forest"]}
    )
    enter_and_resolve(scenario, "Yasharn, Implacable Earth")
    assert names(scenario.player("alice").hand) == ["Forest"]


def test_yasharn_refuses_sacrificing_a_nonland_permanent_for_a_cost():
    import pytest

    scenario = board(
        ["Yasharn, Implacable Earth", "Spiked Pit Trap", *["Wastes"] * 5], ["Grizzly Bears"]
    )
    trap = scenario.creature("Spiked Pit Trap", "alice")
    with pytest.raises(ValueError):
        scenario.activate(
            trap,
            *scenario.untapped_sources(*["Wastes"] * 5),
            sacrificing=[trap],
            targets=[scenario.creature("Grizzly Bears", "bob")],
        )
    assert trap.zone is Zone.BATTLEFIELD


def test_yasharn_still_lets_a_land_be_sacrificed_for_a_cost():
    scenario = board(
        ["Yasharn, Implacable Earth", "Haunted Fengraf", "Wastes", "Wastes", "Wastes"],
        alice_zones={"graveyard": ["Grizzly Bears"]},
    )
    fengraf = scenario.creature("Haunted Fengraf", "alice")
    scenario.activate(
        fengraf,
        *scenario.untapped_sources("Wastes", "Wastes", "Wastes"),
        index=1,
        sacrificing=[fengraf],
    )
    scenario.pass_until_resolved()
    assert names(scenario.player("alice").hand) == ["Grizzly Bears"]


def test_yasharn_refuses_paying_life_for_a_mana_ability():
    import pytest

    scenario = board(["Yasharn, Implacable Earth", "Horizon Canopy"])
    canopy = scenario.creature("Horizon Canopy", "alice")
    with pytest.raises(ValueError, match="CR 101.2"):
        scenario.activate(canopy, color=Color.GREEN)
    assert scenario.player("alice").life == 20


def test_horizon_canopy_pays_life_without_yasharn():
    scenario = board(["Horizon Canopy"])
    canopy = scenario.creature("Horizon Canopy", "alice")
    scenario.activate(canopy, color=Color.GREEN)
    assert scenario.player("alice").life == 19


def _mind_rot(protection: list[str]):
    scenario = board(
        ["Swamp", "Swamp", "Swamp"],
        protection,
        alice_zones={"hand": ["Mind Rot"]},
        bob_zones={"hand": ["Island", "Forest"]},
    )
    scenario.cast_and_resolve(
        "Mind Rot", *scenario.untapped_sources("Swamp", "Swamp", "Swamp"), targets=["bob"]
    )
    return scenario


def test_tamiyo_stops_an_opponents_spell_making_you_discard():
    scenario = _mind_rot(["Tamiyo, Collector of Tales"])
    assert names(scenario.player("bob").hand) == ["Forest", "Island"]


def test_tamiyo_stops_an_opponents_spell_making_you_sacrifice():
    scenario = board(
        ["Swamp", "Swamp"],
        ["Tamiyo, Collector of Tales", "Grizzly Bears"],
        alice_zones={"hand": ["Diabolic Edict"]},
    )
    scenario.cast_and_resolve(
        "Diabolic Edict", *scenario.untapped_sources("Swamp", "Swamp"), targets=["bob"]
    )
    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD


def test_tamiyo_does_not_stop_its_controllers_own_discard():
    scenario = board(
        ["Tamiyo, Collector of Tales", "Swamp", "Swamp", "Swamp"],
        alice_zones={"hand": ["Mind Rot", "Island", "Forest"]},
    )
    scenario.cast_and_resolve(
        "Mind Rot", *scenario.untapped_sources("Swamp", "Swamp", "Swamp"), targets=["alice"]
    )
    assert scenario.player("alice").hand == []


def test_without_tamiyo_the_opponents_discard_happens():
    scenario = _mind_rot([])
    assert scenario.player("bob").hand == []


def test_tajuru_preserver_still_stops_only_the_sacrifice():
    # The widened reader's existing printing: "can't cause you to sacrifice
    # permanents" alone does not stop a discard.
    scenario = _mind_rot(["Tajuru Preserver"])
    assert scenario.player("bob").hand == []


# --------------------------------------------------------------------------
# "The chosen <thing>" (CR 614.12a): the as-enters answer read back later
# --------------------------------------------------------------------------


def test_dauntless_bodyguard_saves_the_chosen_creature():
    scenario = board(["Grizzly Bears"], alice_zones={"hand": ["Dauntless Bodyguard"]})
    bears = scenario.creature("Grizzly Bears", "alice")
    bodyguard = scenario.put_onto_battlefield("Dauntless Bodyguard", "alice")
    assert bodyguard.choice is not None and bodyguard.choice.value == str(bears.id)
    scenario.activate(bodyguard, sacrificing=[bodyguard])
    scenario.pass_until_resolved()
    scenario.game.destroy(bears)
    assert bears.zone is Zone.BATTLEFIELD  # indestructible (CR 702.12b)


def test_dauntless_bodyguard_grant_ends_with_the_turn():
    scenario = board(["Grizzly Bears"], alice_zones={"hand": ["Dauntless Bodyguard"]})
    bears = scenario.creature("Grizzly Bears", "alice")
    bodyguard = scenario.put_onto_battlefield("Dauntless Bodyguard", "alice")
    scenario.activate(bodyguard, sacrificing=[bodyguard])
    scenario.pass_until_resolved()
    scenario.game.cleanup_step()  # "until end of turn" ends (CR 514.2)
    scenario.game.destroy(bears)
    assert bears.zone is Zone.GRAVEYARD


def test_dauntless_bodyguard_with_no_creature_chosen_grants_nothing():
    scenario = board(["Wastes"], alice_zones={"hand": ["Dauntless Bodyguard"]})
    bodyguard = scenario.put_onto_battlefield("Dauntless Bodyguard", "alice")
    scenario.activate(bodyguard, sacrificing=[bodyguard])
    scenario.pass_until_resolved()
    assert bodyguard.zone is Zone.GRAVEYARD


def _talion(number: str, spell: str, mana: list[str]):
    scenario = (
        Scenario()
        .player("bob", battlefield=mana, hand=[spell], library=["Wastes"] * 3)
        .player("alice", hand=["Talion, the Kindly Lord"], library=["Island", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose(number, source="Talion, the Kindly Lord")
    scenario.put_onto_battlefield("Talion, the Kindly Lord", "alice")
    casting = scenario.cast(spell, username="bob")
    if spell == "Lightning Bolt":
        casting.choose_targets(["alice"])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*mana, username="bob"))
    scenario.put_on_stack(casting)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    return scenario


def test_talion_punishes_a_spell_with_the_chosen_mana_value():
    scenario = _talion("1", "Lightning Bolt", ["Mountain"])
    assert scenario.player("bob").life == 18
    assert len(scenario.player("alice").hand) == 1


def test_talion_ignores_a_spell_with_another_mana_value():
    scenario = _talion("3", "Lightning Bolt", ["Mountain"])
    assert scenario.player("bob").life == 20
    assert scenario.player("alice").hand == []


def test_talion_reads_the_spells_toughness():
    # Ornithopter: mana value 0, power 0, toughness 2.
    scenario = _talion("2", "Ornithopter", [])
    assert scenario.player("bob").life == 18


def test_talion_ignores_its_controllers_own_spell():
    scenario = board(
        ["Mountain"],
        alice_zones={"hand": ["Talion, the Kindly Lord", "Lightning Bolt"], "library": ["Island"]},
    )
    scenario.will_choose("1", source="Talion, the Kindly Lord")
    scenario.put_onto_battlefield("Talion, the Kindly Lord", "alice")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    assert scenario.player("alice").life == 20
    assert scenario.player("alice").hand == []


def test_sarpadian_empires_makes_a_token_of_the_chosen_color_and_type():
    scenario = board(
        ["Wastes", "Wastes", "Wastes"], alice_zones={"hand": ["Sarpadian Empires, Vol. VII"]}
    )
    scenario.will_choose("white Citizen", source="Sarpadian Empires, Vol. VII")
    empires = scenario.put_onto_battlefield("Sarpadian Empires, Vol. VII", "alice")
    scenario.activate(empires, *scenario.untapped_sources("Wastes", "Wastes", "Wastes"))
    scenario.pass_until_resolved()
    (citizen,) = on_battlefield(scenario, "Citizen", "alice")
    stats = scenario.game.characteristics_of(citizen)
    assert (stats.power, stats.toughness) == (1, 1)
    assert {color.value for color in stats.colors} == {"W"}
    assert "Citizen" in stats.subtypes


def test_sarpadian_empires_another_answer_another_token():
    scenario = board(
        ["Wastes", "Wastes", "Wastes"], alice_zones={"hand": ["Sarpadian Empires, Vol. VII"]}
    )
    scenario.will_choose("green Saproling", source="Sarpadian Empires, Vol. VII")
    empires = scenario.put_onto_battlefield("Sarpadian Empires, Vol. VII", "alice")
    scenario.activate(empires, *scenario.untapped_sources("Wastes", "Wastes", "Wastes"))
    scenario.pass_until_resolved()
    (saproling,) = on_battlefield(scenario, "Saproling", "alice")
    assert {c.value for c in scenario.game.characteristics_of(saproling).colors} == {"G"}


def test_tamiyo_plus_one_takes_every_card_with_the_chosen_name():
    scenario = board(
        ["Tamiyo, Collector of Tales"],
        alice_zones={"library": ["Lightning Bolt", "Island", "Lightning Bolt", "Forest", "Plains"]},
    )
    tamiyo = scenario.creature("Tamiyo, Collector of Tales", "alice")
    scenario.will_choose("Lightning Bolt", source="Tamiyo, Collector of Tales")
    scenario.activate(tamiyo, index=0)
    scenario.pass_until_resolved()
    alice = scenario.player("alice")
    assert names(alice.hand) == ["Lightning Bolt", "Lightning Bolt"]
    assert names(alice.graveyard) == ["Forest", "Island"]
    assert names(alice.library) == ["Plains"]


def test_tamiyo_plus_one_naming_a_missing_card_bins_all_four():
    scenario = board(
        ["Tamiyo, Collector of Tales"],
        alice_zones={"library": ["Island", "Forest", "Swamp", "Mountain"]},
    )
    tamiyo = scenario.creature("Tamiyo, Collector of Tales", "alice")
    scenario.will_choose("Lightning Bolt", source="Tamiyo, Collector of Tales")
    scenario.activate(tamiyo, index=0)
    scenario.pass_until_resolved()
    assert scenario.player("alice").hand == []
    assert len(scenario.player("alice").graveyard) == 4


def test_tamiyo_plus_one_refuses_a_land_name():
    import pytest

    scenario = board(["Tamiyo, Collector of Tales"], alice_zones={"library": ["Island"] * 4})
    tamiyo = scenario.creature("Tamiyo, Collector of Tales", "alice")
    scenario.will_choose("Island", source="Tamiyo, Collector of Tales")
    scenario.activate(tamiyo, index=0)
    with pytest.raises(ValueError, match="nonland"):
        scenario.pass_until_resolved()


# --------------------------------------------------------------------------
# War's Toll: an opponent's mana tap taps all their lands
# --------------------------------------------------------------------------


def test_wars_toll_taps_all_lands_of_the_opponent_who_tapped_for_mana():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Forest", "Forest", "Mountain"], library=["Wastes"] * 3)
        .player("alice", battlefield=["War's Toll", "Island"], library=["Wastes"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.untapped_sources("Forest", username="bob")[0]
    scenario.activate(forest, username="bob", color=Color.GREEN)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert all(land.tapped for land in scenario.game.battlefield if land.controller == "bob")
    assert not scenario.creature("Island", "alice").tapped


def test_wars_toll_ignores_its_controllers_own_mana():
    scenario = board(["War's Toll", "Island", "Island"])
    island = scenario.untapped_sources("Island")[0]
    scenario.activate(island, color=Color.BLUE)
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack == []
    assert len([c for c in scenario.game.battlefield if c.name == "Island" and not c.tapped]) == 1


def test_wars_toll_makes_every_creature_of_an_attacking_opponent_attack():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"], library=["Wastes"] * 3)
        .player("alice", battlefield=["War's Toll"], library=["Wastes"] * 3)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    # CR 508.1d: one attacker turns the conditional requirement on for both.
    with pytest.raises(ValueError, match="War's Toll"):
        scenario.attack_with(bears)
    scenario.attack_with(bears, giant)
    assert {c.name for c in scenario.attackers()} == {"Grizzly Bears", "Hill Giant"}


def test_wars_toll_lets_an_opponent_attack_with_nothing():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"], library=["Wastes"] * 3)
        .player("alice", battlefield=["War's Toll"], library=["Wastes"] * 3)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.game.declare_attackers([])
    assert scenario.attackers() == []


def test_wars_toll_does_not_bind_its_controllers_attack():
    scenario = board(["War's Toll", "Grizzly Bears", "Hill Giant"], step=Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    assert [c.name for c in scenario.attackers()] == ["Grizzly Bears"]


# --------------------------------------------------------------------------
# Zenos yae Galvus // Shinryu: the chosen creature and the chosen player
# --------------------------------------------------------------------------


def _zenos(extra_bob: list[str] | None = None, *, carol: bool = False):
    builder = (
        Scenario()
        .player("alice", battlefield=["Savannah Lions"], hand=["Zenos yae Galvus"])
        .player("bob", battlefield=["Hill Giant", "Grizzly Bears", *(extra_bob or [])])
    )
    if carol:
        builder = builder.player("carol", battlefield=["Memnite"])
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_choose_cards(giant, source="Zenos yae Galvus")
    zenos = scenario.put_onto_battlefield("Zenos yae Galvus", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    return scenario, zenos, giant


def test_zenos_shrinks_every_other_creature_but_the_chosen_one():
    scenario, zenos, giant = _zenos()
    assert zenos.choice is not None and zenos.choice.value == str(giant.id)
    stats = scenario.game.characteristics_of(giant)
    assert (stats.power, stats.toughness) == (3, 3)
    assert (scenario.game.power_of(zenos), scenario.game.toughness_of(zenos)) == (4, 4)
    # Grizzly Bears and Savannah Lions get -2/-2 and die (CR 704.5f).
    graveyards = names(scenario.player("bob").graveyard) + names(scenario.player("alice").graveyard)
    assert sorted(graveyards) == ["Grizzly Bears", "Savannah Lions"]


def test_zenos_shrink_ends_with_the_turn():
    scenario, _zenos_state, _giant = _zenos(["Craw Wurm"])
    wurm = scenario.creature("Craw Wurm", "bob")
    assert scenario.game.power_of(wurm) == 4
    scenario.game.cleanup_step()
    assert scenario.game.power_of(wurm) == 6


def test_zenos_transforms_when_the_chosen_creature_leaves_and_chooses_an_opponent():
    scenario, zenos, giant = _zenos(carol=True)
    scenario.will_choose("carol", source="Shinryu, Transcendent Rival")
    scenario.game.destroy(giant)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert zenos.up_face_name == "Shinryu, Transcendent Rival"
    assert zenos.chosen_player == "carol"


def test_zenos_ignores_another_creature_leaving():
    scenario, zenos, _giant = _zenos(["Craw Wurm"])
    scenario.game.destroy(scenario.creature("Craw Wurm", "bob"))
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert zenos.up_face_name == "Zenos yae Galvus"


def test_shinryu_wins_the_game_when_the_chosen_player_loses():
    scenario, zenos, giant = _zenos(carol=True)
    scenario.will_choose("bob", source="Shinryu, Transcendent Rival")
    scenario.game.destroy(giant)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert zenos.chosen_player == "bob"
    scenario.game.player_loses_the_game("bob")
    assert not scenario.game.is_over  # carol is still in (CR 104.2a)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.game.winner == "alice"  # CR 104.2b


def test_shinryu_ignores_another_player_losing():
    scenario, zenos, giant = _zenos(carol=True)
    scenario.will_choose("bob", source="Shinryu, Transcendent Rival")
    scenario.game.destroy(giant)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    scenario.game.player_loses_the_game("carol")
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack == []
    assert scenario.game.winner is None


# --------------------------------------------------------------------------
# Unstable Glyphbridge // Sandswirl Wanderglyph
# --------------------------------------------------------------------------


def _glyphbridge_cast():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Savannah Lions", "Hill Giant", *(["Plains"] * 5)],
            hand=["Unstable Glyphbridge"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Memnite", "Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_unstable_glyphbridge_keeps_one_small_creature_per_player():
    scenario = _glyphbridge_cast()
    lions = scenario.creature("Savannah Lions", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_cards(lions, source="Unstable Glyphbridge")
    scenario.will_choose_cards(bears, source="Unstable Glyphbridge")
    scenario.cast_and_resolve("Unstable Glyphbridge", *scenario.untapped_sources(*["Plains"] * 5))
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    survivors = {c.name for c in scenario.game.battlefield if c.card.is_creature}
    assert survivors == {"Savannah Lions", "Grizzly Bears"}


def test_unstable_glyphbridge_put_onto_the_battlefield_does_nothing():
    # CR 603.4: "if you cast it" - not cast, no trigger.
    scenario = _glyphbridge_cast()
    scenario.put_onto_battlefield("Unstable Glyphbridge", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack == []
    assert len([c for c in scenario.game.battlefield if c.card.is_creature]) == 5


def _wanderglyph(bob_hand: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Island"],
            hand=bob_hand or [],
            library=["Wastes"] * 3,
        )
        .player("alice", hand=["Unstable Glyphbridge"], library=["Wastes"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    glyph = scenario.put_onto_battlefield("Unstable Glyphbridge", "alice")
    transform_permanent(scenario.game, glyph)
    assert glyph.up_face_name == "Sandswirl Wanderglyph"
    return scenario


def test_sandswirl_wanderglyph_stops_an_opponent_who_cast_on_their_turn_from_attacking():
    scenario = _wanderglyph(["Opt"])
    scenario.cast_and_resolve(
        "Opt", *scenario.untapped_sources("Island", username="bob"), username="bob"
    )
    scenario.pass_until_resolved()  # the cast trigger resolved first, then Opt
    scenario.start_at(Step.DECLARE_ATTACKERS)
    with pytest.raises(ValueError, match="Sandswirl Wanderglyph"):
        scenario.attack_with(scenario.creature("Grizzly Bears", "bob"))


def test_sandswirl_wanderglyph_lets_a_quiet_opponent_attack():
    scenario = _wanderglyph()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "bob"))
    assert [c.name for c in scenario.attackers()] == ["Grizzly Bears"]


def test_sandswirl_wanderglyph_bars_an_opponent_who_attacked_from_casting():
    scenario = _wanderglyph(["Opt"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "bob"))
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    with pytest.raises(ValueError, match="Sandswirl Wanderglyph"):
        scenario.cast("Opt", username="bob")


def test_sandswirl_wanderglyph_lets_an_opponent_who_did_not_attack_cast():
    scenario = _wanderglyph(["Opt"])
    scenario.cast_and_resolve(
        "Opt", *scenario.untapped_sources("Island", username="bob"), username="bob"
    )
    scenario.pass_until_resolved()  # the cast trigger resolved first, then Opt
    assert "Opt" in names(scenario.player("bob").graveyard)


# Second printing for the "a player loses the game" event (CR 104.3):
# Withengar Unbound counts any player's loss, not only a chosen one.


def _elbrus_equipped():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Elbrus, the Binding Blade", "Grizzly Bears"])
        .player("bob", life=2)
        .player("carol", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elbrus = scenario.creature("Elbrus, the Binding Blade", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    elbrus.attach_to(bears)
    return scenario, elbrus, bears


def test_elbrus_unattaches_and_transforms_after_combat_damage():
    scenario, elbrus, bears = _elbrus_equipped()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="carol")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert elbrus.up_face_name == "Withengar Unbound"
    assert elbrus.attached_to is None  # CR 701.3d


def test_withengar_unbound_grows_when_any_player_loses():
    scenario, elbrus, _bears = _elbrus_equipped()
    elbrus.unattach()
    transform_permanent(scenario.game, elbrus)
    scenario.game.player_loses_the_game("bob")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert elbrus.counter_count(Counter.PLUS_ONE) == 13
