"""Scenario: a team pump whose X is an extremum, not a count.

Tyvar, the Pummeler: "{3}{G}{G}: Creatures you control get +X/+X until end of
turn, where X is the greatest power among creatures you control."

The mass-pump machinery already read "where X is the number of creatures you
control" (Craterhoof Behemoth). "The greatest power among ..." is not a count
of anything - it is a maximum over a characteristic - so `count_expression`
returned `None` for it and the whole ability fell through to a layer notice.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 611.2c** - the affected group and the magnitude are both fixed as the
  effect begins, so a creature that arrives afterwards neither joins the group
  nor grows X.
- **CR 613.5** - the layer system is applied continually and automatically, so
  "greatest power" is the greatest *computed* power, counters and anthems
  included, not the greatest printed one.
- **CR 208.5** - "If a creature somehow has no value for its power, its power
  is 0. The same is true for toughness."
- **CR 107.2** - "If anything needs to use a number that can't be determined,
  either as a result or in a calculation, it uses 0 instead", which is what an
  empty group makes X.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

FIVE_FORESTS = ["Forest"] * 5


def _pump(scenario, tyvar):
    scenario.activate(tyvar, *scenario.untapped_sources(*FIVE_FORESTS), index=1)
    scenario.resolve_top()


def test_x_is_the_greatest_power_on_the_board_not_the_number_of_creatures():
    """Tyvar is a 3/3 and the Bears a 2/2, so X is 3 - and would be 2 if this
    were a count of creatures, which is the whole point of the distinction."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tyvar, the Pummeler", "Grizzly Bears", *FIVE_FORESTS],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    tyvar = scenario.find("Tyvar, the Pummeler", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    _pump(scenario, tyvar)

    assert scenario.game.characteristics_of(tyvar).power_toughness == (6, 6)
    assert scenario.game.characteristics_of(bears).power_toughness == (5, 5)


def test_the_biggest_creature_sets_x_for_everybody():
    """A single fatty raises X for the whole team, which a count never would."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Tyvar, the Pummeler",
                "Grizzly Bears",
                "Craterhoof Behemoth",
                *FIVE_FORESTS,
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    tyvar = scenario.find("Tyvar, the Pummeler", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    hoof = scenario.find("Craterhoof Behemoth", Zone.BATTLEFIELD, "alice")
    _pump(scenario, tyvar)

    # Craterhoof is a printed 5/5, so X = 5.
    assert scenario.game.characteristics_of(hoof).power_toughness == (10, 10)
    assert scenario.game.characteristics_of(tyvar).power_toughness == (8, 8)
    assert scenario.game.characteristics_of(bears).power_toughness == (7, 7)


def test_an_opponents_bigger_creature_does_not_set_x():
    """ "Among creatures you control" - CR 611.2c's group is one player's."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tyvar, the Pummeler", *FIVE_FORESTS])
        .player("bob", battlefield=["Craterhoof Behemoth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    tyvar = scenario.find("Tyvar, the Pummeler", Zone.BATTLEFIELD, "alice")
    hoof = scenario.find("Craterhoof Behemoth", Zone.BATTLEFIELD, "bob")
    _pump(scenario, tyvar)

    assert scenario.game.characteristics_of(tyvar).power_toughness == (6, 6), "X is Tyvar's own 3"
    assert scenario.game.characteristics_of(hoof).power_toughness == (5, 5), "bob's is untouched"


def test_a_creature_that_arrives_afterwards_neither_joins_nor_grows_x():
    """CR 611.2c fixes both the group and the number when the effect begins."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Craterhoof Behemoth"],
            battlefield=["Tyvar, the Pummeler", *FIVE_FORESTS],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    tyvar = scenario.find("Tyvar, the Pummeler", Zone.BATTLEFIELD, "alice")
    _pump(scenario, tyvar)
    assert scenario.game.characteristics_of(tyvar).power_toughness == (6, 6)

    late = scenario.put_onto_battlefield("Craterhoof Behemoth", "alice")
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert scenario.game.characteristics_of(late).power_toughness == (5, 5), "not in the group"
    assert scenario.game.characteristics_of(tyvar).power_toughness == (6, 6), "X did not grow"
