"""Life lost "this way", and life lost or gained "this turn", used as an amount.

The mechanic is one: a later instruction reads the life that an earlier one
really took or gave. Three shapes of it:

- the drain pair - "Each opponent loses N life. You gain life equal to the life
  lost this way." The second sentence is what the first one *actually* did
  (CR 119.3 adjusts the life total; CR 608.2c lets a later instruction modify an
  earlier one), summed over every player who lost, not a second evaluation of N.
- counters per life lost - "Put a +1/+1 counter on this creature for each 1
  life lost this way" after "each player loses 1 life" (Blood Tyrant).
- the this-turn amounts - "the amount of life you gained this turn", "the life
  they lost this turn", "the total life lost by all players this turn" as the X
  of a loss, a mill or a gain, taken once when the instruction is applied
  (CR 608.2h) and, for "they", once per player.

CR numbers below were looked up with `mise run rules:find`: 119.3, 119.2,
608.2c, 608.2h, 107.3a, 107.3f, 102.3, 201.2, 701.17a, 700.4, 702.101a, 603.2,
118.3b, 614.1a, 119.10, 701.23e.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

SWAMPS = ["Swamp"] * 8


def settle(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def life(scenario, name: str) -> int:
    return scenario.player(name).life


def cast_x(scenario, name: str, x: int, *sources, targets=None) -> None:
    casting = scenario.cast(name, targets=targets)
    casting.determine_cost(x_value=x)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def to_end_step(scenario) -> None:
    """Walk to the end step so "at the beginning of ... end step" triggers fire."""
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    assert scenario.step is Step.END_STEP


def main_phase(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


# -- the drain pair on a spell ---------------------------------------------------


def test_blood_tithe_drains_three_and_gains_what_was_lost():
    scenario = (
        Scenario().player("alice", hand=["Blood Tithe"], battlefield=SWAMPS).player("bob").build()
    )
    main_phase(scenario)
    scenario.cast_and_resolve("Blood Tithe", *scenario.untapped_sources(*["Swamp"] * 4))
    assert life(scenario, "bob") == 17
    assert life(scenario, "alice") == 23


def test_the_pair_sums_over_every_opponent():
    """CR 102.3 / 119.3: three players, two opponents lose 3 each, six gained."""
    scenario = (
        Scenario()
        .player("alice", hand=["Blood Tithe"], battlefield=SWAMPS)
        .player("bob")
        .player("carol")
        .build()
    )
    main_phase(scenario)
    scenario.cast_and_resolve("Blood Tithe", *scenario.untapped_sources(*["Swamp"] * 4))
    assert life(scenario, "bob") == 17
    assert life(scenario, "carol") == 17
    assert life(scenario, "alice") == 26


def test_the_gain_runs_through_gain_replacements():
    """CR 614.1a / 119.10: Alhammarret's Archive doubles the gain of the 3 lost."""
    scenario = (
        Scenario()
        .player("alice", hand=["Blood Tithe"], battlefield=[*SWAMPS, "Alhammarret's Archive"])
        .player("bob")
        .build()
    )
    main_phase(scenario)
    scenario.cast_and_resolve("Blood Tithe", *scenario.untapped_sources(*["Swamp"] * 4))
    assert life(scenario, "bob") == 17
    assert life(scenario, "alice") == 26


def test_exsanguinate_reads_the_announced_x():
    scenario = (
        Scenario().player("alice", hand=["Exsanguinate"], battlefield=SWAMPS).player("bob").build()
    )
    main_phase(scenario)
    cast_x(scenario, "Exsanguinate", 4, *scenario.untapped_sources(*["Swamp"] * 6))
    assert life(scenario, "bob") == 16
    assert life(scenario, "alice") == 24


def test_exsanguinate_for_zero_drains_nothing():
    scenario = (
        Scenario().player("alice", hand=["Exsanguinate"], battlefield=SWAMPS).player("bob").build()
    )
    main_phase(scenario)
    cast_x(scenario, "Exsanguinate", 0, *scenario.untapped_sources(*["Swamp"] * 2))
    assert life(scenario, "bob") == 20
    assert life(scenario, "alice") == 20


def test_debt_to_the_deathless_loses_two_times_x():
    scenario = (
        Scenario()
        .player("alice", hand=["Debt to the Deathless"], battlefield=[*SWAMPS, *["Plains"] * 4])
        .player("bob")
        .build()
    )
    main_phase(scenario)
    cast_x(
        scenario,
        "Debt to the Deathless",
        3,
        *scenario.untapped_sources("Plains", "Plains", *["Swamp"] * 5),
    )
    assert life(scenario, "bob") == 14
    assert life(scenario, "alice") == 26


# -- the drain pair on abilities ---------------------------------------------------


def test_agent_of_masks_upkeep_trigger():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Agent of Masks"], library=["Swamp"] * 3)
        .player("bob", library=["Swamp"] * 3)
        .build()
    )
    scenario.advance()
    assert scenario.step is Step.UPKEEP
    settle(scenario)
    assert life(scenario, "bob") == 19
    assert life(scenario, "alice") == 21


def test_scholar_of_athreos_activated_pair_can_repeat():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Scholar of Athreos", *SWAMPS])
        .player("bob")
        .build()
    )
    main_phase(scenario)
    scholar = scenario.find("Scholar of Athreos", Zone.BATTLEFIELD)
    for _ in range(2):
        scenario.activate(scholar, *scenario.untapped_sources(*["Swamp"] * 3))
        scenario.resolve_top()
    assert life(scenario, "bob") == 18
    assert life(scenario, "alice") == 22


def test_urborg_syphon_mage_hits_each_other_player():
    scenario = (
        Scenario()
        .player("alice", hand=["Swamp"], battlefield=["Urborg Syphon-Mage", *SWAMPS])
        .player("bob")
        .player("carol")
        .build()
    )
    main_phase(scenario)
    mage = scenario.find("Urborg Syphon-Mage", Zone.BATTLEFIELD)
    mage.summoning_sick = False
    scenario.activate(
        mage,
        *scenario.untapped_sources(*["Swamp"] * 3),
        discarding=[scenario.find("Swamp", Zone.HAND)],
    )
    scenario.resolve_top()
    assert life(scenario, "bob") == 18
    assert life(scenario, "carol") == 18
    assert life(scenario, "alice") == 24


def test_bubbling_cauldron_second_ability_needs_the_newt():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bubbling Cauldron", "Festering Newt", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    main_phase(scenario)
    cauldron = scenario.find("Bubbling Cauldron", Zone.BATTLEFIELD)
    newt = scenario.find("Festering Newt", Zone.BATTLEFIELD)
    scenario.activate(
        cauldron,
        *scenario.untapped_sources("Swamp"),
        index=1,
        sacrificing=[newt],
    )
    scenario.resolve_top()
    assert life(scenario, "bob") == 16
    assert life(scenario, "alice") == 24


def test_gontis_machinations_pays_energy_and_sacrifices_itself():
    scenario = (
        Scenario().player("alice", battlefield=["Gonti's Machinations"]).player("bob").build()
    )
    main_phase(scenario)
    scenario.player("alice").add_counters(Counter.ENERGY, 2)
    machinations = scenario.find("Gonti's Machinations", Zone.BATTLEFIELD)
    scenario.activate(machinations, sacrificing=[machinations])
    scenario.resolve_top()
    assert scenario.player("alice").energy == 0
    assert machinations.zone is Zone.GRAVEYARD
    assert life(scenario, "bob") == 17
    assert life(scenario, "alice") == 23


# -- the drain pair on triggers ------------------------------------------------------


def test_kokusho_death_trigger_drains_five():
    scenario = (
        Scenario().player("alice", battlefield=["Kokusho, the Evening Star"]).player("bob").build()
    )
    main_phase(scenario)
    scenario.game.destroy(scenario.find("Kokusho, the Evening Star", Zone.BATTLEFIELD))
    settle(scenario)
    assert life(scenario, "bob") == 15
    assert life(scenario, "alice") == 25


def test_malakir_bloodwitch_counts_vampires_when_it_enters():
    """CR 608.2h: the Vampire count is taken once, as the trigger resolves; the
    Bloodwitch is itself a Vampire and is on the battlefield by then."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Malakir Bloodwitch"],
            battlefield=["Vampire Nighthawk", *SWAMPS],
        )
        .player("bob")
        .build()
    )
    main_phase(scenario)
    scenario.cast_and_resolve("Malakir Bloodwitch", *scenario.untapped_sources(*["Swamp"] * 5))
    settle(scenario)
    assert life(scenario, "bob") == 18
    assert life(scenario, "alice") == 22


def test_servant_of_tymaret_inspired_when_it_untaps():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Servant of Tymaret"], library=["Swamp"] * 3)
        .player("bob", library=["Swamp"] * 3)
        .build()
    )
    scenario.find("Servant of Tymaret", Zone.BATTLEFIELD).tap()
    scenario.start_at(Step.UPKEEP)  # runs the untap step on the way
    settle(scenario)
    assert life(scenario, "bob") == 19
    assert life(scenario, "alice") == 21


def test_tormented_hero_heroic_trigger():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Tormented Hero", "Mountain"])
        .player("bob")
        .build()
    )
    main_phase(scenario)
    hero = scenario.find("Tormented Hero", Zone.BATTLEFIELD)
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[hero]
    )
    settle(scenario)
    assert life(scenario, "bob") == 19
    assert life(scenario, "alice") == 21


# -- counters per life lost --------------------------------------------------------


def test_blood_tyrant_gets_a_counter_for_each_life_lost_by_every_player():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Blood Tyrant"], library=["Swamp"] * 3)
        .player("bob", library=["Swamp"] * 3)
        .player("carol", library=["Swamp"] * 3)
        .build()
    )
    scenario.advance()
    settle(scenario)
    tyrant = scenario.find("Blood Tyrant", Zone.BATTLEFIELD)
    assert [life(scenario, n) for n in ("alice", "bob", "carol")] == [19, 19, 19]
    assert tyrant.counters[Counter.PLUS_ONE] == 3


def test_blood_tyrant_counts_only_life_actually_lost():
    """Platinum Emperion: a player whose life total can't change loses nothing, so the
    counters follow the 2 life really lost, not the 3 players at the table."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Blood Tyrant"], library=["Swamp"] * 3)
        .player("bob", battlefield=["Platinum Emperion"], library=["Swamp"] * 3)
        .player("carol", library=["Swamp"] * 3)
        .build()
    )
    scenario.advance()
    settle(scenario)
    tyrant = scenario.find("Blood Tyrant", Zone.BATTLEFIELD)
    assert life(scenario, "bob") == 20
    assert tyrant.counters[Counter.PLUS_ONE] == 2


def test_the_pair_gains_only_what_a_frozen_life_total_really_lost():
    """Platinum Emperion: bob's life total can't change, so only carol's 3 is lost and
    only 3 is gained."""
    scenario = (
        Scenario()
        .player("alice", hand=["Blood Tithe"], battlefield=SWAMPS)
        .player("bob", battlefield=["Platinum Emperion"])
        .player("carol")
        .build()
    )
    main_phase(scenario)
    scenario.cast_and_resolve("Blood Tithe", *scenario.untapped_sources(*["Swamp"] * 4))
    assert life(scenario, "bob") == 20
    assert life(scenario, "carol") == 17
    assert life(scenario, "alice") == 23


# -- this-turn amounts -------------------------------------------------------------


def test_hope_estheim_mills_by_life_gained_this_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hope Estheim"])
        .player("bob", library=["Swamp"] * 10)
        .build()
    )
    main_phase(scenario)
    scenario.game.gain_life("alice", 4)
    to_end_step(scenario)
    settle(scenario)
    assert len(scenario.player("bob").graveyard) == 4
    assert len(scenario.player("bob").library) == 6


def test_hope_estheim_with_no_life_gained_mills_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hope Estheim"])
        .player("bob", library=["Swamp"] * 10)
        .build()
    )
    main_phase(scenario)
    to_end_step(scenario)
    settle(scenario)
    assert len(scenario.player("bob").graveyard) == 0


def test_midnight_snack_loses_life_equal_to_life_gained_this_turn():
    scenario = (
        Scenario().player("alice", battlefield=["Midnight Snack", *SWAMPS]).player("bob").build()
    )
    main_phase(scenario)
    scenario.game.gain_life("alice", 5)
    snack = scenario.find("Midnight Snack", Zone.BATTLEFIELD)
    scenario.activate(
        snack, *scenario.untapped_sources(*["Swamp"] * 3), sacrificing=[snack], targets=["bob"]
    )
    scenario.resolve_top()
    assert life(scenario, "bob") == 15
    assert life(scenario, "alice") == 25


def test_midnight_snack_with_nothing_gained_loses_nothing():
    scenario = (
        Scenario().player("alice", battlefield=["Midnight Snack", *SWAMPS]).player("bob").build()
    )
    main_phase(scenario)
    snack = scenario.find("Midnight Snack", Zone.BATTLEFIELD)
    scenario.activate(
        snack, *scenario.untapped_sources(*["Swamp"] * 3), sacrificing=[snack], targets=["bob"]
    )
    scenario.resolve_top()
    assert life(scenario, "bob") == 20


def test_wound_reflection_doubles_each_opponents_own_loss():
    """The amount is per player: bob lost 3 this turn, carol 1, alice (not an
    opponent) 2."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wound Reflection"])
        .player("bob")
        .player("carol")
        .build()
    )
    main_phase(scenario)
    scenario.game.lose_life("bob", 3)
    scenario.game.lose_life("carol", 1)
    scenario.game.lose_life("alice", 2)
    to_end_step(scenario)
    settle(scenario)
    assert life(scenario, "bob") == 14
    assert life(scenario, "carol") == 18
    assert life(scenario, "alice") == 18


def test_wound_reflection_with_no_loss_does_nothing():
    scenario = Scenario().player("alice", battlefield=["Wound Reflection"]).player("bob").build()
    main_phase(scenario)
    to_end_step(scenario)
    settle(scenario)
    assert life(scenario, "bob") == 20


def test_warlock_class_level_three_uses_the_life_they_lost():
    scenario = Scenario().player("alice", battlefield=["Warlock Class"]).player("bob").build()
    main_phase(scenario)
    scenario.find("Warlock Class", Zone.BATTLEFIELD).class_level = 3
    scenario.game.lose_life("bob", 4)
    to_end_step(scenario)
    settle(scenario)
    assert life(scenario, "bob") == 12


def test_tainted_sigil_gains_the_total_life_lost_by_all_players():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tainted Sigil", "Plains", "Swamp"])
        .player("bob")
        .build()
    )
    main_phase(scenario)
    scenario.game.lose_life("bob", 3)
    scenario.game.lose_life("alice", 2)
    sigil = scenario.find("Tainted Sigil", Zone.BATTLEFIELD)
    sigil.summoning_sick = False
    scenario.activate(sigil, sacrificing=[sigil])
    scenario.resolve_top()
    # alice: 20 - 2 + (3 + 2)
    assert life(scenario, "alice") == 23
    assert life(scenario, "bob") == 17


def test_tainted_sigil_with_no_loss_gains_nothing():
    scenario = Scenario().player("alice", battlefield=["Tainted Sigil"]).player("bob").build()
    main_phase(scenario)
    sigil = scenario.find("Tainted Sigil", Zone.BATTLEFIELD)
    sigil.summoning_sick = False
    scenario.activate(sigil, sacrificing=[sigil])
    scenario.resolve_top()
    assert life(scenario, "alice") == 20


# -- second printing: the same pair reader on Gray Merchant of Asphodel ------------------


def test_gray_merchant_pair_through_the_shared_reader():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gray Merchant of Asphodel"],
            battlefield=[*SWAMPS],
        )
        .player("bob")
        .player("carol")
        .build()
    )
    main_phase(scenario)
    scenario.cast_and_resolve(
        "Gray Merchant of Asphodel", *scenario.untapped_sources(*["Swamp"] * 5)
    )
    settle(scenario)
    # devotion to black: Gray Merchant's {B}{B} only (the Swamps carry no cost)
    assert life(scenario, "bob") == 18
    assert life(scenario, "carol") == 18
    assert life(scenario, "alice") == 24


def test_gray_merchant_gain_goes_through_gain_replacements():
    """CR 119.10 / 614.1a: the pair's gain is a real gain, so Alhammarret's
    Archive doubles it (the devotion-drain path used to add life directly)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gray Merchant of Asphodel"],
            battlefield=[*SWAMPS, "Alhammarret's Archive"],
        )
        .player("bob")
        .build()
    )
    main_phase(scenario)
    scenario.cast_and_resolve(
        "Gray Merchant of Asphodel", *scenario.untapped_sources(*["Swamp"] * 5)
    )
    settle(scenario)
    assert life(scenario, "bob") == 18
    assert life(scenario, "alice") == 24


def test_bubbling_cauldron_refuses_a_creature_not_named_festering_newt():
    """CR 201.2: the cost names its sacrifice; a Grizzly Bears does not pay it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bubbling Cauldron", "Grizzly Bears", "Swamp"],
        )
        .player("bob")
        .build()
    )
    main_phase(scenario)
    cauldron = scenario.find("Bubbling Cauldron", Zone.BATTLEFIELD)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    with pytest.raises(ValueError, match="Festering Newt"):
        scenario.activate(
            cauldron, *scenario.untapped_sources("Swamp"), index=1, sacrificing=[bears]
        )
    assert life(scenario, "bob") == 20


def test_blood_tyrant_gets_five_counters_when_a_player_loses_the_game():
    """The card's other trigger, on the same Tyrant: three players, one loses."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Blood Tyrant"])
        .player("bob")
        .player("carol")
        .build()
    )
    main_phase(scenario)
    scenario.game.player_loses_the_game("bob")
    settle(scenario)
    tyrant = scenario.find("Blood Tyrant", Zone.BATTLEFIELD)
    assert tyrant.counters[Counter.PLUS_ONE] == 5


# -- fixtures the Cauldron's named-sacrifice cost needs, each played for real ------------
# Festering Newt is the only creature that can pay Bubbling Cauldron's cost, and
# Bogbrew Witch is the card its trigger names; both printings are in the pool,
# so both are proven here rather than left unplayed.


def test_festering_newt_dies_and_shrinks_an_opponents_creature_by_one():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Festering Newt"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    main_phase(scenario)
    scenario.game.destroy(scenario.find("Festering Newt", Zone.BATTLEFIELD))
    scenario.game.put_triggers_on_stack()
    scenario.choose_trigger_targets("Festering Newt", [scenario.creature("Grizzly Bears", "bob")])
    settle(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    assert (scenario.game.power_of(bears), scenario.game.toughness_of(bears)) == (1, 1)


def test_festering_newt_shrinks_by_four_when_its_controller_has_a_bogbrew_witch():
    """CR 614.1a: the "instead" replaces the -1/-1, it does not add to it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Festering Newt", "Bogbrew Witch"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    main_phase(scenario)
    scenario.game.destroy(scenario.find("Festering Newt", Zone.BATTLEFIELD))
    scenario.game.put_triggers_on_stack()
    scenario.choose_trigger_targets("Festering Newt", [scenario.creature("Hill Giant", "bob")])
    settle(scenario)
    scenario.state_based_actions()
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "bob")
    assert giant.zone is Zone.GRAVEYARD  # a 3/3 at -4/-4; -1/-1 would leave it alive


def test_bogbrew_witch_fetches_either_named_card_onto_the_battlefield_tapped():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bogbrew Witch", "Swamp", "Swamp"],
            library=["Swamp", "Festering Newt", "Swamp"],
        )
        .player("bob")
        .build()
    )
    main_phase(scenario)
    witch = scenario.find("Bogbrew Witch", Zone.BATTLEFIELD)
    witch.summoning_sick = False
    scenario.activate(witch, *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.resolve_top()
    newt = scenario.find("Festering Newt", Zone.BATTLEFIELD)
    assert newt.tapped
