"""Protection from a colour *count* - "multicolored", "monocolored" (CR
702.16a: the quality "can be any characteristic value or information").

CR 105.2a: "A monocolored object is exactly one of the five colors." CR
105.2b: "A multicolored object is two or more of the five colors." Both
looked up this session with `mise run rules:find 105.2`. The quality is read
by the same `source_has_quality`/`source_has_quality_of_card` pair every
other protection quality goes through, so targeting (CR 702.16b), blocking
(CR 702.16f) and damage (CR 702.16e) all see it.

Basri's Lieutenant is the pool printing; Enemy of the Guildpact
(multicolored) and Guardian of the Guildpact (monocolored) are the off-pool
proof, the second the opposite count.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(creature: str, *spells: str) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(spells),
            battlefield=["Mountain", "Plains"],
        )
        .player("bob", battlefield=[creature])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


@pytest.mark.parametrize("creature", ["Basri's Lieutenant", "Enemy of the Guildpact"])
def test_a_multicolored_spell_cannot_target_protection_from_multicolored(creature):
    scenario = _board(creature, "Lightning Helix")
    target = scenario.creature(creature, "bob")

    casting = scenario.cast("Lightning Helix", username="alice")
    with pytest.raises(ValueError, match="protection"):
        casting.choose_targets([target])


def test_a_monocolored_spell_still_targets_protection_from_multicolored():
    scenario = _board("Enemy of the Guildpact", "Lightning Bolt")
    target = scenario.creature("Enemy of the Guildpact", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[target])

    assert target.zone is Zone.GRAVEYARD, "3 damage to a 4/2"


def test_a_monocolored_spell_cannot_target_protection_from_monocolored():
    scenario = _board("Guardian of the Guildpact", "Lightning Bolt")
    target = scenario.creature("Guardian of the Guildpact", "bob")

    casting = scenario.cast("Lightning Bolt", username="alice")
    with pytest.raises(ValueError, match="protection"):
        casting.choose_targets([target])


def test_a_multicolored_spell_still_targets_protection_from_monocolored():
    scenario = _board("Guardian of the Guildpact", "Lightning Helix")
    target = scenario.creature("Guardian of the Guildpact", "bob")
    sources = scenario.untapped_sources("Mountain", "Plains", username="alice")

    scenario.cast_and_resolve("Lightning Helix", *sources, targets=[target])

    assert target.zone is Zone.GRAVEYARD, "3 damage to a 2/3"
