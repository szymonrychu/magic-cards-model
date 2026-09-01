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
  stated quality to a permanent or player with protection is prevented."
- **CR 702.16b** - "A permanent or player with protection can't be targeted by
  spells with the stated quality." Both halves of CR 702.16 are exercised
  here, and they read the quality with the same matcher, so a red spell aimed
  at a creature Mother has just protected from red is refused at announcement
  (CR 601.2c) rather than announced and then prevented.

  That is why the damage half below is shown with **Pyroclasm** rather than a
  Lightning Bolt: a targeted red spell never gets far enough for CR 702.16e to
  do anything, so only a red source that chooses no targets can demonstrate
  the prevention.
- **CR 611.2a** - a continuous effect from a resolving ability lasts as
  stated ("until end of turn").
- **CR 608.2d** - the colour choice itself.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone

from .harness import Scenario


def _scenario() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Mother of Runes", "Forest"])
        .player(
            "bob",
            hand=["Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
    )


def _sweeper_scenario(*alice_extra: str) -> Scenario:
    """Alice's own board, with the red sweeper in *her* hand.

    Pyroclasm is a sorcery, so it can only be cast by the active player in
    their own main phase with the stack empty (CR 307.1, CR 117.1a), and
    Mother's `{T}` ability needs her to have been under her controller's
    control since that player's turn began (CR 302.6). Both point the same way:
    alice is the active player and alice casts the sweeper.

    Whose spell it is does not matter to the rule being tested. CR 702.16e
    prevents damage "by sources that have the stated quality" without regard to
    who controls the source, so alice's own Pyroclasm is stopped by the
    protection from red she just handed out exactly as an opponent's would be.
    """
    return (
        Scenario()
        .player(
            "alice",
            hand=["Pyroclasm"],
            battlefield=["Mother of Runes", "Mountain", "Mountain", *alice_extra],
        )
        .player("bob", battlefield=["Forest"])
    )


def test_protection_prevents_damage_from_a_source_of_the_chosen_color():
    """CR 702.16e, off a red source that chooses no targets.

    Pyroclasm's "Pyroclasm deals 2 damage to each creature" would kill a 1/1
    Mother of Runes outright; with protection from red she takes none of it.
    A Lightning Bolt cannot show this - CR 702.16b refuses the announcement
    first, which is the next test."""
    scenario = _sweeper_scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.find("Mother of Runes", Zone.BATTLEFIELD, "alice")

    scenario.will_choose(Color.RED.value, source="Mother of Runes")
    scenario.activate(mother, username="alice", targets=[mother])
    scenario.resolve_top()

    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Pyroclasm", *sources, username="alice")

    assert mother.damage == 0
    assert mother.zone is Zone.BATTLEFIELD


def test_a_red_spell_cannot_even_be_aimed_at_the_protected_creature():
    """CR 702.16b: "A permanent or player with protection can't be targeted by
    spells with the stated quality."

    The refusal happens at announcement (CR 601.2c), so the Bolt never reaches
    the stack and bob's Mountain is never tapped for it - the colour half of a
    quality is enforced on the targeting side, not only on the damage side."""
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.find("Mother of Runes", Zone.BATTLEFIELD, "alice")

    scenario.will_choose(Color.RED.value, source="Mother of Runes")
    scenario.activate(mother, targets=[mother])
    scenario.resolve_top()

    scenario.pass_priority("alice")
    with pytest.raises(ValueError, match="protection from red"):
        scenario.cast("Lightning Bolt", username="bob", targets=[mother])

    assert scenario.find("Lightning Bolt", Zone.HAND, "bob").zone is Zone.HAND


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
    """The ability targets "creature you control", not only Mother herself.

    Pyroclasm shows both sides of the one grant at once: it hits *each*
    creature, so the Gargaroth she protected takes none of the 2 damage while
    Mother, who protected nobody this time, dies to it as a 1/1."""
    scenario = _sweeper_scenario("Elder Gargaroth").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.find("Mother of Runes", Zone.BATTLEFIELD, "alice")
    gargaroth = scenario.find("Elder Gargaroth", Zone.BATTLEFIELD, "alice")

    scenario.will_choose(Color.RED.value, source="Mother of Runes")
    scenario.activate(mother, username="alice", targets=[gargaroth])
    scenario.resolve_top()

    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Pyroclasm", *sources, username="alice")

    assert gargaroth.damage == 0, "the grant went to Gargaroth (CR 702.16e)"
    assert mother.zone is Zone.GRAVEYARD, "Mother protected Gargaroth, not herself"


def test_mother_of_runes_is_a_tap_ability_and_taps_herself():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.find("Mother of Runes", Zone.BATTLEFIELD, "alice")

    scenario.will_choose(Color.RED.value, source="Mother of Runes")
    scenario.activate(mother, targets=[mother])

    assert mother.tapped
