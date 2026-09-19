"""Scenario: "return N land(s) you control to its owner's hand" - the
Karoo-cycle bounce lands (Gruul Turf, Simic Growth Chamber, already covered by
`test_amulet_of_vigor.py` and `test_layer_computed_type_selection.py`) always
print "a land", but Khalni Gem prints a wider count: "When this artifact
enters, return two lands you control to their owner's hand." The old regex
matched only the literal "a", so Khalni Gem's whole trigger fell through
unread - the mana rock entered for free with nothing given up for it.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 603.6a** - enters-the-battlefield abilities trigger when a permanent
  enters the battlefield.
- **CR 608.2d** - a resolving ability's choice among "lands you control" (no
  "target" is printed) is made as the ability resolves, and "can't choose an
  option that's illegal or impossible".
- **CR 101.4** - not at issue here (one player only), included for
  completeness of the choice's own controller.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import Color
from tests.scenarios.harness import Scenario


def test_khalni_gem_returns_two_chosen_lands():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Khalni Gem"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")

    scenario.will_choose_cards(mountain, forest, source="Khalni Gem")
    gem = scenario.cast_and_resolve("Khalni Gem", *sources)
    scenario.pass_until_resolved()  # the enters trigger, put on the stack separately

    assert gem.zone is Zone.BATTLEFIELD
    assert mountain.zone is Zone.HAND
    assert forest.zone is Zone.HAND
    remaining = [
        state for state in scenario.game.permanents_controlled_by("alice") if state.name == "Forest"
    ]
    assert len(remaining) == 3, "one Forest was bounced, the other three stayed"


def test_khalni_gem_returning_more_lands_than_control_takes_only_what_is_there():
    """CR 608.2d: the printed count is a maximum, never a requirement to have
    that many - a controller with fewer lands than the printed count returns
    everything they have, the same "as many as possible" floor `search_
    library` already applies to a search."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Khalni Gem"],
            battlefield=["Lotus Petal", "Lotus Petal", "Lotus Petal", "Lotus Petal", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    petals = [state for state in scenario.game.battlefield if state.name == "Lotus Petal"]
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")

    scenario.will_choose_cards(forest, source="Khalni Gem")
    for petal in petals:
        scenario.activate(petal, sacrificing=[petal], color=Color.GREEN)
    casting = scenario.cast("Khalni Gem")
    casting.determine_cost()
    payment = casting.begin_paying()
    payment.pay()  # the four Lotus Petals already floated {4} - no land tapped
    scenario.put_on_stack(casting)
    gem = scenario.resolve_top()
    scenario.pass_until_resolved()  # the enters trigger, put on the stack separately

    assert gem.zone is Zone.BATTLEFIELD
    assert forest.zone is Zone.HAND, "the only land alice controlled was returned"
