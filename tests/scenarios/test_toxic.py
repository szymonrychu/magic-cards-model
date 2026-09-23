"""Toxic: combat damage to a player also gives poison counters (CR 702.164).

Read in this session with `mise run rules:find`:

- **CR 702.164a** - "Toxic is a static ability. It is written 'toxic N,'
  where N is a number."
- **CR 702.164b** - "A creature's total toxic value is the sum of all N
  values of toxic abilities that creature has."
- **CR 702.164c** / **CR 120.3g** - "Combat damage dealt to a player by a
  creature with toxic causes that creature's controller to give the player a
  number of poison counters equal to that creature's total toxic value, in
  addition to the damage's other results."

So three limits, and the corner cases are one per limit: only *combat*
damage, only to a *player*, and only damage actually *dealt* - plus the sum
across instances, and toxic's independence from infect (both results
happen).

Bilious Skulldweller (deathtouch, toxic 1), Venerated Rotpriest and Myr
Convert are the printings; Prosthetic Injector ("Equipped creature gets +0/+2
and has toxic 1.") grants a second instance.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario, mana_from

SKULLDWELLER = "Bilious Skulldweller"
ROTPRIEST = "Venerated Rotpriest"
CONVERT = "Myr Convert"
INJECTOR = "Prosthetic Injector"


def duel(
    *alice: str,
    bob: tuple[str, ...] = (),
    alice_hand: tuple[str, ...] = (),
    bob_hand: tuple[str, ...] = (),
) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=list(alice), hand=list(alice_hand), library=["Forest"] * 3)
        .player("bob", battlefield=list(bob), hand=list(bob_hand), library=["Forest"] * 3)
    )


def attack_unblocked(scenario, *attackers) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    scenario.no_blocks()
    scenario.combat_damage()


def equip(scenario, equipment, creature) -> None:
    activation = equip_activation(scenario.game, equipment, creature, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()


def test_unblocked_toxic_gives_poison_in_addition_to_life_loss():
    """CR 702.164c: one life lost *and* one poison counter."""
    scenario = duel(SKULLDWELLER).build()
    attack_unblocked(scenario, scenario.creature(SKULLDWELLER))

    assert scenario.player("bob").life == 19
    assert scenario.player("bob").poison == 1


def test_a_blocked_toxic_creature_gives_no_poison():
    """Only damage to a player: the blocked Skulldweller's deathtouch kills
    the Bears, and bob gets nothing."""
    scenario = duel(SKULLDWELLER, bob=("Grizzly Bears",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    skulldweller = scenario.creature(SKULLDWELLER)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(skulldweller)
    scenario.block(skulldweller, bears)
    scenario.combat_damage()

    assert scenario.player("bob").poison == 0
    assert scenario.player("bob").life == 20
    assert bears.zone is Zone.GRAVEYARD
    assert bears.last_known_counters[Counter.MINUS_ONE] == 0


def test_myr_convert_deals_two_and_one_poison():
    """The reported card: a 2/1 with toxic 1 - the poison is the toxic
    value, not the damage."""
    scenario = duel(CONVERT).build()
    attack_unblocked(scenario, scenario.creature(CONVERT))

    assert scenario.player("bob").life == 18
    assert scenario.player("bob").poison == 1


def test_venerated_rotpriest_attacks_for_one_and_one_poison():
    scenario = duel(ROTPRIEST).build()
    attack_unblocked(scenario, scenario.creature(ROTPRIEST))

    assert scenario.player("bob").life == 19
    assert scenario.player("bob").poison == 1


def test_total_toxic_value_sums_every_instance():
    """CR 702.164b: Myr Convert's printed toxic 1 plus Prosthetic Injector's
    granted toxic 1 is a total toxic value of 2."""
    scenario = duel(CONVERT, INJECTOR, "Mountain").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    convert = scenario.creature(CONVERT)
    injector = scenario.find(INJECTOR, Zone.BATTLEFIELD, "alice")
    equip(scenario, injector, convert)

    assert scenario.game.characteristics_of(convert).toughness == 3
    attack_unblocked(scenario, convert)

    assert scenario.player("bob").life == 18
    assert scenario.player("bob").poison == 2


def test_noncombat_damage_by_a_creature_with_toxic_gives_no_poison():
    """Only combat damage: Mogg Fanatic equipped with Prosthetic Injector has
    toxic 1, but its sacrifice ability's 1 damage to bob is not combat
    damage - one life, no poison."""
    scenario = duel("Mogg Fanatic", INJECTOR, "Mountain").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fanatic = scenario.creature("Mogg Fanatic")
    injector = scenario.find(INJECTOR, Zone.BATTLEFIELD, "alice")
    equip(scenario, injector, fanatic)
    assert scenario.game.characteristics_of(fanatic).toughness == 3

    scenario.activate(fanatic, sacrificing=[fanatic], targets=["bob"])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 19
    assert scenario.player("bob").poison == 0


def test_prevented_combat_damage_gives_no_toxic_poison():
    """Only damage dealt: Bandage prevents the Skulldweller's one damage to
    bob, so nothing was dealt and no poison counter follows."""
    scenario = duel(SKULLDWELLER, bob=("Plains",), bob_hand=("Bandage",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    plains = scenario.untapped_sources("Plains", username="bob")[0]
    scenario.attack_with(scenario.creature(SKULLDWELLER))
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Bandage", plains, username="bob", targets=["bob"])
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 20
    assert scenario.player("bob").poison == 0


def test_toxic_and_infect_both_happen():
    """CR 120.3g's "in addition to the damage's other results": Tainted
    Strike makes the Skulldweller a 2/1 with infect - two poison counters
    from infect (CR 120.3b) plus one from toxic, and no life lost."""
    scenario = duel(SKULLDWELLER, "Swamp", alice_hand=("Tainted Strike",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skulldweller = scenario.creature(SKULLDWELLER)
    swamp = scenario.untapped_sources("Swamp")[0]
    scenario.cast_and_resolve("Tainted Strike", swamp, targets=[skulldweller])

    attack_unblocked(scenario, skulldweller)

    assert scenario.player("bob").poison == 3
    assert scenario.player("bob").life == 20


def test_rotpriest_trigger_gives_target_opponent_a_poison_counter():
    """Venerated Rotpriest: "Whenever a creature you control becomes the
    target of a spell, target opponent gets a poison counter." Giant Growth
    on alice's own Rotpriest is the spell."""
    scenario = duel(ROTPRIEST, "Forest", alice_hand=("Giant Growth",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rotpriest = scenario.creature(ROTPRIEST)
    forest = scenario.untapped_sources("Forest")[0]
    scenario.choose_trigger_targets(ROTPRIEST, ["bob"])

    scenario.cast_and_resolve("Giant Growth", forest, targets=[rotpriest])
    scenario.pass_until_resolved()

    assert scenario.player("bob").poison == 1
    assert scenario.player("alice").poison == 0


def test_rotpriest_triggers_on_an_opponents_spell_too():
    """ "a spell", whoever controls it: bob's Shock at the Rotpriest triggers
    it, and the poison counter still goes to alice's opponent, bob."""
    scenario = duel(ROTPRIEST, bob=("Mountain",), bob_hand=("Shock",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rotpriest = scenario.creature(ROTPRIEST)
    mountain = scenario.untapped_sources("Mountain", username="bob")[0]
    scenario.choose_trigger_targets(ROTPRIEST, ["bob"])
    scenario.pass_priority("alice")

    scenario.cast_and_resolve("Shock", mountain, username="bob", targets=[rotpriest])
    scenario.pass_until_resolved()

    assert scenario.player("bob").poison == 1
    assert rotpriest.zone is Zone.GRAVEYARD


def test_rotpriest_ignores_a_spell_targeting_another_players_creature():
    """ "a creature you control": Giant Growth on bob's Bears is not one."""
    scenario = duel(
        ROTPRIEST, "Forest", alice_hand=("Giant Growth",), bob=("Grizzly Bears",)
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    forest = scenario.untapped_sources("Forest")[0]

    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])
    scenario.pass_until_resolved()

    assert scenario.player("bob").poison == 0
