"""A static cost reduction keyed on a *characteristic of the spell being
cast* itself, rather than its card type, its subtype, or a board count -
Doran, Besieged by Time's own "Each creature spell you cast with toughness
greater than its power costs {1} less to cast." (CR 601.2f). `machines/cost.
CostModifierEffect.requires_toughness_greater_than_power` is the new field
this reads, applied alongside (never instead of) the ordinary `TYPE_DECREASE`
creature-spell filter `_counted_type_decrease` already enforces.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- CR 601.2f: multiple cost reductions may be applied in any order; the total
  cost is locked in once determined.
- CR 611.3a: a static ability's own magnitude (here, whether the filter
  holds at all) is never locked in - it is asked fresh every time a cost is
  determined, for the spell actually being cast.
- CR 208.1 / CR 208.5: a spell's own power and toughness, read as printed
  (a spell on the stack has no board of its own for the layer system to
  compute against); a value that cannot be determined is 0.
- CR 205.2a: "creature spell" is a spell with the creature card type - a
  noncreature spell never qualifies regardless of any power/toughness the
  card happens to print (a Vehicle, an Equipment).
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _cost(scenario: Scenario, name: str) -> str:
    return str(scenario.cast(name).total_cost.mana)


def test_doran_reduces_a_creature_spell_with_toughness_greater_than_power():
    """Wall of Omens is a printed 0/4 - toughness (4) greater than power
    (0) - so Doran's own static takes {1} off its base {1}{W}.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wall of Omens"],
            battlefield=["Doran, Besieged by Time"] + ["Plains"] * 2,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _cost(scenario, "Wall of Omens") == "{W}"


def test_doran_does_not_reduce_a_creature_spell_with_power_greater_than_toughness():
    """Goblin Guide is a printed 2/2 - not "toughness greater than power" -
    so no reduction applies. (2/2 is an equal case, not a greater one.)
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Goblin Guide"],
            battlefield=["Doran, Besieged by Time"] + ["Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _cost(scenario, "Goblin Guide") == "{R}"


def test_doran_does_not_reduce_a_noncreature_spell_even_with_the_right_shape():
    """CR 205.2a: "creature spell" means the creature card type - Lightning
    Bolt has neither power nor toughness (CR 208.2, no printed value) to
    compare in the first place, and is not a creature spell regardless.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Doran, Besieged by Time"] + ["Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _cost(scenario, "Lightning Bolt") == "{R}"


def test_doran_reduction_holds_up_after_casting_a_spell_it_does_not_reduce():
    """CR 611.3a: the static is asked fresh every time a cost is determined,
    not consumed or disabled by an earlier cast it declined to discount -
    Alice casts Goblin Guide (no reduction) first, then Wall of Omens (which
    still gets its full {1} off) in the same game.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wall of Omens", "Goblin Guide"],
            battlefield=["Doran, Besieged by Time"] + ["Plains"] * 2 + ["Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.untapped_sources("Mountain")[0]
    scenario.cast_and_resolve("Goblin Guide", mountain)

    assert _cost(scenario, "Wall of Omens") == "{W}"
