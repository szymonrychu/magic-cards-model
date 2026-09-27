"""Alliance (CR 207.2c ability word): "Whenever another creature you control
enters, choose one that hasn't been chosen this turn." followed by a
bulleted CR 700.2 modal list.

Lita, Little Orphan Amphibian prints the ability word and the exclusivity
tail with a plain period, not the trailing em dash every other bulleted modal
header in the pool already used - `machines/abilities._MODAL_INSTRUCTION_
TAIL` never folded the bullets under it into the trigger's own effect text,
so each bullet parsed as its own orphaned, unconditioned static line and the
whole mechanic did nothing (`docs/card_coverage/271-tmt/status.md`'s own
"the bullet lines are currently misread as statics").

Once the header merges correctly, the actual per-turn exclusivity is not new
machinery at all: `CardState.chosen_modal_options_this_turn` and `Game.
_announce_trigger_modes`'s own "hasn't been chosen this turn" branch were
already built for The Vision - this file is the first *bulleted* card to
reach that path, and Gala Greeters (a second, non-listed Alliance printing,
verified Modern/Pioneer legal) is the proof it is the mechanism, not the card,
that was fixed.

CR numbers verified this session with `mise run rules:find`:

- **CR 207.2c** - Alliance and Disappear are both ability words: no rules
  meaning of their own, grouping cards with similar functionality.
- **CR 700.2b/700.2d** - a modal triggered ability's modes are chosen as it
  goes on the stack; a mode can't be repeated unless the card says so, which
  "hasn't been chosen this turn" narrows further, to once *per turn* rather
  than once *ever*.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

LITA_COUNTER = "Put a +1/+1 counter on Lita."
LITA_FOOD = "Create a Food token."
LITA_SCRY = "Scry 1."


def _lita_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Hill Giant", "Elite Vanguard"],
            battlefield=["Lita, Little Orphan Amphibian", "Forest", "Forest", "Forest"],
        )
        .player("bob")
    )


def test_the_first_creature_entering_may_choose_the_counter_mode():
    scenario = _lita_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lita = scenario.creature("Lita, Little Orphan Amphibian", "alice")
    scenario.will_choose_mode(LITA_COUNTER, username="alice")

    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.pass_until_resolved()

    assert lita.counters[Counter.PLUS_ONE] == 1
    assert lita.chosen_modal_options_this_turn == (LITA_COUNTER,)


def test_the_chosen_mode_is_not_offered_again_this_turn():
    """CR 700.2d narrowed to "this turn": the second creature to enter this
    turn is offered only the two modes not yet chosen."""
    scenario = _lita_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lita = scenario.creature("Lita, Little Orphan Amphibian", "alice")
    scenario.will_choose_mode(LITA_COUNTER, username="alice")
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.pass_until_resolved()

    scenario.will_choose_mode(LITA_FOOD, username="alice")
    scenario.put_onto_battlefield("Hill Giant", "alice")
    scenario.pass_until_resolved()

    asked = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_A_MODE and question.source == lita.name
    ]
    assert len(asked) == 2
    assert set(asked[1].options) == {LITA_FOOD, LITA_SCRY}, "counter mode already used this turn"
    assert lita.counters[Counter.PLUS_ONE] == 1
    foods = [state for state in scenario.game.battlefield if state.name == "Food Token"]
    assert len(foods) == 1


def test_the_third_creature_this_turn_is_only_offered_the_last_mode():
    scenario = _lita_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lita = scenario.creature("Lita, Little Orphan Amphibian", "alice")
    scenario.will_choose_mode(LITA_COUNTER, username="alice")
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.pass_until_resolved()
    scenario.will_choose_mode(LITA_FOOD, username="alice")
    scenario.put_onto_battlefield("Hill Giant", "alice")
    scenario.pass_until_resolved()

    scenario.will_choose_mode(LITA_SCRY, username="alice")
    scenario.put_onto_battlefield("Elite Vanguard", "alice")
    scenario.pass_until_resolved()

    asked = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_A_MODE and question.source == lita.name
    ]
    assert len(asked) == 3
    assert asked[2].options == (LITA_SCRY,)
    assert set(lita.chosen_modal_options_this_turn) == {LITA_COUNTER, LITA_FOOD, LITA_SCRY}


def test_the_exclusivity_resets_on_the_next_turn():
    scenario = _lita_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lita = scenario.creature("Lita, Little Orphan Amphibian", "alice")
    scenario.will_choose_mode(LITA_COUNTER, username="alice")
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.pass_until_resolved()
    assert lita.chosen_modal_options_this_turn == (LITA_COUNTER,)

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.turn_based_actions()  # CR 514.2: cleanup's own turn-based action
    scenario.advance()  # into bob's turn
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()  # back to alice's turn
    assert lita.chosen_modal_options_this_turn == (), "cleared at cleanup each turn"

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_mode(LITA_COUNTER, username="alice")
    scenario.put_onto_battlefield("Hill Giant", "alice")
    scenario.pass_until_resolved()

    assert lita.counters[Counter.PLUS_ONE] == 2


# -- Gala Greeters: a second Alliance printing, proving the mechanism -------


def test_gala_greeters_offers_its_own_three_modes_with_the_identical_exclusivity():
    """Gala Greeters (Kamigawa: Neon Dynasty, verified Modern/Pioneer legal,
    not one of the listed tmt cards, not in any deck under `decks/*.txt`):
    "Alliance — Whenever another creature you control enters, choose one
    that hasn't been chosen this turn — • Put a +1/+1 counter on this
    creature. • Create a tapped Treasure token. • You gain 2 life." Same
    ability-word shape, different bullets and a different self-reference
    ("this creature" rather than the legend's own printed name) - proof this
    reads the template, not Lita specifically.
    """
    counter_mode = "Put a +1/+1 counter on this creature."
    treasure_mode = "Create a tapped Treasure token."
    life_mode = "You gain 2 life."

    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Hill Giant"],
            battlefield=["Gala Greeters", "Forest", "Forest"],
        )
        .player("bob")
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    greeters = scenario.creature("Gala Greeters", "alice")
    scenario.will_choose_mode(counter_mode, username="alice")
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.pass_until_resolved()
    assert greeters.counters[Counter.PLUS_ONE] == 1

    scenario.will_choose_mode(life_mode, username="alice")
    scenario.put_onto_battlefield("Hill Giant", "alice")
    scenario.pass_until_resolved()

    asked = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_A_MODE and question.source == greeters.name
    ]
    assert set(asked[1].options) == {treasure_mode, life_mode}
    assert scenario.player("alice").life == 22
