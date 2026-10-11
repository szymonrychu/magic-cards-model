"""Scenario: Kasmina, Enigma Sage - "Each other planeswalker you control has
the loyalty abilities of Kasmina." and "-8: Search your library for an instant
or sorcery card that shares a color with this planeswalker, exile that card,
then shuffle. You may cast that card without paying its mana cost."

CR 613.1f (an ability-adding effect, layer 6), CR 606 (loyalty abilities; each
planeswalker is still held to one activation a turn, CR 606.3), CR 701.23
(search), CR 608.2g (casting during resolution). "This planeswalker" in a
granted ability is the planeswalker that has it, so a granted -8 looks for a
card sharing a color with the host, not with Kasmina.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

KASMINA = "Kasmina, Enigma Sage"


def board(alice_battlefield, bob_battlefield=(), library=("Island", "Island")):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[KASMINA, *alice_battlefield],
            library=list(library),
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def loyalty_lines(scenario, name, username="alice"):
    chars = scenario.game.characteristics_of(scenario.creature(name, username))
    return [line for line in chars.abilities if line[:1] in "+-−" or line[:2] == "0:"]


def test_another_planeswalker_you_control_has_kasminas_loyalty_abilities():
    scenario = board(["Jace Beleren"])
    lines = loyalty_lines(scenario, "Jace Beleren")

    assert any(line.startswith("+2: Scry 1") for line in lines)
    assert any(line.startswith("−X: Create a 0/0") for line in lines)
    assert any(line.startswith("−8: Search your library") for line in lines)


def test_kasminas_granted_plus_two_scries_for_jace():
    scenario = board(["Jace Beleren"], library=["Island", "Forest", "Mountain"])
    jace = scenario.creature("Jace Beleren")
    abilities = scenario.game.activated_abilities(jace)
    index = next(i for i, a in enumerate(abilities) if a.raw.startswith("+2: Scry 1"))
    scenario.scry_keeping_everything_on_top()

    scenario.activate(jace, index=index, username="alice")
    scenario.resolve_top()

    assert jace.counter_count(Counter.LOYALTY) == 5


def test_an_opponents_planeswalker_does_not_get_them():
    scenario = board([], bob_battlefield=["Jace Beleren"])
    assert loyalty_lines(scenario, "Jace Beleren", "bob") != []
    assert not any(
        line.startswith("+2: Scry 1") for line in loyalty_lines(scenario, "Jace Beleren", "bob")
    )


def test_kasmina_does_not_get_her_own_abilities_twice():
    scenario = board(["Jace Beleren"])
    lines = loyalty_lines(scenario, KASMINA)

    assert sum(1 for line in lines if line.startswith("+2: Scry 1")) == 1


def test_kasminas_minus_eight_exiles_a_shared_colour_card_and_casts_it_free():
    scenario = board([], library=["Lightning Bolt", "Divination", "Island", "Island"])
    kasmina = scenario.creature(KASMINA)
    kasmina.add_counters(Counter.LOYALTY, 8)
    divination = scenario.find("Divination", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(divination)
    scenario.will_take_the_may(True)
    hand_before = len(scenario.player("alice").hand)

    abilities = scenario.game.activated_abilities(kasmina)
    index = next(i for i, a in enumerate(abilities) if a.raw.startswith("−8:"))
    scenario.activate(kasmina, index=index, username="alice")
    scenario.resolve_top()
    while scenario.game.stack:
        scenario.resolve_top()

    assert divination.zone is Zone.GRAVEYARD, "cast for free and resolved"
    assert len(scenario.player("alice").hand) == hand_before + 2, "Divination drew two"
    bolt = next(c for c in scenario.all_card_states() if c.name == "Lightning Bolt")
    assert bolt.zone is not Zone.EXILE, "a red card shares no color with Kasmina"


def test_a_granted_minus_eight_shares_a_colour_with_the_host_not_with_kasmina():
    """Jace is blue only: a green instant (Kasmina is green and blue) is not
    a legal find for Jace's copy of the ability."""
    scenario = board(["Jace Beleren"], library=["Giant Growth", "Island", "Island"])
    jace = scenario.creature("Jace Beleren")
    jace.add_counters(Counter.LOYALTY, 8)
    abilities = scenario.game.activated_abilities(jace)
    index = next(i for i, a in enumerate(abilities) if a.raw.startswith("−8:"))
    scenario.will_take_the_may(True)

    scenario.activate(jace, index=index, username="alice")
    scenario.resolve_top()

    growth = scenario.find("Giant Growth", Zone.LIBRARY, "alice")
    assert growth.zone is Zone.LIBRARY
