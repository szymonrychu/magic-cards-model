"""Scenario: Prismatic Ending - "Converge — Exile target nonland permanent if
its mana value is less than or equal to the number of colors of mana spent to
cast this spell."

The count of colors spent is not fixed until the spell's cost is fully paid
(CR 601.2g-i), which happens *after* targets are announced (CR 601.2c) - the
opposite order from Fatal Push's own mana-value condition, which is why this
is not built the same way. `machines/targeting.py` reads the converge clause
out of the way (`_COLORS_OF_MANA_SPENT_CONDITION`) rather than treating it as
a comparison, so the target stays the plain "target nonland permanent" - any
nonland permanent may be targeted, and a *land* is refused at CR 601.2c - and
the whole mana-value condition is judged once, at resolution, off
`CastRecord.mana_spent` (colour keys only).

It used to be unreadable instead (`_COMPARISON_UNREADABLE`), which failed the
whole phrase closed: `understood=False` meant no targeting check ran at all,
so a land was an accepted announcement. See
`test_prismatic_ending_refuses_a_land_at_announcement`.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 105.2a/105.2b/105.2c** - one, two-or-more, and zero colors.
- **CR 601.2g-i** - determining and paying the total cost, after targets are
  announced at CR 601.2c.
- **CR 701.13a** - "To exile an object, move it to the exile zone from
  wherever it is."
- Converge is an ability word (CR 207.2c); `knowledge_search` found no
  further numbered rule for it this session, so none is cited.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_main(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


def _cast_with_x(scenario, x_value: int, *sources, targets, username: str = "alice") -> Casting:
    """Announce Prismatic Ending, paying an explicit X, so the test controls
    exactly how many colors of mana are spent.
    """
    casting = scenario.cast("Prismatic Ending", username=username)
    casting.choose_targets(targets)
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    return casting


def test_prismatic_ending_exiles_a_mana_value_1_permanent_paying_one_color():
    """One color of mana spent (just the {W}) - mana value 1 or less is exiled."""
    scenario = (
        Scenario()
        .player("alice", hand=["Prismatic Ending"], battlefield=["Plains"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    _to_main(scenario)
    mystic = scenario.creature("Elvish Mystic", "bob")

    (plains,) = scenario.untapped_sources("Plains")
    _cast_with_x(scenario, 0, plains, targets=[mystic])
    scenario.resolve_top()

    assert mystic.zone is Zone.EXILE


def test_prismatic_ending_does_not_exile_a_mana_value_2_permanent_with_one_color():
    """The spell still resolves (the target was legal to announce), but the
    condition is false at resolution - one color spent is not enough for a
    mana value 2 permanent, so nothing happens to it. CR 608.2c: an effect
    whose condition is not met simply does not act, it does not fizzle
    outright (the target was legal, just unaffected).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Prismatic Ending"], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Gray Merchant of Asphodel"])
        .build()
    )
    _to_main(scenario)
    merchant = scenario.creature("Gray Merchant of Asphodel", "bob")
    assert merchant.card.cmc >= 2

    sources = scenario.untapped_sources("Plains", "Plains")
    _cast_with_x(scenario, 1, *sources, targets=[merchant])
    scenario.resolve_top()

    assert merchant.zone is Zone.BATTLEFIELD


def test_prismatic_ending_exiles_a_mana_value_2_permanent_with_two_colors():
    """Two distinct colors spent widens the threshold to mana value 2 - the
    same permanent the previous test could not touch is exiled once alice
    pays with a second color.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Prismatic Ending"], battlefield=["Plains", "Island"])
        .player("bob", battlefield=["Servant of the Conduit"])
        .build()
    )
    _to_main(scenario)
    servant = scenario.creature("Servant of the Conduit", "bob")
    assert servant.card.cmc == 2.0

    sources = scenario.untapped_sources("Plains", "Island")
    _cast_with_x(scenario, 1, *sources, targets=[servant])
    scenario.resolve_top()

    assert servant.zone is Zone.EXILE


def test_prismatic_ending_does_not_count_generic_mana_as_a_color():
    """Colorless (generic) mana never counts as one of CR 105.1's five colors
    (CR 105.2c) - paying the {X} with a colorless source does not add to the
    count, only the coloured symbols spent on top of it do.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Prismatic Ending"],
            battlefield=["Plains", "Wastes"],
        )
        .player("bob", battlefield=["Servant of the Conduit"])
        .build()
    )
    _to_main(scenario)
    servant = scenario.creature("Servant of the Conduit", "bob")
    assert servant.card.cmc == 2.0

    sources = scenario.untapped_sources("Plains", "Wastes")
    _cast_with_x(scenario, 1, *sources, targets=[servant])
    scenario.resolve_top()

    # Only white was spent as a color (Wastes paid the generic {X}=1 with
    # colorless mana) - the count of colors is one, not enough for a mana
    # value 2 permanent. Miscounting colorless as a color here would wrongly
    # exile it.
    assert servant.zone is Zone.BATTLEFIELD


def test_prismatic_ending_can_target_a_land_free_artifact():
    """ "Target nonland permanent" reaches any permanent type but a land -
    an artifact is exiled the same way a creature is, once the mana-value
    condition holds.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Prismatic Ending"], battlefield=["Plains"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    _to_main(scenario)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    assert ring.card.cmc == 1.0

    (plains,) = scenario.untapped_sources("Plains")
    _cast_with_x(scenario, 0, plains, targets=[ring])
    scenario.resolve_top()

    assert ring.zone is Zone.EXILE


def test_prismatic_ending_refuses_a_land_at_announcement():
    """ "Target **nonland** permanent" - and now the announcement says so.

    Measured before this test existed: `machines/targeting.py` read the
    trailing "if its mana value is less than or equal to the number of colors
    of mana spent to cast this spell" as the start of a mana-value comparison
    it could not finish, failed the whole phrase closed, and so reported
    `understood=False` for the card - which meant *no* targeting check at all,
    and a land was an accepted announcement. The converge clause is now read
    out of the way (it is a condition on the effect, not on the target - CR
    601.2c announces targets before CR 601.2h pays the cost that decides how
    many colors were spent), leaving the plain "target nonland permanent" this
    refusal enforces at CR 601.2c.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Prismatic Ending"], battlefield=["Plains"])
        .player("bob", battlefield=["Island"])
        .build()
    )
    _to_main(scenario)
    island = scenario.find("Island", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Prismatic Ending", username="alice")
    with pytest.raises(ValueError, match="land"):
        casting.choose_targets([island])
