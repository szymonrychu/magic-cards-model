"""Scenario: a permanent's static ability gives the spells its controller casts
a keyword - "Assassin spells you cast have freerunning {B}{B}." (Ezio Auditore
da Firenze), "Each legendary spell you cast that's one or more colors has
web-slinging {G}{W}{U}." (Peter Parker), "Artifact creature spells you cast
have affinity for artifacts." (Mycosynth Golem), "Enchantment spells you cast
have affinity for Auras." (Pearl-Ear, Imperial Advisor), "Instant and sorcery
spells you control have rebound." (Cast Through Time), "Spells you cast from
exile have convoke." (Hoarding Broodlord), "Spells you cast have ripple 4."
(Thrumming Stone).

CR 611.3d / CR 613.1f: the grant applies to the spell as it is cast and goes
through the machine of the printed keyword (CR 702.173a, CR 702.188a,
CR 702.41a, CR 702.88a, CR 702.51a, CR 702.60a).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board(alice, bob=None, hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), hand=list(hand), library=["Island"] * 6)
        .player("bob", battlefield=list(bob or []), library=["Island"] * 6)
        .build()
    )
    for state in scenario.game.battlefield:
        state.summoning_sick = False
    return scenario


def hit_bob_with(scenario, *attackers):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()
    scenario.start_at(Step.POSTCOMBAT_MAIN)


# -- freerunning (CR 702.173a) -----------------------------------------------


def test_ezio_gives_assassin_spells_freerunning_once_an_assassin_connected():
    scenario = board(["Ezio Auditore da Firenze", "Swamp", "Swamp", "Mountain"], hand=["Ezio Auditore da Firenze"])
    ezio = scenario.creature("Ezio Auditore da Firenze")
    second = scenario.find("Ezio Auditore da Firenze", Zone.HAND, "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    with pytest.raises(ValueError, match="(?i)freerunning"):
        scenario.game.cast(
            second, "alice", keyword="freerunning", mana_sources=scenario.untapped_sources("Swamp", "Mountain")
        )

    hit_bob_with(scenario, ezio)
    swamps = scenario.untapped_sources("Swamp", "Swamp")
    scenario.game.cast(second, "alice", keyword="freerunning", mana_sources=swamps)

    assert second.zone is Zone.STACK
    assert all(swamp.tapped for swamp in swamps)


def test_freerunning_is_only_for_assassin_spells():
    scenario = board(
        ["Ezio Auditore da Firenze", "Swamp", "Swamp", "Mountain"], hand=["Kalain, Reclusive Painter"]
    )
    ezio = scenario.creature("Ezio Auditore da Firenze")
    kalain = scenario.find("Kalain, Reclusive Painter", Zone.HAND, "alice")
    hit_bob_with(scenario, ezio)

    with pytest.raises(ValueError):
        scenario.game.cast(
            kalain, "alice", keyword="freerunning", mana_sources=scenario.untapped_sources("Swamp", "Swamp")
        )


def test_freerunning_needs_an_assassin_that_connected_not_just_any_attacker():
    scenario = board(
        ["Grizzly Bears", "Ezio Auditore da Firenze", "Swamp", "Swamp", "Mountain"],
        hand=["Ezio Auditore da Firenze"],
    )
    bears = scenario.creature("Grizzly Bears")
    hit_bob_with(scenario, bears)
    second = scenario.find("Ezio Auditore da Firenze", Zone.HAND, "alice")

    with pytest.raises(ValueError, match="(?i)freerunning"):
        scenario.game.cast(
            second, "alice", keyword="freerunning", mana_sources=scenario.untapped_sources("Swamp", "Swamp")
        )


def test_freerunning_grant_ends_when_ezio_leaves():
    scenario = board(
        ["Ezio Auditore da Firenze", "Swamp", "Swamp", "Mountain"], hand=["Ezio Auditore da Firenze"]
    )
    ezio = scenario.creature("Ezio Auditore da Firenze")
    hit_bob_with(scenario, ezio)
    scenario.game.put_into_graveyard(ezio)
    second = scenario.find("Ezio Auditore da Firenze", Zone.HAND, "alice")

    with pytest.raises(ValueError):
        scenario.game.cast(
            second, "alice", keyword="freerunning", mana_sources=scenario.untapped_sources("Swamp", "Swamp")
        )


# -- web-slinging (CR 702.188a) ----------------------------------------------


def amazing_spider_man(scenario):
    """Peter Parker's back face, which is the one that grants web-slinging."""
    peter = scenario.find("Peter Parker", Zone.HAND, "alice")
    return scenario.game.put_onto_battlefield(peter, "alice", transformed=True)


def test_peter_parker_gives_a_colored_legendary_spell_web_slinging():
    scenario = board(
        ["Grizzly Bears", "Forest", "Plains", "Island"],
        hand=["Kalain, Reclusive Painter", "Peter Parker"],
    )
    amazing_spider_man(scenario)
    bears = scenario.creature("Grizzly Bears")
    kalain = scenario.find("Kalain, Reclusive Painter", Zone.HAND, "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears.tapped = True

    scenario.game.cast(
        kalain,
        "alice",
        keyword="web-slinging",
        choosing=[bears],
        mana_sources=scenario.untapped_sources("Forest", "Plains", "Island"),
    )

    assert kalain.zone is Zone.STACK
    assert bears.zone is Zone.HAND


def test_web_slinging_grant_skips_a_nonlegendary_spell():
    scenario = board(
        ["Grizzly Bears", "Forest", "Plains", "Island"],
        hand=["Llanowar Elves", "Peter Parker"],
    )
    amazing_spider_man(scenario)
    bears = scenario.creature("Grizzly Bears")
    elves = scenario.find("Llanowar Elves", Zone.HAND, "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears.tapped = True

    with pytest.raises(ValueError):
        scenario.game.cast(
            elves,
            "alice",
            keyword="web-slinging",
            choosing=[bears],
            mana_sources=scenario.untapped_sources("Forest", "Plains", "Island"),
        )


# -- affinity (CR 702.41a) ----------------------------------------------------


def test_mycosynth_golem_gives_artifact_creature_spells_affinity_for_artifacts():
    """Sliver Construct ({3}) with two artifacts out costs {1}; a plain creature
    spell does not get the discount."""
    scenario = board(["Mycosynth Golem", "Sol Ring"], hand=["Sliver Construct", "Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    construct = scenario.cast("Sliver Construct")
    discounted = str(construct.total_cost.mana)
    construct.cancel()
    bears = scenario.cast("Grizzly Bears")

    assert discounted == "{1}", "{3} less the Golem and the Sol Ring"
    assert str(bears.total_cost.mana) == "{1}{G}"


def test_the_affinity_grant_ends_with_the_golem():
    scenario = board(["Mycosynth Golem", "Sol Ring"], hand=["Sliver Construct"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.put_into_graveyard(scenario.creature("Mycosynth Golem"))
    construct = scenario.cast("Sliver Construct")

    assert str(construct.total_cost.mana) == "{3}", "no affinity without the Golem"


# -- rebound (CR 702.88a) -----------------------------------------------------


def test_cast_through_time_gives_instants_rebound():
    scenario = board(["Cast Through Time", "Mountain"], bob=["Grizzly Bears"], hand=["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")

    bolt = scenario.cast_and_resolve(
        "Lightning Bolt", mountain, targets=[scenario.creature("Grizzly Bears", "bob")]
    )

    assert bolt.zone is Zone.EXILE, "exiled by rebound instead of the graveyard"


def test_without_the_grant_the_instant_goes_to_the_graveyard():
    scenario = board(["Mountain"], bob=["Grizzly Bears"], hand=["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")

    bolt = scenario.cast_and_resolve(
        "Lightning Bolt", mountain, targets=[scenario.creature("Grizzly Bears", "bob")]
    )

    assert bolt.zone is Zone.GRAVEYARD


# -- ripple (CR 702.60a) ------------------------------------------------------


def ripple_board(library):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Thrumming Stone", "Mountain"],
            hand=["Lightning Bolt"],
            library=library,
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_thrumming_stone_ripples_a_spell_with_the_same_name_for_free():
    scenario = ripple_board(["Lightning Bolt", "Island", "Island", "Island", "Swamp"])
    scenario.will_choose_targets("bob", source="Lightning Bolt", times=None)
    (mountain,) = scenario.untapped_sources("Mountain")
    casting = scenario.cast("Lightning Bolt")
    casting.choose_targets(["bob"])
    scenario.pay_with(casting.begin_paying(), mountain)
    scenario.put_on_stack(casting)
    while not scenario.game.stack_is_empty:
        scenario.game.put_triggers_on_stack()
        scenario.resolve_top()

    names = [state.name for state in scenario.player("alice").graveyard]
    assert names.count("Lightning Bolt") == 2, "the cast one and the rippled one"
    assert scenario.player("bob").life == 14
    library = [state.name for state in scenario.player("alice").library]
    assert library == ["Swamp", "Island", "Island", "Island"], "revealed and uncast go to the bottom"


def test_ripple_with_no_same_name_card_just_bottoms_the_revealed_cards():
    scenario = ripple_board(["Island", "Swamp", "Island", "Island", "Forest"])
    (mountain,) = scenario.untapped_sources("Mountain")
    casting = scenario.cast("Lightning Bolt")
    casting.choose_targets(["bob"])
    scenario.pay_with(casting.begin_paying(), mountain)
    scenario.put_on_stack(casting)
    while not scenario.game.stack_is_empty:
        scenario.game.put_triggers_on_stack()
        scenario.resolve_top()

    assert [state.name for state in scenario.player("alice").graveyard] == ["Lightning Bolt"]
    assert [state.name for state in scenario.player("alice").library][0] == "Forest"
