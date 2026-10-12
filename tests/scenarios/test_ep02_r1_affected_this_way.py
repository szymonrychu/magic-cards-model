"""EP-02 R1 T2: "N things affected this way" back-references - the payoff
sentence that counts what the instruction before it really moved.

    Destroy all creatures. You gain 1 life for each creature destroyed this way.
    Destroy any number of target creatures. For each creature destroyed this
    way, its controller creates a 4/4 red Dragon creature token with flying.
    Target player mills four cards. You draw a card for each creature card put
    into their graveyard this way.

Rules, each read in full with `mise run rules:find` in this session:

- CR 608.2c - the instructions are followed in order and later text on the
  card may modify the meaning of earlier text: "this way" is the earlier
  instruction's own outcome.
- CR 701.8a - to destroy a permanent is to move it from the battlefield to its
  owner's graveyard, so a permanent that is indestructible, regenerated or sent
  elsewhere by a replacement effect was not destroyed "this way".
- CR 701.17a / CR 701.17c - a milled card is found in the zone it moved to.
- CR 608.2h - the information is taken once, as the instruction is applied; a
  creature's controller and characteristics are those it last had on the
  battlefield (last known information).

Listed cards: Death Begets Life, Fracturing Gust, Fumigate, Paraselene, Kaya's
Wrath, Phyrexian Rebirth, Descent of the Dragons, Rampage of the Clans,
Terastodon, Hour of Need, Curse of the Swine, Krenko's Buzzcrusher, Sylvan
Primordial, Noxious Gearhulk, Midnight Ritual, Culmination of Studies,
Froghemoth, Faerie Slumber Party, Paradoxical Outcome, Morgue Burst, Skull
Raid, Jace's Archivist, Coerced Confession, Dread Summons, Patient Rebuilding,
Liliana's Indignation.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LISTED = [
    "Death Begets Life",
    "Fracturing Gust",
    "Fumigate",
    "Paraselene",
    "Kaya's Wrath",
    "Phyrexian Rebirth",
    "Descent of the Dragons",
    "Rampage of the Clans",
    "Terastodon",
    "Hour of Need",
    "Curse of the Swine",
    "Krenko's Buzzcrusher",
    "Sylvan Primordial",
    "Noxious Gearhulk",
    "Midnight Ritual",
    "Culmination of Studies",
    "Froghemoth",
    "Faerie Slumber Party",
    "Paradoxical Outcome",
    "Morgue Burst",
    "Skull Raid",
    "Jace's Archivist",
    "Coerced Confession",
    "Dread Summons",
    "Patient Rebuilding",
    "Liliana's Indignation",
]


@pytest.mark.parametrize("name", LISTED)
def test_every_listed_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(
    *,
    alice_hand=(),
    alice_battlefield=(),
    alice_lands=("Plains", "Swamp", "Mountain", "Forest", "Island"),
    alice_library=("Forest",) * 8,
    alice_graveyard=(),
    bob_hand=(),
    bob_battlefield=(),
    bob_library=("Island",) * 8,
    bob_graveyard=(),
    start=Step.PRECOMBAT_MAIN,
    manual=False,
):
    builder = Scenario()
    if manual:
        builder = builder.manual_turn_based_actions()
    scenario = (
        builder.player(
            "alice",
            hand=list(alice_hand),
            battlefield=[*alice_lands, *alice_lands, *alice_battlefield],
            library=list(alice_library),
            graveyard=list(alice_graveyard),
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=["Swamp", "Swamp", *bob_battlefield],
            library=list(bob_library),
            graveyard=list(bob_graveyard),
        )
        .build()
    )
    scenario.start_at(start)
    return scenario


def _alice_upkeep(scenario):
    """Walk the turn order on to alice's next upkeep step (CR 503.1a)."""
    for _ in range(2):
        scenario.turn.advance_to(Step.CLEANUP)
        scenario.advance()  # untap
        scenario.advance()  # upkeep


def _cast(scenario, name, targets=None):
    return scenario.cast_and_resolve(name, username="alice", targets=targets, auto=True)


def _names(scenario, username, zone):
    return sorted(state.name for state in getattr(scenario.player(username), zone.value))


def _battlefield_of(scenario, username):
    return sorted(
        state.name
        for state in scenario.game.battlefield
        if state.controller == username and "Land" not in str(state.card.type_line)
    )


# -- Fumigate: "You gain 1 life for each creature destroyed this way" ---------


def test_fumigate_gains_one_life_per_creature_it_destroyed_from_every_side():
    scenario = _board(
        alice_hand=["Fumigate"],
        alice_battlefield=["Grizzly Bears", "Hill Giant"],
        bob_battlefield=["Serra Angel"],
    )
    _cast(scenario, "Fumigate")
    assert _battlefield_of(scenario, "alice") == []
    assert _battlefield_of(scenario, "bob") == []
    assert scenario.player("alice").life == 23


def test_fumigate_does_not_count_an_indestructible_creature():
    scenario = _board(
        alice_hand=["Fumigate"],
        alice_battlefield=["Grizzly Bears", "Darksteel Myr"],
    )
    _cast(scenario, "Fumigate")
    assert _battlefield_of(scenario, "alice") == ["Darksteel Myr"]
    assert scenario.player("alice").life == 21


def test_fumigate_with_no_creatures_gains_nothing():
    scenario = _board(alice_hand=["Fumigate"])
    _cast(scenario, "Fumigate")
    assert scenario.player("alice").life == 20


def test_fumigate_does_not_count_a_regenerated_creature():
    scenario = _board(
        alice_hand=["Fumigate"],
        alice_battlefield=["Manor Skeleton", "Grizzly Bears"],
    )
    skeleton = scenario.creature("Manor Skeleton", "alice")
    swamp = scenario.untapped_sources("Swamp", username="alice")[0]
    island = scenario.untapped_sources("Island", username="alice")[0]
    scenario.activate(skeleton, swamp, island)
    scenario.pass_until_resolved()
    assert skeleton.regeneration_shields == 1
    _cast(scenario, "Fumigate")
    assert "Manor Skeleton" in _battlefield_of(scenario, "alice")
    assert scenario.player("alice").life == 21


# -- Death Begets Life / Fracturing Gust / Paraselene: "permanent destroyed" --


def test_death_begets_life_draws_a_card_per_creature_and_enchantment_destroyed():
    scenario = _board(
        alice_hand=["Death Begets Life"],
        alice_battlefield=["Grizzly Bears", "Glorious Anthem", "Ghostly Prison", "Sol Ring"],
        bob_battlefield=["Serra Angel"],
        alice_lands=("Plains", "Swamp", "Mountain", "Forest", "Island", "Forest"),
    )
    before = len(scenario.player("alice").hand)
    _cast(scenario, "Death Begets Life")
    # Grizzly Bears + Serra Angel + Pacifism + Rancor destroyed, Sol Ring stays.
    assert len(scenario.player("alice").hand) == before - 1 + 4
    assert "Sol Ring" in _battlefield_of(scenario, "alice")


def test_fracturing_gust_gains_two_life_per_artifact_and_enchantment_destroyed():
    scenario = _board(
        alice_hand=["Fracturing Gust"],
        alice_battlefield=["Sol Ring", "Glorious Anthem", "Grizzly Bears"],
        bob_battlefield=["Ornithopter"],
    )
    _cast(scenario, "Fracturing Gust")
    assert scenario.player("alice").life == 26
    assert "Grizzly Bears" in _battlefield_of(scenario, "alice")


def test_paraselene_gains_one_life_per_enchantment_destroyed():
    scenario = _board(
        alice_hand=["Paraselene"],
        alice_battlefield=["Glorious Anthem", "Ghostly Prison", "Grizzly Bears", "Sol Ring"],
    )
    _cast(scenario, "Paraselene")
    assert scenario.player("alice").life == 22
    assert _battlefield_of(scenario, "alice") == ["Grizzly Bears", "Sol Ring"]


# -- Kaya's Wrath: "the number of creatures you controlled that were destroyed" -


def test_kayas_wrath_counts_only_the_creatures_you_controlled():
    scenario = _board(
        alice_hand=["Kaya's Wrath"],
        alice_battlefield=["Grizzly Bears", "Hill Giant"],
        bob_battlefield=["Serra Angel", "Serra Angel", "Serra Angel"],
    )
    _cast(scenario, "Kaya's Wrath")
    assert _battlefield_of(scenario, "bob") == []
    assert scenario.player("alice").life == 22


# -- Phyrexian Rebirth: "an X/X token, where X is the number destroyed this way"


def test_phyrexian_rebirth_makes_a_token_sized_by_the_creatures_destroyed():
    scenario = _board(
        alice_hand=["Phyrexian Rebirth"],
        alice_battlefield=["Grizzly Bears", "Hill Giant"],
        bob_battlefield=["Serra Angel"],
    )
    _cast(scenario, "Phyrexian Rebirth")
    horror = [s for s in scenario.game.battlefield if s.name == "Phyrexian Horror Token"]
    assert len(horror) == 1
    assert horror[0].controller == "alice"
    characteristics = scenario.game.characteristics_of(horror[0])
    assert (characteristics.power, characteristics.toughness) == (3, 3)


def test_phyrexian_rebirth_counts_only_what_was_destroyed():
    scenario = _board(
        alice_hand=["Phyrexian Rebirth"],
        alice_battlefield=["Grizzly Bears", "Darksteel Myr"],
    )
    _cast(scenario, "Phyrexian Rebirth")
    horror = [s for s in scenario.game.battlefield if s.name == "Phyrexian Horror Token"]
    assert len(horror) == 1
    characteristics = scenario.game.characteristics_of(horror[0])
    assert (characteristics.power, characteristics.toughness) == (1, 1)


# -- Descent of the Dragons / Rampage of the Clans: "its controller creates" ---


def test_descent_of_the_dragons_gives_each_destroyed_creature_s_controller_a_dragon():
    scenario = _board(
        alice_hand=["Descent of the Dragons"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Serra Angel", "Hill Giant"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    _cast(scenario, "Descent of the Dragons", targets=[bears, angel, giant])
    dragons = [s for s in scenario.game.battlefield if s.name == "Dragon Token"]
    assert sorted(s.controller for s in dragons) == ["alice", "bob", "bob"]
    for dragon in dragons:
        characteristics = scenario.game.characteristics_of(dragon)
        assert (characteristics.power, characteristics.toughness) == (4, 4)


def test_descent_of_the_dragons_skips_a_target_that_was_not_destroyed():
    scenario = _board(
        alice_hand=["Descent of the Dragons"],
        alice_battlefield=["Darksteel Myr"],
        bob_battlefield=["Serra Angel"],
    )
    myr = scenario.creature("Darksteel Myr", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, "Descent of the Dragons", targets=[myr, angel])
    dragons = [s for s in scenario.game.battlefield if s.name == "Dragon Token"]
    assert [s.controller for s in dragons] == ["bob"]


def test_descent_of_the_dragons_with_no_targets_does_nothing():
    scenario = _board(alice_hand=["Descent of the Dragons"], bob_battlefield=["Serra Angel"])
    _cast(scenario, "Descent of the Dragons", targets=[])
    assert not [s for s in scenario.game.battlefield if s.name == "Dragon Token"]
    assert "Serra Angel" in _battlefield_of(scenario, "bob")


def test_rampage_of_the_clans_gives_each_destroyed_permanent_s_controller_a_centaur():
    scenario = _board(
        alice_hand=["Rampage of the Clans"],
        alice_battlefield=["Sol Ring", "Glorious Anthem"],
        bob_battlefield=["Ornithopter"],
    )
    _cast(scenario, "Rampage of the Clans")
    centaurs = [s for s in scenario.game.battlefield if s.name == "Centaur Token"]
    assert sorted(s.controller for s in centaurs) == ["alice", "alice", "bob"]
    for centaur in centaurs:
        characteristics = scenario.game.characteristics_of(centaur)
        assert (characteristics.power, characteristics.toughness) == (3, 3)


def _settle(scenario):
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _tokens(scenario, name):
    return sorted(s.controller for s in scenario.game.battlefield if s.name == f"{name} Token")


def _cast_x(scenario, name, x_value, targets=None):
    casting = scenario.cast(name)
    casting.choose_modes([], x_value=x_value)  # X is announced before targets (CR 107.3a)
    casting.choose_targets(targets or [])
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


# -- Terastodon: "For each permanent put into a graveyard this way" ----------


def test_terastodon_gives_each_destroyed_permanent_s_controller_an_elephant():
    scenario = _board(
        alice_hand=["Terastodon"],
        alice_battlefield=["Glorious Anthem"],
        bob_battlefield=["Sol Ring", "Ghostly Prison"],
    )
    targets = [
        scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice"),
        scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob"),
        scenario.find("Ghostly Prison", Zone.BATTLEFIELD, "bob"),
    ]
    scenario.choose_trigger_targets("Terastodon", targets)
    scenario.will_take_the_may(True, source="Terastodon")
    _cast(scenario, "Terastodon")
    _settle(scenario)
    assert _tokens(scenario, "Elephant") == ["alice", "bob", "bob"]


def test_terastodon_declined_destroys_nothing_and_makes_no_elephant():
    scenario = _board(alice_hand=["Terastodon"], bob_battlefield=["Sol Ring"])
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("Terastodon", [sol_ring])
    scenario.will_take_the_may(False, source="Terastodon")
    _cast(scenario, "Terastodon")
    _settle(scenario)
    assert sol_ring.zone is Zone.BATTLEFIELD
    assert _tokens(scenario, "Elephant") == []


def test_terastodon_does_not_count_an_indestructible_target():
    # Darksteel Forge: "Artifacts you control have indestructible", itself included.
    scenario = _board(
        alice_hand=["Terastodon"],
        alice_battlefield=["Sol Ring"],
        bob_battlefield=["Darksteel Forge"],
    )
    targets = [
        scenario.find("Darksteel Forge", Zone.BATTLEFIELD, "bob"),
        scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"),
    ]
    scenario.choose_trigger_targets("Terastodon", targets)
    scenario.will_take_the_may(True, source="Terastodon")
    _cast(scenario, "Terastodon")
    _settle(scenario)
    assert targets[0].zone is Zone.BATTLEFIELD
    assert targets[1].zone is Zone.GRAVEYARD
    assert _tokens(scenario, "Elephant") == ["alice"]


# -- Hour of Need / Curse of the Swine: "For each creature exiled this way" ---


def test_hour_of_need_gives_each_exiled_creature_s_controller_a_sphinx():
    scenario = _board(
        alice_hand=["Hour of Need"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Serra Angel"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, "Hour of Need", targets=[bears, angel])
    assert bears.zone is Zone.EXILE and angel.zone is Zone.EXILE
    assert _tokens(scenario, "Sphinx") == ["alice", "bob"]
    for sphinx in (s for s in scenario.game.battlefield if s.name == "Sphinx Token"):
        characteristics = scenario.game.characteristics_of(sphinx)
        assert (characteristics.power, characteristics.toughness) == (4, 4)


def test_curse_of_the_swine_exiles_x_creatures_and_boars_their_controllers():
    scenario = _board(
        alice_hand=["Curse of the Swine"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Serra Angel", "Hill Giant"],
    )
    targets = [
        scenario.creature("Grizzly Bears", "alice"),
        scenario.creature("Serra Angel", "bob"),
    ]
    _cast_x(scenario, "Curse of the Swine", 2, targets=targets)
    assert all(t.zone is Zone.EXILE for t in targets)
    assert _tokens(scenario, "Boar") == ["alice", "bob"]
    assert "Hill Giant" in _battlefield_of(scenario, "bob")


def test_curse_of_the_swine_with_x_zero_exiles_nothing():
    scenario = _board(alice_hand=["Curse of the Swine"], bob_battlefield=["Serra Angel"])
    _cast_x(scenario, "Curse of the Swine", 0, targets=[])
    assert _tokens(scenario, "Boar") == []
    assert "Serra Angel" in _battlefield_of(scenario, "bob")


# -- Krenko's Buzzcrusher / Sylvan Primordial: per-opponent destroy, then search


def test_krenkos_buzzcrusher_lets_each_land_s_controller_fetch_a_basic():
    scenario = _board(
        alice_hand=["Krenko's Buzzcrusher"],
        alice_battlefield=["Ancient Tomb"],
        bob_battlefield=["Ancient Tomb"],
    )
    mine = scenario.find("Ancient Tomb", Zone.BATTLEFIELD, "alice")
    theirs = scenario.find("Ancient Tomb", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(mine, username="alice", source="Krenko's Buzzcrusher")
    scenario.will_choose_cards(theirs, username="alice", source="Krenko's Buzzcrusher")
    scenario.will_take_the_may(True, username="alice", source="Krenko's Buzzcrusher")
    scenario.will_take_the_may(True, username="bob", source="Krenko's Buzzcrusher")
    _cast(scenario, "Krenko's Buzzcrusher")
    _settle(scenario)
    assert mine.zone is Zone.GRAVEYARD and theirs.zone is Zone.GRAVEYARD
    forests = [
        s for s in scenario.game.battlefield if s.name == "Forest" and s.controller == "alice"
    ]
    islands = [s for s in scenario.game.battlefield if s.name == "Island" and s.controller == "bob"]
    assert len(forests) == 3 and forests[-1].tapped  # two to begin with, one fetched
    assert len(islands) == 1 and islands[0].tapped


def test_krenkos_buzzcrusher_fetches_only_for_a_land_it_destroyed():
    scenario = _board(
        alice_hand=["Krenko's Buzzcrusher"],
        bob_battlefield=["Ancient Tomb"],
    )
    theirs = scenario.find("Ancient Tomb", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(theirs, username="alice", source="Krenko's Buzzcrusher")
    scenario.will_take_the_may(True, username="bob", source="Krenko's Buzzcrusher")
    _cast(scenario, "Krenko's Buzzcrusher")
    _settle(scenario)
    assert theirs.zone is Zone.GRAVEYARD
    assert [s for s in scenario.game.battlefield if s.name == "Island" and s.controller == "bob"]
    assert (
        len(
            [s for s in scenario.game.battlefield if s.name == "Forest" and s.controller == "alice"]
        )
        == 2
    )


def test_sylvan_primordial_fetches_a_forest_per_permanent_destroyed():
    scenario = _board(alice_hand=["Sylvan Primordial"], bob_battlefield=["Sol Ring"])
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("Sylvan Primordial", [sol_ring])
    before = len(
        [s for s in scenario.game.battlefield if s.name == "Forest" and s.controller == "alice"]
    )
    _cast(scenario, "Sylvan Primordial")
    _settle(scenario)
    assert sol_ring.zone is Zone.GRAVEYARD
    forests = [
        s for s in scenario.game.battlefield if s.name == "Forest" and s.controller == "alice"
    ]
    assert len(forests) == before + 1
    assert forests[-1].tapped


def test_sylvan_primordial_fetches_nothing_when_the_target_survives():
    scenario = _board(alice_hand=["Sylvan Primordial"], bob_battlefield=["Darksteel Forge"])
    forge = scenario.find("Darksteel Forge", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("Sylvan Primordial", [forge])
    before = len(
        [s for s in scenario.game.battlefield if s.name == "Forest" and s.controller == "alice"]
    )
    _cast(scenario, "Sylvan Primordial")
    _settle(scenario)
    assert forge.zone is Zone.BATTLEFIELD
    assert (
        len(
            [s for s in scenario.game.battlefield if s.name == "Forest" and s.controller == "alice"]
        )
        == before
    )


# -- Noxious Gearhulk: "If a creature is destroyed this way, ... its toughness" -


def test_noxious_gearhulk_gains_life_equal_to_the_destroyed_creature_s_toughness():
    scenario = _board(alice_hand=["Noxious Gearhulk"], bob_battlefield=["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    scenario.choose_trigger_targets("Noxious Gearhulk", [angel])
    scenario.will_take_the_may(True, source="Noxious Gearhulk")
    _cast(scenario, "Noxious Gearhulk")
    _settle(scenario)
    assert angel.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 24


def test_noxious_gearhulk_reads_the_toughness_the_creature_had_on_the_battlefield():
    scenario = _board(
        alice_hand=["Noxious Gearhulk"], bob_battlefield=["Serra Angel", "Glorious Anthem"]
    )
    angel = scenario.creature("Serra Angel", "bob")
    scenario.choose_trigger_targets("Noxious Gearhulk", [angel])
    scenario.will_take_the_may(True, source="Noxious Gearhulk")
    _cast(scenario, "Noxious Gearhulk")
    _settle(scenario)
    assert scenario.player("alice").life == 25  # 4 + the Anthem's +1


def test_noxious_gearhulk_gains_nothing_when_the_creature_is_indestructible():
    scenario = _board(alice_hand=["Noxious Gearhulk"], bob_battlefield=["Darksteel Myr"])
    myr = scenario.creature("Darksteel Myr", "bob")
    scenario.choose_trigger_targets("Noxious Gearhulk", [myr])
    scenario.will_take_the_may(True, source="Noxious Gearhulk")
    _cast(scenario, "Noxious Gearhulk")
    _settle(scenario)
    assert myr.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20


def test_noxious_gearhulk_declined_gains_nothing():
    scenario = _board(alice_hand=["Noxious Gearhulk"], bob_battlefield=["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    scenario.choose_trigger_targets("Noxious Gearhulk", [angel])
    scenario.will_take_the_may(False, source="Noxious Gearhulk")
    _cast(scenario, "Noxious Gearhulk")
    _settle(scenario)
    assert angel.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20


# -- Midnight Ritual: "For each creature card exiled this way, create a Zombie" -


def test_midnight_ritual_makes_a_zombie_per_creature_card_exiled():
    scenario = _board(
        alice_hand=["Midnight Ritual"],
        alice_graveyard=["Grizzly Bears", "Hill Giant", "Sol Ring"],
    )
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    _cast_x(scenario, "Midnight Ritual", 2, targets=[bears, giant])
    assert bears.zone is Zone.EXILE and giant.zone is Zone.EXILE
    assert _tokens(scenario, "Zombie") == ["alice", "alice"]


def test_midnight_ritual_with_x_zero_makes_no_zombie():
    scenario = _board(alice_hand=["Midnight Ritual"], alice_graveyard=["Grizzly Bears"])
    _cast_x(scenario, "Midnight Ritual", 0, targets=[])
    assert _tokens(scenario, "Zombie") == []


# -- Culmination of Studies: per-quality payoffs off the exiled top cards ------


def test_culmination_of_studies_pays_off_each_exiled_land_blue_and_red_card():
    scenario = _board(
        alice_hand=["Culmination of Studies"],
        alice_library=(
            "Island",
            "Counterspell",
            "Lightning Bolt",
            "Mountain",
            "Grizzly Bears",
            "Forest",
            "Forest",
        ),
    )
    hand_before = len(scenario.player("alice").hand)
    _cast_x(scenario, "Culmination of Studies", 4)
    treasures = [s for s in scenario.game.battlefield if s.name == "Treasure Token"]
    assert len(treasures) == 2  # Island, Mountain
    assert scenario.player("bob").life == 19  # Lightning Bolt is the one red card
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1  # Counterspell is blue
    assert [c.name for c in scenario.game.exile if c.owner == "alice"].count("Counterspell") == 1


def test_culmination_of_studies_with_an_empty_library_pays_nothing():
    scenario = _board(alice_hand=["Culmination of Studies"], alice_library=())
    _cast_x(scenario, "Culmination of Studies", 3)
    assert not [s for s in scenario.game.battlefield if s.name == "Treasure Token"]
    assert scenario.player("bob").life == 20


# -- Faerie Slumber Party: "For each opponent who controlled a creature returned"


def _three_player_board(carol=("Swamp",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Faerie Slumber Party"],
            battlefield=[
                "Island",
                "Island",
                "Island",
                "Island",
                "Island",
                "Island",
                "Grizzly Bears",
            ],
            library=["Forest"] * 6,
        )
        .player("bob", battlefield=["Serra Angel", "Hill Giant"], library=["Island"] * 6)
        .player("carol", battlefield=list(carol), library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_faerie_slumber_party_makes_two_faeries_per_opponent_who_lost_a_creature():
    scenario = _three_player_board()
    scenario.cast_and_resolve("Faerie Slumber Party", username="alice", auto=True)
    assert _tokens(scenario, "Faerie") == [
        "alice",
        "alice",
    ]  # bob only, once, whatever he controlled
    assert {c.name for c in scenario.player("bob").hand} == {"Serra Angel", "Hill Giant"}
    assert [c.name for c in scenario.player("alice").hand] == ["Grizzly Bears"]


def test_faerie_slumber_party_counts_each_opponent_once_and_not_a_player_without_creatures():
    scenario = _three_player_board(carol=("Swamp", "Hill Giant"))
    scenario.cast_and_resolve("Faerie Slumber Party", username="alice", auto=True)
    assert _tokens(scenario, "Faerie") == ["alice"] * 4


def test_faerie_slumber_party_with_only_my_creatures_makes_no_faerie():
    scenario = _board(alice_hand=["Faerie Slumber Party"], alice_battlefield=["Grizzly Bears"])
    scenario.cast_and_resolve("Faerie Slumber Party", username="alice", auto=True)
    assert _tokens(scenario, "Faerie") == []


# -- Paradoxical Outcome: "Draw a card for each card returned to your hand" -----


def test_paradoxical_outcome_draws_a_card_per_permanent_returned():
    scenario = _board(
        alice_hand=["Paradoxical Outcome"],
        alice_battlefield=["Grizzly Bears", "Hill Giant", "Sol Ring"],
        alice_library=("Forest", "Forest", "Forest", "Forest"),
    )
    targets = [
        scenario.creature("Grizzly Bears", "alice"),
        scenario.creature("Hill Giant", "alice"),
        scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice"),
    ]
    _cast(scenario, "Paradoxical Outcome", targets=targets)
    names = sorted(c.name for c in scenario.player("alice").hand)
    assert names == ["Forest", "Forest", "Forest", "Grizzly Bears", "Hill Giant", "Sol Ring"]


def test_paradoxical_outcome_with_no_targets_draws_nothing():
    scenario = _board(alice_hand=["Paradoxical Outcome"], alice_battlefield=["Grizzly Bears"])
    _cast(scenario, "Paradoxical Outcome", targets=[])
    assert scenario.player("alice").hand == []


# -- Morgue Burst: "damage ... equal to the power of the card returned this way"


def test_morgue_burst_deals_damage_equal_to_the_power_of_the_returned_card():
    scenario = _board(alice_hand=["Morgue Burst"], alice_graveyard=["Serra Angel"])
    angel = scenario.find("Serra Angel", Zone.GRAVEYARD, "alice")
    _cast(scenario, "Morgue Burst", targets=[angel, "bob"])
    assert angel.zone is Zone.HAND
    assert scenario.player("bob").life == 16


def test_morgue_burst_can_hit_a_creature():
    scenario = _board(
        alice_hand=["Morgue Burst"],
        alice_graveyard=["Hill Giant"],
        bob_battlefield=["Grizzly Bears"],
    )
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast(scenario, "Morgue Burst", targets=[giant, bears])
    assert bears.zone is Zone.GRAVEYARD  # Hill Giant has power 3


# -- Skull Raid: "If fewer than two cards were discarded this way, ... difference"


def _skull_raid(bob_hand):
    scenario = _board(
        alice_hand=["Skull Raid"],
        bob_hand=bob_hand,
        alice_library=("Forest",) * 4,
    )
    return scenario


def test_skull_raid_draws_the_shortfall_when_the_opponent_has_one_card():
    scenario = _skull_raid(["Island"])
    _cast(scenario, "Skull Raid", targets=["bob"])
    assert scenario.player("bob").hand == []
    assert [c.name for c in scenario.player("alice").hand] == ["Forest"]


def test_skull_raid_draws_two_when_the_opponent_has_no_cards():
    scenario = _skull_raid([])
    _cast(scenario, "Skull Raid", targets=["bob"])
    assert [c.name for c in scenario.player("alice").hand] == ["Forest", "Forest"]


def test_skull_raid_draws_nothing_when_two_were_discarded():
    scenario = _skull_raid(["Island", "Island", "Island"])
    _cast(scenario, "Skull Raid", targets=["bob"])
    assert len(scenario.player("bob").hand) == 1
    assert scenario.player("alice").hand == []


# -- Jace's Archivist: "the greatest number of cards a player discarded" -------


def test_jaces_archivist_has_every_player_draw_the_greatest_discard_count():
    scenario = _board(
        alice_hand=["Opt", "Opt"],
        alice_battlefield=["Jace's Archivist"],
        alice_library=("Forest",) * 8,
        bob_hand=["Shock"] * 4,
        bob_library=("Island",) * 8,
    )
    archivist = scenario.creature("Jace's Archivist", "alice")
    island = scenario.untapped_sources("Island", username="alice")[0]
    scenario.activate(archivist, island)
    scenario.pass_until_resolved()
    assert sorted(c.name for c in scenario.player("alice").hand) == ["Forest"] * 4
    assert sorted(c.name for c in scenario.player("bob").hand) == ["Island"] * 4


def test_jaces_archivist_with_empty_hands_draws_nothing():
    scenario = _board(alice_battlefield=["Jace's Archivist"])
    archivist = scenario.creature("Jace's Archivist", "alice")
    island = scenario.untapped_sources("Island", username="alice")[0]
    scenario.activate(archivist, island)
    scenario.pass_until_resolved()
    assert scenario.player("alice").hand == []
    assert scenario.player("bob").hand == []


# -- Coerced Confession / Dread Summons / Liliana's Indignation: milled cards --


def test_coerced_confession_draws_a_card_per_creature_card_milled_from_their_library():
    scenario = _board(
        alice_hand=["Coerced Confession"],
        bob_library=("Grizzly Bears", "Island", "Hill Giant", "Serra Angel", "Island", "Island"),
    )
    _cast(scenario, "Coerced Confession", targets=["bob"])
    assert [c.name for c in scenario.player("bob").graveyard].count("Island") == 1
    assert len(scenario.player("bob").graveyard) == 4
    assert [c.name for c in scenario.player("alice").hand] == ["Forest"] * 3


def test_coerced_confession_on_myself_counts_my_own_milled_creatures():
    scenario = _board(
        alice_hand=["Coerced Confession"],
        alice_library=("Grizzly Bears", "Island", "Island", "Hill Giant", "Forest", "Forest"),
    )
    _cast(scenario, "Coerced Confession", targets=["alice"])
    assert len(scenario.player("alice").graveyard) == 4 + 1  # four milled + the spell
    assert sorted(c.name for c in scenario.player("alice").hand) == ["Forest", "Forest"]


def test_coerced_confession_with_no_creature_card_milled_draws_nothing():
    scenario = _board(alice_hand=["Coerced Confession"], bob_library=("Island",) * 6)
    _cast(scenario, "Coerced Confession", targets=["bob"])
    assert scenario.player("alice").hand == []


def test_dread_summons_makes_a_tapped_zombie_per_creature_card_milled_by_anyone():
    scenario = _board(
        alice_hand=["Dread Summons"],
        alice_library=("Grizzly Bears", "Island", "Hill Giant", "Forest"),
        bob_library=("Serra Angel", "Island", "Island", "Island"),
    )
    _cast_x(scenario, "Dread Summons", 3)
    zombies = [s for s in scenario.game.battlefield if s.name == "Zombie Token"]
    assert sorted(z.controller for z in zombies) == ["alice", "alice", "alice"]
    assert all(z.tapped for z in zombies)


def test_dread_summons_only_counts_what_actually_reached_a_graveyard():
    scenario = _board(
        alice_hand=["Dread Summons"],
        alice_library=("Grizzly Bears",),
        bob_library=(),
    )
    _cast_x(scenario, "Dread Summons", 3)
    assert _tokens(scenario, "Zombie") == ["alice"]


def test_lilianas_indignation_drains_two_per_creature_card_milled_from_my_library():
    scenario = _board(
        alice_hand=["Liliana's Indignation"],
        alice_library=("Grizzly Bears", "Island", "Hill Giant", "Serra Angel", "Forest"),
    )
    _cast_x(scenario, "Liliana's Indignation", 3, targets=["bob"])
    assert scenario.player("bob").life == 16  # Bears and Hill Giant: 2 creatures x 2


def test_lilianas_indignation_can_target_myself():
    scenario = _board(
        alice_hand=["Liliana's Indignation"],
        alice_library=("Grizzly Bears", "Hill Giant", "Forest"),
    )
    _cast_x(scenario, "Liliana's Indignation", 2, targets=["alice"])
    assert scenario.player("alice").life == 16


# -- Patient Rebuilding: "you draw a card for each land card put into their graveyard"


def test_patient_rebuilding_draws_a_card_per_land_card_it_milled_from_the_opponent():
    scenario = _board(
        alice_battlefield=["Patient Rebuilding"],
        bob_library=("Island", "Grizzly Bears", "Swamp", "Island", "Island"),
        manual=True,
    )
    _alice_upkeep(scenario)
    scenario.choose_trigger_targets("Patient Rebuilding", ["bob"])
    _settle(scenario)
    assert len(scenario.player("bob").graveyard) == 3
    # Island, Swamp milled with the Bears: two land cards.
    assert [c.name for c in scenario.player("alice").hand] == ["Forest"] * 2


def test_patient_rebuilding_counts_nothing_when_no_land_was_milled():
    scenario = _board(
        alice_battlefield=["Patient Rebuilding"],
        bob_library=("Grizzly Bears", "Hill Giant", "Serra Angel", "Island"),
        manual=True,
    )
    _alice_upkeep(scenario)
    scenario.choose_trigger_targets("Patient Rebuilding", ["bob"])
    _settle(scenario)
    assert scenario.player("alice").hand == []


# -- Froghemoth: exile up to that many target cards, then count by quality -----


def test_froghemoth_counts_exiled_creature_cards_for_counters_and_the_rest_for_life():
    scenario = _board(
        alice_battlefield=["Froghemoth"],
        bob_graveyard=["Grizzly Bears", "Hill Giant", "Sol Ring", "Opt"],
        start=Step.DECLARE_ATTACKERS,
    )
    froghemoth = scenario.creature("Froghemoth", "alice")
    graveyard = list(scenario.player("bob").graveyard)
    scenario.attack_with(froghemoth)
    scenario.no_blocks()
    scenario.will_choose_targets(*graveyard, source="Froghemoth")
    scenario.combat_damage()
    _settle(scenario)
    assert all(card.zone is Zone.EXILE for card in graveyard)
    assert froghemoth.counters["+1/+1"] == 2  # Bears and Hill Giant
    assert scenario.player("alice").life == 22  # Sol Ring and Opt


def test_froghemoth_exiling_fewer_cards_counts_only_those():
    scenario = _board(
        alice_battlefield=["Froghemoth"],
        bob_graveyard=["Grizzly Bears", "Sol Ring"],
        start=Step.DECLARE_ATTACKERS,
    )
    froghemoth = scenario.creature("Froghemoth", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    scenario.attack_with(froghemoth)
    scenario.no_blocks()
    scenario.will_choose_targets(bears, source="Froghemoth")
    scenario.combat_damage()
    _settle(scenario)
    assert froghemoth.counters["+1/+1"] == 1
    assert scenario.player("alice").life == 20


# -- Proof printings: not listed, not in an api deck, legal in Modern ----------
#
# Gorging Vulture (Pioneer, Modern): "mill four cards. You gain 1 life for each
#   creature card milled this way."
# Voracious Fell Beast (Modern): "each opponent sacrifices a creature ... Create
#   a Food token for each creature sacrificed this way."
# Crypt Incursion (Pioneer, Modern): "Exile all creature cards from target
#   player's graveyard. You gain 3 life for each card exiled this way."
# Necromancer's Covenant (Modern): "exile all creature cards from target
#   player's graveyard, then create a 2/2 black Zombie creature token for each
#   card exiled this way."

PROOFS = ["Gorging Vulture", "Voracious Fell Beast", "Crypt Incursion", "Necromancer's Covenant"]


@pytest.mark.parametrize("name", PROOFS)
def test_every_proof_printing_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def test_gorging_vulture_gains_life_for_each_creature_card_it_milled():
    scenario = _board(
        alice_hand=["Gorging Vulture"],
        alice_library=("Grizzly Bears", "Island", "Hill Giant", "Serra Angel", "Forest"),
    )
    _cast(scenario, "Gorging Vulture")
    _settle(scenario)
    assert len(scenario.player("alice").graveyard) == 4
    assert scenario.player("alice").life == 23


def test_gorging_vulture_with_a_short_library_counts_only_what_was_milled():
    scenario = _board(alice_hand=["Gorging Vulture"], alice_library=("Grizzly Bears", "Island"))
    _cast(scenario, "Gorging Vulture")
    _settle(scenario)
    assert scenario.player("alice").life == 21


def test_voracious_fell_beast_makes_a_food_per_creature_the_opponent_sacrificed():
    scenario = _board(
        alice_hand=["Voracious Fell Beast"],
        bob_battlefield=["Grizzly Bears", "Hill Giant"],
    )
    scenario.will_choose_cards(
        scenario.creature("Grizzly Bears", "bob"), username="bob", source="Voracious Fell Beast"
    )
    _cast(scenario, "Voracious Fell Beast")
    _settle(scenario)
    assert _tokens(scenario, "Food") == ["alice"]


def test_voracious_fell_beast_makes_no_food_when_the_opponent_has_no_creature():
    scenario = _board(alice_hand=["Voracious Fell Beast"])
    _cast(scenario, "Voracious Fell Beast")
    _settle(scenario)
    assert _tokens(scenario, "Food") == []


def test_crypt_incursion_gains_three_life_per_creature_card_exiled():
    scenario = _board(
        alice_hand=["Crypt Incursion"],
        bob_graveyard=["Grizzly Bears", "Island", "Hill Giant"],
    )
    _cast(scenario, "Crypt Incursion", targets=["bob"])
    assert [c.name for c in scenario.player("bob").graveyard] == ["Island"]
    assert scenario.player("alice").life == 26


def test_crypt_incursion_on_an_empty_graveyard_gains_nothing():
    scenario = _board(alice_hand=["Crypt Incursion"], bob_graveyard=["Island"])
    _cast(scenario, "Crypt Incursion", targets=["bob"])
    assert scenario.player("alice").life == 20


def test_necromancers_covenant_makes_a_zombie_per_card_exiled_from_the_graveyard():
    scenario = _board(
        alice_hand=["Necromancer's Covenant"],
        alice_lands=("Plains", "Swamp", "Swamp", "Swamp"),
        bob_graveyard=["Grizzly Bears", "Hill Giant", "Island"],
    )
    scenario.choose_trigger_targets("Necromancer's Covenant", ["bob"])
    _cast(scenario, "Necromancer's Covenant")
    _settle(scenario)
    assert _tokens(scenario, "Zombie") == ["alice", "alice"]
