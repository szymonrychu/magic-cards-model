"""Scenario: Hidden Blade's own "When this Equipment enters, attach it to
target creature you control. If that creature is an Assassin, it gains
deathtouch until end of turn." - two instructions in the order written (CR
608.2c), the second gated on a characteristic of the object the first one
just attached to.

`_ATTACH_SELF_TO_TARGET_RE`'s own `.+$` tail used to match straight through
this sentence's trailing period and swallow the whole "If that creature is
an Assassin, ..." sentence as though it were still part of "target creature
you control" - the attach ran, but the rider was silently dropped with no
notice anywhere, on every card printing this shape, not only Hidden Blade.
`_parse_attach_self_then_conditional_rider_clause` reads the two sentences
as the pair they are: the attach (unchanged), then the rider's own quality
check, read by handing `Game.condition_holds` the just-attached-to creature
as `source` rather than the ability's own source (Hidden Blade itself) - the
identical `_is_quality` reader that already answers "it is an Assassin" for
every other card printing that shape, just given a different object than
usual.

No second real Scryfall printing of this exact "attach ..., then a rider
whose condition is the attached-to creature's own quality" shape turned up
in a search of every "attach it to target creature" printing (`Relic Axe`'s
"If it's a Warrior..." is a different mechanic - a *static* granted bonus
read live off the layer system, not part of the ETB instruction at all).
The fix is still written generically over the quality word and the rider's
own effect (`_is_quality`'s whole vocabulary; `_parse_referent_object_clause`
for the rider), not fitted to "Assassin"/"gains deathtouch" - see both
branches below and `_attach_self_to_target_effect`'s own docstring.

Rules verified with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 701.3a** - to attach a permanent to an object or player.
- **CR 608.2c** - the controller follows every instruction in the order
  written; a later instruction may depend on an earlier one's own result.
- **CR 613.5** - a permanent's subtypes are computed continuously, so
  "is an Assassin" is asked of the board as the rider actually runs.
- **CR 205.3m** - creature types (Assassin among them) are subtypes.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from tests.scenarios.harness import Scenario


def _board(target: str) -> tuple[Scenario, object]:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hidden Blade"],
            battlefield=[target, "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    creature = scenario.creature(target, "alice")
    return scenario, creature


def test_attaching_to_an_assassin_grants_deathtouch():
    scenario, gloom_ripper = _board("Gloom Ripper")
    scenario.choose_trigger_targets("Hidden Blade", [gloom_ripper])
    blade = scenario.cast_and_resolve(
        "Hidden Blade", *scenario.untapped_sources("Mountain", "Mountain")
    )
    scenario.pass_until_resolved()

    assert blade.attached_to == gloom_ripper.id
    assert has_keyword(gloom_ripper, "deathtouch", scenario.game)


def test_attaching_to_a_non_assassin_grants_nothing_extra():
    scenario, bears = _board("Grizzly Bears")
    scenario.choose_trigger_targets("Hidden Blade", [bears])
    blade = scenario.cast_and_resolve(
        "Hidden Blade", *scenario.untapped_sources("Mountain", "Mountain")
    )
    scenario.pass_until_resolved()

    assert blade.attached_to == bears.id, "the attach itself still ran"
    assert not has_keyword(bears, "deathtouch", scenario.game)


def test_the_rider_still_applies_when_the_equipment_is_destroyed_before_its_trigger_resolves():
    """CR 608.2c/608.2b: "that creature" is the target this trigger already
    announced going on the stack (CR 603.3d) - if Hidden Blade itself is
    destroyed before its own ETB trigger resolves, the attach can no longer
    happen (there is no Equipment left to move), but the target is still
    legal and the rider still checks it."""
    from magic_cards_model.models import Zone

    scenario, gloom_ripper = _board("Gloom Ripper")
    scenario.choose_trigger_targets("Hidden Blade", [gloom_ripper])
    blade = scenario.cast_and_resolve(
        "Hidden Blade", *scenario.untapped_sources("Mountain", "Mountain")
    )
    scenario.game.destroy(blade)
    assert blade.zone is not Zone.BATTLEFIELD

    scenario.pass_until_resolved()

    assert blade.attached_to is None, "gone before it could attach anything"
    assert has_keyword(gloom_ripper, "deathtouch", scenario.game)
