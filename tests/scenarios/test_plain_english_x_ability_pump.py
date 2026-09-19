"""Scenario: `create_continuous_effect_of_ability` (`machines/effects.py`)
substituted an activated ability's announced X into its own text only when
the printed cost carried the literal `{X}` mana symbol - Fiend Artisan's
`{X}{B/G}`. CR 107.3a's X is not only a mana symbol: "Sacrifice X Squirrels"
(Chatterfang, Squirrel General) announces X in plain English, inside a
`Sacrifice` cost, with no `{X}` anywhere in the printed cost at all. That
narrower check left the resolving ability's own effect text - "Target
creature gets +X/-X until end of turn." - unsubstituted, so
`continuous_effects(game).create(...)` was called with no `ability_text` at
all and fell back to the *card's* raw, unsubstituted oracle text, which
`parsed_layer_effects` cannot read a bare, non-numeric "X" out of. The cost
paid correctly (`Game.activation_cost` reads X the same general way, see
`machines/cost.cost_announces_x`); only the pump itself silently did
nothing.

The fix widens the gate to `cost_announces_x`, the same general "does this
cost's own text carry a bare X" reader `Game.activate_ability`'s own
`x_value` gating and `scripts/sweep_pool.py`'s own X-probe already use -
not a Chatterfang-specific patch - and passes the substituted text through
to `ContinuousEffects.create` so the pump it builds is stored with a real
number in it.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 107.3a** - "If the object with X in its rules text or an ability
  whose rules text includes X is on the stack, ... the value of X is the
  amount of mana of that color spent to pay its... " and more generally
  "value... is announced when the spell or ability is put onto the stack" -
  X is not defined as only a `{X}` mana symbol; it is any variable a cost or
  effect names, chosen as the ability is activated.
- **CR 602.2b/CR 601.2b** - a cost's own object choices (here, how many
  Squirrels to sacrifice) are made and paid as the ability is announced,
  fixing X before the effect ever resolves.
- **CR 701.21a** - to sacrifice a permanent, its controller moves it from
  the battlefield to its owner's graveyard.
- **CR 611.2c** - a continuous effect's own magnitude is fixed once, as it
  is created, not re-read from the board afterward.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def computed(scenario: Scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def test_chatterfang_pumps_and_shrinks_the_target_by_squirrels_sacrificed():
    """Two Squirrels (a pair of Prairie Dogs; Chatterfang itself, a
    Squirrel too, stays on the battlefield) sacrificed pays X=2: the target
    Serra Angel gets +2/-2 until end of turn, 6/2 instead of its printed
    4/4.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Chatterfang, Squirrel General", "Prairie Dog", "Prairie Dog", "Swamp"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chatterfang = scenario.find("Chatterfang, Squirrel General", Zone.BATTLEFIELD, "alice")
    dogs = [c for c in scenario.game.battlefield if c.name == "Prairie Dog"]
    serra = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    swamp = scenario.untapped_sources("Swamp")

    ability = scenario.activate(chatterfang, *swamp, sacrificing=dogs, x_value=2, targets=[serra])
    assert isinstance(ability, AbilityOnStack)
    assert all(dog.zone is Zone.GRAVEYARD for dog in dogs), "the cost is paid on activation"

    scenario.pass_until_resolved()

    board = computed(scenario)
    assert board.of(serra).power_toughness == (6, 2)


def test_chatterfang_sacrificing_none_pumps_by_zero():
    """CR 107.2's own "0 instead" for X announced as zero - a real, legal
    activation (CR 118.6: an unaffordable/degenerate cost is still legal to
    announce) that pays nothing and pumps nothing.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Chatterfang, Squirrel General", "Swamp"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chatterfang = scenario.find("Chatterfang, Squirrel General", Zone.BATTLEFIELD, "alice")
    serra = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    swamp = scenario.untapped_sources("Swamp")

    scenario.activate(chatterfang, *swamp, sacrificing=[], x_value=0, targets=[serra])
    scenario.pass_until_resolved()

    board = computed(scenario)
    assert board.of(serra).power_toughness == (4, 4)
