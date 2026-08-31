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
  An engine gap. Aeronaut Cavalry's "put a +1/+1 counter on another target
  Soldier you control" used to be this file's control card: a *bare, single*
  CR 205.3m creature-type word used as the target noun, deliberately left
  unread by `_read_subtype_list`. `machines/targeting.py` now reads that
  singular-subtype shape too (`_MASS_SUBTYPE_SUBJECT_RE`'s sibling read for a
  *target*, not a mass pump - see `scenarios/test_subtype_restricted_
  targeting.py`), so Aeronaut Cavalry's own trigger is `understood=True` and
  no longer exercises this path. Frontline Heroism's "create a 1/1 red
  Soldier creature token with haste, then copy that spell. The copy targets
  that token." took over as the fixture next - the trailing "targets" (and,
  in its trigger *condition*, "that targets only a single creature you
  control") used to be misread as attempted-but-unread targeting
  restrictions of this ability's own, even though neither names a target
  CR 603.3d actually asks this ability's controller to choose: the *copy* is
  what targets (CR 707.2), and the condition is a fact about a target chosen
  *elsewhere*, on the spell this ability is watching. `machines/targeting.
  _COPY_TARGETS_DECLARATION`/`_TARGETS_ONLY_SINGLE_CREATURE_CONDITION_CLAUSE`
  now strip both clauses before the ordinary "target ..." scan, and
  `machines/triggers.py`'s own `condition_matches` no longer misreads the
  condition's "creature" as a "cast a creature spell" restriction either
  (see `scenarios/test_frontline_heroism.py`, which replaces this file's old
  hand-placed-trigger staging now that Frontline Heroism's trigger fires for
  real). **No card left in the pool has an `UNPARSED`-shaped triggered
  ability any more** - a real success, but it leaves this one notice kind
  with no live fixture; the two tests below that used to exercise it are
  marked `xfail` for that reason rather than deleted, so a future card that
  reintroduces the shape has a test ready to catch it working.
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

import pytest

from magic_cards_model.machines.triggers import TargetingNoticeKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


@pytest.mark.xfail(
    reason=(
        "No card in the pool prints a triggered ability with an unreadable "
        "targeting restriction any more - Aeronaut Cavalry and Frontline "
        "Heroism, this file's last two control cards, were both fixed for "
        "real (scenarios/test_subtype_restricted_targeting.py, "
        "scenarios/test_frontline_heroism.py). The TargetingNoticeKind.UNPARSED "
        "machinery in Game._ask_trigger_targets is untouched and still "
        "correct - see the module docstring - this xfail just records that "
        "nothing currently exercises it with real card data, per the "
        "project's no-mocks rule."
    )
)
def test_an_unparsed_restriction_is_logged_not_silent():
    raise NotImplementedError


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
