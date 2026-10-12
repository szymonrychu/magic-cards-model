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
from magic_cards_model.machines.casting import why_cannot_cast_from
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


# -- graveyard exile family: Hedonist's Trove, Cemetery Illuminator, Azula, Tinybones


def _cast_from_permission(scenario, card, username="alice", targets=None):
    """Cast `card` from where a "you may cast ... from" permission found it."""
    scenario.game.cast(
        card,
        username,
        keyword="Cast permission",
        targets=targets,
        mana_sources=scenario.game.permanents_controlled_by(username),
    )
    _resolve_everything(scenario)


def _cast_top_of_library(scenario):
    top = scenario.player("alice").library[0]
    casting = scenario.cast(top.name, username="alice", from_zone=Zone.LIBRARY)
    casting.use_keyword("Cast permission")
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    _resolve_everything(scenario)
    return top


def _graveyard_names(scenario, username):
    return [card.name for card in scenario.player(username).graveyard]


def _trove(bob_graveyard, alice_graveyard=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hedonist's Trove"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            graveyard=list(alice_graveyard),
            library=FILLER,
        )
        .player("bob", graveyard=list(bob_graveyard), library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trove = scenario.put_onto_battlefield("Hedonist's Trove", "alice")
    _resolve_everything(scenario)
    return scenario, trove


def test_hedonists_trove_exiles_the_opponents_whole_graveyard_linked_to_it():
    scenario, trove = _trove(["Grizzly Bears", "Lightning Bolt", "Mountain"], ["Hill Giant"])
    assert scenario.player("bob").graveyard == []
    assert _graveyard_names(scenario, "alice") == ["Hill Giant"], "only the opponent's"
    pile = _exiled_with(scenario, trove)
    assert sorted(_names(pile)) == ["Grizzly Bears", "Lightning Bolt", "Mountain"]
    assert all(card.face_up for card in pile)


def test_hedonists_trove_with_an_empty_opponent_graveyard_exiles_nothing():
    scenario, trove = _trove([])
    assert _exiled_with(scenario, trove) == []


def test_hedonists_trove_lets_its_controller_play_a_land_from_the_pile():
    scenario, trove = _trove(["Mountain", "Grizzly Bears"])
    land = scenario.play_land("Mountain", "alice", from_zone=Zone.EXILE)
    assert land.zone is Zone.BATTLEFIELD and land.controller == "alice"


def test_hedonists_trove_allows_only_one_spell_from_the_pile_each_turn():
    scenario, trove = _trove(["Lightning Bolt", "Lightning Bolt"])
    first, second = _exiled_with(scenario, trove)
    _cast_from_permission(scenario, first, targets=["bob"])
    assert first.zone is Zone.GRAVEYARD
    with pytest.raises(ValueError):
        _cast_from_permission(scenario, second, targets=["bob"])
    assert second.zone is Zone.EXILE


def _illuminator(alice_graveyard=(), bob_graveyard=(), library=("Grizzly Bears", "Forest")):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cemetery Illuminator"],
            battlefield=["Island", "Island", "Island", "Island", "Forest", "Forest"],
            graveyard=list(alice_graveyard),
            library=list(library),
        )
        .player("bob", graveyard=list(bob_graveyard), library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_cemetery_illuminator_exiles_a_card_of_the_controllers_choice_from_any_graveyard():
    scenario = _illuminator(["Hill Giant"], ["Lightning Bolt", "Grizzly Bears"])
    bolt = next(c for c in scenario.player("bob").graveyard if c.name == "Lightning Bolt")
    scenario.will_choose_cards(bolt, username="alice")
    illuminator = scenario.put_onto_battlefield("Cemetery Illuminator", "alice")
    _resolve_everything(scenario)
    assert _exiled_with(scenario, illuminator) == [bolt]
    assert sorted(_graveyard_names(scenario, "bob")) == ["Grizzly Bears"]
    assert _graveyard_names(scenario, "alice") == ["Hill Giant"]


def test_cemetery_illuminator_with_every_graveyard_empty_exiles_nothing():
    scenario = _illuminator()
    illuminator = scenario.put_onto_battlefield("Cemetery Illuminator", "alice")
    _resolve_everything(scenario)
    assert _exiled_with(scenario, illuminator) == []


def test_cemetery_illuminator_exiles_again_when_it_attacks():
    scenario = _illuminator(bob_graveyard=["Lightning Bolt", "Grizzly Bears"])
    illuminator = scenario.put_onto_battlefield("Cemetery Illuminator", "alice")
    illuminator.summoning_sick = False
    _resolve_everything(scenario)
    assert len(_exiled_with(scenario, illuminator)) == 1
    _attack_and_resolve(scenario, illuminator)
    assert len(_exiled_with(scenario, illuminator)) == 2


def test_cemetery_illuminator_casts_from_the_top_when_it_shares_a_type_with_its_pile():
    scenario = _illuminator(bob_graveyard=["Hill Giant"], library=["Grizzly Bears", "Forest"])
    scenario.put_onto_battlefield("Cemetery Illuminator", "alice")
    _resolve_everything(scenario)
    assert _cast_top_of_library(scenario).zone is Zone.BATTLEFIELD


def test_cemetery_illuminator_allows_only_one_cast_from_the_top_each_turn():
    scenario = _illuminator(bob_graveyard=["Hill Giant"], library=["Grizzly Bears", "Hill Giant"])
    scenario.put_onto_battlefield("Cemetery Illuminator", "alice")
    _resolve_everything(scenario)
    _cast_top_of_library(scenario)
    top = scenario.player("alice").library[0]
    assert why_cannot_cast_from(top, "alice", Zone.LIBRARY, scenario.game) is not None


def test_cemetery_illuminator_cannot_cast_from_the_top_without_a_shared_type():
    scenario = _illuminator(bob_graveyard=["Lightning Bolt"], library=["Grizzly Bears", "Forest"])
    scenario.put_onto_battlefield("Cemetery Illuminator", "alice")
    _resolve_everything(scenario)
    top = scenario.player("alice").library[0]
    assert why_cannot_cast_from(top, "alice", Zone.LIBRARY, scenario.game) is not None


def test_cemetery_illuminator_lets_its_controller_look_at_the_top_card():
    scenario = _illuminator(library=["Grizzly Bears", "Forest"])
    scenario.put_onto_battlefield("Cemetery Illuminator", "alice")
    (top,) = scenario.top_of_library(1, username="alice")
    assert top.id in _known(scenario, "alice")
    assert top.id not in _known(scenario, "bob")


def _azula(bob_battlefield, bob_graveyard):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Azula, Cunning Usurper"],
            battlefield=["Mountain"] * 4,
            library=FILLER,
        )
        .player(
            "bob", battlefield=list(bob_battlefield), graveyard=list(bob_graveyard), library=FILLER
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_azula_makes_the_opponent_exile_a_nontoken_creature_then_a_nonland_card_linked_to_azula():
    scenario = _azula(["Grizzly Bears", "Hill Giant"], ["Mountain", "Lightning Bolt", "Forest"])
    hill_giant = scenario.creature("Hill Giant", "bob")
    bolt = next(c for c in scenario.player("bob").graveyard if c.name == "Lightning Bolt")
    scenario.will_choose_cards(hill_giant, username="bob")
    scenario.will_choose_cards(bolt, username="bob")
    azula = scenario.put_onto_battlefield("Azula, Cunning Usurper", "alice")
    _resolve_everything(scenario)
    assert sorted(_names(_exiled_with(scenario, azula))) == ["Hill Giant", "Lightning Bolt"]
    assert [c.name for c in scenario.game.battlefield if c.controller == "bob"] == ["Grizzly Bears"]
    assert sorted(_graveyard_names(scenario, "bob")) == ["Forest", "Mountain"]


def test_azula_with_no_creature_and_no_nonland_card_exiles_nothing():
    scenario = _azula([], ["Mountain"])
    azula = scenario.put_onto_battlefield("Azula, Cunning Usurper", "alice")
    _resolve_everything(scenario)
    assert _exiled_with(scenario, azula) == []
    assert _graveyard_names(scenario, "bob") == ["Mountain"]


def test_azula_exiled_cards_can_be_cast_on_its_controllers_turn_with_any_mana():
    scenario = _azula(["Grizzly Bears"], [])
    scenario.put_onto_battlefield("Azula, Cunning Usurper", "alice")
    _resolve_everything(scenario)
    (bears,) = [c for c in scenario.game.exile if c.card.name == "Grizzly Bears"]
    _cast_from_permission(scenario, bears)  # {1}{G} paid with Mountains
    assert bears.zone is Zone.BATTLEFIELD and bears.controller == "alice"


def test_azula_exiled_cards_may_be_cast_as_though_they_had_flash():
    scenario = _azula(["Grizzly Bears"], [])
    scenario.put_onto_battlefield("Azula, Cunning Usurper", "alice")
    _resolve_everything(scenario)
    (bears,) = [c for c in scenario.game.exile if c.card.name == "Grizzly Bears"]
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    _cast_from_permission(scenario, bears)
    assert bears.zone is Zone.BATTLEFIELD


def _tinybones(opponent_hand):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tinybones, Bauble Burglar", "Swamp"] * 1 + ["Swamp"] * 3,
            library=FILLER,
        )
        .player("bob", hand=list(opponent_hand), library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature("Tinybones, Bauble Burglar", "alice")


def test_tinybones_exiles_each_card_an_opponent_discards_with_a_stash_counter():
    scenario, tinybones = _tinybones(["Grizzly Bears", "Hill Giant"])
    bears, giant = scenario.player("bob").hand
    scenario.game.discard_cards("bob", [bears, giant])
    _resolve_everything(scenario)
    assert scenario.player("bob").graveyard == []
    assert sorted(c.name for c in scenario.game.exile) == ["Grizzly Bears", "Hill Giant"]
    for card in (bears, giant):
        assert card.zone is Zone.EXILE
        assert card.counters["stash"] == 1


def test_tinybones_does_not_trigger_on_its_controllers_own_discard():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tinybones, Bauble Burglar"],
            hand=["Grizzly Bears"],
            library=FILLER,
        )
        .player("bob", library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bears,) = scenario.player("alice").hand
    scenario.game.discard_cards("alice", [bears])
    _resolve_everything(scenario)
    assert bears.zone is Zone.GRAVEYARD


def test_tinybones_stashed_card_is_playable_on_its_controllers_turn_though_not_owned():
    scenario, tinybones = _tinybones(["Mountain"])
    (mountain,) = scenario.player("bob").hand
    scenario.game.discard_cards("bob", [mountain])
    _resolve_everything(scenario)
    land = scenario.play_land("Mountain", "alice", from_zone=Zone.EXILE)
    assert land.zone is Zone.BATTLEFIELD and land.controller == "alice"


# -- a card put into a graveyard from a library: Grolnok, Undead Alchemist -----


def _grolnok(library):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grolnok, the Omnivore"], library=list(library))
        .player("bob", library=FILLER)
        .build()
    )
    grolnok = scenario.creature("Grolnok, the Omnivore", "alice")
    grolnok.summoning_sick = False
    return scenario, grolnok


def test_grolnok_exiles_each_permanent_card_it_mills_with_a_croak_counter():
    scenario, grolnok = _grolnok(["Grizzly Bears", "Lightning Bolt", "Forest", "Island"])
    _attack_and_resolve(
        scenario, grolnok
    )  # "Whenever a Frog you control attacks, mill three cards."
    exiled = [c for c in scenario.game.exile if c.card.name in ("Grizzly Bears", "Forest")]
    assert sorted(_names(exiled)) == ["Forest", "Grizzly Bears"]
    for card in exiled:
        assert card.counters["croak"] == 1
    assert _graveyard_names(scenario, "alice") == ["Lightning Bolt"], "a nonpermanent card stays"


def test_grolnok_ignores_cards_milled_from_an_opponents_library():
    scenario, grolnok = _grolnok(["Forest"] * 4)
    scenario.game.put_into_graveyard(scenario.player("bob").library[0])
    _resolve_everything(scenario)
    assert len(scenario.player("bob").graveyard) == 1
    assert not scenario.game.exile


def test_grolnok_ignores_a_permanent_card_that_reached_the_graveyard_from_elsewhere():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grolnok, the Omnivore"],
            hand=["Grizzly Bears"],
            library=FILLER,
        )
        .player("bob", library=FILLER)
        .build()
    )
    (bears,) = scenario.player("alice").hand
    scenario.game.discard_cards("alice", [bears])
    _resolve_everything(scenario)
    assert bears.zone is Zone.GRAVEYARD


def test_grolnok_plays_its_croaked_cards():
    scenario, grolnok = _grolnok(["Forest", "Forest", "Forest", "Island"])
    _attack_and_resolve(scenario, grolnok)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    land = scenario.play_land("Forest", "alice", from_zone=Zone.EXILE)
    assert land.zone is Zone.BATTLEFIELD


def _alchemist(bob_library):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Undead Alchemist"], library=FILLER)
        .player("bob", library=list(bob_library))
        .build()
    )
    alchemist = scenario.creature("Undead Alchemist", "alice")
    alchemist.summoning_sick = False
    return scenario, alchemist


def test_undead_alchemist_exiles_each_creature_card_milled_from_an_opponent_and_makes_a_zombie():
    scenario, alchemist = _alchemist(
        ["Grizzly Bears", "Forest", "Hill Giant", "Lightning Bolt", "Island", "Island"]
    )
    _to_combat_damage(scenario, alchemist)  # the Zombie's combat damage mills bob instead
    assert scenario.player("bob").life == 20
    assert sorted(_graveyard_names(scenario, "bob")) == ["Forest", "Lightning Bolt"]
    assert sorted(c.card.name for c in scenario.game.exile) == ["Grizzly Bears", "Hill Giant"]
    zombies = [c for c in scenario.game.battlefield if c.token and c.controller == "alice"]
    assert len(zombies) == 2
    assert all(z.token and (z.power, z.toughness) == (2, 2) for z in zombies)


def test_undead_alchemist_ignores_creature_cards_milled_from_its_controllers_library():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Undead Alchemist"], library=["Grizzly Bears", "Island"])
        .player("bob", library=FILLER)
        .build()
    )
    scenario.game.put_into_graveyard(scenario.player("alice").library[0])
    _resolve_everything(scenario)
    assert [c for c in scenario.game.battlefield if c.token] == []
    assert _graveyard_names(scenario, "alice") == ["Grizzly Bears"]


# -- Valki, God of Lies // Tibalt, Cosmic Impostor ----------------------------

VALKI = "Valki, God of Lies // Tibalt, Cosmic Impostor"


def _valki(bob_hand, *, lands=("Swamp",) * 6):
    scenario = (
        Scenario()
        .player("alice", hand=[VALKI], battlefield=list(lands), library=FILLER)
        .player("bob", hand=list(bob_hand), library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _enter_valki(scenario, *, exile=None):
    if exile is not None:
        scenario.will_choose_cards(exile, username="alice")
    valki = scenario.put_onto_battlefield(VALKI, "alice")
    _resolve_everything(scenario)
    return valki


def test_valki_reveals_the_opponents_hand_and_exiles_a_chosen_creature_card_from_it():
    scenario = _valki(["Grizzly Bears", "Lightning Bolt", "Hill Giant"])
    bears = next(c for c in scenario.player("bob").hand if c.name == "Grizzly Bears")
    hand_ids = {c.id for c in scenario.player("bob").hand}
    valki = _enter_valki(scenario, exile=bears)
    assert _exiled_with(scenario, valki) == [bears]
    assert bears.face_up
    assert sorted(c.name for c in scenario.player("bob").hand) == ["Hill Giant", "Lightning Bolt"]
    assert hand_ids - {bears.id} <= _known(scenario, "alice"), "the hand was revealed"


def test_valki_exiles_nothing_when_the_hand_has_no_creature_card():
    scenario = _valki(["Lightning Bolt", "Mountain"])
    valki = _enter_valki(scenario)
    assert _exiled_with(scenario, valki) == []
    assert len(scenario.player("bob").hand) == 2


def test_the_exiled_card_returns_to_its_owners_hand_when_valki_leaves():
    scenario = _valki(["Grizzly Bears", "Hill Giant"])
    bears = next(c for c in scenario.player("bob").hand if c.name == "Grizzly Bears")
    valki = _enter_valki(scenario, exile=bears)
    scenario.game.destroy(valki)
    _resolve_everything(scenario)
    assert bears.zone is Zone.HAND and bears.owner == "bob"


def _activate_valki(scenario, valki, x, *, choose):
    scenario.will_choose_cards(choose, username="alice")
    scenario.activate(valki, index=0, x_value=x, auto=True)
    scenario.pass_until_resolved()


def test_valki_becomes_a_copy_of_a_chosen_exiled_creature_card_with_mana_value_x():
    scenario = _valki(["Grizzly Bears", "Hill Giant"])
    bears = next(c for c in scenario.player("bob").hand if c.name == "Grizzly Bears")
    valki = _enter_valki(scenario, exile=bears)
    _activate_valki(scenario, valki, 2, choose=bears)
    board = scenario.game.computed_board().of(valki)
    assert (board.name, board.power, board.toughness) == ("Grizzly Bears", 2, 2)


def test_valki_cannot_copy_a_card_whose_mana_value_is_not_x():
    scenario = _valki(["Grizzly Bears"])
    bears = scenario.player("bob").hand[0]
    valki = _enter_valki(scenario, exile=bears)
    scenario.activate(valki, index=0, x_value=3, auto=True)
    scenario.pass_until_resolved()
    assert scenario.game.computed_board().of(valki).name.startswith("Valki")


def test_valki_copy_ability_with_no_matching_card_does_nothing():
    scenario = _valki([])
    valki = _enter_valki(scenario)
    scenario.activate(valki, index=0, x_value=2, auto=True)
    scenario.pass_until_resolved()
    assert scenario.game.computed_board().of(valki).name.startswith("Valki")


def test_tibalts_emblem_lets_its_controller_play_and_cast_what_plus_two_exiled_after_it_left():
    scenario = (
        Scenario()
        .player("alice", hand=[VALKI], battlefield=["Swamp"] * 3, library=["Forest"] * 4)
        .player("bob", library=["Grizzly Bears", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find(VALKI, Zone.HAND, "alice")
    tibalt = scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    scenario.activate(tibalt, index=0)  # +2: exile the top card of each player's library
    scenario.pass_until_resolved()
    forest = next(c for c in _exiled_with(scenario, tibalt) if c.owner == "alice")
    bears = next(c for c in _exiled_with(scenario, tibalt) if c.owner == "bob")
    scenario.game.destroy(tibalt)
    _resolve_everything(scenario)
    assert scenario.game.play_land(forest, "alice").zone is Zone.BATTLEFIELD
    _cast_from_permission(scenario, bears)  # {1}{G} paid with Swamps: any color
    assert bears.zone is Zone.BATTLEFIELD and bears.controller == "alice"


def test_tibalts_emblem_does_not_open_cards_exiled_with_something_else():
    scenario = _valki([])
    card = scenario.find(VALKI, Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    (stray,) = scenario.game.exile_cards([scenario.player("bob").library[0]])
    with pytest.raises(ValueError):
        scenario.game.play_land(stray, "alice")


# -- proof printings of the graveyard readers (not listed, Modern/Pioneer) ----


def test_elspeths_nightmare_chapter_three_exiles_the_opponents_graveyard():
    scenario = (
        Scenario()
        .player("alice", hand=["Elspeth's Nightmare"], graveyard=["Hill Giant"], library=FILLER)
        .player("bob", graveyard=["Grizzly Bears", "Lightning Bolt"], library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.put_onto_battlefield("Elspeth's Nightmare", "alice")
    scenario.pass_until_resolved()
    scenario.game.add_counters(saga, "lore", 2)  # chapter III
    scenario.pass_until_resolved()
    assert scenario.player("bob").graveyard == []
    assert _graveyard_names(scenario, "alice") == ["Hill Giant"]
    assert sorted(c.card.name for c in scenario.game.exile) == ["Grizzly Bears", "Lightning Bolt"]


def _cemetery_creature(name, alice_graveyard=(), bob_graveyard=(), extra_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[name, *extra_hand],
            battlefield=["Plains"] * 5,
            graveyard=list(alice_graveyard),
            library=FILLER,
        )
        .player("bob", graveyard=list(bob_graveyard), library=FILLER)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


@pytest.mark.parametrize("name", ["Cemetery Gatekeeper", "Cemetery Protector"])
def test_a_cemetery_creature_exiles_a_chosen_graveyard_card_on_entering(name):
    scenario = _cemetery_creature(name, ["Hill Giant"], ["Grizzly Bears", "Lightning Bolt"])
    bolt = next(c for c in scenario.player("bob").graveyard if c.name == "Lightning Bolt")
    scenario.will_choose_cards(bolt, username="alice")
    creature = scenario.put_onto_battlefield(name, "alice")
    _resolve_everything(scenario)
    assert _exiled_with(scenario, creature) == [bolt]
    assert bolt.zone is Zone.EXILE


def test_cemetery_protector_makes_a_token_for_a_land_when_a_land_was_exiled():
    scenario = _cemetery_creature(
        "Cemetery Protector", bob_graveyard=["Mountain"], extra_hand=["Forest"]
    )
    scenario.put_onto_battlefield("Cemetery Protector", "alice")
    _resolve_everything(scenario)
    scenario.play_land("Forest", "alice")
    _resolve_everything(scenario)
    tokens = [c for c in scenario.game.battlefield if c.token and c.controller == "alice"]
    assert [(t.power, t.toughness) for t in tokens] == [(1, 1)]
