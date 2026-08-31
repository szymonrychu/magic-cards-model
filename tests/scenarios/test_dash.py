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

Three abilities, and this file covers all three. The second and third both hang
off "was the dash cost paid", which the engine records - `Game.note_cast` keeps
the keyword on the cast record, and that record deliberately survives the
permanent spell's resolution - so both are answered from
`Game.was_cast_with(spell, "Dash")` as the permanent enters:

- the delayed trigger has exactly the shape warp's does (CR 603.7, CR 608.3g),
  and `Game._create_resolution_delayed_triggers` builds both;
- haste is a static ability (CR 702.10a) granting a keyword in layer 6
  (CR 613.1f), built there too as a plain `Layer.ABILITY` continuous effect
  scoped to the exact permanent that just entered - so no `LAYER_EFFECTS`
  registry entry, and no new fact on the layer context, was needed for it.

Ragavan, Nimble Pilferer is the printing in this pool: `Dash {1}{R}` on a {R}
creature, so the dash cost is *more* than the mana cost - which is exactly the
point of it, and a good check that this is an alternative cost and not a
discount (CR 118.9c).
"""

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

    The record is what the two tests below are built on: it survives the
    permanent spell's resolution, so "was the dash cost paid" is answerable at
    the moment the permanent enters, which is when both abilities need it.
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


def test_a_dashed_creature_has_haste():
    """CR 702.109a: "As long as this permanent's dash cost was paid, it has haste"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ragavan = dash_it(scenario)

    assert has_keyword(ragavan, Keyword.HASTE, scenario.game)


def test_a_dashed_creature_goes_back_to_hand_at_the_next_end_step():
    """CR 702.109a: "return the permanent this spell becomes to its owner's hand
    at the beginning of the next end step".

    `Game._create_resolution_delayed_triggers` now builds dash's delayed
    trigger the same way it already built warp's - `machines/delayed.py`'s
    `return_subject_to_hand` is the executor, shared with Aether Membrane's
    "return that creature to its owner's hand at end of combat".

    The turn is walked with `scenario.advance()` rather than jumped to with
    `start_at`: CR 500.6's "a step began" event is what `Game.advance` emits,
    and a delayed trigger only fires off that event - `start_at` moves the
    turn machine directly and fires nothing, so it would never trigger this
    even once the executor existed.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ragavan = dash_it(scenario)

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert ragavan.zone is Zone.HAND
