"""EP-02 R1 T8: an amount read off the counters on an object ("X is the number
of <kind> counters on this artifact", "equal to the number of <kind> counters
on it", "for each <kind> counter on it").

CR 122.1 (a counter is a marker on an object; the kind is its name) and, for a
source that has left the battlefield, CR 603.10a (a leaves-the-battlefield
trigger looks back in time) with CR 122.2 (counters cease to exist as the
object moves). Every number below is the live count when the ability resolves.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _settle(scenario, limit=12):
    """Put triggers on the stack and resolve until the stack is empty."""
    for _ in range(limit):
        scenario.game.put_triggers_on_stack()
        if not scenario.stack_names():
            return
        scenario.pass_until_resolved()
    raise AssertionError(f"stack never emptied: {scenario.stack_names()}")


def _board(alice, bob=None, *, alice_hand=(), bob_hand=(), library=12):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(alice_hand),
            library=["Forest"] * library,
        )
        .player(
            "bob",
            battlefield=list(bob or ()),
            hand=list(bob_hand),
            library=["Forest"] * library,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _count(scenario, name, username="alice"):
    return len([c for c in scenario.game.permanents_controlled_by(username) if c.card.name == name])


# -- mill X, where X is the number of <kind> counters on this artifact


def test_font_of_progress_mills_one_card_per_oil_counter():
    scenario = _board(["Font of Progress", "Island", "Island", "Island"])
    font = scenario.find("Font of Progress", Zone.BATTLEFIELD, "alice")
    font.add_counters("oil", 3)
    scenario.activate(font, auto=True, targets=[scenario.player("bob")])
    _settle(scenario)
    assert len(scenario.player("bob").library) == 12 - 3
    assert len(scenario.player("bob").graveyard) == 3


def test_font_of_progress_with_no_oil_counters_mills_nothing():
    scenario = _board(["Font of Progress", "Island", "Island", "Island"])
    font = scenario.find("Font of Progress", Zone.BATTLEFIELD, "alice")
    scenario.activate(font, auto=True, targets=[scenario.player("bob")])
    _settle(scenario)
    assert len(scenario.player("bob").library) == 12


def test_font_of_progress_counts_only_oil_counters():
    scenario = _board(["Font of Progress", "Island", "Island", "Island"])
    font = scenario.find("Font of Progress", Zone.BATTLEFIELD, "alice")
    font.add_counters("oil", 2)
    font.add_counters("charge", 5)
    scenario.activate(font, auto=True, targets=[scenario.player("alice")])
    _settle(scenario)
    assert len(scenario.player("alice").library) == 12 - 2


def test_grindclock_mills_per_charge_counter_on_a_chosen_player():
    scenario = _board(["Grindclock"])
    clock = scenario.find("Grindclock", Zone.BATTLEFIELD, "alice")
    clock.add_counters("charge", 4)
    scenario.activate(clock, targets=[scenario.player("bob")], index=1)
    _settle(scenario)
    assert len(scenario.player("bob").library) == 12 - 4


# -- loses life equal to the number of <kind> counters on this artifact


def test_ravenous_amulet_drains_each_opponent_by_its_soul_counters():
    scenario = _board(["Ravenous Amulet", "Island", "Island", "Island", "Island"])
    amulet = scenario.find("Ravenous Amulet", Zone.BATTLEFIELD, "alice")
    amulet.add_counters("soul", 3)
    scenario.activate(amulet, auto=True, index=1, sacrificing=[amulet])
    _settle(scenario)
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20
    assert amulet.zone is Zone.GRAVEYARD


def test_ravenous_amulet_with_no_soul_counters_costs_the_opponent_nothing():
    scenario = _board(["Ravenous Amulet", "Island", "Island", "Island", "Island"])
    amulet = scenario.find("Ravenous Amulet", Zone.BATTLEFIELD, "alice")
    scenario.activate(amulet, auto=True, index=1, sacrificing=[amulet])
    _settle(scenario)
    assert scenario.player("bob").life == 20


# -- discards a card for each <kind> counter on this artifact


def test_shrine_of_limitless_power_makes_the_target_discard_per_charge_counter():
    scenario = _board(
        ["Shrine of Limitless Power", "Island", "Island", "Island", "Island"],
        bob_hand=["Forest"] * 4,
    )
    shrine = scenario.find("Shrine of Limitless Power", Zone.BATTLEFIELD, "alice")
    shrine.add_counters("charge", 3)
    scenario.activate(shrine, auto=True, targets=[scenario.player("bob")], sacrificing=[shrine])
    _settle(scenario)
    assert len(scenario.player("bob").hand) == 1


def test_shrine_of_limitless_power_discards_no_more_than_the_hand_holds():
    scenario = _board(
        ["Shrine of Limitless Power", "Island", "Island", "Island", "Island"],
        bob_hand=["Forest"],
    )
    shrine = scenario.find("Shrine of Limitless Power", Zone.BATTLEFIELD, "alice")
    shrine.add_counters("charge", 5)
    scenario.activate(shrine, auto=True, targets=[scenario.player("bob")], sacrificing=[shrine])
    _settle(scenario)
    assert len(scenario.player("bob").hand) == 0


# -- damage equal to the number of <kind> counters on it, and that much again


def test_dragonspark_reactor_deals_its_charge_counters_to_a_player_and_a_creature():
    scenario = _board(
        ["Dragonspark Reactor", "Mountain", "Mountain", "Mountain", "Mountain"],
        ["Grizzly Bears", "Hill Giant"],
    )
    reactor = scenario.find("Dragonspark Reactor", Zone.BATTLEFIELD, "alice")
    reactor.add_counters("charge", 3)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.activate(
        reactor,
        auto=True,
        targets=[scenario.player("bob"), giant],
        sacrificing=[reactor],
    )
    _settle(scenario)
    assert scenario.player("bob").life == 17
    assert giant.zone is Zone.GRAVEYARD  # 3 damage kills a 3/3


def test_dragonspark_reactor_marks_the_same_amount_on_a_creature_that_survives():
    scenario = _board(
        ["Dragonspark Reactor", "Mountain", "Mountain", "Mountain", "Mountain"],
        ["Hill Giant"],
    )
    reactor = scenario.find("Dragonspark Reactor", Zone.BATTLEFIELD, "alice")
    reactor.add_counters("charge", 2)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.activate(
        reactor, auto=True, targets=[scenario.player("bob"), giant], sacrificing=[reactor]
    )
    _settle(scenario)
    assert scenario.player("bob").life == 18
    assert giant.damage == 2


# -- draw X cards, where X is the number of <kind> counters on it


def test_surrakar_spellblade_draws_per_charge_counter_on_combat_damage():
    scenario = _board(["Surrakar Spellblade"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    blade = scenario.creature("Surrakar Spellblade", "alice")
    blade.add_counters("charge", 2)
    scenario.attack_with(blade)
    scenario.no_blocks()
    scenario.will_take_the_may(True)
    scenario.combat_damage()
    _settle(scenario)
    assert len(scenario.player("alice").hand) == 2
    assert len(scenario.player("alice").library) == 10


# -- statics: "get +1/+1 for each <kind> counter on this <permanent>"


def _stats(scenario, card):
    chars = scenario.game.characteristics_of(card)
    return chars.power, chars.toughness


def test_call_for_unity_pumps_every_creature_you_control_per_unity_counter():
    scenario = _board(["Call for Unity", "Grizzly Bears", "Hill Giant"], ["Grizzly Bears"])
    call = scenario.find("Call for Unity", Zone.BATTLEFIELD, "alice")
    mine = scenario.creature("Grizzly Bears", "alice")
    assert _stats(scenario, mine) == (2, 2)
    call.add_counters("unity", 2)
    assert _stats(scenario, mine) == (4, 4)
    assert _stats(scenario, scenario.creature("Hill Giant", "alice")) == (5, 5)
    assert _stats(scenario, scenario.creature("Grizzly Bears", "bob")) == (2, 2)


def test_call_for_unity_ignores_other_counter_kinds_and_moves_with_the_count():
    scenario = _board(["Call for Unity", "Grizzly Bears"])
    call = scenario.find("Call for Unity", Zone.BATTLEFIELD, "alice")
    mine = scenario.creature("Grizzly Bears", "alice")
    call.add_counters("charge", 4)
    assert _stats(scenario, mine) == (2, 2)
    call.add_counters("unity", 1)
    assert _stats(scenario, mine) == (3, 3)
    call.add_counters("unity", 2)
    assert _stats(scenario, mine) == (5, 5)


def test_chitterspitter_pumps_only_squirrels_you_control():
    scenario = _board(["Chitterspitter", "Forest", "Grizzly Bears"])
    spitter = scenario.find("Chitterspitter", Zone.BATTLEFIELD, "alice")
    scenario.activate(spitter, auto=True)
    _settle(scenario)
    squirrel = scenario.creature("Squirrel Token", "alice")
    assert _stats(scenario, squirrel) == (1, 1)
    spitter.add_counters("acorn", 3)
    assert _stats(scenario, squirrel) == (4, 4)
    assert _stats(scenario, scenario.creature("Grizzly Bears", "alice")) == (2, 2)
    spitter.add_counters("charge", 5)
    assert _stats(scenario, squirrel) == (4, 4)


def test_high_sentinels_counts_other_creatures_with_a_plus_one_counter():
    scenario = _board(["High Sentinels of Arashin", "Grizzly Bears", "Hill Giant"])
    sentinels = scenario.creature("High Sentinels of Arashin", "alice")
    base = _stats(scenario, sentinels)
    scenario.creature("Grizzly Bears", "alice").add_counters(Counter.PLUS_ONE, 3)
    assert _stats(scenario, sentinels) == (base[0] + 1, base[1] + 1)
    scenario.creature("Hill Giant", "alice").add_counters(Counter.PLUS_ONE, 1)
    assert _stats(scenario, sentinels) == (base[0] + 2, base[1] + 2)


def test_high_sentinels_does_not_count_itself_or_other_counter_kinds_or_opponents():
    scenario = _board(["High Sentinels of Arashin", "Grizzly Bears"], ["Hill Giant"])
    sentinels = scenario.creature("High Sentinels of Arashin", "alice")
    base = _stats(scenario, sentinels)
    sentinels.add_counters(Counter.PLUS_ONE, 2)
    scenario.creature("Grizzly Bears", "alice").add_counters("charge", 2)
    scenario.creature("Hill Giant", "bob").add_counters(Counter.PLUS_ONE, 2)
    # Its own two counters pump it directly (+2/+2); none of the rest counts.
    assert _stats(scenario, sentinels) == (base[0] + 2, base[1] + 2)


# -- a dies trigger reads the counters the creature had (CR 603.10a, CR 122.2)


def test_chasm_skulker_dies_into_a_squid_per_plus_one_counter():
    scenario = _board(["Chasm Skulker"])
    skulker = scenario.creature("Chasm Skulker", "alice")
    skulker.add_counters(Counter.PLUS_ONE, 3)
    scenario.game.put_into_graveyard(skulker)
    _settle(scenario)
    assert _count(scenario, "Squid Token") == 3


def test_chasm_skulker_squids_have_islandwalk():
    scenario = _board(["Chasm Skulker"])
    skulker = scenario.creature("Chasm Skulker", "alice")
    skulker.add_counters(Counter.PLUS_ONE, 1)
    scenario.game.put_into_graveyard(skulker)
    _settle(scenario)
    squid = scenario.creature("Squid Token", "alice")
    assert scenario.game.computed_board().of(squid).has_ability("Islandwalk")


def test_chasm_skulker_without_counters_makes_nothing():
    scenario = _board(["Chasm Skulker"])
    scenario.game.put_into_graveyard(scenario.creature("Chasm Skulker", "alice"))
    _settle(scenario)
    assert _count(scenario, "Squid Token") == 0


def test_grief_tyrant_spreads_its_minus_counters_onto_a_target_creature():
    scenario = _board(["Grief Tyrant"], ["Craw Wurm"])
    tyrant = scenario.creature("Grief Tyrant", "alice")
    tyrant.add_counters(Counter.MINUS_ONE, 3)
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.game.put_into_graveyard(tyrant)
    scenario.choose_trigger_targets("Grief Tyrant", [wurm])
    _settle(scenario)
    assert wurm.counter_count(Counter.MINUS_ONE) == 3


def test_soulstinger_asks_before_putting_its_counters_on_a_creature():
    scenario = _board(["Soulstinger"], ["Craw Wurm"])
    stinger = scenario.creature("Soulstinger", "alice")
    stinger.add_counters(Counter.MINUS_ONE, 2)
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.will_take_the_may(True)
    scenario.game.put_into_graveyard(stinger)
    scenario.choose_trigger_targets("Soulstinger", [wurm])
    _settle(scenario)
    assert wurm.counter_count(Counter.MINUS_ONE) == 2


def test_soulstinger_declined_puts_nothing():
    scenario = _board(["Soulstinger"], ["Craw Wurm"])
    stinger = scenario.creature("Soulstinger", "alice")
    stinger.add_counters(Counter.MINUS_ONE, 2)
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.will_take_the_may(False)
    scenario.game.put_into_graveyard(stinger)
    scenario.choose_trigger_targets("Soulstinger", [wurm])
    _settle(scenario)
    assert wurm.counter_count(Counter.MINUS_ONE) == 0


# -- pumps and life totals read off the source's counters


def test_scroll_of_the_masters_pumps_by_its_lore_counters():
    scenario = _board(["Scroll of the Masters", "Island", "Island", "Island", "Grizzly Bears"])
    scroll = scenario.find("Scroll of the Masters", Zone.BATTLEFIELD, "alice")
    scroll.add_counters("lore", 3)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(scroll, auto=True, targets=[bears])
    _settle(scenario)
    assert _stats(scenario, bears) == (5, 5)


def test_scroll_of_the_masters_with_no_lore_counters_pumps_nothing():
    scenario = _board(["Scroll of the Masters", "Island", "Island", "Island", "Grizzly Bears"])
    scroll = scenario.find("Scroll of the Masters", Zone.BATTLEFIELD, "alice")
    scroll.add_counters("charge", 4)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(scroll, auto=True, targets=[bears])
    _settle(scenario)
    assert _stats(scenario, bears) == (2, 2)


def test_the_triumph_of_anax_chapter_pumps_by_the_lore_counters_it_has_then():
    scenario = _board(["Grizzly Bears"], alice_hand=["The Triumph of Anax"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.put_onto_battlefield("The Triumph of Anax", "alice")
    scenario.choose_trigger_targets("The Triumph of Anax", [bears])
    _settle(scenario)
    assert _stats(scenario, bears) == (3, 2)
    assert scenario.game.computed_board().of(bears).has_ability("Trample")


def test_eternity_vessel_sets_life_to_its_charge_counters_on_landfall():
    scenario = _board(["Eternity Vessel"], alice_hand=["Forest"])
    vessel = scenario.find("Eternity Vessel", Zone.BATTLEFIELD, "alice")
    vessel.add_counters("charge", 7)
    scenario.will_take_the_may(True)
    scenario.play_land("Forest")
    _settle(scenario)
    assert scenario.player("alice").life == 7


def test_eternity_vessel_may_decline_to_change_its_life_total():
    scenario = _board(["Eternity Vessel"], alice_hand=["Forest"])
    vessel = scenario.find("Eternity Vessel", Zone.BATTLEFIELD, "alice")
    vessel.add_counters("charge", 7)
    scenario.will_take_the_may(False)
    scenario.play_land("Forest")
    _settle(scenario)
    assert scenario.player("alice").life == 20


def test_eternity_vessel_can_raise_life_as_well_as_lower_it():
    scenario = _board(["Eternity Vessel"], alice_hand=["Forest"])
    scenario.player("alice").life = 4
    scenario.find("Eternity Vessel", Zone.BATTLEFIELD, "alice").add_counters("charge", 30)
    scenario.will_take_the_may(True)
    scenario.play_land("Forest")
    _settle(scenario)
    assert scenario.player("alice").life == 30


# -- Add X mana of any one color, where X is the number of charge counters (a mana ability)


def test_the_eternity_elevator_taps_for_its_charge_counters_in_one_color():
    scenario = _board(["The Eternity Elevator"])
    elevator = scenario.find("The Eternity Elevator", Zone.BATTLEFIELD, "alice")
    elevator.add_counters("charge", 21)
    ability = scenario.activate(elevator, index=1, color=Color.GREEN)
    assert ability is None, ability.ability.text  # a mana ability: no stack
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 21}


def test_the_eternity_elevator_adds_nothing_without_charge_counters_past_its_threshold():
    scenario = _board(["The Eternity Elevator"])
    elevator = scenario.find("The Eternity Elevator", Zone.BATTLEFIELD, "alice")
    elevator.add_counters("charge", 5)
    # CR 721.2: the 20+ ability is not there yet; only the colorless one is.
    assert scenario.why_cannot_activate(elevator, index=1) is not None
