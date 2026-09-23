"""Scenario: "When `<event>`, transform `<this>` at the beginning of the next
upkeep." - a triggered ability that creates a delayed triggered ability
(`_parse_transform_self_at_next_step_clause`, `machines/delayed.
TransformSubject`).

Aang, at the Crossroads ("When another creature you control leaves the
battlefield, ...") is the reported card. Archangel Avacyn ("When a non-Angel
creature you control dies, ..."; Modern- and Pioneer-legal, in no
`magic-cards-model-api` deck) is the off-pool proof: a different trigger
event and a back face whose own "When this creature transforms into Avacyn,
the Purifier, ..." trigger is exercised in `test_transforms_into_trigger.py`.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 603.7a** - a delayed triggered ability is created during the
  resolution of the ability that makes it, and won't trigger before then.
- **CR 603.7c** - "if that object is no longer in the zone it's expected to
  be in at the time the delayed triggered ability resolves, the ability won't
  affect it. (Note that if that object left that zone and then returned, it's
  a new object and thus won't be affected. See rule 400.7.)"
- **CR 400.7** - an object that changes zones is a new object.
- **CR 701.27a** - "To transform a permanent, turn it over so that its other
  face is up."
- **CR 701.27f** - "If a delayed triggered ability of a permanent tries to
  transform that permanent, the permanent does so only if it hasn't
  transformed or converted since that delayed triggered ability was
  created." Two creatures leaving at once make two delayed triggers; only
  the first turns Aang over.
- **CR 603.2b** - "When a phase or step begins, all abilities that trigger
  'at the beginning of' that phase or step trigger."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

AANG = "Aang, at the Crossroads"
SAVIOR = "Aang, Destined Savior"
AVACYN = "Archangel Avacyn"


def _board(*battlefield: str, bob: tuple[str, ...] = ()) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=list(battlefield), library=["Forest"] * 10)
        .player("bob", battlefield=list(bob), library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_everything(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _to_next_upkeep(scenario: PlayedScenario) -> None:
    """Run the turn out and stop in the next turn's upkeep, with whatever
    triggered there on the stack (CR 603.2b)."""
    active = scenario.game.turn.active_player
    while not (scenario.step is Step.UPKEEP and scenario.game.turn.active_player != active):
        scenario.advance()
    scenario.game.put_triggers_on_stack()


def test_aang_transforms_at_the_next_upkeep_after_another_creature_leaves():
    scenario = _board(AANG, "Grizzly Bears")
    aang = scenario.creature(AANG, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.return_to_hand(bears)
    _resolve_everything(scenario)
    assert aang.name == AANG, "CR 603.7a: nothing happens until the upkeep"

    _to_next_upkeep(scenario)
    _resolve_everything(scenario)

    assert aang.zone is Zone.BATTLEFIELD
    assert aang.name == SAVIOR


def test_two_creatures_leaving_at_once_transform_aang_only_once():
    """CR 701.27f: the second delayed trigger finds Aang already transformed
    since it was created, so it leaves Aang as it is rather than turning it
    back."""
    scenario = _board(AANG, "Grizzly Bears", "Llanowar Elves")
    aang = scenario.creature(AANG, "alice")
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    scenario.game.destroy(scenario.creature("Llanowar Elves", "alice"))
    _resolve_everything(scenario)
    assert len(scenario.game.delayed_triggers.triggers) == 2

    _to_next_upkeep(scenario)
    _resolve_everything(scenario)

    assert aang.name == SAVIOR
    assert aang.times_transformed == 1


def test_aang_that_left_and_came_back_does_not_transform():
    """CR 603.7c / 400.7: the Aang that returned is a new object."""
    scenario = _board(AANG, "Grizzly Bears")
    aang = scenario.creature(AANG, "alice")
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    _resolve_everything(scenario)

    scenario.game.exile_permanent(aang)
    scenario.game.put_onto_battlefield(aang, "alice")
    _resolve_everything(scenario)
    _to_next_upkeep(scenario)
    _resolve_everything(scenario)

    assert aang.zone is Zone.BATTLEFIELD
    assert aang.name == AANG


def test_aang_gone_before_its_trigger_resolves_creates_nothing():
    scenario = _board(AANG, "Grizzly Bears")
    aang = scenario.creature(AANG, "alice")
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{AANG}'s triggered ability"]

    scenario.game.return_to_hand(aang)
    _resolve_everything(scenario)

    assert scenario.game.delayed_triggers.triggers == []


def test_aang_leaving_itself_does_not_trigger():
    """ "Another creature": Aang's own departure is not the event."""
    scenario = _board(AANG)
    scenario.game.return_to_hand(scenario.creature(AANG, "alice"))
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_an_opponent_s_creature_leaving_does_not_trigger():
    scenario = _board(AANG, bob=("Grizzly Bears",))
    scenario.game.destroy(scenario.creature("Grizzly Bears", "bob"))
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_a_noncreature_permanent_leaving_does_not_trigger():
    scenario = _board(AANG, "Forest")
    scenario.game.return_to_hand(scenario.find("Forest", Zone.BATTLEFIELD, "alice"))
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


# --------------------------------------------------------------------------
# Archangel Avacyn - the off-pool proof
# --------------------------------------------------------------------------


def test_avacyn_transforms_at_the_next_upkeep_after_a_non_angel_dies():
    scenario = _board(AVACYN, "Grizzly Bears")
    avacyn = scenario.creature(AVACYN, "alice")
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    _resolve_everything(scenario)
    assert avacyn.name == AVACYN

    _to_next_upkeep(scenario)
    _resolve_everything(scenario)

    assert avacyn.name == "Avacyn, the Purifier"


def test_an_angel_dying_does_not_transform_avacyn():
    scenario = _board(AVACYN, "Serra Angel")
    scenario.game.destroy(scenario.creature("Serra Angel", "alice"))
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
