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
from magic_cards_model.models.card import Type
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


def test_anim_pakal_does_not_trigger_when_only_a_gnome_attacks():
    scenario = _board(["Anim Pakal, Thousandth Moon", "Clockwork Servant"])
    pakal = scenario.creature("Anim Pakal, Thousandth Moon", "alice")
    servant = scenario.creature("Clockwork Servant", "alice")
    assert "Gnome" in scenario.game.characteristics_of(servant).subtypes
    _attack(scenario, servant)
    assert pakal.counter_count(Counter.PLUS_ONE) == 0
    assert not _named(scenario, "Gnome Token")


def test_anim_pakal_triggers_once_for_a_mixed_attack_and_its_tokens_do_not_retrigger():
    scenario = _board(["Anim Pakal, Thousandth Moon", "Clockwork Servant", "Grizzly Bears"])
    pakal = scenario.creature("Anim Pakal, Thousandth Moon", "alice")
    servant = scenario.creature("Clockwork Servant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _attack(scenario, servant, bears)
    assert pakal.counter_count(Counter.PLUS_ONE) == 1
    (gnome,) = _named(scenario, "Gnome Token")
    assert gnome.tapped and gnome in scenario.attackers()  # CR 508.4


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
    scenario = _board(
        ["Hill Giant"], ["Grizzly Bears", "Market Gnome"], alice_hand=["Rumbling Ruin"]
    )
    scenario.put_onto_battlefield("Rumbling Ruin", "alice")
    _settle(scenario)
    attacker = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacker)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    # zero counters: power 0 or less can't block; Market Gnome is 0/3, Grizzly Bears 2/2
    try:
        scenario.block(attacker, scenario.creature("Market Gnome", "bob"))
    except ValueError:
        pass
    else:
        raise AssertionError("a power 0 creature blocked")
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


# -- Descendant of Masumaro: counters up per card in your hand, down per card in theirs


def test_descendant_of_masumaro_nets_hand_sizes_into_counters():
    scenario = _board(
        ["Descendant of Masumaro"],
        alice_hand=["Forest", "Forest", "Forest"],
        bob_hand=["Island"],
        step=Step.UNTAP,
    )
    descendant = scenario.creature("Descendant of Masumaro", "alice")
    _to_step(scenario, Step.UPKEEP)
    scenario.choose_trigger_targets("Descendant of Masumaro", ["bob"])
    _settle(scenario)
    assert descendant.counter_count(Counter.PLUS_ONE) == 2  # +3 for yours, -1 for theirs


def test_descendant_of_masumaro_removes_only_counters_it_has():
    scenario = _board(
        ["Descendant of Masumaro"],
        alice_hand=["Forest"],
        bob_hand=["Island"] * 4,
        step=Step.UNTAP,
    )
    descendant = scenario.creature("Descendant of Masumaro", "alice")
    _to_step(scenario, Step.UPKEEP)
    scenario.choose_trigger_targets("Descendant of Masumaro", ["bob"])
    _settle(scenario)
    assert descendant.counter_count(Counter.PLUS_ONE) == 0  # +1 then at most 1 removed


def test_descendant_of_masumaro_hand_count_amount_is_applied_once():
    """Two readers on one clause would double the count: exactly one hand count lands."""
    scenario = _board(
        ["Descendant of Masumaro"],
        alice_hand=["Forest", "Forest"],
        bob_hand=[],
        step=Step.UNTAP,
    )
    descendant = scenario.creature("Descendant of Masumaro", "alice")
    _to_step(scenario, Step.UPKEEP)
    scenario.choose_trigger_targets("Descendant of Masumaro", ["bob"])
    _settle(scenario)
    assert descendant.counter_count(Counter.PLUS_ONE) == 2


# -- Sphere of Annihilation: exile everything with mana value up to its void counters


def test_sphere_of_annihilation_exiles_by_mana_value_in_play_and_graveyards():
    scenario = _board(
        ["Sphere of Annihilation", "Grizzly Bears", "Hill Giant", "Forest"],
        ["Craw Wurm", "Jace Beleren"],
        alice_graveyard=["Grizzly Bears", "Lightning Bolt"],
        bob_graveyard=["Grizzly Bears", "Hill Giant"],
        step=Step.UNTAP,
    )
    sphere = scenario.find("Sphere of Annihilation", Zone.BATTLEFIELD, "alice")
    sphere.add_counters("void", 3)
    _to_step(scenario, Step.UPKEEP)
    _settle(scenario)
    names = scenario.battlefield_names()
    assert "Sphere of Annihilation" not in names
    assert "Grizzly Bears" not in names  # mana value 2
    assert "Jace Beleren" not in names  # mana value 3
    assert "Hill Giant" in names  # mana value 4
    assert "Craw Wurm" in names  # mana value 6
    assert "Forest" in names  # not a creature or planeswalker
    exiled = {c.name for c in scenario.game.exile}
    assert {"Sphere of Annihilation", "Grizzly Bears", "Jace Beleren"} <= exiled
    assert [c.name for c in scenario.player("bob").graveyard] == ["Hill Giant"]
    assert [c.name for c in scenario.player("alice").graveyard] == ["Lightning Bolt"]


# -- Cheering Crowd: each player's first main phase, that player may grow it for mana


def test_cheering_crowd_pays_the_active_player_mana_per_counter():
    scenario = _board(["Cheering Crowd"], step=Step.UPKEEP)
    crowd = scenario.creature("Cheering Crowd", "alice")
    crowd.add_counters(Counter.PLUS_ONE, 2)
    scenario.will_take_the_may(True)
    _to_step(scenario, Step.PRECOMBAT_MAIN)
    _settle(scenario)
    assert crowd.counter_count(Counter.PLUS_ONE) == 3
    assert scenario.player("alice").mana_pool.total == 3


def test_cheering_crowd_declined_adds_nothing():
    scenario = _board(["Cheering Crowd"], step=Step.UPKEEP)
    crowd = scenario.creature("Cheering Crowd", "alice")
    scenario.will_take_the_may(False)
    _to_step(scenario, Step.PRECOMBAT_MAIN)
    _settle(scenario)
    assert crowd.counter_count(Counter.PLUS_ONE) == 0
    assert scenario.player("alice").mana_pool.total == 0


# -- Quarry Hauler / Dramatist's Puppet: for each kind of counter, one more or one fewer


def _enter_with_kind_choice(name, answers):
    scenario = _board(["Grizzly Bears"], bob=["Grizzly Bears"], alice_hand=[name])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)
    bears.add_counters("charge", 2)
    for answer in answers:
        scenario.will_choose(answer, source=name)
    scenario.put_onto_battlefield(name, "alice")
    scenario.choose_trigger_targets(name, [bears])
    _settle(scenario)
    return bears


def test_quarry_hauler_adds_one_of_a_kind_and_removes_one_of_another():
    bears = _enter_with_kind_choice("Quarry Hauler", ["put", "remove"])
    assert bears.counter_count(Counter.PLUS_ONE) == 2
    assert bears.counter_count("charge") == 1


def test_dramatists_puppet_reads_the_same_text():
    bears = _enter_with_kind_choice("Dramatist's Puppet", ["remove", "remove"])
    assert bears.counter_count(Counter.PLUS_ONE) == 0
    assert bears.counter_count("charge") == 1


def test_quarry_hauler_on_a_permanent_with_no_counters_does_nothing():
    scenario = _board(["Grizzly Bears"], alice_hand=["Quarry Hauler"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.put_onto_battlefield("Quarry Hauler", "alice")
    scenario.choose_trigger_targets("Quarry Hauler", [bears])
    _settle(scenario)
    assert not bears.counters.counts


# -- Exotic Pets: a counter of each kind among your creatures on either token


def test_exotic_pets_puts_one_counter_per_kind_among_your_creatures_on_the_tokens():
    scenario = _board(["Grizzly Bears", "Plains", "Island", "Plains"], alice_hand=["Exotic Pets"])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 3)
    bears.add_counters("charge", 1)
    scenario.cast_and_resolve(
        "Exotic Pets",
        *[p for p in scenario.game.permanents_controlled_by("alice") if p.name != "Grizzly Bears"],
    )
    fish = _named(scenario, "Fish Token")
    assert len(fish) == 2
    assert sum(f.counter_count(Counter.PLUS_ONE) for f in fish) == 1
    assert sum(f.counter_count("charge") for f in fish) == 1


def test_exotic_pets_without_counters_makes_plain_fish():
    scenario = _board(["Plains", "Island", "Plains"], alice_hand=["Exotic Pets"])
    scenario.cast_and_resolve("Exotic Pets", *scenario.game.permanents_controlled_by("alice"))
    fish = _named(scenario, "Fish Token")
    assert len(fish) == 2
    assert all(not f.counters.counts for f in fish)


# -- Tanazir Quandrix: double the +1/+1 counters; base P/T of the others becomes its own


def test_tanazir_doubles_plus_one_counters_on_its_target():
    scenario = _board(["Grizzly Bears"], alice_hand=["Tanazir Quandrix"])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 3)
    bears.add_counters("charge", 2)
    scenario.put_onto_battlefield("Tanazir Quandrix", "alice")
    scenario.choose_trigger_targets("Tanazir Quandrix", [bears])
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 6
    assert bears.counter_count("charge") == 2


def test_tanazir_attack_sets_the_other_creatures_base_stats_to_its_own():
    scenario = _board(["Tanazir Quandrix", "Grizzly Bears"])
    tanazir = scenario.creature("Tanazir Quandrix", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    tanazir.add_counters(Counter.PLUS_ONE, 2)
    bears.add_counters(Counter.PLUS_ONE, 1)
    scenario.will_take_the_may(True)
    _attack(scenario, tanazir)
    assert _stats(scenario, tanazir) == (6, 6)
    assert _stats(scenario, bears) == (7, 7)  # base 6/6, then its own counter


def test_tanazir_attack_declined_leaves_the_others_alone():
    scenario = _board(["Tanazir Quandrix", "Grizzly Bears"])
    tanazir = scenario.creature("Tanazir Quandrix", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_take_the_may(False)
    _attack(scenario, tanazir)
    assert _stats(scenario, bears) == (2, 2)


# -- Sita Varma: X counters on herself, then the others take her power as base P/T


def test_sita_varma_puts_x_counters_then_sets_the_others_to_her_power():
    scenario = _board(
        ["Sita Varma, Masked Racer", "Grizzly Bears"] + ["Forest"] * 4 + ["Island"],
    )
    sita = scenario.creature("Sita Varma, Masked Racer", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    lands = [
        p for p in scenario.game.permanents_controlled_by("alice") if p.name in ("Forest", "Island")
    ]
    scenario.will_take_the_may(True)
    scenario.activate(sita, *lands, x_value=2)
    scenario.pass_until_resolved()
    assert sita.counter_count(Counter.PLUS_ONE) == 2
    assert _stats(scenario, sita) == (4, 5)  # base 2/3
    assert _stats(scenario, bears) == (4, 4)


# -- Sarulf: remove all +1/+1 counters, then exile each other nonland permanent
#    with mana value at most the number removed


def test_sarulf_exiles_other_nonland_permanents_up_to_the_removed_counter_count():
    scenario = _board(
        ["Sarulf, Realm Eater", "Grizzly Bears", "Forest"],
        bob=["Savannah Lions", "Serra Angel", "Island"],
        step=Step.UNTAP,
    )
    sarulf = scenario.creature("Sarulf, Realm Eater", "alice")
    sarulf.add_counters(Counter.PLUS_ONE, 3)
    scenario.will_take_the_may(True)
    _to_step(scenario, Step.UPKEEP)
    _settle(scenario)
    assert sarulf.counter_count(Counter.PLUS_ONE) == 0
    assert sarulf.zone is Zone.BATTLEFIELD  # "each other"
    assert not _named(scenario, "Grizzly Bears")
    assert not _named(scenario, "Savannah Lions", "bob")
    assert _named(scenario, "Serra Angel", "bob")
    assert _named(scenario, "Forest") and _named(scenario, "Island", "bob")  # lands stay


def test_sarulf_declined_keeps_the_counters_and_the_board():
    scenario = _board(["Sarulf, Realm Eater", "Grizzly Bears"], step=Step.UNTAP)
    sarulf = scenario.creature("Sarulf, Realm Eater", "alice")
    sarulf.add_counters(Counter.PLUS_ONE, 3)
    scenario.will_take_the_may(False)
    _to_step(scenario, Step.UPKEEP)
    _settle(scenario)
    assert sarulf.counter_count(Counter.PLUS_ONE) == 3
    assert _named(scenario, "Grizzly Bears")


# -- Galloping Lizrog: remove any number of +1/+1 counters from among your creatures,
#    put twice that many on it


def _lizrog_board():
    scenario = _board(["Grizzly Bears", "Savannah Lions"], alice_hand=["Galloping Lizrog"])
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "alice")
    bears.add_counters(Counter.PLUS_ONE, 3)
    lions.add_counters(Counter.PLUS_ONE, 1)
    return scenario, bears, lions


def test_galloping_lizrog_trades_counters_for_twice_as_many():
    scenario, bears, lions = _lizrog_board()
    scenario.will_choose_an_amount(3)
    lizrog = scenario.put_onto_battlefield("Galloping Lizrog", "alice")
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) + lions.counter_count(Counter.PLUS_ONE) == 1
    assert lizrog.counter_count(Counter.PLUS_ONE) == 6


def test_galloping_lizrog_choosing_zero_removes_nothing_and_adds_nothing():
    scenario, bears, lions = _lizrog_board()
    scenario.will_choose_an_amount(0)
    lizrog = scenario.put_onto_battlefield("Galloping Lizrog", "alice")
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 3
    assert lions.counter_count(Counter.PLUS_ONE) == 1
    assert lizrog.counter_count(Counter.PLUS_ONE) == 0


def test_galloping_lizrog_removes_from_the_creatures_the_player_picks():
    scenario, bears, lions = _lizrog_board()
    scenario.will_choose_an_amount(2)
    scenario.will_choose_cards(lions, username="alice")
    scenario.will_choose_cards(bears, username="alice")
    lizrog = scenario.put_onto_battlefield("Galloping Lizrog", "alice")
    _settle(scenario)
    assert lions.counter_count(Counter.PLUS_ONE) == 0
    assert bears.counter_count(Counter.PLUS_ONE) == 2
    assert lizrog.counter_count(Counter.PLUS_ONE) == 4


# -- Thornmantle Striker: X is the number of Elves you control


def _striker_board():
    return _board(
        ["Llanowar Elves", "Elvish Mystic"],
        bob=["Grizzly Bears"],
        alice_hand=["Thornmantle Striker"],
    )


def test_thornmantle_striker_removes_x_counters_from_the_target_permanent():
    scenario = _striker_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.add_counters("charge", 5)
    scenario.will_choose_mode(
        "Remove X counters from target permanent, where X is the number of Elves you control.",
        source="Thornmantle Striker",
    )
    scenario.will_choose_targets(bears, source="Thornmantle Striker")
    scenario.put_onto_battlefield("Thornmantle Striker", "alice")
    _settle(scenario)
    assert bears.counter_count("charge") == 2  # Llanowar, Mystic and the Striker (an Elf)


def test_thornmantle_striker_gives_minus_x_minus_x():
    scenario = _striker_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_mode(
        "Target creature an opponent controls gets -X/-X until end of turn, where X is the "
        "number of Elves you control.",
        source="Thornmantle Striker",
    )
    scenario.will_choose_targets(bears, source="Thornmantle Striker")
    scenario.put_onto_battlefield("Thornmantle Striker", "alice")
    _settle(scenario)
    scenario.state_based_actions()
    assert bears.zone is Zone.GRAVEYARD  # -3/-3 on a 2/2


# -- Confront the Past: X is the cast X, twice X loyalty counters off a planeswalker


def _confront(scenario, mode, x_value, targets):
    lands = [p for p in scenario.game.permanents_controlled_by("alice") if p.name == "Swamp"]
    scenario.game.cast(
        scenario.find("Confront the Past", Zone.HAND, "alice"),
        "alice",
        modes=[mode],
        x_value=x_value,
        targets=targets,
        mana_sources=lands,
    )
    scenario.resolve_top()


def test_confront_the_past_removes_twice_x_loyalty_counters():
    scenario = _board(
        ["Swamp"] * 4, bob=["Jace, the Mind Sculptor"], alice_hand=["Confront the Past"]
    )
    jace = scenario.find("Jace, the Mind Sculptor", Zone.BATTLEFIELD, "bob")
    before = jace.counter_count("loyalty")
    _confront(scenario, 2, 1, [jace])
    assert jace.counter_count("loyalty") == before - 2


def test_confront_the_past_returns_a_planeswalker_card_with_mana_value_x_or_less():
    scenario = _board(
        ["Swamp"] * 5,
        alice_hand=["Confront the Past"],
        alice_graveyard=["Jace, the Mind Sculptor"],
    )
    jace = scenario.find("Jace, the Mind Sculptor", Zone.GRAVEYARD, "alice")
    _confront(scenario, 1, 4, [jace])
    assert _named(scenario, "Jace, the Mind Sculptor")


# -- Garruk Relentless: a state trigger on its own loyalty, and a one-sided fight back


def test_garruk_fights_back_and_transforms_when_loyalty_falls_to_two_or_fewer():
    scenario = _board(["Garruk Relentless"], bob=["Grizzly Bears"])
    garruk = scenario.find("Garruk Relentless", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    assert garruk.counter_count("loyalty") == 3
    scenario.activate(garruk, index=0, targets=[bears])
    _settle(scenario)
    assert bears.zone is Zone.GRAVEYARD  # 3 damage
    assert garruk.counter_count("loyalty") == 1  # the bear hit back for 2
    assert garruk.transformed
    assert scenario.game.characteristics_of(garruk).name == "Garruk, the Veil-Cursed"


def test_garruk_transforms_at_exactly_two_loyalty():
    scenario = _board(["Garruk Relentless"], bob=["Llanowar Elves"])
    garruk = scenario.find("Garruk Relentless", Zone.BATTLEFIELD, "alice")
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.activate(garruk, index=0, targets=[elves])
    _settle(scenario)
    assert garruk.counter_count("loyalty") == 2 and garruk.transformed  # 3 - 1


def test_garruk_does_not_transform_at_three_loyalty():
    scenario = _board(["Garruk Relentless"])
    garruk = scenario.find("Garruk Relentless", Zone.BATTLEFIELD, "alice")
    _settle(scenario)
    assert not garruk.transformed


# -- Gideon, Champion of Justice


def test_gideon_champion_of_justice_plus_one_counts_the_opponents_creatures():
    scenario = _board(["Gideon, Champion of Justice"], bob=["Grizzly Bears", "Llanowar Elves"])
    gideon = scenario.find("Gideon, Champion of Justice", Zone.BATTLEFIELD, "alice")
    scenario.activate(gideon, index=0, targets=["bob"])
    _settle(scenario)
    assert gideon.counter_count("loyalty") == 4 + 1 + 2  # cost, then two creatures


def test_gideon_champion_of_justice_zero_is_an_indestructible_creature_with_loyalty_stats():
    scenario = _board(["Gideon, Champion of Justice"], bob=["Grizzly Bears"])
    gideon = scenario.find("Gideon, Champion of Justice", Zone.BATTLEFIELD, "alice")
    scenario.activate(gideon, index=1)
    _settle(scenario)
    chars = scenario.game.characteristics_of(gideon)
    assert chars.is_creature
    assert Type.PLANESWALKER in chars.types
    assert {"Human", "Soldier"} <= set(chars.subtypes)
    assert (chars.power, chars.toughness) == (4, 4)
    assert any("ndestructible" in a for a in chars.abilities)
    scenario.game.deal_damage(gideon, 3, source=scenario.creature("Grizzly Bears", "bob"))
    assert gideon.counter_count("loyalty") == 4  # all damage to him is prevented


def test_gideon_champion_of_justice_stats_follow_loyalty_and_end_with_the_turn():
    scenario = _board(["Gideon, Champion of Justice"])
    gideon = scenario.find("Gideon, Champion of Justice", Zone.BATTLEFIELD, "alice")
    gideon.add_counters("loyalty", 2)
    scenario.activate(gideon, index=1)
    _settle(scenario)
    assert _stats(scenario, gideon) == (6, 6)
    _to_step(scenario, Step.CLEANUP)
    scenario.turn_based_actions()
    assert not scenario.game.characteristics_of(gideon).is_creature


# -- Spark Rupture: planeswalkers with loyalty counters lose abilities and are creatures


def test_spark_rupture_turns_planeswalkers_into_vanilla_creatures_sized_by_loyalty():
    scenario = _board(["Spark Rupture"], bob=["Jace, the Mind Sculptor"], alice_hand=[])
    jace = scenario.find("Jace, the Mind Sculptor", Zone.BATTLEFIELD, "bob")
    chars = scenario.game.characteristics_of(jace)
    assert chars.is_creature
    assert (chars.power, chars.toughness) == (3, 3)
    assert not chars.abilities
    jace.add_counters("loyalty", 2)
    assert _stats(scenario, jace) == (5, 5)


def test_spark_rupture_leaves_other_permanents_alone():
    scenario = _board(["Spark Rupture", "Forest"], bob=["Grizzly Bears"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert not scenario.game.characteristics_of(forest).is_creature
    assert _stats(scenario, scenario.creature("Grizzly Bears", "bob")) == (2, 2)


# -- Toxrill, the Corrosive: -1/-1 per slime counter


def test_toxrill_shrinks_each_opposing_creature_per_slime_counter():
    scenario = _board(["Toxrill, the Corrosive"], bob=["Craw Wurm", "Grizzly Bears"])
    wurm = scenario.creature("Craw Wurm", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    wurm.add_counters("slime", 2)
    bears.add_counters("slime", 1)
    assert _stats(scenario, wurm) == (4, 2)
    assert _stats(scenario, bears) == (1, 1)
    scenario.creature("Toxrill, the Corrosive", "alice").add_counters("slime", 3)
    assert _stats(scenario, scenario.creature("Toxrill, the Corrosive", "alice")) == (7, 7)


def test_toxrill_end_step_counters_kill_a_small_creature_and_leave_a_slug():
    scenario = _board(["Toxrill, the Corrosive"], bob=["Grizzly Bears"], step=Step.POSTCOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.add_counters("slime", 1)
    _to_step(scenario, Step.END_STEP)
    _settle(scenario)
    assert bears.zone is Zone.GRAVEYARD
    assert len(_named(scenario, "Slug Token")) == 1


# -- Thelon of Havenwood: spore counters grow every Fungus


def test_thelon_gives_each_fungus_plus_one_per_spore_counter_on_it():
    scenario = _board(["Thelon of Havenwood", "Mold Shambler"], bob=["Grizzly Bears"])
    shambler = scenario.creature("Mold Shambler", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    shambler.add_counters("spore", 2)
    bears.add_counters("spore", 2)
    assert _stats(scenario, shambler) == (5, 5)
    assert _stats(scenario, bears) == (2, 2)  # not a Fungus


def test_thelon_exiles_a_fungus_card_to_put_a_spore_counter_on_each_fungus():
    scenario = _board(
        ["Thelon of Havenwood", "Mold Shambler", "Swamp", "Forest"],
        bob=["Mold Shambler"],
        alice_graveyard=["Mold Shambler"],
    )
    yours = scenario.creature("Mold Shambler", "alice")
    theirs = scenario.creature("Mold Shambler", "bob")
    thelon = scenario.creature("Thelon of Havenwood", "alice")
    lands = [
        p for p in scenario.game.permanents_controlled_by("alice") if p.name in ("Swamp", "Forest")
    ]
    card = scenario.find("Mold Shambler", Zone.GRAVEYARD, "alice")
    scenario.activate(thelon, *lands, exiling=[card])
    _settle(scenario)
    assert yours.counter_count("spore") == 1 and theirs.counter_count("spore") == 1
    assert card.zone is Zone.EXILE
    assert _stats(scenario, yours) == (4, 4)


# -- Jenova, Ancient Calamity: its power in counters, and a new creature type


def test_jenova_puts_counters_equal_to_its_power_and_makes_the_target_a_mutant():
    scenario = _board(["Jenova, Ancient Calamity", "Grizzly Bears"], step=Step.UPKEEP)
    jenova = scenario.creature("Jenova, Ancient Calamity", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    jenova.add_counters(Counter.PLUS_ONE, 2)
    scenario.will_choose_targets(bears, source="Jenova, Ancient Calamity")
    _to_step(scenario, Step.BEGINNING_OF_COMBAT)
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 3  # Jenova is 1/5 + 2 counters
    assert "Mutant" in scenario.game.characteristics_of(bears).subtypes


def test_jenova_mutant_dying_on_your_turn_draws_its_power():
    scenario = _board(["Jenova, Ancient Calamity", "Grizzly Bears"], step=Step.UPKEEP)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets(bears, source="Jenova, Ancient Calamity")
    _to_step(scenario, Step.BEGINNING_OF_COMBAT)
    _settle(scenario)
    hand_before = len(scenario.player("alice").hand)
    scenario.game.destroy(bears)
    _settle(scenario)
    assert len(scenario.player("alice").hand) == hand_before + 3  # 2/2 + one counter


def test_jenova_with_no_target_does_nothing():
    scenario = _board(["Jenova, Ancient Calamity", "Grizzly Bears"], step=Step.UPKEEP)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets(username="alice", source="Jenova, Ancient Calamity")
    _to_step(scenario, Step.BEGINNING_OF_COMBAT)
    _settle(scenario)
    assert not bears.counters.counts


# -- Omega, Heartless Evolution: X stun counters and X life, X = your nonbasic lands


def test_omega_stuns_one_permanent_per_opponent_and_gains_life_for_nonbasic_lands():
    scenario = _board(
        ["Blood Crypt", "Breeding Pool", "Forest"],
        bob=["Grizzly Bears", "Forest"],
        alice_hand=["Omega, Heartless Evolution"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears, source="Omega, Heartless Evolution")
    scenario.put_onto_battlefield("Omega, Heartless Evolution", "alice")
    _settle(scenario)
    assert bears.tapped
    assert bears.counter_count("stun") == 2
    assert scenario.player("alice").life == 22


def test_omega_never_targets_a_land_and_can_choose_nothing():
    scenario = _board(["Blood Crypt"], bob=["Forest"], alice_hand=["Omega, Heartless Evolution"])
    scenario.put_onto_battlefield("Omega, Heartless Evolution", "alice")
    _settle(scenario)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    assert not forest.tapped and forest.counter_count("stun") == 0


# -- Descent into Madness: a despair counter, then each player exiles that many


def test_descent_into_madness_makes_each_player_exile_x_permanents_or_cards():
    scenario = _board(
        ["Descent into Madness", "Forest", "Island"],
        bob=["Grizzly Bears", "Forest"],
        bob_hand=["Island"],
        step=Step.UNTAP,
    )
    descent = scenario.find("Descent into Madness", Zone.BATTLEFIELD, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_cards(forest, username="alice")
    scenario.will_choose_cards(bears, username="bob")
    _to_step(scenario, Step.UPKEEP)
    _settle(scenario)
    assert descent.counter_count("despair") == 1
    assert forest.zone is Zone.EXILE
    assert bears.zone is Zone.EXILE


def test_descent_into_madness_second_upkeep_exiles_two_each():
    scenario = _board(
        ["Descent into Madness", "Forest", "Island"],
        bob=["Grizzly Bears"],
        step=Step.UNTAP,
    )
    descent = scenario.find("Descent into Madness", Zone.BATTLEFIELD, "alice")
    descent.add_counters("despair", 1)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(forest, island, username="alice")
    _to_step(scenario, Step.UPKEEP)
    _settle(scenario)
    assert descent.counter_count("despair") == 2
    assert len(scenario.game.permanents_controlled_by("alice")) <= 1  # two of three gone
    assert not scenario.game.permanents_controlled_by("bob")  # only one to exile


# -- Blessing of Frost: X is the snow mana spent; distribute X counters; draw per big creature


def _cast_blessing(scenario, lands):
    scenario.cast_and_resolve("Blessing of Frost", *lands)


def test_blessing_of_frost_distributes_counters_equal_to_snow_mana_spent_then_draws():
    scenario = _board(
        ["Grizzly Bears", "Llanowar Elves"] + ["Snow-Covered Forest"] * 4,
        alice_hand=["Blessing of Frost"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    lands = scenario.untapped_sources(*["Snow-Covered Forest"] * 4)
    for target in (bears, bears, bears, elves):
        scenario.will_choose_cards(target, username="alice")
    hand_before = len(scenario.player("alice").hand)
    _cast_blessing(scenario, lands)
    assert bears.counter_count(Counter.PLUS_ONE) == 3
    assert elves.counter_count(Counter.PLUS_ONE) == 1
    # Grizzly Bears is 5/5 now, Elves 2/2: one creature with power 4 or greater; the spell
    # left the hand and one card came in.
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1


def test_blessing_of_frost_counts_only_snow_mana():
    scenario = _board(
        ["Grizzly Bears", "Snow-Covered Forest", "Snow-Covered Forest", "Forest", "Forest"],
        alice_hand=["Blessing of Frost"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    lands = scenario.untapped_sources(
        "Snow-Covered Forest", "Snow-Covered Forest", "Forest", "Forest"
    )
    _cast_blessing(scenario, lands)
    assert bears.counter_count(Counter.PLUS_ONE) == 2  # only the one creature to take them


def test_blessing_of_frost_with_no_snow_mana_distributes_nothing():
    scenario = _board(["Grizzly Bears"] + ["Forest"] * 4, alice_hand=["Blessing of Frost"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_blessing(scenario, scenario.untapped_sources(*["Forest"] * 4))
    assert not bears.counters.counts


# -- Lightning Storm: X is 3 plus its charge counters; any player may add two from the stack


def _storm_board():
    scenario = _board(
        ["Mountain", "Mountain", "Mountain"],
        alice_hand=["Lightning Storm", "Forest"],
        bob_hand=["Forest", "Grizzly Bears"],
    )
    lands = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    storm = scenario.cast_onto_stack("Lightning Storm", *lands, targets=["bob"])
    return scenario, storm


def test_lightning_storm_deals_three_with_no_charge_counters():
    scenario, storm = _storm_board()
    scenario.resolve_top()
    assert scenario.player("bob").life == 17


def test_lightning_storm_discarding_a_land_adds_two_counters_and_a_new_target():
    scenario, storm = _storm_board()
    forest = scenario.find("Forest", Zone.HAND, "alice")
    scenario.activate(storm, discarding=[forest], username="alice")
    scenario.will_choose_targets("alice", username="alice")
    scenario.resolve_top()
    assert storm.counter_count("charge") == 2
    scenario.resolve_top()
    assert scenario.player("alice").life == 15  # 3 + 2, retargeted at herself
    assert scenario.player("bob").life == 20


def test_lightning_storm_keeps_its_target_when_the_activator_declines_a_new_one():
    scenario, storm = _storm_board()
    forest = scenario.find("Forest", Zone.HAND, "alice")
    scenario.activate(storm, discarding=[forest], username="alice")
    scenario.will_take_the_may(False)
    scenario.resolve_top()
    scenario.resolve_top()
    assert scenario.player("bob").life == 15


def test_lightning_storm_can_be_activated_by_an_opponent_while_it_is_on_the_stack():
    scenario, storm = _storm_board()
    bob_forest = scenario.find("Forest", Zone.HAND, "bob")
    scenario.pass_priority("alice")
    assert scenario.why_cannot_activate(storm, 0, "bob") is None
    scenario.activate(storm, discarding=[bob_forest], username="bob")
    scenario.resolve_top()
    assert storm.counter_count("charge") == 2
    assert bob_forest.zone is Zone.GRAVEYARD


def test_lightning_storm_cannot_be_activated_from_the_hand():
    scenario = _board([], alice_hand=["Lightning Storm", "Forest"])
    storm = scenario.find("Lightning Storm", Zone.HAND, "alice")
    assert scenario.why_cannot_activate(storm, 0, "alice") is not None


# -- Second proof printings: the same readers on other cards (legal in Modern/Pioneer,
#    in no listed deck, none of this task's cards)


def test_mossborn_hydra_doubles_its_own_counters_on_landfall():
    """Mossborn Hydra: "double the number of +1/+1 counters on this creature" - the
    self form of Tanazir's doubling reader (CR 701.10e)."""
    scenario = _board(["Mossborn Hydra"], alice_hand=["Forest", "Forest"])
    hydra = scenario.creature("Mossborn Hydra", "alice")
    hydra.add_counters(Counter.PLUS_ONE, 1)
    scenario.play_land("Forest", "alice")
    _settle(scenario)
    assert hydra.counter_count(Counter.PLUS_ONE) == 2
    scenario.game.put_onto_battlefield(scenario.find("Forest", Zone.HAND, "alice"), "alice")
    _settle(scenario)
    assert hydra.counter_count(Counter.PLUS_ONE) == 4


def test_hex_parasite_gets_plus_one_power_for_each_counter_removed_this_way():
    """Hex Parasite: "Remove up to X counters from target permanent. For each counter
    removed this way, this creature gets +1/+0" - the removed-this-way reader."""
    scenario = _board(["Hex Parasite", "Swamp", "Swamp", "Swamp"], bob=["Grizzly Bears"])
    parasite = scenario.creature("Hex Parasite", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.add_counters(Counter.PLUS_ONE, 1)
    before = _stats(scenario, parasite)
    lands = [p for p in scenario.game.permanents_controlled_by("alice") if p.name == "Swamp"]
    scenario.activate(parasite, *lands, x_value=2, targets=[bears])
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 0  # only one was there to remove
    assert _stats(scenario, parasite) == (before[0] + 1, before[1])


def test_skyship_plunderer_gives_another_counter_of_each_kind_on_the_target():
    """Skyship Plunderer reads "for each kind of counter on target permanent or
    player" - the kinds concept on a different card."""
    scenario = _board(["Skyship Plunderer", "Grizzly Bears"])
    plunderer = scenario.creature("Skyship Plunderer", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 2)
    bears.add_counters("charge", 1)
    scenario.will_choose_targets(bears, source="Skyship Plunderer")
    _attack(scenario, plunderer)
    scenario.no_blocks()
    scenario.combat_damage()
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 3
    assert bears.counter_count("charge") == 2


# -- Corner cases


def test_tanazir_doubling_a_creature_with_no_counters_changes_nothing():
    scenario = _board(["Grizzly Bears"], alice_hand=["Tanazir Quandrix"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.put_onto_battlefield("Tanazir Quandrix", "alice")
    scenario.choose_trigger_targets("Tanazir Quandrix", [bears])
    _settle(scenario)
    assert not bears.counters.counts


def test_sita_varma_with_x_zero_still_sets_the_others_to_her_power():
    scenario = _board(
        ["Sita Varma, Masked Racer", "Grizzly Bears"] + ["Forest"] * 2 + ["Island"] * 2
    )
    sita = scenario.creature("Sita Varma, Masked Racer", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    lands = [
        p for p in scenario.game.permanents_controlled_by("alice") if p.name in ("Forest", "Island")
    ]
    scenario.will_take_the_may(True)
    scenario.activate(sita, *lands, x_value=0)
    scenario.pass_until_resolved()
    assert not sita.counters.counts
    assert _stats(scenario, bears) == (2, 2)  # Sita is a 2/3: base power 2 for both


def test_sita_varma_declining_the_set_leaves_the_others_alone():
    scenario = _board(
        ["Sita Varma, Masked Racer", "Grizzly Bears", "Craw Wurm"] + ["Forest"] * 3 + ["Island"] * 2
    )
    sita = scenario.creature("Sita Varma, Masked Racer", "alice")
    wurm = scenario.creature("Craw Wurm", "alice")
    lands = [
        p for p in scenario.game.permanents_controlled_by("alice") if p.name in ("Forest", "Island")
    ]
    scenario.will_take_the_may(False)
    scenario.activate(sita, *lands, x_value=1)
    scenario.pass_until_resolved()
    assert sita.counter_count(Counter.PLUS_ONE) == 1
    assert _stats(scenario, wurm) == (6, 4)


def test_galloping_lizrog_removing_every_counter_among_your_creatures_doubles_them_all_onto_it():
    scenario, bears, lions = _lizrog_board()
    scenario.will_choose_an_amount(4)
    lizrog = scenario.put_onto_battlefield("Galloping Lizrog", "alice")
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 0 and lions.counter_count(Counter.PLUS_ONE) == 0
    assert lizrog.counter_count(Counter.PLUS_ONE) == 8


def test_omega_with_no_nonbasic_lands_taps_but_adds_no_counters_or_life():
    scenario = _board(["Forest"], bob=["Grizzly Bears"], alice_hand=["Omega, Heartless Evolution"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears, source="Omega, Heartless Evolution")
    scenario.put_onto_battlefield("Omega, Heartless Evolution", "alice")
    _settle(scenario)
    assert bears.tapped and bears.counter_count("stun") == 0
    assert scenario.player("alice").life == 20


def test_confront_the_past_with_x_zero_removes_nothing():
    scenario = _board(["Swamp"], bob=["Jace, the Mind Sculptor"], alice_hand=["Confront the Past"])
    jace = scenario.find("Jace, the Mind Sculptor", Zone.BATTLEFIELD, "bob")
    _confront(scenario, 2, 0, [jace])
    assert jace.counter_count("loyalty") == 3


def test_lightning_storm_two_activations_stack_four_counters():
    scenario = _board(
        ["Mountain", "Mountain", "Mountain"],
        alice_hand=["Lightning Storm", "Forest", "Forest"],
    )
    lands = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    storm = scenario.cast_onto_stack("Lightning Storm", *lands, targets=["bob"])
    for forest in scenario.player("alice").hand.copy():
        if forest.name != "Forest":
            continue
        scenario.activate(storm, discarding=[forest], username="alice")
        scenario.will_take_the_may(False)
        scenario.resolve_top()
    assert storm.counter_count("charge") == 4
    scenario.resolve_top()
    assert scenario.player("bob").life == 13  # 3 + 4


def test_blessing_of_frost_with_no_creatures_still_resolves():
    scenario = _board(["Snow-Covered Forest"] * 4, alice_hand=["Blessing of Frost"])
    _cast_blessing(scenario, scenario.untapped_sources(*["Snow-Covered Forest"] * 4))
    assert scenario.game.stack_is_empty


# -- Cards the same readers made handled beyond the task's list (Modern/Pioneer/Standard
#    legal, in no listed deck)


def test_byrke_doubles_the_counters_on_the_creature_that_attacked_not_on_itself():
    scenario = _board(["Byrke, Long Ear of the Law", "Grizzly Bears", "Llanowar Elves"])
    byrke = scenario.creature("Byrke, Long Ear of the Law", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    byrke.add_counters(Counter.PLUS_ONE, 1)
    bears.add_counters(Counter.PLUS_ONE, 2)
    _attack(scenario, bears, elves)
    assert bears.counter_count(Counter.PLUS_ONE) == 4
    assert byrke.counter_count(Counter.PLUS_ONE) == 1  # it did not attack
    assert elves.counter_count(Counter.PLUS_ONE) == 0  # no counter, no trigger


def test_byrke_puts_a_counter_on_each_of_up_to_two_targets_when_it_enters():
    scenario = _board(
        ["Grizzly Bears", "Llanowar Elves"], alice_hand=["Byrke, Long Ear of the Law"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.will_choose_targets(bears, elves, source="Byrke, Long Ear of the Law")
    scenario.put_onto_battlefield("Byrke, Long Ear of the Law", "alice")
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 1 and elves.counter_count(Counter.PLUS_ONE) == 1


def test_ornery_tumblewagg_doubles_the_target_only_while_saddled():
    scenario = _board(["Ornery Tumblewagg", "Grizzly Bears"])
    wagg = scenario.creature("Ornery Tumblewagg", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 3)
    wagg.saddled = True
    scenario.will_choose_targets(bears, source="Ornery Tumblewagg")
    _attack(scenario, wagg)
    assert bears.counter_count(Counter.PLUS_ONE) == 6


def test_ornery_tumblewagg_unsaddled_attack_does_not_double():
    scenario = _board(["Ornery Tumblewagg", "Grizzly Bears"])
    wagg = scenario.creature("Ornery Tumblewagg", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 3)
    _attack(scenario, wagg)
    assert bears.counter_count(Counter.PLUS_ONE) == 3


def test_ornery_tumblewagg_adds_a_counter_at_the_beginning_of_combat():
    scenario = _board(["Ornery Tumblewagg", "Grizzly Bears"], step=Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets(bears, source="Ornery Tumblewagg")
    _to_step(scenario, Step.BEGINNING_OF_COMBAT)
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) == 1


WARLEADER_TOKEN = "Create a 1/1 white Rabbit creature token that's tapped and attacking."
WARLEADER_PUMP = "Attacking creatures you control get +1/+1 until end of turn."


def test_warren_warleader_makes_a_tapped_and_attacking_rabbit():
    scenario = _board(["Warren Warleader", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_mode(WARLEADER_TOKEN, source="Warren Warleader")
    _attack(scenario, bears)
    (rabbit,) = _named(scenario, "Rabbit Token")
    assert rabbit.tapped and rabbit in scenario.attackers()


def test_warren_warleader_pump_mode_makes_the_attackers_bigger():
    scenario = _board(["Warren Warleader", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_mode(WARLEADER_PUMP, source="Warren Warleader")
    _attack(scenario, bears)
    assert _stats(scenario, bears) == (3, 3)
    assert not _named(scenario, "Rabbit Token")


def test_lilianas_influence_puts_a_minus_counter_on_each_creature_you_dont_control():
    scenario = _board(
        ["Swamp"] * 6,
        bob=["Grizzly Bears", "Hill Giant"],
        alice_hand=["Liliana's Influence"],
    )
    scenario.will_take_the_may(False)
    scenario.cast_and_resolve("Liliana's Influence", *scenario.untapped_sources(*["Swamp"] * 6))
    assert scenario.creature("Grizzly Bears", "bob").counter_count(Counter.MINUS_ONE) == 1
    assert scenario.creature("Hill Giant", "bob").counter_count(Counter.MINUS_ONE) == 1
