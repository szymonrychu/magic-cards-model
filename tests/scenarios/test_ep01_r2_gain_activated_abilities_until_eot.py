"""Scenario: "{U}: This creature gains all activated abilities of target
creature until end of turn." (Quicksilver Elemental, CR 613.1f, CR 602.1) plus
its second sentence, "You may spend blue mana as though it were mana of any
color to pay the activation costs of this creature's abilities." (CR 609.4b).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Color
from magic_cards_model.models.action import ActionKind, Affordability
from tests.scenarios.harness import Scenario


def setup(bob=("Shivan Dragon",), lands=("Island", "Island", "Island"), manual=True):
    builder = Scenario()
    if manual:
        builder = builder.manual_turn_based_actions()
    scenario = (
        builder.player("alice", battlefield=["Quicksilver Elemental", *lands])
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def gain(scenario):
    elemental = scenario.creature("Quicksilver Elemental")
    dragon = scenario.creature("Shivan Dragon", "bob")
    (island,) = scenario.untapped_sources("Island")[:1]
    scenario.activate(elemental, island, targets=[dragon], color=Color.BLUE)
    scenario.pass_until_resolved()
    return elemental, dragon


def abilities(scenario, state):
    return scenario.game.characteristics_of(state).abilities


def test_it_gains_the_targets_activated_abilities():
    scenario = setup()
    elemental, _ = gain(scenario)
    assert any(
        line.startswith("{R}:") and "+1/+0" in line for line in abilities(scenario, elemental)
    )


def test_the_target_keeps_its_abilities():
    scenario = setup()
    _, dragon = gain(scenario)
    assert any(line.startswith("{R}:") for line in abilities(scenario, dragon))


def test_the_gained_ability_is_activatable_with_blue_mana():
    """CR 609.4b: blue mana pays the granted ability's {R}."""
    scenario = setup()
    elemental, _ = gain(scenario)
    before = scenario.game.characteristics_of(elemental).power
    island = scenario.untapped_sources("Island")[0]
    scenario.activate(elemental, island, index=1, color=Color.BLUE)
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(elemental).power == before + 1


def test_other_colours_do_not_get_the_permission():
    """Forests make {G}: only blue mana is widened, so {R} stays unpayable."""
    scenario = setup(lands=("Island", "Forest"))
    elemental, _ = gain(scenario)
    granted = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.ACTIVATE
        and action.card_id == elemental.id
        and action.ability_index == 1
    ]
    assert granted and not any(action.affordable is Affordability.YES for action in granted)


def test_the_grant_ends_at_end_of_turn():
    scenario = setup(manual=False)
    elemental, _ = gain(scenario)
    scenario.start_at(Step.END_OF_COMBAT)
    while scenario.turn.active_player == "alice":
        scenario.advance("alice")
    assert not any(line.startswith("{R}:") for line in abilities(scenario, elemental))
