"""Wither: damage to creatures dealt as -1/-1 counters (CR 702.80).

Read in this session with `mise run rules:find`:

- **CR 702.80a** - "Damage dealt to a creature by a source with wither isn't
  marked on that creature. Rather, it causes that source's controller to put
  that many -1/-1 counters on that creature."
- **CR 120.3d** - the same result from the damage rules' side ("wither and/or
  infect"); **CR 120.3a** - damage to a player by a source without infect is
  ordinary life loss, wither or not; **CR 120.3c** - a planeswalker still
  loses loyalty.
- **CR 702.80b/c** - last known information, and any zone; shared with
  infect's CR 702.90d/e and proven in `test_infect.py`.
- **CR 701.14a** - a fight is noncombat damage by each creature.
- **CR 615.1a** - prevented damage is not dealt, so no counters.

Boggart Ram-Gang (Haste, Wither; not in the deck pool) is the source.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

RAM_GANG = "Boggart Ram-Gang"


def duel(*alice: str, bob: tuple[str, ...] = (), alice_hand: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=list(alice), hand=list(alice_hand))
        .player("bob", battlefield=list(bob))
    )


def test_wither_damage_to_a_player_is_ordinary_life_loss():
    """CR 120.3a: wither says nothing about players - three life, no poison."""
    scenario = duel(RAM_GANG).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ram_gang = scenario.creature(RAM_GANG)
    scenario.attack_with(ram_gang)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 17
    assert scenario.player("bob").poison == 0


def test_a_blocker_gets_minus_one_counters_instead_of_marked_damage():
    """CR 702.80a: Serra Angel (4/4) takes three -1/-1 counters and no marked
    damage, and survives as a 1/1; the Ram-Gang takes four marked and dies."""
    scenario = duel(RAM_GANG, bob=("Serra Angel",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ram_gang = scenario.creature(RAM_GANG)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.attack_with(ram_gang)
    scenario.block(ram_gang, angel)
    scenario.combat_damage()

    assert angel.counter_count(Counter.MINUS_ONE) == 3
    assert angel.damage == 0
    assert angel.zone is Zone.BATTLEFIELD
    chars = scenario.game.characteristics_of(angel)
    assert (chars.power, chars.toughness) == (1, 1)
    assert ram_gang.zone is Zone.GRAVEYARD


def test_the_counters_outlive_the_turn():
    """Marked damage goes away in the cleanup step (CR 514.2); -1/-1 counters
    do not - the Angel is still a 1/1 on bob's own turn."""
    scenario = duel(RAM_GANG, bob=("Serra Angel",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ram_gang = scenario.creature(RAM_GANG)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.attack_with(ram_gang)
    scenario.block(ram_gang, angel)
    scenario.combat_damage()

    scenario.start_at(Step.END_OF_COMBAT)
    while scenario.turn.active_player == "alice":
        scenario.advance()

    assert angel.counter_count(Counter.MINUS_ONE) == 3
    assert scenario.game.characteristics_of(angel).toughness == 1


def test_a_fight_is_noncombat_wither_damage():
    """CR 701.14a: Prey Upon has the Ram-Gang fight the Bears - three -1/-1
    counters kill the 2/2 (CR 704.5f, toughness 0 or less)."""
    scenario = duel(RAM_GANG, "Forest", alice_hand=("Prey Upon",), bob=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ram_gang = scenario.creature(RAM_GANG)
    bears = scenario.creature("Grizzly Bears", "bob")
    forest = scenario.untapped_sources("Forest")[0]

    scenario.cast_and_resolve("Prey Upon", forest, targets=[ram_gang, bears])

    assert bears.zone is Zone.GRAVEYARD
    assert bears.last_known_counters[Counter.MINUS_ONE] == 3
    assert ram_gang.damage == 2


def test_wither_damage_to_a_planeswalker_still_removes_loyalty():
    """CR 120.3c: Jace Beleren loses three loyalty counters and dies at zero
    (CR 704.5i); nothing about wither reaches a noncreature."""
    scenario = duel(RAM_GANG, bob=("Jace Beleren",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ram_gang = scenario.creature(RAM_GANG)
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    scenario.attack_with(ram_gang, defending=jace)
    scenario.no_blocks()
    scenario.combat_damage()

    assert jace.zone is Zone.GRAVEYARD
    assert jace.last_known_counters[Counter.MINUS_ONE] == 0


def test_prevented_wither_damage_puts_no_counters():
    """CR 615.1a: Fog Bank prevents all combat damage dealt to it, so no
    damage is dealt and no -1/-1 counter is put."""
    scenario = duel(RAM_GANG, bob=("Fog Bank",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ram_gang = scenario.creature(RAM_GANG)
    bank = scenario.creature("Fog Bank", "bob")
    scenario.attack_with(ram_gang)
    scenario.block(ram_gang, bank)
    scenario.combat_damage()

    assert bank.counter_count(Counter.MINUS_ONE) == 0
    assert bank.damage == 0
