"""Dissection Practice and Hostile Takeover: several "up to one (other) target
creature" sentences, each with its own pump or base power and toughness
(CR 601.2c announces every target at once; CR 115.6 lets each "up to one"
choose zero).

- **CR 601.2c** - the targets of every sentence are chosen on announcement.
- **CR 115.6** - "up to one target" may legally choose no target.
- **CR 608.2b** - a sentence whose target is gone does nothing; the others run.
- **CR 613.4b** - a base power and toughness setting is layer 7b.
- **CR 120.3** - "deals 3 damage to each creature" (Hostile Takeover's tail).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

DISSECTION = "Dissection Practice"
TAKEOVER = "Hostile Takeover"


def _practice():
    scenario = (
        Scenario()
        .player("alice", hand=[DISSECTION], battlefield=["Swamp", "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_dissection_practice_applies_both_pumps_and_the_life_swing():
    scenario = _practice()
    ours = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Hill Giant", "bob")
    swamp = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve(DISSECTION, *swamp, targets=["bob", ours, theirs])
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21
    chars = scenario.game.characteristics_of(ours)
    assert (chars.power, chars.toughness) == (3, 3)
    chars = scenario.game.characteristics_of(theirs)
    assert (chars.power, chars.toughness) == (2, 2)


def test_dissection_practice_may_decline_the_creature_targets():
    scenario = _practice()
    ours = scenario.creature("Grizzly Bears", "alice")
    swamp = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve(DISSECTION, *swamp, targets=["bob"])
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21
    chars = scenario.game.characteristics_of(ours)
    assert (chars.power, chars.toughness) == (2, 2)


def test_dissection_practice_with_only_the_minus_target_chosen():
    scenario = _practice()
    theirs = scenario.creature("Hill Giant", "bob")
    swamp = scenario.untapped_sources("Swamp")
    scenario.cast_and_resolve(DISSECTION, *swamp, targets=["bob", theirs])
    # One creature target given: it fills the first "up to one" slot (+1/+1).
    chars = scenario.game.characteristics_of(theirs)
    assert (chars.power, chars.toughness) == (4, 4)


def _takeover():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[TAKEOVER],
            battlefield=["Island", "Swamp", "Mountain", "Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_hostile_takeover_shrinks_one_grows_another_then_damages_all():
    scenario = _takeover()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.cast_and_resolve(TAKEOVER, auto=True, targets=[giant, bears])
    # Hill Giant is 1/1 (dies to 3 damage); Grizzly Bears is 4/4 and survives
    # with 3 damage; Serra Angel (4/4) was not targeted and survives too.
    assert giant.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert angel.zone is Zone.BATTLEFIELD
    chars = scenario.game.characteristics_of(bears)
    assert (chars.power, chars.toughness) == (4, 4)


def test_hostile_takeover_with_no_targets_still_deals_the_damage():
    scenario = _takeover()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve(TAKEOVER, auto=True, targets=[])
    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD


def test_hostile_takeover_second_target_must_be_a_different_creature():
    scenario = _takeover()
    bears = scenario.creature("Grizzly Bears", "alice")
    import pytest

    with pytest.raises(ValueError):
        scenario.cast(TAKEOVER, targets=[bears, bears])
