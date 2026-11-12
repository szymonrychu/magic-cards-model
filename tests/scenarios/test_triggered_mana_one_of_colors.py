"""Scenario: a triggered ability that adds "{R} or {G}" - one mana, of a colour
its controller picks from a printed list, as the ability resolves.

Printings (oracle text read from the pool this session):

- Dal R'El, Augment Orphan (TRK): "Landfall - Whenever a land you control
  enters, add {R} or {G}."
- Kessig Naturalist (MID, the proof printing: Modern legal, not a listed card,
  not in the pool's decks): "Whenever this creature attacks, add {R} or {G}.
  Until end of turn, you don't lose this mana as steps and phases end." - a
  different trigger condition, and the retention rider on the same shape.
- Lotus Cobra stays a regression: its "one mana of any color" is the same
  trigger with five options.

Rules, each looked up with `mise run rules:find` in the session that wrote this
file:

- **CR 106.4** - added mana goes into the player's mana pool.
- **CR 605.1b / CR 605.5a** - a triggered ability is a mana ability only when it
  triggers from a mana ability or from mana being added; a land entering
  neither is, so these triggers use the stack and can be responded to.
- **CR 608.2d** - the choice of colour is made as the ability resolves.
- **CR 500.5** - the pool empties as a step or phase ends; **CR 500.5b** /
  **CR 514.2** give "until end of turn" retention its special rule, which the
  Kessig Naturalist rider uses.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_triggered_mana
from magic_cards_model.models import Color
from tests.scenarios.harness import Scenario


def _dal_board(*, hand=("Forest",), bob_hand=()) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=list(hand), battlefield=["Dal R'El, Augment Orphan"])
        .player("bob", hand=list(bob_hand))
    )


def _land_and_resolve(scenario, land="Forest", username="alice"):
    scenario.play_land(land, username)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()


# -- what the text reads -------------------------------------------------------


def test_a_two_colour_list_reads_as_one_choice_between_them():
    shape = parse_triggered_mana("add {R} or {G}.")

    assert shape is not None
    assert shape.one_of == (Color.RED, Color.GREEN)
    assert shape.colors == ()


def test_a_three_colour_list_reads_in_order():
    shape = parse_triggered_mana("add {W}, {U}, or {B}.")

    assert shape is not None
    assert shape.one_of == (Color.WHITE, Color.BLUE, Color.BLACK)


def test_two_symbols_with_no_or_stay_both_added():
    """ "Add {R}{G}" is two mana, not a choice: the list reading must not steal it."""
    shape = parse_triggered_mana("add {R}{G}.")

    assert shape is not None
    assert shape.one_of == ()
    assert shape.colors == (Color.RED, Color.GREEN)


def test_may_add_a_listed_colour_is_optional_and_keeps_the_list():
    shape = parse_triggered_mana("that player may add {G} or {W}.")

    assert shape is not None
    assert shape.optional
    assert shape.one_of == (Color.GREEN, Color.WHITE)


def test_the_retention_rider_and_the_spend_restriction_join_the_list():
    shape = parse_triggered_mana(
        "add {R} or {G}. Until end of turn, you don't lose this mana as steps and phases end."
    )

    assert shape is not None
    assert shape.one_of == (Color.RED, Color.GREEN)
    assert shape.retain_until_end_of_turn is True
    assert parse_triggered_mana("add {R} or {G}.").retain_until_end_of_turn is False


def test_the_payment_search_offers_each_listed_colour_per_mana_added():
    """What a tap would add if this list were a CR 605.1b triggered mana ability:
    one alternative per way of choosing, here three for two mana of two colours."""
    from magic_cards_model.machines.cost.payment import _triggered_mana_alternatives

    scenario = _dal_board().build()
    dal = scenario.creature("Dal R'El, Augment Orphan", "alice")
    shape = parse_triggered_mana("add {R} or {G}.")

    alternatives = _triggered_mana_alternatives(shape, dal, dal, [Color.RED], 2, scenario.game)

    assert sorted(sorted(c.value for c in option) for option in alternatives) == [
        ["G", "G"],
        ["G", "R"],
        ["R", "R"],
    ]


@pytest.mark.parametrize("text", ["add {R} or {R}.", "add {R} or.", "add {R} or {G} and {B}."])
def test_a_malformed_list_fails_closed(text):
    shape = parse_triggered_mana(text)

    assert shape is None or not shape.one_of


# -- Dal R'El ------------------------------------------------------------------


def test_landfall_adds_the_red_the_controller_chose():
    scenario = _dal_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("R", source="Dal R'El, Augment Orphan")

    _land_and_resolve(scenario)

    pool = scenario.player("alice").mana_pool
    assert pool.floating.get(Color.RED) == 1
    assert pool.total == 1


def test_landfall_adds_the_green_the_controller_chose():
    scenario = _dal_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("G", source="Dal R'El, Augment Orphan")

    _land_and_resolve(scenario)

    pool = scenario.player("alice").mana_pool
    assert pool.floating.get(Color.GREEN) == 1
    assert pool.total == 1


def test_the_question_offers_only_the_two_printed_colours():
    """CR 608.2d: no illegal option - not blue, not white, not colourless."""
    scenario = _dal_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("R")

    _land_and_resolve(scenario)

    (question,) = scenario.questions_asked()
    assert set(question.options) == {"R", "G"}
    assert question.player == "alice"


def test_a_colour_outside_the_list_is_refused():
    scenario = _dal_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("U")

    with pytest.raises(ValueError):
        _land_and_resolve(scenario)


def test_the_trigger_uses_the_stack_and_adds_nothing_until_it_resolves():
    """CR 605.5a: a land entering is not a mana ability's event."""
    scenario = _dal_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("G")

    scenario.play_land("Forest")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Dal R'El, Augment Orphan's triggered ability"]
    assert scenario.player("alice").mana_pool.total == 0
    scenario.resolve_top()
    assert scenario.player("alice").mana_pool.floating.get(Color.GREEN) == 1


def test_an_opponents_land_does_not_trigger_it():
    scenario = _dal_board(bob_hand=("Mountain",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Mountain", "bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert scenario.questions_asked() == []


def test_a_nonland_permanent_entering_does_not_trigger_it():
    scenario = _dal_board(hand=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_each_land_asks_again_and_may_choose_differently():
    scenario = _dal_board(hand=("Forest", "Mountain")).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("R")
    scenario.will_choose("G")

    scenario.put_onto_battlefield("Forest", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    scenario.put_onto_battlefield("Mountain", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    pool = scenario.player("alice").mana_pool
    assert pool.floating.get(Color.RED) == 1
    assert pool.floating.get(Color.GREEN) == 1


def test_two_controlled_dals_each_add_a_mana():
    """Each is its own trigger, so each asks its own question (CR 603.2c)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Forest"],
            battlefield=["Dal R'El, Augment Orphan", "Dal R'El, Augment Orphan"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.play_land("Forest")
    scenario.game.put_triggers_on_stack()

    assert len(scenario.game.stack) == 2
    scenario.will_choose("R", times=2)
    scenario.resolve_top()
    scenario.resolve_top()
    assert scenario.player("alice").mana_pool.total == 2


def test_the_mana_empties_at_the_end_of_the_step():
    """No retention clause on Dal R'El: CR 500.5 empties the pool."""
    scenario = _dal_board().manual_turn_based_actions().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("R")
    _land_and_resolve(scenario)
    assert scenario.player("alice").mana_pool.total == 1

    scenario.advance()
    scenario.turn_based_actions()

    assert scenario.player("alice").mana_pool.total == 0


def test_the_mana_pays_for_a_spell_cast_with_it():
    """The chosen mana is ordinary mana in the pool: the Shock it pays for resolves."""
    scenario = _dal_board(hand=("Forest", "Shock")).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("R")
    _land_and_resolve(scenario)

    scenario.cast_and_resolve("Shock", targets=["bob"])

    assert scenario.player("bob").life == 18
    assert scenario.player("alice").mana_pool.total == 0


# -- Kessig Naturalist: the proof printing --------------------------------------


def _naturalist_board():
    return (
        Scenario()
        .player("alice", battlefield=["Kessig Naturalist"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )


def test_an_attack_trigger_adds_the_chosen_colour():
    scenario = _naturalist_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    naturalist = scenario.creature("Kessig Naturalist", "alice")
    naturalist.summoning_sick = False
    scenario.will_choose("G")

    scenario.attack_with(naturalist)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    pool = scenario.player("alice").mana_pool
    assert pool.floating.get(Color.GREEN) == 1
    assert pool.total == 1


def test_the_retention_rider_keeps_the_chosen_mana_to_the_end_of_the_turn():
    """CR 500.5b: "until end of turn" retention - the mana survives the end of
    combat and the cleanup step's start, and goes at CR 514.2's cleanup."""
    scenario = _naturalist_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    naturalist = scenario.creature("Kessig Naturalist", "alice")
    naturalist.summoning_sick = False
    scenario.will_choose("R")
    scenario.attack_with(naturalist)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    pool = scenario.player("alice").mana_pool

    scenario.advance()  # declare blockers
    scenario.advance()  # combat damage
    scenario.advance()  # end of combat
    scenario.advance()  # postcombat main
    assert pool.floating.get(Color.RED) == 1

    scenario.advance()  # end step
    scenario.advance()  # cleanup
    scenario.turn_based_actions()
    assert pool.total == 0
    assert pool.retained == []


def test_the_attack_trigger_does_not_fire_for_a_creature_that_does_not_attack():
    scenario = _naturalist_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.total == 0
