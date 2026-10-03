"""Scenario: "as long as an opponent has N or more cards in their graveyard"
(the Rogues' / Spectre's threshold-by-the-other-side static).

- **Blackbloom Rogue** (Wilds of Eldraine // Blackbloom Bog), "This creature
  gets +3/+0 as long as an opponent has eight or more cards in their
  graveyard."
- Second printings with differing wording, pump + keyword, condition leading
  or trailing, a different number: **Jace's Phantasm** ("gets +4/+4 ... ten or
  more"), **Nimana Skitter-Sneak** ("As long as an opponent has eight or more
  cards in their graveyard, this creature gets +1/+0 and has menace.").

CR 604.2 (a static ability's effect is active only while the permanent has the
ability) and CR 611.3a (such an effect is not locked in, it applies at any
given moment to whatever its text indicates): the condition is re-read on
every board computation, so the pump toggles as the graveyard fills and
empties. "An opponent" is any other player, never the source's controller.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

#: Blackbloom Rogue's front face is a 2/3 (the MDFC card itself has no P/T).
ROGUE_POWER, ROGUE_TOUGHNESS = 2, 3


def _scenario(name: str, bob_graveyard: int, alice_graveyard: int = 0):
    scenario = (
        Scenario()
        .player("alice", battlefield=[name], graveyard=["Mountain"] * alice_graveyard)
        .player("bob", graveyard=["Island"] * bob_graveyard, library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(name, "alice")


def _chars(scenario, creature):
    return scenario.game.characteristics_of(creature)


def test_blackbloom_rogue_gets_plus_three_with_eight_cards_in_an_opponents_graveyard():
    scenario, rogue = _scenario("Blackbloom Rogue", 8)
    chars = _chars(scenario, rogue)
    assert chars.power == ROGUE_POWER + 3
    assert chars.toughness == ROGUE_TOUGHNESS


def test_blackbloom_rogue_is_vanilla_with_seven_cards():
    scenario, rogue = _scenario("Blackbloom Rogue", 7)
    assert _chars(scenario, rogue).power == ROGUE_POWER


def test_blackbloom_rogue_ignores_its_own_controllers_graveyard():
    scenario, rogue = _scenario("Blackbloom Rogue", 0, alice_graveyard=12)
    assert _chars(scenario, rogue).power == ROGUE_POWER


def test_blackbloom_rogue_toggles_as_the_opponents_graveyard_fills_and_empties():
    scenario, rogue = _scenario("Blackbloom Rogue", 7)
    base = ROGUE_POWER
    assert _chars(scenario, rogue).power == base

    entering = scenario.player("bob").library[0]
    scenario.game.put_into_graveyard(entering)
    assert _chars(scenario, rogue).power == base + 3

    scenario.game.exile_cards([entering])
    assert _chars(scenario, rogue).power == base


def test_jaces_phantasm_needs_ten_and_gets_plus_four_plus_four():
    scenario, phantasm = _scenario("Jace's Phantasm", 9)
    assert _chars(scenario, phantasm).power == int(phantasm.card.power)
    scenario, phantasm = _scenario("Jace's Phantasm", 10)
    chars = _chars(scenario, phantasm)
    assert (chars.power, chars.toughness) == (
        int(phantasm.card.power) + 4,
        int(phantasm.card.toughness) + 4,
    )


def test_nimana_skitter_sneak_condition_leading_pump_and_menace():
    scenario, nimana = _scenario("Nimana Skitter-Sneak", 8)
    chars = _chars(scenario, nimana)
    assert chars.power == int(nimana.card.power) + 1
    assert chars.has_ability("Menace")


def test_nimana_skitter_sneak_is_vanilla_below_the_threshold():
    scenario, nimana = _scenario("Nimana Skitter-Sneak", 7)
    chars = _chars(scenario, nimana)
    assert chars.power == int(nimana.card.power)
    assert not chars.has_ability("Menace")
