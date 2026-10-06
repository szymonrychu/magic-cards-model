"""Scenario: converge (CR 207.2c) read through the generic "number of colors of
mana spent to cast this spell" amount, in the positions the generic reader now
serves beyond the damage clauses of `test_nw03_damage_amount_terms.py`.

- **Token count** - Unified Front ("a 1/1 white Kor Ally creature token for each
  color of mana spent") and Sweep the Skies, whose {X}{U}{U} cost makes the
  colours spent independent of X.
- **A mass pump** - Roilmage's Trick, "Creatures your opponents control get -X/-0
  ... where X is the number of colors of mana spent", then a card drawn.
- **A trigger written on a permanent** - Radiant Epicure's "When this creature
  enters, each opponent loses X life and you gain X life, where X is the number
  of colors of mana spent to cast this creature": the count is the cast record
  of the permanent the ability came from (CR 400.7a), not of the ability.

The colours are those actually spent (CR 601.2h); colourless is not one
(CR 105.1, 105.2c). Every CR number here was verified with `mise run rules:find`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _main(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _tokens(scenario, name, username):
    return [
        permanent
        for permanent in scenario.game.battlefield
        if permanent.name == name and permanent.controller == username
    ]


def test_unified_front_makes_a_kor_ally_per_colour_spent():
    scenario = _main(
        Scenario()
        .player(
            "alice", hand=["Unified Front"], battlefield=["Plains", "Mountain", "Island", "Swamp"]
        )
        .player("bob")
        .build()
    )
    sources = scenario.untapped_sources("Plains", "Mountain", "Island", "Swamp")
    scenario.cast_and_resolve("Unified Front", *sources)
    assert len(_tokens(scenario, "Kor Ally Token", "alice")) == 4


def test_unified_front_with_one_colour_makes_one():
    scenario = _main(
        Scenario()
        .player("alice", hand=["Unified Front"], battlefield=["Plains"] * 4)
        .player("bob")
        .build()
    )
    sources = scenario.untapped_sources(*["Plains"] * 4)
    scenario.cast_and_resolve("Unified Front", *sources)
    assert len(_tokens(scenario, "Kor Ally Token", "alice")) == 1


def test_sweep_the_skies_counts_colours_not_x():
    """X=1 on {X}{U}{U}: the {1} is paid with a Mountain, so blue and red were
    spent - two Thopters, whatever X is."""
    scenario = _main(
        Scenario()
        .player("alice", hand=["Sweep the Skies"], battlefield=["Island", "Island", "Mountain"])
        .player("bob")
        .build()
    )
    sources = scenario.untapped_sources("Island", "Island", "Mountain")
    casting = scenario.cast("Sweep the Skies")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert len(_tokens(scenario, "Thopter Token", "alice")) == 2


def test_roilmages_trick_shrinks_only_opponents_creatures_and_draws():
    scenario = _main(
        Scenario()
        .player(
            "alice",
            hand=["Roilmage's Trick"],
            library=["Island"] * 3,
            battlefield=["Island", "Mountain", "Forest", "Swamp", "Colossal Dreadmaw"],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    sources = scenario.untapped_sources("Island", "Mountain", "Forest", "Swamp")
    scenario.cast_and_resolve("Roilmage's Trick", *sources)
    mine = scenario.creature("Colossal Dreadmaw", "alice")
    theirs = scenario.creature("Colossal Dreadmaw", "bob")
    assert scenario.game.characteristics_of(theirs).power == 2  # -4/-0: U, R, G, B
    assert scenario.game.characteristics_of(mine).power == 6
    assert len(scenario.player("alice").hand) == 1


def test_radiant_epicure_drains_per_colour_spent_on_the_permanent():
    scenario = _main(
        Scenario()
        .player(
            "alice",
            hand=["Radiant Epicure"],
            battlefield=["Swamp", "Mountain", "Island", "Swamp", "Swamp"],
        )
        .player("bob")
        .build()
    )
    sources = scenario.untapped_sources("Swamp", "Mountain", "Island", "Swamp", "Swamp")
    scenario.cast_and_resolve("Radiant Epicure", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    # B, R and U were spent: three colours.
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 23
    assert scenario.find("Radiant Epicure", Zone.BATTLEFIELD, "alice") is not None


def test_radiant_epicure_with_one_colour_drains_one():
    scenario = _main(
        Scenario()
        .player("alice", hand=["Radiant Epicure"], battlefield=["Swamp"] * 5)
        .player("bob")
        .build()
    )
    sources = scenario.untapped_sources(*["Swamp"] * 5)
    scenario.cast_and_resolve("Radiant Epicure", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21
