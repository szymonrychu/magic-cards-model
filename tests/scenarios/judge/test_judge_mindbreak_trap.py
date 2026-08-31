"""Judge scenarios: a spell that targets *any number* of spells, and exiles them.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#1009** - How Does Mindbreak Trap Work?

Mindbreak Trap's real oracle text, confirmed with `resolve_cards`: "If an
opponent cast three or more spells this turn, you may pay {0} rather than pay
this spell's mana cost. / Exile any number of target spells."

Three separate rulings live in that text, and this file takes them one at a
time: how many targets "any number of target spells" allows (CR 107.1c), that
the Trap may not be one of them (CR 115.5), that the alternative cost leaves the
spell's mana cost and mana value alone (CR 118.9c), and that exiling a spell is
not countering it (CR 701.6a). Every CR number here was looked up with
`knowledge_search(type="rules")` in the session that wrote the file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import targeting_profile
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    """bob is the active player, so his creature spell is castable (CR 117.1a).

    alice holds the Trap and four Islands, which is what its printed
    {2}{U}{U} costs - the alternative cost is a separate question, below.
    """
    return (
        Scenario()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player(
            "alice",
            hand=["Mindbreak Trap"],
            battlefield=["Island", "Island", "Island", "Island"],
        )
    )


def _bears_on_the_stack(scenario):
    """bob casts Grizzly Bears and passes, so alice may respond (CR 117.3c)."""
    sources = scenario.untapped_sources("Forest", "Forest", username="bob")
    bears = scenario.cast_onto_stack("Grizzly Bears", *sources, username="bob")
    scenario.pass_priority("bob")
    return bears


# --------------------------------------------------------------------------
# "any number of target spells" (CR 107.1c)
# --------------------------------------------------------------------------


def test_any_number_of_target_spells_has_no_maximum_and_no_minimum():
    """CR 107.1c: "any number" is zero or more, so the Trap's target count is
    unbounded below as well as above.

    The episode's point about targeting nothing at all - casting the Trap purely
    for a prowess trigger - depends on the minimum being zero, which a
    Counterspell's "target spell" is not.
    """
    (requirement,) = targeting_profile(card("Mindbreak Trap")).requirements

    assert requirement.unbounded
    assert requirement.minimum == 0
    assert requirement.zones == frozenset({Zone.STACK})


def test_the_trap_may_be_cast_with_no_targets_at_all():
    """The zero end of CR 107.1c, played out rather than parsed.

    Nothing on the stack has to be aimed at: the Trap is announced legally
    (CR 601.2c chooses "the required number of targets", and the required number
    here may be none) and sits on the stack above bob's creature spell.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bears_on_the_stack(scenario)

    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")
    scenario.cast_onto_stack("Mindbreak Trap", *sources, username="alice", targets=[])

    assert scenario.stack_names() == ["Grizzly Bears", "Mindbreak Trap"]


def test_one_chosen_spell_is_recorded_as_the_traps_single_target():
    """CR 115.1: the targets are declared as the spell is cast, and they are
    what CR 608.2b rechecks on resolution.

    The episode's Misdirection line turns on the Trap having *exactly* one
    target when it has been aimed at one spell, which is what this asserts:
    one `TargetRef`, pointing at the spell on the stack.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = _bears_on_the_stack(scenario)

    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")
    trap = scenario.cast_onto_stack("Mindbreak Trap", *sources, username="alice", targets=[bears])

    assert [ref.card_id for ref in trap.targets] == [bears.id]


def test_the_trap_may_not_target_itself():
    """CR 115.5: "A spell or ability on the stack is an illegal target for
    itself."

    The refusal is real, though this engine reaches it by a different road: its
    `Casting` chooses targets while the card is still in hand rather than after
    CR 601.2a has moved it to the stack, so the Trap is refused as a target in
    the wrong *zone* rather than as itself. Either way the episode's trick - a
    Trap shielding itself from Misdirection by targeting itself - does not work.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = _bears_on_the_stack(scenario)

    casting = scenario.cast("Mindbreak Trap", username="alice")

    with pytest.raises(ValueError, match="Mindbreak Trap"):
        casting.choose_targets([casting.spell, bears])


# --------------------------------------------------------------------------
# The alternative cost (CR 118.9, 118.9c)
# --------------------------------------------------------------------------


def test_the_printed_mana_value_is_four_however_it_was_paid_for():
    """CR 118.9c: "An alternative cost doesn't change a spell's mana cost, only
    what its controller has to pay to cast it."

    This is the whole of the episode's Minor Misstep ruling: the Trap's mana
    value is four on the stack whatever was paid, so a "counter target spell
    with mana value 1 or less" never sees it.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = _bears_on_the_stack(scenario)

    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")
    trap = scenario.cast_onto_stack("Mindbreak Trap", *sources, username="alice", targets=[bears])

    assert trap.card.cmc == 4
    assert trap.card.mana_cost == "{2}{U}{U}"


def test_the_trap_can_be_cast_for_zero_after_three_opposing_spells():
    """CR 118.9: an alternative cost is "a cost ... that its controller may pay
    rather than paying the spell's mana cost", and CR 601.2f applies it when the
    total cost is determined.

    The condition the episode dwells on is reached here: one opponent, three
    spells this turn, the third still on the stack for the Trap to answer.
    `Casting.alternative_costs` reads the offer straight off the printed
    sentence now - no keyword names it - and `_condition_refusal` counts the
    spells off `Game.spells_cast_this_turn`.
    """
    scenario = (
        Scenario()
        .player(
            "bob",
            hand=["Lightning Bolt", "Lava Spike", "Grizzly Bears"],
            battlefield=["Mountain", "Mountain", "Forest", "Forest"],
        )
        .player(
            "alice",
            hand=["Mindbreak Trap"],
            battlefield=["Island", "Island", "Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for name, land in (("Lightning Bolt", "Mountain"), ("Lava Spike", "Mountain")):
        (source,) = scenario.untapped_sources(land, username="bob")
        scenario.cast_and_resolve(name, source, username="bob", targets=["alice"])
    bears = _bears_on_the_stack(scenario)

    casting = scenario.cast("Mindbreak Trap", username="alice")
    casting.use_pitch_cost()  # CR 601.2b, ahead of CR 601.2c's targets
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)

    assert str(payment.cost) == "{0}"
    assert scenario.stack_names() == ["Grizzly Bears", "Mindbreak Trap"]


# --------------------------------------------------------------------------
# Exiling a spell is not countering it (CR 701.6a)
# --------------------------------------------------------------------------


def test_the_targeted_spell_is_moved_from_the_stack_to_exile():
    """The episode's central distinction: the Trap exiles, it does not counter.

    CR 701.6a defines countering as cancelling a spell and putting it into its
    owner's graveyard. Exiling a spell moves it off the stack to exile instead,
    which is why nothing that watches for a spell being countered - and nothing
    that says it can't be countered - has anything to say about it.

    CR 406.2: "To exile an object is to put it into the exile zone from
    whatever zone it's currently in", and CR 701.13a says the same of the
    keyword action - neither names an origin zone, so the stack is as reachable
    as the battlefield. CR 107.1c is the quantifier: "If a rule or ability
    instructs a player to choose 'any number,' that player may choose any
    positive number or zero."
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = _bears_on_the_stack(scenario)

    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")
    scenario.cast_onto_stack("Mindbreak Trap", *sources, username="alice", targets=[bears])
    scenario.resolve_top()

    assert bears.zone is Zone.EXILE
    assert scenario.stack_names() == []


def test_a_spell_the_trap_failed_to_exile_was_not_countered_either():
    """The half of the distinction the engine *can* prove today.

    Whatever the Trap does or does not do to the creature spell, it is not a
    counter: CR 701.6a's counter puts the spell into its owner's graveyard and
    `Game.fizzled` records a spell removed from the stack without resolving.
    Neither happened here.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = _bears_on_the_stack(scenario)

    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", username="alice")
    scenario.cast_onto_stack("Mindbreak Trap", *sources, username="alice", targets=[bears])
    scenario.resolve_top()

    assert bears.zone is not Zone.GRAVEYARD
    assert bears.id not in scenario.game.fizzled
