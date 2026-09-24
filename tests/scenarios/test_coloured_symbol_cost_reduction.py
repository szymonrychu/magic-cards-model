"""A board-wide "Spells you cast cost `<mana symbols>` less to cast." reduction.

CR 601.2f: the total cost is "the mana cost or alternative cost ... plus all
additional costs and cost increases, and minus all cost reductions", and "If
the mana component of the total cost is reduced to nothing by cost reduction
effects, it is considered to be {0}."

CR 118.7 is how a reduction written in mana symbols lands on a cost:

- 118.7a: "Effects that reduce a cost by an amount of generic mana affect only
  the generic mana component of that cost."
- 118.7b: "If a cost is reduced by an amount of colored or colorless mana, but
  the cost doesn't require mana of that type, the cost is reduced by that
  amount of generic mana."
- 118.7c: "If a cost is reduced by an amount of colored mana that exceeds its
  mana component of that color, the cost's mana component of that color is
  reduced to nothing and the cost's generic mana component is reduced by the
  difference."

Aang, Master of Elements (Avatar Aang's back face) prints "Spells you cast cost
{W}{U}{B}{R}{G} less to cast. (This can reduce generic costs.)" - each coloured
symbol takes its own colour off first and, where the spell has none of it,
generic mana instead. The same reader, with no symbol-specific branch, reads The
Immortal Sun's "Spells you cast cost {1} less to cast." (the second printing,
legal in Modern and Pioneer, in no deck list here), which by CR 118.7a never
touches a coloured pip.

Every CR number here was read whole with `mise run rules:find`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import CostModifierKind, cost_modifier_effect
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

AANG_STATIC = "Spells you cast cost {W}{U}{B}{R}{G} less to cast. (This can reduce generic costs.)"


def _aang_board(hand: list[str], *, bob_hand: list[str] | None = None, transformed: bool = True):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island"] * 5, hand=hand, battlefield=["Avatar Aang"])
        .player("bob", library=["Island"] * 5, hand=bob_hand or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    aang = scenario.creature("Avatar Aang", "alice")
    if transformed:
        # Staging the back face up, the way a real transform leaves it (CR
        # 701.27a) - the transform itself is test_optional_transform_payoff's.
        aang.transform()
        assert aang.name == "Aang, Master of Elements"
    return scenario


def _cost(scenario, name: str, username: str = "alice") -> str:
    return str(scenario.cast(name, username).total_cost.mana)


def test_the_reader_keeps_every_symbol():
    effect = cost_modifier_effect(AANG_STATIC)
    assert effect is not None
    assert effect.kind is CostModifierKind.SYMBOL_DECREASE
    assert effect.reduction == "{W}{U}{B}{R}{G}"


def test_a_two_mana_creature_costs_nothing():
    """Grizzly Bears {1}{G}: {G} takes the {G}; {W}{U}{B}{R} find no pip of
    their colour and each take one generic (118.7b) - {1} has only one to give,
    so the cost is {0} (CR 601.2f)."""
    scenario = _aang_board(["Grizzly Bears"])
    assert _cost(scenario, "Grizzly Bears") in ("", "{0}")


def test_a_double_white_pip_keeps_one_white():
    """Serra Angel {3}{W}{W}: one {W} off the two white pips (118.7c's excess
    is zero), {U}{B}{R}{G} take four generic off {3} - the white pip the one
    {W} could not reach stays."""
    scenario = _aang_board(["Serra Angel"])
    assert _cost(scenario, "Serra Angel") == "{W}"


def test_a_single_coloured_pip_spell_is_free():
    scenario = _aang_board(["Lightning Bolt"])
    assert _cost(scenario, "Lightning Bolt") in ("", "{0}")


def test_hybrid_pips_are_not_a_colour_requirement():
    """Kitchen Finks {1}{G/W}{G/W}: a hybrid symbol is not a green or white
    requirement, so all five symbols reduce generic (118.7b) - the one generic
    goes and both hybrid pips stay."""
    scenario = _aang_board(["Kitchen Finks"])
    assert _cost(scenario, "Kitchen Finks") == "{G/W}{G/W}"


def test_an_x_spell_pays_its_announced_x_less_four():
    """Fireball {X}{R} with X announced as 6 (CR 107.3a: any X in the mana
    cost "equals the announced value"): the {R} takes the red pip and the other four symbols
    take four of the six generic (118.7b) - {2} left."""
    scenario = _aang_board(["Fireball"])
    casting = scenario.cast("Fireball", "alice")
    casting.x_value = 6
    assert str(casting.total_cost.mana) == "{2}"


def test_mana_value_is_unchanged():
    """The ruling on Avatar Aang: "The mana value of the spell remains
    unchanged, no matter what the total cost to cast it was." (CR 202.3)"""
    scenario = _aang_board(["Serra Angel"])
    angel = scenario.find("Serra Angel", Zone.HAND, "alice")
    assert angel.mana_value == 5


def test_a_spell_cast_for_nothing_actually_resolves():
    scenario = _aang_board(["Grizzly Bears"])
    scenario.cast_and_resolve("Grizzly Bears")
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_opponents_spells_are_not_reduced():
    """ "Spells *you* cast" - bob's Lightning Bolt costs its full {R}."""
    scenario = _aang_board([], bob_hand=["Lightning Bolt"])
    assert _cost(scenario, "Lightning Bolt", "bob") == "{R}"


def test_the_front_face_has_no_reduction():
    """CR 712.8d: with the front face up, the permanent has only the front
    face's characteristics - Avatar Aang prints no cost reduction."""
    scenario = _aang_board(["Serra Angel"], transformed=False)
    assert _cost(scenario, "Serra Angel") == "{3}{W}{W}"


# --------------------------------------------------------------------------
# The Immortal Sun - the same reader, one generic symbol
# --------------------------------------------------------------------------


def _sun_board(hand: list[str], bob_hand: list[str] | None = None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island"] * 5, hand=hand, battlefield=["The Immortal Sun"])
        .player("bob", library=["Island"] * 5, hand=bob_hand or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_immortal_sun_reads_as_a_one_generic_reduction():
    effect = cost_modifier_effect("Spells you cast cost {1} less to cast.")
    assert effect is not None
    assert effect.kind is CostModifierKind.SYMBOL_DECREASE
    assert effect.reduction == "{1}"


def test_immortal_sun_takes_one_generic_off():
    scenario = _sun_board(["Serra Angel"])
    assert _cost(scenario, "Serra Angel") == "{2}{W}{W}"


def test_immortal_sun_never_touches_a_coloured_pip():
    """CR 118.7a: a generic reduction leaves Lightning Bolt's {R} alone."""
    scenario = _sun_board(["Lightning Bolt"])
    assert _cost(scenario, "Lightning Bolt") == "{R}"


def test_immortal_sun_does_not_reduce_an_opponents_spell():
    scenario = _sun_board([], bob_hand=["Mana Leak"])
    assert _cost(scenario, "Mana Leak", "bob") == "{1}{U}"


def test_the_colour_only_template_is_a_different_ability():
    """ "This effect reduces only the amount of colored mana you pay." is a
    different reduction (no 118.7b spill into generic), so a type-qualified
    line carrying it is never read as this one."""
    effect = cost_modifier_effect(
        "Legendary spells you cast cost {R}{G} less to cast. This effect reduces only "
        "the amount of colored mana you pay."
    )
    assert effect is None or effect.kind is not CostModifierKind.SYMBOL_DECREASE
