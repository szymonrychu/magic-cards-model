"""What a hypothetical land's entering triggers do to the answer.

A land entering can trigger abilities: Amulet of Vigor untaps a permanent
that entered tapped, Lotus Cobra adds mana, a surveil land looks at the top
card. In a real game those go on the stack before anyone can cast a sorcery-
speed spell, so a payability answer that ignores them is wrong. The copy the
answer is worked out on resolves every trigger that needs nobody to choose
anything through the engine itself, and names every trigger that does need a
choice instead of guessing its answer.

The prediction still reports how the land *enters* - tapped, for a surveil
land - because the trigger happens after the land is on the battlefield, and
says so in a notice when a trigger would change that.

Rules, each read in full with `mise run rules:find` in the session that wrote
this file:

- **CR 603.2** - an ability triggers when its trigger event happens.
- **CR 603.3 / 603.3b** - a triggered ability is put on the stack the next
  time a player would receive priority, after the event, in APNAP order.
- **CR 605.1b** - a triggered ability that adds mana is a mana ability only if
  it triggers from a mana ability or from mana being added; Lotus Cobra's
  landfall triggers from a land entering, so it uses the stack.
- **CR 704.3** - state-based actions are checked before triggers go on the
  stack.
"""

from magic_cards_model.machines import EntersState, Step, payability, predict_enters
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(hand, battlefield=(), library=("Island",)):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=list(battlefield), library=list(library))
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _payability(scenario, card, land):
    return payability(
        scenario.game,
        "alice",
        scenario.find(card, Zone.HAND, "alice"),
        assuming_land=scenario.find(land, Zone.HAND, "alice"),
    )


# --------------------------------------------------------------------------
# A choice-free trigger is resolved on the copy
# --------------------------------------------------------------------------


def test_amulet_of_vigor_untaps_a_surveil_land_so_psychic_frog_is_payable():
    scenario = _board(
        ["Psychic Frog", "Undercity Sewers"], battlefield=["Swamp", "Amulet of Vigor"]
    )

    report = _payability(scenario, "Psychic Frog", "Undercity Sewers")

    assert report.payable
    assert report.assumed_land.state is EntersState.TAPPED
    assert any("Amulet of Vigor" in notice for notice in report.assumed_land.notices)


def test_the_surveil_trigger_needs_a_choice_and_is_named_not_guessed():
    scenario = _board(
        ["Psychic Frog", "Undercity Sewers"], battlefield=["Swamp", "Amulet of Vigor"]
    )

    report = _payability(scenario, "Psychic Frog", "Undercity Sewers")

    assert any("Undercity Sewers" in notice for notice in report.notices)


def test_the_prediction_reports_entering_tapped_with_an_untap_notice():
    scenario = _board(["Undercity Sewers"], battlefield=["Amulet of Vigor"])

    prediction = predict_enters(
        scenario.game, "alice", scenario.find("Undercity Sewers", Zone.HAND, "alice")
    )

    assert prediction.state is EntersState.TAPPED
    assert any("Amulet of Vigor" in notice and "603.3" in notice for notice in prediction.notices)


def test_without_amulet_the_surveil_land_stays_tapped():
    scenario = _board(["Psychic Frog", "Undercity Sewers"], battlefield=["Swamp"])

    report = _payability(scenario, "Psychic Frog", "Undercity Sewers")

    assert not report.payable
    assert not any("Amulet" in notice for notice in report.assumed_land.notices)


# --------------------------------------------------------------------------
# A trigger that needs a choice is named, never guessed
# --------------------------------------------------------------------------


def test_lotus_cobras_color_is_not_guessed():
    """Island makes {U}; Psychic Frog also needs {B}, which Lotus Cobra's
    landfall could make only if a color were chosen for alice."""
    scenario = _board(["Psychic Frog", "Island"], battlefield=["Lotus Cobra"])

    report = _payability(scenario, "Psychic Frog", "Island")

    assert not report.payable
    assert any("Lotus Cobra" in notice for notice in report.notices)


def test_an_answer_with_no_triggers_has_no_notices():
    scenario = _board(["Psychic Frog", "Island"], battlefield=["Swamp"])

    report = _payability(scenario, "Psychic Frog", "Island")

    assert report.payable
    assert report.notices == ()


# --------------------------------------------------------------------------
# Side-effect free
# --------------------------------------------------------------------------


def test_resolving_triggers_on_the_copy_mutates_nothing():
    scenario = _board(
        ["Psychic Frog", "Undercity Sewers", "Island"],
        battlefield=["Swamp", "Amulet of Vigor", "Lotus Cobra"],
    )
    before = scenario.game.model_dump_json()

    _payability(scenario, "Psychic Frog", "Undercity Sewers")
    _payability(scenario, "Psychic Frog", "Island")
    predict_enters(scenario.game, "alice", scenario.find("Undercity Sewers", Zone.HAND, "alice"))

    assert scenario.game.model_dump_json() == before
