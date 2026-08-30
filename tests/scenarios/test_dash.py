"""Dash: a cheap creature that leaves at the end of the turn (CR 702.109).

CR 702.109a: "Dash represents **three abilities**: two static abilities that
function while the card with dash is on the stack, one of which may create a
delayed triggered ability, and a static ability that functions while the object
with dash is on the battlefield. 'Dash [cost]' means "You may cast this card by
paying [cost] rather than its mana cost," "If this spell's dash cost was paid,
return the permanent this spell becomes to its owner's hand at the beginning of
the next end step," and "As long as this permanent's dash cost was paid, it has
haste." Casting a spell for its dash cost follows the rules for paying
alternative costs in rules 601.2b and 601.2f-h."

Three abilities, and this file covers the first. The second and third both hang
off "was the dash cost paid", which the engine records - `Game.note_cast` keeps
the keyword on the cast record - and neither is acted on:

- the delayed trigger has exactly the shape warp's does (CR 603.7, CR 608.3g),
  and `Game._create_resolution_delayed_triggers` builds warp's and not dash's;
- haste is a static ability granting a keyword in layer 6 (CR 613.1f), and what
  a card generates is the hand-written `LAYER_EFFECTS` registry.

Both are xfails at the bottom, and both are named in `docs/engine-coverage.md`.

Ragavan, Nimble Pilferer is the printing in this pool: `Dash {1}{R}` on a {R}
creature, so the dash cost is *more* than the mana cost - which is exactly the
point of it, and a good check that this is an alternative cost and not a
discount (CR 118.9c).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ragavan, Nimble Pilferer"], battlefield=["Mountain", "Mountain"])
        .player("bob")
    )


def test_dash_hands_out_a_way_to_cast_from_hand():
    """CR 702.109a's first ability, as a CR 601.3 permission."""
    options = [
        option
        for option in keyword_cast_options(card("Ragavan, Nimble Pilferer"))
        if option.keyword.lower() == "dash"
    ]
    (option,) = options
    assert option.zone is Zone.HAND
    assert option.pays_mana_cost is False  # an alternative cost, CR 118.9


def test_the_dash_cost_replaces_the_mana_cost_even_when_it_is_dearer():
    """CR 118.9c: an alternative cost does not change the printed mana cost.

    Ragavan is {R} and dashes for {1}{R}. Paying more is still an alternative
    cost, not a cost increase, which is what makes the distinction worth a test.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ragavan, Nimble Pilferer")
    assert casting.base_cost == ManaCost.parse("{R}")

    casting.use_keyword("Dash")

    assert casting.total_cost.mana == ManaCost.parse("{1}{R}")
    assert casting.base_cost == ManaCost.parse("{R}")


def test_a_dashed_creature_reaches_the_battlefield():
    """The whole first ability, played out."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ragavan, Nimble Pilferer")
    casting.use_keyword("Dash")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    ragavan = scenario.resolve_top()

    assert ragavan.zone is Zone.BATTLEFIELD


def test_the_cast_record_remembers_the_dash_cost_was_paid():
    """CR 702.109a's other two abilities both read "was the dash cost paid".

    Nothing acts on it yet, but the answer is kept, which is what makes the two
    xfails below a wiring gap rather than a missing fact.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ragavan, Nimble Pilferer")
    casting.use_keyword("Dash")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    spell = casting.cast()

    assert scenario.game.was_cast_with(spell, "Dash")


def test_casting_it_normally_records_no_keyword():
    """The control: a Ragavan cast for {R} has no dash cost paid."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ragavan, Nimble Pilferer")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain"))
    spell = casting.cast()

    assert not scenario.game.was_cast_with(spell, "Dash")


def dash_it(scenario):
    casting = scenario.cast("Ragavan, Nimble Pilferer")
    casting.use_keyword("Dash")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


@pytest.mark.xfail(
    reason=(
        "CR 702.109a's third ability grants haste in layer 6 (CR 613.1f) for as long "
        "as the dash cost was paid. What a card generates is the hand-written "
        "LAYER_EFFECTS registry in machines/layers.py, which has no dash entry. "
        "See docs/engine-coverage.md."
    ),
    strict=True,
)
def test_a_dashed_creature_has_haste():
    """CR 702.109a: "As long as this permanent's dash cost was paid, it has haste"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ragavan = dash_it(scenario)

    assert has_keyword(ragavan, Keyword.HASTE, scenario.game)


@pytest.mark.xfail(
    reason=(
        "CR 702.109a's second ability is a delayed triggered ability (CR 603.7) created "
        "as the permanent enters (CR 608.3g). Game._create_resolution_delayed_triggers "
        "builds warp's and nothing builds dash's. See docs/engine-coverage.md."
    ),
    strict=True,
)
def test_a_dashed_creature_goes_back_to_hand_at_the_next_end_step():
    """CR 702.109a: "return the permanent this spell becomes to its owner's hand
    at the beginning of the next end step"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ragavan = dash_it(scenario)

    scenario.start_at(Step.END_STEP)
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert ragavan.zone is Zone.HAND
