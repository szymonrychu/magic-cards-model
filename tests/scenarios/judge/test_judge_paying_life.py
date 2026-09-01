"""Judge scenarios: life as a *cost* against life as an *effect*.

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#964** - Leyline of Punishment vs. Armistice. An activated ability's
  colon is the cost/effect boundary (CR 602.1a): a life payment printed before
  it must actually be payable, while a life *gain* printed after it is an
  instruction that simply does as much as possible (CR 609.3, CR 101.3).
- **DDR#958** - Children of Korlis + Bolas's Citadel. Paying life is losing
  life, so a cost paid in life feeds "the life you've lost this turn" exactly
  the way damage does.

Both episodes rest on the same fact, from opposite sides: a life payment is a
subtraction from the life total (CR 118.3b) that the payer must be able to
afford (CR 118.3, CR 119.4), whereas an effect's life gain is just an
instruction.

Card text verified with `resolve_cards`; every CR number here was looked up
with `knowledge_search(type="rules")` in this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import CostKind, parse_abilities
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import Color
from tests.cards import card
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# DDR#964 - everything before the colon is the cost
# --------------------------------------------------------------------------


def test_the_colon_is_where_the_cost_stops_and_the_effect_starts():
    """DDR#964, the parser half: CR 602.1a, read off two real cards.

    CR 602.1: "Activated abilities have a cost and an effect. They are written
    as '[Cost]: [Effect.] [Activation instructions (if any).]'" CR 602.1a: "The
    activation cost is everything before the colon (:)."

    Mana Confluence prints "{T}, Pay 1 life: Add one mana of any color." - the
    life payment is *before* the colon, so it is part of what has to be paid.
    Armistice prints "{3}{W}{W}: You draw a card and target opponent gains 3
    life." - the life gain is *after* it, so it is an instruction performed on
    resolution and no part of the cost. That difference is the whole episode,
    and `machines/abilities.py` already splits both correctly.
    """
    (confluence,) = parse_abilities(card("Mana Confluence"))
    (armistice,) = parse_abilities(card("Armistice"))

    assert [component.kind for component in confluence.costs] == [
        CostKind.TAP,
        CostKind.PAY_LIFE,
    ]
    assert [component.kind for component in armistice.costs] == [CostKind.MANA]
    assert "gains 3 life" in armistice.effect
    assert "life" not in armistice.cost


def test_a_life_payment_in_the_cost_must_actually_be_payable():
    """DDR#964's Mana Confluence challenge question: a cost you cannot pay is a
    cost you cannot choose to pay, so the ability cannot be activated.

    CR 118.3: "A player can't pay a cost without having the necessary resources
    to pay it fully. For example, a player with only 1 life can't pay a cost of
    2 life". CR 119.4 says the same from the other side - a player may pay an
    amount of life greater than 0 "only if their life total is greater than or
    equal to the amount of the payment" - and CR 614.17b generalises it: "If an
    event can't happen, a player can't choose to pay a cost that includes that
    event."

    Alice sits at 0 life, which is a real board state until somebody would
    receive priority and the state-based action in CR 704.5a is checked
    (CR 104.3b). She cannot pay the 1 life, so `CostPayment.pay` refuses.

    The refusal now arrives before anything is announced: `Game.
    why_cannot_activate` consults the life cost too (CR 119.4, the section
    below), and `begin_activating` raises its answer. `CostPayment.pay` still
    refuses the same payment on its own, which is what an activation built by
    hand runs into.
    """
    scenario = (
        Scenario().player("alice", life=0, battlefield=["Mana Confluence"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    confluence = scenario.find("Mana Confluence", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError, match="cannot pay 1 life"):
        scenario.activate(confluence, username="alice", color=Color.GREEN)

    assert confluence.untapped, "the refused cost left the land untapped"


def test_armistices_life_gain_is_an_effect_paid_for_with_mana_alone():
    """DDR#964, the positive control: Armistice costs {3}{W}{W} and nothing
    else, and its opponent's life gain happens when the ability resolves.

    CR 602.1a puts "{3}{W}{W}" - and only that - in the cost. CR 608.2c has the
    controller follow the resolving ability's instructions in the order
    written, which here is "You draw a card and target opponent gains 3 life."

    This is the baseline the `xfail` below is measured against: with no effect
    saying otherwise, both halves of the instruction happen.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Armistice"] + ["Plains"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    armistice = scenario.find("Armistice", Zone.BATTLEFIELD, "alice")
    plains = scenario.untapped_sources(*["Plains"] * 5, username="alice")

    scenario.activate(armistice, *plains, username="alice", targets=["bob"])
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == 1
    assert scenario.player("bob").life == 23


def test_leyline_of_punishment_stops_only_the_life_gain_half():
    """DDR#964's actual question: with Leyline of Punishment out, Amy activates
    Armistice - she draws, her opponent gains nothing.

    Leyline of Punishment (verified with `resolve_cards`): "Players can't gain
    life. Damage can't be prevented." The gain is in Armistice's *effect*, not
    its cost, so CR 609.3 ("If an effect attempts to do something impossible,
    it does only as much as possible") and CR 101.3 ("Any part of an
    instruction that's impossible to perform is ignored") apply: the draw still
    happens, the life gain does not.

    The prohibition is **not** a CR 613 layer, which is why it was missing for
    so long while `machines/layers.py` was blamed for it: "Players can't gain
    life" changes no characteristic of any object, so the layers have nothing
    to write. It is CR 611.1's "affects players or the rules of the game", read
    back by CR 119.7, and it lives in `Game.life_gain_prohibited` - a fresh
    battlefield scan on every call, the same shape as
    `Game._activation_prohibition` (CR 604.2, CR 611.3a).
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Armistice"] + ["Plains"] * 5)
        .player("bob", battlefield=["Leyline of Punishment"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    armistice = scenario.find("Armistice", Zone.BATTLEFIELD, "alice")
    plains = scenario.untapped_sources(*["Plains"] * 5, username="alice")

    scenario.activate(armistice, *plains, username="alice", targets=["bob"])
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == 1, "the draw still happens"
    assert scenario.player("bob").life == 20, "the life gain does not"


# --------------------------------------------------------------------------
# DDR#958 - paying life is losing life
# --------------------------------------------------------------------------


def test_paying_life_lowers_the_life_total_the_same_way_damage_does():
    """DDR#958's premise: damage and a life payment are both life loss.

    CR 119.2: "Damage dealt to a player normally causes that player to lose
    that much life." CR 118.3b: "Paying life is done by subtracting the
    indicated amount of life from a player's life total."

    Two different routes, one arithmetic: alice takes a Lightning Bolt for 3
    and then pays 1 life to Mana Confluence, ending on 16. Nothing in the model
    treats the payment as a special kind of bookkeeping - it goes through the
    same life total, which is the fact Children of Korlis is built on.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mana Confluence", "Children of Korlis"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )

    assert alice.life == 17, "CR 119.2: the damage was a loss of 3 life"

    confluence = scenario.find("Mana Confluence", Zone.BATTLEFIELD, "alice")
    scenario.activate(confluence, username="alice", color=Color.GREEN)

    assert alice.life == 16, "CR 118.3b: the payment was a loss of 1 more"


def test_children_of_korlis_gives_back_the_life_paid_as_well_as_the_damage():
    """DDR#958's ruling: paying life counts for Children of Korlis, and it
    counts *gross*, not net.

    Children of Korlis (verified with `resolve_cards`): "Sacrifice this
    creature: You gain life equal to the life you've lost this turn. (Damage
    causes loss of life.)" The reminder text mentions only damage; the episode's
    point is that every route by which a life total goes down counts, the CR
    118.3b payment included.

    Alice takes 3 from a Bolt and pays 1 to Mana Confluence: 4 life lost this
    turn, so sacrificing Children of Korlis takes her from 16 back to 20.

    `Player.life_lost_this_turn` is the gross per-turn ledger both routes write
    to, and `machines/effects.parse_clause_effect` now reads it for the printed
    clause "You gain life equal to the life you've lost this turn."
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mana Confluence", "Children of Korlis"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )
    confluence = scenario.find("Mana Confluence", Zone.BATTLEFIELD, "alice")
    scenario.activate(confluence, username="alice", color=Color.GREEN)

    children = scenario.find("Children of Korlis", Zone.BATTLEFIELD, "alice")
    scenario.activate(children, username="alice", sacrificing=[children])
    scenario.resolve_top()

    assert alice.life == 20, "3 damage plus 1 paid is 4 life lost this turn"


# --------------------------------------------------------------------------
# DDR#964's smaller half - the advisory answer, not just the payment
# --------------------------------------------------------------------------


def test_why_cannot_activate_refuses_a_life_cost_the_player_cannot_afford():
    """CR 119.4, checked *before* the activation is begun.

    "If a cost or effect allows a player to pay an amount of life greater than
    0, the player may do so only if their life total is greater than or equal
    to the amount of the payment." CR 118.3 says the same from the resource
    side, and CR 614.17b makes it a restriction on choosing to pay at all: an
    event that can't happen is not one a player may choose to pay.

    Nurturing Peatland (verified with `resolve_cards`): "{T}, Pay 1 life: Add
    {B} or {G}." At 0 life alice cannot pay the 1, so the ability is not
    activatable and `why_cannot_activate` has to say so - an engine that offers
    it and only refuses once `{T}` is already announced is offering a play that
    does not exist.
    """
    scenario = (
        Scenario().player("alice", life=0, battlefield=["Nurturing Peatland"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    peatland = scenario.find("Nurturing Peatland", Zone.BATTLEFIELD, "alice")

    reason = scenario.why_cannot_activate(peatland, index=0)

    assert reason is not None
    assert "cannot pay 1 life" in reason, reason
    assert "CR 119.4" in reason, reason
    assert peatland.untapped


def test_the_same_ability_is_offered_at_a_life_total_that_can_pay_it():
    """The control: nothing about a life cost is refused when it is affordable.

    CR 119.4's condition is "greater than or equal to the amount", and 20 is
    comfortably that. The refusal above must be about the life total and only
    the life total.
    """
    scenario = Scenario().player("alice", battlefield=["Nurturing Peatland"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    peatland = scenario.find("Nurturing Peatland", Zone.BATTLEFIELD, "alice")

    assert scenario.why_cannot_activate(peatland, index=0) is None

    scenario.activate(peatland, username="alice", color=Color.BLACK)

    assert scenario.player("alice").life == 19
    assert peatland.tapped
    assert scenario.player("alice").mana_pool.total == 1


def test_paying_life_down_to_exactly_zero_is_legal():
    """The boundary, and it falls on the payable side.

    CR 119.4 permits the payment when the life total is "greater than or equal
    to the amount", so 1 life pays a cost of 1 life - the rule is not "must
    survive it". CR 704.5a ("If a player has 0 or less life, that player loses
    the game") is a *state-based action*, checked later, when a player would
    receive priority; it is not a restriction on paying.

    So the ability is activatable, the mana is produced, and alice sits at 0
    life holding it until state-based actions are checked.
    """
    scenario = (
        Scenario().player("alice", life=1, battlefield=["Nurturing Peatland"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    peatland = scenario.find("Nurturing Peatland", Zone.BATTLEFIELD, "alice")

    assert scenario.why_cannot_activate(peatland, index=0) is None, "CR 119.4 allows paying to 0"

    scenario.activate(peatland, username="alice", color=Color.GREEN)

    assert scenario.player("alice").life == 0
    assert scenario.player("alice").mana_pool.total == 1

    scenario.state_based_actions()

    assert "alice" in scenario.game.losers, "CR 704.5a, and only now"


def test_the_refusal_names_the_life_cost_rather_than_some_other_reason():
    """A wrong reason is its own defect: the second ability is unaffordable for
    a different reason, and must not be described as a life problem.

    Nurturing Peatland's other ability is "{1}, {T}, Sacrifice this land: Draw
    a card." - no life in the cost at all - so at 0 life the life check has
    nothing to say about it, and CR 119.4 must not be quoted at it.
    """
    scenario = (
        Scenario().player("alice", life=0, battlefield=["Nurturing Peatland"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    peatland = scenario.find("Nurturing Peatland", Zone.BATTLEFIELD, "alice")

    assert scenario.why_cannot_activate(peatland, index=1) is None, (
        "no life is paid by the draw ability, so nothing here refuses it"
    )
