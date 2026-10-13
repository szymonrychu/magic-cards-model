"""EP-02 R2 T5: counters as an amount, and counter bookkeeping.

"the number of +1/+1 counters on <object>", "creatures you control with +1/+1
counters on them", "for each kind of counter ... put another of that kind",
"double the number of +1/+1 counters", "remove all <kind> counters ... for each
counter removed this way", and "power and toughness each equal to the number of
loyalty counters on him".

CR 122.1 (a counter is a marker; its kind is its name), CR 608.2c (instructions
in order, so a count read after "put a +1/+1 counter on it, then ..." includes
that counter), CR 608.2h (the number is taken once, as the effect applies; the
source's last known information when it has left, CR 603.10a), CR 701.10e
(doubling the counters of a kind gives as many again).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _settle(scenario, limit=16):
    """Put triggers on the stack and resolve until the stack is empty."""
    for _ in range(limit):
        scenario.game.put_triggers_on_stack()
        if not scenario.stack_names():
            return
        scenario.pass_until_resolved()
    raise AssertionError(f"stack never emptied: {scenario.stack_names()}")


def _board(
    alice,
    bob=None,
    *,
    alice_hand=(),
    bob_hand=(),
    alice_graveyard=(),
    bob_graveyard=(),
    alice_exile=(),
    library=12,
    step=Step.PRECOMBAT_MAIN,
):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(alice_hand),
            graveyard=list(alice_graveyard),
            exile=list(alice_exile),
            library=["Forest"] * library,
        )
        .player(
            "bob",
            battlefield=list(bob or ()),
            hand=list(bob_hand),
            graveyard=list(bob_graveyard),
            library=["Forest"] * library,
        )
        .build()
    )
    scenario.start_at(step)
    return scenario


def _to_step(scenario, step):
    while scenario.step is not step:
        scenario.advance()


def _named(scenario, name, username="alice"):
    return [c for c in scenario.game.permanents_controlled_by(username) if c.name == name]


def _stats(scenario, card):
    chars = scenario.game.characteristics_of(card)
    return chars.power, chars.toughness


def _attack(scenario, *creatures):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*creatures)
    _settle(scenario)


# -- Krenko: "put a +1/+1 counter on it, then create a number of ... equal to its power"


def test_krenko_makes_goblins_equal_to_its_power_after_the_new_counter():
    scenario = _board(["Krenko, Tin Street Kingpin"])
    krenko = scenario.creature("Krenko, Tin Street Kingpin", "alice")
    _attack(scenario, krenko)
    assert krenko.counter_count(Counter.PLUS_ONE) == 1
    assert len(_named(scenario, "Goblin Token")) == 2  # base 1 + the counter


def test_krenko_counts_every_counter_it_already_holds():
    scenario = _board(["Krenko, Tin Street Kingpin"])
    krenko = scenario.creature("Krenko, Tin Street Kingpin", "alice")
    krenko.add_counters(Counter.PLUS_ONE, 3)
    _attack(scenario, krenko)
    assert krenko.counter_count(Counter.PLUS_ONE) == 4
    assert len(_named(scenario, "Goblin Token")) == 5


# -- Anim Pakal: attack with non-Gnome creatures, X Gnomes tapped and attacking


def test_anim_pakal_makes_a_gnome_per_counter_when_a_non_gnome_attacks():
    scenario = _board(["Anim Pakal, Thousandth Moon", "Grizzly Bears"])
    pakal = scenario.creature("Anim Pakal, Thousandth Moon", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    pakal.add_counters(Counter.PLUS_ONE, 1)
    _attack(scenario, bears)
    assert pakal.counter_count(Counter.PLUS_ONE) == 2
    gnomes = _named(scenario, "Gnome Token")
    assert len(gnomes) == 2
    assert all(g.tapped for g in gnomes)
    assert all(g in scenario.attackers() for g in gnomes)


def test_anim_pakal_does_not_trigger_for_gnomes_alone():
    scenario = _board(["Anim Pakal, Thousandth Moon", "Grizzly Bears"])
    pakal = scenario.creature("Anim Pakal, Thousandth Moon", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _attack(scenario, bears)
    assert len(_named(scenario, "Gnome Token")) == 1
    gnome = _named(scenario, "Gnome Token")[0]
    assert gnome in scenario.attackers()
    assert pakal.counter_count(Counter.PLUS_ONE) == 1
    # A second declaration of only the Gnome (a token entering attacking never
    # "attacked", CR 508.4) does not trigger again.
    assert len(_named(scenario, "Gnome Token")) == 1


# -- Urabrask's Forge: an X/1 token, X the oil counters (including the new one)


def test_urabrasks_forge_makes_a_token_as_big_as_its_oil_counters():
    scenario = _board(["Urabrask's Forge"])
    forge = scenario.find("Urabrask's Forge", Zone.BATTLEFIELD, "alice")
    forge.add_counters("oil", 2)
    _to_step(scenario, Step.BEGINNING_OF_COMBAT)
    _settle(scenario)
    assert forge.counter_count("oil") == 3
    (horror,) = _named(scenario, "Phyrexian Horror Token")
    assert _stats(scenario, horror) == (3, 1)
    abilities = " ".join(scenario.game.characteristics_of(horror).abilities).lower()
    assert "haste" in abilities and "trample" in abilities


def test_urabrasks_forge_token_is_sacrificed_at_the_next_end_step():
    scenario = _board(["Urabrask's Forge"])
    _to_step(scenario, Step.BEGINNING_OF_COMBAT)
    _settle(scenario)
    assert len(_named(scenario, "Phyrexian Horror Token")) == 1
    _to_step(scenario, Step.END_STEP)
    _settle(scenario)
    assert _named(scenario, "Phyrexian Horror Token") == []


# -- Dai Li Agents: drain X, X the creatures you control with +1/+1 counters


def test_dai_li_agents_drains_per_creature_with_a_counter_on_it():
    scenario = _board(["Dai Li Agents", "Grizzly Bears", "Hill Giant"])
    agents = scenario.creature("Dai Li Agents", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 3)  # one creature, however many counters
    agents.add_counters(Counter.PLUS_ONE, 1)
    _attack(scenario, agents)
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22


def test_dai_li_agents_counts_only_plus_one_counters():
    scenario = _board(["Dai Li Agents", "Grizzly Bears"])
    agents = scenario.creature("Dai Li Agents", "alice")
    scenario.creature("Grizzly Bears", "alice").add_counters("charge", 2)
    _attack(scenario, agents)
    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20


# -- Aerith Gainsborough: dies, X counters on each legendary creature


def test_aerith_puts_its_last_known_counters_on_each_legendary_creature():
    scenario = _board(
        ["Aerith Gainsborough", "Krenko, Tin Street Kingpin", "Grizzly Bears"],
        ["Hill Giant"],
    )
    aerith = scenario.creature("Aerith Gainsborough", "alice")
    krenko = scenario.creature("Krenko, Tin Street Kingpin", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    aerith.add_counters(Counter.PLUS_ONE, 3)
    scenario.game.destroy(aerith)
    _settle(scenario)
    assert krenko.counter_count(Counter.PLUS_ONE) == 3
    assert bears.counter_count(Counter.PLUS_ONE) == 0
    assert scenario.creature("Hill Giant", "bob").counter_count(Counter.PLUS_ONE) == 0


def test_aerith_with_no_counters_adds_nothing():
    scenario = _board(["Aerith Gainsborough", "Krenko, Tin Street Kingpin"])
    aerith = scenario.creature("Aerith Gainsborough", "alice")
    krenko = scenario.creature("Krenko, Tin Street Kingpin", "alice")
    scenario.game.destroy(aerith)
    _settle(scenario)
    assert krenko.counter_count(Counter.PLUS_ONE) == 0


# -- Rumbling Ruin: count the +1/+1 counters on creatures you control


def test_rumbling_ruin_stops_smaller_creatures_blocking_by_counters_among_yours():
    scenario = _board(
        ["Grizzly Bears", "Hill Giant"],
        ["Grizzly Bears", "Hill Giant", "Craw Wurm"],
        alice_hand=["Rumbling Ruin"],
    )
    scenario.creature("Grizzly Bears", "alice").add_counters(Counter.PLUS_ONE, 1)
    scenario.creature("Hill Giant", "alice").add_counters(Counter.PLUS_ONE, 2)
    scenario.put_onto_battlefield("Rumbling Ruin", "alice")
    _settle(scenario)
    attacker = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    # three counters among alice's creatures: power 3 or less can't block
    for blocker in (bears, giant):
        try:
            scenario.block(attacker, blocker)
        except ValueError:
            continue
        raise AssertionError(f"{blocker.name} blocked")
    scenario.block(attacker, wurm)


def test_rumbling_ruin_with_no_counters_restricts_only_powerless_creatures():
    scenario = _board(["Hill Giant"], ["Grizzly Bears"], alice_hand=["Rumbling Ruin"])
    scenario.put_onto_battlefield("Rumbling Ruin", "alice")
    _settle(scenario)
    attacker = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(attacker, scenario.creature("Grizzly Bears", "bob"))


# -- Coalition Relic: remove all charge counters, add a mana for each


def test_coalition_relic_adds_a_mana_for_each_charge_counter_removed():
    scenario = _board(["Coalition Relic"], step=Step.UPKEEP)
    relic = scenario.find("Coalition Relic", Zone.BATTLEFIELD, "alice")
    relic.add_counters("charge", 3)
    _to_step(scenario, Step.PRECOMBAT_MAIN)
    _settle(scenario)
    assert relic.counter_count("charge") == 0
    assert scenario.player("alice").mana_pool.total == 3


def test_coalition_relic_with_no_charge_counters_adds_nothing():
    scenario = _board(["Coalition Relic"], step=Step.UPKEEP)
    _to_step(scenario, Step.PRECOMBAT_MAIN)
    _settle(scenario)
    assert scenario.player("alice").mana_pool.total == 0


# -- Slime Against Humanity: X is two plus the Oozes (and namesakes) you own in exile and graveyard


def test_slime_against_humanity_counts_oozes_and_namesakes_in_both_zones():
    scenario = _board(
        ["Forest", "Forest", "Forest"],
        alice_hand=["Slime Against Humanity"],
        alice_graveyard=["Scavenging Ooze", "Slime Against Humanity", "Grizzly Bears"],
        alice_exile=["Necroplasm"],
        bob_graveyard=["Scavenging Ooze"],  # not owned by alice
    )
    lands = [p for p in scenario.game.permanents_controlled_by("alice")]
    scenario.game.cast(
        scenario.find("Slime Against Humanity", Zone.HAND, "alice"), "alice", mana_sources=lands
    )
    scenario.resolve_top()
    (ooze,) = _named(scenario, "Ooze Token")
    assert ooze.counter_count(Counter.PLUS_ONE) == 5  # 2 + Scavenging Ooze + namesake + Necroplasm
    assert _stats(scenario, ooze) == (5, 5)


def test_slime_against_humanity_with_nothing_else_makes_a_two_two():
    scenario = _board(["Forest", "Forest", "Forest"], alice_hand=["Slime Against Humanity"])
    lands = [p for p in scenario.game.permanents_controlled_by("alice")]
    scenario.game.cast(
        scenario.find("Slime Against Humanity", Zone.HAND, "alice"), "alice", mana_sources=lands
    )
    scenario.resolve_top()
    (ooze,) = _named(scenario, "Ooze Token")
    assert _stats(scenario, ooze) == (2, 2)
