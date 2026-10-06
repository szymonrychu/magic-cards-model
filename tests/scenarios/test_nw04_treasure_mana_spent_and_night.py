"""Two cast-time / game-state facts read by amounts and conditions (NW-04, T3).

- "for each mana from a Treasure that was spent to cast this spell" (Spoils of
  the Hunt) and "if mana from a Treasure was spent to cast this spell" (Price
  of Loyalty): CR 601.2h's spent mana, whose source CR 106.3 keeps. Read from
  the spell's own `CastRecord` (fixed as it was cast), never from what is left
  on the board when it resolves.
- "if it's night" / "if it's day" (Wolf Strike, Olivia's Midnight Ambush,
  Moonrager's Slash): the day/night designation of CR 731.1. A game that has
  neither designation is neither day nor night.

CR numbers checked with `mise run rules:find` (rules effective 2026-09-25).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.turn import DayNight
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.token import create_predefined_tokens
from tests.scenarios.harness import Scenario


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _treasure_mana(scenario, color: Color, username: str = "alice") -> None:
    (treasure,) = create_predefined_tokens(scenario.game, "Treasure", username)
    _resolve_all(scenario)
    scenario.game.activate_ability(treasure, 0, username, color=color)


def _power(scenario, creature) -> int:
    return scenario.game.characteristics_of(creature).power


# -- Spoils of the Hunt: +1/+0 for each mana from a Treasure spent --------------


def _spoils_board(forests: int):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spoils of the Hunt"],
            battlefield=["Grizzly Bears", *["Forest"] * forests],
        )
        .player("bob", battlefield=["Elder Gargaroth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return (
        scenario,
        scenario.creature("Grizzly Bears", "alice"),
        scenario.creature("Elder Gargaroth", "bob"),
    )


def _spoils(scenario, mine, theirs, *sources):
    return scenario.cast_and_resolve("Spoils of the Hunt", *sources, targets=[mine, theirs])


def test_spoils_paid_with_lands_only_pumps_nothing_and_bites_for_base_power():
    scenario, mine, theirs = _spoils_board(3)
    _spoils(scenario, mine, theirs, *scenario.untapped_sources("Forest", "Forest", "Forest"))
    assert _power(scenario, mine) == 2
    assert theirs.damage == 2


def test_spoils_pumps_once_per_treasure_mana_and_bites_with_the_new_power():
    scenario, mine, theirs = _spoils_board(2)
    _treasure_mana(scenario, Color.GREEN)
    _spoils(scenario, mine, theirs, *scenario.untapped_sources("Forest", "Forest"))
    assert _power(scenario, mine) == 3
    assert theirs.damage == 3


def test_spoils_counts_every_treasure_mana_spent():
    scenario, mine, theirs = _spoils_board(0)
    for _ in range(3):
        _treasure_mana(scenario, Color.GREEN)
    _spoils(scenario, mine, theirs)
    assert _power(scenario, mine) == 5
    assert theirs.damage == 5


def test_spoils_pump_lasts_until_end_of_turn_only():
    scenario, mine, theirs = _spoils_board(2)
    _treasure_mana(scenario, Color.GREEN)
    _spoils(scenario, mine, theirs, *scenario.untapped_sources("Forest", "Forest"))
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.game.cleanup_step()
    assert _power(scenario, mine) == 2


def test_spoils_reads_the_cast_record_not_the_treasures_left_on_the_board():
    """The Treasure was sacrificed to make the mana, so nothing on the board
    says it paid; the count is what the spell was cast with."""
    scenario, mine, theirs = _spoils_board(2)
    _treasure_mana(scenario, Color.GREEN)
    spell = scenario.cast_onto_stack(
        "Spoils of the Hunt",
        *scenario.untapped_sources("Forest", "Forest"),
        targets=[mine, theirs],
    )
    assert scenario.game.cast_record(spell).treasure_mana_spent == 1
    scenario.resolve_top()
    assert _power(scenario, mine) == 3


def test_spoils_with_its_creature_gone_does_nothing():
    scenario, mine, theirs = _spoils_board(2)
    _treasure_mana(scenario, Color.GREEN)
    scenario.cast_onto_stack(
        "Spoils of the Hunt",
        *scenario.untapped_sources("Forest", "Forest"),
        targets=[mine, theirs],
    )
    scenario.game.destroy(mine)
    scenario.resolve_top()
    assert mine.zone is Zone.GRAVEYARD
    assert theirs.damage == 0


# -- Price of Loyalty: "if mana from a Treasure was spent to cast this spell" ---


def _price_board(mountains: int):
    scenario = (
        Scenario()
        .player("alice", hand=["Price of Loyalty"], battlefield=["Mountain"] * mountains)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature("Grizzly Bears", "bob")


def test_price_of_loyalty_without_treasure_mana_gives_no_bonus():
    scenario, bears = _price_board(3)
    scenario.cast_and_resolve(
        "Price of Loyalty",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=[bears],
    )
    assert _power(scenario, bears) == 2
    assert scenario.game.controller_of(bears).username == "alice"
    assert not scenario.game.conditional_clause_notices


def test_price_of_loyalty_with_treasure_mana_adds_two_power():
    scenario, bears = _price_board(2)
    _treasure_mana(scenario, Color.RED)
    scenario.cast_and_resolve(
        "Price of Loyalty", *scenario.untapped_sources("Mountain", "Mountain"), targets=[bears]
    )
    assert _power(scenario, bears) == 4
    assert not scenario.game.conditional_clause_notices


# -- Wolf Strike: "gets +2/+0 until end of turn if it's night" ------------------


def _wolf_board(designation: DayNight | None):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wolf Strike"],
            battlefield=["Grizzly Bears", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Elder Gargaroth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if designation is not None:
        scenario.game.set_day_night(designation)
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Elder Gargaroth", "bob")
    scenario.cast_and_resolve(
        "Wolf Strike",
        *scenario.untapped_sources("Forest", "Forest", "Forest"),
        targets=[mine, theirs],
    )
    return scenario, mine, theirs


def test_wolf_strike_at_night_pumps_two_and_bites_with_the_new_power():
    scenario, mine, theirs = _wolf_board(DayNight.NIGHT)
    assert _power(scenario, mine) == 4
    assert theirs.damage == 4


def test_wolf_strike_by_day_only_bites_for_base_power():
    scenario, mine, theirs = _wolf_board(DayNight.DAY)
    assert _power(scenario, mine) == 2
    assert theirs.damage == 2
    assert not scenario.game.conditional_clause_notices


def test_wolf_strike_with_neither_designation_is_not_night():
    """CR 731.1: the game starts with neither designation, so it is not night."""
    scenario, mine, theirs = _wolf_board(None)
    assert _power(scenario, mine) == 2
    assert theirs.damage == 2
    assert not scenario.game.conditional_clause_notices


# -- "it's night" / "it's day" as a condition: the mechanic, on other printings -


def test_olivia_midnight_ambush_swaps_to_the_larger_shrink_at_night():
    scenario = (
        Scenario()
        .player("alice", hand=["Olivia's Midnight Ambush"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Elder Gargaroth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.set_day_night(DayNight.NIGHT)
    target = scenario.creature("Elder Gargaroth", "bob")
    scenario.cast_and_resolve(
        "Olivia's Midnight Ambush", *scenario.untapped_sources("Swamp", "Swamp"), targets=[target]
    )
    assert target.zone is Zone.GRAVEYARD, "-13/-13 instead of -2/-2"


def test_olivia_midnight_ambush_only_shrinks_two_by_day():
    scenario = (
        Scenario()
        .player("alice", hand=["Olivia's Midnight Ambush"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Elder Gargaroth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.set_day_night(DayNight.DAY)
    target = scenario.creature("Elder Gargaroth", "bob")
    scenario.cast_and_resolve(
        "Olivia's Midnight Ambush", *scenario.untapped_sources("Swamp", "Swamp"), targets=[target]
    )
    assert target.zone is Zone.BATTLEFIELD
    assert _power(scenario, target) == 4


def test_moonragers_slash_costs_two_less_at_night_and_full_price_by_day():
    night = (
        Scenario()
        .player("alice", hand=["Moonrager's Slash"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    night.start_at(Step.PRECOMBAT_MAIN)
    night.game.set_day_night(DayNight.NIGHT)
    night.cast_and_resolve(
        "Moonrager's Slash", *night.untapped_sources("Mountain"), targets=["bob"]
    )
    assert night.player("bob").life == 17

    day = (
        Scenario()
        .player("alice", hand=["Moonrager's Slash"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    day.start_at(Step.PRECOMBAT_MAIN)
    day.game.set_day_night(DayNight.DAY)
    with pytest.raises(ValueError):
        day.cast_onto_stack("Moonrager's Slash", *day.untapped_sources("Mountain"), targets=["bob"])
    assert day.player("bob").life == 20


def test_the_designation_can_flip_between_two_casts():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wolf Strike", "Wolf Strike"],
            battlefield=["Grizzly Bears", *["Forest"] * 6],
        )
        .player("bob", battlefield=["Elder Gargaroth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Elder Gargaroth", "bob")
    scenario.game.set_day_night(DayNight.DAY)
    scenario.cast_and_resolve(
        "Wolf Strike",
        *scenario.untapped_sources("Forest", "Forest", "Forest"),
        targets=[mine, theirs],
    )
    assert theirs.damage == 2
    scenario.game.set_day_night(DayNight.NIGHT)
    scenario.cast_and_resolve(
        "Wolf Strike",
        *scenario.untapped_sources("Forest", "Forest", "Forest"),
        targets=[mine, theirs],
    )
    assert theirs.zone is Zone.GRAVEYARD, "2 by day, then 4 more at night kills the 6/6"


# -- Devour Intellect: "If mana from a Treasure was spent to cast this spell, instead" --


def _devour_board():
    scenario = (
        Scenario()
        .player("alice", hand=["Devour Intellect"], battlefield=["Swamp"])
        .player("bob", hand=["Forest", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_devour_intellect_with_treasure_mana_lets_the_caster_pick_the_nonland():
    scenario = _devour_board()
    _treasure_mana(scenario, Color.BLACK)
    scenario.cast_and_resolve("Devour Intellect", targets=["bob"])
    discarded = [card.name for card in scenario.player("bob").graveyard]
    assert discarded == ["Grizzly Bears"]
    assert [card.name for card in scenario.player("bob").hand] == ["Forest"]
    assert not scenario.game.conditional_clause_notices


def test_devour_intellect_without_treasure_mana_is_a_plain_discard():
    scenario = _devour_board()
    scenario.cast_and_resolve(
        "Devour Intellect", *scenario.untapped_sources("Swamp"), targets=["bob"]
    )
    assert len(scenario.player("bob").graveyard) == 1
    assert len(scenario.player("bob").hand) == 1
    assert not scenario.game.conditional_clause_notices
