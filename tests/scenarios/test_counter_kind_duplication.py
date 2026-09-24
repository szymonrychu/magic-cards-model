"""Scenario: "For each kind of counter on target permanent or player, give
that permanent or player another counter of that kind."

Proliferate's one-target sibling (CR 701.34a gives "each one additional
counter of each kind that permanent or player already has" to any number
chosen; this gives the same thing to exactly one target). Printed on:

- Powerful Broker (MSH): "{T}: ... Activate only as a sorcery."
- Maulfist Revolutionary (AER, not listed, not in a deck): "When this
  creature enters or dies, ..."
- Skyship Plunderer (AER, not listed, not in a deck): "Whenever this creature
  deals combat damage to a player, ..."

"Give ... another counter" is putting a counter (CR 122.6), so a replacement
on counters being put (Hardened Scales) applies and the ability's controller
is who puts it (CR 122.6a).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 122.1** - "Counters with the same name or description are
  interchangeable" - the kind is the name.
- **CR 122.6** / **CR 122.6a** - counters put on an object, and who puts them.
- **CR 701.34a** - proliferate, the any-number form of the same gift.
- **CR 602.5d** - "Activate only as a sorcery".
- **CR 608.2b** - an illegal target on resolution: the ability does nothing
  to it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _broker_board(*alice: str, bob: tuple[str, ...] = ("Grizzly Bears",)) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Powerful Broker", *alice])
        .player("bob", battlefield=list(bob))
    )


def _broker(scenario):
    broker = scenario.creature("Powerful Broker", "alice")
    broker.summoning_sick = False
    return broker


def test_each_kind_on_a_permanent_gets_one_more():
    scenario = _broker_board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 2)
    bears.add_counters("shield", 1)
    bears.add_counters(Counter.STUN, 1)

    scenario.activate(_broker(scenario), targets=[bears])
    scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 3
    assert bears.counter_count("shield") == 2
    assert bears.counter_count(Counter.STUN) == 2


def test_a_permanent_with_no_counters_gets_nothing():
    scenario = _broker_board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(_broker(scenario), targets=[bears])
    scenario.resolve_top()

    assert dict(bears.counters.counts) == {}


def test_a_player_gets_one_more_of_each_kind():
    scenario = _broker_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bob.add_counters(Counter.POISON, 3)
    bob.add_counters(Counter.ENERGY, 1)

    scenario.activate(_broker(scenario), targets=[bob])
    scenario.resolve_top()

    assert bob.counter_count(Counter.POISON) == 4
    assert bob.counter_count(Counter.ENERGY) == 2


def test_an_opponents_permanent_is_a_legal_target():
    scenario = _broker_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")
    theirs.add_counters(Counter.MINUS_ONE, 1)

    scenario.activate(_broker(scenario), targets=[theirs])
    scenario.resolve_top()
    scenario.state_based_actions()

    # A second -1/-1 counter makes bob's 2/2 a 0/0 (CR 704.5f).
    assert theirs.zone.value == "graveyard"


def test_hardened_scales_sees_the_counter_being_put():
    """CR 122.6: giving a counter is putting one, so Hardened Scales adds one
    - and the ability's controller is the one putting it (CR 122.6a)."""
    scenario = _broker_board("Grizzly Bears", "Hardened Scales").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)

    scenario.activate(_broker(scenario), targets=[bears])
    scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 3


def test_a_target_gone_by_resolution_gets_nothing():
    """CR 608.2b: the only target is illegal, so the ability does nothing."""
    scenario = _broker_board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)

    scenario.activate(_broker(scenario), targets=[bears])
    scenario.game.put_into_graveyard(bears)
    scenario.resolve_top()

    assert all(p.counter_count(Counter.PLUS_ONE) == 0 for p in scenario.game.battlefield)


def test_the_broker_is_sorcery_speed():
    """CR 602.5d: not outside a main phase."""
    scenario = _broker_board().build()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    broker = _broker(scenario)

    assert scenario.why_cannot_activate(broker) is not None


# -- the same instruction on a trigger ---------------------------------------


def test_maulfist_revolutionary_enters_and_gives_another_counter():
    scenario = (
        Scenario()
        .player("alice", hand=["Maulfist Revolutionary"], battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)
    bears.add_counters("oil", 2)
    scenario.choose_trigger_targets("Maulfist Revolutionary", [bears])

    scenario.put_onto_battlefield("Maulfist Revolutionary", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 2
    assert bears.counter_count("oil") == 3


def test_maulfist_revolutionary_dies_and_gives_a_player_another_counter():
    scenario = (
        Scenario().player("alice", battlefield=["Maulfist Revolutionary"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    maulfist = scenario.creature("Maulfist Revolutionary", "alice")
    bob = scenario.player("bob")
    bob.add_counters(Counter.POISON, 9)
    scenario.choose_trigger_targets("Maulfist Revolutionary", [bob])

    scenario.game.destroy(maulfist)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bob.counter_count(Counter.POISON) == 10


def test_skyship_plunderer_combat_damage_gives_another_counter():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Skyship Plunderer", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plunderer = scenario.creature("Skyship Plunderer", "alice")
    plunderer.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)
    scenario.choose_trigger_targets("Skyship Plunderer", [bears])

    scenario.attack_with(plunderer)
    scenario.no_blocks()
    scenario.combat_damage()
    while scenario.game.stack:
        scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 2
