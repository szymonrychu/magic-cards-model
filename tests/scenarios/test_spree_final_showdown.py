"""Scenario: Final Showdown - every Spree mode alone and in every combination.

    Spree (Choose one or more additional costs.)
    + {1} - All creatures lose all abilities until end of turn.
    + {1} - Choose a creature you control. It gains indestructible until end
      of turn.
    + {3}{W}{W} - Destroy all creatures.

Two readers are new here, each proven on a second printing:

- **A mass "lose all abilities" one-shot effect.** The group is fixed when
  the effect begins (CR 611.2c), and the removal is a layer 6 effect
  (CR 613.1f). Proof: Sudden Spoiling ("Until end of turn, creatures target
  player controls lose all abilities and have base power and toughness
  0/2.") - a different subject (a targeted player's creatures), the
  duration written first, and a base power/toughness rider (CR 613.4b).
- **A non-targeted choice followed by an anaphor** - "Choose a creature you
  control. It gains ..." The choice is made on resolution (CR 608.2d), and
  it is not a target (CR 115.10a), so shroud does not stop it. Proof: Crush
  Underfoot ("Choose a Giant creature you control. It deals damage equal to
  its power to target creature.") - a subtype-narrowed choice and a damage
  rider with a target of its own.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 702.172a** - Spree: choose one or more modes, paying each chosen
  mode's cost as an additional cost.
- **CR 700.2h** - each chosen mode's cost is paid; all of them, together.
- **CR 608.2c** - modes resolve in printed order (CR 702.42b's general
  statement, `resolve_modal_spell`).
- **CR 608.2d** - a choice an effect offers is made while it resolves.
- **CR 115.10a** - an object an effect affects without the word "target" is
  not a target.
- **CR 611.2c** - the set of objects a resolving continuous effect affects is
  fixed when it begins.
- **CR 613.1f** - layer 6, ability-adding and ability-removing effects,
  applied in timestamp order (CR 613.7).
- **CR 613.4b** - sublayer 7b, effects that set base power and toughness.
- **CR 701.8a** - destroy.
- **CR 514.2** - "until end of turn" effects end in the cleanup step.
"""

import itertools

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario

#: The printed {W} plus each chosen mode's own cost (CR 700.2h), summed.
TOTAL_COSTS = {
    (1,): "{1}{W}",
    (2,): "{1}{W}",
    (3,): "{3}{W}{W}{W}",
    (1, 2): "{2}{W}",
    (1, 3): "{4}{W}{W}{W}",
    (2, 3): "{4}{W}{W}{W}",
    (1, 2, 3): "{5}{W}{W}{W}",
}


def _resolve_all(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def _board(alice_extra: list[str] | None = None, bob: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Final Showdown"],
            battlefield=["Plains"] * 8 + (alice_extra or ["Serra Angel", "Grizzly Bears"]),
        )
        .player(
            "bob",
            hand=["Serra Angel"],
            battlefield=bob if bob is not None else ["Birds of Paradise"],
        )
    )


def _cast(scenario, modes: list[int]) -> object:
    casting = scenario.cast("Final Showdown")
    casting.choose_modes(modes)
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*(["Plains"] * 8)))
    spell = scenario.put_on_stack(casting)
    _resolve_all(scenario)
    return spell


def _abilities(scenario, state) -> tuple[str, ...]:
    return tuple(scenario.game.characteristics_of(state).abilities)


# -- Costs: every legal combination ----------------------------------------


@pytest.mark.parametrize(
    "modes",
    [list(combo) for size in (1, 2, 3) for combo in itertools.combinations((1, 2, 3), size)],
)
def test_every_combination_charges_the_printed_cost_plus_each_chosen_modes_cost(modes):
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Final Showdown")
    casting.choose_modes(modes)

    assert casting.total_cost.mana == ManaCost.parse(TOTAL_COSTS[tuple(modes)])


@pytest.mark.parametrize(
    "modes",
    [list(combo) for size in (1, 2, 3) for combo in itertools.combinations((1, 2, 3), size)],
)
def test_every_combination_resolves_with_no_mode_left_unread(modes):
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    scenario.will_choose_cards(angel, source="Final Showdown")

    spell = _cast(scenario, modes)

    assert spell.zone is Zone.GRAVEYARD
    assert not scenario.game.mode_notices
    assert not scenario.game.anaphoric_clause_notices


# -- Mode 1: all creatures lose all abilities until end of turn -------------


def test_mode_one_strips_every_creatures_abilities_on_both_sides():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    birds = scenario.creature("Birds of Paradise", "bob")
    assert has_keyword(angel, "Flying", scenario.game)

    _cast(scenario, [1])

    assert not has_keyword(angel, "Flying", scenario.game)
    assert not has_keyword(angel, "Vigilance", scenario.game)
    assert not has_keyword(birds, "Flying", scenario.game)
    assert _abilities(scenario, birds) == ()


def test_mode_one_does_not_touch_a_noncreature_permanent():
    scenario = _board(bob=["Glorious Anthem", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    their_bears = scenario.creature("Grizzly Bears", "bob")
    assert scenario.game.power_of(their_bears) == 3

    _cast(scenario, [1])

    assert scenario.game.power_of(their_bears) == 3, "the anthem is not a creature"


def test_mode_one_misses_a_creature_that_enters_afterward():
    """CR 611.2c: the group is fixed when the effect begins."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast(scenario, [1])
    newcomer = scenario.put_onto_battlefield("Serra Angel", "bob")

    assert has_keyword(newcomer, "Flying", scenario.game)


def test_mode_one_ends_at_cleanup():
    """CR 514.2."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")

    _cast(scenario, [1])
    assert not has_keyword(angel, "Flying", scenario.game)
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert has_keyword(angel, "Flying", scenario.game)


# -- Mode 2: choose a creature you control; it gains indestructible --------


def test_mode_two_grants_indestructible_to_the_chosen_creature_only():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_cards(bears, source="Final Showdown")

    _cast(scenario, [2])

    assert has_keyword(bears, "Indestructible", scenario.game)
    assert not has_keyword(angel, "Indestructible", scenario.game)


def test_mode_two_offers_only_creatures_you_control():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    birds = scenario.creature("Birds of Paradise", "bob")
    scenario.will_choose_cards(angel, source="Final Showdown")

    _cast(scenario, [2])

    (question,) = [q for q in scenario.questions_asked() if q.source == "Final Showdown"]
    assert set(question.cards) == {angel.id, bears.id}
    assert birds.id not in question.cards


def test_mode_two_is_not_a_target_so_shroud_does_not_stop_it():
    """CR 115.10a: "choose" is not "target"."""
    scenario = _board(alice_extra=["Elvish Lookout"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lookout = scenario.creature("Elvish Lookout", "alice")

    _cast(scenario, [2])

    assert has_keyword(lookout, "Indestructible", scenario.game)


def test_mode_two_with_no_creature_to_choose_does_nothing_and_says_nothing():
    """CR 608.2d: nothing legal to choose - the rider has nothing to act on,
    and that is not an unread mode."""
    scenario = _board(alice_extra=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spell = _cast(scenario, [2])

    assert spell.zone is Zone.GRAVEYARD
    assert not scenario.game.mode_notices


def test_mode_two_ends_at_cleanup():
    scenario = _board(alice_extra=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast(scenario, [2])
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert not has_keyword(bears, "Indestructible", scenario.game)


# -- Mode 3 and the combinations -------------------------------------------


def test_mode_three_destroys_every_creature():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    creatures = [
        scenario.creature("Serra Angel", "alice"),
        scenario.creature("Grizzly Bears", "alice"),
        scenario.creature("Birds of Paradise", "bob"),
    ]

    _cast(scenario, [3])

    assert all(state.zone is Zone.GRAVEYARD for state in creatures)


def test_modes_two_and_three_the_chosen_creature_survives_the_wrath():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    birds = scenario.creature("Birds of Paradise", "bob")
    scenario.will_choose_cards(angel, source="Final Showdown")

    _cast(scenario, [2, 3])

    assert angel.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.GRAVEYARD
    assert birds.zone is Zone.GRAVEYARD


def test_modes_one_and_three_an_indestructible_creature_loses_it_and_dies():
    """Blightsteel Colossus's indestructible is an ability; mode 1 removes it
    before mode 3 destroys (printed order)."""
    scenario = _board(bob=["Blightsteel Colossus"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    colossus = scenario.creature("Blightsteel Colossus", "bob")

    _cast(scenario, [1, 3])

    assert colossus.zone is not Zone.BATTLEFIELD


def test_modes_one_and_two_the_later_grant_wins_over_the_earlier_removal():
    """CR 613.7: both in layer 6, applied in timestamp order - mode 2's grant
    comes after mode 1's removal, so the chosen creature keeps it while every
    other creature has nothing."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_cards(bears, source="Final Showdown")

    _cast(scenario, [1, 2])

    assert has_keyword(bears, "Indestructible", scenario.game)
    assert not has_keyword(angel, "Flying", scenario.game)
    assert not has_keyword(angel, "Indestructible", scenario.game)


def test_all_three_modes_leave_exactly_the_chosen_creature():
    scenario = _board(bob=["Blightsteel Colossus", "Birds of Paradise"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    colossus = scenario.creature("Blightsteel Colossus", "bob")
    birds = scenario.creature("Birds of Paradise", "bob")
    scenario.will_choose_cards(angel, source="Final Showdown")

    _cast(scenario, [1, 2, 3])

    assert angel.zone is Zone.BATTLEFIELD
    assert not has_keyword(angel, "Flying", scenario.game)
    assert bears.zone is Zone.GRAVEYARD
    assert birds.zone is Zone.GRAVEYARD
    assert colossus.zone is not Zone.BATTLEFIELD


# -- Proof printing: Sudden Spoiling (mass lose-all, targeted-player group) --


def _spoiling_board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Sudden Spoiling"], battlefield=["Swamp"] * 3 + ["Serra Angel"])
        .player("bob", hand=["Serra Angel"], battlefield=["Serra Angel", "Birds of Paradise"])
    )


def _cast_spoiling(scenario, target: str) -> None:
    scenario.cast_and_resolve(
        "Sudden Spoiling", *scenario.untapped_sources("Swamp", "Swamp", "Swamp"), targets=[target]
    )


def test_sudden_spoiling_strips_and_resets_the_targeted_players_creatures():
    scenario = _spoiling_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    their_angel = scenario.creature("Serra Angel", "bob")
    birds = scenario.creature("Birds of Paradise", "bob")
    my_angel = scenario.creature("Serra Angel", "alice")

    _cast_spoiling(scenario, "bob")

    assert not has_keyword(their_angel, "Flying", scenario.game)
    assert _abilities(scenario, birds) == ()
    assert (scenario.game.power_of(their_angel), scenario.game.toughness_of(their_angel)) == (0, 2)
    assert (scenario.game.power_of(birds), scenario.game.toughness_of(birds)) == (0, 2)
    assert has_keyword(my_angel, "Flying", scenario.game), "not the targeted player's"
    assert scenario.game.power_of(my_angel) == 4


def test_sudden_spoiling_misses_a_creature_that_enters_afterward():
    scenario = _spoiling_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_spoiling(scenario, "bob")
    newcomer = scenario.put_onto_battlefield("Serra Angel", "bob")

    assert has_keyword(newcomer, "Flying", scenario.game)
    assert scenario.game.power_of(newcomer) == 4


def test_sudden_spoiling_ends_at_cleanup():
    scenario = _spoiling_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    their_angel = scenario.creature("Serra Angel", "bob")

    _cast_spoiling(scenario, "bob")
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert has_keyword(their_angel, "Flying", scenario.game)
    assert scenario.game.power_of(their_angel) == 4


def test_sudden_spoiling_on_yourself_hits_only_your_own_creatures():
    scenario = _spoiling_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    my_angel = scenario.creature("Serra Angel", "alice")
    their_angel = scenario.creature("Serra Angel", "bob")

    _cast_spoiling(scenario, "alice")

    assert scenario.game.power_of(my_angel) == 0
    assert scenario.game.power_of(their_angel) == 4


# -- Proof printing: Crush Underfoot (choose a Giant; it deals damage) -------


def _crush_board(alice: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Crush Underfoot"], battlefield=["Mountain", "Mountain"] + alice)
        .player("bob", battlefield=["Serra Angel", "Grizzly Bears"])
    )


def test_crush_underfoot_the_chosen_giant_deals_damage_equal_to_its_power():
    scenario = _crush_board(["Hill Giant"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "alice")

    scenario.cast_and_resolve(
        "Crush Underfoot", *scenario.untapped_sources("Mountain", "Mountain"), targets=[bears]
    )

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.BATTLEFIELD
    assert giant.damage == 0, "one-sided damage, not a fight"


def test_crush_underfoot_the_giant_is_the_source_of_the_damage():
    """The chosen Giant, not the spell, deals it: 3 damage to a 4/4 Angel."""
    scenario = _crush_board(["Hill Giant"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve(
        "Crush Underfoot", *scenario.untapped_sources("Mountain", "Mountain"), targets=[angel]
    )

    assert angel.zone is Zone.BATTLEFIELD
    assert angel.damage == 3


def test_crush_underfoot_offers_only_giants_you_control():
    scenario = _crush_board(["Hill Giant", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    my_bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Crush Underfoot", *scenario.untapped_sources("Mountain", "Mountain"), targets=[angel]
    )

    assert angel.damage == 3, "the lone Giant was chosen; the Bears were never offered"
    assert my_bears.zone is Zone.BATTLEFIELD


def test_crush_underfoot_with_no_giant_does_nothing():
    scenario = _crush_board(["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    their_bears = scenario.creature("Grizzly Bears", "bob")

    spell = scenario.cast_and_resolve(
        "Crush Underfoot",
        *scenario.untapped_sources("Mountain", "Mountain"),
        targets=[their_bears],
    )

    assert spell.zone is Zone.GRAVEYARD
    assert their_bears.zone is Zone.BATTLEFIELD
    assert their_bears.damage == 0
    assert not scenario.game.anaphoric_clause_notices
