"""`machines/replacement.py::_keyword_replacements` grants umbra armor's
replacement effect (CR 702.89a) off a battlefield permanent's *computed*
ability list, not its printed `Card.keywords` (CR 613.5, CR 613.1f).

`tests/scenarios/judge/test_judge_replacement_effects.py::
test_umbra_armor_eats_the_destruction_and_the_creature_survives` (DDR#403)
already covers the ordinary case with a real Hyena Umbra - printed and
computed agree there. This file is the disagreement: Hyena Umbra's own umbra
armor line stripped by a real layer-6 continuous effect (`lose_all_abilities`,
CR 613.1f - the same production `Modification` this defect class's other
"stripped ability" tests use, added through `ContinuousEffects.add`), so the
Aura's own printed keyword line is still there but the ability itself is not,
and the destruction it would have eaten goes through instead.

CR numbers already verified this session: CR 613.5, CR 613.1f. CR 702.89a and
CR 614.6's "the replaced event never happens" are quoted from `test_judge_
replacement_effects.py`, which verified them in the session that wrote that
file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import (
    ContinuousEffect,
    Layer,
    lose_all_abilities,
    only_this_incarnation,
)
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _strip_umbras_abilities(scenario, umbra) -> None:
    store = scenario.game.continuous_effects
    with scenario.game._id_allocator_scope():  # noqa: SLF001
        store.add(
            ContinuousEffect(
                description="test: Hyena Umbra loses all abilities",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                selector=only_this_incarnation(umbra, umbra.zone_change_stamp),
                modification=lose_all_abilities,
            )
        )


def test_a_stripped_umbra_armor_no_longer_replaces_the_destruction():
    """The positive case: Hyena Umbra's printed keyword line is still "Umbra
    armor" - `_keyword_replacements` must read the computed, now-empty
    ability list instead, so the destruction goes through and Grizzly Bears
    actually dies.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Hyena Umbra"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    umbra = scenario.creature("Hyena Umbra", "bob")
    umbra.attach_to(bears)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert "umbra armor" in [k.lower() for k in umbra.keywords], "still printed"
    _strip_umbras_abilities(scenario, umbra)
    assert scenario.game.characteristics_of(umbra).abilities == ()

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bears.zone is Zone.GRAVEYARD, "umbra armor no longer applies once stripped"


def test_umbra_armor_still_applies_without_the_strip():
    """The control: the same board, minus the layer-6 strip, still saves the
    creature exactly as `test_umbra_armor_eats_the_destruction_and_the_
    creature_survives` already proves - the premise this file's positive
    case needs to be a meaningful negative.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Hyena Umbra"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    umbra = scenario.creature("Hyena Umbra", "bob")
    umbra.attach_to(bears)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD
    assert umbra.zone is Zone.GRAVEYARD, "the Aura is destroyed in the creature's place"
