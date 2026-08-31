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
  An engine gap. Frontline Heroism's "create a 1/1 red Soldier creature token
  with haste, then copy that spell. The copy targets that token." is the
  control card here: the trailing "targets" is `machines/targeting.
  profile_for_text`'s own signal of an attempted-but-unread restriction, even
  though the sentence names no target of its own at all (the *copy* is what
  targets, an artifact of copying CR 707.2, not this ability's own CR 603.3d
  announcement) - exactly the "recognised-as-attempted but not understood"
  shape this notice exists to keep audible rather than indistinguishable from
  "nothing to target". Aeronaut Cavalry's "put a +1/+1 counter on another
  target Soldier you control" used to be this file's control card: a *bare,
  single* CR 205.3m creature-type word used as the target noun, deliberately
  left unread by `_read_subtype_list`. `machines/targeting.py` now reads that
  singular-subtype shape too (`_MASS_SUBTYPE_SUBJECT_RE`'s sibling read for a
  *target*, not a mass pump - see `scenarios/test_subtype_restricted_
  targeting.py`), so Aeronaut Cavalry's own trigger is `understood=True` and
  no longer exercises this path; Frontline Heroism, still genuinely unread,
  takes over as the fixture. Its own CAST_SPELL condition ("a spell that
  targets only a single creature you control") never actually matches in a
  real game either - `_types_match` misreads the word "creature" in that
  relative clause as a "cast a creature spell" restriction, a second,
  unrelated gap this file is not about - so the `AbilityOnStack` below is
  built directly off the card's own real, parsed `TriggeredAbility` and
  queued straight onto `pending_triggers`, the same "real card, hand-placed
  state" staging `test_token_effect_parser.py` already uses, rather than
  through a cast this engine would not actually trigger on yet.
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
from magic_cards_model.machines.abilities import TriggeredAbility, TriggerEvent, parse_abilities
from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack, TargetingNoticeKind
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _queue_frontline_heroisms_cast_trigger(scenario: Scenario) -> None:
    """Put Frontline Heroism's real, printed CAST_SPELL `TriggeredAbility`
    straight onto `pending_triggers`, bypassing the (separate, unrelated)
    reason it never fires off a real cast - see the module docstring."""
    (source,) = [p for p in scenario.game.battlefield if p.name == "Frontline Heroism"]
    triggered_ability = next(
        a
        for a in parse_abilities(card("Frontline Heroism"))
        if isinstance(a, TriggeredAbility) and a.event is TriggerEvent.CAST_SPELL
    )
    scenario.game.pending_triggers.append(
        AbilityOnStack(
            kind=AbilityKind.TRIGGERED,
            ability=triggered_ability,
            source_id=source.id,
            source_name="Frontline Heroism",
            controller="alice",
        )
    )


def _frontline_heroism_on_the_battlefield() -> Scenario:
    """Frontline Heroism, its own ETB trigger already drained, so only the
    CAST_SPELL trigger queued by the test itself is on `pending_triggers`."""
    scenario = Scenario().player("alice", battlefield=["Frontline Heroism"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    scenario.game.targeting_notices.clear()
    return scenario


def test_an_unparsed_restriction_is_logged_not_silent():
    """Frontline Heroism's own copy-target sentence cannot be read - and now
    says so."""
    scenario = _frontline_heroism_on_the_battlefield()
    _queue_frontline_heroisms_cast_trigger(scenario)
    scenario.game.put_triggers_on_stack()

    (ability,) = scenario.game.abilities_on_stack
    assert ability.targets == [], "still no target chosen - CR 603.3d's outcome is unchanged"

    (notice,) = scenario.game.targeting_notices
    assert notice.kind is TargetingNoticeKind.UNPARSED
    assert notice.source_name == "Frontline Heroism"


def test_a_regression_to_silent_no_op_would_fail_this():
    """The negative case: if `_ask_trigger_targets` ever again just `return []`
    for an unreadable restriction, nothing would land in `targeting_notices`
    and this assertion catches it.
    """
    scenario = _frontline_heroism_on_the_battlefield()
    _queue_frontline_heroisms_cast_trigger(scenario)
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
