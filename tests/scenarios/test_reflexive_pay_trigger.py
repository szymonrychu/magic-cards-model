"""Scenario: "you may pay `<mana>` and `<N>` life. When you do, ..." (CR
603.12's reflexive trigger, CR 118.3/119.4's payment) - a *combined*
mana-and-life cost, which neither the pure-mana nor the pure-life reflexive
reader already in place could parse, so the whole clause fell through to a
fail-closed notice.

Oracle text, pulled with `scripts/add_card.py` and verified against the
printings pool (every card Modern-legal):

- **Zoraline, Cosmos Caller**: "Flying, vigilance / Whenever a Bat you
  control attacks, you gain 1 life. / Whenever Zoraline enters or attacks,
  you may pay {W}{B} and 2 life. When you do, return target nonland
  permanent card with mana value 3 or less from your graveyard to the
  battlefield with a finality counter on it."
- **Ambulatory Edifice** (a second printing, not in the api deck pool):
  "When this creature enters, you may pay 2 life. When you do, target
  creature gets -1/-1 until end of turn." - proof of the pure-life sibling
  reader this file also adds, since nothing in the pool printed that shape
  either.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

ZORALINE = "Zoraline, Cosmos Caller"
EDIFICE = "Ambulatory Edifice"


def _questions(scenario: Scenario, kind: DecisionKind) -> list:
    return [q for q in scenario.questions_asked() if q.kind is kind]


def _zoraline_board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ZORALINE],
            graveyard=["Grizzly Bears"],
            battlefield=["Plains", "Swamp", "Forest", "Plains", "Swamp"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_zoraline_paying_returns_the_graveyard_creature_with_a_finality_counter():
    scenario = _zoraline_board()
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may(True, source=ZORALINE)
    life_before = scenario.player("alice").life

    (plains, swamp, forest) = scenario.untapped_sources("Plains", "Swamp", "Forest")
    scenario.cast_onto_stack(ZORALINE, plains, swamp, forest)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{ZORALINE}'s triggered ability"]
    scenario.choose_trigger_targets(ZORALINE, [bears])
    scenario.resolve_top()  # pays {W}{B} and 2 life, creates the reflexive ability
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{ZORALINE}'s triggered ability"]
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counter_count(Counter.FINALITY) == 1
    assert scenario.player("alice").life == life_before - 2


def test_zoraline_declining_creates_no_reflexive_ability():
    scenario = _zoraline_board()
    scenario.will_take_the_may(False, source=ZORALINE)
    life_before = scenario.player("alice").life

    (plains, swamp, forest) = scenario.untapped_sources("Plains", "Swamp", "Forest")
    scenario.cast_onto_stack(ZORALINE, plains, swamp, forest)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.stack_names() == []
    assert scenario.player("alice").life == life_before


def test_zoraline_cannot_pay_below_two_life():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ZORALINE],
            graveyard=["Grizzly Bears"],
            battlefield=["Plains", "Swamp", "Forest", "Plains", "Swamp"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.player("alice").life = 1

    (plains, swamp, forest) = scenario.untapped_sources("Plains", "Swamp", "Forest")
    scenario.cast_onto_stack(ZORALINE, plains, swamp, forest)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    (question,) = _questions(scenario, DecisionKind.MAY)
    assert question.affirmative_is_legal is False


def test_ambulatory_edifice_pure_life_reflexive_when_you_do():
    """A second printing: the pure-life "you may pay N life. When you do,
    ..." reflexive this file's reader also adds, proven on a shape with no
    mana component at all."""
    scenario = (
        Scenario()
        .player("alice", hand=[EDIFICE], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_take_the_may(True, source=EDIFICE)
    life_before = scenario.player("alice").life

    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    scenario.cast_onto_stack(EDIFICE, *swamps)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{EDIFICE}'s triggered ability"]
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{EDIFICE}'s triggered ability"]
    scenario.choose_trigger_targets(EDIFICE, [bears])
    scenario.resolve_top()

    assert scenario.player("alice").life == life_before - 2
    assert (scenario.game.power_of(bears), scenario.game.toughness_of(bears)) == (1, 1)
