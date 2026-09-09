"""Sunburst: entering with counters for each color of mana spent (CR 702.44).

CR 702.44a: "Sunburst is a static ability that functions as an object is
entering the battlefield. 'Sunburst' means 'If this object is entering as a
creature, ignoring any type-changing effects that would affect it, it enters
with a +1/+1 counter on it for each color of mana spent to cast it. Otherwise,
it enters with a charge counter on it for each color of mana spent to cast
it.'"

CR 702.44b: "Sunburst adds counters only if the object with sunburst is
entering the battlefield from the stack as a resolving spell and only if one
or more colored mana was spent on its costs, including additional or
alternative costs."

The count comes from `Game.cast_record(...).mana_spent` - the same record
`Game._apply_mana_spend_effects`/CR 601.2h's own bookkeeping already
maintains for every cast - read as an "enters ..." replacement effect through
`machines/replacement.py::_self_enters_modifiers`, alongside every other
CR 614.1c "enters with N counters" clause. Sunburst is not itself a sentence
on the card (it is a keyword whose CR 702.44a expansion is reminder text, CR
207.2), so it is read off `Card.keywords` directly rather than off a parsed
clause the way `_ENTERS_WITH` reads a printed "enters with" sentence.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.

Engineered Explosives ({X}, an artifact - the "otherwise" / charge-counter
half) is the assigned card. Solarion ({7}, an artifact *creature* - the "as a
creature" / +1/+1-counter half) is not in the deck pool and not named in the
brief, and its own printed cost has no colored symbols at all (same as
Engineered Explosives) - proving the count comes from mana actually *spent*,
never from the printed cost, and that the creature/noncreature branch reads
`Card.types` generally rather than by name.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def board(**kwargs) -> Scenario:
    return Scenario().manual_turn_based_actions().player("alice", **kwargs).player("bob")


# -- the "otherwise" / charge-counter half, on a noncreature artifact --------


def test_engineered_explosives_enters_with_a_charge_counter_per_color_spent():
    scenario = board(
        hand=["Engineered Explosives"],
        battlefield=["Mountain", "Island", "Forest"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Engineered Explosives")
    casting.choose_modes([], x_value=3)
    casting.determine_cost(x_value=3)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Island", "Forest"))
    scenario.put_on_stack(casting)
    explosives = scenario.resolve_top()

    assert explosives.zone.value == "battlefield"
    assert explosives.counters["charge"] == 3
    assert explosives.counters["+1/+1"] == 0, "not a creature - CR 702.44a's second branch"


def test_engineered_explosives_counts_colors_not_mana_spent():
    """Two Mountains still spend one color, not two (CR 702.44a: "for each
    **color**", not for each mana)."""
    scenario = board(
        hand=["Engineered Explosives"],
        battlefield=["Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Engineered Explosives")
    casting.choose_modes([], x_value=2)
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    explosives = scenario.resolve_top()

    assert explosives.counters["charge"] == 1


def test_no_colored_mana_spent_enters_with_no_counters():
    """CR 702.44b: "only if one or more colored mana was spent" - Wastes
    would be the printed example; a colorless-producing land generally is,
    but nothing in the pool taps for pure colorless at will, so this pays
    the whole X with life instead (Phyrexian-adjacent staging is out of
    scope) - a spell with x_value 0 spends nothing at all, which is the
    plainest way to show zero colors."""
    scenario = board(hand=["Engineered Explosives"], battlefield=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Engineered Explosives")
    casting.choose_modes([], x_value=0)
    casting.determine_cost(x_value=0)
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    explosives = scenario.resolve_top()

    assert explosives.counters["charge"] == 0


# -- generality: a second, un-named sunburst printing, on the creature branch


def test_solarion_enters_as_a_creature_with_a_plus_one_plus_one_counter_per_color():
    scenario = board(
        hand=["Solarion"],
        battlefield=["Mountain", "Island", "Forest", "Plains", "Swamp", "Mountain", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Solarion")
    payment = casting.begin_paying()
    scenario.pay_with(
        payment,
        *scenario.untapped_sources(
            "Mountain", "Island", "Forest", "Plains", "Swamp", "Mountain", "Island"
        ),
    )
    scenario.put_on_stack(casting)
    solarion = scenario.resolve_top()

    assert solarion.counters["+1/+1"] == 5, "five distinct colors spent: W U B R G"
    assert solarion.counters["charge"] == 0
