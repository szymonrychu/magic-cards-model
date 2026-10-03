"""Scenario: "as long as you've committed a crime this turn" as a self static.

- **Omenport Vigilante**, "This creature has double strike as long as you've
  committed a crime this turn." (grant only).
- Second printing, pump instead of a keyword: **Slickshot Vault-Buster**,
  "This creature gets +2/+0 as long as you've committed a crime this turn."

CR 700.13 defines the crime (casting a spell or activating or triggering an
ability that targets an opponent, something they control or a card in their
graveyard); `machines/conditions/history.record_crime` records it as a
turn-scoped fact. CR 604.2 / CR 611.3a: the static re-reads that fact on
every board computation, so it is on after the crime and off again once the
turn ends. Targeting your own permanent is not a crime.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _scenario(name: str):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[name, "Mountain", "Grizzly Bears"],
            hand=["Lightning Bolt"],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature(name, "alice")


def _chars(scenario, creature):
    return scenario.game.characteristics_of(creature)


def _bolt(scenario, target):
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[target]
    )


def test_omenport_vigilante_has_no_double_strike_before_any_crime():
    scenario, vigilante = _scenario("Omenport Vigilante")
    assert not _chars(scenario, vigilante).has_ability("Double strike")


def test_omenport_vigilante_gets_double_strike_after_targeting_an_opponent():
    scenario, vigilante = _scenario("Omenport Vigilante")
    _bolt(scenario, "bob")
    assert _chars(scenario, vigilante).has_ability("Double strike")


def test_omenport_vigilante_gets_double_strike_after_targeting_an_opponents_permanent():
    scenario, vigilante = _scenario("Omenport Vigilante")
    _bolt(scenario, scenario.creature("Grizzly Bears", "bob"))
    assert _chars(scenario, vigilante).has_ability("Double strike")


def test_targeting_your_own_creature_is_not_a_crime_so_no_double_strike():
    scenario, vigilante = _scenario("Omenport Vigilante")
    _bolt(scenario, scenario.creature("Grizzly Bears", "alice"))
    assert not _chars(scenario, vigilante).has_ability("Double strike")


def test_omenport_vigilante_loses_double_strike_when_the_turn_ends():
    scenario, vigilante = _scenario("Omenport Vigilante")
    _bolt(scenario, "bob")
    assert _chars(scenario, vigilante).has_ability("Double strike")

    turn = scenario.game.turn.turn_number
    for _ in range(60):
        if scenario.game.turn.turn_number != turn:
            break
        scenario.advance()
    assert scenario.game.turn.turn_number != turn
    assert not _chars(scenario, vigilante).has_ability("Double strike")


def test_the_opponents_crime_does_not_turn_it_on():
    scenario, vigilante = _scenario("Omenport Vigilante")
    scenario.game.record_turn_fact("committed_crime", "bob")
    assert not _chars(scenario, vigilante).has_ability("Double strike")


def test_slickshot_vault_buster_pumps_only_after_a_crime():
    scenario, buster = _scenario("Slickshot Vault-Buster")
    assert _chars(scenario, buster).power == int(buster.card.power)
    _bolt(scenario, "bob")
    chars = _chars(scenario, buster)
    assert chars.power == int(buster.card.power) + 2
    assert chars.toughness == int(buster.card.toughness)
