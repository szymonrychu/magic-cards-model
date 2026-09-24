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
  real). A sweep of all 738 fixture cards once found three triggered
  abilities `profile_for_text` still reported `understood=False` for -
  **Bonecrusher Giant**, **Loki, God of Mischief** and **Stirring
  Hopesinger** - each a "becomes the target of ..." / "that targets ..."
  *condition* the parser mistook for an attempted targeting restriction of
  the ability's own. Task C02-T7's own fix for Speedball, New Warrior's
  identical shape closed all three at once: `Game._ask_trigger_targets` now
  reads `TriggeredAbility.effect` rather than an ability's whole printed
  text, so a condition's own stray "target" word is never scanned at all.
  Bonecrusher Giant is this file's live fixture for that fix, played out
  for real.
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

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import TargetingNoticeKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_bonecrusher_giants_condition_is_no_longer_misread_as_a_target():
    """Bonecrusher Giant, bolted: the trigger fires with nothing to point at
    - and, as this test's own predecessor predicted it should once fixed, no
    longer through a false engine gap.

    Its printed trigger (verified with `resolve_cards`) is "Whenever this
    creature becomes the target of a spell, this creature deals 2 damage to
    that spell's controller." "becomes the target of a spell" is CR 603.1's
    trigger *condition* - a fact about something that already happened to
    this permanent - never a CR 601.2c target this ability's own controller
    is asked to choose. `Game._ask_trigger_targets` used to hand
    `profile_for_text` the ability's *whole* printed text, condition
    included, so the bare word "target" inside the condition read as an
    attempted-but-unreadable targeting restriction of the ability's own
    (`understood=False`, `TargetingNoticeKind.UNPARSED`) - task C02-T7's own
    fix for Speedball, New Warrior's identical shape ("a player casts a
    spell that targets Speedball") widened this to every triggered ability:
    `_ask_trigger_targets` now reads `TriggeredAbility.effect` - the words
    *after* the condition, already split off by `machines/abilities.py`'s
    own parser - which names no target at all here, so the profile comes
    back `understood=True` with no requirements and no notice is recorded.
    A sweep of all 738 fixture cards found exactly three triggered abilities
    shaped this way - Bonecrusher Giant, Loki, God of Mischief and Stirring
    Hopesinger - and all three now read the same correct way.
    """
    scenario = (
        Scenario()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("alice", battlefield=["Bonecrusher Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Bonecrusher Giant", "alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[giant])
    scenario.game.put_triggers_on_stack()

    (ability,) = scenario.game.abilities_on_stack
    assert ability.source_name == "Bonecrusher Giant"
    assert ability.targets == []
    assert scenario.game.targeting_notices == []


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
