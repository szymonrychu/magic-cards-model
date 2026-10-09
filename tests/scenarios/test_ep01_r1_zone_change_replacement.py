"""EP-01 round 1, task 6: zone-change replacement statics (CR 614.1a, 614.6).

Every shape is raised through the engine's single graveyard choke point
(`Game.put_into_graveyard`, reached by a real destroy, a real discard, a real
mill) and asserted by where the card ends up; every shape has the negative
(a card or controller it must NOT reach).

- CR 614.1a: "instead" effects are replacement effects.
- CR 614.6: a replaced event never happens - a creature exiled instead of dying
  never "dies" (CR 700.4).
- CR 701.24c: shuffling a card into a library shuffles even when it is elsewhere.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import TargetKind, TargetRef, Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice, bob, *, hand=None, bob_hand=None, library=None, bob_library=None, graveyard=None):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=alice,
            hand=hand or [],
            library=library if library is not None else ["Island"] * 5,
            graveyard=graveyard or [],
        )
        .player(
            "bob",
            battlefield=bob,
            hand=bob_hand or [],
            library=bob_library if bob_library is not None else ["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _every_static_clause_handled(name, containing="would"):
    outcomes = [o for o in classify_clauses(card(name)) if containing in o.text]
    assert outcomes
    assert {o.category for o in outcomes} == {HANDLED}, outcomes


# -- "If ~ would be put into a graveyard from anywhere, reveal ~ and shuffle it
#    into its owner's library instead." (Blightsteel Colossus, Progenitus) ----


@pytest.mark.parametrize("name", ["Blightsteel Colossus", "Progenitus"])
def test_shuffle_self_when_destroyed_on_the_battlefield(name):
    scenario = _board([name], [])
    colossus = scenario.creature(name, "alice")

    scenario.game.sacrifice(colossus)  # Blightsteel is indestructible

    assert colossus.zone is Zone.LIBRARY
    assert colossus in scenario.player("alice").library
    assert colossus not in scenario.player("alice").graveyard


@pytest.mark.parametrize("name", ["Blightsteel Colossus", "Progenitus"])
def test_shuffle_self_when_discarded_from_hand(name):
    scenario = _board([], [], hand=[name])
    colossus = scenario.find(name, Zone.HAND, "alice")

    scenario.game.put_into_graveyard(colossus)

    assert colossus.zone is Zone.LIBRARY
    assert scenario.player("alice").graveyard == []


def test_shuffle_self_when_milled_from_the_library():
    scenario = _board([], [], library=["Blightsteel Colossus", "Island"])
    colossus = scenario.player("alice").library[0]

    scenario.game.put_into_graveyard(colossus)

    assert colossus.zone is Zone.LIBRARY


def test_shuffle_self_goes_to_its_owners_library_not_the_controllers():
    scenario = _board([], ["Blightsteel Colossus"])
    colossus = scenario.creature("Blightsteel Colossus", "bob")
    scenario.game.sacrifice(colossus)
    assert colossus in scenario.player("bob").library


def test_shuffle_self_negative_other_cards_still_reach_the_graveyard():
    scenario = _board(["Blightsteel Colossus", "Grizzly Bears"], [])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)

    assert bears.zone is Zone.GRAVEYARD


@pytest.mark.parametrize("name", ["Blightsteel Colossus", "Progenitus", "Legacy Weapon"])
def test_shuffle_self_line_is_handled(name):
    _every_static_clause_handled(name)


# -- "If ~ would die, <exile it with counters | put it on the bottom>" -------


def test_darigaaz_dying_is_exiled_with_three_egg_counters():
    scenario = _board(["Darigaaz Reincarnated"], [])
    darigaaz = scenario.creature("Darigaaz Reincarnated", "alice")

    scenario.game.destroy(darigaaz)

    assert darigaaz.zone is Zone.EXILE
    assert darigaaz.counter_count("egg") == 3


def test_darigaaz_only_dies_from_the_battlefield():
    """A discard from hand is not "dies" (CR 700.4): it reaches the graveyard."""
    scenario = _board([], [], hand=["Darigaaz Reincarnated"])
    darigaaz = scenario.find("Darigaaz Reincarnated", Zone.HAND, "alice")

    scenario.game.put_into_graveyard(darigaaz)

    assert darigaaz.zone is Zone.GRAVEYARD
    assert darigaaz.counter_count("egg") == 0


def test_nissas_chosen_goes_to_the_bottom_of_its_owners_library():
    scenario = _board(["Nissa's Chosen"], [], library=["Island", "Forest"])
    chosen = scenario.creature("Nissa's Chosen", "alice")

    scenario.game.destroy(chosen)

    assert chosen.zone is Zone.LIBRARY
    assert scenario.player("alice").library[-1] is chosen
    assert scenario.player("alice").graveyard == []


def test_nissas_chosen_milled_from_the_library_is_not_dying():
    scenario = _board([], [], library=["Nissa's Chosen", "Island"])
    chosen = scenario.player("alice").library[0]

    scenario.game.put_into_graveyard(chosen)

    assert chosen.zone is Zone.GRAVEYARD


# -- "If a nontoken creature an opponent controls would die, exile it ..." ---


def test_kalitas_exiles_the_opponents_creature_and_makes_a_zombie():
    scenario = _board(["Kalitas, Traitor of Ghet"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(bears)

    assert bears.zone is Zone.EXILE
    zombies = [c for c in scenario.game.battlefield if c.name == "Zombie Token"]
    assert len(zombies) == 1
    assert zombies[0].controller == "alice"


def test_kalitas_negative_own_creature_and_tokens_still_die():
    scenario = _board(["Kalitas, Traitor of Ghet", "Grizzly Bears"], ["Grizzly Bears"])
    mine = scenario.creatures("Grizzly Bears", username="alice")[0]

    scenario.game.destroy(mine)

    assert mine.zone is Zone.GRAVEYARD
    assert [c for c in scenario.game.battlefield if c.name == "Zombie Token"] == []


def test_kalitas_and_the_crystal_do_not_both_apply_to_one_death():
    """CR 614.5/616.1: the first chosen effect exiles it, so the other one's
    "would die" no longer matches - one rider, never both."""
    scenario = _board(["Kalitas, Traitor of Ghet", "The Darkness Crystal"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    life = scenario.player("alice").life

    scenario.game.destroy(bears)

    zombies = len([c for c in scenario.game.battlefield if c.name == "Zombie Token"])
    gained = scenario.player("alice").life - life
    assert bears.zone is Zone.EXILE
    assert (zombies, gained) in {(1, 0), (0, 2)}


def test_darkness_crystal_exiles_and_gains_two_life():
    scenario = _board(["The Darkness Crystal"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    before = scenario.player("alice").life

    scenario.game.destroy(bears)

    assert bears.zone is Zone.EXILE
    assert scenario.player("alice").life == before + 2


def test_darkness_crystal_gains_nothing_for_your_own_creature():
    scenario = _board(["The Darkness Crystal", "Grizzly Bears"], [])
    mine = scenario.creature("Grizzly Bears", "alice")
    before = scenario.player("alice").life

    scenario.game.destroy(mine)

    assert mine.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == before


@pytest.mark.parametrize("name", ["Kalitas, Traitor of Ghet", "The Darkness Crystal"])
def test_nontoken_opponent_creature_lines_are_handled(name):
    _every_static_clause_handled(name)


# -- the group zone-change shapes ---------------------------------------------


def test_void_maw_exiles_any_other_creature_but_not_itself():
    scenario = _board(["Void Maw", "Grizzly Bears"], ["Grizzly Bears"])
    mine = scenario.creatures("Grizzly Bears", username="alice")[0]
    theirs = scenario.creature("Grizzly Bears", "bob")
    maw = scenario.creature("Void Maw", "alice")

    scenario.game.destroy(mine)
    scenario.game.destroy(theirs)
    scenario.game.destroy(maw)

    assert (mine.zone, theirs.zone) == (Zone.EXILE, Zone.EXILE)
    assert maw.zone is Zone.GRAVEYARD  # "another": never itself


def test_samurai_exiles_a_permanent_but_not_a_spell():
    scenario = _board(["Samurai of the Pale Curtain", "Grizzly Bears"], [], hand=["Lightning Bolt"])
    bears = scenario.creatures("Grizzly Bears", username="alice")[0]
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    scenario.game.destroy(bears)
    scenario.game.put_into_graveyard(bolt)

    assert bears.zone is Zone.EXILE
    assert bolt.zone is Zone.GRAVEYARD


def test_dryad_militant_exiles_instants_and_sorceries_only():
    scenario = _board(
        ["Dryad Militant", "Grizzly Bears"], [], hand=["Lightning Bolt", "Grizzly Bears"]
    )
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    bears_card = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    scenario.game.put_into_graveyard(bolt)
    scenario.game.put_into_graveyard(bears_card)

    assert bolt.zone is Zone.EXILE
    assert bears_card.zone is Zone.GRAVEYARD


def test_anafenza_exiles_opponent_owned_creatures_dying_or_milled_only():
    scenario = _board(
        ["Anafenza, the Foremost", "Grizzly Bears"],
        ["Grizzly Bears"],
        bob_library=["Grizzly Bears", "Lightning Bolt"],
    )
    mine = scenario.creatures("Grizzly Bears", username="alice")[0]
    theirs = scenario.creature("Grizzly Bears", "bob")
    milled_creature, milled_spell = scenario.player("bob").library[:2]

    scenario.game.destroy(mine)
    scenario.game.destroy(theirs)
    scenario.game.put_into_graveyard(milled_creature)
    scenario.game.put_into_graveyard(milled_spell)

    assert mine.zone is Zone.GRAVEYARD
    assert theirs.zone is Zone.EXILE
    assert milled_creature.zone is Zone.EXILE
    assert milled_spell.zone is Zone.GRAVEYARD  # not a creature card


def test_valgavoth_exiles_cards_you_did_not_control_going_to_an_opponents_graveyard():
    scenario = _board(
        ["Valgavoth, Terror Eater", "Grizzly Bears"], ["Grizzly Bears"], bob_hand=["Lightning Bolt"]
    )
    mine = scenario.creatures("Grizzly Bears", username="alice")[0]
    theirs = scenario.creature("Grizzly Bears", "bob")
    discarded = scenario.find("Lightning Bolt", Zone.HAND, "bob")

    scenario.game.destroy(mine)
    scenario.game.destroy(theirs)
    scenario.game.put_into_graveyard(discarded)

    assert mine.zone is Zone.GRAVEYARD  # my own graveyard, and I controlled it
    assert theirs.zone is Zone.EXILE
    assert discarded.zone is Zone.EXILE


def test_draugr_necromancer_exiles_with_an_ice_counter():
    scenario = _board(["Draugr Necromancer"], ["Grizzly Bears"])
    theirs = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(theirs)

    assert theirs.zone is Zone.EXILE
    assert theirs.counter_count("ice") == 1


def test_wheel_of_sun_and_moon_bottoms_the_enchanted_players_cards_only():
    scenario = _board(["Grizzly Bears"], ["Grizzly Bears"], hand=["Wheel of Sun and Moon"])
    aura = scenario.put_onto_battlefield("Wheel of Sun and Moon", "alice")
    aura.attachment = TargetRef(kind=TargetKind.PLAYER, username="bob")
    theirs = scenario.creature("Grizzly Bears", "bob")
    mine = scenario.creatures("Grizzly Bears", username="alice")[0]

    scenario.game.destroy(theirs)
    scenario.game.destroy(mine)

    assert theirs.zone is Zone.LIBRARY
    assert scenario.player("bob").library[-1] is theirs
    assert mine.zone is Zone.GRAVEYARD


def test_beloved_beggar_back_face_is_exiled_but_the_front_face_is_not():
    scenario = _board(["Beloved Beggar"], [])
    beggar = scenario.creature("Beloved Beggar", "alice")
    scenario.game.put_into_graveyard(beggar)
    assert beggar.zone is Zone.GRAVEYARD  # front face: no such line

    scenario = _board(["Beloved Beggar"], [])
    soul = scenario.creature("Beloved Beggar", "alice")
    soul.transform()
    scenario.game.put_into_graveyard(soul)
    assert soul.zone is Zone.EXILE


@pytest.mark.parametrize(
    "name",
    [
        "Void Maw",
        "Samurai of the Pale Curtain",
        "Dryad Militant",
        "Anafenza, the Foremost",
        "Valgavoth, Terror Eater",
        "Draugr Necromancer",
        "Wheel of Sun and Moon",
        "Nissa's Chosen",
        "Darigaaz Reincarnated",
        "Beloved Beggar // Generous Soul",
    ],
)
def test_group_zone_change_lines_are_handled(name):
    _every_static_clause_handled(name)


# -- "a creature dealt damage by <source> this turn would die" ----------------


def test_frostwielder_exiles_what_it_damaged_when_it_dies_later_this_turn():
    scenario = _board(["Frostwielder"], ["Colossal Dreadmaw"])
    wielder = scenario.creature("Frostwielder", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.game.deal_damage(dreadmaw, 1, source=wielder)
    scenario.game.destroy(dreadmaw)

    assert dreadmaw.zone is Zone.EXILE


def test_frostwielder_negative_creature_it_did_not_damage_just_dies():
    scenario = _board(["Frostwielder"], ["Colossal Dreadmaw", "Grizzly Bears"])
    wielder = scenario.creature("Frostwielder", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.deal_damage(dreadmaw, 1, source=wielder)
    scenario.game.destroy(bears)

    assert bears.zone is Zone.GRAVEYARD


def test_frostwielder_ledger_ends_with_the_turn():
    scenario = _board(["Frostwielder"], ["Colossal Dreadmaw"])
    wielder = scenario.creature("Frostwielder", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.game.deal_damage(dreadmaw, 1, source=wielder)

    turn = scenario.game.turn.turns_taken
    while scenario.game.turn.turns_taken == turn:
        scenario.advance()
    scenario.game.destroy(dreadmaw)

    assert dreadmaw.zone is Zone.GRAVEYARD


def test_kumano_faces_kakkazan_exiles_what_any_source_you_control_damaged():
    scenario = _board(["Kumano Faces Kakkazan", "Frostwielder"], ["Colossal Dreadmaw"])
    etching = next(c for c in scenario.game.battlefield if c.name.startswith("Kumano Faces"))
    etching.transform()  # the creature face prints the static line
    wielder = scenario.creature("Frostwielder", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.game.deal_damage(dreadmaw, 1, source=wielder)
    scenario.game.destroy(dreadmaw)

    assert dreadmaw.zone is Zone.EXILE


def _pests(scenario):
    return [c for c in scenario.game.battlefield if c.name == "Pest Token"]


def test_valentin_exiles_and_a_paid_reflexive_ability_makes_a_pest():
    scenario = _board(["Valentin, Dean of the Vein", "Swamp", "Swamp"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.will_pay_the_mana_cost(True, username="alice")
    scenario.game.destroy(bears)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    assert len(_pests(scenario)) == 1


def test_valentin_unpaid_makes_no_pest():
    scenario = _board(["Valentin, Dean of the Vein", "Swamp", "Swamp"], ["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.will_pay_the_mana_cost(False, username="alice")
    scenario.game.destroy(bears)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    assert _pests(scenario) == []


def test_valentin_own_creature_dying_creates_no_reflexive_ability():
    scenario = _board(["Valentin, Dean of the Vein", "Grizzly Bears"], [])
    mine = scenario.creatures("Grizzly Bears", username="alice")[0]

    scenario.game.destroy(mine)

    assert mine.zone is Zone.GRAVEYARD
    assert scenario.pending_triggers == []


@pytest.mark.parametrize(
    "name",
    [
        "Frostwielder",
        "Kumano Faces Kakkazan // Etching of Kumano",
        "Valentin, Dean of the Vein // Lisette, Dean of the Root",
    ],
)
def test_damage_ledger_and_reflexive_lines_are_handled(name):
    _every_static_clause_handled(name)
