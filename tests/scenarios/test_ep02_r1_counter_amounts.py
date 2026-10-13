"""EP-02 R1 T8: an amount read off the counters on an object ("X is the number
of <kind> counters on this artifact", "equal to the number of <kind> counters
on it", "for each <kind> counter on it").

CR 122.1 (a counter is a marker on an object; the kind is its name) and, for a
source that has left the battlefield, CR 603.10a (a leaves-the-battlefield
trigger looks back in time) with CR 122.2 (counters cease to exist as the
object moves). Every number below is the live count when the ability resolves.
"""

import pytest

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


def _board(alice, bob=None, *, alice_hand=(), bob_hand=(), library=12, alice_library=None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(alice_hand),
            library=list(alice_library) if alice_library is not None else ["Forest"] * library,
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


# -- a counter-count that names a card by mana value (CR 202.3), not a size

_LIBRARY = ["Llanowar Elves", "Grizzly Bears", "Hill Giant", "Craw Wurm", "Forest"]


def _hand_names(scenario, username="alice"):
    return sorted(c.name for c in scenario.player(username).hand)


def test_aether_vial_puts_the_creature_whose_mana_value_equals_its_charge_counters():
    scenario = _board(["Aether Vial"], alice_hand=["Grizzly Bears", "Hill Giant"])
    vial = scenario.find("Aether Vial", Zone.BATTLEFIELD, "alice")
    vial.add_counters("charge", 4)
    scenario.will_take_the_may(True)
    scenario.activate(vial)
    _settle(scenario)
    assert _count(scenario, "Hill Giant") == 1
    assert _hand_names(scenario) == ["Grizzly Bears"]


def test_aether_vial_does_not_offer_a_creature_of_a_different_mana_value():
    scenario = _board(["Aether Vial"], alice_hand=["Grizzly Bears", "Craw Wurm"])
    vial = scenario.find("Aether Vial", Zone.BATTLEFIELD, "alice")
    vial.add_counters("charge", 3)
    scenario.will_take_the_may(True)
    scenario.activate(vial)
    _settle(scenario)
    assert _count(scenario, "Grizzly Bears") == 0
    assert _count(scenario, "Craw Wurm") == 0
    assert _hand_names(scenario) == ["Craw Wurm", "Grizzly Bears"]


def test_aether_vial_at_zero_counters_puts_nothing_not_even_a_land_or_free_spell():
    scenario = _board(["Aether Vial"], alice_hand=["Grizzly Bears"])
    vial = scenario.find("Aether Vial", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True)
    scenario.activate(vial)
    _settle(scenario)
    assert _count(scenario, "Grizzly Bears") == 0


def test_instrument_of_the_bards_fetches_the_creature_matching_its_harmony_counters():
    scenario = _board(
        ["Instrument of the Bards", "Forest", "Forest", "Forest", "Forest"],
        alice_library=_LIBRARY,
    )
    instrument = scenario.find("Instrument of the Bards", Zone.BATTLEFIELD, "alice")
    instrument.add_counters("harmony", 2)
    scenario.activate(instrument, auto=True)
    _settle(scenario)
    assert _hand_names(scenario) == ["Grizzly Bears"]
    assert not [
        c for c in scenario.game.permanents_controlled_by("alice") if c.card.name == "Treasure"
    ]


def test_instrument_of_the_bards_makes_a_treasure_only_for_a_legendary_find():
    scenario = _board(
        ["Instrument of the Bards", "Forest", "Forest", "Forest", "Forest"],
        alice_library=["Yisan, the Wanderer Bard", "Forest"],
    )
    instrument = scenario.find("Instrument of the Bards", Zone.BATTLEFIELD, "alice")
    instrument.add_counters("harmony", 3)
    scenario.activate(instrument, auto=True)
    _settle(scenario)
    assert _hand_names(scenario) == ["Yisan, the Wanderer Bard"]
    assert _count(scenario, "Treasure Token") == 1


def test_instrument_of_the_bards_finds_nothing_when_no_creature_matches():
    scenario = _board(
        ["Instrument of the Bards", "Forest", "Forest", "Forest", "Forest"],
        alice_library=_LIBRARY,
    )
    instrument = scenario.find("Instrument of the Bards", Zone.BATTLEFIELD, "alice")
    instrument.add_counters("harmony", 9)
    scenario.activate(instrument, auto=True)
    _settle(scenario)
    assert _hand_names(scenario) == []


def test_yisan_puts_a_verse_counter_as_a_cost_then_fetches_that_mana_value():
    scenario = _board(
        ["Yisan, the Wanderer Bard", "Forest", "Forest", "Forest"], alice_library=_LIBRARY
    )
    yisan = scenario.find("Yisan, the Wanderer Bard", Zone.BATTLEFIELD, "alice")
    yisan.summoning_sick = False
    yisan.add_counters("verse", 3)
    scenario.activate(yisan, auto=True)
    assert yisan.counter_count("verse") == 4
    _settle(scenario)
    assert _count(scenario, "Hill Giant") == 1


def test_yisan_with_no_counters_has_to_count_the_one_it_just_added():
    scenario = _board(
        ["Yisan, the Wanderer Bard", "Forest", "Forest", "Forest"], alice_library=_LIBRARY
    )
    yisan = scenario.find("Yisan, the Wanderer Bard", Zone.BATTLEFIELD, "alice")
    yisan.summoning_sick = False
    scenario.activate(yisan, auto=True)
    _settle(scenario)
    assert _count(scenario, "Llanowar Elves") == 1


def test_brain_in_a_jar_casts_a_free_spell_whose_mana_value_equals_its_counters():
    scenario = _board(
        ["Brain in a Jar", "Forest"],
        ["Hill Giant"],
        alice_hand=["Lightning Bolt", "Divination"],
    )
    jar = scenario.find("Brain in a Jar", Zone.BATTLEFIELD, "alice")
    jar.add_counters("charge", 2)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True)
    scenario.activate(jar, auto=True, targets=[])
    scenario.will_choose_targets(giant)
    _settle(scenario)
    assert jar.counter_count("charge") == 3
    # Divination (mana value 3) was cast for free and resolved: two cards drawn.
    assert "Divination" not in _hand_names(scenario)
    assert "Lightning Bolt" in _hand_names(scenario)


def test_brain_in_a_jar_casts_nothing_when_no_spell_has_the_mana_value():
    scenario = _board(["Brain in a Jar", "Forest"], alice_hand=["Divination"])
    jar = scenario.find("Brain in a Jar", Zone.BATTLEFIELD, "alice")
    jar.add_counters("charge", 5)
    scenario.will_take_the_may(True)
    scenario.activate(jar, auto=True)
    _settle(scenario)
    assert jar.counter_count("charge") == 6
    assert _hand_names(scenario) == ["Divination"]


# -- an X cost sets the counters, and the counters then set a number of targets


def _cast_with_x(scenario, name, x, *, lands):
    card = scenario.find(name, Zone.HAND, "alice")
    scenario.game.cast(card, "alice", x_value=x, mana_sources=lands)
    return scenario.resolve_top()


def _lands(scenario):
    return [
        p for p in scenario.game.permanents_controlled_by("alice") if "Land" in p.card.type_line
    ]


def test_quarantine_field_exiles_one_target_per_isolation_counter():
    scenario = _board(
        ["Plains"] * 6,
        ["Grizzly Bears", "Hill Giant", "Craw Wurm"],
        alice_hand=["Quarantine Field"],
    )
    bears, giant = scenario.creature("Grizzly Bears", "bob"), scenario.creature("Hill Giant", "bob")
    scenario.choose_trigger_targets("Quarantine Field", [bears, giant])
    field = _cast_with_x(scenario, "Quarantine Field", 2, lands=_lands(scenario))
    assert field.counter_count("isolation") == 2
    _settle(scenario)
    assert _count(scenario, "Grizzly Bears", "bob") == 0
    assert _count(scenario, "Hill Giant", "bob") == 0
    assert _count(scenario, "Craw Wurm", "bob") == 1


def test_quarantine_field_returns_what_it_exiled_when_it_leaves():
    scenario = _board(["Plains"] * 4, ["Grizzly Bears"], alice_hand=["Quarantine Field"])
    scenario.choose_trigger_targets("Quarantine Field", [scenario.creature("Grizzly Bears", "bob")])
    field = _cast_with_x(scenario, "Quarantine Field", 1, lands=_lands(scenario))
    _settle(scenario)
    assert _count(scenario, "Grizzly Bears", "bob") == 0
    scenario.game.put_into_graveyard(field)
    _settle(scenario)
    assert _count(scenario, "Grizzly Bears", "bob") == 1


def test_quarantine_field_with_x_of_zero_exiles_nothing():
    scenario = _board(["Plains"] * 2, ["Grizzly Bears"], alice_hand=["Quarantine Field"])
    field = _cast_with_x(scenario, "Quarantine Field", 0, lands=_lands(scenario))
    assert field.counter_count("isolation") == 0
    _settle(scenario)
    assert _count(scenario, "Grizzly Bears", "bob") == 1
    assert scenario.stack_names() == []


def test_quarantine_field_exiles_fewer_when_there_are_fewer_legal_targets():
    scenario = _board(["Plains"] * 6, ["Grizzly Bears"], alice_hand=["Quarantine Field"])
    scenario.choose_trigger_targets("Quarantine Field", [scenario.creature("Grizzly Bears", "bob")])
    _cast_with_x(scenario, "Quarantine Field", 2, lands=_lands(scenario))
    _settle(scenario)
    assert _count(scenario, "Grizzly Bears", "bob") == 0


# -- Vastwood Hydra: spreads the counters it died with (CR 603.10a, CR 122.2)


def _hydra_dies(*, take_the_may):
    scenario = _board(
        ["Forest"] * 5 + ["Grizzly Bears", "Llanowar Elves"], [], alice_hand=["Vastwood Hydra"]
    )
    bears, elves = scenario.creature("Grizzly Bears"), scenario.creature("Llanowar Elves")
    hydra = _cast_with_x(scenario, "Vastwood Hydra", 3, lands=_lands(scenario))
    assert hydra.counter_count(Counter.PLUS_ONE) == 3
    scenario.will_take_the_may(take_the_may)
    scenario.choose_trigger_targets("Vastwood Hydra", [bears, elves])
    scenario.game.put_into_graveyard(hydra)
    _settle(scenario)
    return bears.counter_count(Counter.PLUS_ONE), elves.counter_count(Counter.PLUS_ONE)


def test_vastwood_hydra_distributes_every_counter_it_died_with():
    assert sum(_hydra_dies(take_the_may=True)) == 3


def test_vastwood_hydra_gives_each_chosen_creature_at_least_one():
    assert all(n >= 1 for n in _hydra_dies(take_the_may=True))


def test_vastwood_hydra_declined_distributes_nothing():
    assert _hydra_dies(take_the_may=False) == (0, 0)


# -- Necroplasm: destroy each creature whose mana value equals its counters


def _to_end_step(scenario):
    while scenario.step is not Step.END_STEP:
        scenario.advance()


def _necroplasm_end_step(counters, alice=(), bob=()):
    scenario = _board(["Necroplasm", *alice], list(bob))
    necroplasm = scenario.creature("Necroplasm", "alice")
    necroplasm.add_counters(Counter.PLUS_ONE, counters)
    _to_end_step(scenario)
    _settle(scenario)
    return scenario


def test_necroplasm_destroys_every_creature_with_the_counter_count_as_mana_value():
    scenario = _necroplasm_end_step(2, ["Grizzly Bears"], ["Grizzly Bears", "Hill Giant"])
    assert _count(scenario, "Grizzly Bears", "alice") == 0
    assert _count(scenario, "Grizzly Bears", "bob") == 0
    assert _count(scenario, "Hill Giant", "bob") == 1
    assert _count(scenario, "Necroplasm", "alice") == 1


def test_necroplasm_destroys_itself_when_its_counters_equal_its_own_mana_value():
    scenario = _necroplasm_end_step(3, [], ["Hill Giant", "Grizzly Bears"])
    assert _count(scenario, "Necroplasm", "alice") == 0
    assert _count(scenario, "Hill Giant", "bob") == 1
    assert _count(scenario, "Grizzly Bears", "bob") == 1


def test_necroplasm_ignores_other_counter_kinds():
    scenario = _board(["Necroplasm"], ["Grizzly Bears"])
    scenario.creature("Necroplasm", "alice").add_counters("charge", 2)
    _to_end_step(scenario)
    _settle(scenario)
    assert _count(scenario, "Grizzly Bears", "bob") == 1


# -- Huatli, Radiant Champion: a loyalty counter for each creature you control


def test_huatli_plus_one_adds_a_loyalty_counter_for_each_creature_you_control():
    scenario = _board(["Huatli, Radiant Champion", "Grizzly Bears", "Hill Giant"], ["Craw Wurm"])
    huatli = scenario.find("Huatli, Radiant Champion", Zone.BATTLEFIELD, "alice")
    before = huatli.counter_count(Counter.LOYALTY)
    scenario.activate(huatli, index=0)
    _settle(scenario)
    # +1 as the cost, then two creatures (the opponent's does not count).
    assert huatli.counter_count(Counter.LOYALTY) == before + 1 + 2


def test_huatli_plus_one_with_no_creatures_only_pays_its_cost():
    scenario = _board(["Huatli, Radiant Champion"])
    huatli = scenario.find("Huatli, Radiant Champion", Zone.BATTLEFIELD, "alice")
    before = huatli.counter_count(Counter.LOYALTY)
    scenario.activate(huatli, index=0)
    _settle(scenario)
    assert huatli.counter_count(Counter.LOYALTY) == before + 1


# -- Celeborn the Wise: +1/+1 for each card looked at while scrying


def _celeborn_scries(spell, scry_n_looked):
    scenario = _board(["Celeborn the Wise", "Island"], alice_hand=[spell])
    celeborn = scenario.creature("Celeborn the Wise", "alice")
    base = _stats(scenario, celeborn)
    scenario.scry_keeping_everything_on_top()
    scenario.cast_and_resolve(spell, auto=True)
    _settle(scenario)
    return base, _stats(scenario, celeborn), scry_n_looked


def test_celeborn_gets_plus_one_for_one_card_looked_at_while_scrying():
    base, now, looked = _celeborn_scries("Opt", 1)
    assert now == (base[0] + looked, base[1] + looked)


def test_celeborn_gets_plus_two_for_two_cards_looked_at_while_scrying():
    base, now, looked = _celeborn_scries("Preordain", 2)
    assert now == (base[0] + looked, base[1] + looked)


def test_celeborn_scries_when_the_controller_attacks_with_an_elf():
    scenario = _board(["Celeborn the Wise"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    celeborn = scenario.creature("Celeborn the Wise", "alice")
    scenario.scry_keeping_everything_on_top()
    scenario.attack_with(celeborn)
    _settle(scenario)
    # The attack trigger scried one card, which pumped Celeborn by one.
    assert _stats(scenario, celeborn) == (4, 4)


def test_celeborn_pump_ends_at_end_of_turn():
    scenario = _board(["Celeborn the Wise", "Island"], alice_hand=["Opt"])
    celeborn = scenario.creature("Celeborn the Wise", "alice")
    base = _stats(scenario, celeborn)
    scenario.scry_keeping_everything_on_top()
    scenario.cast_and_resolve("Opt", auto=True)
    _settle(scenario)
    assert _stats(scenario, celeborn) != base
    _to_end_step(scenario)
    scenario.advance()  # cleanup
    scenario.turn_based_actions()  # CR 514.2 ends "until end of turn"
    assert _stats(scenario, celeborn) == base


# -- counters removed as a cost (CR 118.3, CR 107.3a), and "for each counter removed"


def _baku(ki, x):
    scenario = _board(["Blademane Baku", "Mountain"])
    baku = scenario.creature("Blademane Baku", "alice")
    baku.add_counters("ki", ki)
    scenario.activate(baku, auto=True, x_value=x)
    _settle(scenario)
    return scenario, baku


def test_blademane_baku_gets_plus_two_power_for_each_ki_counter_removed():
    scenario, baku = _baku(3, 2)
    assert baku.counter_count("ki") == 1
    assert _stats(scenario, baku) == (1 + 4, 1)


def test_blademane_baku_removing_none_pumps_nothing():
    scenario, baku = _baku(3, 0)
    assert baku.counter_count("ki") == 3
    assert _stats(scenario, baku) == (1, 1)


def test_blademane_baku_cannot_remove_more_ki_counters_than_it_has():
    scenario = _board(["Blademane Baku", "Mountain"])
    baku = scenario.creature("Blademane Baku", "alice")
    baku.add_counters("ki", 1)
    with pytest.raises(ValueError):
        scenario.activate(baku, auto=True, x_value=2)


def _parasite(counters, x, *, kind=Counter.PLUS_ONE):
    scenario = _board(["Hex Parasite", "Swamp", "Swamp", "Swamp", "Grizzly Bears"])
    parasite = scenario.creature("Hex Parasite", "alice")
    target = scenario.creature("Grizzly Bears", "alice")
    target.add_counters(kind, counters)
    scenario.activate(parasite, auto=True, x_value=x, targets=[target])
    _settle(scenario)
    return scenario, parasite, target


def test_hex_parasite_removes_up_to_x_counters_and_pumps_per_counter_removed():
    scenario, parasite, target = _parasite(3, 2)
    assert target.counter_count(Counter.PLUS_ONE) == 1
    assert _stats(scenario, parasite) == (1 + 2, 1)


def test_hex_parasite_pumps_only_by_the_counters_that_were_really_there():
    scenario, parasite, target = _parasite(1, 3)
    assert target.counter_count(Counter.PLUS_ONE) == 0
    assert _stats(scenario, parasite) == (1 + 1, 1)


def test_hex_parasite_with_x_of_zero_removes_nothing_and_pumps_nothing():
    scenario, parasite, target = _parasite(2, 0)
    assert target.counter_count(Counter.PLUS_ONE) == 2
    assert _stats(scenario, parasite) == (1, 1)


def test_hex_parasite_takes_counters_of_any_kind():
    scenario, parasite, target = _parasite(2, 1, kind="oil")
    assert target.counter_count("oil") == 1
    assert _stats(scenario, parasite) == (2, 1)


def test_hex_parasite_aimed_at_a_permanent_with_no_counters_pumps_nothing():
    scenario, parasite, target = _parasite(0, 2)
    assert _stats(scenario, parasite) == (1, 1)


def _garnet_attacks(sagas, *, take=True):
    scenario = _board(["Garnet, Princess of Alexandria", *sagas], ["Craw Wurm"])
    garnet = scenario.creature("Garnet, Princess of Alexandria", "alice")
    garnet.summoning_sick = False
    saga_cards = [
        c
        for c in scenario.game.permanents_controlled_by("alice")
        if c.card.name == "The Triumph of Anax"
    ]
    # A Saga enters with a lore counter (CR 714.3a); these two hold three and two.
    for saga, extra in zip(saga_cards, (2, 1), strict=False):
        saga.add_counters("lore", extra)
    before = [saga.counter_count("lore") for saga in saga_cards]
    scenario.will_take_the_may(take)
    scenario.will_choose_cards(*saga_cards, times=None)
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(garnet)
    _settle(scenario)
    return garnet, saga_cards, before


def test_garnet_removes_a_lore_counter_from_each_chosen_saga_and_grows_per_counter():
    garnet, sagas, before = _garnet_attacks(["The Triumph of Anax", "The Triumph of Anax"])
    assert [s.counter_count("lore") for s in sagas] == [n - 1 for n in before]
    assert garnet.counter_count(Counter.PLUS_ONE) == 2


def test_garnet_only_removes_from_the_sagas_chosen():
    scenario = _board(
        ["Garnet, Princess of Alexandria", "The Triumph of Anax", "The Triumph of Anax"],
        ["Craw Wurm"],
    )
    garnet = scenario.creature("Garnet, Princess of Alexandria", "alice")
    garnet.summoning_sick = False
    first, second = [
        c
        for c in scenario.game.permanents_controlled_by("alice")
        if c.card.name == "The Triumph of Anax"
    ]
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(first)
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(garnet)
    _settle(scenario)
    assert (first.counter_count("lore"), second.counter_count("lore")) == (0, 1)
    assert garnet.counter_count(Counter.PLUS_ONE) == 1


def test_garnet_declined_removes_nothing():
    garnet, sagas, before = _garnet_attacks(["The Triumph of Anax"], take=False)
    assert [s.counter_count("lore") for s in sagas] == before
    assert garnet.counter_count(Counter.PLUS_ONE) == 0


def test_garnet_with_no_sagas_gets_nothing():
    garnet, _sagas, _before = _garnet_attacks([])
    assert garnet.counter_count(Counter.PLUS_ONE) == 0


def _ooze_flux(first, second, x):
    scenario = _board(["Ooze Flux", "Forest", "Forest", "Grizzly Bears", "Hill Giant"])
    bears, giant = (
        scenario.creature("Grizzly Bears", "alice"),
        scenario.creature("Hill Giant", "alice"),
    )
    bears.add_counters(Counter.PLUS_ONE, first)
    giant.add_counters(Counter.PLUS_ONE, second)
    flux = scenario.find("Ooze Flux", Zone.BATTLEFIELD, "alice")
    scenario.activate(flux, auto=True, x_value=x)
    _settle(scenario)
    return scenario, bears, giant


def test_ooze_flux_makes_an_ooze_as_large_as_the_counters_it_removed():
    scenario, bears, giant = _ooze_flux(2, 1, 3)
    ooze = scenario.creature("Ooze Token", "alice")
    assert _stats(scenario, ooze) == (3, 3)
    assert bears.counter_count(Counter.PLUS_ONE) + giant.counter_count(Counter.PLUS_ONE) == 0


def test_ooze_flux_may_remove_fewer_counters_than_the_creatures_hold():
    scenario, bears, giant = _ooze_flux(2, 1, 1)
    assert _stats(scenario, scenario.creature("Ooze Token", "alice")) == (1, 1)
    assert bears.counter_count(Counter.PLUS_ONE) + giant.counter_count(Counter.PLUS_ONE) == 2


def test_ooze_flux_cannot_remove_more_counters_than_the_creatures_hold():
    with pytest.raises(ValueError):
        _ooze_flux(1, 1, 3)


def test_ooze_flux_has_to_remove_at_least_one_counter():
    with pytest.raises(ValueError):
        _ooze_flux(1, 1, 0)


# -- second printings of each family, so no family rests on one card alone


def _to_step(scenario, step):
    while scenario.step is not step:
        scenario.advance()


def test_savanti_romero_counts_the_counter_it_just_put_on_itself():
    # CR 608.2c: "Put a +1/+1 counter on Savanti Romero. Then you draw X cards
    # and lose X life, where X is the number of counters on Savanti Romero."
    scenario = _board(["Savanti Romero, Time's Exile"])
    savanti = scenario.creature("Savanti Romero, Time's Exile", "alice")
    savanti.add_counters(Counter.PLUS_ONE, 2)
    _to_step(scenario, Step.BEGINNING_OF_COMBAT)
    _settle(scenario)
    assert savanti.counter_count(Counter.PLUS_ONE) == 3
    assert len(scenario.player("alice").hand) == 3
    assert scenario.player("alice").life == 17


def test_savanti_romero_starts_at_one():
    scenario = _board(["Savanti Romero, Time's Exile"])
    _to_step(scenario, Step.BEGINNING_OF_COMBAT)
    _settle(scenario)
    assert len(scenario.player("alice").hand) == 1
    assert scenario.player("alice").life == 19


def test_quirion_beastcaller_distributes_the_counters_it_died_with():
    scenario = _board(["Quirion Beastcaller", "Grizzly Bears", "Hill Giant"])
    beastcaller = scenario.creature("Quirion Beastcaller", "alice")
    beastcaller.add_counters(Counter.PLUS_ONE, 3)
    bears, giant = scenario.creature("Grizzly Bears", "alice"), scenario.creature("Hill Giant")
    scenario.choose_trigger_targets("Quirion Beastcaller", [bears, giant])
    scenario.game.put_into_graveyard(beastcaller)
    _settle(scenario)
    assert bears.counter_count(Counter.PLUS_ONE) + giant.counter_count(Counter.PLUS_ONE) == 3


def test_otherworld_atlas_draws_per_charge_counter_for_each_player():
    scenario = _board(["Otherworld Atlas"], library=12)
    atlas = scenario.find("Otherworld Atlas", Zone.BATTLEFIELD, "alice")
    atlas.add_counters("charge", 3)
    scenario.activate(atlas, index=1)
    _settle(scenario)
    assert len(scenario.player("alice").hand) == 3
    assert len(scenario.player("bob").hand) == 3


def test_walking_archive_draws_per_plus_one_counter_at_each_upkeep():
    scenario = _board(["Walking Archive"])
    archive = scenario.creature("Walking Archive", "alice")
    archive.add_counters(Counter.PLUS_ONE, 2)
    _to_step(scenario, Step.UPKEEP)
    while scenario.game.active_player.username != "bob":
        scenario.advance()
        if scenario.step is Step.UPKEEP and scenario.game.active_player.username != "bob":
            _settle(scenario)
            continue
    _settle(scenario)
    assert len(scenario.player("bob").hand) >= 2


def test_joraga_warcaller_pumps_other_elves_per_plus_one_counter_on_itself():
    scenario = _board(["Joraga Warcaller", "Llanowar Elves", "Grizzly Bears"], ["Llanowar Elves"])
    warcaller = scenario.creature("Joraga Warcaller", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    assert _stats(scenario, elves) == (1, 1)
    warcaller.add_counters(Counter.PLUS_ONE, 2)
    assert _stats(scenario, elves) == (3, 3)
    assert _stats(scenario, scenario.creature("Grizzly Bears", "alice")) == (2, 2)
    assert _stats(scenario, scenario.creature("Llanowar Elves", "bob")) == (1, 1)
    # "Other": the Warcaller's own pump is only its counters.
    assert _stats(scenario, warcaller) == (3, 3)


def test_glittering_stockpile_adds_one_mana_per_stash_counter():
    scenario = _board(["Glittering Stockpile"])
    stockpile = scenario.find("Glittering Stockpile", Zone.BATTLEFIELD, "alice")
    stockpile.add_counters("stash", 3)
    scenario.activate(stockpile, index=1, color=Color.BLUE)
    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 3}


def test_coral_barrier_makes_a_squid_with_islandwalk():
    scenario = _board(["Island", "Island", "Island"], alice_hand=["Coral Barrier"])
    scenario.cast_and_resolve("Coral Barrier", auto=True)
    _settle(scenario)
    squid = scenario.creature("Squid Token", "alice")
    assert scenario.game.computed_board().of(squid).has_ability("Islandwalk")


def test_jedit_ojanen_makes_a_cat_warrior_with_forestwalk_when_it_attacks():
    scenario = _board(["Jedit Ojanen of Efrava"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Jedit Ojanen of Efrava", "alice"))
    _settle(scenario)
    cat = scenario.creature("Cat Warrior Token", "alice")
    assert scenario.game.computed_board().of(cat).has_ability("Forestwalk")


def test_inspiring_call_draws_per_creature_with_a_plus_one_counter():
    scenario = _board(
        ["Grizzly Bears", "Hill Giant", "Forest", "Forest", "Forest"], alice_hand=["Inspiring Call"]
    )
    scenario.creature("Grizzly Bears", "alice").add_counters(Counter.PLUS_ONE, 1)
    scenario.cast_and_resolve("Inspiring Call", auto=True)
    _settle(scenario)
    assert len(scenario.player("alice").hand) == 1


def test_armorcraft_judge_draws_per_creature_with_a_plus_one_counter():
    scenario = _board(
        ["Grizzly Bears", "Hill Giant", "Forest", "Forest", "Forest", "Forest"],
        alice_hand=["Armorcraft Judge"],
    )
    scenario.creature("Grizzly Bears", "alice").add_counters(Counter.PLUS_ONE, 2)
    scenario.creature("Hill Giant", "alice").add_counters(Counter.PLUS_ONE, 1)
    scenario.cast_and_resolve("Armorcraft Judge", auto=True)
    _settle(scenario)
    assert len(scenario.player("alice").hand) == 2


def test_avatar_of_the_resolute_enters_with_a_counter_per_other_creature_with_one():
    scenario = _board(
        ["Grizzly Bears", "Hill Giant", "Forest", "Forest"], alice_hand=["Avatar of the Resolute"]
    )
    scenario.creature("Grizzly Bears", "alice").add_counters(Counter.PLUS_ONE, 2)
    scenario.creature("Hill Giant", "alice").add_counters(Counter.PLUS_ONE, 1)
    scenario.cast_and_resolve("Avatar of the Resolute", auto=True)
    assert scenario.creature("Avatar of the Resolute", "alice").counter_count(Counter.PLUS_ONE) == 2


def test_glittering_stockpile_marks_itself_with_a_stash_counter_as_it_makes_red():
    # CR 405.6c: the counter is the mana ability's own immediate effect.
    scenario = _board(["Glittering Stockpile"])
    stockpile = scenario.find("Glittering Stockpile", Zone.BATTLEFIELD, "alice")
    assert scenario.activate(stockpile, index=0) is None
    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}
    assert stockpile.counter_count("stash") == 1


# -- the controller chooses which counters come off, and from which permanents
# (CR 122.1, CR 608.2d; Ooze Flux's cost CR 118.3 / CR 601.2b-h)

_STOP = "no more counters"


def _mixed_parasite(*answers, x=2):
    scenario = _board(["Hex Parasite", "Swamp", "Swamp", "Swamp", "Grizzly Bears"])
    parasite = scenario.creature("Hex Parasite", "alice")
    target = scenario.creature("Grizzly Bears", "alice")
    target.add_counters(Counter.PLUS_ONE, 2)
    target.add_counters("oil", 1)
    for answer in answers:
        scenario.will_choose_mode(answer)
    scenario.activate(parasite, auto=True, x_value=x, targets=[target])
    _settle(scenario)
    return scenario, parasite, target


def test_hex_parasite_player_picks_the_kinds_it_removes():
    # Unscripted, the larger pile (+1/+1) goes first; naming "oil" first changes it.
    _, _, default_target = _mixed_parasite()
    assert (
        default_target.counter_count(Counter.PLUS_ONE),
        default_target.counter_count("oil"),
    ) == (
        0,
        1,
    )
    scenario, parasite, target = _mixed_parasite("oil", str(Counter.PLUS_ONE))
    assert (target.counter_count(Counter.PLUS_ONE), target.counter_count("oil")) == (1, 0)
    assert _stats(scenario, parasite) == (1 + 2, 1)


def test_hex_parasite_player_may_stop_before_x_counters():
    scenario, parasite, target = _mixed_parasite("oil", _STOP)
    assert target.counter_count("oil") == 0
    assert target.counter_count(Counter.PLUS_ONE) == 2
    assert _stats(scenario, parasite) == (1 + 1, 1)


def _mixed_flux(*answers, x=2):
    scenario = _board(["Ooze Flux", "Forest", "Forest", "Grizzly Bears", "Hill Giant"])
    bears, giant = (
        scenario.creature("Grizzly Bears", "alice"),
        scenario.creature("Hill Giant", "alice"),
    )
    bears.add_counters(Counter.PLUS_ONE, 2)
    giant.add_counters(Counter.PLUS_ONE, 2)
    for name in answers:
        scenario.will_choose_cards(bears if name == "bears" else giant)
    flux = scenario.find("Ooze Flux", Zone.BATTLEFIELD, "alice")
    scenario.activate(flux, auto=True, x_value=x)
    _settle(scenario)
    return scenario, bears, giant


def _plus(card):
    return card.counter_count(Counter.PLUS_ONE)


def test_ooze_flux_player_picks_which_creature_loses_the_counters():
    _, bears, giant = _mixed_flux()
    assert (_plus(bears), _plus(giant)) == (0, 2)
    scenario, bears, giant = _mixed_flux("giant", "giant")
    assert (_plus(bears), _plus(giant)) == (2, 0)
    assert _stats(scenario, scenario.creature("Ooze Token", "alice")) == (2, 2)


def test_ooze_flux_player_splits_the_counters_between_creatures():
    scenario, bears, giant = _mixed_flux("giant", "bears")
    assert (_plus(bears), _plus(giant)) == (1, 1)
    assert _stats(scenario, scenario.creature("Ooze Token", "alice")) == (2, 2)
