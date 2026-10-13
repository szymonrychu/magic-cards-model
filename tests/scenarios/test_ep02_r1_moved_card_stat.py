"""EP-02-R1 T7: the power, toughness, mana value or counters of a card or spell
that was moved by the same spell or ability, used as an amount.

"X is the sacrificed creature's toughness", "damage equal to that card's
power" (a card just returned from a graveyard), "where X is the exiled
card's toughness", "that spell's mana value" (the spell just countered),
"you gain life equal to the number of counters on it" (the permanent just
exiled).

Rules, each looked up with `mise run rules:find` in the session that wrote
this file:

- **CR 608.2c** - a spell or ability does what its text says in order, and
  later text may refer back to what earlier text named ("that card", "that
  spell").
- **CR 608.2h** - information from an object that left the zone it was
  expected in is its last known information: the toughness a sacrificed
  creature had on the battlefield, counters and effects included.
- **CR 602.2b** - a sacrifice or exile paid as an activation cost happens
  before the ability is on the stack; "the sacrificed creature" and "the
  exiled card" are read from what the cost paid.
- **CR 202.3** - a spell's or card's mana value comes from its mana cost.
- **CR 701.6a** - to counter a spell is to cancel it, removing it from the
  stack; it is put into its owner's graveyard.
- **CR 202.3e** - an {X} in a spell's mana cost is the number chosen for it
  while the spell is on the stack.
- **CR 400.7** - a card that changed zones is a new object: a creature card
  in a graveyard has its printed power and toughness, not the counters it died
  with.
- **CR 701.21a** - to sacrifice a permanent, its controller moves it to the
  graveyard; the controller picks it.
- **CR 107.1b** - a calculation that would be negative uses zero instead.
- **CR 111.2** - the player who creates a token is its owner, and it enters
  under that player's control.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

LISTED = [
    "Blood-Chin Fanatic",
    "Dina, Soul Steeper",
    "Disciple of Bolas",
    "Feed the Pack",
    "Fruit of the First Tree",
    "Geralf, Visionary Stitcher",
    "Korozda Guildmage",
    "Mercy Killing",
    "Onward // Victory",
    "Rush of Blood",
    "Surtland Flinger",
    "Railway Brawler",
    "Soul's Might",
    "Bioplasm",
    "Dead Reckoning",
    "Dread Defiler",
    "Flesh // Blood",
    "Lie in Wait",
    "Pyretic Rebirth",
    "Ritual of the Returned",
    "Rotfeaster Maggot",
    "Vengeful Rebirth",
    "Volcanic Vision",
    "Morbid Bloom",
    "Scour the Desert",
    "Essence Backlash",
    "Overwhelming Intellect",
    "Mystic Genesis",
    "Spell Swindle",
    "Flay Essence",
]

MANA = ["Plains"] * 3 + ["Swamp"] * 4 + ["Island"] * 4 + ["Forest"] * 3 + ["Mountain"] * 3


@pytest.mark.parametrize("name", LISTED)
def test_every_clause_of_a_listed_card_is_handled(name: str) -> None:
    clauses = classify_clauses(card(name))
    assert clauses
    assert all(clause.category == HANDLED for clause in clauses), [
        (clause.text, clause.category) for clause in clauses if clause.category != HANDLED
    ]


def _scenario(
    alice: list[str],
    bob: list[str] | None = None,
    *,
    hand: list[str] | None = None,
    graveyard: list[str] | None = None,
    bob_hand: list[str] | None = None,
    bob_graveyard: list[str] | None = None,
    library: list[str] | None = None,
):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=alice,
            hand=hand,
            graveyard=graveyard,
            library=library or ["Island"] * 12,
        )
        .player(
            "bob",
            battlefield=bob or [],
            hand=bob_hand,
            graveyard=bob_graveyard,
            library=["Island"] * 12,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _ready(creature):
    creature.summoning_sick = False
    return creature


def _life(scenario, who: str) -> int:
    return scenario.player(who).life


# ---------------------------------------------------------------------------
# Activated abilities whose cost sacrifices a creature
# ---------------------------------------------------------------------------


def test_blood_chin_fanatic_drains_the_sacrificed_warriors_power() -> None:
    scenario = _scenario(["Blood-Chin Fanatic", "Ash Zealot", *MANA])
    fanatic = scenario.creature("Blood-Chin Fanatic", "alice")
    zealot = scenario.creature("Ash Zealot", "alice")
    power = zealot.power
    scenario.activate(fanatic, sacrificing=[zealot], targets=["bob"], auto=True)
    scenario.pass_until_resolved()
    assert zealot.zone is Zone.GRAVEYARD
    assert _life(scenario, "bob") == 20 - power
    assert _life(scenario, "alice") == 20 + power


def test_blood_chin_fanatic_reads_a_pumped_warriors_last_known_power() -> None:
    scenario = _scenario(["Blood-Chin Fanatic", "Ash Zealot", "Glorious Anthem", *MANA])
    fanatic = scenario.creature("Blood-Chin Fanatic", "alice")
    zealot = scenario.creature("Ash Zealot", "alice")
    scenario.game.add_counters(zealot, Counter.PLUS_ONE, 2)
    power = scenario.game.power_of(zealot)
    assert power == 5, "two printed, two counters, one anthem"
    scenario.activate(fanatic, sacrificing=[zealot], targets=["bob"], auto=True)
    scenario.pass_until_resolved()
    assert _life(scenario, "bob") == 20 - power
    assert _life(scenario, "alice") == 20 + power


def test_blood_chin_fanatic_cannot_sacrifice_a_non_warrior() -> None:
    scenario = _scenario(["Blood-Chin Fanatic", "Grizzly Bears", *MANA])
    fanatic = scenario.creature("Blood-Chin Fanatic", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError):
        scenario.activate(fanatic, sacrificing=[bears], targets=["bob"], auto=True)
    assert bears.zone is Zone.BATTLEFIELD


def test_blood_chin_fanatic_a_warrior_with_no_power_drains_nothing() -> None:
    scenario = _scenario(["Blood-Chin Fanatic", "Ash Zealot", *MANA])
    fanatic = scenario.creature("Blood-Chin Fanatic", "alice")
    zealot = scenario.creature("Ash Zealot", "alice")
    scenario.game.add_counters(zealot, Counter.MINUS_ONE, 5)
    scenario.activate(fanatic, sacrificing=[zealot], targets=["bob"], auto=True)
    scenario.pass_until_resolved()
    assert _life(scenario, "bob") == 20
    assert _life(scenario, "alice") == 20


def test_dina_gets_the_sacrificed_creatures_power_until_end_of_turn() -> None:
    scenario = _scenario(["Dina, Soul Steeper", "Serra Angel", *MANA])
    dina = scenario.creature("Dina, Soul Steeper", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    before = scenario.game.power_of(dina)
    scenario.activate(dina, sacrificing=[angel], auto=True)
    scenario.pass_until_resolved()
    assert angel.zone is Zone.GRAVEYARD
    assert scenario.game.power_of(dina) == before + 4
    assert scenario.game.toughness_of(dina) == dina.toughness


def test_dina_cannot_sacrifice_herself_for_her_own_cost() -> None:
    scenario = _scenario(["Dina, Soul Steeper", *MANA])
    dina = scenario.creature("Dina, Soul Steeper", "alice")
    with pytest.raises(ValueError):
        scenario.activate(dina, sacrificing=[dina], auto=True)


def test_dina_pump_ends_at_end_of_turn() -> None:
    scenario = _scenario(["Dina, Soul Steeper", "Serra Angel", *MANA])
    dina = scenario.creature("Dina, Soul Steeper", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    before = scenario.game.power_of(dina)
    scenario.activate(dina, sacrificing=[angel], auto=True)
    scenario.pass_until_resolved()
    assert scenario.game.power_of(dina) == before + 4
    scenario.game.cleanup_step()
    assert scenario.game.power_of(dina) == before


def test_geralf_makes_a_zombie_as_big_as_the_sacrificed_toughness() -> None:
    scenario = _scenario(["Geralf, Visionary Stitcher", "Wall of Omens", "Island"])
    geralf = _ready(scenario.creature("Geralf, Visionary Stitcher", "alice"))
    wall = scenario.creature("Wall of Omens", "alice")
    scenario.activate(geralf, sacrificing=[wall], auto=True)
    scenario.pass_until_resolved()
    zombies = [p for p in scenario.game.battlefield if "Zombie" in p.name]
    assert len(zombies) == 1
    assert (zombies[0].power, zombies[0].toughness) == (4, 4)


def test_geralf_cannot_sacrifice_a_token() -> None:
    scenario = _scenario(["Geralf, Visionary Stitcher", "Island"])
    geralf = _ready(scenario.creature("Geralf, Visionary Stitcher", "alice"))
    from magic_cards_model.models.token import TokenDefinition, create_tokens

    (token,) = create_tokens(
        scenario.game, TokenDefinition(subtypes=("Bear",), power=2, toughness=2), "alice", 1
    )
    with pytest.raises(ValueError):
        scenario.activate(geralf, sacrificing=[token], auto=True)


def test_korozda_guildmage_makes_saprolings_equal_to_the_sacrificed_toughness() -> None:
    scenario = _scenario(["Korozda Guildmage", "Wall of Omens", *MANA])
    guildmage = scenario.creature("Korozda Guildmage", "alice")
    wall = scenario.creature("Wall of Omens", "alice")
    scenario.activate(guildmage, index=1, sacrificing=[wall], auto=True)
    scenario.pass_until_resolved()
    saprolings = [p for p in scenario.game.battlefield if "Saproling" in p.name]
    assert len(saprolings) == 4
    assert all((s.power, s.toughness) == (1, 1) for s in saprolings)


def test_korozda_guildmage_counts_a_toughness_raised_by_counters() -> None:
    scenario = _scenario(["Korozda Guildmage", "Grizzly Bears", *MANA])
    guildmage = scenario.creature("Korozda Guildmage", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 3)
    scenario.activate(guildmage, index=1, sacrificing=[bears], auto=True)
    scenario.pass_until_resolved()
    assert len([p for p in scenario.game.battlefield if "Saproling" in p.name]) == 5


def test_dread_defiler_drains_the_exiled_cards_power() -> None:
    scenario = _scenario(["Dread Defiler", "Wastes", *MANA], graveyard=["Serra Angel"])
    defiler = scenario.creature("Dread Defiler", "alice")
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    scenario.activate(defiler, exiling=[angel], targets=["bob"], auto=True)
    scenario.pass_until_resolved()
    assert angel.zone is Zone.EXILE
    assert _life(scenario, "bob") == 16
    assert _life(scenario, "alice") == 20


# ---------------------------------------------------------------------------
# Spells and abilities that sacrifice something as they resolve
# ---------------------------------------------------------------------------


def test_mercy_killing_the_victims_controller_gets_elf_warriors_equal_to_its_power() -> None:
    scenario = _scenario([*MANA], ["Serra Angel"], hand=["Mercy Killing"])
    angel = scenario.creature("Serra Angel", "bob")
    scenario.cast_and_resolve("Mercy Killing", username="alice", targets=[angel], auto=True)
    assert angel.zone is Zone.GRAVEYARD
    elves = [p for p in scenario.game.battlefield if "Elf" in p.name]
    assert len(elves) == 4
    assert all(scenario.game.controller_of(e).username == "bob" for e in elves)
    assert all((e.power, e.toughness) == (1, 1) for e in elves)


def test_mercy_killing_sacrifices_through_indestructible() -> None:
    scenario = _scenario([*MANA], ["Wurmcoil Engine"], hand=["Mercy Killing"])
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.cast_and_resolve("Mercy Killing", username="alice", targets=[wurm], auto=True)
    assert wurm.zone is Zone.GRAVEYARD
    assert len([p for p in scenario.game.battlefield if "Elf" in p.name]) == 6


def test_mercy_killing_your_own_creature_gives_you_the_elves() -> None:
    scenario = _scenario([*MANA, "Grizzly Bears"], hand=["Mercy Killing"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Mercy Killing", username="alice", targets=[bears], auto=True)
    elves = [p for p in scenario.game.battlefield if "Elf" in p.name]
    assert len(elves) == 2
    assert all(scenario.game.controller_of(e).username == "alice" for e in elves)


def test_mercy_killing_reads_the_last_known_power_with_counters() -> None:
    scenario = _scenario([*MANA], ["Grizzly Bears"], hand=["Mercy Killing"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    scenario.cast_and_resolve("Mercy Killing", username="alice", targets=[bears], auto=True)
    assert len([p for p in scenario.game.battlefield if "Elf" in p.name]) == 4


def test_disciple_of_bolas_sacrifices_another_creature_and_gains_and_draws_its_power() -> None:
    scenario = _scenario(["Serra Angel"], hand=["Disciple of Bolas"])
    scenario.put_onto_battlefield("Disciple of Bolas", "alice")
    scenario.game.put_triggers_on_stack()
    hand_before = len(scenario.player("alice").hand)
    scenario.pass_until_resolved()
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    assert angel.zone is Zone.GRAVEYARD
    assert _life(scenario, "alice") == 24
    assert len(scenario.player("alice").hand) == hand_before + 4


def test_disciple_of_bolas_the_controller_picks_which_creature() -> None:
    scenario = _scenario(["Serra Angel", "Grizzly Bears"], hand=["Disciple of Bolas"])
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.put_onto_battlefield("Disciple of Bolas", "alice")
    scenario.will_choose_cards(bears)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert bears.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.BATTLEFIELD
    assert _life(scenario, "alice") == 22


def test_disciple_of_bolas_with_nothing_else_to_sacrifice_does_nothing() -> None:
    scenario = _scenario([], hand=["Disciple of Bolas"])
    disciple = scenario.put_onto_battlefield("Disciple of Bolas", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert disciple.zone is Zone.BATTLEFIELD
    assert _life(scenario, "alice") == 20


def _end_step(scenario) -> None:
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()


def test_feed_the_pack_makes_wolves_equal_to_the_sacrificed_toughness() -> None:
    scenario = _scenario(["Feed the Pack", "Wall of Omens"])
    wall = scenario.creature("Wall of Omens", "alice")
    scenario.will_take_the_may(True)
    _end_step(scenario)
    scenario.pass_until_resolved()
    assert wall.zone is Zone.GRAVEYARD
    wolves = [p for p in scenario.game.battlefield if "Wolf" in p.name]
    assert len(wolves) == 4
    assert all((w.power, w.toughness) == (2, 2) for w in wolves)


def test_feed_the_pack_declining_sacrifices_nothing_and_makes_nothing() -> None:
    scenario = _scenario(["Feed the Pack", "Wall of Omens"])
    wall = scenario.creature("Wall of Omens", "alice")
    scenario.will_take_the_may(False)
    _end_step(scenario)
    scenario.pass_until_resolved()
    assert wall.zone is Zone.BATTLEFIELD
    assert [p for p in scenario.game.battlefield if "Wolf" in p.name] == []


def test_feed_the_pack_needs_a_nontoken_creature() -> None:
    scenario = _scenario(["Feed the Pack"])
    from magic_cards_model.models.token import TokenDefinition, create_tokens

    (token,) = create_tokens(
        scenario.game, TokenDefinition(subtypes=("Bear",), power=2, toughness=5), "alice", 1
    )
    _end_step(scenario)
    if scenario.stack_names():
        scenario.pass_until_resolved()
    assert token.zone is Zone.BATTLEFIELD
    assert [p for p in scenario.game.battlefield if "Wolf" in p.name] == []


def test_surtland_flinger_hits_any_target_for_the_sacrificed_power() -> None:
    scenario = _scenario(["Surtland Flinger", "Serra Angel"])
    flinger = scenario.creature("Surtland Flinger", "alice")
    flinger.summoning_sick = False
    angel = scenario.creature("Serra Angel", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(True)
    scenario.choose_trigger_targets("Surtland Flinger", ["bob"])
    scenario.attack_with(flinger)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert angel.zone is Zone.GRAVEYARD
    assert _life(scenario, "bob") == 16


def test_surtland_flinger_deals_twice_that_much_for_a_sacrificed_giant() -> None:
    scenario = _scenario(["Surtland Flinger", "Hill Giant"])
    flinger = scenario.creature("Surtland Flinger", "alice")
    flinger.summoning_sick = False
    giant = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(True)
    scenario.choose_trigger_targets("Surtland Flinger", ["bob"])
    scenario.attack_with(flinger)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert giant.zone is Zone.GRAVEYARD
    assert _life(scenario, "bob") == 20 - 6


def test_surtland_flinger_declining_deals_no_damage() -> None:
    scenario = _scenario(["Surtland Flinger", "Serra Angel"])
    flinger = scenario.creature("Surtland Flinger", "alice")
    flinger.summoning_sick = False
    angel = scenario.creature("Serra Angel", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(False)
    scenario.choose_trigger_targets("Surtland Flinger", ["bob"])
    scenario.attack_with(flinger)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert angel.zone is Zone.BATTLEFIELD
    assert _life(scenario, "bob") == 20


def test_surtland_flinger_can_hit_a_creature() -> None:
    scenario = _scenario(["Surtland Flinger", "Serra Angel"], ["Craw Wurm"])
    flinger = scenario.creature("Surtland Flinger", "alice")
    flinger.summoning_sick = False
    scenario.creature("Serra Angel", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_take_the_may(True)
    scenario.choose_trigger_targets("Surtland Flinger", [wurm])
    scenario.attack_with(flinger)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert wurm.zone is Zone.GRAVEYARD


# ---------------------------------------------------------------------------
# "Its power" / "that creature's power" as an amount
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "cost_lands"), [("Rush of Blood", 2), ("Onward // Victory", 3)])
def test_the_target_gets_plus_its_own_power(name: str, cost_lands: int) -> None:
    scenario = _scenario([*MANA, "Serra Angel"], hand=[name])
    angel = scenario.creature("Serra Angel", "alice")
    scenario.cast_and_resolve(name, username="alice", targets=[angel], auto=True)
    assert scenario.game.power_of(angel) == 8
    assert scenario.game.toughness_of(angel) == 4


def test_rush_of_blood_reads_the_power_it_has_with_counters_and_effects() -> None:
    scenario = _scenario([*MANA, "Grizzly Bears", "Glorious Anthem"], hand=["Rush of Blood"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    assert scenario.game.power_of(bears) == 4
    scenario.cast_and_resolve("Rush of Blood", username="alice", targets=[bears], auto=True)
    assert scenario.game.power_of(bears) == 8


def test_rush_of_blood_on_an_opponents_creature() -> None:
    scenario = _scenario([*MANA], ["Craw Wurm"], hand=["Rush of Blood"])
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_and_resolve("Rush of Blood", username="alice", targets=[wurm], auto=True)
    assert scenario.game.power_of(wurm) == 12


def test_rush_of_blood_on_a_zero_power_creature_adds_nothing() -> None:
    scenario = _scenario([*MANA, "Wall of Omens"], hand=["Rush of Blood"])
    wall = scenario.creature("Wall of Omens", "alice")
    scenario.cast_and_resolve("Rush of Blood", username="alice", targets=[wall], auto=True)
    assert scenario.game.power_of(wall) == 0


def test_the_power_pump_ends_at_end_of_turn() -> None:
    scenario = _scenario([*MANA, "Serra Angel"], hand=["Rush of Blood"])
    angel = scenario.creature("Serra Angel", "alice")
    scenario.cast_and_resolve("Rush of Blood", username="alice", targets=[angel], auto=True)
    assert scenario.game.power_of(angel) == 8
    scenario.game.cleanup_step()
    assert scenario.game.power_of(angel) == 4


def test_souls_might_puts_counters_equal_to_the_targets_power() -> None:
    scenario = _scenario([*MANA, "Serra Angel"], hand=["Soul's Might"])
    angel = scenario.creature("Serra Angel", "alice")
    scenario.cast_and_resolve("Soul's Might", username="alice", targets=[angel], auto=True)
    assert angel.counters[Counter.PLUS_ONE] == 4
    assert scenario.game.power_of(angel) == 8


def test_souls_might_counts_the_power_before_the_counters_land() -> None:
    scenario = _scenario([*MANA, "Grizzly Bears"], hand=["Soul's Might"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Soul's Might", username="alice", targets=[bears], auto=True)
    assert bears.counters[Counter.PLUS_ONE] == 2


def test_souls_might_on_a_creature_with_no_power_puts_none() -> None:
    scenario = _scenario([*MANA, "Wall of Omens"], hand=["Soul's Might"])
    wall = scenario.creature("Wall of Omens", "alice")
    scenario.cast_and_resolve("Soul's Might", username="alice", targets=[wall], auto=True)
    assert wall.counters[Counter.PLUS_ONE] == 0


def test_railway_brawler_puts_counters_equal_to_the_entering_creatures_power() -> None:
    scenario = _scenario(["Railway Brawler"], hand=["Serra Angel"])
    angel = scenario.put_onto_battlefield("Serra Angel", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert angel.counters[Counter.PLUS_ONE] == 4


def test_railway_brawler_ignores_an_opponents_creature() -> None:
    scenario = _scenario(["Railway Brawler"], bob_hand=["Serra Angel"])
    angel = scenario.put_onto_battlefield("Serra Angel", "bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert angel.counters[Counter.PLUS_ONE] == 0


def test_railway_brawler_does_not_trigger_on_itself() -> None:
    scenario = _scenario([], hand=["Railway Brawler"])
    brawler = scenario.put_onto_battlefield("Railway Brawler", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert brawler.counters[Counter.PLUS_ONE] == 0


# ---------------------------------------------------------------------------
# An enchanted creature that dies
# ---------------------------------------------------------------------------


def test_fruit_of_the_first_tree_gains_and_draws_the_dead_creatures_toughness() -> None:
    scenario = _scenario([*MANA, "Wall of Omens"], hand=["Fruit of the First Tree"])
    wall = scenario.creature("Wall of Omens", "alice")
    scenario.cast_and_resolve(
        "Fruit of the First Tree", username="alice", targets=[wall], auto=True
    )
    hand_before = len(scenario.player("alice").hand)
    scenario.game.destroy(wall)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert _life(scenario, "alice") == 24
    assert len(scenario.player("alice").hand) == hand_before + 4


def test_fruit_of_the_first_tree_reads_toughness_with_counters_it_died_with() -> None:
    scenario = _scenario([*MANA, "Grizzly Bears"], hand=["Fruit of the First Tree"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Fruit of the First Tree", username="alice", targets=[bears], auto=True
    )
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    scenario.game.destroy(bears)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert _life(scenario, "alice") == 24


# ---------------------------------------------------------------------------
# Bioplasm: the exiled top card
# ---------------------------------------------------------------------------


def _attack_with_bioplasm(library: list[str]):
    scenario = _scenario(["Bioplasm"], library=library)
    bioplasm = _ready(scenario.creature("Bioplasm", "alice"))
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bioplasm)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    return scenario, bioplasm


def test_bioplasm_gets_the_exiled_creature_cards_power_and_toughness() -> None:
    scenario, bioplasm = _attack_with_bioplasm(["Serra Angel", "Island", "Island"])
    assert scenario.game.power_of(bioplasm) == 4 + 4
    assert scenario.game.toughness_of(bioplasm) == 4 + 4


def test_bioplasm_exiles_the_top_card_whether_or_not_it_is_a_creature() -> None:
    scenario, bioplasm = _attack_with_bioplasm(["Island", "Serra Angel", "Island"])
    assert scenario.game.power_of(bioplasm) == 4
    assert [c.name for c in scenario.game.exile] == ["Island"]


def test_bioplasm_with_an_empty_library_gets_nothing() -> None:
    scenario, bioplasm = _attack_with_bioplasm([])
    assert scenario.game.power_of(bioplasm) == 4


# ---------------------------------------------------------------------------
# Returning a card from a graveyard, then damage equal to it
# ---------------------------------------------------------------------------


def test_lie_in_wait_returns_the_card_and_deals_damage_equal_to_its_power() -> None:
    scenario = _scenario([*MANA], ["Craw Wurm"], hand=["Lie in Wait"], graveyard=["Serra Angel"])
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_and_resolve("Lie in Wait", username="alice", targets=[angel, wurm], auto=True)
    assert angel.zone is Zone.HAND
    assert wurm.zone is Zone.GRAVEYARD


def test_lie_in_wait_damage_is_the_cards_printed_power_not_a_creature_it_was() -> None:
    scenario = _scenario([*MANA], ["Craw Wurm"], hand=["Lie in Wait"], graveyard=["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_and_resolve("Lie in Wait", username="alice", targets=[bears, wurm], auto=True)
    assert bears.zone is Zone.HAND
    assert wurm.zone is Zone.BATTLEFIELD
    assert wurm.damage == 2


def test_lie_in_wait_the_card_gone_before_resolution_deals_no_damage() -> None:
    scenario = _scenario(
        [*MANA], ["Wurmcoil Engine"], hand=["Lie in Wait"], graveyard=["Serra Angel"]
    )
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.cast_onto_stack("Lie in Wait", username="alice", targets=[angel, wurm], auto=True)
    scenario.game.exile_permanent(angel)
    scenario.resolve_top()
    assert angel.zone is Zone.EXILE
    assert wurm.damage == 0


def test_pyretic_rebirth_damage_is_the_returned_cards_mana_value() -> None:
    scenario = _scenario(
        [*MANA], ["Wurmcoil Engine"], hand=["Pyretic Rebirth"], graveyard=["Serra Angel"]
    )
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.cast_and_resolve("Pyretic Rebirth", username="alice", targets=[angel, wurm], auto=True)
    assert angel.zone is Zone.HAND
    assert wurm.damage == 5


def test_pyretic_rebirth_returns_an_artifact_and_damages_with_its_mana_value() -> None:
    scenario = _scenario(
        [*MANA], ["Craw Wurm"], hand=["Pyretic Rebirth"], graveyard=["Wurmcoil Engine"]
    )
    engine = scenario.find("Wurmcoil Engine", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_and_resolve(
        "Pyretic Rebirth", username="alice", targets=[engine, wurm], auto=True
    )
    assert engine.zone is Zone.HAND
    assert wurm.zone is Zone.GRAVEYARD


def test_pyretic_rebirth_the_damage_target_is_optional() -> None:
    scenario = _scenario([*MANA], hand=["Pyretic Rebirth"], graveyard=["Serra Angel"])
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Pyretic Rebirth", username="alice", targets=[angel], auto=True)
    assert angel.zone is Zone.HAND


def test_volcanic_vision_hits_each_opposing_creature_and_exiles_itself() -> None:
    scenario = _scenario(
        [*MANA, "Grizzly Bears"],
        ["Craw Wurm", "Wall of Omens"],
        hand=["Volcanic Vision"],
        graveyard=["Fireball"],
    )
    fireball = scenario.find("Fireball", Zone.GRAVEYARD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    wall = scenario.creature("Wall of Omens", "bob")
    spell = scenario.cast_and_resolve(
        "Volcanic Vision", username="alice", targets=[fireball], auto=True
    )
    assert fireball.zone is Zone.HAND
    assert wurm.damage == 1
    assert wall.damage == 1
    assert bears.damage == 0
    assert spell.zone is Zone.EXILE


def test_volcanic_vision_damage_is_the_returned_cards_mana_value() -> None:
    scenario = _scenario(
        [*MANA], ["Craw Wurm", "Wall of Omens"], hand=["Volcanic Vision"], graveyard=["Divination"]
    )
    divination = scenario.find("Divination", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    wall = scenario.creature("Wall of Omens", "bob")
    scenario.cast_and_resolve("Volcanic Vision", username="alice", targets=[divination], auto=True)
    assert wurm.damage == 3
    assert wall.damage == 3


def test_vengeful_rebirth_deals_damage_equal_to_a_nonland_cards_mana_value() -> None:
    scenario = _scenario([*MANA], hand=["Vengeful Rebirth"], graveyard=["Serra Angel"])
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    spell = scenario.cast_and_resolve(
        "Vengeful Rebirth", username="alice", targets=[angel, "bob"], auto=True
    )
    assert angel.zone is Zone.HAND
    assert _life(scenario, "bob") == 15
    assert spell.zone is Zone.EXILE


def test_vengeful_rebirth_a_land_card_returns_without_damage() -> None:
    scenario = _scenario([*MANA], hand=["Vengeful Rebirth"], graveyard=["Island"])
    island = scenario.find("Island", Zone.GRAVEYARD, "alice")
    spell = scenario.cast_and_resolve(
        "Vengeful Rebirth", username="alice", targets=[island, "bob"], auto=True
    )
    assert island.zone is Zone.HAND
    assert _life(scenario, "bob") == 20
    assert spell.zone is Zone.EXILE


def test_dead_reckoning_puts_the_card_on_top_and_deals_its_power() -> None:
    scenario = _scenario(
        [*MANA], ["Wurmcoil Engine"], hand=["Dead Reckoning"], graveyard=["Serra Angel"]
    )
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.will_take_the_may(True)
    scenario.cast_and_resolve("Dead Reckoning", username="alice", targets=[angel, wurm], auto=True)
    assert angel.zone is Zone.LIBRARY
    assert scenario.player("alice").library[0] is angel
    assert wurm.damage == 4


def test_dead_reckoning_declining_does_nothing() -> None:
    scenario = _scenario([*MANA], ["Craw Wurm"], hand=["Dead Reckoning"], graveyard=["Serra Angel"])
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.will_take_the_may(False)
    scenario.cast_and_resolve("Dead Reckoning", username="alice", targets=[angel, wurm], auto=True)
    assert angel.zone is Zone.GRAVEYARD
    assert wurm.damage == 0


# ---------------------------------------------------------------------------
# Exiling a creature card from a graveyard, then an amount from it
# ---------------------------------------------------------------------------


def test_scour_the_desert_makes_birds_equal_to_the_exiled_toughness() -> None:
    scenario = _scenario([*MANA], hand=["Scour the Desert"], graveyard=["Wall of Omens"])
    wall = scenario.find("Wall of Omens", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Scour the Desert", username="alice", targets=[wall], auto=True)
    assert wall.zone is Zone.EXILE
    birds = [p for p in scenario.game.battlefield if "Bird" in p.name]
    assert len(birds) == 4
    assert all(has_keyword(b, "flying", scenario.game) for b in birds)


def test_scour_the_desert_reads_the_cards_printed_toughness_in_the_graveyard() -> None:
    scenario = _scenario([*MANA], hand=["Scour the Desert"], graveyard=["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Scour the Desert", username="alice", targets=[bears], auto=True)
    assert len([p for p in scenario.game.battlefield if "Bird" in p.name]) == 2


def test_morbid_bloom_exiles_from_any_graveyard_and_makes_saprolings() -> None:
    scenario = _scenario([*MANA], hand=["Morbid Bloom"], bob_graveyard=["Wall of Omens"])
    wall = scenario.find("Wall of Omens", Zone.GRAVEYARD, "bob")
    scenario.cast_and_resolve("Morbid Bloom", username="alice", targets=[wall], auto=True)
    assert wall.zone is Zone.EXILE
    saprolings = [p for p in scenario.game.battlefield if "Saproling" in p.name]
    assert len(saprolings) == 4
    assert all(scenario.game.controller_of(s).username == "alice" for s in saprolings)


def test_ritual_of_the_returned_makes_a_zombie_with_the_cards_power_and_toughness() -> None:
    scenario = _scenario([*MANA], hand=["Ritual of the Returned"], graveyard=["Serra Angel"])
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve(
        "Ritual of the Returned", username="alice", targets=[angel], auto=True
    )
    assert angel.zone is Zone.EXILE
    (zombie,) = [p for p in scenario.game.battlefield if "Zombie" in p.name]
    assert (zombie.power, zombie.toughness) == (4, 4)


def test_ritual_of_the_returned_uses_unequal_power_and_toughness() -> None:
    scenario = _scenario([*MANA], hand=["Ritual of the Returned"], graveyard=["Wall of Omens"])
    wall = scenario.find("Wall of Omens", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Ritual of the Returned", username="alice", targets=[wall], auto=True)
    (zombie,) = [p for p in scenario.game.battlefield if "Zombie" in p.name]
    assert (zombie.power, zombie.toughness) == (0, 4)


def test_rotfeaster_maggot_gains_the_exiled_cards_toughness() -> None:
    scenario = _scenario([], hand=["Rotfeaster Maggot"], bob_graveyard=["Wall of Omens"])
    wall = scenario.find("Wall of Omens", Zone.GRAVEYARD, "bob")
    scenario.choose_trigger_targets("Rotfeaster Maggot", [wall])
    scenario.put_onto_battlefield("Rotfeaster Maggot", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert wall.zone is Zone.EXILE
    assert _life(scenario, "alice") == 24


def test_flesh_exiles_a_creature_card_and_puts_counters_equal_to_its_power() -> None:
    scenario = _scenario(
        [*MANA, "Grizzly Bears"], hand=["Flesh // Blood"], bob_graveyard=["Serra Angel"]
    )
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Flesh // Blood", username="alice", targets=[angel, bears], auto=True)
    assert angel.zone is Zone.EXILE
    assert bears.counters[Counter.PLUS_ONE] == 4


def test_flesh_counters_go_on_the_second_target_not_the_first() -> None:
    scenario = _scenario(
        [*MANA], ["Craw Wurm"], hand=["Flesh // Blood"], graveyard=["Grizzly Bears"]
    )
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_and_resolve("Flesh // Blood", username="alice", targets=[bears, wurm], auto=True)
    assert wurm.counters[Counter.PLUS_ONE] == 2


# ---------------------------------------------------------------------------
# Countering a spell, then an amount from it
# ---------------------------------------------------------------------------


def _countered(spell: str, counter: str):
    """Alice casts `spell` and holds priority-passing; bob answers with `counter`."""
    scenario = _scenario([*MANA], [*MANA], hand=[spell], bob_hand=[counter])
    target = scenario.cast_onto_stack(spell, username="alice", auto=True)
    scenario.pass_priority("alice")
    return scenario, target


def _answer(scenario, counter: str, target):
    return scenario.cast_and_resolve(counter, username="bob", targets=[target], auto=True)


def test_essence_backlash_counters_a_creature_spell_and_hits_its_controller() -> None:
    scenario, angel = _countered("Serra Angel", "Essence Backlash")
    _answer(scenario, "Essence Backlash", angel)
    assert angel.zone is Zone.GRAVEYARD
    assert _life(scenario, "alice") == 16
    assert _life(scenario, "bob") == 20


def test_essence_backlash_cannot_target_a_noncreature_spell() -> None:
    scenario, spell = _countered("Divination", "Essence Backlash")
    with pytest.raises(ValueError):
        scenario.cast("Essence Backlash", username="bob", targets=[spell])


def test_essence_backlash_a_zero_power_creature_spell_deals_nothing() -> None:
    scenario, wall = _countered("Wall of Omens", "Essence Backlash")
    _answer(scenario, "Essence Backlash", wall)
    assert wall.zone is Zone.GRAVEYARD
    assert _life(scenario, "alice") == 20


def test_overwhelming_intellect_draws_cards_equal_to_the_spells_mana_value() -> None:
    scenario, angel = _countered("Serra Angel", "Overwhelming Intellect")
    hand_before = len(scenario.player("bob").hand)
    _answer(scenario, "Overwhelming Intellect", angel)
    assert angel.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").hand) == hand_before - 1 + 5


def test_mystic_genesis_makes_an_ooze_as_big_as_the_spells_mana_value() -> None:
    scenario, angel = _countered("Serra Angel", "Mystic Genesis")
    _answer(scenario, "Mystic Genesis", angel)
    (ooze,) = [p for p in scenario.game.battlefield if "Ooze" in p.name]
    assert (ooze.power, ooze.toughness) == (5, 5)
    assert scenario.game.controller_of(ooze).username == "bob"


def test_mystic_genesis_counters_a_noncreature_spell_too() -> None:
    scenario, spell = _countered("Divination", "Mystic Genesis")
    _answer(scenario, "Mystic Genesis", spell)
    assert spell.zone is Zone.GRAVEYARD
    (ooze,) = [p for p in scenario.game.battlefield if "Ooze" in p.name]
    assert (ooze.power, ooze.toughness) == (3, 3)


def test_spell_swindle_makes_treasures_equal_to_the_spells_mana_value() -> None:
    scenario, angel = _countered("Serra Angel", "Spell Swindle")
    _answer(scenario, "Spell Swindle", angel)
    treasures = [p for p in scenario.game.battlefield if "Treasure" in p.name]
    assert len(treasures) == 5
    assert all(scenario.game.controller_of(t).username == "bob" for t in treasures)


def test_spell_swindle_counts_the_x_chosen_for_a_spell_on_the_stack() -> None:
    scenario = _scenario([*MANA], [*MANA], hand=["Fireball"], bob_hand=["Spell Swindle"])
    casting = scenario.cast("Fireball", "alice", targets=["bob"])
    casting.x_value = 3
    scenario.auto_pay(casting.begin_paying(), "alice")
    fireball = scenario.put_on_stack(casting)
    scenario.pass_priority("alice")
    _answer(scenario, "Spell Swindle", fireball)
    assert fireball.zone is Zone.GRAVEYARD
    assert len([p for p in scenario.game.battlefield if "Treasure" in p.name]) == 4


def test_spell_swindle_a_free_spell_makes_no_treasure() -> None:
    scenario, memnite = _countered("Memnite", "Spell Swindle")
    _answer(scenario, "Spell Swindle", memnite)
    assert memnite.zone is Zone.GRAVEYARD
    assert [p for p in scenario.game.battlefield if "Treasure" in p.name] == []


# ---------------------------------------------------------------------------
# Exiling a permanent, then life equal to its counters
# ---------------------------------------------------------------------------


def test_flay_essence_gains_life_equal_to_the_counters_on_the_exiled_creature() -> None:
    scenario = _scenario([*MANA], ["Grizzly Bears"], hand=["Flay Essence"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 3)
    scenario.cast_and_resolve("Flay Essence", username="alice", targets=[bears], auto=True)
    assert bears.zone is Zone.EXILE
    assert _life(scenario, "alice") == 23


def test_flay_essence_counts_counters_of_every_kind() -> None:
    scenario = _scenario([*MANA], ["Grizzly Bears"], hand=["Flay Essence"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    scenario.game.add_counters(bears, "shield", 1)
    scenario.cast_and_resolve("Flay Essence", username="alice", targets=[bears], auto=True)
    assert _life(scenario, "alice") == 23


def test_flay_essence_exiling_a_creature_with_no_counters_gains_nothing() -> None:
    scenario = _scenario([*MANA], ["Grizzly Bears"], hand=["Flay Essence"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Flay Essence", username="alice", targets=[bears], auto=True)
    assert bears.zone is Zone.EXILE
    assert _life(scenario, "alice") == 20


# ---------------------------------------------------------------------------
# The same readers on printings that are not in the listed set
# (Call for Blood, Tend the Pests, Corpse Lunge, Corpse
# Explosion, Morgue Burst, Lobelia Sackville-Baggins)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Call for Blood",
        "Tend the Pests",
        "Corpse Lunge",
        "Corpse Explosion",
        "Morgue Burst",
        "Lobelia Sackville-Baggins",
    ],
)
def test_the_proof_printings_are_handled(name: str) -> None:
    clauses = classify_clauses(card(name))
    assert all(clause.category == HANDLED for clause in clauses), [
        (clause.text, clause.category) for clause in clauses if clause.category != HANDLED
    ]


def test_call_for_blood_shrinks_the_target_by_the_sacrificed_power() -> None:
    scenario = _scenario([*MANA, "Serra Angel"], ["Craw Wurm"], hand=["Call for Blood"])
    angel = scenario.creature("Serra Angel", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_and_resolve(
        "Call for Blood", username="alice", targets=[wurm], sacrificing=[angel], auto=True
    )
    assert angel.zone is Zone.GRAVEYARD
    assert wurm.zone is Zone.GRAVEYARD


def test_call_for_blood_a_small_sacrifice_only_shrinks() -> None:
    scenario = _scenario([*MANA, "Grizzly Bears"], ["Craw Wurm"], hand=["Call for Blood"])
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_and_resolve(
        "Call for Blood", username="alice", targets=[wurm], sacrificing=[bears], auto=True
    )
    assert wurm.zone is Zone.BATTLEFIELD
    assert scenario.game.power_of(wurm) == 4
    assert scenario.game.toughness_of(wurm) == 2


def test_tend_the_pests_makes_pests_equal_to_the_sacrificed_power() -> None:
    scenario = _scenario([*MANA, "Serra Angel"], hand=["Tend the Pests"])
    angel = scenario.creature("Serra Angel", "alice")
    scenario.cast_and_resolve("Tend the Pests", username="alice", sacrificing=[angel], auto=True)
    assert len([p for p in scenario.game.battlefield if "Pest" in p.name]) == 4


def test_corpse_lunge_deals_damage_equal_to_the_exiled_cards_power() -> None:
    scenario = _scenario(
        [*MANA], ["Wurmcoil Engine"], hand=["Corpse Lunge"], graveyard=["Serra Angel"]
    )
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.cast_and_resolve(
        "Corpse Lunge", username="alice", targets=[wurm], exiling=[angel], auto=True
    )
    assert angel.zone is Zone.EXILE
    assert wurm.damage == 4


def test_corpse_lunge_a_zero_power_card_deals_no_damage() -> None:
    scenario = _scenario(
        [*MANA], ["Wurmcoil Engine"], hand=["Corpse Lunge"], graveyard=["Wall of Omens"]
    )
    wall = scenario.find("Wall of Omens", Zone.GRAVEYARD, "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.cast_and_resolve(
        "Corpse Lunge", username="alice", targets=[wurm], exiling=[wall], auto=True
    )
    assert wurm.damage == 0


def test_corpse_explosion_hits_every_creature() -> None:
    scenario = _scenario(
        [*MANA, "Wurmcoil Engine"],
        ["Wurmcoil Engine"],
        hand=["Corpse Explosion"],
        graveyard=["Serra Angel"],
    )
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    mine = scenario.creature("Wurmcoil Engine", "alice")
    theirs = scenario.creature("Wurmcoil Engine", "bob")
    scenario.cast_and_resolve("Corpse Explosion", username="alice", exiling=[angel], auto=True)
    assert angel.zone is Zone.EXILE
    assert mine.damage == 4
    assert theirs.damage == 4


def test_morgue_burst_returns_the_card_and_deals_damage_equal_to_its_power() -> None:
    scenario = _scenario([*MANA], hand=["Morgue Burst"], graveyard=["Serra Angel"])
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    scenario.cast_and_resolve("Morgue Burst", username="alice", targets=[angel, "bob"], auto=True)
    assert angel.zone is Zone.HAND
    assert _life(scenario, "bob") == 16


def test_lobelia_cannot_target_a_card_that_was_not_put_there_this_turn() -> None:
    scenario = _scenario([], [], hand=["Lobelia Sackville-Baggins"], bob_graveyard=["Serra Angel"])
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "bob")
    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Lobelia Sackville-Baggins", [angel])


def test_lobelia_exiles_a_card_and_makes_treasures_equal_to_its_power() -> None:
    scenario = _scenario([], ["Serra Angel"], hand=["Lobelia Sackville-Baggins"])
    bob_angel = scenario.creature("Serra Angel", "bob")
    scenario.game.destroy(bob_angel)
    scenario.state_based_actions()
    assert bob_angel.zone is Zone.GRAVEYARD
    scenario.choose_trigger_targets("Lobelia Sackville-Baggins", [bob_angel])
    scenario.put_onto_battlefield("Lobelia Sackville-Baggins", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert bob_angel.zone is Zone.EXILE
    assert len([p for p in scenario.game.battlefield if "Treasure" in p.name]) == 4
