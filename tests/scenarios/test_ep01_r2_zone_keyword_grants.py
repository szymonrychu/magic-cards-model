"""Scenario: a permanent's static ability gives cards in a hand or graveyard a
keyword - "Each creature card in your graveyard has unearth {2}{B}." (Sedris,
the Traitor King), "Each Sliver creature card in your graveyard has unearth
{2}." (Dregscape Sliver), "Each land card in your hand has cycling {R}."
(Tectonic Reformation), "Each Sliver card in each player's hand has
slivercycling {3}." (Homing Sliver), "Land cards in your graveyard have dredge
2." (The Necrobloom), "Each creature card in your hand has ninjutsu
{2}{U}{B}." (Satoru Umezawa).

CR 604.2 makes each a static ability; CR 613.1f a keyword-granting effect is a
layer 6 effect that applies to whatever its text indicates (CR 611.3a), here
cards in another zone. The granted keyword runs through the machine of the
printed keyword (CR 702.84a unearth, CR 702.29a cycling, CR 702.52a dredge,
CR 702.49a ninjutsu).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import (
    cycling_activation,
    dredge,
    ninjutsu_activation,
    unearth_activation,
    why_cannot_dredge,
)
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from tests.scenarios.harness import Scenario, mana_from


def build(alice, bob=None):
    scenario = Scenario().manual_turn_based_actions()
    scenario = scenario.player("alice", **alice)
    scenario = scenario.player("bob", **(bob or {}))
    built = scenario.build()
    built.start_at(Step.PRECOMBAT_MAIN)
    return built


def off_zone(scenario, card):
    return [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.ACTIVATE_OFF_ZONE and action.card_id == card.id
    ]


def pay(activation, scenario, *sources):
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    return activation


def test_sedris_gives_a_creature_card_in_the_graveyard_unearth():
    scenario = build(
        {
            "battlefield": ["Sedris, the Traitor King", "Swamp", "Swamp", "Swamp"],
            "graveyard": ["Grizzly Bears", "Divination"],
        }
    )
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    divination = scenario.find("Divination", Zone.GRAVEYARD, "alice")
    assert off_zone(scenario, bears), "legal_actions offers the granted unearth"
    assert not off_zone(scenario, divination), "not a creature card"

    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    activation = pay(unearth_activation(scenario.game, bears, "alice"), scenario, *sources)
    activation.activate()
    entered = activation.resolve()

    assert entered.zone is Zone.BATTLEFIELD
    assert "Haste" in scenario.game.characteristics_of(entered).abilities


def test_the_unearth_grant_is_only_for_your_own_graveyard():
    scenario = build(
        {"battlefield": ["Sedris, the Traitor King", "Swamp", "Swamp", "Swamp"]},
        {"graveyard": ["Grizzly Bears"]},
    )
    theirs = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    assert not off_zone(scenario, theirs)


def test_the_unearth_grant_ends_when_the_source_leaves():
    scenario = build(
        {
            "battlefield": ["Sedris, the Traitor King", "Swamp", "Swamp", "Swamp"],
            "graveyard": ["Grizzly Bears"],
        }
    )
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert off_zone(scenario, bears)
    scenario.game.put_into_graveyard(scenario.creature("Sedris, the Traitor King"))

    assert not off_zone(scenario, bears)


def test_dregscape_sliver_unearth_is_for_slivers_only():
    scenario = build(
        {
            "battlefield": ["Dregscape Sliver", "Swamp", "Swamp"],
            "graveyard": ["Muscle Sliver", "Grizzly Bears"],
        }
    )
    sliver = scenario.find("Muscle Sliver", Zone.GRAVEYARD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    assert off_zone(scenario, sliver)
    assert not off_zone(scenario, bears)


def test_tectonic_reformation_gives_a_land_card_in_hand_cycling():
    scenario = build(
        {
            "battlefield": ["Tectonic Reformation", "Mountain"],
            "hand": ["Forest", "Grizzly Bears"],
            "library": ["Island"],
        }
    )
    forest = scenario.find("Forest", Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    assert not any(a for a in off_zone(scenario, bears))

    activation = cycling_activation(scenario.game, forest, "alice")
    pay(activation, scenario, *scenario.untapped_sources("Mountain")).activate()
    activation.resolve()

    assert forest.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.player("alice").cards_in(Zone.HAND)].count("Island") == 1


def test_homing_sliver_reaches_each_players_hand():
    scenario = build(
        {"battlefield": ["Homing Sliver", "Plains", "Plains", "Plains"], "hand": ["Muscle Sliver"]},
        {"hand": ["Sliver Construct"]},
    )
    mine = scenario.find("Muscle Sliver", Zone.HAND, "alice")
    theirs = scenario.find("Sliver Construct", Zone.HAND, "bob")

    assert off_zone(scenario, mine)
    bobs = [a for a in legal_actions(scenario.game, "bob") if a.card_id == theirs.id]
    assert [a.kind for a in bobs] == [ActionKind.ACTIVATE_OFF_ZONE], "each player's hand"
    assert bobs[0].rule == "CR 702.29e"


def test_the_necrobloom_gives_land_cards_in_the_graveyard_dredge_two():
    scenario = build(
        {
            "battlefield": ["The Necrobloom"],
            "graveyard": ["Forest", "Grizzly Bears"],
            "library": ["Island", "Plains", "Swamp"],
        }
    )
    forest = scenario.find("Forest", Zone.GRAVEYARD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert why_cannot_dredge(scenario.game, bears, "alice") is not None

    milled = dredge(scenario.game, forest, "alice")

    assert [state.name for state in milled] == ["Island", "Plains"]
    assert forest.zone is Zone.HAND


def test_satoru_umezawa_gives_creature_cards_in_hand_ninjutsu():
    scenario = build(
        {
            "battlefield": ["Satoru Umezawa", "Grizzly Bears", "Island", "Swamp", "Island", "Swamp"],
            "hand": ["Llanowar Elves"],
        },
        {},
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears")
    scenario.attack_with(bears, defending="bob")
    scenario.advance()
    scenario.no_blocks()
    elves = scenario.find("Llanowar Elves", Zone.HAND, "alice")

    activation = ninjutsu_activation(scenario.game, elves, bears, "alice")
    activation.begin_paying()
    activation.payment.auto_tap(scenario.game.permanents_controlled_by("alice"))
    activation.payment.pay()
    activation.activate()
    activation.resolve()

    assert elves.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.HAND
