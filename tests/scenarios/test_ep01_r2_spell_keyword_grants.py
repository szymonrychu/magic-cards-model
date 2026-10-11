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
