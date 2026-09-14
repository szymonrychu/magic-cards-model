"""`_TAP_TARGET_THEN_NO_UNTAP_RE`/`_parse_tap_target_then_no_untap_clause`
beyond Tamiyo, Compleated Sage's own "Tap up to one target artifact or
creature. It doesn't untap during its controller's next untap step.":

- **Frost Breath** (real printing, instant): "Tap up to two target
  creatures. Those creatures don't untap during their controller's next
  untap step." - a *plural* count with no singular "it", which the old
  regex's hardcoded "up to \\S+ target" + "it doesn't" shape could not read
  at all (silent, per the number sweep).
- **Chill of the Grave** (real printing, instant): "Tap target creature. It
  doesn't untap during its controller's next untap step. Draw a card." - no
  "up to" at all (a single mandatory target), plus a third clause after the
  pair. Before this fix the regex's `up to \\S+` prefix was mandatory, so
  this fell through to the generic anaphoric-clause notice instead of
  resolving (per the number sweep).

Both are cast as spells, not activated abilities like Tamiyo, so the
two-sentence pair also has to be readable by `_parse_mixed_clauses`'s merge
chain (`_merge_tap_target_then_no_untap_clauses`), not only by the
whole-ability-text path `_ability_effect_or_notice` already used. Targets are
the caster's own creatures (as `test_tamiyo_compleated_sage.py` already does)
so `Game.untap_step` - which untaps only the active player's permanents,
CR 502.3 - actually exercises the withheld untap.

CR numbers verified this session with `mise run rules:find`:

- **CR 701.26a** - "To tap a permanent, turn it sideways from an upright
  position. Only untapped permanents can be tapped."
- **CR 701.43a** - exert's own "you choose to have it not untap during your
  next untap step" wording, reused for the mechanism (see
  `_parse_tap_target_then_no_untap_clause`'s own docstring).
- **CR 115.6** - "A spell or ability that requires targets may allow zero
  targets to be chosen."
- **CR 608.2b** - an illegal (already-gone) target is simply skipped.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Frost Breath"],
            battlefield=["Island", "Island", "Island", "Grizzly Bears", "Goblin Guide"],
        )
        .player("bob")
    )


def test_frost_breath_taps_two_targets_and_they_stay_tapped_through_the_next_untap():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    goblin = scenario.creature("Goblin Guide", "alice")
    assert not bears.tapped
    assert not goblin.tapped

    sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Frost Breath", *sources, targets=[bears, goblin])

    assert bears.tapped
    assert goblin.tapped
    assert bears.exerted
    assert goblin.exerted

    scenario.game.untap_step()
    assert bears.tapped
    assert goblin.tapped
    assert not bears.exerted
    assert not goblin.exerted

    scenario.game.untap_step()
    assert not bears.tapped
    assert not goblin.tapped


def test_frost_breath_up_to_two_may_tap_only_one():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    goblin = scenario.creature("Goblin Guide", "alice")

    sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Frost Breath", *sources, targets=[bears])

    assert bears.tapped
    assert bears.exerted
    assert not goblin.tapped


def test_chill_of_the_grave_singular_no_up_to_taps_and_exerts_then_draws():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Chill of the Grave"],
            battlefield=["Island", "Island", "Island", "Grizzly Bears"],
            library=["Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    alice = scenario.game.player("alice")
    assert len(alice.library) == 1

    sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Chill of the Grave", *sources, targets=[bears])

    assert bears.tapped
    assert bears.exerted
    # The trailing "Draw a card." clause resolved too - the "Plains" staged
    # on top of the library is now in hand.
    assert not alice.library
    assert scenario.find("Plains", Zone.HAND, "alice") is not None

    scenario.game.untap_step()
    assert bears.tapped
    assert not bears.exerted
    scenario.game.untap_step()
    assert not bears.tapped


def test_frost_breath_skips_an_illegal_target_and_still_taps_the_legal_one():
    """CR 608.2b: a target gone by resolution is simply skipped, not a
    reason for the whole spell to fizzle (Grizzly Bears is sacrificed in
    response, leaving only Goblin Guide a legal target)."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    goblin = scenario.creature("Goblin Guide", "alice")

    sources = scenario.untapped_sources("Island", "Island", "Island")
    casting = scenario.cast_onto_stack("Frost Breath", *sources, targets=[bears, goblin])
    scenario.game.sacrifice(bears)

    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert goblin.tapped
    assert goblin.exerted
    assert casting.zone is Zone.GRAVEYARD
