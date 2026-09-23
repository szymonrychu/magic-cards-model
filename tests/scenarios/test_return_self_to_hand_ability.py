"""Scenario: an activated ability that returns its own permanent to its
owner's hand - Bramble Familiar's "{1}{G}, {T}, Discard a card: Return this
creature to its owner's hand." (`_parse_return_self_to_owners_hand_clause`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 201.5** - "this creature" is the object the ability is printed on.
- **CR 602.2b** - the discard and the tap are paid as the ability is
  activated, before it resolves.
- **CR 400.7** - a permanent that left the battlefield and came back is a
  new object; the ability returns nothing then.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

FAMILIAR = "Bramble Familiar"


def _board() -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Opt"],
            battlefield=[FAMILIAR, "Forest", "Forest"],
            library=["Forest"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate(scenario: PlayedScenario):
    familiar = scenario.creature(FAMILIAR, "alice")
    opt = scenario.find("Opt", Zone.HAND, "alice")
    forests = scenario.untapped_sources("Forest", "Forest")
    ability_index = 1  # {T}: Add {G}. is the first activated ability
    scenario.activate(familiar, *forests, index=ability_index, discarding=[opt])
    return familiar, opt


def test_bramble_familiar_returns_itself_to_hand():
    scenario = _board()
    familiar, opt = _activate(scenario)
    assert opt.zone is Zone.GRAVEYARD, "CR 602.2b: the discard is paid on activation"

    scenario.pass_until_resolved()

    assert familiar.zone is Zone.HAND


def test_a_familiar_that_left_and_came_back_stays_on_the_battlefield():
    """CR 400.7: the returned Familiar is a new object, not the one the
    ability was activated from."""
    scenario = _board()
    familiar, _ = _activate(scenario)
    scenario.game.exile_permanent(familiar)
    scenario.game.put_onto_battlefield(familiar, "alice")

    scenario.pass_until_resolved()

    assert familiar.zone is Zone.BATTLEFIELD
