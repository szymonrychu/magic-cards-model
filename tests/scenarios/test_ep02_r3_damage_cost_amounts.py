"""EP-02-R3 T8: damage, pump and cost amounts - "+X/+X where X is ...", "deals damage
equal to ...", "costs {X} less ..." and the cards that grant, copy or cast from a
graveyard.

Rules, each looked up with `mise run rules:find` in the session that wrote this file:

- **CR 608.2h** - information about an object is taken once, as the effect applies.
- **CR 608.2c** - instructions are followed in order; later text refers to earlier text.
- **CR 107.3f** - X in the text of a spell or ability, not in a cost, is defined by that text.
- **CR 107.1b** - a calculation that yields a negative number uses zero instead.
- **CR 202.3** - mana value is the total amount of mana in the mana cost.
- **CR 119.3** - life gain and loss adjust a player's life total.
- **CR 122.1** - counters.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.support import HANDLED, card_support, classify_clauses
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
# Earthshaker Khenra, Gurgling Anointer ("mana value / power less than or equal to this creature's
# power"), Torrential Gearhulk, Daring Waverider ("you may cast target ... card from your graveyard
# without paying its mana cost. If that spell would be put into your graveyard, exile it instead"),
# Radical Idea (the "Jump" + "Jump-start" keyword pair) and Hands of Binding (cipher) are second
# printings of the readers below (Scryfall legalities checked 2026-10-14, none in the api decks).
# No other Modern/Pioneer/Standard card prints "cast up to two instant and/or sorcery spells with
# total mana value 6 or less", "draw a card. If you have nine or more cards in hand, flip", "when it
# deals excess damage this way, destroy", "deals damage equal to its power divided as you choose",
# "may sacrifice a nonland permanent ... or discard a card. Then ... deals damage" or "gains
# harmonize" (Scryfall oracle search): the listed card is the only printing of each.
PROOF: list[str] = [
    "Rubblebelt Rioters",
    "Hands of Binding",
    "Earthshaker Khenra",
    "Gurgling Anointer",
    "Torrential Gearhulk",
    "Daring Waverider",
    "Radical Idea",
]

LANDS = ["Plains"] * 6 + ["Swamp"] * 4 + ["Island"] * 4 + ["Forest"] * 3 + ["Mountain"] * 4


@pytest.mark.parametrize("name", LISTED + PROOF)
def test_every_clause_of_a_listed_card_is_handled(name: str) -> None:
    clauses = classify_clauses(card(name))
    assert clauses
    assert all(clause.category == HANDLED for clause in clauses), [
        (clause.text, clause.category) for clause in clauses if clause.category != HANDLED
    ]
    # The campaign's own oracle also judges every printed keyword.
    assert card_support(card(name)).status == "handled", [
        (c.text, c.status) for c in card_support(card(name)).clauses if c.status != "handled"
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
    exile: list[str] | None = None,
    step: Step = Step.PRECOMBAT_MAIN,
):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[*alice, *LANDS],
            hand=hand,
            graveyard=graveyard,
            exile=exile,
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


def test_flunk_with_a_full_hand_changes_nothing() -> None:
    scenario = _scenario(
        [],
        ["Serra Angel"],
        hand=["Flunk"],
        bob_hand=["Island"] * 8,
    )
    angel = scenario.creature("Serra Angel", "bob")
    _cast_all(scenario, "Flunk", targets=[angel])
    # 7 - 8 = -1: CR 107.1b uses zero, so the creature gets -0/-0
    assert _stats(scenario, angel) == (4, 4)


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


# ---------------------------------------------------------------------------
# Jump-start (CR 702.133a): Beacon Bolt
# ---------------------------------------------------------------------------


def test_beacon_bolt_counts_instants_and_sorceries_in_graveyard_and_exile() -> None:
    scenario = _scenario(
        [],
        ["Hill Giant"],
        hand=["Island"],
        graveyard=["Beacon Bolt", "Lightning Bolt", "Grizzly Bears"],
        exile=["Think Twice", "Divination"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    island = scenario.find("Island", Zone.HAND, "alice")
    beacon = scenario.find("Beacon Bolt", Zone.GRAVEYARD, "alice")
    casting = scenario.cast("Beacon Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Jump-start", choosing=[island])
    casting.choose_targets([giant])
    scenario.auto_pay(casting.begin_paying())
    scenario.put_on_stack(casting)
    _resolve_all(scenario)
    assert island.zone is Zone.GRAVEYARD  # the discard
    assert beacon.zone is Zone.EXILE  # CR 702.133a
    assert giant.zone is Zone.GRAVEYARD  # Lightning Bolt + Think Twice + Divination = 3


def test_beacon_bolt_does_not_count_creatures_or_the_spell_itself() -> None:
    scenario = _scenario(
        [],
        ["Hill Giant"],
        hand=["Island"],
        graveyard=["Beacon Bolt", "Lightning Bolt", "Grizzly Bears"],
        exile=["Think Twice"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    island = scenario.find("Island", Zone.HAND, "alice")
    casting = scenario.cast("Beacon Bolt", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Jump-start", choosing=[island])
    casting.choose_targets([giant])
    scenario.auto_pay(casting.begin_paying())
    scenario.put_on_stack(casting)
    _resolve_all(scenario)
    assert giant.zone is Zone.BATTLEFIELD  # only 2 damage on a 3/3


# ---------------------------------------------------------------------------
# Free casts from the graveyard: Dreadhorde Arcanist, Arcane Proxy, Invoke Calamity
# ---------------------------------------------------------------------------


def _life(scenario, user: str) -> int:
    return scenario.player(user).life


def test_dreadhorde_arcanist_casts_a_cheap_graveyard_spell_free_and_exiles_it() -> None:
    scenario = _scenario(
        ["Dreadhorde Arcanist"], graveyard=["Lightning Bolt"], step=Step.BEGINNING_OF_COMBAT
    )
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Dreadhorde Arcanist", [bolt])
    scenario.will_take_the_may(True, source="Dreadhorde Arcanist")
    scenario.will_choose_targets("bob")
    _attack(scenario, "Dreadhorde Arcanist")
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 17
    assert bolt.zone is Zone.EXILE  # "exile it instead" (CR 614.1a)


def test_dreadhorde_arcanist_may_decline() -> None:
    scenario = _scenario(
        ["Dreadhorde Arcanist"], graveyard=["Lightning Bolt"], step=Step.BEGINNING_OF_COMBAT
    )
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Dreadhorde Arcanist", [bolt])
    scenario.will_take_the_may(False, source="Dreadhorde Arcanist")
    _attack(scenario, "Dreadhorde Arcanist")
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 20
    assert bolt.zone is Zone.GRAVEYARD


def test_dreadhorde_arcanist_cannot_target_a_spell_above_its_power() -> None:
    scenario = _scenario(
        ["Dreadhorde Arcanist"], graveyard=["Think Twice"], step=Step.BEGINNING_OF_COMBAT
    )
    think = scenario.find("Think Twice", Zone.GRAVEYARD, "alice")
    hand = len(scenario.player("alice").hand)
    _attack(scenario, "Dreadhorde Arcanist")
    _resolve_all(scenario)
    assert think.zone is Zone.GRAVEYARD  # mana value 2 > power 1
    assert len(scenario.player("alice").hand) == hand


def test_dreadhorde_arcanist_reads_its_power_as_it_attacks() -> None:
    scenario = _scenario(
        ["Dreadhorde Arcanist"], graveyard=["Think Twice"], step=Step.BEGINNING_OF_COMBAT
    )
    arcanist = scenario.creature("Dreadhorde Arcanist", "alice")
    arcanist.add_counters("+1/+1", 1)
    think = scenario.find("Think Twice", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Dreadhorde Arcanist", [think])
    scenario.will_take_the_may(True, source="Dreadhorde Arcanist")
    hand = len(scenario.player("alice").hand)
    _attack(scenario, "Dreadhorde Arcanist")
    _resolve_all(scenario)
    assert think.zone is Zone.EXILE
    assert len(scenario.player("alice").hand) == hand + 1


def _cast_proxy(scenario, *, prototyped: bool):
    casting = scenario.cast("Arcane Proxy")
    if prototyped:
        casting.use_keyword("Prototype")
    scenario.auto_pay(casting.begin_paying())
    scenario.put_on_stack(casting)


def test_arcane_proxy_copies_a_graveyard_spell_and_casts_the_copy_free() -> None:
    scenario = _scenario([], hand=["Arcane Proxy"], graveyard=["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(bolt)  # the trigger's target, asked once Proxy has entered
    scenario.will_take_the_may(True, source="Arcane Proxy")
    scenario.will_choose_targets("bob")
    _cast_proxy(scenario, prototyped=True)
    _resolve_all(scenario)
    assert _life(scenario, "bob") == 17
    assert bolt.zone is Zone.EXILE  # the card is exiled as the copy is made


def test_arcane_proxy_uses_the_prototyped_power() -> None:
    scenario = _scenario([], hand=["Arcane Proxy"], graveyard=["Divination"])
    divination = scenario.find("Divination", Zone.GRAVEYARD, "alice")
    _cast_proxy(scenario, prototyped=True)
    _resolve_all(scenario)
    assert divination.zone is Zone.GRAVEYARD  # mana value 3 > prototyped power 2


def test_arcane_proxy_cast_for_its_full_cost_copies_a_bigger_spell() -> None:
    scenario = _scenario([], hand=["Arcane Proxy"], graveyard=["Divination"])
    divination = scenario.find("Divination", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(divination)
    scenario.will_take_the_may(True, source="Arcane Proxy")
    hand = len(scenario.player("alice").hand)
    _cast_proxy(scenario, prototyped=False)
    _resolve_all(scenario)
    assert divination.zone is Zone.EXILE
    assert len(scenario.player("alice").hand) == hand - 1 + 2  # the Proxy left, two drawn


def test_arcane_proxy_does_nothing_when_not_cast() -> None:
    scenario = _scenario([], hand=["Arcane Proxy"], graveyard=["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.put_onto_battlefield("Arcane Proxy")
    _resolve_all(scenario)
    assert bolt.zone is Zone.GRAVEYARD  # CR 603.4: "if you cast it" was false


def _calamity(scenario, *chosen):
    scenario.will_choose_cards(*chosen)
    _cast_all(scenario, "Invoke Calamity")


def test_invoke_calamity_casts_two_spells_from_hand_and_graveyard_free() -> None:
    scenario = _scenario(
        [], hand=["Invoke Calamity", "Think Twice"], graveyard=["Lightning Bolt", "Divination"]
    )
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    think = scenario.find("Think Twice", Zone.HAND, "alice")
    scenario.will_take_the_may(True, source="Invoke Calamity")
    scenario.will_choose_targets("bob")
    scenario.will_choose_cards(bolt)
    _calamity(scenario, think)
    assert _life(scenario, "bob") == 17
    assert bolt.zone is Zone.EXILE and think.zone is Zone.EXILE  # exiled, not the graveyard
    calamity = scenario.find("Invoke Calamity", Zone.EXILE, "alice")
    assert calamity.zone is Zone.EXILE


def test_invoke_calamity_total_mana_value_is_at_most_six() -> None:
    scenario = _scenario(
        [], hand=["Invoke Calamity"], graveyard=["Day of Judgment", "Divination", "Think Twice"]
    )
    judgment = scenario.find("Day of Judgment", Zone.GRAVEYARD, "alice")
    divination = scenario.find("Divination", Zone.GRAVEYARD, "alice")
    think = scenario.find("Think Twice", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may(True, source="Invoke Calamity")
    # Day of Judgment (4) + Divination (3) is 7: the second pick may only be Think Twice.
    scenario.will_choose_cards(judgment)
    scenario.will_choose_cards(think)
    _cast_all(scenario, "Invoke Calamity")
    assert judgment.zone is Zone.EXILE and think.zone is Zone.EXILE
    assert divination.zone is Zone.GRAVEYARD


def test_invoke_calamity_may_cast_none() -> None:
    scenario = _scenario([], hand=["Invoke Calamity"], graveyard=["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.will_choose_cards()
    _cast_all(scenario, "Invoke Calamity")
    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.find("Invoke Calamity", Zone.EXILE, "alice").zone is Zone.EXILE


# ---------------------------------------------------------------------------
# Excess damage (CR 120.10) with a reflexive trigger (CR 603.12): Unleash the Inferno
# ---------------------------------------------------------------------------


def test_unleash_the_inferno_destroys_an_artifact_up_to_the_excess() -> None:
    scenario = _scenario(
        [], ["Hill Giant", "Chromatic Lantern", "Worship"], hand=["Unleash the Inferno"]
    )
    giant = scenario.creature("Hill Giant", "bob")
    lantern = scenario.find("Chromatic Lantern", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_targets(lantern)  # the reflexive trigger's target
    _cast_all(scenario, "Unleash the Inferno", targets=[giant])
    assert giant.zone is Zone.GRAVEYARD
    assert lantern.zone is Zone.GRAVEYARD  # mana value 3 <= 7 - 3 = 4 excess


def test_unleash_the_inferno_cannot_reach_a_permanent_above_the_excess() -> None:
    scenario = _scenario([], ["Serra Angel", "Worship"], hand=["Unleash the Inferno"])
    angel = scenario.creature("Serra Angel", "bob")
    worship = scenario.find("Worship", Zone.BATTLEFIELD, "bob")
    _cast_all(scenario, "Unleash the Inferno", targets=[angel])
    assert angel.zone is Zone.GRAVEYARD
    assert worship.zone is Zone.BATTLEFIELD  # mana value 4 > 7 - 4 = 3 excess


def test_unleash_the_inferno_without_excess_makes_no_trigger() -> None:
    scenario = _scenario([], ["Darksteel Colossus", "Sol Ring"], hand=["Unleash the Inferno"])
    colossus = scenario.creature("Darksteel Colossus", "bob")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    _cast_all(scenario, "Unleash the Inferno", targets=[colossus])
    assert colossus.damage == 7
    assert ring.zone is Zone.BATTLEFIELD  # 7 damage on an 11-toughness creature: no excess


def test_unleash_the_inferno_counts_damage_already_marked() -> None:
    scenario = _scenario([], ["Serra Angel", "Sol Ring"], hand=["Unleash the Inferno"])
    angel = scenario.creature("Serra Angel", "bob")
    angel.damage = 3  # only 1 more damage is lethal: 6 are excess
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_targets(ring)
    _cast_all(scenario, "Unleash the Inferno", targets=[angel])
    assert ring.zone is Zone.GRAVEYARD


# ---------------------------------------------------------------------------
# Divided damage equal to power (CR 601.2d) with a retaliation: Living Inferno
# ---------------------------------------------------------------------------


def _inferno(scenario):
    inferno = scenario.creature("Living Inferno", "alice")
    inferno.summoning_sick = False
    return inferno


def test_living_inferno_divides_its_power_and_each_target_hits_back() -> None:
    scenario = _scenario(["Living Inferno"], ["Grizzly Bears", "Wall of Omens"])
    inferno = _inferno(scenario)
    bears, wall = (
        scenario.creature("Grizzly Bears", "bob"),
        scenario.creature("Wall of Omens", "bob"),
    )
    _activate_all(scenario, inferno, targets=[bears, wall], division=[4, 4])  # power 8
    assert bears.zone is Zone.GRAVEYARD and wall.zone is Zone.GRAVEYARD
    assert inferno.damage == 2  # Grizzly Bears 2 + Wall of Omens 0


def test_living_inferno_divides_unevenly_as_announced() -> None:
    scenario = _scenario(["Living Inferno"], ["Hill Giant", "Wall of Omens"])
    inferno = _inferno(scenario)
    giant, wall = scenario.creature("Hill Giant", "bob"), scenario.creature("Wall of Omens", "bob")
    _activate_all(scenario, inferno, targets=[giant, wall], division=[2, 6])
    assert giant.zone is Zone.BATTLEFIELD  # 2 damage on a 3/3
    assert wall.zone is Zone.GRAVEYARD  # 6 damage on a 0/4
    assert inferno.damage == 3  # the surviving Hill Giant hits back for its power


def test_living_inferno_division_must_use_all_of_its_power() -> None:
    scenario = _scenario(["Living Inferno"], ["Grizzly Bears"])
    inferno = _inferno(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    with pytest.raises(ValueError):
        scenario.activate(inferno, targets=[bears], division=[7], auto=True)  # power is 8


def test_living_inferno_reads_its_power_as_the_division_is_announced() -> None:
    scenario = _scenario(["Living Inferno"], ["Grizzly Bears"])
    inferno = _inferno(scenario)
    inferno.add_counters("+1/+1", 1)
    bears = scenario.creature("Grizzly Bears", "bob")
    _activate_all(scenario, inferno, targets=[bears], division=[9])
    assert bears.zone is Zone.GRAVEYARD


def test_living_inferno_may_have_no_targets() -> None:
    scenario = _scenario(["Living Inferno"], ["Grizzly Bears"])
    inferno = _inferno(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    _activate_all(scenario, inferno, targets=[])
    assert bears.zone is Zone.BATTLEFIELD and inferno.damage == 0


# ---------------------------------------------------------------------------
# "Each opponent may sacrifice or discard. Then damage to each who did neither":
# Osseous Sticktwister (delirium, CR 207.2c ability word)
# ---------------------------------------------------------------------------

FOUR_TYPES = ["Lightning Bolt", "Grizzly Bears", "Sol Ring", "Plains"]


def _to_end_step(scenario) -> None:
    while True:
        while scenario.game.stack:
            scenario.pass_until_resolved()
        if scenario.step is Step.END_STEP:
            return
        scenario.advance()


def test_osseous_sticktwister_damages_an_opponent_who_does_neither() -> None:
    scenario = _scenario(["Osseous Sticktwister"], graveyard=FOUR_TYPES, bob_hand=["Island"])
    scenario.will_choose("neither")
    _to_end_step(scenario)
    assert scenario.player("bob").life == 20 - 2
    assert scenario.player("alice").life == 20 + 2  # lifelink on the damage it dealt


def test_osseous_sticktwister_lets_an_opponent_discard_instead() -> None:
    scenario = _scenario(["Osseous Sticktwister"], graveyard=FOUR_TYPES, bob_hand=["Island"])
    island = scenario.find("Island", Zone.HAND, "bob")
    scenario.will_choose("discard a card")
    scenario.will_choose_cards(island)
    _to_end_step(scenario)
    assert island.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_osseous_sticktwister_lets_an_opponent_sacrifice_instead() -> None:
    scenario = _scenario(["Osseous Sticktwister"], ["Hill Giant"], graveyard=FOUR_TYPES)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_choose("sacrifice a nonland permanent")
    scenario.will_choose_cards(giant)
    _to_end_step(scenario)
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_osseous_sticktwister_needs_four_card_types_in_the_graveyard() -> None:
    scenario = _scenario(["Osseous Sticktwister"], graveyard=FOUR_TYPES[:3], bob_hand=["Island"])
    _to_end_step(scenario)
    assert scenario.player("bob").life == 20
    assert len(scenario.player("bob").hand) == 1  # nothing was asked


def test_osseous_sticktwister_damages_an_opponent_with_nothing_to_give() -> None:
    scenario = _scenario(["Osseous Sticktwister"], graveyard=FOUR_TYPES)
    _to_end_step(scenario)  # bob has only lands and no hand: no choice to offer
    assert scenario.player("bob").life == 20 - 2


# ---------------------------------------------------------------------------
# "Draw a card. If you have nine or more cards in hand, flip this creature":
# Jushi Apprentice // Tomoya the Revealer (CR 710)
# ---------------------------------------------------------------------------

JUSHI = "Jushi Apprentice // Tomoya the Revealer"


def _jushi_board(hand_size: int):
    scenario = _scenario([JUSHI], hand=["Island"] * hand_size)
    jushi = scenario.creature("Jushi Apprentice", "alice")
    jushi.summoning_sick = False
    return scenario, jushi


def test_jushi_apprentice_flips_when_the_draw_makes_nine_cards() -> None:
    scenario, jushi = _jushi_board(8)
    _activate_all(scenario, jushi)
    assert len(scenario.player("alice").hand) == 9
    assert jushi.flipped and jushi.name == "Tomoya the Revealer"


def test_jushi_apprentice_stays_unflipped_below_nine_cards() -> None:
    scenario, jushi = _jushi_board(7)
    _activate_all(scenario, jushi)
    assert len(scenario.player("alice").hand) == 8
    assert not jushi.flipped


def test_jushi_apprentice_counts_the_hand_after_the_draw() -> None:
    scenario, jushi = _jushi_board(9)  # already nine, ten after the draw
    _activate_all(scenario, jushi)
    assert jushi.flipped


def test_tomoya_the_revealer_draws_as_many_cards_as_the_controllers_hand() -> None:
    scenario, jushi = _jushi_board(3)
    jushi.flip()
    target_hand = len(scenario.player("bob").hand)
    _activate_all(scenario, jushi, targets=["bob"])
    assert len(scenario.player("bob").hand) == target_hand + 3  # the caster's hand, not bob's


# ---------------------------------------------------------------------------
# A granted harmonize (CR 702.180): Songcrafter Mage
# ---------------------------------------------------------------------------


def _songcrafter_grants(graveyard: list[str], target: str | None = "Think Twice", extra=None):
    scenario = _scenario(extra or [], hand=["Songcrafter Mage"], graveyard=graveyard)
    if target is not None:
        scenario.choose_trigger_targets(
            "Songcrafter Mage", [scenario.find(target, Zone.GRAVEYARD, "alice")]
        )
    _cast_all(scenario, "Songcrafter Mage")
    return scenario


def _harmonize_cast(scenario, name: str, creature=None) -> int:
    """Cast `name` from the graveyard with the granted harmonize; the lands tapped to pay."""
    before = _tapped_lands(scenario)
    casting = scenario.cast(name, from_zone=Zone.GRAVEYARD)
    casting.use_permission()
    if creature is not None:
        casting.pay_harmonize(creature)
    scenario.auto_pay(casting.begin_paying())
    scenario.put_on_stack(casting)
    paid = _tapped_lands(scenario) - before
    _resolve_all(scenario)
    return paid


def test_a_permission_can_be_a_granted_harmonize() -> None:
    from magic_cards_model.machines.casting import PlayPermission

    assert "harmonize" in PlayPermission.model_fields


def test_songcrafter_mage_grants_harmonize_at_the_mana_cost() -> None:
    scenario = _songcrafter_grants(["Think Twice"])
    think = scenario.find("Think Twice", Zone.GRAVEYARD, "alice")
    # {G}{U}{R} for the Mage itself is spent: only the graveyard cast is measured now.
    assert _harmonize_cast(scenario, "Think Twice") == 2  # {1}{U}
    assert think.zone is Zone.EXILE  # CR 702.180a: exiled instead of the graveyard


def test_songcrafter_mage_harmonize_taps_a_creature_to_pay_its_power_in_generic() -> None:
    scenario = _songcrafter_grants(["Think Twice"], extra=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "alice")
    think = scenario.find("Think Twice", Zone.GRAVEYARD, "alice")
    paid = _harmonize_cast(scenario, "Think Twice", creature=giant)
    assert paid == 1  # {1}{U} less Hill Giant's power of 3 generic leaves {U}
    assert giant.tapped
    assert think.zone is Zone.EXILE


def test_songcrafter_mage_grants_nothing_to_a_creature_card() -> None:
    scenario = _songcrafter_grants(["Grizzly Bears"], target=None)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert scenario.game.play_permission_for(bears, "alice") is None


def test_a_card_without_the_grant_cannot_be_harmonized() -> None:
    scenario = _scenario([], graveyard=["Think Twice"])
    with pytest.raises(ValueError):
        casting = scenario.cast("Think Twice", from_zone=Zone.GRAVEYARD)
        casting.pay_harmonize(None)


# ---------------------------------------------------------------------------
# Cipher (CR 702.99): Whispering Madness, with Hands of Binding as the second printing
# ---------------------------------------------------------------------------


def _hands_encoded(*, bob=("Hill Giant",)):
    """Hands of Binding resolved onto Grizzly Bears, encoded."""
    scenario = _scenario(["Grizzly Bears"], list(bob), hand=["Hands of Binding"])
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True, source="Hands of Binding")
    scenario.will_choose_cards(bears)
    _cast_all(scenario, "Hands of Binding", targets=[giant])
    return scenario, bears, giant


def test_cipher_exiles_the_resolved_spell_encoded_on_a_creature() -> None:
    scenario, bears, giant = _hands_encoded()
    hands = scenario.find("Hands of Binding", Zone.EXILE, "alice")
    assert hands.zone is Zone.EXILE
    assert giant.tapped  # the spell's own text resolved first (CR 608.2c)


def test_cipher_may_be_declined_and_the_card_goes_to_the_graveyard() -> None:
    scenario = _scenario(["Grizzly Bears"], ["Hill Giant"], hand=["Hands of Binding"])
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(False, source="Hands of Binding")
    _cast_all(scenario, "Hands of Binding", targets=[giant])
    assert scenario.find("Hands of Binding", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_cipher_needs_a_creature_to_encode_onto() -> None:
    scenario = _scenario([], ["Hill Giant"], hand=["Hands of Binding"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast_all(scenario, "Hands of Binding", targets=[giant])  # no question is asked
    assert scenario.find("Hands of Binding", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def _hit_bob_with(scenario, bears):
    scenario.advance()  # declare attackers
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()


def test_cipher_casts_a_copy_free_when_the_encoded_creature_hits_a_player() -> None:
    scenario, bears, _giant = _hands_encoded(bob=("Hill Giant", "Serra Angel"))
    bears.summoning_sick = False
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.will_take_the_may(True, source="Hands of Binding")
    scenario.will_choose_targets(angel)
    _hit_bob_with(scenario, bears)
    _resolve_all(scenario)
    assert scenario.player("bob").life == 20 - 2
    assert angel.tapped  # the copy was cast without paying {1}{U}
    exiled = [c for c in scenario.game.exile if c.name == "Hands of Binding"]
    assert len(exiled) == 1 and not exiled[0].is_copy  # the card stays encoded; no copy lingers


def test_cipher_does_not_trigger_when_the_creature_is_blocked() -> None:
    scenario, bears, giant = _hands_encoded()
    bears.summoning_sick = False
    giant.tapped = False
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.advance()
    scenario.attack_with(bears)
    scenario.block(bears, giant)
    scenario.combat_damage()
    _resolve_all(scenario)
    assert scenario.player("bob").life == 20


def test_cipher_is_lost_when_the_encoded_creature_leaves_the_battlefield() -> None:
    scenario, bears, _giant = _hands_encoded(bob=("Hill Giant", "Serra Angel"))
    scenario.game.return_to_hand(bears)
    scenario.put_onto_battlefield("Grizzly Bears")  # a new object (CR 400.7)
    again = scenario.creature("Grizzly Bears", "alice")
    again.summoning_sick = False
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    _hit_bob_with(scenario, again)
    _resolve_all(scenario)
    assert scenario.player("bob").life == 20 - 2  # combat damage only: no free copy was offered


def test_whispering_madness_discards_every_hand_and_draws_the_greatest() -> None:
    scenario = _scenario(
        [],
        hand=["Whispering Madness", "Island"],
        bob_hand=["Island", "Island", "Island"],
        library=["Mountain"] * 12,
    )
    _cast_all(scenario, "Whispering Madness")
    assert len(scenario.player("alice").hand) == 3  # one discarded, three drawn
    assert len(scenario.player("bob").hand) == 3  # three discarded, three drawn


def test_whispering_madness_may_be_encoded_on_a_creature_you_control() -> None:
    scenario = _scenario(["Grizzly Bears"], hand=["Whispering Madness"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_take_the_may(True, source="Whispering Madness")
    scenario.will_choose_cards(bears)
    _cast_all(scenario, "Whispering Madness")
    assert scenario.find("Whispering Madness", Zone.EXILE, "alice").zone is Zone.EXILE


# ---------------------------------------------------------------------------
# Second printings: "less than or equal to this creature's power", the free cast from the
# graveyard, and jump-start's Scryfall keyword pair
# ---------------------------------------------------------------------------


def test_earthshaker_khenra_targets_a_creature_with_power_up_to_its_own() -> None:
    scenario = _scenario([], ["Grizzly Bears", "Hill Giant"], hand=["Earthshaker Khenra"])
    bears, giant = scenario.creature("Grizzly Bears", "bob"), scenario.creature("Hill Giant", "bob")
    scenario.will_choose_targets(giant)  # power 3 > the Khenra's 2
    with pytest.raises(ValueError):
        _cast_all(scenario, "Earthshaker Khenra")
    scenario = _scenario([], ["Grizzly Bears", "Hill Giant"], hand=["Earthshaker Khenra"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears)  # power 2 is equal: legal (CR 601.2c)
    _cast_all(scenario, "Earthshaker Khenra")
    assert scenario.find("Earthshaker Khenra", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD


def test_gurgling_anointer_returns_a_creature_card_up_to_its_last_known_power() -> None:
    scenario = _scenario(
        ["Gurgling Anointer"], graveyard=["Grizzly Bears", "Serra Angel"], step=Step.PRECOMBAT_MAIN
    )
    anointer = scenario.creature("Gurgling Anointer", "alice")
    anointer.add_counters("+1/+1", 1)  # power 2
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(bears)
    scenario.game.destroy(anointer)
    _resolve_all(scenario)
    assert bears.zone is Zone.BATTLEFIELD  # mana value 2 <= power 2
    assert scenario.find("Serra Angel", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_torrential_gearhulk_casts_an_instant_free_and_exiles_it() -> None:
    scenario = _scenario([], hand=["Torrential Gearhulk"], graveyard=["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Torrential Gearhulk", [bolt])
    scenario.will_take_the_may(True, source="Torrential Gearhulk")
    scenario.will_choose_targets("bob")
    _cast_all(scenario, "Torrential Gearhulk")
    assert _life(scenario, "bob") == 17
    assert bolt.zone is Zone.EXILE


def test_daring_waverider_casts_a_spell_of_mana_value_four_or_less_free() -> None:
    scenario = _scenario([], hand=["Daring Waverider"], graveyard=["Divination", "Day of Judgment"])
    divination = scenario.find("Divination", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Daring Waverider", [divination])
    scenario.will_take_the_may(True, source="Daring Waverider")
    hand = len(scenario.player("alice").hand)
    _cast_all(scenario, "Daring Waverider")
    assert divination.zone is Zone.EXILE
    assert len(scenario.player("alice").hand) == hand - 1 + 2  # the Waverider left, two drawn


def test_radical_idea_is_cast_with_jump_start() -> None:
    scenario = _scenario([], hand=["Island"], graveyard=["Radical Idea"])
    island = scenario.find("Island", Zone.HAND, "alice")
    radical = scenario.find("Radical Idea", Zone.GRAVEYARD, "alice")
    casting = scenario.cast("Radical Idea", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Jump-start", choosing=[island])
    scenario.auto_pay(casting.begin_paying())
    scenario.put_on_stack(casting)
    _resolve_all(scenario)
    assert island.zone is Zone.GRAVEYARD and radical.zone is Zone.EXILE
    assert len(scenario.player("alice").hand) == 1  # drew a card


# ---------------------------------------------------------------------------
# Porcuparrot: "X damage ..., where X is the number of times this creature has mutated"
# (CR 702.140c: each spell merged into it is one mutation)
# ---------------------------------------------------------------------------


def _mutate_onto(scenario, name: str, target) -> None:
    casting = scenario.cast(name)
    casting.use_keyword("Mutate")
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    scenario.will_choose_top(False, username="alice")  # under: Porcuparrot stays on top
    scenario.resolve_top()


def test_porcuparrot_deals_damage_equal_to_the_times_it_has_mutated() -> None:
    scenario = _scenario(["Porcuparrot"], hand=["Gemrazer", "Brokkos, Apex of Forever"])
    parrot = scenario.creature("Porcuparrot", "alice")
    _mutate_onto(scenario, "Gemrazer", parrot)
    _activate_all(scenario, parrot, targets=["bob"])
    assert scenario.player("bob").life == 20 - 1
    for permanent in scenario.game.battlefield:
        permanent.untap(exert_applies=False)
    _mutate_onto(scenario, "Brokkos, Apex of Forever", parrot)
    _activate_all(scenario, parrot, targets=["bob"])
    assert scenario.player("bob").life == 20 - 1 - 2


def test_porcuparrot_that_never_mutated_deals_no_damage() -> None:
    scenario = _scenario(["Porcuparrot"])
    parrot = scenario.creature("Porcuparrot", "alice")
    _activate_all(scenario, parrot, targets=["bob"])
    assert scenario.player("bob").life == 20
