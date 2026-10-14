"""EP-02-R3 T8: damage, pump and cost amounts - "+X/+X where X is ...", "deals damage
equal to ...", "costs {X} less ..." and the cards that grant, copy or cast from a
graveyard.

Rules, each looked up with `mise run rules:find` in the session that wrote this file:

- **CR 608.2h** - information about an object is taken once, as the effect applies.
- **CR 608.2c** - instructions are followed in order; later text refers to earlier text.
- **CR 107.3f** - X in the text of a spell or ability, not in a cost, is defined by that text.
- **CR 202.3** - mana value is the total amount of mana in the mana cost.
- **CR 119.3** - life gain and loss adjust a player's life total.
- **CR 122.1** - counters.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

LISTED = [
    "Arcane Proxy",
    "Archmage's Newt",
    "Beacon Bolt",
    "Bishop of Binding",
    "Boon of Boseiju",
    "Bronze Cudgels",
    "Cyclops Gladiator",
    "Dreadhorde Arcanist",
    "Flunk",
    "Freelance Muscle",
    "Friendly Fire",
    "Invoke Calamity",
    "Isildur's Fateful Strike",
    "Jushi Apprentice // Tomoya the Revealer",
    "Living Inferno",
    "Maelstrom Muse",
    "Nibelheim Aflame",
    "Osseous Sticktwister",
    "Porcuparrot",
    "Resilient Khenra",
    "Rowan, Scion of War",
    "Songcrafter Mage",
    "Sphinx of Forgotten Lore",
    "Survey Mechan",
    "Unleash the Inferno",
    "Voyager Drake",
    "Walking Bulwark",
    "Whispering Madness",
    "Will, Scion of Peace",
    "Zur, Eternal Schemer",
]

#: Second printings of the readers added or widened here (see each section).
# Rubblebelt Rioters (Pioneer, Modern; legalities checked 2026-10-14, not in the api decks):
# "it gets +X/+0 until end of turn, where X is the greatest power among creatures you control".
# No other Modern/Pioneer/Standard card prints "where X is the greatest mana value among
# permanents you control", "7 minus ...", "you may have target creature get +X/+X, where X ...",
# "the power of the exiled card" or "the number of times this ability has resolved" (bulk scan).
PROOF: list[str] = ["Rubblebelt Rioters"]

LANDS = ["Plains"] * 6 + ["Swamp"] * 4 + ["Island"] * 4 + ["Forest"] * 3 + ["Mountain"] * 4


@pytest.mark.parametrize("name", LISTED + PROOF)
def test_every_clause_of_a_listed_card_is_handled(name: str) -> None:
    clauses = classify_clauses(card(name))
    assert clauses
    assert all(clause.category == HANDLED for clause in clauses), [
        (clause.text, clause.category) for clause in clauses if clause.category != HANDLED
    ]


def _scenario(
    alice: list[str],
    bob: list[str] | None = None,
    *,
    hand: list[str] | None = None,
    library: list[str] | None = None,
    bob_hand: list[str] | None = None,
    graveyard: list[str] | None = None,
    bob_graveyard: list[str] | None = None,
    step: Step = Step.PRECOMBAT_MAIN,
):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[*alice, *LANDS],
            hand=hand,
            graveyard=graveyard,
            library=library or ["Island"] * 12,
        )
        .player(
            "bob",
            battlefield=[*(bob or []), *LANDS],
            hand=bob_hand,
            graveyard=bob_graveyard,
            library=["Island"] * 12,
        )
        .build()
    )
    scenario.start_at(step)
    return scenario


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast_all(scenario, name: str, *, user: str = "alice", targets=None) -> None:
    scenario.cast_onto_stack(name, username=user, targets=targets, auto=True)
    _resolve_all(scenario)


def _activate_all(scenario, source, *, index: int = 0, **kwargs) -> None:
    scenario.activate(source, index=index, auto=True, **kwargs)
    _resolve_all(scenario)


def _attack(scenario, *names: str) -> list:
    attackers = scenario.creatures(*names, username=scenario.player().username)
    scenario.advance()  # declare attackers
    scenario.attack_with(*attackers)
    return attackers


def _cast_kicked(scenario, name: str, times: int, *, user: str = "alice") -> None:
    casting = scenario.cast(name, username=user)
    for _ in range(times):
        casting.pay_kicker()
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username=user)
    scenario.put_on_stack(casting)
    _resolve_all(scenario)


def _stats(scenario, state) -> tuple[int, int]:
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


# ---------------------------------------------------------------------------
# Pumps: "+X/+X until end of turn, where X is ..."
# ---------------------------------------------------------------------------


def test_boon_of_boseiju_pumps_by_the_greatest_mana_value_and_untaps() -> None:
    scenario = _scenario(["Grizzly Bears", "Serra Angel"], hand=["Boon of Boseiju"])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True
    _cast_all(scenario, "Boon of Boseiju", targets=[bears])
    assert _stats(scenario, bears) == (2 + 5, 2 + 5)  # Serra Angel is mana value 5
    assert not bears.tapped


def test_boon_of_boseiju_counts_only_permanents_the_caster_controls() -> None:
    scenario = _scenario(["Grizzly Bears"], ["Serra Angel"], hand=["Boon of Boseiju"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_all(scenario, "Boon of Boseiju", targets=[bears])
    assert _stats(scenario, bears) == (2 + 2, 2 + 2)  # Bears itself (mana value 2)


def test_boon_of_boseiju_ends_at_end_of_turn() -> None:
    scenario = _scenario(["Grizzly Bears", "Serra Angel"], hand=["Boon of Boseiju"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_all(scenario, "Boon of Boseiju", targets=[bears])
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    assert _stats(scenario, bears) == (2, 2)


def test_flunk_shrinks_by_seven_minus_the_targets_controllers_hand() -> None:
    scenario = _scenario(
        [], ["Serra Angel"], hand=["Flunk"], bob_hand=["Island", "Island", "Island"]
    )
    angel = scenario.creature("Serra Angel", "bob")
    _cast_all(scenario, "Flunk", targets=[angel])
    assert angel.zone is Zone.GRAVEYARD  # 4/4 gets -4/-4


def test_flunk_reads_the_hand_of_the_creatures_controller_not_the_casters() -> None:
    scenario = _scenario(
        ["Grizzly Bears"], [], hand=["Flunk", "Island", "Island", "Island", "Island", "Island"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_all(scenario, "Flunk", targets=[bears])
    # alice holds 5 cards after casting Flunk: -2/-2 kills the 2/2
    assert bears.zone is Zone.GRAVEYARD


def test_flunk_with_a_full_hand_is_not_a_pump() -> None:
    scenario = _scenario(
        [],
        ["Serra Angel"],
        hand=["Flunk"],
        bob_hand=["Island"] * 8,
    )
    angel = scenario.creature("Serra Angel", "bob")
    _cast_all(scenario, "Flunk", targets=[angel])
    # 7 - 8 = -1: the creature gets +1/+1 (CR 107.1b is about counts; X stays -1 here)
    assert _stats(scenario, angel) == (5, 5)


def test_resilient_khenra_pumps_a_creature_by_its_own_power() -> None:
    scenario = _scenario(["Grizzly Bears"], hand=["Resilient Khenra"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Resilient Khenra", [bears])
    scenario.will_take_the_may(True, source="Resilient Khenra")
    _cast_all(scenario, "Resilient Khenra")
    assert _stats(scenario, bears) == (2 + 2, 2 + 2)  # Resilient Khenra is a 2/2


def test_resilient_khenra_may_be_declined() -> None:
    scenario = _scenario(["Grizzly Bears"], hand=["Resilient Khenra"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Resilient Khenra", [bears])
    scenario.will_take_the_may(False, source="Resilient Khenra")
    _cast_all(scenario, "Resilient Khenra")
    assert _stats(scenario, bears) == (2, 2)


def test_freelance_muscle_gets_the_greatest_power_or_toughness_of_the_others() -> None:
    scenario = _scenario(["Freelance Muscle", "Wall of Omens", "Grizzly Bears"])
    (muscle,) = _attack(scenario, "Freelance Muscle")
    _resolve_all(scenario)
    # Freelance Muscle is a 4/4; Wall of Omens is 0/4: toughness 4 is the greatest figure
    assert _stats(scenario, muscle) == (4 + 4, 4 + 4)


def test_freelance_muscle_does_not_count_itself() -> None:
    scenario = _scenario(["Freelance Muscle"])
    (muscle,) = _attack(scenario, "Freelance Muscle")
    _resolve_all(scenario)
    assert _stats(scenario, muscle) == (4, 4)  # no other creature: X = 0


def test_bishop_of_binding_pumps_a_vampire_by_the_power_of_the_exiled_card() -> None:
    scenario = _scenario([], ["Serra Angel"], hand=["Bishop of Binding"])
    angel = scenario.creature("Serra Angel", "bob")
    scenario.choose_trigger_targets("Bishop of Binding", [angel])
    _cast_all(scenario, "Bishop of Binding")
    assert angel.zone is Zone.EXILE
    bishop = scenario.find("Bishop of Binding", Zone.BATTLEFIELD, "alice")
    bishop.summoning_sick = False
    base = _stats(scenario, bishop)
    scenario.choose_trigger_targets("Bishop of Binding", [bishop])
    _attack(scenario, "Bishop of Binding")
    _resolve_all(scenario)
    assert _stats(scenario, bishop) == (base[0] + 4, base[1] + 4)  # Serra Angel's power is 4


def test_bronze_cudgels_counts_the_resolutions_this_turn() -> None:
    scenario = _scenario(["Bronze Cudgels", "Grizzly Bears"])
    cudgels = scenario.find("Bronze Cudgels", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    cudgels.attach_to(bears)
    assert cudgels.attached_to == bears.id
    _activate_all(scenario, cudgels, index=0)
    assert scenario.game.power_of(bears) == 2 + 1
    _activate_all(scenario, cudgels, index=0)
    assert scenario.game.power_of(bears) == 2 + 1 + 2  # second resolution: +2


def test_voyager_drake_gives_flying_to_up_to_x_creatures_for_x_kicks() -> None:
    scenario = _scenario(["Grizzly Bears", "Hill Giant", "Runeclaw Bear"], hand=["Voyager Drake"])
    bears, giant, runeclaw = (
        scenario.creature(n, "alice") for n in ("Grizzly Bears", "Hill Giant", "Runeclaw Bear")
    )
    scenario.choose_trigger_targets("Voyager Drake", [bears, giant])
    _cast_kicked(scenario, "Voyager Drake", 2)
    assert has_keyword(bears, "Flying", scenario.game)
    assert has_keyword(giant, "Flying", scenario.game)
    assert not has_keyword(runeclaw, "Flying", scenario.game)


def test_rubblebelt_rioters_gets_the_greatest_power_among_your_creatures() -> None:
    scenario = _scenario(["Rubblebelt Rioters", "Serra Angel"])
    (rioters,) = _attack(scenario, "Rubblebelt Rioters")
    _resolve_all(scenario)
    assert _stats(scenario, rioters) == (0 + 4, 4)  # Serra Angel's power 4 is the greatest


def test_rubblebelt_rioters_ignores_an_opponents_bigger_creature() -> None:
    scenario = _scenario(["Rubblebelt Rioters", "Grizzly Bears"], ["Serra Angel"])
    (rioters,) = _attack(scenario, "Rubblebelt Rioters")
    _resolve_all(scenario)
    assert _stats(scenario, rioters) == (0 + 2, 4)


def test_zur_turns_an_enchantment_into_a_creature_as_big_as_its_mana_value() -> None:
    scenario = _scenario(["Zur, Eternal Schemer", "Journey to Nowhere"])
    zur = scenario.find("Zur, Eternal Schemer", Zone.BATTLEFIELD, "alice")
    journey = scenario.find("Journey to Nowhere", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, zur, index=0, targets=[journey])
    chars = scenario.game.characteristics_of(journey)
    assert chars.is_creature
    assert Type.ENCHANTMENT in chars.types  # in addition to its other types
    assert _stats(scenario, journey) == (2, 2)  # mana value {1}{W}
    assert journey.zone is Zone.BATTLEFIELD


def test_zur_effect_does_not_end_with_the_turn() -> None:
    scenario = _scenario(["Zur, Eternal Schemer", "Journey to Nowhere"])
    zur = scenario.find("Zur, Eternal Schemer", Zone.BATTLEFIELD, "alice")
    journey = scenario.find("Journey to Nowhere", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, zur, index=0, targets=[journey])
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()
    assert scenario.game.characteristics_of(journey).is_creature


def test_walking_bulwark_attacks_despite_defender_and_deals_its_toughness() -> None:
    scenario = _scenario(["Walking Bulwark"])
    bulwark = scenario.find("Walking Bulwark", Zone.BATTLEFIELD, "alice")
    assert not scenario.can_attack(bulwark)  # defender
    _activate_all(scenario, bulwark, index=0, targets=[bulwark])
    _attack(scenario, "Walking Bulwark")
    scenario.no_blocks()
    scenario.combat_damage()
    assert scenario.player("bob").life == 20 - 3  # Walking Bulwark is a 0/3


def test_walking_bulwark_grant_ends_at_end_of_turn() -> None:
    scenario = _scenario(["Walking Bulwark"])
    bulwark = scenario.find("Walking Bulwark", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, bulwark, index=0, targets=[bulwark])
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()
    scenario.advance()  # bob's turn passes priority; the next alice turn is later
    assert not has_keyword(bulwark, "Haste", scenario.game)


# ---------------------------------------------------------------------------
# Costs: "costs {X} less to cast / activate, where X is ..." (CR 601.2f)
# ---------------------------------------------------------------------------


def _tapped_lands(scenario, user: str = "alice") -> int:
    return sum(
        1
        for state in scenario.game.battlefield
        if state.controller == user and state.tapped and Type.LAND in state.types
    )


def test_survey_mechan_costs_one_less_per_differently_named_land() -> None:
    scenario = _scenario(["Survey Mechan"])
    mechan = scenario.find("Survey Mechan", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, mechan, index=0, targets=["bob", "alice"])
    # five differently named lands (Plains, Swamp, Island, Forest, Mountain): {10} - 5
    assert _tapped_lands(scenario) == 5
    assert scenario.player("bob").life == 20 - 3
    assert mechan.zone is Zone.GRAVEYARD


def test_survey_mechan_counts_names_not_lands() -> None:
    scenario = _scenario(["Survey Mechan", "Plains", "Plains", "Plains", "Swamp"])
    mechan = scenario.find("Survey Mechan", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, mechan, index=0, targets=["bob", "alice"])
    assert _tapped_lands(scenario) == 5  # extra copies of a name add nothing


def test_survey_mechan_resolves_its_whole_effect() -> None:
    scenario = _scenario(["Survey Mechan"], library=["Island"] * 12)
    mechan = scenario.find("Survey Mechan", Zone.BATTLEFIELD, "alice")
    hand_before = len(scenario.player("alice").hand)
    _activate_all(scenario, mechan, index=0, targets=["bob", "alice"])
    assert len(scenario.player("alice").hand) == hand_before + 3
    assert scenario.player("alice").life == 20 + 3


def _cast_cost_in_lands(scenario, name: str, user: str = "alice", **kwargs) -> int:
    before = _tapped_lands(scenario, user)
    scenario.cast_onto_stack(name, username=user, auto=True, **kwargs)
    paid = _tapped_lands(scenario, user) - before
    _resolve_all(scenario)
    return paid


def test_rowan_makes_black_and_red_spells_cheaper_by_the_life_lost() -> None:
    scenario = _scenario(["Rowan, Scion of War"], hand=["Hill Giant", "Serra Angel"])
    scenario.player("alice").lose_life(2)
    rowan = scenario.find("Rowan, Scion of War", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, rowan, index=0)
    assert _cast_cost_in_lands(scenario, "Hill Giant") == 2  # {3}{R} - {2}
    assert _cast_cost_in_lands(scenario, "Serra Angel") == 5  # a white spell: not reduced


def test_rowan_reads_the_life_lost_when_the_ability_resolves() -> None:
    scenario = _scenario(["Rowan, Scion of War"], hand=["Hill Giant"])
    rowan = scenario.find("Rowan, Scion of War", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, rowan, index=0)  # nothing lost yet: {0} less
    scenario.player("alice").lose_life(3)
    assert _cast_cost_in_lands(scenario, "Hill Giant") == 4


def test_will_makes_white_and_blue_spells_cheaper_by_the_life_gained() -> None:
    scenario = _scenario(["Will, Scion of Peace"], hand=["Serra Angel", "Hill Giant"])
    scenario.player("alice").gain_life(3)
    will = scenario.find("Will, Scion of Peace", Zone.BATTLEFIELD, "alice")
    _activate_all(scenario, will, index=0)
    assert _cast_cost_in_lands(scenario, "Serra Angel") == 2  # {3}{W}{W} - {3}
    assert _cast_cost_in_lands(scenario, "Hill Giant") == 4  # red: not reduced


def test_will_is_sorcery_speed() -> None:
    scenario = _scenario(["Will, Scion of Peace"], step=Step.BEGINNING_OF_COMBAT)
    will = scenario.find("Will, Scion of Peace", Zone.BATTLEFIELD, "alice")
    assert scenario.why_cannot_activate(will, 0) is not None


def test_maelstrom_muse_reduces_the_next_instant_or_sorcery_by_its_power() -> None:
    scenario = _scenario(["Maelstrom Muse"], hand=["Think Twice", "Think Twice"])
    _attack(scenario, "Maelstrom Muse")
    _resolve_all(scenario)
    assert _cast_cost_in_lands(scenario, "Think Twice") == 1  # {1}{U} - {2} (Muse is a 2/4)
    assert _cast_cost_in_lands(scenario, "Think Twice") == 2  # the reduction is used up


# ---------------------------------------------------------------------------
# Grants: "target instant or sorcery card in your graveyard gains flashback" (CR 702.34a)
# ---------------------------------------------------------------------------


def _graveyard_cast_cost(scenario, name: str, user: str = "alice") -> int:
    card_state = scenario.find(name, Zone.GRAVEYARD, user)
    before = _tapped_lands(scenario, user)
    casting = scenario.cast(name, username=user, from_zone=Zone.GRAVEYARD)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username=user)
    scenario.put_on_stack(casting)
    paid = _tapped_lands(scenario, user) - before
    _resolve_all(scenario)
    assert card_state.zone is Zone.EXILE  # CR 702.34a: exiled, not put into the graveyard
    return paid


def test_sphinx_of_forgotten_lore_grants_flashback_at_the_cards_mana_cost() -> None:
    scenario = _scenario(["Sphinx of Forgotten Lore"], graveyard=["Think Twice"])
    think = scenario.find("Think Twice", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Sphinx of Forgotten Lore", [think])
    _attack(scenario, "Sphinx of Forgotten Lore")
    _resolve_all(scenario)
    assert _graveyard_cast_cost(scenario, "Think Twice") == 2  # {1}{U}


def test_sphinx_of_forgotten_lore_grants_nothing_without_a_target_in_the_graveyard() -> None:
    scenario = _scenario(["Sphinx of Forgotten Lore"], graveyard=["Grizzly Bears"])
    _attack(scenario, "Sphinx of Forgotten Lore")
    _resolve_all(scenario)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert scenario.game.play_permission_for(bears, "alice") is None


def test_archmages_newt_grants_flashback_at_the_mana_cost() -> None:
    scenario = _scenario(["Archmage's Newt"], graveyard=["Think Twice"])
    think = scenario.find("Think Twice", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Archmage's Newt", [think])
    _attack(scenario, "Archmage's Newt")
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve_all(scenario)
    assert _graveyard_cast_cost(scenario, "Think Twice") == 2


def test_archmages_newt_grants_flashback_zero_when_saddled() -> None:
    scenario = _scenario(["Archmage's Newt"], graveyard=["Think Twice"])
    newt = scenario.creature("Archmage's Newt", "alice")
    newt.saddled = True  # CR 702.171b
    think = scenario.find("Think Twice", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Archmage's Newt", [think])
    _attack(scenario, "Archmage's Newt")
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve_all(scenario)
    assert _graveyard_cast_cost(scenario, "Think Twice") == 0


# ---------------------------------------------------------------------------
# Damage: "deals damage equal to its power" between creatures and players
# ---------------------------------------------------------------------------


def test_nibelheim_aflame_hits_every_other_creature_with_the_chosen_ones_power() -> None:
    scenario = _scenario(
        ["Serra Angel", "Grizzly Bears"], ["Hill Giant", "Wall of Omens"], hand=["Nibelheim Aflame"]
    )
    angel = scenario.creature("Serra Angel", "alice")
    _cast_all(scenario, "Nibelheim Aflame", targets=[angel])
    assert angel.zone is Zone.BATTLEFIELD  # "each other creature"
    for name, user in (("Grizzly Bears", "alice"), ("Hill Giant", "bob"), ("Wall of Omens", "bob")):
        assert scenario.find(name, Zone.GRAVEYARD, user).zone is Zone.GRAVEYARD  # 4 damage each


def test_nibelheim_aflame_reads_the_power_as_it_resolves() -> None:
    scenario = _scenario(
        ["Grizzly Bears"], ["Hill Giant", "Wall of Omens"], hand=["Nibelheim Aflame"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_all(scenario, "Nibelheim Aflame", targets=[bears])
    assert scenario.creature("Hill Giant", "bob").zone is Zone.BATTLEFIELD  # 2 damage on a 3/3
    assert scenario.creature("Wall of Omens", "bob").zone is Zone.BATTLEFIELD


def test_nibelheim_aflame_keeps_the_hand_when_cast_from_hand() -> None:
    scenario = _scenario(["Serra Angel"], hand=["Nibelheim Aflame", "Island", "Island"])
    angel = scenario.creature("Serra Angel", "alice")
    _cast_all(scenario, "Nibelheim Aflame", targets=[angel])
    assert len(scenario.player("alice").hand) == 2


def test_cyclops_gladiator_trades_damage_with_a_defending_creature() -> None:
    scenario = _scenario(["Cyclops Gladiator"], ["Hill Giant"])
    scenario.will_take_the_may(True, source="Cyclops Gladiator")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.choose_trigger_targets("Cyclops Gladiator", [giant])
    (cyclops,) = _attack(scenario, "Cyclops Gladiator")
    _resolve_all(scenario)
    assert giant.zone is Zone.GRAVEYARD  # Cyclops Gladiator is a 4/4
    assert cyclops.zone is Zone.BATTLEFIELD  # it took 3 damage back (CR 608.2c)


def test_cyclops_gladiator_may_decline() -> None:
    scenario = _scenario(["Cyclops Gladiator"], ["Hill Giant"])
    scenario.will_take_the_may(False, source="Cyclops Gladiator")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.choose_trigger_targets("Cyclops Gladiator", [giant])
    _attack(scenario, "Cyclops Gladiator")
    _resolve_all(scenario)
    assert giant.zone is Zone.BATTLEFIELD


def test_friendly_fire_deals_the_revealed_mana_value_to_creature_and_controller() -> None:
    scenario = _scenario([], ["Serra Angel"], hand=["Friendly Fire"], bob_hand=["Hill Giant"])
    angel = scenario.creature("Serra Angel", "bob")
    _cast_all(scenario, "Friendly Fire", targets=[angel])
    assert angel.zone is Zone.GRAVEYARD  # 4 damage on a 4/4
    assert scenario.player("bob").life == 20 - 4


def test_friendly_fire_with_an_empty_hand_does_nothing() -> None:
    scenario = _scenario([], ["Serra Angel"], hand=["Friendly Fire"], bob_hand=[])
    angel = scenario.creature("Serra Angel", "bob")
    _cast_all(scenario, "Friendly Fire", targets=[angel])
    assert angel.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 20


def test_isildurs_fateful_strike_exiles_hand_cards_above_four() -> None:
    scenario = _scenario(
        ["Zur, Eternal Schemer"],
        ["Serra Angel"],
        hand=["Isildur's Fateful Strike"],
        bob_hand=["Island"] * 6,
    )
    angel = scenario.creature("Serra Angel", "bob")
    _cast_all(scenario, "Isildur's Fateful Strike", targets=[angel])
    assert angel.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == 4
    assert len(scenario.game.exile) == 2  # six cards, more than four by two


def test_isildurs_fateful_strike_leaves_a_four_card_hand_alone() -> None:
    scenario = _scenario(
        ["Zur, Eternal Schemer"],
        ["Serra Angel"],
        hand=["Isildur's Fateful Strike"],
        bob_hand=["Island"] * 4,
    )
    angel = scenario.creature("Serra Angel", "bob")
    _cast_all(scenario, "Isildur's Fateful Strike", targets=[angel])
    assert angel.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == 4
    assert not scenario.game.exile


def test_isildurs_fateful_strike_needs_a_legendary_creature_or_planeswalker() -> None:
    scenario = _scenario([], ["Serra Angel"], hand=["Isildur's Fateful Strike"])
    with pytest.raises(ValueError):
        scenario.cast_onto_stack(
            "Isildur's Fateful Strike",
            username="alice",
            targets=[scenario.creature("Serra Angel", "bob")],
            auto=True,
        )
