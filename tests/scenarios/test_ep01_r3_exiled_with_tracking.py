"""EP-01-R3 T6: cards exiled with an object (CR 607.2a), tracked and read back.

Listed cards: Bane Alley Broker, Grimoire Thief, Jacob Hauken, Colfenor's
Plans, Evelyn the Covetous, Rogue Class, Vivien Champion of the Wilds,
Semblance Anvil, Azula Cunning Usurper, Cemetery Illuminator, Tinybones,
Hedonist's Trove, Grolnok, Undead Alchemist, Valki.

Proof printings (not listed, Modern/Pioneer legal, in no deck list): Bomat
Courier and Connecting the Dots (exile the top card face down, put all cards
exiled with this into their owners' hands), Gonti and Thief of Sanity (look at
the top cards, exile one face down, cast it).

Rules, each read with `mise run rules:find` in the session that wrote this
file:

- **CR 406.3** - a card "exiled face down" can't be examined by any player
  except when instructions allow it; a player who was allowed to look may keep
  looking until it leaves exile.
- **CR 406.3a** - a card exiled face down has no characteristics.
- **CR 607.2a** - the second ability refers only to cards the first one exiled.
- **CR 701.20e** - looking at a card shows it only to the specified player.
- **CR 400.7** - a permanent that leaves and returns is a new object.
- **CR 603.2c** - an ability triggers once for each occurrence.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

FILLER = ["Forest"] * 6


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _exiled_with(scenario, permanent):
    return scenario.game.cards_exiled_with(permanent.id, permanent.zone_change_stamp)


def _names(cards):
    """Printed names: a face-down card has no name of its own (CR 406.3a)."""
    return [card.card.name for card in cards]


def _known(scenario, username):
    return {known.card_id for known in scenario.game.known_to(username)}


def _attack_and_resolve(scenario, *attackers):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    _resolve_everything(scenario)


def _to_combat_damage(scenario, *attackers):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    _resolve_everything(scenario)
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve_everything(scenario)


# -- exile the top N cards face down (Colfenor's Plans, Grimoire Thief) -------

PLANS_TOP = [
    "Grizzly Bears",
    "Llanowar Elves",
    "Hill Giant",
    "Lightning Bolt",
    "Mountain",
    "Island",
    "Ornithopter",
]


def _plans(library):
    scenario = (
        Scenario()
        .player("alice", hand=["Colfenor's Plans"], library=library)
        .player("bob", library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plans = scenario.put_onto_battlefield("Colfenor's Plans", "alice")
    _resolve_everything(scenario)
    return scenario, plans


def test_colfenors_plans_exiles_the_top_seven_face_down_linked_to_it():
    scenario, plans = _plans([*PLANS_TOP, "Forest"])
    pile = _exiled_with(scenario, plans)
    assert _names(pile) == PLANS_TOP
    assert [card.name for card in scenario.player("alice").library] == ["Forest"]
    for card in pile:
        assert card.zone is Zone.EXILE
        assert not card.face_up
        assert card.has_no_characteristics, "CR 406.3a"


def test_colfenors_plans_pile_is_visible_to_its_controller_only():
    scenario, plans = _plans([*PLANS_TOP, "Forest"])
    pile = {card.id for card in _exiled_with(scenario, plans)}
    assert pile <= _known(scenario, "alice")
    assert not pile & _known(scenario, "bob"), "CR 406.3"


def test_colfenors_plans_exiles_what_the_library_holds_when_short():
    scenario, plans = _plans(["Grizzly Bears", "Forest", "Island"])
    assert len(_exiled_with(scenario, plans)) == 3
    assert scenario.player("alice").library == []


def test_a_second_colfenors_plans_keeps_its_own_pile():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Colfenor's Plans", "Colfenor's Plans"],
            library=[*PLANS_TOP, *PLANS_TOP],
        )
        .player("bob", library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first = scenario.put_onto_battlefield("Colfenor's Plans", "alice")
    _resolve_everything(scenario)
    second = scenario.put_onto_battlefield("Colfenor's Plans", "alice")
    _resolve_everything(scenario)
    assert len(_exiled_with(scenario, first)) == 7
    assert len(_exiled_with(scenario, second)) == 7
    assert not {c.id for c in _exiled_with(scenario, first)} & {
        c.id for c in _exiled_with(scenario, second)
    }


def test_colfenors_plans_pile_cards_can_be_played():
    scenario, plans = _plans(["Mountain", "Grizzly Bears", *PLANS_TOP[2:], "Forest"])
    land = scenario.play_land("Mountain", "alice", from_zone=Zone.EXILE)
    assert land.zone is Zone.BATTLEFIELD


# -- Grimoire Thief: becomes tapped, target opponent's library ---------------


def _thief(bob_library):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grimoire Thief", "Island"], library=FILLER)
        .player("bob", library=bob_library)
        .build()
    )
    thief = scenario.creature("Grimoire Thief", "alice")
    thief.summoning_sick = False
    return scenario, thief


def test_grimoire_thief_exiles_three_from_the_opponents_library_when_tapped():
    scenario, thief = _thief(["Grizzly Bears", "Lightning Bolt", "Hill Giant", "Island"])
    _attack_and_resolve(scenario, thief)
    pile = _exiled_with(scenario, thief)
    assert _names(pile) == ["Grizzly Bears", "Lightning Bolt", "Hill Giant"]
    assert [card.name for card in scenario.player("bob").library] == ["Island"]
    for card in pile:
        assert not card.face_up
        assert card.owner == "bob"


def test_grimoire_thief_pile_is_visible_to_its_controller_not_the_owner():
    scenario, thief = _thief(["Grizzly Bears", "Lightning Bolt", "Hill Giant", "Island"])
    _attack_and_resolve(scenario, thief)
    pile = {card.id for card in _exiled_with(scenario, thief)}
    assert pile <= _known(scenario, "alice")
    assert not pile & _known(scenario, "bob")


def test_grimoire_thief_exiles_less_from_a_short_library():
    scenario, thief = _thief(["Grizzly Bears"])
    _attack_and_resolve(scenario, thief)
    assert _names(_exiled_with(scenario, thief)) == ["Grizzly Bears"]


# -- Rogue Class: combat damage, that player's library, may look --------------


def _rogue_class(bob_library):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rogue Class", "Grizzly Bears"], library=FILLER)
        .player("bob", library=bob_library)
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = False
    return scenario, bears


def test_rogue_class_exiles_the_damaged_players_top_card_face_down_and_alice_may_look():
    scenario, bears = _rogue_class(["Lightning Bolt", "Hill Giant", "Island"])
    _to_combat_damage(scenario, bears)
    (rogue,) = [p for p in scenario.game.battlefield if p.name == "Rogue Class"]
    (card,) = _exiled_with(scenario, rogue)
    assert card.card.name == "Lightning Bolt"
    assert not card.face_up
    assert card.owner == "bob"
    assert card.id in _known(scenario, "alice")
    assert card.id not in _known(scenario, "bob")
    assert [c.name for c in scenario.player("bob").library] == ["Hill Giant", "Island"]


def test_rogue_class_does_not_exile_when_no_damage_is_dealt():
    scenario, bears = _rogue_class(["Lightning Bolt", "Island"])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    _resolve_everything(scenario)
    assert [c.name for c in scenario.player("bob").library] == ["Lightning Bolt", "Island"]


# -- Evelyn, the Covetous: each player's top card with a collection counter ---


def test_evelyn_exiles_each_players_top_card_with_a_collection_counter():
    scenario = (
        Scenario()
        .player("alice", hand=["Evelyn, the Covetous"], library=["Mountain", "Island", "Forest"])
        .player("bob", library=["Forest", "Hill Giant", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    evelyn = scenario.put_onto_battlefield("Evelyn, the Covetous", "alice")
    _resolve_everything(scenario)
    pile = [card for card in scenario.game.exile if card.counter_count("collection") > 0]
    assert sorted((card.name, card.owner) for card in pile) == [
        ("Forest", "bob"),
        ("Mountain", "alice"),
    ]
    for card in pile:
        assert card.face_up, "no 'face down' in the text: examinable by any player"
        assert card.exile_annotation is not None
        assert card.exile_annotation.linked_permanent_id == evelyn.id
    assert [c.name for c in scenario.player("alice").library] == ["Island", "Forest"]
    assert [c.name for c in scenario.player("bob").library] == ["Hill Giant", "Island"]


def test_evelyn_lets_its_controller_play_a_land_exiled_with_a_collection_counter():
    scenario = (
        Scenario()
        .player("alice", hand=["Evelyn, the Covetous"], library=["Island", "Forest"])
        .player("bob", library=["Mountain", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Evelyn, the Covetous", "alice")
    _resolve_everything(scenario)
    land = scenario.play_land("Mountain", "alice", from_zone=Zone.EXILE)
    assert land.zone is Zone.BATTLEFIELD
    assert land.owner == "bob"


def test_evelyn_exiles_nothing_from_an_empty_library():
    scenario = (
        Scenario()
        .player("alice", hand=["Evelyn, the Covetous"], library=["Island"])
        .player("bob", library=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Evelyn, the Covetous", "alice")
    _resolve_everything(scenario)
    assert [card.name for card in scenario.game.exile] == ["Island"]


# -- proof printings: Bomat Courier, Connecting the Dots ---------------------


def test_bomat_courier_exiles_the_top_card_face_down_when_it_attacks():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bomat Courier"], library=["Lightning Bolt", "Forest"])
        .player("bob", library=FILLER)
        .build()
    )
    courier = scenario.creature("Bomat Courier", "alice")
    courier.summoning_sick = False
    _attack_and_resolve(scenario, courier)
    (card,) = _exiled_with(scenario, courier)
    assert card.card.name == "Lightning Bolt"
    assert not card.face_up
    assert card.id not in _known(scenario, "alice"), "(You can't look at it.)"


def test_connecting_the_dots_exiles_one_card_per_attacking_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Connecting the Dots", "Grizzly Bears", "Llanowar Elves"],
            library=["Lightning Bolt", "Hill Giant", "Forest"],
        )
        .player("bob", library=FILLER)
        .build()
    )
    dots = next(p for p in scenario.game.battlefield if p.name == "Connecting the Dots")
    bears, elves = scenario.creatures("Grizzly Bears", "Llanowar Elves", username="alice")
    bears.summoning_sick = elves.summoning_sick = False
    _attack_and_resolve(scenario, bears, elves)
    assert _names(_exiled_with(scenario, dots)) == ["Lightning Bolt", "Hill Giant"]


# -- Bane Alley Broker: draw, exile from hand face down, look, return --------


def _broker(*, hand=("Lightning Bolt",), library=("Grizzly Bears", "Forest", "Forest")):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bane Alley Broker", "Island", "Swamp"],
            hand=list(hand),
            library=list(library),
        )
        .player("bob", library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    broker = scenario.creature("Bane Alley Broker", "alice")
    broker.summoning_sick = False
    return scenario, broker


def _broker_exiles(scenario, broker, card):
    scenario.will_choose_cards(card, username="alice")
    scenario.activate(broker, index=0)
    scenario.pass_until_resolved()


def test_bane_alley_broker_draws_then_exiles_the_chosen_hand_card_face_down():
    scenario, broker = _broker()
    (bolt,) = scenario.player("alice").hand
    _broker_exiles(scenario, broker, bolt)
    assert [c.name for c in scenario.player("alice").hand] == ["Grizzly Bears"]
    assert _exiled_with(scenario, broker) == [bolt]
    assert bolt.zone is Zone.EXILE and not bolt.face_up


def test_bane_alley_broker_can_exile_the_card_it_just_drew():
    scenario, broker = _broker(hand=())
    (bears,) = [c for c in scenario.player("alice").library if c.name == "Grizzly Bears"]
    _broker_exiles(scenario, broker, bears)
    assert scenario.player("alice").hand == []
    assert _names(_exiled_with(scenario, broker)) == ["Grizzly Bears"]


def test_bane_alley_brokers_pile_is_visible_to_its_controller_only():
    scenario, broker = _broker()
    (bolt,) = scenario.player("alice").hand
    _broker_exiles(scenario, broker, bolt)
    assert bolt.id in _known(scenario, "alice")
    assert bolt.id not in _known(scenario, "bob"), "CR 406.3"


def test_bane_alley_broker_returns_a_card_exiled_with_it_to_its_owners_hand():
    scenario, broker = _broker()
    (bolt,) = scenario.player("alice").hand
    _broker_exiles(scenario, broker, bolt)
    broker.untap()
    island, swamp = scenario.untapped_sources("Island", "Swamp", username="alice")
    scenario.will_choose_cards(bolt, username="alice")
    scenario.activate(broker, island, swamp, index=1)
    scenario.pass_until_resolved()
    assert bolt.zone is Zone.HAND and bolt.owner == "alice"
    assert _exiled_with(scenario, broker) == []


def test_bane_alley_broker_returns_only_the_chosen_card_of_several():
    scenario, broker = _broker(hand=("Lightning Bolt", "Hill Giant"), library=("Forest",) * 4)
    bolt, giant = [c for c in scenario.player("alice").hand]
    _broker_exiles(scenario, broker, bolt)
    broker.untap()
    _broker_exiles(scenario, broker, giant)
    broker.untap()
    island, swamp = scenario.untapped_sources("Island", "Swamp", username="alice")
    scenario.will_choose_cards(giant, username="alice")
    scenario.activate(broker, island, swamp, index=1)
    scenario.pass_until_resolved()
    assert giant.zone is Zone.HAND
    assert bolt.zone is Zone.EXILE and not bolt.face_up


def test_bane_alley_broker_with_nothing_exiled_returns_nothing():
    scenario, broker = _broker()
    island, swamp = scenario.untapped_sources("Island", "Swamp", username="alice")
    scenario.activate(broker, island, swamp, index=1)
    scenario.pass_until_resolved()
    assert [c.name for c in scenario.player("alice").hand] == ["Lightning Bolt"]


def test_a_second_bane_alley_broker_does_not_return_the_first_ones_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bane Alley Broker", "Bane Alley Broker", "Island", "Swamp"],
            hand=["Lightning Bolt"],
            library=["Forest"] * 4,
        )
        .player("bob", library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Bane Alley Broker", "Bane Alley Broker", username="alice")
    first.summoning_sick = second.summoning_sick = False
    (bolt,) = scenario.player("alice").hand
    _broker_exiles(scenario, first, bolt)
    island, swamp = scenario.untapped_sources("Island", "Swamp", username="alice")
    scenario.activate(second, island, swamp, index=1)
    scenario.pass_until_resolved()
    assert bolt.zone is Zone.EXILE, "CR 607.2a: the second Broker's pile is empty"


# -- Grimoire Thief: turn face up, counter spells with those names -----------


def test_grimoire_thief_sacrificed_turns_its_pile_up_and_counters_spells_with_those_names():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grimoire Thief", "Island"], library=FILLER)
        .player(
            "bob",
            battlefield=["Mountain"],
            hand=["Lightning Bolt"],
            library=["Lightning Bolt", "Hill Giant", "Forest", "Forest"],
        )
        .build()
    )
    thief = scenario.creature("Grimoire Thief", "alice")
    thief.summoning_sick = False
    _attack_and_resolve(scenario, thief)
    pile = _exiled_with(scenario, thief)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.activate(thief, island, index=0, sacrificing=[thief])
    scenario.pass_until_resolved()
    assert all(card.face_up for card in pile)
    assert sorted(c.name for c in pile) == ["Forest", "Hill Giant", "Lightning Bolt"]
    assert bolt.zone is Zone.GRAVEYARD, "countered: its name is one of the exiled cards"
    assert scenario.player("alice").life == 20


def test_grimoire_thief_does_not_counter_a_spell_with_another_name():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grimoire Thief", "Island"], library=FILLER)
        .player(
            "bob",
            battlefield=["Mountain"],
            hand=["Lightning Bolt"],
            library=["Hill Giant", "Forest", "Forest", "Forest"],
        )
        .build()
    )
    thief = scenario.creature("Grimoire Thief", "alice")
    thief.summoning_sick = False
    _attack_and_resolve(scenario, thief)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.activate(thief, island, index=0, sacrificing=[thief])
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 17


# -- Bomat Courier / Connecting the Dots: put all cards into owners' hands ---


def test_bomat_courier_sacrificed_puts_every_exiled_card_into_its_owners_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Bomat Courier", "Mountain"],
            hand=["Hill Giant"],
            library=["Lightning Bolt", "Forest"],
        )
        .player("bob", library=FILLER)
        .build()
    )
    courier = scenario.creature("Bomat Courier", "alice")
    courier.summoning_sick = False
    _attack_and_resolve(scenario, courier)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    (giant,) = scenario.player("alice").hand
    scenario.activate(courier, mountain, index=0, sacrificing=[courier])
    scenario.pass_until_resolved()
    assert sorted(c.name for c in scenario.player("alice").hand) == ["Lightning Bolt"]
    assert [c.name for c in scenario.player("alice").graveyard if c.name == "Hill Giant"]


# -- look at the top cards, exile one face down, cast it (Vivien, Gonti, Thief) --


def _cast_from_exile(scenario, name, *lands, username="alice"):
    casting = scenario.cast(name, username, from_zone=Zone.EXILE)
    scenario.pay_with(casting.begin_paying(), *lands)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def _vivien(library):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Vivien, Champion of the Wilds", "Forest", "Forest"],
            library=library,
        )
        .player("bob", library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (vivien,) = [p for p in scenario.game.battlefield if p.name.startswith("Vivien")]
    return scenario, vivien


def test_vivien_minus_two_exiles_the_chosen_card_face_down_and_bottoms_the_rest():
    scenario, vivien = _vivien(["Grizzly Bears", "Lightning Bolt", "Island", "Forest"])
    bears, bolt, island = scenario.top_of_library(3, "alice")
    scenario.scry_bottoming(bears, username="alice")
    scenario.activate(vivien, index=1)
    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE and not bears.face_up
    assert _exiled_with(scenario, vivien) == [bears]
    assert bears.id in _known(scenario, "alice")
    assert bears.id not in _known(scenario, "bob")
    names = [c.name for c in scenario.player("alice").library]
    assert names[0] == "Forest" and sorted(names[1:]) == ["Island", "Lightning Bolt"]


def test_vivien_lets_its_controller_cast_the_exiled_creature_card():
    scenario, vivien = _vivien(["Grizzly Bears", "Lightning Bolt", "Island", "Forest"])
    (bears,) = scenario.top_of_library(1, "alice")
    scenario.scry_bottoming(bears, username="alice")
    scenario.activate(vivien, index=1)
    scenario.pass_until_resolved()
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    _cast_from_exile(scenario, "Grizzly Bears", *forests)
    assert bears.zone is Zone.BATTLEFIELD and bears.face_up


def test_vivien_does_not_let_its_controller_cast_an_exiled_noncreature_card():
    scenario, vivien = _vivien(["Grizzly Bears", "Lightning Bolt", "Island", "Forest"])
    _, bolt, _ = scenario.top_of_library(3, "alice")
    scenario.scry_bottoming(bolt, username="alice")
    scenario.activate(vivien, index=1)
    scenario.pass_until_resolved()
    assert bolt.zone is Zone.EXILE
    casting = scenario.cast("Lightning Bolt", "alice", from_zone=Zone.EXILE)
    with pytest.raises(ValueError):
        scenario.pay_with(
            casting.begin_paying(), *scenario.untapped_sources("Forest", username="alice")
        )
        scenario.put_on_stack(casting)


def test_vivien_minus_two_with_a_short_library_looks_at_what_is_there():
    scenario, vivien = _vivien(["Grizzly Bears"])
    scenario.activate(vivien, index=1)
    scenario.pass_until_resolved()
    assert _names(_exiled_with(scenario, vivien)) == ["Grizzly Bears"]
    assert scenario.player("alice").library == []


def _gonti(bob_library):
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Gonti, Lord of Luxury"], battlefield=["Swamp", "Swamp"], library=FILLER
        )
        .player("bob", library=bob_library)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_gonti_exiles_the_chosen_card_of_the_opponents_top_four_face_down():
    scenario = _gonti(["Grizzly Bears", "Lightning Bolt", "Hill Giant", "Island", "Forest"])
    bears, bolt, giant, island = scenario.top_of_library(4, "bob")
    scenario.scry_bottoming(giant, username="alice")
    gonti = scenario.put_onto_battlefield("Gonti, Lord of Luxury", "alice")
    scenario.choose_trigger_targets("Gonti, Lord of Luxury", ["bob"])
    _resolve_everything(scenario)
    assert _exiled_with(scenario, gonti) == [giant]
    assert not giant.face_up and giant.owner == "bob"
    assert giant.id in _known(scenario, "alice") and giant.id not in _known(scenario, "bob")
    assert scenario.player("bob").library[0].name == "Forest"
    assert len(scenario.player("bob").library) == 5 - 1


def test_gonti_lets_its_controller_cast_that_card_with_mana_of_any_type():
    scenario = _gonti(["Grizzly Bears", "Lightning Bolt", "Hill Giant", "Island", "Forest"])
    (bears,) = scenario.top_of_library(1, "bob")
    scenario.scry_bottoming(bears, username="alice")
    scenario.put_onto_battlefield("Gonti, Lord of Luxury", "alice")
    scenario.choose_trigger_targets("Gonti, Lord of Luxury", ["bob"])
    _resolve_everything(scenario)
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    _cast_from_exile(scenario, "Grizzly Bears", *swamps)
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "alice"


def test_thief_of_sanity_puts_the_rest_into_the_damaged_players_graveyard():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Thief of Sanity"], library=FILLER)
        .player("bob", library=["Grizzly Bears", "Lightning Bolt", "Hill Giant", "Island"])
        .build()
    )
    thief = scenario.creature("Thief of Sanity", "alice")
    thief.summoning_sick = False
    bears, bolt, giant = scenario.top_of_library(3, "bob")
    scenario.scry_bottoming(bolt, username="alice")
    _to_combat_damage(scenario, thief)
    assert _names(_exiled_with(scenario, thief)) == ["Lightning Bolt"]
    assert sorted(c.name for c in scenario.player("bob").graveyard) == [
        "Grizzly Bears",
        "Hill Giant",
    ]
    assert [c.name for c in scenario.player("bob").library] == ["Island"]


def _keywords(scenario, permanent):
    return {line.lower() for line in scenario.game.characteristics_of(permanent).abilities}


def _vivien_plus_one(*, target):
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Vivien, Champion of the Wilds", "Grizzly Bears"], library=FILLER
        )
        .player("bob", battlefield=["Hill Giant"], library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (vivien,) = [p for p in scenario.game.battlefield if p.name.startswith("Vivien")]
    creature = scenario.creature(target[0], target[1])
    scenario.activate(vivien, index=0, targets=[creature])
    scenario.pass_until_resolved()
    return scenario, creature


def test_vivien_plus_one_gives_reach_and_vigilance():
    scenario, bears = _vivien_plus_one(target=("Grizzly Bears", "alice"))
    assert {"reach", "vigilance"} <= _keywords(scenario, bears)


def test_vivien_plus_one_can_target_an_opponents_creature():
    scenario, giant = _vivien_plus_one(target=("Hill Giant", "bob"))
    assert {"reach", "vigilance"} <= _keywords(scenario, giant)


def test_vivien_plus_one_lasts_through_the_opponents_turn_and_ends_on_alices_next_turn():
    scenario, bears = _vivien_plus_one(target=("Grizzly Bears", "alice"))
    start = scenario.game.turn.turns_taken
    seen_on_bobs_turn = False
    for _ in range(120):
        scenario.advance()
        turn = scenario.game.turn
        if turn.turns_taken == start + 1 and turn.active_player == "bob":
            seen_on_bobs_turn = {"reach", "vigilance"} <= _keywords(scenario, bears)
        if turn.turns_taken >= start + 2 and turn.active_player == "alice":
            break
    assert seen_on_bobs_turn
    assert not {"reach", "vigilance"} & _keywords(scenario, bears)


# -- Jacob Hauken, Inspector // Hauken's Insight ------------------------------


def _jacob(*, hand=("Lightning Bolt",), library=("Grizzly Bears", "Forest", "Forest")):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jacob Hauken, Inspector", *["Island"] * 6],
            hand=list(hand),
            library=list(library),
        )
        .player("bob", library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jacob = scenario.creature("Jacob Hauken, Inspector", "alice")
    jacob.summoning_sick = False
    return scenario, jacob


def test_jacob_exiles_a_hand_card_face_down_and_its_controller_may_look():
    scenario, jacob = _jacob()
    (bolt,) = scenario.player("alice").hand
    scenario.will_choose_cards(bolt, username="alice")
    scenario.will_pay_the_mana_cost(False)
    scenario.activate(jacob, index=0)
    scenario.pass_until_resolved()
    assert _exiled_with(scenario, jacob) == [bolt]
    assert not bolt.face_up
    assert bolt.id in _known(scenario, "alice") and bolt.id not in _known(scenario, "bob")
    assert not jacob.transformed


def test_jacob_transforms_when_its_controller_pays_four_blue_blue():
    scenario, jacob = _jacob()
    (bolt,) = scenario.player("alice").hand
    scenario.will_choose_cards(bolt, username="alice")
    scenario.will_pay_the_mana_cost(True)
    scenario.activate(jacob, index=0)
    scenario.pass_until_resolved()
    assert jacob.transformed


def test_jacobs_back_face_exiles_the_top_card_each_upkeep_and_may_play_one_free_per_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jacob Hauken, Inspector"],
            library=["Island", "Forest", "Mountain", "Plains"],
        )
        .player("bob", library=FILLER)
        .build()
    )
    jacob = scenario.creature("Jacob Hauken, Inspector", "alice")
    jacob.transformed = True
    scenario.start_at(Step.UNTAP)
    while scenario.step is not Step.UPKEEP:
        scenario.advance()
    _resolve_everything(scenario)
    (pile_card,) = _exiled_with(scenario, jacob)
    assert pile_card.card.name == "Island" and not pile_card.face_up
    assert pile_card.id in _known(scenario, "alice")
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
        _resolve_everything(scenario)
    land = scenario.play_land("Island", "alice", from_zone=Zone.EXILE)
    assert land.zone is Zone.BATTLEFIELD


# -- Semblance Anvil: imprint a nonland card, share a card type, cost {2} less --


def _anvil(hand):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Semblance Anvil", *hand],
            battlefield=["Mountain", "Mountain"],
            library=FILLER,
        )
        .player("bob", library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_anvil(scenario, *, exile=None):
    if exile is None:
        scenario.will_take_the_may(False, username="alice")
    else:
        scenario.will_take_the_may(True, username="alice")
        scenario.will_choose_cards(exile, username="alice")
    anvil = scenario.put_onto_battlefield("Semblance Anvil", "alice")
    _resolve_everything(scenario)
    return anvil


def test_semblance_anvil_exiles_the_chosen_nonland_card_from_hand():
    scenario = _anvil(["Grizzly Bears", "Mountain"])
    (bears,) = [c for c in scenario.player("alice").hand if c.name == "Grizzly Bears"]
    anvil = _enter_anvil(scenario, exile=bears)
    assert bears.zone is Zone.EXILE and bears.face_up
    assert _exiled_with(scenario, anvil) == [bears]


def test_semblance_anvil_cannot_exile_a_land():
    scenario = _anvil(["Mountain"])
    scenario.will_take_the_may(True, username="alice")
    scenario.put_onto_battlefield("Semblance Anvil", "alice")
    with pytest.raises(ValueError, match="CR 608.2d"):
        _resolve_everything(scenario)
    assert [c.name for c in scenario.player("alice").hand] == ["Mountain"]


def test_semblance_anvil_may_be_declined():
    scenario = _anvil(["Grizzly Bears"])
    anvil = _enter_anvil(scenario)
    assert _exiled_with(scenario, anvil) == []
    assert [c.name for c in scenario.player("alice").hand] == ["Grizzly Bears"]


def test_semblance_anvil_discounts_spells_sharing_a_type_with_the_exiled_card():
    scenario = _anvil(["Grizzly Bears", "Hill Giant"])
    (bears,) = [c for c in scenario.player("alice").hand if c.name == "Grizzly Bears"]
    _enter_anvil(scenario, exile=bears)
    casting = scenario.cast("Hill Giant", "alice")
    assert str(casting.total_cost.mana) == "{1}{R}"


def test_semblance_anvil_does_not_discount_a_spell_of_another_type():
    scenario = _anvil(["Lightning Bolt", "Hill Giant"])
    (bolt,) = [c for c in scenario.player("alice").hand if c.name == "Lightning Bolt"]
    _enter_anvil(scenario, exile=bolt)
    casting = scenario.cast("Hill Giant", "alice")
    assert str(casting.total_cost.mana) == "{3}{R}"
