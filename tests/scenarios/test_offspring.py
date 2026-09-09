"""Offspring: CR 702.175a's additional cost plus its linked ETB trigger.

"Offspring [cost]" is two abilities: an optional additional cost
(`machines/casting.py`'s `Casting.pay_offspring`, CR 118.8a) and, if that cost
was paid, "when this permanent enters, create a token that's a copy of it,
except it's 1/1" (`machines/keywords._offspring_ability`, read generically
off `CastRecord.offspring_paid` the same way evoke reads `CastRecord.
keyword`). Proved on Darkstar Augur - a colored, single-symbol offspring cost
and a flying creature, unlike Thundertrap Trainer's generic {4} - which is
outside the deck pool and outside this wave's brief.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from tests.scenarios.harness import Scenario


def test_paying_offspring_creates_a_1_1_copy():
    """Darkstar Augur: "Offspring {B} ... Flying." Paying the offspring cost
    makes a 1/1 token copy with flying - the copy's own printed keyword, not
    a stub.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Darkstar Augur"], battlefield=["Swamp"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")

    casting = scenario.cast("Darkstar Augur", username="alice")
    casting.pay_offspring()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    originals = [
        state
        for state in scenario.game.battlefield
        if state.name == "Darkstar Augur" and not state.token
    ]
    copies = [
        state
        for state in scenario.game.battlefield
        if state.name == "Darkstar Augur" and state.token
    ]
    assert len(originals) == 1
    assert len(copies) == 1
    (copy,) = copies
    assert scenario.game.power_of(copy) == 1
    assert scenario.game.toughness_of(copy) == 1
    assert has_keyword(copy, Keyword.FLYING, scenario.game)


def test_declining_offspring_creates_no_copy():
    """CR 702.175a's cost is optional (CR 118.8a): nothing paid, nothing
    created, and the intervening *if* fails closed rather than defaulting to
    a free copy.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Darkstar Augur"], battlefield=["Swamp"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")

    scenario.cast_and_resolve("Darkstar Augur", *sources, username="alice")

    copies = [
        state
        for state in scenario.game.battlefield
        if state.name == "Darkstar Augur" and state.token
    ]
    assert copies == []
