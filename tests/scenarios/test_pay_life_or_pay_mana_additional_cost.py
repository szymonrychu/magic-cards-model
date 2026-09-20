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

CR numbers verified with `mise run rules:find` in the session that wrote
this file: CR 601.2b (additional costs announced with the spell), CR 118.8a
(an additional cost the caster may choose among).
"""

from magic_cards_model.machines import Step
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
