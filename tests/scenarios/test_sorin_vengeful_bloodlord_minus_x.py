""" "-X: Return target creature card with mana value X from your graveyard to
the battlefield. That creature is a Vampire in addition to its other types."
- Sorin, Vengeful Bloodlord's third loyalty ability (CR 107.7, CR 606.4,
CR 205.1b).

Two things past a bare reanimation:

- **CR 606.5** - X's own value is announced as the ability's cost is
  activated (CR 107.3a), and the target must have exactly that mana value:
  not "X or less" (Unearth's own shape, `_RETURN_FROM_YOUR_GRAVEYARD_TO_
  BATTLEFIELD_RE`'s existing reading), but exactly X, read off the target at
  announcement (CR 601.2c's own timing for "target" restrictions applies the
  same way to an activated ability's targets, CR 602.2b).
- **CR 205.1b** - "That creature is a Vampire in addition to its other
  types" is an anaphoric one-shot type addition to the permanent the same
  ability just put onto the battlefield, not a continuous grant on Sorin
  himself.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def test_minus_x_returns_a_creature_of_exactly_that_mana_value_as_a_vampire():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Sorin, Vengeful Bloodlord"],
            graveyard=["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sorin = scenario.creature("Sorin, Vengeful Bloodlord", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    assert sorin.loyalty == 4
    scenario.activate(sorin, index=1, x_value=2, targets=[bears])
    scenario.resolve_top()

    assert sorin.loyalty == 2, "CR 606.4: 4 printed, minus X=2"
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    chars = scenario.game.computed_board().of(bears)
    assert "Bear" in chars.subtypes, "CR 205.1b: in addition to its other types"
    assert "Vampire" in chars.subtypes


def test_minus_x_cannot_target_a_creature_card_of_a_different_mana_value():
    """Exactly X, not "X or less": Grizzly Bears (mana value 2) is not a legal
    target for X=3 (CR 601.2c's target restriction, read at announcement)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Sorin, Vengeful Bloodlord"],
            graveyard=["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sorin = scenario.creature("Sorin, Vengeful Bloodlord", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    with pytest.raises(ValueError, match="needs mana value 3"):
        scenario.activate(sorin, index=1, x_value=3, targets=[bears])
    assert bears.zone is Zone.GRAVEYARD
