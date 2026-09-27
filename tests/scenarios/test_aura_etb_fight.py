"""Pitiless Fists: "When this Aura enters, enchanted creature fights up to
one target creature an opponent controls." (CR 701.14a)

`_SELF_FIGHTS_TARGET_RE` (`machines/effects.py`) already read "[it/this
creature] fights `<target>`" as CR 109.2's plain self-reference to the
ability's own source - Mind Meanderer's own printing. An Aura is never
itself a creature able to fight (CR 701.14b), so its own ETB trigger instead
names CR 303.4b's "enchanted creature" - whatever the Aura (`source.
attached_to`) is attached to. `_ENCHANTED_CREATURE_FIGHTS_TARGET_RE` is the
new, additive sibling reading that subject, over the identical `_fight`
primitive and the identical `_targets_understood`/CR 115.6 "up to one"
handling `_parse_self_fights_target_clause` already has.

**Warbriar Blessing** (proof printing, Modern-legal, not a listed card, not
in any `decks/*.txt`) proves the reader past Pitiless Fists's own wording:
"target creature you don't control" rather than "target creature an
opponent controls" - a differently-worded restriction on the second fighter,
read by `machines/targeting.py`'s own general grammar rather than anything
this reader has to know about.

CR numbers verified this session with `mise run rules:find`:

- **CR 701.14a** - "To have a permanent 'fight' another permanent means
  that the first permanent deals damage equal to its power to the second,
  and the second permanent deals damage equal to its power to the first."
- **CR 701.14b** - "Each permanent must be a creature to be able to fight
  ... an Aura, Equipment, or Fortification can't fight."
- **CR 115.6** - "up to one target ..." lets the ability's controller choose
  not to target anything, in which case the ability does as much as it can
  (nothing).
- **CR 303.4b** - "The object or player an Aura is attached to is called
  enchanted."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_pitiless_fists_fights_the_chosen_opposing_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Pitiless Fists"],
            battlefield=["Grizzly Bears", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Goblin Piker"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    piker = scenario.creature("Goblin Piker", "bob")
    scenario.choose_trigger_targets("Pitiless Fists", [piker])
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Pitiless Fists", *sources, targets=[bears])
    scenario.resolve_top()  # the Aura's own enters-the-battlefield trigger

    # Grizzly Bears is 2/2, +2/+2 from Pitiless Fists's own static = 4/4;
    # Goblin Piker is 2/1. The fight: 4 damage kills the 2/1, 2 damage marks
    # (but does not kill) the now-4-toughness bear.
    assert piker.zone is Zone.GRAVEYARD, "4 power is lethal to a 2/1"
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 2, "took the Piker's 2 power back"


def test_pitiless_fists_choosing_no_target_still_enters_and_pumps():
    """CR 115.6: "up to one" legally chooses zero - the fight simply does not
    happen, but the Aura's own static pump still applies."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Pitiless Fists"],
            battlefield=["Grizzly Bears", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Goblin Piker"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    piker = scenario.creature("Goblin Piker", "bob")
    scenario.choose_trigger_targets("Pitiless Fists", [])
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Pitiless Fists", *sources, targets=[bears])
    scenario.resolve_top()

    assert piker.zone is Zone.BATTLEFIELD, "no fight happened"
    assert piker.damage == 0
    assert bears.damage == 0
    assert scenario.game.power_of(bears) == 4, "the static pump still applies"


def test_pitiless_fists_cannot_target_a_creature_alice_controls():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Pitiless Fists"],
            battlefield=["Grizzly Bears", "Hill Giant", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "alice")

    with pytest.raises(ValueError, match="(?i)opponent|controls"):
        scenario.choose_trigger_targets("Pitiless Fists", [giant])


def test_warbriar_blessing_off_pool_proof_fights_a_creature_you_dont_control():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Warbriar Blessing"],
            battlefield=["Grizzly Bears", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Goblin Piker"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    piker = scenario.creature("Goblin Piker", "bob")
    scenario.choose_trigger_targets("Warbriar Blessing", [piker])
    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Warbriar Blessing", *sources, targets=[bears])
    scenario.resolve_top()

    assert piker.zone is Zone.GRAVEYARD, "2 power (Bears) is lethal to a 2/1"
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 2, "took the Piker's 2 power back"
