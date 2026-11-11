"""Scenario: T-109 S0, exalted and ripple cards credited by the keyword oracle.

CR 702.83a: exalted is "Whenever a creature you control attacks alone, that
creature gets +1/+1 until end of turn", and CR 702.83b: each instance triggers
separately. CR 702.60a: ripple N is "When you cast this spell, you may reveal
the top N cards of your library. You may cast spells with the same name as this
spell from among the revealed cards without paying their mana costs. Put all
revealed cards not cast this way on the bottom of your library in any order."
The machines for both existed (`machines/keywords._TRIGGER_EXPANSIONS`); the
support oracle (`keywords.executes`) did not list them, so every card printing
only the keyword reported silent. One test per card: the keyword plus whatever
else the card prints.

Rules cited here were checked with `mise run rules:find` in the writing session.
"""

import json
from pathlib import Path

import magic_cards_model
from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Card, Color
from magic_cards_model.support import card_support
from tests.scenarios.harness import Scenario

PRINTINGS = Path(magic_cards_model.__file__).parent / "data" / "printings"


def combat_board(alice, bob=(), hand=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice), hand=list(hand))
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def pt(scenario, state):
    return scenario.game.characteristics_of(state).power_toughness


def lone_attack(scenario, attacker):
    """Attack with this creature alone and let the exalted triggers resolve."""
    scenario.attack_with(attacker, defending="bob")
    resolve_everything(scenario)
    return pt(scenario, attacker)


def is_handled(name):
    slug = "".join(c if c.isalnum() else "_" for c in name.split("//")[0].strip().lower())
    card = Card.model_validate(json.loads((PRINTINGS / f"{slug.strip('_')}.json").read_text()))
    return card_support(card).status == "handled"


def exalted_self(name, base, *, extra=()):
    """The shared shape: `name` attacks alone and gets +1/+1 for its own exalted."""
    assert is_handled(name)
    scenario = combat_board([name, *extra])
    creature = scenario.creature(name)
    assert pt(scenario, creature) == base
    assert lone_attack(scenario, creature) == (base[0] + 1, base[1] + 1)
    return scenario, creature


def exalted_for_another(name, *, extra=(), hand=()):
    """The card is a noncreature: Grizzly Bears attacks alone and gets +1/+1."""
    assert is_handled(name)
    scenario = combat_board(["Grizzly Bears", name, *extra], hand=hand)
    bears = scenario.creature("Grizzly Bears")
    assert lone_attack(scenario, bears) == (3, 3)
    return scenario, bears


# -- exalted creatures with at most keywords printed ------------------------------


def test_aven_squire_exalted_and_flying():
    scenario, squire = exalted_self("Aven Squire", (1, 1))
    assert has_keyword(squire, "flying", scenario.game)


def test_akrasan_squire_exalted():
    exalted_self("Akrasan Squire", (1, 1))


def test_sigiled_behemoth_exalted():
    exalted_self("Sigiled Behemoth", (5, 4))


def test_servant_of_nefarox_exalted():
    exalted_self("Servant of Nefarox", (3, 1))


def test_ethercaste_knight_exalted():
    exalted_self("Ethercaste Knight", (1, 3))


def test_outrider_of_jhess_exalted():
    exalted_self("Outrider of Jhess", (2, 2))


def test_waveskimmer_aven_exalted_and_flying():
    scenario, aven = exalted_self("Waveskimmer Aven", (2, 4))
    assert has_keyword(aven, "flying", scenario.game)


def test_sigiled_paladin_exalted_and_first_strike():
    scenario, paladin = exalted_self("Sigiled Paladin", (2, 2))
    assert has_keyword(paladin, "first strike", scenario.game)


def test_rhox_charger_exalted_and_trample():
    scenario, charger = exalted_self("Rhox Charger", (3, 3))
    assert has_keyword(charger, "trample", scenario.game)


def test_court_archers_exalted_and_reach():
    scenario, archers = exalted_self("Court Archers", (1, 3))
    assert has_keyword(archers, "reach", scenario.game)


def test_goblin_champion_exalted_and_haste():
    scenario, champion = exalted_self("Goblin Champion", (0, 1))
    assert has_keyword(champion, "haste", scenario.game)


def test_duskmantle_prowler_exalted_and_haste():
    scenario, prowler = exalted_self("Duskmantle Prowler", (2, 2))
    assert has_keyword(prowler, "haste", scenario.game)


def test_knight_of_glory_exalted_and_protection_from_black():
    scenario, knight = exalted_self("Knight of Glory", (2, 1))
    assert scenario.game._effective_protection_qualities(knight)


def test_knight_of_infamy_exalted_and_protection_from_white():
    scenario, knight = exalted_self("Knight of Infamy", (2, 1))
    assert scenario.game._effective_protection_qualities(knight)


def test_guardians_of_akrasa_defender_cannot_attack_but_exalts_another():
    """Defender (CR 702.3b) keeps it home; its exalted still reaches the lone attacker."""
    scenario, _ = exalted_for_another("Guardians of Akrasa")
    guardians = scenario.creature("Guardians of Akrasa")
    assert has_keyword(guardians, "defender", scenario.game)
    assert pt(scenario, guardians) == (0, 4)


def test_two_exalted_creatures_stack_on_a_lone_attacker():
    """CR 702.83b: two instances of exalted trigger separately."""
    assert is_handled("Akrasan Squire") and is_handled("Ethercaste Knight")
    scenario = combat_board(["Akrasan Squire", "Ethercaste Knight"])
    squire = scenario.creature("Akrasan Squire")
    assert lone_attack(scenario, squire) == (3, 3)


# -- exalted creatures with a second ability -------------------------------------


# -- exalted creatures with a second ability -------------------------------------


def test_qasali_pridemage_exalted_and_sacrifice_to_destroy_an_artifact():
    scenario, pridemage = exalted_self("Qasali Pridemage", (2, 2))
    scenario = (
        Scenario()
        .player("alice", battlefield=["Qasali Pridemage", "Forest"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pridemage = scenario.creature("Qasali Pridemage")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.activate(pridemage, forest, targets=[ring], index=0)
    scenario.pass_until_resolved()
    assert pridemage.zone is Zone.GRAVEYARD, "sacrificed as part of the cost"
    assert ring.zone is Zone.GRAVEYARD


def test_dawnray_archer_exalted_and_pings_an_attacking_creature():
    assert is_handled("Dawnray Archer")
    scenario = combat_board(["Dawnray Archer", "Plains", "Grizzly Bears"])
    archer = scenario.creature("Dawnray Archer")
    bears = scenario.creature("Grizzly Bears")
    assert lone_attack(scenario, bears) == (3, 3)
    (plains,) = scenario.untapped_sources("Plains")
    scenario.activate(archer, plains, targets=[bears], index=0)
    scenario.pass_until_resolved()
    assert bears.damage == 1
    assert archer.tapped


def test_rhox_bodyguard_exalted_and_gains_three_life_on_entering():
    scenario, _ = exalted_self("Rhox Bodyguard", (2, 3))
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rhox Bodyguard"],
            battlefield=["Forest", "Forest", "Forest", "Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Plains", "Plains")
    scenario.cast_onto_stack("Rhox Bodyguard", *sources)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 23


def test_battlegrace_angel_exalted_and_grants_lifelink_to_the_lone_attacker():
    assert is_handled("Battlegrace Angel")
    scenario = combat_board(["Battlegrace Angel", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    assert not has_keyword(bears, "lifelink", scenario.game)
    assert lone_attack(scenario, bears) == (3, 3), "the Angel's one exalted instance"
    assert has_keyword(bears, "lifelink", scenario.game)


def test_duty_bound_dead_exalted_and_regenerates_for_three_and_black():
    exalted_self("Duty-Bound Dead", (0, 2))
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Supreme Verdict"], battlefield=["Plains", "Plains", "Plains", "Island"]
        )
        .player("bob", battlefield=["Duty-Bound Dead", "Swamp", "Swamp", "Swamp", "Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dead = scenario.creature("Duty-Bound Dead", "bob")
    mana = scenario.untapped_sources("Plains", "Plains", "Plains", "Island", username="alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="bob")
    scenario.cast_onto_stack("Supreme Verdict", *mana, username="alice")
    scenario.pass_priority()
    scenario.activate(dead, *swamps, index=0, username="bob")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert dead.zone is Zone.BATTLEFIELD
    assert dead.tapped


def test_ardent_plea_exalted_and_cascades_into_a_cheaper_spell():
    scenario, _ = exalted_for_another("Ardent Plea")
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ardent Plea"],
            battlefield=["Plains", "Island", "Island"],
            library=["Forest", "Grizzly Bears", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Island", "Island")
    scenario.cast_onto_stack("Ardent Plea", *sources)
    scenario.pass_until_resolved()
    while not scenario.game.stack_is_empty:
        scenario.pass_until_resolved()
    assert "Grizzly Bears" in scenario.battlefield_names()
    assert "Ardent Plea" in scenario.battlefield_names()


def test_cathedral_of_war_exalted_enters_tapped_and_taps_for_colorless():
    scenario, _ = exalted_for_another("Cathedral of War")
    scenario = Scenario().player("alice", hand=["Cathedral of War"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cathedral = scenario.play_land("Cathedral of War")
    assert cathedral.tapped
    cathedral.untap()
    scenario.activate(cathedral)
    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 1}


def test_angelic_benediction_exalted_and_taps_a_creature_when_one_attacks_alone():
    assert is_handled("Angelic Benediction")
    scenario = combat_board(["Grizzly Bears", "Angelic Benediction"], bob=["Hill Giant"])
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True)
    scenario.will_choose_targets(giant, times=None)
    assert lone_attack(scenario, bears) == (3, 3)
    assert giant.tapped


def test_noble_hierarch_exalted_and_taps_for_green_white_or_blue():
    scenario, _ = exalted_self("Noble Hierarch", (0, 1))
    for color in (Color.GREEN, Color.WHITE, Color.BLUE):
        scenario = Scenario().player("alice", battlefield=["Noble Hierarch"]).player("bob").build()
        scenario.start_at(Step.PRECOMBAT_MAIN)
        scenario.activate(scenario.creature("Noble Hierarch"), color=color)
        assert scenario.player("alice").mana_pool.floating == {color: 1}


def test_ignoble_hierarch_exalted_and_taps_for_black_red_or_green():
    scenario, _ = exalted_self("Ignoble Hierarch", (0, 1))
    for color in (Color.BLACK, Color.RED, Color.GREEN):
        scenario = (
            Scenario().player("alice", battlefield=["Ignoble Hierarch"]).player("bob").build()
        )
        scenario.start_at(Step.PRECOMBAT_MAIN)
        scenario.activate(scenario.creature("Ignoble Hierarch"), color=color)
        assert scenario.player("alice").mana_pool.floating == {color: 1}


def test_frontline_sage_exalted_and_loots_for_blue():
    scenario, _ = exalted_self("Frontline Sage", (0, 1))
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Frontline Sage", "Island"],
            hand=["Mountain"],
            library=["Forest", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sage = scenario.creature("Frontline Sage")
    (island,) = scenario.untapped_sources("Island")
    scenario.activate(sage, island, index=0)
    scenario.pass_until_resolved()
    hand = [state.name for state in scenario.player("alice").hand]
    assert len(hand) == 1, "drew one, discarded one"
    assert sage.tapped


def test_sublime_archangel_gives_other_creatures_exalted_so_they_stack():
    """CR 702.83b: the Archangel's own instance plus the granted one on the lone attacker."""
    assert is_handled("Sublime Archangel")
    scenario = combat_board(["Sublime Archangel", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    assert has_keyword(bears, "exalted", scenario.game)
    assert lone_attack(scenario, bears) == (4, 4), "Archangel's exalted plus the one it grants"
    scenario2 = combat_board(["Sublime Archangel", "Grizzly Bears"])
    archangel = scenario2.creature("Sublime Archangel")
    assert lone_attack(scenario2, archangel) == (6, 5), "its own plus the granted Bears' one"
    assert has_keyword(archangel, "flying", scenario2.game)


def test_rafiq_of_the_many_exalted_and_gives_the_lone_attacker_double_strike():
    assert is_handled("Rafiq of the Many")
    scenario = combat_board(["Rafiq of the Many", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears")
    assert lone_attack(scenario, bears) == (3, 3)
    assert has_keyword(bears, "double strike", scenario.game)


def test_giltspire_avenger_exalted_and_destroys_a_creature_that_hurt_you():
    scenario, _ = exalted_self("Giltspire Avenger", (2, 2))
    scenario = (
        Scenario()
        .player("alice", battlefield=["Giltspire Avenger"])
        .player("bob", battlefield=["Hill Giant", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    avenger = scenario.creature("Giltspire Avenger")
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.deal_damage(scenario.player("alice"), 3, source=giant)
    scenario.activate(avenger, targets=[giant])
    scenario.pass_until_resolved()
    assert giant.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD


def test_sighted_caste_sorcerer_exalted_and_gains_shroud_for_blue():
    scenario, _ = exalted_self("Sighted-Caste Sorcerer", (1, 1))
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sighted-Caste Sorcerer", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sorcerer = scenario.creature("Sighted-Caste Sorcerer")
    (island,) = scenario.untapped_sources("Island")
    assert not has_keyword(sorcerer, "shroud", scenario.game)
    scenario.activate(sorcerer, island, index=0)
    scenario.pass_until_resolved()
    assert has_keyword(sorcerer, "shroud", scenario.game)


# -- ripple 4 ---------------------------------------------------------------------

FILLER = ["Island", "Swamp", "Forest", "Plains"]


def ripple_board(hand, battlefield, library, bob_battlefield=(), bob_hand=()):
    scenario = (
        Scenario()
        .player("alice", hand=hand, battlefield=battlefield, library=library)
        .player(
            "bob", battlefield=list(bob_battlefield), hand=list(bob_hand), library=["Island"] * 4
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def settle(scenario):
    while not scenario.game.stack_is_empty:
        scenario.game.put_triggers_on_stack()
        scenario.resolve_top()


def test_surging_flame_ripple_casts_a_second_copy_for_free():
    assert is_handled("Surging Flame")
    scenario = ripple_board(
        ["Surging Flame"],
        ["Mountain", "Mountain"],
        ["Surging Flame", "Island", "Island", "Swamp", "Forest"],
    )
    scenario.will_choose_targets("bob", source="Surging Flame", times=None)
    sources = scenario.untapped_sources("Mountain", "Mountain")
    casting = scenario.cast("Surging Flame")
    casting.choose_targets(["bob"])
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    settle(scenario)
    names = [state.name for state in scenario.player("alice").graveyard]
    assert names.count("Surging Flame") == 2
    assert scenario.player("bob").life == 16, "2 damage from the cast one, 2 from the rippled one"
    assert [s.name for s in scenario.player("alice").library] == [
        "Forest",
        "Island",
        "Island",
        "Swamp",
    ]


def test_surging_aether_ripple_bounces_a_permanent_and_bottoms_the_rest():
    assert is_handled("Surging Aether")
    scenario = ripple_board(
        ["Surging Aether"],
        ["Island"] * 4,
        FILLER + ["Mountain"],
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*["Island"] * 4)
    scenario.cast_onto_stack("Surging Aether", *sources, targets=[bears])
    settle(scenario)
    assert bears.zone is Zone.HAND
    assert [s.name for s in scenario.player("alice").library][0] == "Mountain"
    assert [s.name for s in scenario.player("alice").graveyard] == ["Surging Aether"]


def test_surging_dementia_ripple_makes_the_target_player_discard():
    assert is_handled("Surging Dementia")
    scenario = ripple_board(
        ["Surging Dementia"], ["Swamp", "Swamp"], FILLER + ["Mountain"], bob_hand=["Forest"]
    )
    sources = scenario.untapped_sources("Swamp", "Swamp")
    scenario.cast_onto_stack("Surging Dementia", *sources, targets=["bob"])
    settle(scenario)
    assert [s.name for s in scenario.player("bob").graveyard] == ["Forest"]
    assert [s.name for s in scenario.player("alice").library][0] == "Mountain"


def test_surging_might_ripple_aura_gives_plus_two_plus_two():
    assert is_handled("Surging Might")
    scenario = ripple_board(
        ["Surging Might"],
        ["Forest", "Forest", "Forest", "Grizzly Bears"],
        FILLER + ["Mountain"],
    )
    bears = scenario.creature("Grizzly Bears")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_onto_stack("Surging Might", *sources, targets=[bears])
    settle(scenario)
    assert pt(scenario, bears) == (4, 4)
    assert [s.name for s in scenario.player("alice").library][0] == "Mountain"


def test_surging_sentinels_ripple_creature_with_first_strike_casts_its_twin():
    assert is_handled("Surging Sentinels")
    scenario = ripple_board(
        ["Surging Sentinels"],
        ["Plains", "Plains", "Plains"],
        ["Surging Sentinels", "Island", "Island", "Swamp", "Forest"],
    )
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_onto_stack("Surging Sentinels", *sources)
    settle(scenario)
    sentinels = scenario.creatures("Surging Sentinels", "Surging Sentinels")
    assert has_keyword(sentinels[0], "first strike", scenario.game)
    assert pt(scenario, sentinels[0]) == (2, 1)
