"""Echoing Deeps (CR 614.1c, CR 707.9b): "You may have this land enter tapped
as a copy of any land card in a graveyard, except it's a Cave in addition to
its other types."

A triage this session flagged a live wrong-board defect at parse and
registration level (not yet confirmed by actually playing a game, which is
what this file does): `machines/replacement._parse_copy_exception` returns
`None` both when a card prints no "except ..." tail at all *and* when it
prints one this parser cannot read - CR 707.9b's exception and the copy
itself are one atomic computation of copiable values ("The final set of
values for that characteristic becomes part of the copiable values of the
copy"), so the two `None`s are not the same fact, but both callers
(`machines/replacement.py`'s `_try_enters_as_copy` at parse time and
`_enters_as_copy` at resolution) read the field with `effect.copy_exception
or CopyException()`, which cannot tell "nothing was printed" from "something
was printed and I could not read it" - a fail-closed parser result read as a
fail-open default. Echoing Deeps' own tail - "it's a Cave in addition to its
other types" - has no power/toughness, and the only regex that reads a
type-adding tail (`_COPY_EXCEPT_PT_AND_TYPES`) required one, so the whole
tail fell through and Echoing Deeps copied the graveyard land without ever
becoming a Cave.

Confirmed live below: before the fix, `test_echoing_deeps_copies_a_graveyard_
land_and_gains_the_cave_type` failed - the copy entered as a plain Forest,
`"Cave" not in characteristics.subtypes`.

The fix has two parts:

1. **Fail closed, loudly.** `ReplacementEffect` now keeps the raw text of an
   "except ..." tail that failed to parse (`copy_exception_unparsed`)
   separately from "there was no tail at all". `_enters_as_copy` checks that
   field before ever building a copy and, when it is set, records a new
   `UnreadableCopyExceptionNotice` and skips the whole "enter as a copy"
   replacement rather than applying half of CR 707.9b's single computation -
   the permanent enters as itself (`test_enter_as_copy_exceptions.py`).
2. **Read the tail that is genuinely readable.** "it's a Cave in addition to
   its other types" is exactly `_COPY_EXCEPT_PT_AND_TYPES`'s existing shape
   with the power/toughness clause absent - CR 205.1b's "in addition to its
   other types" retaining-type language doesn't require a body at all, and a
   land's own exception naming only added types is a real, general shape, not
   a card-name special case. Making the power/toughness half of that regex
   optional is what makes Echoing Deeps' own graveyard-land copy actually
   correct, not merely honest about failing.

Blast radius, measured by scanning every printing in
`src/magic_cards_model/data/printings` for `"as a copy of"` combined with a
`", except"` tail: **three cards**, not just Echoing Deeps.

- **Echoing Deeps** - fixed by (2) above; this file's happy-path test.
- **Superior Spider-Man** - "except his name is Superior Spider-Man and he's
  a 4/4 Spider Human Hero in addition to his other types" already parses in
  full (a name plus a power/toughness-and-types clause, both readable before
  this change) and is untouched: `copy_exception` was never `None` for it, so
  neither the notice path nor the regex change changes its behaviour. See
  `tests/scenarios/judge/test_judge_copying.py`'s existing coverage.
- **Mockingbird** - "except it's a Bird in addition to its other types and it
  has flying" now reads in full (CR 707.9a's gained ability) and is covered by
  `test_enter_as_copy_mana_spent.py`; the fail-closed notice for a tail that
  still does not read is covered by `test_enter_as_copy_exceptions.py`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_echoing_deeps_copies_a_graveyard_land_and_gains_the_cave_type():
    """The real case: Echoing Deeps entering as a copy of a graveyard Forest.

    CR 707.2 copies Forest's own printed subtype and mana ability; CR 707.9b's
    "except ..." tail adds Cave on top (CR 205.1b's retaining form - "in
    addition to its other types" keeps Forest, it does not replace it), and
    the whole land enters tapped, per the printed "enter tapped as a copy of".
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Echoing Deeps"], graveyard=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    deeps = scenario.play_land("Echoing Deeps")

    assert deeps.zone is Zone.BATTLEFIELD
    characteristics = scenario.game.characteristics_of(deeps)
    # Asserted against the real printed subtype, never against the computed
    # answer this test exists to check.
    assert "Forest" in card("Forest").type_line
    assert "Forest" in characteristics.subtypes
    assert "Cave" in characteristics.subtypes
    assert scenario.game.unreadable_copy_exception_notices == []
    assert deeps.tapped is True
