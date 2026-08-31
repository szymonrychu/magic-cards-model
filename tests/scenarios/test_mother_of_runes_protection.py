"""Scenario: Mother of Runes's "{T}: Target creature you control gains
protection from the color of your choice until end of turn."

`docs/engine-coverage.md`'s own "Protection *granted* by another static
ability" row already flagged this shape as the open item: a *targeted*
"gains protection from the color of your choice" needs a colour-choice
mechanism the engine did not have. `machines/effects.py`'s
`_parse_protection_from_chosen_color_clause` is that mechanism - CR 608.2d's
choice, asked with `DecisionKind.CHOOSE_A_QUALITY`, then granted as a plain
layer-6 "Protection from `<color>`" line through the same `grant_ability`
primitive Akroma's Memorial's own *un*-chosen grant already uses
(`machines/layers._indefinite_keyword_grant_builder`), built by hand through
`ContinuousEffects.add` since the colour is not on the printed card.

Every rule cited here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 702.16a** - "Protection is a static ability, written 'Protection from
  [quality].'"
- **CR 702.16e** - "Any damage that would be dealt by sources that have the
  stated quality ... is prevented" - the half this file actually exercises;
  `docs/engine-coverage.md` already records that a *granted* colour quality
  is read on the damage side but not yet on the targeting side, a pre-
  existing, documented gap this card does not widen or narrow - Lightning
  Bolt is still allowed to *target* a protected Mother of Runes below, and
  the damage is prevented anyway once it resolves.
- **CR 611.2a** - a continuous effect from a resolving ability lasts as
  stated ("until end of turn").
- **CR 608.2d** - the colour choice itself.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone

from .harness import Scenario


def _scenario() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Mother of Runes", "Forest"])
        .player(
            "bob", hand=["Lightning Bolt", "Lightning Bolt"], battlefield=["Mountain", "Mountain"]
        )
    )


def test_protection_prevents_damage_from_a_source_of_the_chosen_color():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.find("Mother of Runes", Zone.BATTLEFIELD, "alice")

    scenario.will_choose(Color.RED.value, source="Mother of Runes")
    scenario.activate(mother, targets=[mother])
    scenario.resolve_top()

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[mother])

    assert mother.damage == 0
    assert mother.zone is Zone.BATTLEFIELD


def test_a_color_that_was_not_chosen_still_deals_damage():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.find("Mother of Runes", Zone.BATTLEFIELD, "alice")

    scenario.will_choose(Color.BLUE.value, source="Mother of Runes")
    scenario.activate(mother, targets=[mother])
    scenario.resolve_top()

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[mother])

    assert mother.zone is Zone.GRAVEYARD


def test_the_protection_ends_at_cleanup():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.find("Mother of Runes", Zone.BATTLEFIELD, "alice")

    scenario.will_choose(Color.RED.value, source="Mother of Runes")
    scenario.activate(mother, targets=[mother])
    scenario.resolve_top()

    scenario.game.continuous_effects.end_the_turn()

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[mother])

    assert mother.zone is Zone.GRAVEYARD


def test_mother_of_runes_can_protect_another_creature_you_control():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mother of Runes", "Forest", "Elder Gargaroth"])
        .player(
            "bob", hand=["Lightning Bolt", "Lightning Bolt"], battlefield=["Mountain", "Mountain"]
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.find("Mother of Runes", Zone.BATTLEFIELD, "alice")
    gargaroth = scenario.find("Elder Gargaroth", Zone.BATTLEFIELD, "alice")

    scenario.will_choose(Color.RED.value, source="Mother of Runes")
    scenario.activate(mother, targets=[gargaroth])
    scenario.resolve_top()

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[gargaroth])

    assert gargaroth.damage == 0


def test_mother_of_runes_is_a_tap_ability_and_taps_herself():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.find("Mother of Runes", Zone.BATTLEFIELD, "alice")

    scenario.will_choose(Color.RED.value, source="Mother of Runes")
    scenario.activate(mother, targets=[mother])

    assert mother.tapped
