"""Scenario: a modal triggered ability that says "choose up to X -" / "choose
up to one -".

The Ruinous Wrecking Crew: "The Ruinous Wrecking Crew enters with X +1/+1
counters on it. When The Ruinous Wrecking Crew enters, choose up to X - •
Discard a card, then draw a card. • Target opponent loses 2 life. • Destroy
target token. • Each player sacrifices a creature of their choice."

X there is the X paid to cast it (CR 107.3m), so the number of modes a player
may choose is what they spent on X - and "up to" lets them choose none, which
removes the ability (CR 700.2b / CR 603.3c). Sawblade Slinger (VOW, not listed,
not in a deck) prints the fixed-count twin: "When this creature enters,
choose up to one - • Destroy target artifact an opponent controls. • This
creature fights target Zombie an opponent controls."

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 107.3m** - an enters-the-battlefield triggered ability that refers to X
  uses the X chosen for the spell that became the object.
- **CR 603.3c** - a modal triggered ability's modes are announced as it goes
  on the stack; a mode with no legal target can't be chosen; "If no mode is
  chosen, the ability is removed from the stack."
- **CR 700.2b** - the same rule, from the modal side.
- **CR 700.2d** - a mode can't be chosen more than once unless the ability
  says so.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.effects import NO_FURTHER_MODES
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

CREW = "The Ruinous Wrecking Crew"
LOOT = "Discard a card, then draw a card."
DRAIN = "Target opponent loses 2 life."
TOKEN = "Destroy target token."
EDICT = "Each player sacrifices a creature of their choice."


def _crew_board(lands: int, *, bob: tuple[str, ...] = ("Grizzly Bears",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[CREW, "Forest"],
            battlefield=["Swamp", "Mountain"] + ["Swamp"] * lands,
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_crew(scenario, x_value: int):
    sources = scenario.untapped_sources(
        "Swamp", "Mountain", *(["Swamp"] * x_value), username="alice"
    )
    casting = scenario.cast(CREW, "alice")
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    crew = scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    return crew


def _resolve_all(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def _mode_questions(scenario):
    return [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_A_MODE]


def test_x_two_chooses_two_modes():
    scenario = _crew_board(2)
    scenario.will_choose_mode(DRAIN, username="alice")
    scenario.will_choose_mode(LOOT, username="alice")
    scenario.will_choose_targets(scenario.player("bob"), username="alice")
    scenario.will_discard(scenario.find("Forest", Zone.HAND, "alice"), username="alice")

    crew = _cast_crew(scenario, 2)
    _resolve_all(scenario)

    assert crew.counter_count(Counter.PLUS_ONE) == 2
    assert scenario.player("bob").life == 18
    assert scenario.find("Forest", Zone.GRAVEYARD, "alice") is not None
    assert len(scenario.player("alice").hand) == 1


def test_up_to_lets_a_player_stop_after_one():
    scenario = _crew_board(2)
    scenario.will_choose_mode(DRAIN, username="alice")
    scenario.will_choose_mode(NO_FURTHER_MODES, username="alice")
    scenario.will_choose_targets(scenario.player("bob"), username="alice")

    _cast_crew(scenario, 2)
    _resolve_all(scenario)

    assert scenario.player("bob").life == 18
    assert len(scenario.player("alice").hand) == 1, "the Forest is still in hand"


def test_up_to_lets_a_player_choose_none_and_the_ability_is_removed():
    """CR 700.2b: no mode chosen - the ability is removed from the stack."""
    scenario = _crew_board(2)
    scenario.will_choose_mode(NO_FURTHER_MODES, username="alice")

    _cast_crew(scenario, 2)

    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 20


def test_x_zero_offers_no_mode_at_all():
    """X is 0: "up to 0" modes - nothing is asked and nothing goes on the
    stack. The Crew is a 2/2 with no counters."""
    scenario = _crew_board(0)

    crew = _cast_crew(scenario, 0)

    assert _mode_questions(scenario) == []
    assert scenario.stack_names() == []
    assert crew.counter_count(Counter.PLUS_ONE) == 0


def test_x_one_offers_one_mode_only():
    """The count is capped at X: after one mode, nothing further is asked."""
    scenario = _crew_board(1)
    scenario.will_choose_mode(EDICT, username="alice")

    _cast_crew(scenario, 1)
    _resolve_all(scenario)
    scenario.state_based_actions()

    assert len(_mode_questions(scenario)) == 1
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find(CREW, Zone.GRAVEYARD, "alice") is not None, "her only creature"


def test_a_mode_is_never_offered_twice():
    """CR 700.2d: with X = 4 a player may choose every mode, each once."""
    scenario = _crew_board(4)
    scenario.will_choose_mode(DRAIN, username="alice")
    scenario.will_choose_mode(LOOT, username="alice")
    scenario.will_choose_mode(NO_FURTHER_MODES, username="alice")
    scenario.will_choose_targets(scenario.player("bob"), username="alice")
    scenario.will_discard(scenario.find("Forest", Zone.HAND, "alice"), username="alice")

    _cast_crew(scenario, 4)

    second = _mode_questions(scenario)[1]
    assert DRAIN not in second.options
    assert LOOT in second.options


def test_a_mode_with_no_legal_target_is_not_offered():
    """CR 603.3c: with no token on the battlefield, "Destroy target token"
    can't be chosen."""
    scenario = _crew_board(1)
    scenario.will_choose_mode(DRAIN, username="alice")
    scenario.will_choose_targets(scenario.player("bob"), username="alice")

    _cast_crew(scenario, 1)

    assert TOKEN not in _mode_questions(scenario)[0].options


def test_put_onto_the_battlefield_uncast_has_no_x():
    """No spell became it, so no X was chosen: "up to 0"."""
    scenario = _crew_board(0)

    crew = scenario.put_onto_battlefield(CREW, "alice")
    scenario.game.put_triggers_on_stack()

    assert crew.zone is Zone.BATTLEFIELD
    assert _mode_questions(scenario) == []
    assert scenario.stack_names() == []


# -- the fixed-count twin: "choose up to one -" --------------------------------


def test_sawblade_slinger_may_destroy_an_artifact():
    scenario = (
        Scenario()
        .player("alice", hand=["Sawblade Slinger"])
        .player("bob", battlefield=["Ornithopter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.creature("Ornithopter", "bob")
    scenario.will_choose_mode("Destroy target artifact an opponent controls.", username="alice")
    scenario.will_choose_targets(thopter, username="alice")

    scenario.put_onto_battlefield("Sawblade Slinger", "alice")
    scenario.game.put_triggers_on_stack()
    _resolve_all(scenario)

    assert thopter.zone is Zone.GRAVEYARD


def test_sawblade_slinger_may_choose_nothing():
    scenario = (
        Scenario()
        .player("alice", hand=["Sawblade Slinger"])
        .player("bob", battlefield=["Ornithopter"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.creature("Ornithopter", "bob")
    scenario.will_choose_mode(NO_FURTHER_MODES, username="alice")

    scenario.put_onto_battlefield("Sawblade Slinger", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert thopter.zone is Zone.BATTLEFIELD


def test_sawblade_slinger_with_no_legal_target_is_removed():
    """Neither mode has a legal target, so none can be chosen (CR 603.3c)."""
    scenario = Scenario().player("alice", hand=["Sawblade Slinger"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Sawblade Slinger", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert _mode_questions(scenario) == []
