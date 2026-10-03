"""Scenario: "as long as an opponent has N or less life" - a self static
gated on the *other* side's life total (CR 119.1: each player has a life
total).

- **Bloodghast**, "This creature has haste as long as an opponent has 10 or
  less life." (grant only, condition trailing).
- Second printings with differing wording: **Ruthless Cullblade** ("This
  creature gets +2/+1 as long as an opponent has 10 or less life.", pump
  only) and **Blood Baron of Vizkopa** ("As long as you have 30 or more
  life and an opponent has 10 or less life, this creature gets +6/+6 and has
  flying.", condition leading, conjoined, pump and keyword). Guul Draz
  Vampire's identical leading wording grants intimidate, which the engine has
  no keyword for, so it cannot serve as a witness.

CR 604.2 / CR 611.3a: re-read on every board computation, so the effect turns
on and off as the life total crosses the line in either direction. The
controller's own life total is never consulted.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _scenario(name: str, bob_life: int = 20, alice_life: int = 20):
    scenario = (
        Scenario()
        .player("alice", battlefield=[name], life=alice_life)
        .player("bob", life=bob_life)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(name, "alice")


def _chars(scenario, creature):
    return scenario.game.characteristics_of(creature)


def test_bloodghast_has_haste_while_an_opponent_is_at_ten_life():
    scenario, ghast = _scenario("Bloodghast", bob_life=10)
    assert _chars(scenario, ghast).has_ability("Haste")


def test_bloodghast_has_no_haste_at_eleven_life():
    scenario, ghast = _scenario("Bloodghast", bob_life=11)
    assert not _chars(scenario, ghast).has_ability("Haste")


def test_bloodghast_ignores_its_own_controllers_low_life():
    scenario, ghast = _scenario("Bloodghast", bob_life=20, alice_life=3)
    assert not _chars(scenario, ghast).has_ability("Haste")


def test_bloodghast_haste_toggles_as_the_opponent_loses_and_regains_life():
    scenario, ghast = _scenario("Bloodghast", bob_life=12)
    assert not _chars(scenario, ghast).has_ability("Haste")

    scenario.game.lose_life("bob", 2)
    assert _chars(scenario, ghast).has_ability("Haste")

    scenario.game.gain_life("bob", 1)
    assert not _chars(scenario, ghast).has_ability("Haste")


def test_ruthless_cullblade_pumps_at_ten_or_less_and_not_above():
    scenario, blade = _scenario("Ruthless Cullblade", bob_life=10)
    chars = _chars(scenario, blade)
    assert (chars.power, chars.toughness) == (
        int(blade.card.power) + 2,
        int(blade.card.toughness) + 1,
    )
    scenario.game.gain_life("bob", 1)
    chars = _chars(scenario, blade)
    assert (chars.power, chars.toughness) == (int(blade.card.power), int(blade.card.toughness))


def test_blood_baron_needs_both_halves_of_its_conjoined_life_condition():
    """Blood Baron of Vizkopa: "As long as you have 30 or more life and an
    opponent has 10 or less life, this creature gets +6/+6 and has flying." -
    condition leading, a conjunction of the controller's own life total and
    an opponent's, pump and keyword."""
    scenario, baron = _scenario("Blood Baron of Vizkopa", bob_life=10, alice_life=30)
    chars = _chars(scenario, baron)
    assert (chars.power, chars.toughness) == (
        int(baron.card.power) + 6,
        int(baron.card.toughness) + 6,
    )
    assert chars.has_ability("Flying")

    scenario.game.gain_life("bob", 1)
    chars = _chars(scenario, baron)
    assert chars.power == int(baron.card.power)
    assert not chars.has_ability("Flying")

    scenario.game.lose_life("bob", 1)
    scenario.game.lose_life("alice", 1)
    assert _chars(scenario, baron).power == int(baron.card.power)
