"""Scenario: "When this creature transforms into `<face>`, `<effect>`" - CR
701.27e's trigger event (`TriggerEvent.TRANSFORMS`, raised by
`machines/effects.transform_permanent`), whose face name may itself hold a
comma (`machines/abilities._transforms_into_face_boundary`).

Avacyn, the Purifier (Archangel Avacyn's back face) is the printing: "When
this creature transforms into Avacyn, the Purifier, it deals 3 damage to each
other creature and each opponent." - read whole ahead of the clause split
(`_parse_damage_each_other_type_and_each_opponent_clause`), since the bare
"and" would cut it in two.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.27e** - "Some triggered abilities trigger when an object
  'transforms into' an object with a specified characteristic. Such an
  ability triggers if the object either transforms ... and has the specified
  characteristic immediately after it does so."
- **CR 120.2b** - "The spell or ability will specify which object deals that
  damage": the Purifier deals it, so it is not dealt to itself ("each other
  creature").
- **CR 102.2** - the opponent is the other player; the controller takes no
  damage.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

AVACYN = "Archangel Avacyn"
PURIFIER = "Avacyn, the Purifier"


def _resolve_everything(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _to_next_upkeep(scenario: PlayedScenario) -> None:
    active = scenario.game.turn.active_player
    while not (scenario.step is Step.UPKEEP and scenario.game.turn.active_player != active):
        scenario.advance()


def test_the_purifier_deals_three_to_each_other_creature_and_each_opponent():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[AVACYN, "Grizzly Bears", "Hill Giant", "Craw Wurm"],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=["Serra Angel", "Gray Ogre"], library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    avacyn = scenario.creature(AVACYN, "alice")
    alice_life = scenario.player("alice").life
    bob_life = scenario.player("bob").life
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    _resolve_everything(scenario)

    _to_next_upkeep(scenario)
    _resolve_everything(scenario)

    assert avacyn.name == PURIFIER and avacyn.zone is Zone.BATTLEFIELD
    assert avacyn.damage == 0, "each *other* creature"
    assert scenario.find("Hill Giant", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert scenario.find("Gray Ogre", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD
    assert scenario.creature("Craw Wurm", "alice").damage == 3
    assert scenario.creature("Serra Angel", "bob").damage == 3
    assert scenario.player("bob").life == bob_life - 3
    assert scenario.player("alice").life == alice_life


def test_turning_back_to_the_front_face_does_not_trigger_the_back_face():
    """CR 701.27e: the ability names Avacyn, the Purifier - a transform that
    leaves the front face up does not have that characteristic afterwards."""
    from magic_cards_model.machines.effects import transform_permanent

    scenario = (
        Scenario()
        .player("alice", battlefield=[AVACYN], library=["Forest"] * 5)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    avacyn = scenario.creature(AVACYN, "alice")
    transform_permanent(scenario.game, avacyn)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{PURIFIER}'s triggered ability"]
    scenario.pass_until_resolved()

    transform_permanent(scenario.game, avacyn)
    scenario.game.put_triggers_on_stack()

    assert avacyn.name == AVACYN
    assert scenario.stack_names() == []
