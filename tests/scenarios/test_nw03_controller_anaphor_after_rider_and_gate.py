"""'That creature's controller' after a non-damage clause or behind a gate.

Blur of Blades ({1}{R}): "Put a -1/-1 counter on target creature. Blur of
Blades deals 2 damage to that creature's controller." Searing Barrage
({4}{R}): "Searing Barrage deals 5 damage to target creature. Adamant - If at
least three red mana was spent to cast this spell, Searing Barrage deals 3
damage to that creature's controller." Outmuscle ({3}{G}): "Put a +1/+1
counter on target creature you control, then it fights target creature you
don't control. Adamant - If at least three green mana was spent to cast this
spell, the creature you control gains indestructible until end of turn."

- CR 608.2c: instructions are followed in order; "that creature" is the
  spell's target (the second sentence names no new target of its own).
- CR 608.2b: with its only target illegal the spell does nothing, so the
  controller is not damaged.
- CR 608.2h: a creature that left (or dies to the first instruction) is
  still looked at as it last existed, so its last controller is damaged.
- CR 601.2h / CR 207.2c: adamant is an ability word; the gate is the mana
  actually spent on the cast, read when the instruction is followed.

Proof printings on the same readers: Sonic Assault (a tap clause, then the
controller line) and Draconic Roar (a gate whose condition is "you revealed
a Dragon card or controlled a Dragon", then the controller line).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _life(scenario) -> tuple[int, int]:
    return scenario.player("alice").life, scenario.player("bob").life


def _board(hand, lands, bob_battlefield, alice_extra=(), bob_hand=(), bob_extra=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=list(hand), battlefield=list(lands) + list(alice_extra))
        .player("bob", hand=list(bob_hand), battlefield=list(bob_battlefield) + list(bob_extra))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Blur of Blades ------------------------------------------------------------


def test_blur_of_blades_counter_then_two_damage_to_the_controller():
    scenario = _board(["Blur of Blades"], ["Mountain"] * 2, ["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    scenario.cast_and_resolve(
        "Blur of Blades", *scenario.untapped_sources("Mountain", "Mountain"), targets=[angel]
    )
    assert angel.counters["-1/-1"] == 1
    assert _life(scenario) == (20, 18)


def test_blur_of_blades_pays_the_controller_even_when_the_counter_kills_the_creature():
    """CR 608.2h: the creature dies as a state-based action afterwards, but the
    damage already went to the player who controlled it."""
    scenario = _board(["Blur of Blades"], ["Mountain"] * 2, ["Llanowar Elves"])
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.cast_and_resolve(
        "Blur of Blades", *scenario.untapped_sources("Mountain", "Mountain"), targets=[elves]
    )
    assert elves.zone is Zone.GRAVEYARD
    assert _life(scenario) == (20, 18)


def test_blur_of_blades_does_nothing_when_its_target_has_left():
    """CR 608.2b: no legal target, so neither the counter nor the damage."""
    scenario = _board(
        ["Blur of Blades"],
        ["Mountain"] * 2,
        ["Grizzly Bears"],
        bob_hand=["Unsummon"],
        bob_extra=["Island"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    spell = scenario.cast_onto_stack(
        "Blur of Blades", *scenario.untapped_sources("Mountain", "Mountain"), targets=[bears]
    )
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Unsummon",
        *scenario.untapped_sources("Island", username="bob"),
        username="bob",
        targets=[bears],
    )
    assert bears.zone is Zone.HAND
    scenario.resolve_top()
    assert spell.zone is Zone.GRAVEYARD
    assert _life(scenario) == (20, 20)


def test_blur_of_blades_hits_the_controller_of_a_creature_alice_does_not_control():
    """Damage goes to the targeted creature's controller, never the caster."""
    scenario = _board(["Blur of Blades"], ["Mountain"] * 2, [], alice_extra=["Grizzly Bears"])
    own = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Blur of Blades", *scenario.untapped_sources("Mountain", "Mountain"), targets=[own]
    )
    assert _life(scenario) == (18, 20)


# -- Searing Barrage -----------------------------------------------------------


def _barrage(lands):
    scenario = _board(["Searing Barrage"], lands, ["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    scenario.cast_and_resolve(
        "Searing Barrage", *scenario.untapped_sources(*lands), targets=[angel]
    )
    return scenario, angel


def test_searing_barrage_adamant_red_adds_three_damage_to_the_controller():
    scenario, angel = _barrage(["Mountain"] * 5)
    assert angel.zone is Zone.GRAVEYARD
    assert _life(scenario) == (20, 17)


def test_searing_barrage_exactly_three_red_counts_as_adamant():
    scenario, _ = _barrage(["Mountain"] * 3 + ["Forest"] * 2)
    assert _life(scenario) == (20, 17)


def test_searing_barrage_two_red_is_not_adamant():
    scenario, angel = _barrage(["Mountain"] * 2 + ["Forest"] * 3)
    assert angel.zone is Zone.GRAVEYARD
    assert _life(scenario) == (20, 20)


def test_searing_barrage_pays_the_controller_of_a_creature_it_killed():
    """CR 608.2h again, through the gate."""
    scenario = _board(["Searing Barrage"], ["Mountain"] * 5, ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve(
        "Searing Barrage", *scenario.untapped_sources(*["Mountain"] * 5), targets=[bears]
    )
    assert bears.zone is Zone.GRAVEYARD
    assert _life(scenario) == (20, 17)


# -- Outmuscle -----------------------------------------------------------------


def _outmuscle(lands):
    scenario = _board(["Outmuscle"], lands, ["Grizzly Bears"], alice_extra=["Hill Giant"])
    mine = scenario.creature("Hill Giant", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve(
        "Outmuscle", *scenario.untapped_sources(*lands), targets=[mine, theirs]
    )
    return scenario, mine, theirs


def test_outmuscle_adamant_green_gives_the_fighter_indestructible():
    scenario, mine, theirs = _outmuscle(["Forest"] * 4)
    assert mine.counters["+1/+1"] == 1
    assert theirs.zone is Zone.GRAVEYARD
    assert is_indestructible(mine, scenario.game)


def test_outmuscle_without_three_green_there_is_no_indestructible():
    scenario, mine, _ = _outmuscle(["Forest"] * 2 + ["Mountain"] * 2)
    assert mine.counters["+1/+1"] == 1
    assert not is_indestructible(mine, scenario.game)


# -- Proof printings -----------------------------------------------------------


def test_sonic_assault_taps_then_damages_the_controller():
    scenario = _board(["Sonic Assault"], ["Island", "Mountain", "Island"], ["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    scenario.cast_and_resolve(
        "Sonic Assault",
        *scenario.untapped_sources("Island", "Island", "Mountain"),
        targets=[angel],
    )
    assert angel.tapped
    assert _life(scenario) == (20, 18)


def test_draconic_roar_revealing_a_dragon_also_damages_the_controller():
    scenario = _board(["Draconic Roar", "Shivan Dragon"], ["Mountain"] * 2, ["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    dragon = scenario.find("Shivan Dragon", Zone.HAND, "alice")
    casting = scenario.cast("Draconic Roar")
    casting.reveal_for_cost(dragon)
    casting.choose_targets([angel])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert angel.damage == 3
    assert _life(scenario) == (20, 17)


def test_draconic_roar_without_a_dragon_only_hits_the_creature():
    scenario = _board(["Draconic Roar"], ["Mountain"] * 2, ["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    scenario.cast_and_resolve(
        "Draconic Roar", *scenario.untapped_sources("Mountain", "Mountain"), targets=[angel]
    )
    assert angel.damage == 3
    assert _life(scenario) == (20, 20)


def test_draconic_roar_controlling_a_dragon_counts_too():
    scenario = _board(
        ["Draconic Roar"], ["Mountain"] * 2, ["Serra Angel"], alice_extra=["Shivan Dragon"]
    )
    angel = scenario.creature("Serra Angel", "bob")
    scenario.cast_and_resolve(
        "Draconic Roar", *scenario.untapped_sources("Mountain", "Mountain"), targets=[angel]
    )
    assert _life(scenario) == (20, 17)


# -- Savage Punch: the same "the creature you control" rider, run before the fight


def _punch(alice_extra):
    scenario = _board(
        ["Savage Punch"],
        ["Forest", "Forest"],
        ["Hill Giant"],
        alice_extra=["Grizzly Bears", *alice_extra],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve(
        "Savage Punch", *scenario.untapped_sources("Forest", "Forest"), targets=[bears, giant]
    )
    return bears, giant


def test_savage_punch_ferocious_pumps_before_the_fight():
    """CR 608.2c: the +2/+2 happens first, so the 4/4 Bears survives the Giant."""
    bears, giant = _punch(["Serra Angel"])
    assert bears.zone is Zone.BATTLEFIELD
    assert giant.zone is Zone.GRAVEYARD


def test_savage_punch_without_a_power_four_creature_is_a_plain_fight():
    bears, giant = _punch([])
    assert bears.zone is Zone.GRAVEYARD
    assert giant.damage == 2
