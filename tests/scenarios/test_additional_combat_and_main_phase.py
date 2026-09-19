"""Aggravated Assault's own second instruction: "After this main phase,
there is an additional combat phase followed by an additional main phase."
CR 500.8's phase-adding mechanism, built this session as new turn-structure
support (`TurnMachine.extra_phase_queue`/`insert_extra_phase`) - not scoped
to this one card's own wording, any future card printing the identical
sentence reads through the same clause reader.

Verified this session with `mise run rules:find` (on-disk CR effective
2026-09-25; `knowledge_search` was not reachable from this session, so both
rules below were confirmed only against the primary on-disk text):

- **CR 500.8** - "Some effects can add phases to a turn. They do this by
  adding the phases directly after the specified phase. If multiple extra
  phases are created after the same phase, the most recently created phase
  will occur first."
- **CR 505.1a** - "Only the first main phase of the turn is a precombat
  main phase. All other main phases are postcombat main phases. ... It is
  also true of a turn in which an effect has caused an additional combat
  phase and an additional main phase to be created." - the additional main
  phase this reads is therefore `Step.POSTCOMBAT_MAIN`, whichever main
  phase it was added after.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_aggravated_assault_untaps_creatures_and_inserts_an_extra_combat_and_main_phase() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Aggravated Assault", "Grizzly Bears", "Serra Angel"] + ["Mountain"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assault = scenario.find("Aggravated Assault", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    bears.tap()
    angel.tap()

    scenario.activate(
        assault,
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain", "Mountain"),
    )
    scenario.resolve_top()

    assert not bears.tapped
    assert not angel.tapped

    # Walk the rest of the turn, recording every step reached. `Game.advance`
    # skips declare-blockers/combat-damage when no attackers were declared
    # (pre-existing combat behavior, untouched by this change), so the exact
    # step sequence is not asserted whole - what CR 500.8/505.1a actually
    # promise is checked instead: a *second* beginning-of-combat happens
    # before the turn reaches its end step at all (the extra combat phase,
    # ahead of the turn's own scheduled one), and postcombat main is reached
    # twice - the additional main phase, then the turn's own real one -
    # before the end step, never zero and never once.
    steps: list[Step] = [scenario.step]
    while steps[-1] is not Step.END_STEP:
        steps.append(scenario.advance())

    assert steps.count(Step.BEGINNING_OF_COMBAT) == 2, (
        "the extra combat phase and the turn's own real one, both before the end step"
    )
    assert steps.count(Step.POSTCOMBAT_MAIN) == 2, (
        "the additional main phase (CR 505.1a) and the turn's own real postcombat main"
    )
    first_postcombat_main = steps.index(Step.POSTCOMBAT_MAIN)
    second_beginning_of_combat = steps.index(
        Step.BEGINNING_OF_COMBAT, steps.index(Step.END_OF_COMBAT) + 1
    )
    assert first_postcombat_main < second_beginning_of_combat, (
        "the additional main phase runs before the turn's own combat phase (CR 500.8's "
        "'directly after the specified phase'), not after it"
    )


def test_a_second_activation_during_the_additional_main_phase_chains_another_extra_combat() -> None:
    """Aggravated Assault's own headline combo: activated again *during* the
    additional main phase its first activation created, it queues a second
    extra combat-then-main - directly after the phase now in progress, so
    before the turn's own real combat phase, which is still owed once both
    rounds of extras finish. Proves `insert_extra_phase`'s own "leave the
    original return point alone" behavior, not only a single insertion.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Aggravated Assault"] + ["Mountain"] * 10)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assault = scenario.find("Aggravated Assault", Zone.BATTLEFIELD, "alice")

    scenario.activate(assault, *scenario.untapped_sources(*["Mountain"] * 5))
    scenario.resolve_top()

    steps: list[Step] = [scenario.step]
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        steps.append(scenario.advance())
    # Now sitting in the first additional main phase - activate again.
    scenario.activate(assault, *scenario.untapped_sources(*["Mountain"] * 5))
    scenario.resolve_top()

    while steps[-1] is not Step.END_STEP:
        steps.append(scenario.advance())

    assert steps.count(Step.BEGINNING_OF_COMBAT) == 3, (
        "two extra combats plus the turn's own real one"
    )
    assert steps.count(Step.POSTCOMBAT_MAIN) == 3, (
        "two extra main phases plus the turn's own real postcombat main"
    )
