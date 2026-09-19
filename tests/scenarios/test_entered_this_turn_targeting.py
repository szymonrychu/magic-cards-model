"""Scenario: "target creature that entered this turn" (CR 603.6d's per-turn
historical fact, CR 115.1's target restriction).

Gallia, the Merrymaker's activated ability - "{1}{R}, {T}: Put a +1/+1
counter on target creature that entered this turn." - and Mabel, Valley
Hero's trigger read the identical clause, and `machines/targeting.py` had no
reader for "that entered this turn" at all: the trailing clause was left
unread, so the phrase carried no restriction and *any* creature on the
battlefield was offered, including one that had been there since a previous
turn.

Fixed by `_extract_entered_this_turn` (`_ENTERED_THIS_TURN_RE`), a new
trailing-clause reader built the same way `_extract_attacked_this_turn`
already reads "that attacked this turn", plus a new
`TargetRequirement.must_have_entered_this_turn` field and its own
`_rejects_entered_this_turn` check. Unlike `attacked_this_turn`, which needs
a dedicated per-turn set on `Game` because CR 508.1k's attacking status ends
with combat, this reads straight off `CardState.turn_entered` - the turn
history already stamped once per permanent - against `Game.turn.turn_number`,
so nothing new had to be tracked on `Game` itself.

Mabel's OTHER defect - the "<self> or another creature you control enters"
trigger condition not firing for the *other-creature* half - is batch C's,
not this file's; every scenario here drives Mabel through her own entering,
which already fires the trigger, so only the targeting restriction is on
trial.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import TargetRef

from .harness import Scenario


def test_gallia_cannot_target_a_creature_from_a_previous_turn():
    """The reported misread: "that entered this turn" carried no restriction
    at all, so a creature that had been on the battlefield since before the
    game's own first turn was offered."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gallia, the Merrymaker"],
            battlefield=["Mountain"] * 4 + ["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    cast_sources = scenario.untapped_sources("Mountain", "Mountain")
    gallia = scenario.cast_and_resolve("Gallia, the Merrymaker", *cast_sources)
    act_sources = scenario.untapped_sources("Mountain", "Mountain")

    with pytest.raises(ValueError, match="entered this turn"):
        scenario.activate(gallia, *act_sources, index=0, targets=[bears])


def test_gallia_can_target_a_creature_that_entered_this_turn():
    """Gallia herself entered this turn (she was just cast), so she is a
    legal target for her own ability."""
    scenario = (
        Scenario()
        .player("alice", hand=["Gallia, the Merrymaker"], battlefield=["Mountain"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast_sources = scenario.untapped_sources("Mountain", "Mountain")
    gallia = scenario.cast_and_resolve("Gallia, the Merrymaker", *cast_sources)
    act_sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.activate(gallia, *act_sources, index=0, targets=[gallia])
    scenario.pass_until_resolved()

    assert gallia.counters["+1/+1"] == 1


def test_mabel_offers_only_the_creature_that_entered_this_turn():
    """Mabel's own ETB does fire the "<self> ..." half of her trigger (batch
    C's defect is the *other*-creature half, not this one), so casting her
    with an older creature already on the battlefield proves the targeting
    restriction on its own: only Mabel, who just entered, is offered."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mabel, Valley Hero"],
            battlefield=["Mountain", "Plains", "Mountain", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Mountain", "Plains", "Mountain")

    mabel = scenario.cast_onto_stack("Mabel, Valley Hero", *sources)
    scenario.pass_until_resolved()

    asked = [
        decision
        for decision in scenario.game.decisions.asked
        if decision.kind is DecisionKind.CHOOSE_TARGETS and decision.source == "Mabel, Valley Hero"
    ]
    assert len(asked) == 1
    assert TargetRef.to_card(mabel) in asked[0].targets
    assert TargetRef.to_card(bears) not in asked[0].targets


# -- off-set proof: a different card, a different resolving verb count -----
# -- (two counters), a different qualifying adjective ("colorless"), and a --
# -- land's own tap ability rather than a creature's -----------------------


def test_ruins_of_oran_rief_cannot_target_a_creature_from_a_previous_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ornithopter"],
            battlefield=["Ruins of Oran-Rief", "Ornithopter", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    old_thopter = scenario.creature("Ornithopter", "alice")
    ruins = scenario.find("Ruins of Oran-Rief", Zone.BATTLEFIELD, "alice")
    ruins.tapped = False

    with pytest.raises(ValueError, match="entered this turn"):
        scenario.activate(ruins, index=1, targets=[old_thopter])


def test_ruins_of_oran_rief_targets_a_creature_that_entered_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ornithopter"],
            battlefield=["Ruins of Oran-Rief", "Ornithopter", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ruins = scenario.find("Ruins of Oran-Rief", Zone.BATTLEFIELD, "alice")
    ruins.tapped = False
    new_thopter = scenario.cast_and_resolve("Ornithopter", username="alice")

    scenario.activate(ruins, index=1, targets=[new_thopter])
    scenario.pass_until_resolved()

    assert new_thopter.counters["+1/+1"] == 1
