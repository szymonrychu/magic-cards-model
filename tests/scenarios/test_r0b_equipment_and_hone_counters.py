"""Scenario: Equipment granting keywords and P/T, and hone counters.

Lavaspur Boots ("+1/+0 and has haste and ward {1}"), Leyline Axe ("+1/+1 and
has double strike and trample", plus the opening-hand begin-on-battlefield
line), Basilisk Collar ("has deathtouch and lifelink") and Dwalin,
Weaponmaster's hone counters, each played through the engine.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 702.6a** - Equip: "[Cost]: Attach this permanent to target creature
  you control. Activate only as a sorcery."
- **CR 704.5n** - an Equipment attached to an illegal permanent becomes
  unattached and stays on the battlefield.
- **CR 702.10b** - a creature with haste can attack even if it hasn't been
  controlled continuously since its controller's most recent turn began.
- **CR 702.21a** - ward counters a spell or ability an opponent controls
  that targets it, unless that player pays the ward cost.
- **CR 103.6a** - a card allowing a player to begin the game with it on the
  battlefield is put onto the battlefield by that player.
- **CR 702.4b** - double strike: a creature deals damage in both the
  first-strike and the regular combat damage step.
- **CR 702.19b** - trample: excess damage beyond lethal to the blockers may
  be assigned to the player.
- **CR 702.2b** - any damage from a deathtouch source destroys the creature.
- **CR 702.15b** - damage from a lifelink source makes its controller gain
  that much life.
- **CR 702.7b** - first strike: only first and double strikers deal damage
  in the first combat damage step.
- **CR 122.1j** - "A hone counter on an Equipment gives +1/+0 to any
  creature that Equipment is attached to."
- **CR 603.6a** - an enters ability triggers when its permanent enters.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.machines.keywords import equip_activation, equipped_creature
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def _resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _equip(scenario, equipment, target, *sources, username="alice"):
    activation = equip_activation(scenario.game, equipment, target, username)
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    return activation.resolve()


def _board(alice, bob=(), *, hand=(), bob_hand=()):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(hand),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), hand=list(bob_hand), library=["Island"] * 5)
        .build()
    )


def _to_declare_attackers(scenario):
    scenario.start_at(Step.DECLARE_ATTACKERS)


# -- Lavaspur Boots -----------------------------------------------------------


def test_lavaspur_boots_gives_plus_one_zero_haste_and_ward():
    scenario = _board(["Lavaspur Boots", "Mountain"], hand=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    boots = scenario.find("Lavaspur Boots", Zone.BATTLEFIELD, "alice")
    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert _equip(scenario, boots, bears, *scenario.untapped_sources("Mountain")) is bears
    chars = _chars(scenario, bears)

    assert (chars.power, chars.toughness) == (3, 2)
    assert "Haste" in chars.abilities
    assert any(ability.startswith("Ward") for ability in chars.abilities)


def test_lavaspur_boots_haste_lets_a_fresh_creature_attack():
    """CR 702.10b: the Bears entered this turn and still attack."""
    scenario = _board(["Lavaspur Boots", "Mountain"], hand=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    boots = scenario.find("Lavaspur Boots", Zone.BATTLEFIELD, "alice")
    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")
    _equip(scenario, boots, bears, *scenario.untapped_sources("Mountain"))

    scenario.advance()
    scenario.advance()
    assert scenario.step is Step.DECLARE_ATTACKERS
    scenario.attack_with(bears)
    assert bears in scenario.attackers()


def test_an_unequipped_fresh_creature_still_cannot_attack():
    scenario = _board(["Lavaspur Boots", "Mountain"], hand=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice")

    scenario.advance()
    scenario.advance()
    assert not scenario.can_attack(bears)


def test_lavaspur_boots_ward_counters_an_opponents_unpaid_spell():
    """CR 702.21a: Bob's Bolt targets the equipped Bears; he declines the {1}."""
    scenario = _board(
        ["Lavaspur Boots", "Mountain", "Grizzly Bears"],
        ["Mountain", "Mountain"],
        bob_hand=["Lightning Bolt"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    boots = scenario.find("Lavaspur Boots", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _equip(scenario, boots, bears, *scenario.untapped_sources("Mountain", username="alice"))
    scenario.game.pass_priority("alice")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt",
        scenario.untapped_sources("Mountain", username="bob")[0],
        targets=[bears],
        username="bob",
    )
    assert len(scenario.game.stack) == 2, "the ward trigger waits above the Bolt"
    scenario.will_pay_the_mana_cost(False)
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0


def test_lavaspur_boots_ward_does_not_trigger_on_its_controllers_own_spell():
    scenario = _board(
        ["Lavaspur Boots", "Mountain", "Mountain", "Grizzly Bears"],
        hand=["Lightning Bolt"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    boots = scenario.find("Lavaspur Boots", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    first, second = scenario.untapped_sources("Mountain", "Mountain")
    _equip(scenario, boots, bears, first)

    scenario.cast_onto_stack("Lightning Bolt", second, targets=[bears])

    assert len(scenario.game.stack) == 1


def test_moving_lavaspur_boots_moves_the_bonus():
    scenario = _board(["Lavaspur Boots", "Mountain", "Mountain", "Grizzly Bears", "Watchwolf"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    boots = scenario.find("Lavaspur Boots", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "alice")
    first, second = scenario.untapped_sources("Mountain", "Mountain")

    _equip(scenario, boots, bears, first)
    _equip(scenario, boots, wolf, second)

    assert equipped_creature(scenario.game, boots) is wolf
    assert (_chars(scenario, bears).power, _chars(scenario, wolf).power) == (2, 4)
    assert "Haste" not in _chars(scenario, bears).abilities


def test_lavaspur_boots_equip_is_sorcery_speed():
    scenario = _board(["Lavaspur Boots", "Mountain", "Grizzly Bears"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    boots = scenario.find("Lavaspur Boots", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    activation = equip_activation(scenario.game, boots, bears, "alice")
    assert "only be activated as a sorcery" in (activation.why_not() or "")


# -- Leyline Axe --------------------------------------------------------------


def test_leyline_axe_may_begin_the_game_on_the_battlefield():
    """CR 103.6a's begin-on-battlefield option, taken."""
    scenario = (
        Scenario()
        .player("alice", hand=["Leyline Axe", "Forest"], library=["Forest"] * 3)
        .player("bob", library=["Mountain"] * 3)
        .build()
    )
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.OPENING_HAND_ACTION,
            value=True,
            player="alice",
            source="Leyline Axe",
        )
    )

    scenario.game.take_opening_hand_actions()

    assert [state.name for state in scenario.game.battlefield] == ["Leyline Axe"]
    assert [state.name for state in scenario.player("alice").hand] == ["Forest"]


def test_leyline_axe_declined_stays_in_hand():
    scenario = (
        Scenario()
        .player("alice", hand=["Leyline Axe"], library=["Forest"] * 3)
        .player("bob", library=["Mountain"] * 3)
        .build()
    )

    scenario.game.take_opening_hand_actions()

    assert scenario.game.battlefield == []
    assert [state.name for state in scenario.player("alice").hand] == ["Leyline Axe"]


def _axe_board(bob=()):
    scenario = _board(["Leyline Axe", "Mountain", "Mountain", "Mountain", "Grizzly Bears"], bob)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    axe = scenario.find("Leyline Axe", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _equip(scenario, axe, bears, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"))
    return scenario, axe, bears


def test_leyline_axe_gives_plus_one_double_strike_and_trample():
    scenario, _, bears = _axe_board()
    chars = _chars(scenario, bears)

    assert (chars.power, chars.toughness) == (3, 3)
    assert {"Double strike", "Trample"} <= set(chars.abilities)


def test_leyline_axe_unblocked_deals_damage_twice():
    """CR 702.4b: 3 in the first-strike step and 3 again in the regular one."""
    scenario, _, bears = _axe_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()

    scenario.combat_damage()

    assert scenario.player("bob").life == 14


def test_leyline_axe_tramples_over_a_chump_blocker_in_both_steps():
    """CR 702.19b in each step: 1 is lethal to Savannah Lions, 2 tramples
    over in the first-strike step; the Lions are gone by the regular step, so
    all 3 go to Bob there."""
    scenario, _, bears = _axe_board(["Savannah Lions"])
    lions = scenario.creature("Savannah Lions", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.block(bears, lions)

    scenario.combat_damage()

    assert lions.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 15
    assert bears.damage == 0, "the Lions died before they could strike back"


# -- Basilisk Collar ----------------------------------------------------------


def _collar_board(bob=()):
    scenario = _board(["Basilisk Collar", "Mountain", "Mountain", "Llanowar Elves"], bob)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    collar = scenario.find("Basilisk Collar", Zone.BATTLEFIELD, "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    _equip(scenario, collar, elves, *scenario.untapped_sources("Mountain", "Mountain"))
    return scenario, collar, elves


def test_basilisk_collar_grants_deathtouch_and_lifelink():
    scenario, _, elves = _collar_board()
    assert {"Deathtouch", "Lifelink"} <= set(_chars(scenario, elves).abilities)


def test_basilisk_collar_one_damage_kills_a_big_blocker_and_gains_life():
    """CR 702.2b and CR 702.15b in one hit: the 1/1 Elves trade with Hill
    Giant, and Alice gains the 1 damage they dealt."""
    scenario, _, elves = _collar_board(["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(elves)
    scenario.block(elves, giant)

    scenario.combat_damage()
    scenario.state_based_actions()

    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 21


def test_basilisk_collar_lifelink_on_unblocked_damage():
    scenario, _, elves = _collar_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(elves)
    scenario.no_blocks()

    scenario.combat_damage()

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21


def test_basilisk_collar_stays_when_the_creature_dies():
    """CR 704.5n: it becomes unattached and stays on the battlefield."""
    scenario, collar, elves = _collar_board()
    scenario.game.destroy(elves)
    scenario.state_based_actions()

    assert collar.zone is Zone.BATTLEFIELD
    assert equipped_creature(scenario.game, collar) is None


# -- Dwalin, Weaponmaster: hone counters --------------------------------------


def _hone(permanent):
    return permanent.counters["hone"]


def test_dwalin_entering_puts_a_hone_counter_on_each_equipment_you_control():
    scenario = _board(
        ["Lavaspur Boots", "Basilisk Collar"],
        ["Bonesplitter"],
        hand=["Dwalin, Weaponmaster"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Dwalin, Weaponmaster", "alice")
    _resolve_everything(scenario)

    boots = scenario.find("Lavaspur Boots", Zone.BATTLEFIELD, "alice")
    collar = scenario.find("Basilisk Collar", Zone.BATTLEFIELD, "alice")
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob")
    assert (_hone(boots), _hone(collar)) == (1, 1)
    assert _hone(splitter) == 0, "only Equipment you control"


def test_dwalin_with_no_equipment_does_nothing():
    scenario = _board(["Grizzly Bears"], hand=["Dwalin, Weaponmaster"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    dwalin = scenario.put_onto_battlefield("Dwalin, Weaponmaster", "alice")
    _resolve_everything(scenario)

    assert dwalin.zone is Zone.BATTLEFIELD
    assert not any(_hone(p) for p in scenario.game.battlefield)


def test_a_hone_counter_gives_the_equipped_creature_plus_one_zero():
    """CR 122.1j: Basilisk Collar (no P/T of its own) with one hone counter
    makes the equipped Bears 3/2."""
    scenario = _board(
        ["Basilisk Collar", "Mountain", "Mountain", "Grizzly Bears"],
        hand=["Dwalin, Weaponmaster"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    collar = scenario.find("Basilisk Collar", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.put_onto_battlefield("Dwalin, Weaponmaster", "alice")
    _resolve_everything(scenario)
    assert (_chars(scenario, bears).power, _chars(scenario, bears).toughness) == (2, 2)

    _equip(scenario, collar, bears, *scenario.untapped_sources("Mountain", "Mountain"))

    assert (_chars(scenario, bears).power, _chars(scenario, bears).toughness) == (3, 2)


def test_dwalin_attacking_adds_another_hone_counter():
    scenario = _board(
        ["Lavaspur Boots", "Mountain", "Grizzly Bears"],
        hand=["Dwalin, Weaponmaster"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    boots = scenario.find("Lavaspur Boots", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    dwalin = scenario.put_onto_battlefield("Dwalin, Weaponmaster", "alice")
    _resolve_everything(scenario)
    _equip(scenario, boots, dwalin, *scenario.untapped_sources("Mountain"))
    assert _hone(boots) == 1

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dwalin)
    _resolve_everything(scenario)

    assert _hone(boots) == 2
    # 2 printed + 1 Boots + 2 hone counters (CR 122.1j)
    assert _chars(scenario, dwalin).power == 5
    assert _chars(scenario, bears).power == 2


def test_dwalin_has_first_strike_and_kills_a_blocker_first():
    """CR 702.7b: Dwalin's 2 first-strike damage kills a 2/2 blocker before
    it can deal its regular damage back."""
    scenario = _board(["Dwalin, Weaponmaster"], ["Grizzly Bears"])
    dwalin = scenario.creature("Dwalin, Weaponmaster", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dwalin)
    _resolve_everything(scenario)
    scenario.block(dwalin, bears)

    scenario.combat_damage()

    assert bears.zone is Zone.GRAVEYARD
    assert dwalin.zone is Zone.BATTLEFIELD
    assert dwalin.damage == 0


@pytest.mark.parametrize("count", [1, 2])
def test_hone_counters_on_an_unattached_equipment_pump_nothing(count):
    scenario = _board(["Lavaspur Boots", "Grizzly Bears"])
    boots = scenario.find("Lavaspur Boots", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(boots, "hone", count, putter="alice")

    assert _chars(scenario, bears).power == 2


# -- Giott, King of the Dwarves: two trigger events, one optional loot -------


GIOTT = "Giott, King of the Dwarves"


def _giott_board(*, alice=(), bob=(), hand=()):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(hand),
            library=["Plains", "Island", "Swamp", "Forest"],
        )
        .player("bob", battlefield=list(bob), hand=["Dwarven Mauler"], library=["Island"] * 5)
        .build()
    )


def _loot(scenario, discard_name):
    """Take the "you may discard" and name the card discarded."""
    scenario.will_take_the_may(True, username="alice")
    scenario.will_discard(scenario.find(discard_name, Zone.HAND, "alice"), username="alice")


def test_giott_entering_lets_you_discard_then_draw():
    scenario = _giott_board(hand=[GIOTT, "Mountain"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _loot(scenario, "Mountain")

    scenario.put_onto_battlefield(GIOTT, "alice")
    _resolve_everything(scenario)

    alice = scenario.player("alice")
    assert [c.name for c in alice.graveyard] == ["Mountain"]
    assert [c.name for c in alice.hand] == ["Plains"]


def test_giott_declining_the_loot_changes_nothing():
    scenario = _giott_board(hand=[GIOTT, "Mountain"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice")

    scenario.put_onto_battlefield(GIOTT, "alice")
    _resolve_everything(scenario)

    alice = scenario.player("alice")
    assert alice.graveyard == []
    assert [c.name for c in alice.hand] == ["Mountain"]


def test_giott_with_an_empty_hand_draws_nothing():
    """ "If you do" - there is no card to discard, so the discard is an
    illegal option nobody may choose (CR 608.2d) and there is no draw."""
    scenario = _giott_board(hand=[GIOTT])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield(GIOTT, "alice")
    _resolve_everything(scenario)

    assert scenario.player("alice").hand == []
    assert len(scenario.player("alice").library) == 4


def test_another_dwarf_you_control_entering_triggers_giott():
    scenario = _giott_board(alice=[GIOTT], hand=["Dwarven Mauler", "Mountain"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _loot(scenario, "Mountain")

    scenario.put_onto_battlefield("Dwarven Mauler", "alice")
    _resolve_everything(scenario)

    assert [c.name for c in scenario.player("alice").graveyard] == ["Mountain"]
    assert [c.name for c in scenario.player("alice").hand] == ["Plains"]


def test_an_opponents_dwarf_entering_does_not_trigger_giott():
    scenario = _giott_board(alice=[GIOTT], hand=["Mountain"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Dwarven Mauler", "bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []


def test_an_equipment_you_control_entering_triggers_giott():
    """The second, separate trigger event: Bonesplitter is no Dwarf."""
    scenario = _giott_board(alice=[GIOTT], hand=["Bonesplitter", "Mountain"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _loot(scenario, "Mountain")

    scenario.put_onto_battlefield("Bonesplitter", "alice")
    _resolve_everything(scenario)

    assert [c.name for c in scenario.player("alice").graveyard] == ["Mountain"]
    assert [c.name for c in scenario.player("alice").hand] == ["Plains"]


def test_a_nondwarf_nonequipment_entering_does_not_trigger_giott():
    scenario = _giott_board(alice=[GIOTT], hand=["Grizzly Bears", "Mountain"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []


def test_giott_has_double_strike():
    """CR 702.4b: the 1/1 deals 1 in each combat damage step."""
    scenario = _giott_board(alice=[GIOTT])
    giott = scenario.creature(GIOTT, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giott)
    scenario.no_blocks()

    scenario.combat_damage()

    assert scenario.player("bob").life == 18
