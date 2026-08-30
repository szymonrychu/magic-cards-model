"""Scenario: an unreadable target restriction fails loudly, not silently (CR 603.3d).

The defect this file is written against: `Game._ask_trigger_targets` used to
`return []` unconditionally whenever `TargetingProfile.understood` was False -
the parser's own signal that it could not read the restriction at all. White
Orchid Phantom's "destroy up to one target nonbasic land" hit exactly this
before the supertype fix in `test_targeting_adjectives.py`/`machines/targeting.py`
existed: it went on the stack with `targets: []`, resolved, and destroyed
nothing, with no decision offered and nothing anywhere to say why.

The fix, in `Game._ask_trigger_targets`: the two genuinely different reasons a
trigger ends up with no targets are told apart and both are recorded on
`Game.targeting_notices` (`TargetingNotice`/`TargetingNoticeKind` in
`machines/triggers.py`):

- `UNPARSED` - the restriction itself could not be read (`understood=False`).
  An engine gap. Slayer of the Wicked's "destroy target Vampire, Werewolf, or
  Zombie" is the control card here: a subtype list, explicitly out of scope
  for this wave (`docs/engine-coverage.md`), so it stays unparsed even after
  the `another`/supertype/comma fixes elsewhere in this suite - which is
  exactly why it is the right regression fixture for "the *next* unparsed
  shape is still audible".
- `NO_LEGAL_TARGET` - the restriction parsed fine, but nothing on the
  battlefield satisfies it. A legitimate game state (CR 608.2d's own
  "nobody says otherwise" default), not a bug, and not CR 608.2b's fizzle -
  608.2b only ever concerns a target that was *chosen* and later found
  illegal, never one that was never offered a chance to be chosen at all.

Both cases still leave the ability on the stack with no targets (this wave
does not change CR 603.3d's outcome, only makes it observable), so `targets ==
[]` remains the assertion for "no target chosen" - the new assertion is that
`Game.targeting_notices` now explains why, and the two reasons produce
different `TargetingNoticeKind` values.
"""

from magic_cards_model.machines.triggers import TargetingNoticeKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_an_unparsed_restriction_is_logged_not_silent():
    """Slayer of the Wicked's subtype list cannot be read - and now says so."""
    scenario = (
        Scenario()
        .player("alice", hand=["Slayer of the Wicked"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.put_onto_battlefield("Slayer of the Wicked")
    scenario.game.put_triggers_on_stack()

    (ability,) = scenario.game.abilities_on_stack
    assert ability.targets == [], "still no target chosen - CR 603.3d's outcome is unchanged"

    (notice,) = scenario.game.targeting_notices
    assert notice.kind is TargetingNoticeKind.UNPARSED
    assert notice.source_name == "Slayer of the Wicked"

    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD, "nothing was destroyed - there was never a target"


def test_a_regression_to_silent_no_op_would_fail_this():
    """The negative case: if `_ask_trigger_targets` ever again just `return []`
    for an unreadable restriction, nothing would land in `targeting_notices`
    and this assertion catches it.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Slayer of the Wicked"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.put_onto_battlefield("Slayer of the Wicked")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.targeting_notices, "an unparsed restriction must be logged, not silent"


def test_no_legal_target_is_logged_differently_from_unparsed():
    """White Orchid Phantom, parsed correctly, with nothing nonbasic to hit.

    Both of alice's opponent's lands are basic, so `_legal_target_candidates`
    comes back empty even though the restriction was read fine - that is
    `NO_LEGAL_TARGET`, not `UNPARSED`, and the two must not collapse into one
    notice kind.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["White Orchid Phantom"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    forest = scenario.creature("Forest", "bob")

    scenario.put_onto_battlefield("White Orchid Phantom")
    scenario.game.put_triggers_on_stack()

    (ability,) = scenario.game.abilities_on_stack
    assert ability.targets == []

    (notice,) = scenario.game.targeting_notices
    assert notice.kind is TargetingNoticeKind.NO_LEGAL_TARGET
    assert notice.source_name == "White Orchid Phantom"

    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    assert forest.zone is Zone.BATTLEFIELD, "a basic land was never a legal target"
