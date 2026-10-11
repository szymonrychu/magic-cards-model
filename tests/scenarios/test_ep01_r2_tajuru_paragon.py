"""Scenario: Tajuru Paragon - "When this creature enters, if it was kicked,
reveal the top six cards of your library. You may put a card that shares a
creature type with it from among them into your hand. Put the rest on the
bottom of your library in a random order."

CR 702.33a/d (kicker; "if it was kicked" is an intervening if, CR 603.4),
CR 701.20a (reveal), CR 608.2d (the optional pick among the revealed cards),
CR 205.3m (shares a creature type; the Paragon is also a Cleric, Rogue,
Warrior and Wizard, so a Wizard card qualifies), CR 401.4 (cards put on the
bottom together go in a random order).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

LIBRARY = ["Llanowar Elves", "Grizzly Bears", "Wind Drake", "Island", "Island", "Island", "Forest"]


def board(*lands):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Tajuru Paragon"],
            battlefield=list(lands),
            library=list(LIBRARY),
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def cast_paragon(scenario, *, kicked):
    casting = scenario.cast("Tajuru Paragon")
    if kicked:
        casting.pay_kicker()
    payment = casting.begin_paying()
    for source in scenario.untapped_sources(*["Forest"] * (5 if kicked else 2)):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    while scenario.game.stack:
        scenario.resolve_top()


def test_kicked_it_reveals_six_and_takes_a_card_sharing_a_creature_type():
    scenario = board(*["Forest"] * 5)
    elves = scenario.find("Llanowar Elves", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(elves)

    cast_paragon(scenario, kicked=True)

    alice = scenario.player("alice")
    assert elves.zone is Zone.HAND
    assert len(alice.library) == 6
    assert "Llanowar Elves" not in [c.name for c in alice.library]


def test_the_cards_that_do_not_share_a_type_cannot_be_taken():
    scenario = board(*["Forest"] * 5)
    scenario.will_take_the_may(True)
    # Only the Elf is offered: a Bear or a Drake shares no type with the Paragon.
    cast_paragon(scenario, kicked=True)

    names = [c.name for c in scenario.player("alice").hand]
    assert "Llanowar Elves" in names
    assert "Grizzly Bears" not in names and "Wind Drake" not in names


def test_declining_puts_all_six_on_the_bottom():
    scenario = board(*["Forest"] * 5)
    scenario.will_take_the_may(False)

    cast_paragon(scenario, kicked=True)

    alice = scenario.player("alice")
    assert len(alice.library) == 7
    assert [c.name for c in alice.hand] == []
    # the one unrevealed card is now on top
    assert alice.library[0].name == "Forest"


def test_unkicked_it_does_nothing():
    scenario = board(*["Forest"] * 5)
    scenario.will_take_the_may(True)

    cast_paragon(scenario, kicked=False)

    assert len(scenario.player("alice").library) == 7
    assert [c.name for c in scenario.player("alice").hand] == []


def test_a_type_the_paragon_is_also_counts():
    """Merfolk Looter is a Rogue, a type the Paragon only has through "is also
    a Cleric, Rogue, Warrior, and Wizard"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Tajuru Paragon"],
            battlefield=["Forest"] * 5,
            library=["Merfolk Looter", "Grizzly Bears", "Island", "Island", "Island", "Island"],
        )
        .player("bob", library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True)

    cast_paragon(scenario, kicked=True)

    assert [c.name for c in scenario.player("alice").hand] == ["Merfolk Looter"]
