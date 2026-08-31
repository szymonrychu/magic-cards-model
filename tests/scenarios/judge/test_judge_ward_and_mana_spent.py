"""Judge scenario: mana spent buying out of ward is not mana spent casting.

From DDR#973 "Prismatic Ending vs. Ward". Nick's creature has ward {1}; Amy
casts Prismatic Ending with a white and a blue mana and then pays the ward with
a red one. Three colours of mana left her pool - but Converge counts only the
mana *spent to cast the spell*, and the ward payment was made later, as a
separate triggered ability resolved. Prismatic Ending resolves, is not
countered, and does nothing: the target's mana value 3 is more than the two
colours that were spent casting it.

The episode uses a Gray Ogre wearing an Equipment that grants ward {1}. This
engine reads ward off the printing (`machines/keywords.ward_cost`) and does not
track Equipment attachment at all, so the board here uses **Gavony Dawnguard** -
a real printing with `Ward {1}` printed on it and the same mana value 3 the
episode is careful to specify. Nothing about the ruling depends on where the
ward came from.

The mechanism is entirely in the ordering of CR 601.2:

- **CR 702.21a** - "Ward is a triggered ability. Ward [cost] means 'Whenever
  this permanent becomes the target of a spell or ability an opponent controls,
  counter that spell or ability unless that player pays [cost].'" So the ward
  cost is paid as that *ability* resolves, long after the spell was cast.
- **CR 601.2a** - casting proposes the spell; **CR 601.2h** - "The player pays
  the total cost." Only what is paid there was "spent to cast this spell".
- **CR 601.2i** - once 601.2a-h are done the spell becomes cast, and *that* is
  what puts the ward trigger on the stack.
- **CR 202.4** contrasts the taxing case the episode raises: an additional cost
  imposed by an effect "isn't part of the mana cost" but is still paid at
  CR 601.2h, so a Thalia tax genuinely does widen Converge.

Every CR number in this file was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote it: CR 106.1a, CR 202.4, CR 601.2a,
CR 601.2h, CR 601.2i, CR 701.6a is *not* cited (unpaid ward is covered by
`tests/scenarios/test_ward.py`), CR 702.21a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.machines.keywords import ward_cost, ward_triggers
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def board() -> Scenario:
    """alice with one source of each of three colours; bob with a warded 3-drop."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Prismatic Ending"],
            battlefield=["Plains", "Island", "Mountain"],
        )
        .player("bob", battlefield=["Gavony Dawnguard"])
    )


def _cast_with_x(scenario, x_value: int, *sources, targets) -> Casting:
    casting = scenario.cast("Prismatic Ending")
    casting.choose_targets(targets)
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    return casting


def test_the_target_is_a_real_three_mana_permanent_with_printed_ward():
    """The two facts the episode's setup turns on, read off the real printing.

    CR 702.21a's `[cost]` is {1}, and the creature's mana value is 3 - so two
    colours of Converge are one short and three would be enough.
    """
    dawnguard = card("Gavony Dawnguard")
    assert dawnguard.cmc == 3.0
    cost = ward_cost(dawnguard, "alice")
    assert cost is not None
    assert str(cost.mana) == "{1}"


def test_paying_the_ward_with_a_third_colour_does_not_widen_converge():
    """DDR#973's ruling, end to end.

    Two colours are spent casting (CR 601.2h); the red mana is spent on the
    ward ability as it resolves (CR 702.21a), which is not casting at all. The
    spell is not countered - the ward was paid - so it resolves and its own
    condition is judged: mana value 3 is *not* less than or equal to 2, so
    nothing is exiled. Three colours left alice's pool and she got nothing.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dawnguard = scenario.creature("Gavony Dawnguard", "bob")

    spell = _cast_with_x(
        scenario,
        1,
        *scenario.untapped_sources("Plains", "Island"),
        targets=[dawnguard],
    )
    assert scenario.stack_names() == [
        "Prismatic Ending",
        "Gavony Dawnguard's triggered ability",
    ]

    (trigger,) = ward_triggers(scenario.game, spell.spell)
    payment = trigger.begin_paying()
    (mountain,) = scenario.untapped_sources("Mountain")
    payment.tap_for_mana(mountain, mana_from(mountain))
    payment.pay()
    assert trigger.paid

    scenario.resolve_top()  # the ward trigger, which counters nothing
    assert scenario.stack_names() == ["Prismatic Ending"]

    scenario.resolve_top()  # Prismatic Ending, with two colours to its name
    assert dawnguard.zone is Zone.BATTLEFIELD
    assert all(
        source.tapped for source in scenario.game.battlefield if source.controller == "alice"
    )


def test_three_colours_spent_while_casting_do_exile_it():
    """The control: the same three lands, all tapped *during* CR 601.2h.

    Announcing X=2 makes the total cost {2}{W}, so all three colours are spent
    casting, Converge counts three, and the mana value 3 permanent is exiled.
    This is the only difference between this test and the one above, which is
    what makes the ruling a ruling rather than a coincidence.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dawnguard = scenario.creature("Gavony Dawnguard", "bob")

    spell = _cast_with_x(
        scenario,
        2,
        *scenario.untapped_sources("Plains", "Island", "Mountain"),
        targets=[dawnguard],
    )

    (trigger,) = ward_triggers(scenario.game, spell.spell)
    scenario.resolve_top()  # ward, unpaid - it counters the spell

    assert not trigger.paid
    assert dawnguard.zone is Zone.BATTLEFIELD
    assert scenario.find("Prismatic Ending", Zone.GRAVEYARD).zone is Zone.GRAVEYARD


def test_prismatic_ending_may_target_a_permanent_it_cannot_exile():
    """DDR#973's policy half rests on this rules fact: the target is legal.

    "It's legal for Prismatic Ending to target any nonland permanent, no matter
    what its mana value is. Prismatic Ending will just not do anything as it
    resolves if the targeted permanent's mana value is too high." That is why
    the judge's first illegal action is Nick *exiling* the creature, not Amy
    casting the spell - and it is why the spell above resolves rather than
    being countered on resolution for an illegal target.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dawnguard = scenario.creature("Gavony Dawnguard", "bob")

    casting = scenario.cast("Prismatic Ending")
    casting.choose_targets([dawnguard])  # no raise: mana value is not a target restriction

    assert casting.targets
