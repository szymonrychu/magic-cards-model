"""Elder Gargaroth's modal attack/block trigger (CR 700.2, CR 603.3c).

"Whenever this creature attacks or blocks, choose one -
* Create a 3/3 green Beast creature token.
* You gain 3 life.
* Draw a card."

Two engine gaps this file closes together:

- **CR 508.1/509.1 have no single `TriggerEvent` for "attacks or blocks"**:
  `machines/triggers._expand_attacks_or_blocks` reads the compound condition
  into two separate `TriggeredAbility`s, one per event, so the ability really
  triggers on a block and not only on an attack.
- **CR 700.2's own modal templating is a *triggered* ability here, not a
  spell**: `machines/abilities._merge_modal_bullet_lines` keeps a trigger
  line's own bullets attached to it rather than letting them parse as three
  orphaned static lines, and `machines/effects._resolve_modal_triggered_
  ability_clause` is what actually asks the new `DecisionKind.CHOOSE_A_MODE`
  question and runs the chosen mode.

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 700.2, 700.2a, 603.3c, 508.1, 509.1.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Elder Gargaroth"], library=["Forest"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def resolve_all(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def test_attacking_and_choosing_the_token_mode_creates_a_beast():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gargaroth = scenario.creature("Elder Gargaroth", "alice")
    scenario.will_choose_mode("Create a 3/3 green Beast creature token.")

    scenario.attack_with(gargaroth)
    resolve_all(scenario)

    tokens = [
        state for state in scenario.game.battlefield if state.token and "Beast" in state.subtypes
    ]
    assert len(tokens) == 1
    assert (tokens[0].power, tokens[0].toughness) == (3, 3)


def test_attacking_and_choosing_the_life_mode_gains_three_life():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gargaroth = scenario.creature("Elder Gargaroth", "alice")
    scenario.will_choose_mode("You gain 3 life.")
    before = scenario.player("alice").life

    scenario.attack_with(gargaroth)
    resolve_all(scenario)

    assert scenario.player("alice").life == before + 3


def test_blocking_also_triggers_it_not_only_attacking():
    """The compound-condition fix: a Gargaroth that blocks and never attacks
    still triggers - CR 508.1/509.1's own two separate events, both watched.

    Elder Gargaroth sits on the *defending* side here (bob's), since only
    the active player's creatures may attack - alice attacks with her own
    Grizzly Bears and bob's Gargaroth blocks it.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Elder Gargaroth"], library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    gargaroth = scenario.creature("Elder Gargaroth", "bob")
    scenario.will_choose_mode("Draw a card.")
    hand_before = len(scenario.player("bob").hand)

    scenario.attack_with(bears)
    resolve_all(scenario)  # nothing to resolve from the attack itself

    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.block(bears, gargaroth)
    resolve_all(scenario)

    assert len(scenario.player("bob").hand) == hand_before + 1


def test_an_unscripted_choice_defaults_to_the_first_mode():
    """CR 700.2a's choice is mandatory - an unscripted answer still has to
    pick something, and the documented default is the first printed mode
    (the same "first offered option" convention `DecisionKind.CHOOSE_A_
    QUALITY` already uses)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gargaroth = scenario.creature("Elder Gargaroth", "alice")

    scenario.attack_with(gargaroth)
    resolve_all(scenario)

    tokens = [
        state for state in scenario.game.battlefield if state.token and "Beast" in state.subtypes
    ]
    assert len(tokens) == 1
