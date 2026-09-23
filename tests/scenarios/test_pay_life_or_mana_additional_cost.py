"""CR 601.2b's "[cost] or pay [mana]" additional cost, when the non-mana
side is a life payment rather than an object to nominate (CR 118.8a).

Redirect Lightning: "As an additional cost to cast this spell, pay 5 life or
pay {2}." `Casting._additional_cost_primary_alternatives` infers which side
of an "or pay" sentence the caster is paying from whether objects were
nominated for it - `sacrificing=[...]` already says "pay the sacrifice
half" with no separate flag, the same way `blighted` does for "blight N or
pay {M}". A life payment has no object to nominate at all, so that
inference always saw an empty pool for `ComponentKind.PAY_LIFE` and fell
through to the mana half regardless of what the caster wanted - the payer
could never choose to pay life instead.

`Casting.paying_life_for_additional_cost` is the explicit twin of that
object-pool inference for exactly this shape: an index into
`additional_cost_phrases`, set by the caster, that `_additional_cost_
primary_alternatives` now also treats as "chosen" for a `PAY_LIFE` primary.

The choice is announced on every casting surface, not only on a hand-driven
`Casting`: `Game.cast(pay_life_for_additional_cost=True)` is the atomic seat
path, `Action.additional_cost_options` tells a seat the choice exists, and a
cast the engine makes on a player's behalf during resolution (CR 608.2g - a
cascade hit) asks the caster the same question (CR 601.2b) before CR 601.2f
determines the total cost.

Redirect Lightning is the only printing with a life-or-mana additional cost
in Modern, Pioneer or Standard (Scryfall search, 2026-09-23), so there is no
second printing of this exact template to prove on; the life half rides on
the general "[cost] or pay [mana]" reader every other "or pay" sentence uses.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: CR 601.2b (additional costs announced with the spell), CR 601.2f
(total cost), CR 118.8a (an additional cost the caster may choose among),
CR 119.4 (life may be paid only up to the life total), CR 118.3 (a cost that
cannot be paid fully cannot be paid), CR 733.1 (an illegal cast is reversed),
CR 608.2g (a spell cast during resolution follows CR 601.2a-i).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from tests.scenarios.harness import Scenario


def test_redirect_lightning_lets_the_caster_pay_life_instead_of_mana():
    """Paying the life half: 5 life and {R} (the spell's own mana cost) -
    not {R}{2}, which is what the old, always-mana default would demand."""
    scenario = (
        Scenario()
        .player("alice", hand=["Redirect Lightning"], battlefield=["Mountain"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", bob_mountain, username="bob", targets=["alice"]
    )
    life_before = scenario.player("alice").life

    casting = scenario.cast("Redirect Lightning", username="alice", targets=[bolt])
    casting.paying_life_for_additional_cost = frozenset({0})
    payment = casting.begin_paying()
    (alice_mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.pay_with(payment, alice_mountain)

    assert scenario.player("alice").life == life_before - 5
    assert alice_mountain.tapped


def test_redirect_lightning_still_defaults_to_paying_mana():
    """The other side of the same fix: leaving the choice unset still pays
    the mana half, exactly as before - the fix must not have flipped the
    default."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Redirect Lightning"], battlefield=["Mountain", "Mountain", "Mountain"]
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", bob_mountain, username="bob", targets=["alice"]
    )
    life_before = scenario.player("alice").life

    casting = scenario.cast("Redirect Lightning", username="alice", targets=[bolt])
    payment = casting.begin_paying()
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    scenario.pay_with(payment, *sources)

    assert scenario.player("alice").life == life_before
    assert all(source.tapped for source in sources)


def redirect_board(*alice_lands: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Redirect Lightning"], battlefield=list(alice_lands))
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )


def bob_bolts_alice(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", bob_mountain, username="bob", targets=["alice"]
    )
    scenario.pass_priority("bob")
    return bolt


def test_the_atomic_cast_announces_the_life_half():
    """`Game.cast` is the seat's own atomic path (CR 601.2): announcing the
    life half there pays 5 life and only the spell's {R}."""
    scenario = redirect_board("Mountain", "Mountain", "Mountain")
    bolt = bob_bolts_alice(scenario)
    alice_mountains = scenario.untapped_sources(
        "Mountain", "Mountain", "Mountain", username="alice"
    )

    scenario.game.cast(
        scenario.find("Redirect Lightning", Zone.HAND, "alice"),
        "alice",
        targets=[bolt],
        pay_life_for_additional_cost=True,
        mana_sources=alice_mountains,
    )

    assert scenario.player("alice").life == 15
    assert sum(land.tapped for land in alice_mountains) == 1
    assert scenario.stack_names() == ["Lightning Bolt", "Redirect Lightning"]


def test_the_atomic_cast_defaults_to_the_mana_half():
    scenario = redirect_board("Mountain", "Mountain", "Mountain")
    bolt = bob_bolts_alice(scenario)
    alice_mountains = scenario.untapped_sources(
        "Mountain", "Mountain", "Mountain", username="alice"
    )

    scenario.game.cast(
        scenario.find("Redirect Lightning", Zone.HAND, "alice"),
        "alice",
        targets=[bolt],
        mana_sources=alice_mountains,
    )

    assert scenario.player("alice").life == 20
    assert all(land.tapped for land in alice_mountains)


def test_life_above_the_total_cannot_be_paid_and_the_cast_is_reversed():
    """CR 119.4: life may be paid "only if their life total is greater than or
    equal to the amount". At 4 life the life half is not payable (CR 118.3),
    and CR 733.1 reverses the whole cast: the card is back in hand, nothing is
    tapped, no life is lost."""
    scenario = redirect_board("Mountain", "Mountain", "Mountain")
    bolt = bob_bolts_alice(scenario)
    scenario.player("alice").life = 4
    alice_mountains = scenario.untapped_sources(
        "Mountain", "Mountain", "Mountain", username="alice"
    )
    redirect = scenario.find("Redirect Lightning", Zone.HAND, "alice")

    with pytest.raises(ValueError):
        scenario.game.cast(
            redirect,
            "alice",
            targets=[bolt],
            pay_life_for_additional_cost=True,
            mana_sources=alice_mountains,
        )

    assert redirect.zone is Zone.HAND
    assert scenario.player("alice").life == 4
    assert not any(land.tapped for land in alice_mountains)


def test_exactly_the_life_total_can_be_paid():
    """CR 119.4's "greater than or equal to": at exactly 5 life the life half
    is payable."""
    scenario = redirect_board("Mountain")
    bolt = bob_bolts_alice(scenario)
    scenario.player("alice").life = 5

    scenario.game.cast(
        scenario.find("Redirect Lightning", Zone.HAND, "alice"),
        "alice",
        targets=[bolt],
        pay_life_for_additional_cost=True,
        mana_sources=scenario.untapped_sources("Mountain", username="alice"),
    )

    assert scenario.player("alice").life == 0


def test_the_cast_action_tells_the_seat_the_choice_exists():
    """CR 601.2b: the caster announces which half. `legal_actions` names it on
    the cast action, printed as the card prints it, so a seat can announce
    it rather than only ever paying the default - under a keyword it can
    name back, since a keyword-less option has nothing a seat can send."""
    scenario = redirect_board("Mountain", "Mountain", "Mountain")
    bob_bolts_alice(scenario)

    (action,) = [
        action for action in legal_actions(scenario.game, "alice") if action.kind is ActionKind.CAST
    ]

    (option,) = action.additional_cost_options
    assert option.cost == "pay 5 life or pay {2}"
    assert option.keyword == "pay life"
    assert option.understood
    assert option.rule == "CR 601.2b"


def outburst_board(*alice_lands: str) -> Scenario:
    """Bob bolts Alice; Alice answers with Violent Outburst, whose cascade
    (CR 702.85a) turns up Redirect Lightning."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Violent Outburst"],
            library=["Redirect Lightning"],
            battlefield=["Forest", "Mountain", "Forest", *alice_lands],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )


def cascade_into_redirect(scenario):
    bolt = bob_bolts_alice(scenario)
    scenario.will_take_the_may(True, source="Violent Outburst")
    scenario.will_choose_targets(bolt, source="Redirect Lightning")
    scenario.cast_onto_stack(
        "Violent Outburst",
        *scenario.untapped_sources("Forest", "Mountain", "Forest", username="alice"),
        username="alice",
    )
    return bolt


def test_a_cascaded_redirect_asks_which_half_and_pays_life():
    """CR 608.2g: a spell cast during resolution follows CR 601.2a-i, so the
    caster announces the life half here too - asked, not assumed."""
    scenario = outburst_board()
    cascade_into_redirect(scenario)
    scenario.will_take_the_may(True, source="Redirect Lightning")

    scenario.resolve_top()  # the cascade trigger

    questions = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.MAY and q.source == "Redirect Lightning"
    ]
    assert len(questions) == 1
    assert "5 life" in questions[0].prompt
    assert scenario.player("alice").life == 15
    assert "Redirect Lightning" in scenario.stack_names()


def test_a_cascaded_redirect_declining_the_life_pays_the_mana():
    scenario = outburst_board("Mountain", "Mountain")
    cascade_into_redirect(scenario)
    scenario.will_take_the_may(False, source="Redirect Lightning")

    scenario.resolve_top()

    assert scenario.player("alice").life == 20
    assert "Redirect Lightning" in scenario.stack_names()
    assert not scenario.untapped_sources(username="alice")


def test_a_cascaded_redirect_below_five_life_is_offered_the_life_as_illegal():
    """CR 119.4/CR 608.2d: at 4 life the "yes" is impossible, so it is offered
    as an illegal answer and the mana half is paid instead."""
    scenario = outburst_board("Mountain", "Mountain")
    cascade_into_redirect(scenario)
    scenario.player("alice").life = 4

    scenario.resolve_top()

    (question,) = [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.MAY and q.source == "Redirect Lightning"
    ]
    assert question.affirmative_is_legal is False
    assert scenario.player("alice").life == 4
    assert "Redirect Lightning" in scenario.stack_names()
