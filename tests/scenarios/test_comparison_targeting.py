"""Scenario: "target ... with mana value/power/toughness N or less/greater" (CR 202.3).

`machines/targeting.py` used to read the noun and every plain adjective of a
"target ..." phrase and then silently drop a trailing numeric comparison -
"target creature with mana value 2 or less" came back `understood=True` with
an unrestricted creature requirement, so a removal spell that should only hit
small things would happily accept anything. That is worse than not modelling
the restriction at all: a wrong, permissive game state that looks legal.

These scenarios drive real cards through `Casting.choose_targets`, which is
where CR 601.2c's announcement is checked, to prove the restriction is now
read and enforced - at the bound, below it, above it, off a *current*
characteristic changed by a continuous effect (not the printed one), and
refused outright when the number cannot be pinned down (CR 107.3's unbound X).
"""

import pytest

from magic_cards_model.machines import Step

from .harness import Scenario


def board() -> Scenario:
    """Alice with removal in hand; bob with creatures of different sizes."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Abrupt Decay", "Abzan Charm", "Warping Wail", "March of Otherworldly Light"],
            battlefield=["Swamp", "Forest", "Plains", "Mountain"],
        )
        .player(
            "bob",
            battlefield=[
                "Grizzly Bears",
                "Kitchen Finks",
                "Hill Giant",
                "Fog Bank",
                "Ashmouth Hound",
            ],
        )
    )


# -- mana value: "target nonland permanent with mana value 3 or less" -------
# (Abrupt Decay)


def test_a_permanent_above_the_mana_value_bound_is_not_a_legal_target():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hill_giant = scenario.creature("Hill Giant", "bob")  # mana value 4

    with pytest.raises(ValueError, match="mana value"):
        scenario.cast("Abrupt Decay", username="alice", targets=[hill_giant])


def test_a_permanent_at_the_mana_value_bound_is_a_legal_target():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    finks = scenario.creature("Kitchen Finks", "bob")  # mana value 3, the bound itself

    casting = scenario.cast("Abrupt Decay", username="alice", targets=[finks])

    assert casting.targets[0].card_id == finks.id


def test_a_permanent_below_the_mana_value_bound_is_a_legal_target():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")  # mana value 2

    casting = scenario.cast("Abrupt Decay", username="alice", targets=[bears])

    assert casting.targets[0].card_id == bears.id


# -- power: "target creature with power 3 or greater" (Abzan Charm) ---------


def test_a_creature_below_the_power_bound_is_not_a_legal_target():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")  # printed power 2

    casting = scenario.cast("Abzan Charm", username="alice")
    casting.choose_modes([1])
    with pytest.raises(ValueError, match="power"):
        casting.choose_targets([bears])


def test_a_creature_pumped_past_the_power_bound_by_a_continuous_effect_is_legal():
    """The check reads the *current* power (CR 613.5), not the printed one.

    Grizzly Bears is printed 2/2 - illegal for "power 3 or greater" on its
    own, as the test above shows. Glorious Anthem's "Creatures you control get
    +1/+1" is a continuous effect `machines/layers.py` applies, making Bears a
    3/3 right now. Only a check that asks the board for the *computed*
    characteristics, rather than reading `CardState`/`Card` directly, can tell
    the difference.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Abzan Charm"],
            battlefield=["Swamp", "Forest", "Plains"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Glorious Anthem"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    assert bears.power == 2, "printed power, to make sure the pump is what legalises the target"
    assert scenario.game.power_of(bears) == 3, "the anthem is live before the cast is even tried"

    casting = scenario.cast("Abzan Charm", username="alice")
    casting.choose_modes([1])
    casting.choose_targets([bears])  # would raise if this read the printed 2

    assert casting.targets[0].card_id == bears.id


# -- power-or-toughness disjunction: "target creature with power or ---------
# toughness 1 or less" (Warping Wail)


def test_neither_power_nor_toughness_at_the_bound_is_not_a_legal_target():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")  # 2/2, neither is 1 or less

    casting = scenario.cast("Warping Wail", username="alice")
    casting.choose_modes([1])
    with pytest.raises(ValueError, match="power or toughness"):
        casting.choose_targets([bears])


def test_a_low_power_creature_satisfies_the_disjunction():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fog_bank = scenario.creature("Fog Bank", "bob")  # 0/2: power alone is 1 or less

    casting = scenario.cast("Warping Wail", username="alice")
    casting.choose_modes([1])
    casting.choose_targets([fog_bank])

    assert casting.targets[0].card_id == fog_bank.id


def test_a_low_toughness_creature_satisfies_the_disjunction():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hound = scenario.creature("Ashmouth Hound", "bob")  # 2/1: toughness alone is 1 or less

    casting = scenario.cast("Warping Wail", username="alice")
    casting.choose_modes([1])
    casting.choose_targets([hound])

    assert casting.targets[0].card_id == hound.id


# -- an unevaluable comparison fails closed (CR 107.3's unbound X) ----------


def test_an_unbound_x_comparison_refuses_every_target_instead_of_widening():
    """March of Otherworldly Light: "target ... with mana value X or less".

    X is part of the cost, so it is not known merely from the card's printed
    text - and `Casting`'s non-modal path never re-parses the restriction with
    X substituted in (a known, separate gap: fixing it needs `casting.py`).
    Both together mean this restriction can never be evaluated yet, and the
    fix for this defect is that an unevaluable restriction now refuses every
    target instead of quietly accepting one, which is the fail-open bug this
    file exists to close.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="cannot resolve"):
        scenario.cast("March of Otherworldly Light", username="alice", targets=[bears])
