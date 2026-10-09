"""EP-01 round 1, task 6: draw replacement statics (CR 614.1a, 614.11, 121.6).

Every shape is raised through a real `Game.draw_cards` (the single draw choke
point, one event per individual draw, CR 121.2) and asserted by what ended up
in hand / library / graveyard / exile; every shape has the negative (a
condition that is false, a player the effect does not name).

- CR 614.11 / 121.6a: a draw replacement applies even when the library is empty.
- CR 614.5: an effect gets one opportunity per event - "otherwise, draw a card"
  inside a replacement is the original draw, not a second replaceable one.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice, bob=(), *, hand=(), library=("Island",) * 6, bob_library=("Island",) * 6, bob_hand=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice), hand=list(hand), library=list(library))
        .player("bob", battlefield=list(bob), hand=list(bob_hand), library=list(bob_library))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _draw(scenario, who="alice", count=1):
    return scenario.game.draw_cards(who, count)


def _names(cards):
    return [c.name for c in cards]


def _handled(name, containing="draw"):
    outcomes = [o for o in classify_clauses(card(name)) if containing in o.text]
    assert outcomes
    assert {o.category for o in outcomes} == {HANDLED}, outcomes


# -- "while <condition>" -------------------------------------------------------


def test_blood_scrivener_with_an_empty_hand_draws_two_and_loses_a_life():
    scenario = _board(["Blood Scrivener"], library=["Island", "Forest", "Swamp"])

    _draw(scenario)

    assert _names(scenario.player("alice").hand) == ["Island", "Forest"]
    assert scenario.player("alice").life == 19


def test_blood_scrivener_with_cards_in_hand_draws_normally():
    scenario = _board(["Blood Scrivener"], hand=["Mountain"], library=["Island", "Forest"])

    _draw(scenario)

    assert _names(scenario.player("alice").hand) == ["Mountain", "Island"]
    assert scenario.player("alice").life == 20


def test_phial_of_galadriel_draws_two_with_an_empty_hand_only():
    scenario = _board(["Phial of Galadriel"], library=["Island", "Forest", "Swamp"])
    _draw(scenario)
    assert len(scenario.player("alice").hand) == 2
    assert scenario.player("alice").life == 20  # no life loss on the Phial

    _draw(scenario)  # hand is no longer empty
    assert len(scenario.player("alice").hand) == 3


@pytest.mark.parametrize("name", ["Laboratory Maniac", "Jace, Wielder of Mysteries"])
def test_empty_library_draw_wins_the_game(name):
    scenario = _board([name], library=[])

    _draw(scenario)

    assert scenario.game.is_over
    assert scenario.game.winner == "alice"


def test_laboratory_maniac_with_cards_left_just_draws():
    scenario = _board(["Laboratory Maniac"], library=["Island"])

    _draw(scenario)

    assert not scenario.game.is_over
    assert _names(scenario.player("alice").hand) == ["Island"]


def test_laboratory_maniac_does_not_help_the_opponent():
    scenario = _board(["Laboratory Maniac"], bob_library=[])

    _draw(scenario, "bob")

    assert scenario.game.winner != "alice"


def test_living_conundrum_skips_the_empty_library_draw():
    scenario = _board(["Living Conundrum"], library=[])

    _draw(scenario)
    scenario.state_based_actions()

    assert not scenario.game.is_over  # no failed draw (CR 704.5b)
    assert scenario.player("alice").hand == []


# -- "If you would draw a card, instead <look / reveal / exile ...>" --------


def test_sages_of_the_anima_reveals_three_creatures_to_hand_rest_to_the_bottom():
    scenario = _board(
        ["Sages of the Anima"],
        library=["Grizzly Bears", "Island", "Llanowar Elves", "Forest", "Swamp"],
    )

    _draw(scenario)

    alice = scenario.player("alice")
    assert sorted(_names(alice.hand)) == ["Grizzly Bears", "Llanowar Elves"]
    assert _names(alice.library) == ["Forest", "Swamp", "Island"]  # Island bottomed


def test_sages_negative_the_opponents_draw_is_untouched():
    scenario = _board(["Sages of the Anima"], bob_library=["Grizzly Bears", "Island", "Forest"])

    _draw(scenario, "bob")

    assert _names(scenario.player("bob").hand) == ["Grizzly Bears"]


def test_underrealm_lich_one_to_hand_the_rest_to_the_graveyard():
    scenario = _board(
        ["Underrealm Lich"], library=["Grizzly Bears", "Island", "Llanowar Elves", "Forest"]
    )
    top = scenario.player("alice").library[:3]

    _draw(scenario)

    alice = scenario.player("alice")
    assert len(alice.hand) == 1 and alice.hand[0] in top
    assert sorted(c.id for c in alice.graveyard) == sorted(c.id for c in top if c not in alice.hand)
    assert _names(alice.library) == ["Forest"]


def test_tomorrow_azamis_familiar_one_to_hand_the_rest_to_the_bottom():
    scenario = _board(
        ["Tomorrow, Azami's Familiar"], library=["Grizzly Bears", "Island", "Llanowar Elves", "Forest"]
    )
    top = scenario.player("alice").library[:3]

    _draw(scenario)

    alice = scenario.player("alice")
    assert len(alice.hand) == 1 and alice.hand[0] in top
    assert alice.graveyard == []
    assert len(alice.library) == 3  # Forest on top, the other two looked-at cards below


def test_eruth_exiles_the_top_two_instead_of_drawing():
    scenario = _board(["Eruth, Tormented Prophet"], library=["Grizzly Bears", "Island", "Forest"])

    _draw(scenario)

    alice = scenario.player("alice")
    assert alice.hand == []
    assert sorted(c.name for c in scenario.game.exile) == ["Grizzly Bears", "Island"]


def test_asmodeus_exiles_the_top_card_face_down():
    scenario = _board(["Asmodeus the Archfiend"], library=["Grizzly Bears", "Island"])

    _draw(scenario)

    exiled = [c for c in scenario.game.exile]
    assert [c.card.name for c in exiled] == ["Grizzly Bears"]
    assert exiled[0].face_up is False
    assert scenario.player("alice").hand == []


def test_shared_fate_exiles_from_an_opponents_library_for_either_player():
    scenario = _board(["Shared Fate"], bob_library=["Grizzly Bears", "Forest"], library=["Island", "Swamp"])

    _draw(scenario, "alice")  # alice draws -> exiles the top of bob's library
    _draw(scenario, "bob")  # bob draws -> exiles the top of alice's library

    assert scenario.player("alice").hand == [] and scenario.player("bob").hand == []
    assert sorted(c.card.name for c in scenario.game.exile) == ["Grizzly Bears", "Island"]


def test_uba_mask_exiles_the_card_face_up_instead_of_drawing_it():
    scenario = _board(["Uba Mask"], library=["Grizzly Bears", "Island"])

    _draw(scenario)

    exiled = list(scenario.game.exile)
    assert [c.name for c in exiled] == ["Grizzly Bears"]
    assert exiled[0].face_up is True
    assert scenario.player("alice").hand == []


def test_zur_weirding_draws_when_nobody_pays_and_buries_when_someone_does():
    scenario = _board(["Zur's Weirding"], library=["Grizzly Bears", "Island"])
    scenario.will_pay_the_life(False, username="bob") if hasattr(scenario, "will_pay_the_life") else None
    _draw(scenario)
    assert _names(scenario.player("alice").hand) == ["Grizzly Bears"]

    scenario = _board(["Zur's Weirding"], library=["Grizzly Bears", "Island"])
    scenario.will_pay_the_life(True, username="bob")
    _draw(scenario)
    assert scenario.player("alice").hand == []
    assert _names(scenario.player("alice").graveyard) == ["Grizzly Bears"]
    assert scenario.player("bob").life == 18


def test_enduring_renewal_creature_to_graveyard_otherwise_draw():
    scenario = _board(["Enduring Renewal"], library=["Grizzly Bears", "Island", "Forest"])
    _draw(scenario)
    assert scenario.player("alice").hand == []
    assert _names(scenario.player("alice").graveyard) == ["Grizzly Bears"]

    _draw(scenario)  # Island is not a creature: the draw simply happens
    assert _names(scenario.player("alice").hand) == ["Island"]


def test_abundance_takes_the_first_land_and_buries_the_rest():
    scenario = _board(
        ["Abundance"], library=["Grizzly Bears", "Llanowar Elves", "Forest", "Island"]
    )
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose("land", username="alice")

    _draw(scenario)

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Forest"]
    assert sorted(_names(alice.library)) == ["Grizzly Bears", "Island", "Llanowar Elves"]
    assert alice.library[0].name == "Island"  # the unrevealed top stays on top


def test_abundance_declined_draws_normally():
    scenario = _board(["Abundance"], library=["Grizzly Bears", "Forest"])
    scenario.will_take_the_may(False, username="alice")

    _draw(scenario)

    assert _names(scenario.player("alice").hand) == ["Grizzly Bears"]


def test_archmage_ascension_needs_six_quest_counters():
    scenario = _board(["Archmage Ascension"], library=["Island", "Forest", "Swamp"])
    ascension = scenario.find("Archmage Ascension", Zone.BATTLEFIELD, "alice")
    ascension.add_counters("quest", 5)
    _draw(scenario)
    assert _names(scenario.player("alice").hand) == ["Island"]  # below six: normal

    ascension.add_counters("quest", 1)
    scenario.will_take_the_may(True, username="alice")
    target = scenario.player("alice").library[1]
    scenario.will_choose_cards(target, username="alice")
    _draw(scenario)
    assert target in scenario.player("alice").hand


@pytest.mark.parametrize(
    "name",
    [
        "Blood Scrivener",
        "Phial of Galadriel",
        "Laboratory Maniac",
        "Jace, Wielder of Mysteries",
        "Living Conundrum",
        "Sages of the Anima",
        "Underrealm Lich",
        "Tomorrow, Azami's Familiar",
        "Eruth, Tormented Prophet",
        "Asmodeus the Archfiend",
        "Shared Fate",
        "Uba Mask",
        "Zur's Weirding",
        "Enduring Renewal",
        "Abundance",
        "Archmage Ascension",
    ],
)
def test_draw_replacement_lines_are_handled(name):
    _handled(name, "would draw")
