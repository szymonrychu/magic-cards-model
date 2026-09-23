"""Infect: damage dealt as poison counters and -1/-1 counters (CR 702.90).

Every rule here was read in this session with `mise run rules:find`:

- **CR 120.3** - "Damage may have one or more of the following results,
  depending on whether the recipient of the damage is a player or permanent,
  the characteristics of the damage's source, and the characteristics of the
  damage's recipient". The results are the damage's own, not replacements.
- **CR 120.3b** - "Damage dealt to a player by a source with infect causes
  that source's controller to give the player that many poison counters."
- **CR 120.3c** - damage to a planeswalker removes loyalty, infect or not.
- **CR 120.3d** - "Damage dealt to a creature by a source with wither and/or
  infect causes that source's controller to put that many -1/-1 counters on
  that creature."
- **CR 120.3f** - lifelink still gains life, "in addition to the damage's
  other results".
- **CR 702.90b/c** - the player and creature halves, from the keyword's side:
  the player "doesn't ... lose life", the creature has nothing marked.
- **CR 702.90d** - "If an object is no longer in the zone it's expected to be
  in as an effect causes it to deal damage, its last known information is used
  to determine whether it had infect."
- **CR 702.90e** - "The infect rules function no matter what zone an object
  with infect deals damage from."
- **CR 702.2b** - deathtouch destroys a creature "that's been dealt damage by a
  source with deathtouch", and infect damage is still damage dealt.
- **CR 702.19b** - trample's excess goes to the player, as poison here.
- **CR 704.5c / CR 122.1f** - ten poison counters lose the game as a
  state-based action.
- **CR 701.14a** - a fight is each creature dealing damage equal to its power:
  noncombat damage, still infect damage.

Glistener Elf is the plain infect creature (not in the deck pool), Blightsteel
Colossus the reported card, Tainted Strike the granted infect, and Mogg
Fanatic's sacrifice ability the last-known-information case.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.delayed import DelayedTrigger, SacrificeSubject
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

ELF = "Glistener Elf"


def duel(
    *alice: str,
    bob: tuple[str, ...] = (),
    alice_hand: tuple[str, ...] = (),
    bob_hand: tuple[str, ...] = (),
) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=list(alice), hand=list(alice_hand), library=["Forest"] * 5)
        .player("bob", battlefield=list(bob), hand=list(bob_hand), library=["Forest"] * 5)
    )


def watch_life_loss(scenario) -> None:
    """A delayed trigger on CR 119.3's life-loss event, staged the way
    `test_trigger_events.py` does, so a missing event is observable."""
    scenario.game.create_delayed_trigger(
        DelayedTrigger(
            text="Whenever a player loses life, note it.",
            effect=SacrificeSubject(),
            event=TriggerEvent.LOSES_LIFE,
            controller="bob",
            source_name="a resolving spell",
        )
    )


def attack_unblocked(scenario, *attackers) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    scenario.no_blocks()
    scenario.combat_damage()


def test_unblocked_infect_gives_poison_counters_instead_of_life_loss():
    """CR 120.3b / 702.90b: one poison counter, and bob's life is untouched."""
    scenario = duel(ELF).build()
    elf = scenario.creature(ELF)

    attack_unblocked(scenario, elf)

    bob = scenario.player("bob")
    assert bob.poison == 1
    assert bob.life == 20
    assert bob.life_lost_this_turn == 0


def test_infect_damage_to_a_player_is_not_a_life_loss_event():
    """CR 702.90b: the player "doesn't lose life", so CR 119.3's life-loss
    event never happens and nothing watching for it triggers."""
    scenario = duel(ELF).build()
    elf = scenario.creature(ELF)
    watch_life_loss(scenario)

    attack_unblocked(scenario, elf)

    assert scenario.player("bob").poison == 1
    assert "a resolving spell's triggered ability" not in scenario.stack_names()
    assert not scenario.pending_triggers


def test_a_blocker_gets_minus_one_counters_instead_of_marked_damage():
    """CR 120.3d / 702.90c: the Bears get one -1/-1 counter and no damage;
    the Elf takes ordinary marked damage from the Bears and dies."""
    scenario = duel(ELF, bob=("Grizzly Bears",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    elf = scenario.creature(ELF)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(elf)
    scenario.block(elf, bears)
    scenario.combat_damage()

    assert bears.counter_count(Counter.MINUS_ONE) == 1
    assert bears.damage == 0
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.characteristics_of(bears).toughness == 1
    assert elf.zone is Zone.GRAVEYARD


def test_ten_poison_counters_across_two_attacks_lose_the_game():
    """CR 704.5c / 122.1f: five infect attackers on each of alice's two turns
    add up to ten poison counters, and the state-based action ends it."""
    scenario = duel(*[ELF] * 5).build()
    elves = [s for s in scenario.game.battlefield if s.name == ELF]

    attack_unblocked(scenario, *elves)
    assert scenario.player("bob").poison == 5
    assert "bob" not in scenario.game.losers

    scenario.start_at(Step.END_OF_COMBAT)
    while scenario.turn.turn_number == 1 or scenario.turn.active_player != "alice":
        scenario.advance()
    attack_unblocked(scenario, *elves)

    assert scenario.player("bob").poison == 10
    assert scenario.player("bob").life == 20
    assert "bob" in scenario.game.losers


def test_blightsteel_colossus_tramples_over_as_poison():
    """CR 702.19b: two to the blocking Bears (lethal by toughness), nine
    through to bob - as -1/-1 counters and poison counters respectively."""
    scenario = duel("Blightsteel Colossus", bob=("Grizzly Bears",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    colossus = scenario.creature("Blightsteel Colossus")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(colossus)
    scenario.block(colossus, bears)
    scenario.will_assign_combat_damage((bears, 2), ("bob", 9))
    scenario.combat_damage()

    assert scenario.player("bob").poison == 9
    assert scenario.player("bob").life == 20
    assert bears.zone is Zone.GRAVEYARD
    assert bears.last_known_counters[Counter.MINUS_ONE] == 2


def test_infect_damage_to_a_planeswalker_still_removes_loyalty():
    """CR 120.3c is unchanged by infect: Jace Beleren loses one loyalty
    counter and gets no -1/-1 counter, since it is not a creature."""
    scenario = duel(ELF, bob=("Jace Beleren",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    elf = scenario.creature(ELF)
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    loyalty = jace.counter_count(Counter.LOYALTY)
    scenario.attack_with(elf, defending=jace)
    scenario.no_blocks()
    scenario.combat_damage()

    assert jace.counter_count(Counter.LOYALTY) == loyalty - 1
    assert jace.counter_count(Counter.MINUS_ONE) == 0
    assert scenario.player("bob").poison == 0


def test_a_fight_is_noncombat_infect_damage():
    """CR 701.14a with CR 702.90c: Prey Upon has the Elf fight the Bears -
    one -1/-1 counter on the Bears, two marked damage on the Elf."""
    scenario = duel(ELF, "Forest", alice_hand=("Prey Upon",), bob=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elf = scenario.creature(ELF)
    bears = scenario.creature("Grizzly Bears", "bob")
    forest = scenario.untapped_sources("Forest")[0]

    scenario.cast_and_resolve("Prey Upon", forest, targets=[elf, bears])

    assert bears.counter_count(Counter.MINUS_ONE) == 1
    assert bears.damage == 0
    assert elf.zone is Zone.GRAVEYARD


def test_prevention_reduces_the_poison_counters_given():
    """CR 615.1a: Bandage prevents one of Blightsteel's eleven, so bob gets
    ten poison counters rather than eleven."""
    scenario = duel("Blightsteel Colossus", bob=("Plains",), bob_hand=("Bandage",)).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    colossus = scenario.creature("Blightsteel Colossus")
    plains = scenario.untapped_sources("Plains", username="bob")[0]
    scenario.attack_with(colossus)
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Bandage", plains, username="bob", targets=["bob"])
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").poison == 10


def test_a_creature_that_lost_infect_deals_ordinary_damage():
    """CR 613.5: Dress Down's "Creatures lose all abilities" takes infect
    away in layer 6, so the Elf's damage is CR 120.3a's life loss."""
    scenario = duel(ELF, "Dress Down").build()
    elf = scenario.creature(ELF)

    attack_unblocked(scenario, elf)

    assert scenario.player("bob").poison == 0
    assert scenario.player("bob").life == 19


def test_granted_infect_deals_poison():
    """Tainted Strike: "Target creature gets +1/+0 and gains infect until end
    of turn." The Bears deal three poison counters, not three life."""
    scenario = duel("Grizzly Bears", "Swamp", alice_hand=("Tainted Strike",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    swamp = scenario.untapped_sources("Swamp")[0]
    scenario.cast_and_resolve("Tainted Strike", swamp, targets=[bears])

    attack_unblocked(scenario, bears)

    assert scenario.player("bob").poison == 3
    assert scenario.player("bob").life == 20


def test_last_known_information_decides_infect_for_a_sacrificed_source():
    """CR 702.90d: Mogg Fanatic, given infect by Tainted Strike, sacrifices
    itself to pay for "It deals 1 damage to any target". By resolution it is
    in the graveyard with no infect printed; as it last existed it had
    infect, so bob gets a poison counter."""
    scenario = duel("Mogg Fanatic", "Swamp", alice_hand=("Tainted Strike",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fanatic = scenario.creature("Mogg Fanatic")
    swamp = scenario.untapped_sources("Swamp")[0]
    scenario.cast_and_resolve("Tainted Strike", swamp, targets=[fanatic])

    scenario.activate(fanatic, sacrificing=[fanatic], targets=["bob"])
    scenario.pass_until_resolved()

    assert fanatic.zone is Zone.GRAVEYARD
    assert scenario.player("bob").poison == 1
    assert scenario.player("bob").life == 20


def test_a_sacrificed_source_without_infect_deals_ordinary_damage():
    """The control for the case above: no grant, no infect as it last
    existed, so the same ability costs bob one life."""
    scenario = duel("Mogg Fanatic").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fanatic = scenario.creature("Mogg Fanatic")

    scenario.activate(fanatic, sacrificing=[fanatic], targets=["bob"])
    scenario.pass_until_resolved()

    assert scenario.player("bob").poison == 0
    assert scenario.player("bob").life == 19


def test_infect_and_deathtouch_together_destroy_the_blocker():
    """CR 702.2b: infect damage is still damage dealt. Tainted Strike on
    Bilious Skulldweller (1/1 deathtouch) makes it a 2/1 with infect; Serra
    Angel takes two -1/-1 counters (a 2/2) and deathtouch destroys it."""
    scenario = duel(
        "Bilious Skulldweller", "Swamp", alice_hand=("Tainted Strike",), bob=("Serra Angel",)
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skulldweller = scenario.creature("Bilious Skulldweller")
    angel = scenario.creature("Serra Angel", "bob")
    swamp = scenario.untapped_sources("Swamp")[0]
    scenario.cast_and_resolve("Tainted Strike", swamp, targets=[skulldweller])

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(skulldweller)
    scenario.block(skulldweller, angel)
    scenario.combat_damage()

    assert angel.zone is Zone.GRAVEYARD
    assert angel.last_known_counters[Counter.MINUS_ONE] == 2


def test_infect_and_lifelink_together_still_gain_life():
    """CR 120.3f: Wurmcoil Engine given infect deals seven poison counters
    and its controller still gains seven life."""
    scenario = duel("Wurmcoil Engine", "Swamp", alice_hand=("Tainted Strike",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Wurmcoil Engine")
    swamp = scenario.untapped_sources("Swamp")[0]
    scenario.cast_and_resolve("Tainted Strike", swamp, targets=[wurm])

    attack_unblocked(scenario, wurm)

    assert scenario.player("bob").poison == 7
    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 27
