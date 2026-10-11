"""Bushwhack: "Choose one - Search your library for a basic land card, reveal
it, put it into your hand, then shuffle. / Target creature you control fights
target creature you don't control." (R0c T4).

CR numbers looked up with `mise run rules:find` in the session that wrote this:

- **CR 700.2a / 700.2c** - modes are chosen as the spell is cast, and the
  chosen mode decides what it targets.
- **CR 701.23a / 701.23b** - a search looks through the library and need not
  find a card; **CR 701.24a** - the shuffle closes it.
- **CR 701.14a** - each fighter deals damage equal to its power to the other.
- **CR 701.14b** - if either creature is gone, or an illegal target, neither
  fights or deals damage. **CR 701.14c** - a creature fighting itself.
  **CR 701.14d** - fight damage is not combat damage.
- **CR 608.2b** - a spell with every target illegal does not resolve.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

BUSHWHACK = "Bushwhack"
SEARCH = 1
FIGHT = 2


def _versus(mine, theirs):
    scenario = (
        Scenario()
        .player("alice", hand=[BUSHWHACK], battlefield=["Forest", mine])
        .player("bob", battlefield=[theirs])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, mode, targets=None):
    casting = scenario.cast(BUSHWHACK, username="alice")
    casting.choose_modes([mode])
    if targets is not None:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest"))
    scenario.put_on_stack(casting)
    return casting


def test_the_search_mode_puts_a_basic_land_into_hand_and_does_not_fight():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[BUSHWHACK],
            library=["Lightning Bolt", "Mountain", "Island"],
            battlefield=["Forest", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Goblin Piker"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island = scenario.find("Island", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(island, username="alice")
    _cast(scenario, SEARCH)
    scenario.pass_until_resolved()

    hand = [c.name for c in scenario.player("alice").hand]
    assert hand == ["Island"]
    assert sorted(c.name for c in scenario.player("alice").library) == [
        "Lightning Bolt",
        "Mountain",
    ]
    assert scenario.creature("Grizzly Bears", "alice").damage == 0
    assert scenario.creature("Goblin Piker", "bob").damage == 0


def test_the_search_mode_only_finds_basic_lands():
    """A nonbasic land and a spell in the library are not offered."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[BUSHWHACK],
            library=["Lightning Bolt", "Spara's Headquarters", "Mountain"],
            battlefield=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(scenario.find("Mountain", Zone.LIBRARY, "alice"), username="alice")
    _cast(scenario, SEARCH)
    scenario.pass_until_resolved()
    assert [c.name for c in scenario.player("alice").hand] == ["Mountain"]
    assert sorted(c.name for c in scenario.player("alice").library) == [
        "Lightning Bolt",
        "Spara's Headquarters",
    ]


def test_the_search_mode_may_find_nothing_when_no_basic_land_is_present():
    """CR 701.23b: failing to find is legal, and the spell still resolves."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[BUSHWHACK],
            library=["Lightning Bolt", "Spara's Headquarters"],
            battlefield=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spell = scenario.find(BUSHWHACK, Zone.HAND, "alice")
    _cast(scenario, SEARCH)
    scenario.pass_until_resolved()
    assert scenario.player("alice").hand == []
    assert len(scenario.player("alice").library) == 2
    assert spell.zone is Zone.GRAVEYARD


def test_the_search_mode_needs_no_targets():
    scenario = _versus("Grizzly Bears", "Hill Giant")
    casting = scenario.cast(BUSHWHACK, username="alice")
    casting.choose_modes([SEARCH])
    casting.choose_targets([])
    assert casting.targets == []


def test_the_fight_mode_deals_damage_both_ways():
    scenario = _versus("Grizzly Bears", "Hill Giant")  # 2/2 vs 3/3
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, FIGHT, [bears, giant])
    scenario.pass_until_resolved()

    assert giant.damage == 2
    assert giant.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.GRAVEYARD, "3 damage kills the 2/2"


def test_the_fight_mode_can_kill_the_other_creature():
    scenario = _versus("Hill Giant", "Grizzly Bears")
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, FIGHT, [giant, bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert giant.damage == 2
    assert giant.zone is Zone.BATTLEFIELD


def test_fight_damage_is_not_combat_damage():
    """CR 701.14d: a fight uses no combat, so no combat-damage record is made."""
    scenario = _versus("Hill Giant", "Grizzly Bears")
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, FIGHT, [giant, bears])
    scenario.pass_until_resolved()
    assert scenario.combat_damage() == []


def test_the_fight_mode_needs_both_targets():
    scenario = _versus("Grizzly Bears", "Hill Giant")
    bears = scenario.creature("Grizzly Bears", "alice")
    casting = scenario.cast(BUSHWHACK, username="alice")
    casting.choose_modes([FIGHT])
    with pytest.raises(ValueError):
        casting.choose_targets([bears])
        payment = casting.begin_paying()
        scenario.pay_with(payment, *scenario.untapped_sources("Forest"))
        scenario.put_on_stack(casting)


def test_the_first_target_must_be_your_own_creature():
    scenario = _versus("Grizzly Bears", "Hill Giant")
    giant = scenario.creature("Hill Giant", "bob")
    casting = scenario.cast(BUSHWHACK, username="alice")
    casting.choose_modes([FIGHT])
    with pytest.raises(ValueError):
        casting.choose_targets([giant, giant])


def test_the_second_target_must_be_a_creature_you_dont_control():
    scenario = (
        Scenario()
        .player("alice", hand=[BUSHWHACK], battlefield=["Forest", "Grizzly Bears", "Hill Giant"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    casting = scenario.cast(BUSHWHACK, username="alice")
    casting.choose_modes([FIGHT])
    with pytest.raises(ValueError):
        casting.choose_targets([bears, giant])


def test_if_your_creature_leaves_before_resolution_neither_fights():
    """CR 701.14b: one of the two is gone, so the other takes no damage and
    deals none."""
    scenario = _versus("Grizzly Bears", "Hill Giant")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, FIGHT, [bears, giant])
    scenario.game.destroy(bears)
    scenario.pass_until_resolved()

    assert giant.damage == 0
    assert giant.zone is Zone.BATTLEFIELD


def test_if_their_creature_leaves_before_resolution_neither_fights():
    scenario = _versus("Grizzly Bears", "Hill Giant")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, FIGHT, [bears, giant])
    scenario.game.destroy(giant)
    scenario.pass_until_resolved()

    assert bears.damage == 0
    assert bears.zone is Zone.BATTLEFIELD


def test_the_spell_goes_to_the_graveyard_after_either_mode():
    scenario = _versus("Hill Giant", "Grizzly Bears")
    spell = scenario.find(BUSHWHACK, Zone.HAND, "alice")
    _cast(
        scenario,
        FIGHT,
        [scenario.creature("Hill Giant", "alice"), scenario.creature("Grizzly Bears", "bob")],
    )
    scenario.pass_until_resolved()
    assert spell.zone is Zone.GRAVEYARD


def test_only_one_mode_may_be_chosen():
    scenario = _versus("Grizzly Bears", "Hill Giant")
    casting = scenario.cast(BUSHWHACK, username="alice")
    with pytest.raises(ValueError):
        casting.choose_modes([SEARCH, FIGHT])


def test_a_nonbasic_land_cannot_be_chosen_by_the_search():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[BUSHWHACK],
            library=["Spara's Headquarters", "Mountain"],
            battlefield=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(
        scenario.find("Spara's Headquarters", Zone.LIBRARY, "alice"), username="alice"
    )
    _cast(scenario, SEARCH)
    with pytest.raises(ValueError):
        scenario.pass_until_resolved()
    assert [c.name for c in scenario.player("alice").hand] == []
