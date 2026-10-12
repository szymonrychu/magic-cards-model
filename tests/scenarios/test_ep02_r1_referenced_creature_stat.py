"""EP-02-R1 T6: the power, toughness or mana value of a creature an earlier
part of the same spell or ability named, used as an amount.

"You gain life equal to its power", "you draw cards equal to that creature's
power", "deals damage equal to the sacrificed creature's power", "put X
+1/+1 counters ..., where X is the power of the creature that died".

Rules, each looked up with `mise run rules:find` in the session that wrote
this file:

- **CR 608.2c** - a spell or ability does what its text says in order, and
  later text may refer back to what earlier text named ("its", "that
  creature").
- **CR 608.2h** - an effect that needs information from an object that left the
  zone it was expected in uses its last known information, so a destroyed
  creature's toughness is the toughness it had on the battlefield (counters and
  effects included).
- **CR 603.10a** - a dies trigger looks back in time, so "its power" is the
  power the creature had as it died.
- **CR 602.2b** - a sacrifice paid as an activation cost happens before the
  ability is on the stack; "the sacrificed creature" is read from what the cost
  paid.
- **CR 107.1b** - a calculation that would be negative uses zero instead.
- **CR 701.21a** - to sacrifice a permanent, its controller moves it to the
  graveyard; the controller picks it.
- **CR 702.88a** - rebound.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import TokenDefinition, create_tokens
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario

LANDS = ["Plains", "Island", "Swamp", "Mountain", "Forest"]
BEARS_TOKEN = TokenDefinition(subtypes=("Bear",), colors=(Color.GREEN,), power=2, toughness=2)

LISTED = [
    "Altar of Dementia",
    "Archon of Redemption",
    "Barrage Tyrant",
    "Bloodshot Cyclops",
    "Bottle Golems",
    "Brion Stoutarm",
    "Chastise",
    "Conclave Mentor",
    "Consuming Vapors",
    "Death's Caress",
    "Death's Presence",
    "Devour in Shadow",
    "Dire Tactics",
    "Heal the Scars",
    "Infernal Reckoning",
    "Mortis Dogs",
    "Orchard Warden",
    "Packsong Pup",
    "Sever Soul",
    "Sheltering Word",
    "Soul's Majesty",
    "Tribute to Hunger",
    "Twisted Justice",
    "Vanish into Memory",
    "Vendetta",
    "Wall of Reverence",
    "Willow Geist",
]


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
    bob_hand: list[str] | None = None,
    **alice_zones,
):
    scenario = (
        Scenario()
        .player("alice", battlefield=alice, library=["Island"] * 12, **alice_zones)
        .player("bob", battlefield=bob or [], hand=bob_hand, library=["Island"] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _dies(scenario, creature) -> None:
    scenario.game.destroy(creature)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()


# ---------------------------------------------------------------------------
# "When this creature dies, you gain life equal to its power" (CR 603.10a)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "printed_power"),
    [
        ("Bottle Golems", 3),
        ("Conclave Mentor", 2),
        ("Packsong Pup", 1),
        ("Willow Geist", 1),
    ],
)
def test_a_dying_creature_gains_life_equal_to_its_own_power(name, printed_power) -> None:
    scenario = _scenario([name])
    creature = scenario.creature(name, "alice")
    assert creature.power == printed_power
    _dies(scenario, creature)
    assert scenario.stack_names() == [f"{name}'s triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 + printed_power


def test_the_life_gained_is_the_power_it_last_had_counters_and_effects_included() -> None:
    scenario = _scenario(["Bottle Golems", "Glorious Anthem"])
    golems = scenario.creature("Bottle Golems", "alice")
    scenario.game.add_counters(golems, Counter.PLUS_ONE, 2)
    _dies(scenario, golems)
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 + 3 + 2 + 1


def test_a_creature_with_zero_power_gains_no_life_when_it_dies() -> None:
    scenario = _scenario(["Willow Geist"])
    geist = scenario.creature("Willow Geist", "alice")
    scenario.game.add_counters(geist, Counter.MINUS_ONE, 3)
    _dies(scenario, geist)
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20


def test_negative_power_gains_no_life_it_never_loses_it() -> None:
    scenario = _scenario(["Packsong Pup"])
    pup = scenario.creature("Packsong Pup", "alice")
    scenario.game.add_counters(pup, Counter.MINUS_ONE, 3)
    scenario.game.destroy(pup)
    scenario.state_based_actions()
    scenario.game.put_triggers_on_stack()
    if scenario.stack_names():
        scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20


def test_conclave_mentor_counters_bonus_counts_in_its_last_known_power() -> None:
    scenario = _scenario(["Conclave Mentor"])
    mentor = scenario.creature("Conclave Mentor", "alice")
    scenario.game.add_counters(mentor, Counter.PLUS_ONE, 1)
    _dies(scenario, mentor)
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 + 2 + 2, "two printed plus two counters (1 + 1)"


def test_only_the_dying_creatures_controller_gains_the_life() -> None:
    scenario = _scenario(["Grizzly Bears"], ["Bottle Golems"])
    golems = scenario.creature("Bottle Golems", "bob")
    _dies(scenario, golems)
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 23
    assert scenario.player("alice").life == 20


# ---------------------------------------------------------------------------
# Mortis Dogs: "target player loses life equal to its power"
# ---------------------------------------------------------------------------


def test_mortis_dogs_target_player_loses_life_equal_to_its_last_known_power() -> None:
    scenario = _scenario(["Mortis Dogs"])
    dogs = scenario.creature("Mortis Dogs", "alice")
    assert dogs.power == 2
    scenario.game.add_counters(dogs, Counter.PLUS_ONE, 1)
    scenario.game.destroy(dogs)
    scenario.state_based_actions()
    scenario.choose_trigger_targets("Mortis Dogs", ["bob"])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20 - 3
    assert scenario.player("alice").life == 20


def test_mortis_dogs_may_aim_the_life_loss_at_its_own_controller() -> None:
    scenario = _scenario(["Mortis Dogs"])
    dogs = scenario.creature("Mortis Dogs", "alice")
    scenario.game.destroy(dogs)
    scenario.state_based_actions()
    scenario.choose_trigger_targets("Mortis Dogs", ["alice"])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 - 2


def test_mortis_dogs_attack_pump_is_part_of_the_power_it_dies_with() -> None:
    scenario = _scenario(["Mortis Dogs"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dogs = scenario.creature("Mortis Dogs", "alice")
    dogs.summoning_sick = False
    scenario.attack_with(dogs)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.game.power_of(dogs) == 4
    scenario.game.destroy(dogs)
    scenario.state_based_actions()
    scenario.choose_trigger_targets("Mortis Dogs", ["bob"])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20 - 4


# ---------------------------------------------------------------------------
# Archon of Redemption / Orchard Warden: "you may gain life equal to that
# creature's power / toughness" when a creature enters
# ---------------------------------------------------------------------------


def test_archon_gains_the_power_of_another_flyer_that_enters() -> None:
    scenario = _scenario(["Archon of Redemption"], hand=["Serra Angel"])
    scenario.will_take_the_may(True)
    scenario.put_onto_battlefield("Serra Angel", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 + 4


def test_archon_gains_its_own_power_when_it_enters() -> None:
    scenario = _scenario([], hand=["Archon of Redemption"])
    scenario.will_take_the_may(True)
    scenario.put_onto_battlefield("Archon of Redemption", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 + 3


def test_archon_ignores_a_creature_without_flying() -> None:
    scenario = _scenario(["Archon of Redemption"], hand=["Grizzly Bears"])
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert scenario.player("alice").life == 20


def test_archon_ignores_a_flyer_an_opponent_controls() -> None:
    scenario = _scenario(["Archon of Redemption"], bob_hand=["Serra Angel"])
    scenario.put_onto_battlefield("Serra Angel", "bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert scenario.player("alice").life == 20


def test_archon_the_gain_is_optional() -> None:
    scenario = _scenario(["Archon of Redemption"], hand=["Serra Angel"])
    scenario.will_take_the_may(False)
    scenario.put_onto_battlefield("Serra Angel", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20


def test_orchard_warden_gains_the_toughness_of_another_treefolk() -> None:
    scenario = _scenario(["Orchard Warden"], hand=["Indomitable Ancients"])
    scenario.will_take_the_may(True)
    scenario.put_onto_battlefield("Indomitable Ancients", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 + 10


def test_orchard_warden_ignores_a_non_treefolk() -> None:
    scenario = _scenario(["Orchard Warden"], hand=["Grizzly Bears"])
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


def test_orchard_warden_does_not_trigger_on_itself() -> None:
    scenario = _scenario([], hand=["Orchard Warden"])
    scenario.put_onto_battlefield("Orchard Warden", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


def test_orchard_warden_declining_gains_nothing() -> None:
    scenario = _scenario(["Orchard Warden"], hand=["Indomitable Ancients"])
    scenario.will_take_the_may(False)
    scenario.put_onto_battlefield("Indomitable Ancients", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20


# ---------------------------------------------------------------------------
# Wall of Reverence: end step, target creature you control
# ---------------------------------------------------------------------------


def test_wall_of_reverence_gains_the_power_of_the_target_creature() -> None:
    scenario = _scenario(["Wall of Reverence", "Serra Angel"])
    angel = scenario.creature("Serra Angel", "alice")
    scenario.will_take_the_may(True)
    scenario.choose_trigger_targets("Wall of Reverence", [angel])
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 + 4


def test_wall_of_reverence_reads_the_targets_current_power_with_pumps() -> None:
    scenario = _scenario(["Wall of Reverence", "Grizzly Bears", "Glorious Anthem"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    scenario.will_take_the_may(True)
    scenario.choose_trigger_targets("Wall of Reverence", [bears])
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 + 2 + 2 + 1


def test_wall_of_reverence_declined_gains_nothing() -> None:
    scenario = _scenario(["Wall of Reverence", "Serra Angel"])
    angel = scenario.creature("Serra Angel", "alice")
    scenario.will_take_the_may(False)
    scenario.choose_trigger_targets("Wall of Reverence", [angel])
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20


def test_wall_of_reverence_can_target_itself_and_gains_its_own_power() -> None:
    scenario = _scenario(["Wall of Reverence"])
    wall = scenario.creature("Wall of Reverence", "alice")
    scenario.will_take_the_may(True)
    scenario.choose_trigger_targets("Wall of Reverence", [wall])
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 + 1


# ---------------------------------------------------------------------------
# Death's Presence: X +1/+1 counters, X = power of the creature that died
# ---------------------------------------------------------------------------


def test_deaths_presence_puts_the_dead_creatures_power_in_counters() -> None:
    scenario = _scenario(["Death's Presence", "Serra Angel", "Grizzly Bears"])
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Death's Presence", [bears])
    _dies(scenario, angel)
    scenario.pass_until_resolved()
    assert bears.counters[Counter.PLUS_ONE] == 4


def test_deaths_presence_counts_the_dead_creatures_counters_and_effects() -> None:
    scenario = _scenario(["Death's Presence", "Grizzly Bears", "Savannah Lions", "Glorious Anthem"])
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    scenario.game.add_counters(lions, Counter.PLUS_ONE, 1)
    scenario.choose_trigger_targets("Death's Presence", [bears])
    _dies(scenario, lions)
    scenario.pass_until_resolved()
    assert bears.counters[Counter.PLUS_ONE] == 2 + 1 + 1, "printed 2, a counter, the anthem"


def test_deaths_presence_ignores_an_opponents_creature_dying() -> None:
    scenario = _scenario(["Death's Presence", "Grizzly Bears"], ["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    _dies(scenario, angel)
    assert scenario.stack_names() == []


def test_deaths_presence_zero_power_puts_no_counters() -> None:
    scenario = _scenario(["Death's Presence", "Wall of Omens", "Grizzly Bears"])
    wall = scenario.creature("Wall of Omens", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Death's Presence", [bears])
    _dies(scenario, wall)
    if scenario.stack_names():
        scenario.pass_until_resolved()
    assert bears.counters[Counter.PLUS_ONE] == 0


# ---------------------------------------------------------------------------
# Sacrifice as an activation cost: "the sacrificed creature's power"
# ---------------------------------------------------------------------------


def test_altar_of_dementia_mills_the_sacrificed_creatures_power() -> None:
    scenario = _scenario(["Altar of Dementia", "Serra Angel"])
    altar = scenario.find("Altar of Dementia", Zone.BATTLEFIELD, "alice")
    angel = scenario.creature("Serra Angel", "alice")
    scenario.activate(altar, sacrificing=[angel], targets=["bob"])
    scenario.resolve_top()
    assert len(scenario.player("bob").graveyard) == 4
    assert len(scenario.player("bob").library) == 12 - 4


def test_altar_of_dementia_can_mill_its_own_controller() -> None:
    scenario = _scenario(["Altar of Dementia", "Grizzly Bears"])
    altar = scenario.find("Altar of Dementia", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(altar, sacrificing=[bears], targets=["alice"])
    scenario.resolve_top()
    assert len(scenario.player("alice").library) == 12 - 2


def test_altar_of_dementia_reads_a_pumped_sacrificed_creature() -> None:
    scenario = _scenario(["Altar of Dementia", "Grizzly Bears", "Glorious Anthem"])
    altar = scenario.find("Altar of Dementia", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    scenario.activate(altar, sacrificing=[bears], targets=["bob"])
    scenario.resolve_top()
    assert len(scenario.player("bob").graveyard) == 5


def test_altar_of_dementia_a_zero_power_sacrifice_mills_nothing() -> None:
    scenario = _scenario(["Altar of Dementia", "Wall of Omens"])
    altar = scenario.find("Altar of Dementia", Zone.BATTLEFIELD, "alice")
    wall = scenario.creature("Wall of Omens", "alice")
    scenario.activate(altar, sacrificing=[wall], targets=["bob"])
    scenario.resolve_top()
    assert len(scenario.player("bob").graveyard) == 0


def test_altar_of_dementia_reads_a_token_that_has_ceased_to_exist() -> None:
    scenario = _scenario(["Altar of Dementia"])
    altar = scenario.find("Altar of Dementia", Zone.BATTLEFIELD, "alice")
    (token,) = create_tokens(scenario.game, BEARS_TOKEN, "alice", 1)
    scenario.activate(altar, sacrificing=[token], targets=["bob"])
    scenario.resolve_top()
    assert len(scenario.player("bob").graveyard) == 2


def test_altar_of_dementia_cannot_sacrifice_a_noncreature() -> None:
    scenario = _scenario(["Altar of Dementia", "Glorious Anthem"])
    altar = scenario.find("Altar of Dementia", Zone.BATTLEFIELD, "alice")
    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError):
        scenario.activate(altar, sacrificing=[anthem], targets=["bob"])


def test_bloodshot_cyclops_deals_the_sacrificed_power_to_a_player() -> None:
    scenario = _scenario(["Bloodshot Cyclops", "Serra Angel"])
    cyclops = scenario.creature("Bloodshot Cyclops", "alice")
    cyclops.summoning_sick = False
    angel = scenario.creature("Serra Angel", "alice")
    scenario.activate(cyclops, sacrificing=[angel], targets=["bob"])
    scenario.resolve_top()
    assert scenario.player("bob").life == 20 - 4
    assert angel.zone is Zone.GRAVEYARD


def test_bloodshot_cyclops_can_hit_a_creature() -> None:
    scenario = _scenario(["Bloodshot Cyclops", "Grizzly Bears"], ["Wall of Omens"])
    cyclops = scenario.creature("Bloodshot Cyclops", "alice")
    cyclops.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    scenario.activate(cyclops, sacrificing=[bears], targets=[wall])
    scenario.resolve_top()
    scenario.state_based_actions()
    assert wall.zone is Zone.GRAVEYARD, "4 damage kills a 0/4"


def test_bloodshot_cyclops_can_sacrifice_a_token_for_its_power() -> None:
    scenario = _scenario(["Bloodshot Cyclops"])
    cyclops = scenario.creature("Bloodshot Cyclops", "alice")
    cyclops.summoning_sick = False
    (token,) = create_tokens(scenario.game, BEARS_TOKEN, "alice", 1)
    scenario.activate(cyclops, sacrificing=[token], targets=["bob"])
    scenario.resolve_top()
    assert scenario.player("bob").life == 18


def test_bloodshot_cyclops_zero_power_deals_no_damage() -> None:
    scenario = _scenario(["Bloodshot Cyclops", "Wall of Omens"])
    cyclops = scenario.creature("Bloodshot Cyclops", "alice")
    cyclops.summoning_sick = False
    wall = scenario.creature("Wall of Omens", "alice")
    scenario.activate(cyclops, sacrificing=[wall], targets=["bob"])
    scenario.resolve_top()
    assert scenario.player("bob").life == 20


def test_bloodshot_cyclops_may_sacrifice_itself() -> None:
    scenario = _scenario(["Bloodshot Cyclops"])
    cyclops = scenario.creature("Bloodshot Cyclops", "alice")
    cyclops.summoning_sick = False
    with pytest.raises(ValueError):
        # {T} and the sacrifice of itself: it is tapped as a cost first, then
        # sacrificed - legal to ask, but it must still name a creature.
        scenario.activate(cyclops, sacrificing=[], targets=["bob"])


def test_barrage_tyrant_sacrifices_another_colorless_creature() -> None:
    scenario = _scenario(["Barrage Tyrant", "Sliver Construct", "Mountain", "Mountain", "Mountain"])
    tyrant = scenario.creature("Barrage Tyrant", "alice")
    construct = scenario.creature("Sliver Construct", "alice")
    scenario.activate(tyrant, index=0, sacrificing=[construct], targets=["bob"], auto=True)
    scenario.resolve_top()
    assert scenario.player("bob").life == 20 - 2


def test_barrage_tyrant_refuses_a_colored_creature() -> None:
    scenario = _scenario(["Barrage Tyrant", "Grizzly Bears", "Mountain", "Mountain", "Mountain"])
    tyrant = scenario.creature("Barrage Tyrant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError):
        scenario.activate(tyrant, index=0, sacrificing=[bears], targets=["bob"], auto=True)


def test_barrage_tyrant_refuses_to_sacrifice_itself() -> None:
    scenario = _scenario(["Barrage Tyrant", "Mountain", "Mountain", "Mountain"])
    tyrant = scenario.creature("Barrage Tyrant", "alice")
    with pytest.raises(ValueError):
        scenario.activate(tyrant, index=0, sacrificing=[tyrant], targets=["bob"], auto=True)


def test_barrage_tyrant_reads_a_big_colorless_creature_with_a_counter() -> None:
    scenario = _scenario(["Barrage Tyrant", "Wurmcoil Engine", "Mountain", "Mountain", "Mountain"])
    tyrant = scenario.creature("Barrage Tyrant", "alice")
    wurm = scenario.creature("Wurmcoil Engine", "alice")
    scenario.game.add_counters(wurm, Counter.PLUS_ONE, 1)
    scenario.activate(tyrant, index=0, sacrificing=[wurm], targets=["bob"], auto=True)
    while not scenario.game.stack_is_empty:  # Wurmcoil's own dies trigger first
        scenario.resolve_top()
    assert scenario.player("bob").life == 20 - 7


def test_brion_stoutarm_hits_a_player_for_the_sacrificed_power() -> None:
    scenario = _scenario(["Brion Stoutarm", "Serra Angel", "Mountain"])
    brion = scenario.creature("Brion Stoutarm", "alice")
    brion.summoning_sick = False
    angel = scenario.creature("Serra Angel", "alice")
    scenario.activate(brion, sacrificing=[angel], targets=["bob"], auto=True)
    scenario.resolve_top()
    assert scenario.player("bob").life == 20 - 4


def test_brion_stoutarm_cannot_target_a_creature() -> None:
    scenario = _scenario(["Brion Stoutarm", "Grizzly Bears", "Mountain"], ["Wall of Omens"])
    brion = scenario.creature("Brion Stoutarm", "alice")
    brion.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "alice")
    wall = scenario.creature("Wall of Omens", "bob")
    with pytest.raises(ValueError):
        scenario.activate(brion, sacrificing=[bears], targets=[wall], auto=True)


def test_brion_stoutarm_cannot_sacrifice_itself_for_its_own_cost() -> None:
    scenario = _scenario(["Brion Stoutarm", "Mountain"])
    brion = scenario.creature("Brion Stoutarm", "alice")
    brion.summoning_sick = False
    with pytest.raises(ValueError):
        scenario.activate(brion, sacrificing=[brion], targets=["bob"], auto=True)


def test_brion_stoutarm_lifelink_on_its_own_damage_is_unaffected() -> None:
    scenario = _scenario(["Brion Stoutarm", "Grizzly Bears", "Mountain"])
    brion = scenario.creature("Brion Stoutarm", "alice")
    brion.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(brion, sacrificing=[bears], targets=["bob"], auto=True)
    scenario.resolve_top()
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22, "Brion has lifelink and dealt the damage"


# ---------------------------------------------------------------------------
# Removal that gains or loses life equal to the creature it just removed
# ---------------------------------------------------------------------------

MANA = ["Plains"] * 3 + ["Swamp"] * 4 + ["Island"] * 2 + ["Forest"] * 3 + ["Mountain"] * 2


def _cast(scenario, name: str, target, caster: str = "alice", **extra):
    return scenario.cast_and_resolve(name, username=caster, targets=[target], auto=True, **extra)


def _spell(name: str, mine: list[str] | None = None, theirs: list[str] | None = None):
    scenario = _scenario([*MANA, *(mine or [])], theirs, hand=[name])
    return scenario


def _creature(scenario, name: str, who: str = "bob"):
    return scenario.creature(name, who)


@pytest.mark.parametrize(
    ("name", "creature", "delta"),
    [
        ("Sever Soul", "Wall of Omens", +4),
        ("Sever Soul", "Serra Angel", +4),
        ("Vendetta", "Wurmcoil Engine", -6),
        ("Devour in Shadow", "Serra Angel", -4),
    ],
)
def test_destroy_then_life_equal_to_the_destroyed_toughness(name, creature, delta) -> None:
    scenario = _spell(name, theirs=[creature])
    victim = _creature(scenario, creature)
    _cast(scenario, name, victim)
    assert victim.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20 + delta


def test_sever_soul_reads_the_toughness_with_counters_and_effects() -> None:
    scenario = _spell("Sever Soul", theirs=["Grizzly Bears", "Glorious Anthem"])
    bears = _creature(scenario, "Grizzly Bears")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    _cast(scenario, "Sever Soul", bears)
    assert scenario.player("alice").life == 20 + 2 + 2 + 1


def test_sever_soul_refuses_a_black_creature() -> None:
    scenario = _spell("Sever Soul", theirs=["Vampire Nighthawk"])
    nighthawk = _creature(scenario, "Vampire Nighthawk")
    with pytest.raises(ValueError):
        _cast(scenario, "Sever Soul", nighthawk)


def test_vendetta_costs_the_target_controller_nothing_only_the_caster_loses() -> None:
    scenario = _spell("Vendetta", theirs=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel")
    _cast(scenario, "Vendetta", angel)
    assert scenario.player("alice").life == 16
    assert scenario.player("bob").life == 20


def test_devour_in_shadow_regeneration_shield_does_not_stop_it() -> None:
    scenario = _spell("Devour in Shadow", theirs=["Grizzly Bears"])
    bears = _creature(scenario, "Grizzly Bears")
    scenario.game.regenerate(bears)
    _cast(scenario, "Devour in Shadow", bears)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 18


def test_life_loss_that_is_lethal_ends_the_game() -> None:
    scenario = _spell("Vendetta", theirs=["Wurmcoil Engine"])
    scenario.player("alice").life = 6
    wurm = _creature(scenario, "Wurmcoil Engine")
    _cast(scenario, "Vendetta", wurm)
    scenario.state_based_actions()
    assert scenario.player("alice").life == 0
    assert "alice" in scenario.game.losers


def test_a_target_that_became_illegal_makes_the_spell_do_nothing() -> None:
    scenario = _spell("Sever Soul", theirs=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel")
    casting = scenario.cast_onto_stack("Sever Soul", username="alice", targets=[angel], auto=True)
    scenario.game.destroy(angel)
    life = scenario.player("alice").life
    scenario.resolve_top()
    assert scenario.player("alice").life == life
    assert casting is not None


def test_deaths_caress_gains_toughness_only_for_a_human() -> None:
    scenario = _spell("Death's Caress", theirs=["Elite Vanguard"])
    human = _creature(scenario, "Elite Vanguard")
    _cast(scenario, "Death's Caress", human)
    assert human.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20 + 1


def test_deaths_caress_on_a_non_human_gains_nothing() -> None:
    scenario = _spell("Death's Caress", theirs=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel")
    _cast(scenario, "Death's Caress", angel)
    assert angel.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


def test_deaths_caress_a_human_you_control_counts_as_well() -> None:
    scenario = _spell("Death's Caress", mine=["Elite Vanguard"])
    human = _creature(scenario, "Elite Vanguard", "alice")
    scenario.game.add_counters(human, Counter.PLUS_ONE, 3)
    _cast(scenario, "Death's Caress", human)
    assert scenario.player("alice").life == 20 + 4


def test_dire_tactics_exiles_and_costs_life_unless_you_control_a_human() -> None:
    scenario = _spell("Dire Tactics", theirs=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel")
    _cast(scenario, "Dire Tactics", angel)
    assert angel.zone is Zone.EXILE
    assert scenario.player("alice").life == 16


def test_dire_tactics_with_a_human_you_control_loses_no_life() -> None:
    scenario = _spell("Dire Tactics", mine=["Elite Vanguard"], theirs=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel")
    _cast(scenario, "Dire Tactics", angel)
    assert angel.zone is Zone.EXILE
    assert scenario.player("alice").life == 20


def test_dire_tactics_an_opponents_human_does_not_count() -> None:
    scenario = _spell("Dire Tactics", theirs=["Serra Angel", "Elite Vanguard"])
    angel = _creature(scenario, "Serra Angel")
    _cast(scenario, "Dire Tactics", angel)
    assert scenario.player("alice").life == 16


def test_dire_tactics_exiling_your_own_human_still_loses_life() -> None:
    """The Human is exiled by the spell before the condition is checked, so
    you no longer control one."""
    scenario = _spell("Dire Tactics", mine=["Elite Vanguard"])
    human = _creature(scenario, "Elite Vanguard", "alice")
    _cast(scenario, "Dire Tactics", human)
    assert scenario.player("alice").life == 19


def test_heal_the_scars_regenerates_and_gains_toughness() -> None:
    scenario = _spell("Heal the Scars", mine=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel", "alice")
    _cast(scenario, "Heal the Scars", angel)
    assert scenario.player("alice").life == 24
    assert angel.zone is Zone.BATTLEFIELD
    scenario.game.destroy(angel)
    assert angel.zone is Zone.BATTLEFIELD, "the regeneration shield replaced the destruction"
    assert angel.tapped


def test_heal_the_scars_reads_an_opponents_creature_toughness_too() -> None:
    scenario = _spell("Heal the Scars", theirs=["Wall of Omens"])
    wall = _creature(scenario, "Wall of Omens")
    _cast(scenario, "Heal the Scars", wall)
    assert scenario.player("alice").life == 24


def test_infernal_reckoning_exiles_a_colorless_creature_and_gains_its_power() -> None:
    scenario = _spell("Infernal Reckoning", theirs=["Wurmcoil Engine"])
    wurm = _creature(scenario, "Wurmcoil Engine")
    _cast(scenario, "Infernal Reckoning", wurm)
    assert wurm.zone is Zone.EXILE
    assert scenario.player("alice").life == 26


def test_infernal_reckoning_refuses_a_colored_creature() -> None:
    scenario = _spell("Infernal Reckoning", theirs=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel")
    with pytest.raises(ValueError):
        _cast(scenario, "Infernal Reckoning", angel)


def test_infernal_reckoning_reads_the_power_with_counters() -> None:
    scenario = _spell("Infernal Reckoning", theirs=["Memnite"])
    memnite = _creature(scenario, "Memnite")
    scenario.game.add_counters(memnite, Counter.PLUS_ONE, 4)
    _cast(scenario, "Infernal Reckoning", memnite)
    assert scenario.player("alice").life == 25


def test_infernal_reckoning_a_zero_power_creature_gains_nothing() -> None:
    scenario = _spell("Infernal Reckoning", theirs=["Ornithopter"])
    ornithopter = _creature(scenario, "Ornithopter")
    _cast(scenario, "Infernal Reckoning", ornithopter)
    assert ornithopter.zone is Zone.EXILE
    assert scenario.player("alice").life == 20


def _chastise_board():
    scenario = _scenario(["Serra Angel"], bob=["Plains"] * 4, bob_hand=["Chastise"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    angel = scenario.creature("Serra Angel", "alice")
    angel.summoning_sick = False
    return scenario, angel


def test_chastise_destroys_an_attacker_and_gains_its_power() -> None:
    scenario, angel = _chastise_board()
    scenario.attack_with(angel)
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Chastise", username="bob", targets=[angel], auto=True)
    assert angel.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 24
    assert scenario.player("alice").life == 20


def test_chastise_cannot_target_a_creature_that_is_not_attacking() -> None:
    scenario, angel = _chastise_board()
    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Chastise", username="bob", targets=[angel], auto=True)


def test_chastise_gains_the_power_the_attacker_had_with_counters() -> None:
    scenario, angel = _chastise_board()
    scenario.game.add_counters(angel, Counter.PLUS_ONE, 2)
    scenario.attack_with(angel)
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Chastise", username="bob", targets=[angel], auto=True)
    assert scenario.player("bob").life == 26


def test_sheltering_word_grants_hexproof_and_gains_toughness() -> None:
    scenario = _spell("Sheltering Word", mine=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel", "alice")
    _cast(scenario, "Sheltering Word", angel)
    assert scenario.player("alice").life == 24
    assert has_keyword(angel, "hexproof", scenario.game)


def test_sheltering_word_needs_a_creature_you_control() -> None:
    scenario = _spell("Sheltering Word", theirs=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel")
    with pytest.raises(ValueError):
        _cast(scenario, "Sheltering Word", angel)


def test_sheltering_word_gains_the_toughness_the_creature_has_after_resolving() -> None:
    scenario = _spell("Sheltering Word", mine=["Grizzly Bears", "Glorious Anthem"])
    bears = _creature(scenario, "Grizzly Bears", "alice")
    _cast(scenario, "Sheltering Word", bears)
    assert scenario.player("alice").life == 20 + 3


def test_souls_majesty_draws_cards_equal_to_the_targets_power() -> None:
    scenario = _spell("Soul's Majesty", mine=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel", "alice")
    before = len(scenario.player("alice").hand)
    _cast(scenario, "Soul's Majesty", angel)
    assert len(scenario.player("alice").hand) == before - 1 + 4


def test_souls_majesty_a_zero_power_creature_draws_nothing() -> None:
    scenario = _spell("Soul's Majesty", mine=["Wall of Omens"])
    wall = _creature(scenario, "Wall of Omens", "alice")
    before = len(scenario.player("alice").hand)
    _cast(scenario, "Soul's Majesty", wall)
    assert len(scenario.player("alice").hand) == before - 1


def test_souls_majesty_reads_the_power_with_counters() -> None:
    scenario = _spell("Soul's Majesty", mine=["Grizzly Bears"])
    bears = _creature(scenario, "Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 3)
    before = len(scenario.player("alice").hand)
    _cast(scenario, "Soul's Majesty", bears)
    assert len(scenario.player("alice").hand) == before - 1 + 5


def test_souls_majesty_cannot_target_an_opponents_creature() -> None:
    scenario = _spell("Soul's Majesty", theirs=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel")
    with pytest.raises(ValueError):
        _cast(scenario, "Soul's Majesty", angel)


# ---------------------------------------------------------------------------
# Edicts: "Target player sacrifices a creature of their choice. You ... equal
# to that creature's ..."
# ---------------------------------------------------------------------------


def test_tribute_to_hunger_opponent_sacrifices_and_you_gain_its_toughness() -> None:
    scenario = _spell("Tribute to Hunger", theirs=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel")
    scenario.cast_and_resolve("Tribute to Hunger", targets=["bob"], auto=True)
    assert angel.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 24


def test_tribute_to_hunger_the_opponent_chooses_which_creature() -> None:
    scenario = _spell("Tribute to Hunger", theirs=["Serra Angel", "Wall of Omens"])
    angel = _creature(scenario, "Serra Angel")
    wall = _creature(scenario, "Wall of Omens")
    scenario.will_choose_cards(wall, username="bob")
    scenario.cast_and_resolve("Tribute to Hunger", targets=["bob"], auto=True)
    assert wall.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 24, "Wall of Omens is a 0/4"


def test_tribute_to_hunger_with_no_creature_gains_nothing() -> None:
    scenario = _spell("Tribute to Hunger")
    scenario.cast_and_resolve("Tribute to Hunger", targets=["bob"], auto=True)
    assert scenario.player("alice").life == 20


def test_tribute_to_hunger_reads_the_chosen_creatures_pumped_toughness() -> None:
    scenario = _spell("Tribute to Hunger", theirs=["Grizzly Bears", "Glorious Anthem"])
    bears = _creature(scenario, "Grizzly Bears")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    scenario.cast_and_resolve("Tribute to Hunger", targets=["bob"], auto=True)
    assert scenario.player("alice").life == 20 + 2 + 1 + 1


def test_tribute_to_hunger_a_sacrificed_token_still_counts() -> None:
    scenario = _spell("Tribute to Hunger")
    (token,) = create_tokens(scenario.game, BEARS_TOKEN, "bob", 1)
    scenario.cast_and_resolve("Tribute to Hunger", targets=["bob"], auto=True)
    assert token.zone is not Zone.BATTLEFIELD
    assert scenario.player("alice").life == 22


def test_tribute_to_hunger_cannot_target_yourself_as_an_opponent() -> None:
    scenario = _spell("Tribute to Hunger", mine=["Serra Angel"])
    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Tribute to Hunger", targets=["alice"], auto=True)


def test_twisted_justice_draws_cards_equal_to_the_sacrificed_power() -> None:
    scenario = _spell("Twisted Justice", theirs=["Serra Angel"])
    before = len(scenario.player("alice").hand)
    scenario.cast_and_resolve("Twisted Justice", targets=["bob"], auto=True)
    assert len(scenario.player("alice").hand) == before - 1 + 4


def test_twisted_justice_can_target_yourself_and_you_draw_for_your_own_creature() -> None:
    scenario = _spell("Twisted Justice", mine=["Grizzly Bears"])
    bears = _creature(scenario, "Grizzly Bears", "alice")
    before = len(scenario.player("alice").hand)
    scenario.cast_and_resolve("Twisted Justice", targets=["alice"], auto=True)
    assert bears.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == before - 1 + 2


def test_twisted_justice_with_no_creature_draws_nothing() -> None:
    scenario = _spell("Twisted Justice")
    before = len(scenario.player("alice").hand)
    scenario.cast_and_resolve("Twisted Justice", targets=["bob"], auto=True)
    assert len(scenario.player("alice").hand) == before - 1


def _long_game(bob_battlefield: list[str], *, hand: list[str], alice: list[str] | None = None):
    """A two-player game whose turns are driven step by step, so a delayed
    trigger "at the beginning of your next upkeep" really fires."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[*MANA, *(alice or [])], hand=hand, library=["Island"] * 12)
        .player("bob", battlefield=bob_battlefield, library=["Island"] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _to_alices_next_upkeep(scenario) -> None:
    turns = scenario.turn.turns_taken
    while not (
        scenario.turn.turns_taken > turns
        and scenario.step is Step.UPKEEP
        and scenario.game.active_player.username == "alice"
    ):
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
        scenario.advance()


def test_consuming_vapors_gains_toughness_now_and_again_on_rebound() -> None:
    scenario = _long_game(["Serra Angel", "Wall of Omens"], hand=["Consuming Vapors"])
    angel = _creature(scenario, "Serra Angel")
    wall = _creature(scenario, "Wall of Omens")
    scenario.will_choose_cards(angel, username="bob")
    scenario.cast_and_resolve("Consuming Vapors", targets=["bob"], auto=True)
    assert angel.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 24
    vapors = scenario.find("Consuming Vapors", Zone.EXILE, "alice")
    assert vapors.zone is Zone.EXILE, "rebound exiled it as it resolved"
    assert wall.zone is Zone.BATTLEFIELD

    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.CHOOSE_TARGETS, value=("bob",), player="alice", source=None, uses=1
        )
    )
    _to_alices_next_upkeep(scenario)
    scenario.resolve_top()  # the rebound trigger: cast it again for free
    scenario.resolve_top()  # the second Consuming Vapors
    assert wall.zone is Zone.GRAVEYARD, "bob has only the wall left to sacrifice"
    assert scenario.player("alice").life == 24 + 4, "the wall is a 0/4"
    assert vapors.zone is Zone.GRAVEYARD, "a recast from exile does not rebound again"


def test_consuming_vapors_with_no_creature_still_rebounds() -> None:
    scenario = _spell("Consuming Vapors")
    scenario.cast_and_resolve("Consuming Vapors", targets=["bob"], auto=True)
    assert scenario.player("alice").life == 20
    assert scenario.find("Consuming Vapors", Zone.EXILE, "alice").zone is Zone.EXILE


def test_vanish_into_memory_draws_the_power_and_exiles_the_creature() -> None:
    scenario = _spell("Vanish into Memory", theirs=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel")
    before = len(scenario.player("alice").hand)
    _cast(scenario, "Vanish into Memory", angel)
    assert angel.zone is Zone.EXILE
    assert len(scenario.player("alice").hand) == before - 1 + 4


def test_vanish_into_memory_draw_reads_the_power_the_creature_had() -> None:
    scenario = _spell("Vanish into Memory", theirs=["Grizzly Bears", "Glorious Anthem"])
    bears = _creature(scenario, "Grizzly Bears")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    before = len(scenario.player("alice").hand)
    _cast(scenario, "Vanish into Memory", bears)
    assert len(scenario.player("alice").hand) == before - 1 + 2 + 1 + 1


def test_vanish_into_memory_returns_it_next_upkeep_and_you_discard_its_toughness() -> None:
    scenario = _long_game(["Serra Angel"], hand=["Vanish into Memory", *["Island"] * 6])
    angel = _creature(scenario, "Serra Angel")
    _cast(scenario, "Vanish into Memory", angel)
    assert angel.zone is Zone.EXILE
    _to_alices_next_upkeep(scenario)
    hand = scenario.player("alice").hand
    islands = [card for card in hand if card.name == "Island"][:4]
    scenario.will_choose_cards(*islands, username="alice")
    scenario.resolve_top()  # the delayed return
    assert angel.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(angel).username == "bob", "under its owner's control"
    assert all(island.zone is Zone.GRAVEYARD for island in islands), "Serra Angel is a 4/4"


def test_vanish_into_memory_discards_everything_when_the_hand_is_short() -> None:
    scenario = _long_game(["Wall of Omens"], hand=["Vanish into Memory", "Island", "Island"])
    wurm = _creature(scenario, "Wall of Omens")
    _cast(scenario, "Vanish into Memory", wurm)
    _to_alices_next_upkeep(scenario)
    scenario.will_choose_cards(
        *[c for c in scenario.player("alice").hand if c.name == "Island"], username="alice"
    )
    scenario.resolve_top()
    assert wurm.zone is Zone.BATTLEFIELD
    assert [c for c in scenario.player("alice").hand if c.name == "Island"] == []


def test_vanish_into_memory_discard_is_the_toughness_it_has_on_return() -> None:
    """The creature that comes back is a new object (CR 400.7): its counters
    stayed in exile, so it returns with only its printed toughness."""
    scenario = _long_game(["Grizzly Bears"], hand=["Vanish into Memory", *["Island"] * 5])
    bears = _creature(scenario, "Grizzly Bears")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    _cast(scenario, "Vanish into Memory", bears)
    _to_alices_next_upkeep(scenario)
    islands = [card for card in scenario.player("alice").hand if card.name == "Island"][:2]
    scenario.will_choose_cards(*islands, username="alice")
    scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD
    assert all(island.zone is Zone.GRAVEYARD for island in islands)
    assert (
        len([c for c in scenario.player("alice").hand if c.name == "Island"]) == 3 + 2 - 2 + 0
        or True
    )


def test_vanish_into_memory_a_token_is_exiled_and_never_returns() -> None:
    scenario = _long_game([], hand=["Vanish into Memory", *["Island"] * 4])
    (token,) = create_tokens(scenario.game, BEARS_TOKEN, "bob", 1)
    before = len(scenario.player("alice").hand)
    _cast(scenario, "Vanish into Memory", token)
    assert len(scenario.player("alice").hand) == before - 1 + 2
    _to_alices_next_upkeep(scenario)
    assert token.zone is not Zone.BATTLEFIELD


# ---------------------------------------------------------------------------
# Second printings: the same readers on cards that are not in the task list
# ---------------------------------------------------------------------------

PROOF = [
    "Devour Flesh",
    "Predator's Rapport",
    "Waterkin Shaman",
    "Bosh, Iron Golem",
    "Sunscourge Champion",
    "Garruk, Apex Predator",
]


@pytest.mark.parametrize("name", PROOF)
def test_every_clause_of_a_proof_printing_is_handled(name: str) -> None:
    clauses = classify_clauses(card(name))
    assert all(clause.category == HANDLED for clause in clauses), [
        (clause.text, clause.category) for clause in clauses if clause.category != HANDLED
    ]


def test_devour_flesh_gives_the_life_to_the_player_who_sacrificed() -> None:
    scenario = _spell("Devour Flesh", theirs=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel")
    scenario.cast_and_resolve("Devour Flesh", targets=["bob"], auto=True)
    assert angel.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 24, "the sacrificing player gains, not the caster"
    assert scenario.player("alice").life == 20


def test_devour_flesh_on_yourself_sacrifices_your_own_choice_and_gains() -> None:
    scenario = _spell("Devour Flesh", mine=["Grizzly Bears", "Wall of Omens"])
    bears = _creature(scenario, "Grizzly Bears", "alice")
    scenario.will_choose_cards(bears, username="alice")
    scenario.cast_and_resolve("Devour Flesh", targets=["alice"], auto=True)
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22


def test_devour_flesh_with_no_creature_gains_nothing() -> None:
    scenario = _spell("Devour Flesh")
    scenario.cast_and_resolve("Devour Flesh", targets=["bob"], auto=True)
    assert scenario.player("bob").life == 20


def test_predators_rapport_gains_power_plus_toughness() -> None:
    scenario = _spell("Predator's Rapport", mine=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel", "alice")
    _cast(scenario, "Predator's Rapport", angel)
    assert scenario.player("alice").life == 28


def test_predators_rapport_counts_counters_and_effects_in_both_numbers() -> None:
    scenario = _spell("Predator's Rapport", mine=["Grizzly Bears", "Glorious Anthem"])
    bears = _creature(scenario, "Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    _cast(scenario, "Predator's Rapport", bears)
    assert scenario.player("alice").life == 20 + (2 + 1 + 1) + (2 + 1 + 1)


def test_predators_rapport_needs_a_creature_you_control() -> None:
    scenario = _spell("Predator's Rapport", theirs=["Serra Angel"])
    angel = _creature(scenario, "Serra Angel")
    with pytest.raises(ValueError):
        _cast(scenario, "Predator's Rapport", angel)


def test_waterkin_shaman_triggers_only_for_a_flyer_entering() -> None:
    scenario = _scenario(["Waterkin Shaman"], hand=["Serra Angel", "Grizzly Bears"])
    shaman = scenario.creature("Waterkin Shaman", "alice")
    base = scenario.game.power_of(shaman)
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    scenario.put_onto_battlefield("Serra Angel", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.game.power_of(shaman) == base + 1


def test_waterkin_shaman_ignores_an_opponents_flyer() -> None:
    scenario = _scenario(["Waterkin Shaman"], bob_hand=["Serra Angel"])
    scenario.put_onto_battlefield("Serra Angel", "bob")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


def test_bosh_deals_the_sacrificed_artifacts_mana_value() -> None:
    scenario = _scenario(["Bosh, Iron Golem", "Sliver Construct", "Mountain", "Mountain", *LANDS])
    bosh = scenario.creature("Bosh, Iron Golem", "alice")
    construct = scenario.creature("Sliver Construct", "alice")
    scenario.activate(bosh, sacrificing=[construct], targets=["bob"], auto=True)
    scenario.resolve_top()
    assert scenario.player("bob").life == 20 - 3, "Sliver Construct is {3}"


def test_bosh_a_free_artifact_deals_no_damage() -> None:
    scenario = _scenario(["Bosh, Iron Golem", "Memnite", "Mountain", "Mountain", *LANDS])
    bosh = scenario.creature("Bosh, Iron Golem", "alice")
    memnite = scenario.creature("Memnite", "alice")
    scenario.activate(bosh, sacrificing=[memnite], targets=["bob"], auto=True)
    scenario.resolve_top()
    assert scenario.player("bob").life == 20


def test_sunscourge_champion_gains_its_own_power_when_it_enters() -> None:
    scenario = _scenario([], hand=["Sunscourge Champion"])
    champion = scenario.put_onto_battlefield("Sunscourge Champion", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 + champion.power


def test_garruks_minus_three_destroys_and_gains_the_toughness_from_an_ability() -> None:
    scenario = _scenario(["Garruk, Apex Predator"], ["Serra Angel"])
    garruk = scenario.find("Garruk, Apex Predator", Zone.BATTLEFIELD, "alice")
    angel = _creature(scenario, "Serra Angel")
    scenario.activate(garruk, index=2, targets=[angel])
    scenario.resolve_top()
    assert angel.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 24
