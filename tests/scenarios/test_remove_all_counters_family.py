"""Scenario: "remove all counters from ..." in each of its printed shapes.

- "... from up to one target permanent/creature" - Marchesa, Resolute
  Monarch's attack trigger (Invasion of Fiora's back face) and Purging
  Stormbrood's enters trigger: CR 115.6's "up to one" ahead of the ordinary
  targeted shape Vampire Hexmage prints.
- "Remove all counters from all permanents and exile all tokens." - Aether
  Snap: the mass twin, sharing "Destroy all ..."'s qualifier grammar, with
  "tokens" (CR 111.1) as the qualifier of its second instruction.
- Suncleanser's two modes: the targeted removal plus "It can't have counters
  put on it for as long as this creature remains on the battlefield.", and
  "Target opponent loses all counters. That player can't get counters for
  as long as this creature remains on the battlefield." (CR 611.2b).

Every CR number here was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 115.6** - "up to N" targets; zero is a legal number.
- **CR 122.1** - counters on objects and on players.
- **CR 122.6** - counters put on an object, including as it enters.
- **CR 111.1** - a token is a marker for a permanent that isn't a card.
- **CR 611.2b** - a "for as long as" duration ends when its condition stops
  being true; one that never starts does nothing.
- **CR 400.7** - an object that changes zones is a new object.
- **CR 608.2f** - an action on several objects is processed simultaneously.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import PREDEFINED, create_tokens
from tests.scenarios.harness import Scenario

MARCHESA = "Invasion of Fiora"
STORMBROOD = "Purging Stormbrood"
SNAP = "Aether Snap"
SUNCLEANSER = "Suncleanser"
HYDRA = "Kalonian Hydra"
WALKER = "Liliana of the Veil"

CANT_HAVE = (
    "Remove all counters from target creature. It can't have counters put on it for "
    "as long as this creature remains on the battlefield."
)
LOSES_ALL = (
    "Target opponent loses all counters. That player can't get counters for as long "
    "as this creature remains on the battlefield."
)


def test_marchesa_attacking_removes_every_counter_from_one_target_permanent():
    scenario = (
        Scenario()
        .player("alice", hand=[MARCHESA], library=["Plains"] * 3)
        .player("bob", battlefield=[WALKER], hand=[HYDRA], library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.put_onto_battlefield(HYDRA, "bob")
    card = scenario.find(MARCHESA, Zone.HAND, "alice")
    marchesa = scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    marchesa.summoning_sick = False
    walker = scenario.find(WALKER, Zone.BATTLEFIELD, "bob")
    assert walker.counter_count(Counter.LOYALTY) == 3

    scenario.will_choose_targets(walker, username="alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(marchesa)
    scenario.pass_until_resolved()

    assert walker.counter_count(Counter.LOYALTY) == 0
    scenario.game.check_state_based_actions()
    assert walker.zone is Zone.GRAVEYARD, "CR 704.5i: a planeswalker with 0 loyalty"
    assert hydra.counter_count(Counter.PLUS_ONE) == 4, "only the one target"


def test_purging_stormbrood_with_up_to_one_target_strips_a_hydra():
    scenario = Scenario().player("alice", hand=[STORMBROOD]).player("bob", hand=[HYDRA]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.put_onto_battlefield(HYDRA, "bob")
    scenario.will_choose_targets(hydra, username="alice")

    scenario.put_onto_battlefield(STORMBROOD, "alice")
    scenario.pass_until_resolved()
    scenario.game.check_state_based_actions()

    assert hydra.zone is Zone.GRAVEYARD, "a 0/0 once its counters are gone"


def test_purging_stormbrood_may_choose_no_target():
    """CR 115.6: zero targets is legal; nothing is removed."""
    scenario = Scenario().player("alice", hand=[STORMBROOD]).player("bob", hand=[HYDRA]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.put_onto_battlefield(HYDRA, "bob")
    scenario.will_choose_targets(username="alice")

    scenario.put_onto_battlefield(STORMBROOD, "alice")
    scenario.pass_until_resolved()

    assert hydra.counter_count(Counter.PLUS_ONE) == 4


def test_aether_snap_removes_every_counter_and_exiles_every_token():
    scenario = (
        Scenario()
        .player("alice", hand=[SNAP, HYDRA], battlefield=["Swamp"] * 5 + ["Grizzly Bears"])
        .player("bob", battlefield=[WALKER])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hydra = scenario.put_onto_battlefield(HYDRA, "alice")
    assert hydra.counter_count(Counter.PLUS_ONE) == 4
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    walker = scenario.find(WALKER, Zone.BATTLEFIELD, "bob")
    (treasure,) = create_tokens(scenario.game, PREDEFINED["Treasure"], "bob")

    scenario.cast_and_resolve(SNAP, *scenario.untapped_sources(*["Swamp"] * 5))
    scenario.game.check_state_based_actions()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counter_count(Counter.PLUS_ONE) == 0
    assert hydra.zone is Zone.GRAVEYARD, "a 0/0 once its counters are gone"
    assert walker.zone is Zone.GRAVEYARD, "CR 704.5i: 0 loyalty"
    assert treasure.zone is not Zone.BATTLEFIELD


def test_suncleanser_strips_a_creature_and_it_stays_counterless_while_suncleanser_remains():
    scenario = (
        Scenario()
        .player("alice", hand=[SUNCLEANSER])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 3)
    scenario.will_choose_mode(CANT_HAVE, username="alice")
    scenario.will_choose_targets(bears, username="alice")

    suncleanser = scenario.put_onto_battlefield(SUNCLEANSER, "alice")
    scenario.pass_until_resolved()
    assert bears.counter_count(Counter.PLUS_ONE) == 0

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    assert bears.counter_count(Counter.PLUS_ONE) == 0, "while Suncleanser remains"

    scenario.game.put_into_graveyard(suncleanser)
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    assert bears.counter_count(Counter.PLUS_ONE) == 2, "CR 611.2b: the duration ended"


def test_suncleanser_prohibition_follows_the_object_not_the_card():
    """CR 400.7: a Hydra that dies and comes back is a new object; the
    prohibition was on the old one."""
    scenario = (
        Scenario()
        .player("alice", hand=[SUNCLEANSER])
        .player("bob", battlefield=["Grizzly Bears"], hand=[HYDRA])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_mode(CANT_HAVE, username="alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.put_onto_battlefield(SUNCLEANSER, "alice")
    scenario.pass_until_resolved()

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    assert bears.counter_count(Counter.PLUS_ONE) == 0
    hydra = scenario.put_onto_battlefield(HYDRA, "bob")
    assert hydra.counter_count(Counter.PLUS_ONE) == 4, "another creature is unaffected"


def test_suncleanser_takes_an_opponents_poison_and_blocks_more_while_it_remains():
    scenario = Scenario().player("alice", hand=[SUNCLEANSER]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.add_player_counters("bob", Counter.POISON, 4)
    scenario.game.add_player_counters("bob", Counter.ENERGY, 2)
    scenario.will_choose_mode(LOSES_ALL, username="alice")
    scenario.will_choose_targets("bob", username="alice")

    suncleanser = scenario.put_onto_battlefield(SUNCLEANSER, "alice")
    scenario.pass_until_resolved()
    bob = scenario.player("bob")
    assert bob.counter_count(Counter.POISON) == 0
    assert bob.counter_count(Counter.ENERGY) == 0

    scenario.game.add_player_counters("bob", Counter.POISON, 1)
    scenario.game.add_player_counters("alice", Counter.ENERGY, 1)
    assert bob.counter_count(Counter.POISON) == 0
    assert scenario.player("alice").counter_count(Counter.ENERGY) == 1, "only that player"

    scenario.game.put_into_graveyard(suncleanser)
    scenario.game.add_player_counters("bob", Counter.POISON, 1)
    assert bob.counter_count(Counter.POISON) == 1, "CR 611.2b: the duration ended"


def _suncleansed_bob():
    scenario = Scenario().player("alice", hand=[SUNCLEANSER]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_mode(LOSES_ALL, username="alice")
    scenario.will_choose_targets("bob", username="alice")
    suncleanser = scenario.put_onto_battlefield(SUNCLEANSER, "alice")
    scenario.pass_until_resolved()
    return scenario, suncleanser


def test_suncleansers_player_prohibition_survives_a_save_and_load():
    """The recorded "can't get counters" is game state: a decoded game still
    refuses bob's counters while the same Suncleanser remains."""
    from magic_cards_model.models.game import Game

    scenario, _ = _suncleansed_bob()
    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))

    decoded.add_player_counters("bob", Counter.POISON, 1)
    assert decoded.player("bob").counter_count(Counter.POISON) == 0


def test_suncleansers_player_prohibition_is_dropped_once_its_duration_ends():
    """CR 611.2b: the "for as long as" duration ended with Suncleanser leaving
    the battlefield, so the recorded effect is gone from the game too - not
    kept inert in every later snapshot."""
    scenario, suncleanser = _suncleansed_bob()
    assert scenario.game.casting_rule_effects

    scenario.game.put_into_graveyard(suncleanser)
    scenario.game.check_state_based_actions()

    assert scenario.game.casting_rule_effects == []
