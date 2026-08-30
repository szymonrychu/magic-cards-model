"""Judge scenarios: state-based actions, and what they are not.

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#662** - Mox Opal vs. Legend Rule
- **DDR#775** - Does the Legend Rule make you sacrifice?
- **DDR#3** - Eternal Witness + Elesh Norn, Grand Cenobite
- **DDR#20** - Tarmogoyf vs. Lightning Bolt

State-based actions are checked whenever a player would get priority, all
applicable ones performed simultaneously as a single event, repeating until
none apply (CR 704.3, CR 117.5). Every CR number here was looked up with
`knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_a_second_copy_of_a_legendary_permanent_goes_to_the_graveyard():
    """DDR#662: the legend rule applies to any legendary permanent, not just creatures.

    CR 704.5j: "If two or more legendary permanents with the same name are
    controlled by the same player, that player chooses one of them, and the rest
    are put into their owners' graveyards." Mox Opal is a Legendary Artifact and
    is caught by exactly the same rule a legendary creature is.
    """
    scenario = Scenario().player("alice", battlefield=["Mox Opal", "Mox Opal"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Mox Opal", "Mox Opal", username="alice")

    scenario.state_based_actions()

    assert first.zone is Zone.BATTLEFIELD
    assert second.zone is Zone.GRAVEYARD
    assert scenario.battlefield_names().count("Mox Opal") == 1


def test_the_legend_rule_is_not_a_sacrifice():
    """DDR#775: the loser is *put into* a graveyard, and that is not sacrificing.

    CR 704.5j says the extras are put into their owners' graveyards; nothing in
    it uses the word sacrifice, which matters for every card that watches for
    one. The test asserts what the engine can see of that distinction: the card
    is in the graveyard, and it got there without any player being asked to pay
    a cost.
    """
    scenario = Scenario().player("alice", battlefield=["Mox Opal", "Mox Opal"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    leaving = scenario.state_based_actions()

    assert [state.name for state in leaving] == ["Mox Opal"]
    assert [state.name for state in scenario.player("alice").graveyard] == ["Mox Opal"]


def test_two_players_may_each_control_the_same_legend():
    """DDR#775: the rule is per controller, not per game (CR 704.5j).

    "controlled by the same player" - so alice's Mox Opal and bob's Mox Opal
    coexist happily, and neither player is asked to choose anything.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mox Opal"])
        .player("bob", battlefield=["Mox Opal"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.state_based_actions() == []
    assert scenario.battlefield_names().count("Mox Opal") == 2


def test_elesh_norn_kills_an_opponents_one_toughness_creature_on_sight():
    """DDR#3: a static ability, not a trigger, and the SBA does the killing.

    Elesh Norn gives creatures opponents control -2/-2. Eternal Witness is a
    printed 2/1, so its toughness becomes -1, and CR 704.5f puts a creature with
    toughness 0 or less into its owner's graveyard. Nothing targets, nothing
    goes on the stack, and there is no window to respond in.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Elesh Norn, Grand Cenobite"])
        .player("bob", battlefield=["Eternal Witness"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    witness = scenario.creature("Eternal Witness", "bob")

    scenario.state_based_actions()

    assert witness.zone is Zone.GRAVEYARD


@pytest.mark.xfail(
    strict=True,
    reason="CR 704.5g is judged against the computed board now, so the Goyf does die. The "
    "first assertion is on CardState.toughness, which is still the printed '*' read as None "
    "- the layer engine computes the CDA in 7a (CR 604.3, CR 613.4a) and models/card_state.py "
    "does not ask it.",
)
def test_tarmogoyf_lives_or_dies_by_its_toughness_right_now():
    """DDR#20: lethal damage is checked against the current toughness, always.

    Tarmogoyf's power and toughness come from a characteristic-defining ability,
    applied in layer 7a (CR 613.4a, CR 604.3), and it recomputes continuously
    (CR 613.5). With an instant and a creature in the graveyards it is a 2/3, so
    the three damage from a Bolt is lethal by CR 704.5g - the same three that
    would bounce off it if a third card type were there.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player(
            "bob",
            battlefield=["Tarmogoyf"],
            graveyard=["Grizzly Bears", "Lightning Bolt"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goyf = scenario.creature("Tarmogoyf", "bob")
    assert goyf.toughness == 3, "creature + instant among graveyards, plus one"

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[goyf])

    assert goyf.zone is Zone.GRAVEYARD
