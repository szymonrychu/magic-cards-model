"""Mass tap and untap instructions with a colour or no controller.

CR 701.26a/b: tapping and untapping are not targeted; "tap all <group>" and
"untap all <group>" affect every permanent in the group as the instruction is
applied (CR 608.2h). A colour word (CR 105.2) narrows the group, read off the
computed board; with no "you control" the group is every player's.

- Wrath of Marit Lage: "When this enchantment enters, tap all red creatures."
- Intruder Alarm: "Whenever a creature enters, untap all creatures."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice_bf, bob_bf, hand):
    scenario = (
        Scenario()
        .player("alice", battlefield=alice_bf, hand=hand, library=["Island"] * 5)
        .player("bob", battlefield=bob_bf, library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_all(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def test_wrath_of_marit_lage_taps_every_red_creature_and_nothing_else():
    scenario = _board(
        ["Island"] * 5 + ["Goblin Guide"],
        ["Raging Goblin", "Grizzly Bears"],
        ["Wrath of Marit Lage"],
    )
    scenario.cast_and_resolve("Wrath of Marit Lage", *scenario.untapped_sources(*["Island"] * 5))
    _resolve_all(scenario)

    assert scenario.find("Goblin Guide", Zone.BATTLEFIELD, "alice").tapped
    assert scenario.find("Raging Goblin", Zone.BATTLEFIELD, "bob").tapped
    assert not scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").tapped


def test_wrath_keeps_the_red_creatures_it_tapped_tapped():
    scenario = _board(["Island"] * 5, ["Raging Goblin"], ["Wrath of Marit Lage"])
    scenario.cast_and_resolve("Wrath of Marit Lage", *scenario.untapped_sources(*["Island"] * 5))
    _resolve_all(scenario)
    goblin = scenario.find("Raging Goblin", Zone.BATTLEFIELD, "bob")
    while scenario.game.turn.active_player != "bob":
        _resolve_all(scenario)
        scenario.advance()
    while scenario.game.turn.step in (Step.UNTAP,):
        scenario.advance()
    assert goblin.tapped


def test_intruder_alarm_untaps_every_players_creatures_when_a_creature_enters():
    scenario = _board(
        ["Intruder Alarm", "Forest", "Forest", "Grizzly Bears", "Island"],
        ["Hill Giant"],
        ["Grizzly Bears"],
    )
    mine = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    mine.tapped = giant.tapped = island.tapped = True

    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    _resolve_all(scenario)

    assert not mine.tapped and not giant.tapped
    assert island.tapped  # creatures only


def test_intruder_alarm_does_nothing_until_a_creature_enters():
    scenario = _board(["Intruder Alarm", "Island"], ["Hill Giant"], [])
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    giant.tapped = True
    _resolve_all(scenario)
    assert giant.tapped


def test_both_cards_read_handled():
    for name in ("Wrath of Marit Lage", "Intruder Alarm"):
        support = card_support(card(name))
        assert support.status == "handled", [c for c in support.clauses if c.status != "handled"]
