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

    Note the smaller gap this exposes: `Game.why_cannot_activate` returns None
    here - it does not consult the life cost - so the refusal only arrives at
    payment time. Asserted on the raise rather than on the advisory answer.
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


@pytest.mark.xfail(
    reason="Leyline of Punishment's 'Players can't gain life.' is a static "
    "ability with no entry in machines/layers.LAYER_EFFECTS and no "
    "prohibition anywhere else, so Player.gain_life runs unimpeded",
    strict=True,
)
def test_leyline_of_punishment_stops_only_the_life_gain_half():
    """DDR#964's actual question: with Leyline of Punishment out, Amy activates
    Armistice - she draws, her opponent gains nothing.

    Leyline of Punishment (verified with `resolve_cards`): "Players can't gain
    life. Damage can't be prevented." The gain is in Armistice's *effect*, not
    its cost, so CR 609.3 ("If an effect attempts to do something impossible,
    it does only as much as possible") and CR 101.3 ("Any part of an
    instruction that's impossible to perform is ignored") apply: the draw still
    happens, the life gain does not.

    The engine has no way to express "players can't gain life" at all - it is a
    continuous effect in CR 613's layer system with no row in
    `machines/layers.LAYER_EFFECTS`, and `Player.gain_life` consults nothing -
    so bob gains the 3 life anyway.
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


@pytest.mark.xfail(
    reason="nothing records how much life a player lost this turn - Game has "
    "life_gained_this_turn (a set of usernames, CR 119.9) and no losing "
    "counterpart at all - so Children of Korlis gains 0",
    strict=True,
)
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

    The engine has no per-turn life-loss ledger. `Player.lose_life` and the
    `pay_life` cost component both write straight to `Player.life` and record
    nothing; `Game.life_gained_this_turn` is the only per-turn life fact that
    exists, and it is a set of usernames for CR 119.9's "you gained life this
    turn" triggers, not an amount. So the ability resolves and gains 0.
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
